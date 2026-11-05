import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query

from app.config import PAGE_LIMIT_DEFAULT, PAGE_LIMIT_MAX
from app.db import DbSession, SessionFactory
from app.deps import CurrentUser
from app.llm import LLM
from app.mailer import Mailer
from app.models.enums import ApprovalStatus
from app.orchestrator import engine
from app.schemas.common import Page
from app.schemas.workflows import ApprovalOut, DecisionIn
from app.services import approvals, outbound, procurement, support

router = APIRouter(prefix="/api/approvals", tags=["approvals"])
Limit = Annotated[int, Query(ge=1, le=PAGE_LIMIT_MAX)]


@router.get("")
def list_approvals(
    db: DbSession,
    user: CurrentUser,
    limit: Limit = PAGE_LIMIT_DEFAULT,
    cursor: str | None = None,
    status: ApprovalStatus | None = ApprovalStatus.pending,
) -> Page[ApprovalOut]:
    rows, next_cursor = approvals.list_approvals(db, user, limit, cursor, status)
    return Page(items=[ApprovalOut.model_validate(r) for r in rows], next_cursor=next_cursor)


@router.get("/{approval_id}")
def get_approval(approval_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ApprovalOut:
    return ApprovalOut.model_validate(approvals.get_approval(db, user, approval_id))


def _decide(
    approval_id: uuid.UUID,
    body: DecisionIn,
    approve: bool,
    db: DbSession,
    user: CurrentUser,
    llm: LLM,
    mailer: Mailer,
    factory: SessionFactory,
    background: BackgroundTasks,
) -> ApprovalOut:
    approval = approvals.decide(db, user, approval_id, approve=approve, comment=body.comment)
    support.apply_decision(db, approval, user)
    procurement.apply_decision(db, approval, user)
    outbound.apply_decision(db, approval, user, mailer)
    execution = engine.resume_after_decision(db, approval, user)
    if execution is not None:
        background.add_task(engine.advance_in_background, factory, execution.id, llm, user.id)
    return ApprovalOut.model_validate(approval)


@router.post("/{approval_id}/approve")
def approve(
    approval_id: uuid.UUID,
    body: DecisionIn,
    db: DbSession,
    user: CurrentUser,
    llm: LLM,
    mailer: Mailer,
    factory: SessionFactory,
    background: BackgroundTasks,
) -> ApprovalOut:
    return _decide(approval_id, body, True, db, user, llm, mailer, factory, background)


@router.post("/{approval_id}/reject")
def reject(
    approval_id: uuid.UUID,
    body: DecisionIn,
    db: DbSession,
    user: CurrentUser,
    llm: LLM,
    mailer: Mailer,
    factory: SessionFactory,
    background: BackgroundTasks,
) -> ApprovalOut:
    return _decide(approval_id, body, False, db, user, llm, mailer, factory, background)
