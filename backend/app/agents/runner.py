"""Runs agents and tools on behalf of a user, and writes an agent_tasks + audit_logs row for each.

The runner is where permissions, retries and the activity log are enforced — not the agents.
"""

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel
from pydantic_core import PydanticSerializationError, to_jsonable_python
from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.config import AGENT_RETRY_DELAYS_S
from app.errors import ApiError
from app.llm import LLMClient, LLMError
from app.models import AgentTask, User
from app.models.enums import Department, TaskStatus
from app.services import audit
from app.services.authz import can_access

ERROR_MAX_CHARS = 500


class ToolOwner(Protocol):
    """Anything that calls tools: an agent, or the orchestrator itself."""

    name: str
    department: Department
    tools: frozenset[str]


@dataclass(frozen=True)
class ToolUser:
    name: str
    department: Department
    tools: frozenset[str]


class AgentFailed(ApiError):
    def __init__(self, agent: str, reason: str) -> None:
        super().__init__(502, "agent_failed", f"{agent} failed: {reason}")


@dataclass
class TaskContext:
    """Who triggered the work, and (for workflows) which execution and step it belongs to."""

    actor: User
    execution_id: Any = None
    step_id: Any = None
    sleep: Callable[[float], None] = field(default=time.sleep)


def input_hash(data: Any) -> str:
    payload = json.dumps(to_jsonable_python(data), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _check_permission(ctx: TaskContext, agent: ToolOwner) -> None:
    write = getattr(agent, "requires_write", True)
    if not can_access(ctx.actor, agent.department, write=write):
        raise ApiError(403, "forbidden", f"Your role cannot run {agent.name}")


def _start_task(
    db: Session, ctx: TaskContext, agent: ToolOwner, tool: str | None, data: Any, attempt: int
) -> AgentTask:
    task = AgentTask(
        agent=agent.name,
        tool=tool,
        execution_id=ctx.execution_id,
        step_id=ctx.step_id,
        triggered_by_id=ctx.actor.id,
        input_hash=input_hash(data),
        attempt=attempt,
        status=TaskStatus.running,
    )
    db.add(task)
    db.flush()
    return task


def _finish(
    db: Session,
    task: AgentTask,
    started: float,
    *,
    output: Any = None,
    error: str | None = None,
) -> None:
    task.duration_ms = int((time.monotonic() - started) * 1000)
    task.status = TaskStatus.failed if error else TaskStatus.succeeded
    task.output = to_jsonable_python(output) if output is not None else None
    task.error = error[:ERROR_MAX_CHARS] if error else None
    kind = "tool" if task.tool else "agent"
    audit.record(
        db,
        action=f"{kind}.{'failed' if error else 'succeeded'}",
        entity="agent_task",
        entity_id=task.id,
        actor_id=task.triggered_by_id,
        detail={"agent": task.agent, "tool": task.tool, "attempt": task.attempt},
    )
    db.commit()


def run_agent[Out: BaseModel](
    db: Session, agent: Agent[Any, Out], data: BaseModel, llm: LLMClient, ctx: TaskContext
) -> Out:
    """Run with up to two retries on retryable LLM errors. Raises AgentFailed when exhausted."""
    _check_permission(ctx, agent)
    attempts = 1 + len(AGENT_RETRY_DELAYS_S)
    for attempt in range(1, attempts + 1):
        task = _start_task(db, ctx, agent, None, data, attempt)
        started = time.monotonic()
        try:
            output = agent.run(data, llm)
        except LLMError as exc:
            _finish(db, task, started, error=str(exc))
            if not exc.retryable or attempt == attempts:
                raise AgentFailed(agent.name, str(exc)) from exc
            ctx.sleep(AGENT_RETRY_DELAYS_S[attempt - 1])
            continue
        _finish(db, task, started, output=output)
        return output
    raise AssertionError("unreachable")


def call_tool[R](
    db: Session,
    agent: ToolOwner,
    tool: str,
    args: dict[str, Any],
    fn: Callable[[], R],
    ctx: TaskContext,
) -> R:
    """Run one allowlisted tool (a service function) for an agent, and log it."""
    if tool not in agent.tools:
        raise RuntimeError(f"{agent.name} is not allowed to call {tool}")
    _check_permission(ctx, agent)
    task = _start_task(db, ctx, agent, tool, args, attempt=1)
    started = time.monotonic()
    try:
        result = fn()
    except Exception as exc:
        db.rollback()
        db.add(task)
        _finish(db, task, started, error=f"{type(exc).__name__}: {exc}")
        raise
    _finish(db, task, started, output=_summary(result))
    return result


def _summary(result: Any) -> Any:
    """What a tool returned, in a form that fits the activity log (never raw database rows)."""
    if isinstance(result, BaseModel):
        return result.model_dump(mode="json")
    if isinstance(result, str):
        return {"chars": len(result)}
    if isinstance(result, list | tuple):
        if all(isinstance(item, BaseModel) for item in result):
            return [item.model_dump(mode="json") for item in result]
        return {"count": len(result)}
    if result is None or isinstance(result, int | float | bool | dict):
        try:
            return to_jsonable_python(result)
        except PydanticSerializationError:
            return {"type": type(result).__name__}
    return {"type": type(result).__name__}
