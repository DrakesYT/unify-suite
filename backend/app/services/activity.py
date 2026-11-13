"""The agent activity log (FR-LOG-01): every agent and tool call, newest first."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentTask, User, WorkflowExecution, WorkflowStep
from app.models.enums import Role, TaskStatus
from app.orchestrator import engine
from app.schemas.workflows import Handoff, HandoffNode
from app.services.pagination import paginate

# Workflow B in the order work really changes hands: (step key, label, kind).
HANDOFF = (
    ("F1", "Invoice Processor", "agent"),
    ("F2", "PO match", "rules"),
    ("A1", "Manager approval", "human"),
    ("F4", "Payment", "tool"),
    ("V1", "Verification", "rules"),
)


def latest_handoff(db: Session, user: User) -> Handoff | None:
    """The newest supplier-payment run the caller may see, one node per hand-off stop."""
    stmt = select(WorkflowExecution).order_by(WorkflowExecution.created_at.desc()).limit(1)
    if user.role == Role.employee:  # same rule as the activity log: your own runs
        stmt = stmt.where(WorkflowExecution.started_by_id == user.id)
    execution = db.scalar(stmt)
    if execution is None:
        return None
    steps = engine.steps_of(db, execution)
    return Handoff(
        execution_id=execution.id,
        status=execution.status,
        file_name=execution.input.get("file_name"),
        updated_at=execution.updated_at,
        nodes=[
            HandoffNode(
                key=key,
                label=label,
                kind=kind,
                status=steps[key].status,
                attempts=steps[key].attempts,
                duration_ms=_duration_ms(steps[key]),
            )
            for key, label, kind in HANDOFF
        ],
    )


def _duration_ms(step: WorkflowStep) -> int | None:
    if step.started_at is None or step.finished_at is None:
        return None
    return round((step.finished_at - step.started_at).total_seconds() * 1000)


def list_tasks(
    db: Session,
    user: User,
    limit: int,
    cursor: str | None,
    *,
    execution_id: uuid.UUID | None = None,
    status: TaskStatus | None = None,
) -> tuple[list[AgentTask], str | None]:
    stmt = select(AgentTask)
    if user.role == Role.employee:  # employees see the work they triggered
        stmt = stmt.where(AgentTask.triggered_by_id == user.id)
    if execution_id:
        stmt = stmt.where(AgentTask.execution_id == execution_id)
    if status:
        stmt = stmt.where(AgentTask.status == status)
    return paginate(db, stmt, AgentTask, limit, cursor)
