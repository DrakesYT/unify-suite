"""The agent activity log (FR-LOG-01): every agent and tool call, newest first."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentTask, User
from app.models.enums import Role, TaskStatus
from app.services.pagination import paginate


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
