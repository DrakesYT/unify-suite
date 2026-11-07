import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.config import PAGE_LIMIT_DEFAULT, PAGE_LIMIT_MAX
from app.db import DbSession
from app.deps import CurrentUser
from app.models.enums import TaskStatus
from app.schemas.common import Page
from app.schemas.workflows import AgentTaskOut, LatestHandoff
from app.services import activity

router = APIRouter(prefix="/api/agents", tags=["agents"])
Limit = Annotated[int, Query(ge=1, le=PAGE_LIMIT_MAX)]


@router.get("/handoff")
def agent_handoff(db: DbSession, user: CurrentUser) -> LatestHandoff:
    """The newest supplier-payment run as a hand-off between agents, rules, a human and a tool."""
    return LatestHandoff(run=activity.latest_handoff(db, user))


@router.get("/activity")
def agent_activity(
    db: DbSession,
    user: CurrentUser,
    limit: Limit = PAGE_LIMIT_DEFAULT,
    cursor: str | None = None,
    execution_id: uuid.UUID | None = None,
    status: TaskStatus | None = None,
) -> Page[AgentTaskOut]:
    """Every agent call and tool call, newest first (FR-LOG-01)."""
    rows, next_cursor = activity.list_tasks(
        db, user, limit, cursor, execution_id=execution_id, status=status
    )
    return Page(items=[AgentTaskOut.model_validate(r) for r in rows], next_cursor=next_cursor)
