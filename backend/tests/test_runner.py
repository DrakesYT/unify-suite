"""FR-LOG-01 and the retry policy: every agent and tool call leaves an agent_tasks row."""

from collections.abc import Callable
from typing import ClassVar

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import runner
from app.agents.base import Agent
from app.agents.runner import AgentFailed, TaskContext, call_tool, input_hash, run_agent
from app.errors import ApiError
from app.llm import LLMClient, LLMError
from app.llm.fake import FakeLLMClient
from app.models import AgentTask, AuditLog, User
from app.models.enums import Department, Role, TaskStatus


class EchoIn(BaseModel):
    text: str


class EchoOut(BaseModel):
    reply: str


class EchoAgent(Agent[EchoIn, EchoOut]):
    name: ClassVar[str] = "echo"
    department = Department.finance
    input_model = EchoIn
    output_model = EchoOut
    tools = frozenset({"lookup"})
    max_llm_calls = 1
    timeout_s = 5.0

    def run(self, data: EchoIn, llm: LLMClient) -> EchoOut:
        return llm.complete_json(EchoOut, "echo", data.text, timeout_s=self.timeout_s)


@pytest.fixture
def ctx(make_user: Callable[..., User]) -> TaskContext:
    return TaskContext(actor=make_user(Role.employee, Department.finance))


def _tasks(db: Session) -> list[AgentTask]:
    return list(db.scalars(select(AgentTask).order_by(AgentTask.attempt)))


def test_success_writes_one_task_and_audit_row(db: Session, ctx: TaskContext) -> None:
    llm = FakeLLMClient(replies=[{"reply": "hi"}])

    out = run_agent(db, EchoAgent(), EchoIn(text="hello"), llm, ctx)

    assert out == EchoOut(reply="hi")
    [task] = _tasks(db)
    assert task.agent == "echo" and task.tool is None
    assert task.status == TaskStatus.succeeded
    assert task.output == {"reply": "hi"}
    assert task.input_hash == input_hash(EchoIn(text="hello")) and len(task.input_hash) == 64
    assert task.duration_ms is not None and task.triggered_by_id == ctx.actor.id
    assert db.scalar(select(AuditLog.action)) == "agent.succeeded"


def test_invalid_output_is_retried(
    db: Session, ctx: TaskContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "AGENT_RETRY_DELAYS_S", (2, 8))
    waits: list[float] = []
    ctx.sleep = waits.append
    llm = FakeLLMClient(replies=["not json", {"reply": "second time"}])

    assert run_agent(db, EchoAgent(), EchoIn(text="x"), llm, ctx).reply == "second time"
    assert [(t.attempt, t.status) for t in _tasks(db)] == [
        (1, TaskStatus.failed),
        (2, TaskStatus.succeeded),
    ]
    assert waits == [2]


def test_exhausted_retries_fail_the_task(
    db: Session, ctx: TaskContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "AGENT_RETRY_DELAYS_S", (2, 8))
    waits: list[float] = []
    ctx.sleep = waits.append
    llm = FakeLLMClient(replies=["bad", "bad", "bad"])

    with pytest.raises(AgentFailed) as exc:
        run_agent(db, EchoAgent(), EchoIn(text="x"), llm, ctx)
    assert exc.value.status_code == 502
    assert [t.status for t in _tasks(db)] == [TaskStatus.failed] * 3
    assert waits == [2, 8]
    assert all(t.error for t in _tasks(db))


def test_non_retryable_error_stops_at_once(db: Session, ctx: TaskContext) -> None:
    llm = FakeLLMClient(replies=[LLMError("bad key", retryable=False)])

    with pytest.raises(AgentFailed):
        run_agent(db, EchoAgent(), EchoIn(text="x"), llm, ctx)
    assert len(_tasks(db)) == 1


def test_user_from_another_department_cannot_run_the_agent(
    db: Session, make_user: Callable[..., User]
) -> None:
    ctx = TaskContext(actor=make_user(Role.employee, Department.sales))

    with pytest.raises(ApiError) as exc:
        run_agent(db, EchoAgent(), EchoIn(text="x"), FakeLLMClient(), ctx)
    assert exc.value.status_code == 403
    assert _tasks(db) == []


def test_tool_calls_are_logged_and_allowlisted(db: Session, ctx: TaskContext) -> None:
    assert call_tool(db, EchoAgent(), "lookup", {"id": 1}, lambda: {"found": True}, ctx) == {
        "found": True
    }
    [task] = _tasks(db)
    assert (task.tool, task.status, task.output) == (
        "lookup",
        TaskStatus.succeeded,
        {"found": True},
    )

    with pytest.raises(RuntimeError, match="not allowed"):
        call_tool(db, EchoAgent(), "delete_everything", {}, lambda: None, ctx)


def test_failing_tool_is_logged(db: Session, ctx: TaskContext) -> None:
    def _boom() -> None:
        raise ValueError("no such row")

    with pytest.raises(ValueError):
        call_tool(db, EchoAgent(), "lookup", {"id": 2}, _boom, ctx)
    [task] = _tasks(db)
    assert task.status == TaskStatus.failed
    assert task.error == "ValueError: no such row"
