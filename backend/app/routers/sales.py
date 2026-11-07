import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.agents.runner import TaskContext
from app.config import PAGE_LIMIT_DEFAULT, PAGE_LIMIT_MAX
from app.db import DbSession
from app.deps import CurrentUser, require_department
from app.llm import LLM
from app.mailer import Mailer
from app.models.enums import Department, LeadRating, LeadStatus
from app.schemas.common import Page
from app.schemas.outreach import EmailDraftUpdate, OutboundEmailOut
from app.schemas.sales import LeadCreate, LeadOut, LeadUpdate, SalesSummary
from app.services import outbound, outreach, sales

router = APIRouter(
    prefix="/api/sales",
    tags=["sales"],
    dependencies=[Depends(require_department(Department.sales))],
)
Limit = Annotated[int, Query(ge=1, le=PAGE_LIMIT_MAX)]


@router.get("/summary")
def sales_summary(db: DbSession) -> SalesSummary:
    """Funnel stage totals and weekly trend lines for the Sales page (read-only)."""
    return sales.summary(db)


@router.get("/leads")
def list_leads(
    db: DbSession,
    limit: Limit = PAGE_LIMIT_DEFAULT,
    cursor: str | None = None,
    status: LeadStatus | None = None,
    rating: LeadRating | None = None,
) -> Page[LeadOut]:
    rows, next_cursor = sales.list_leads(db, limit, cursor, status, rating)
    return Page(items=[LeadOut.model_validate(r) for r in rows], next_cursor=next_cursor)


@router.post("/leads", status_code=201)
def create_lead(data: LeadCreate, db: DbSession, user: CurrentUser) -> LeadOut:
    return LeadOut.model_validate(sales.create_lead(db, data, user))


@router.get("/leads/{lead_id}")
def get_lead(lead_id: uuid.UUID, db: DbSession) -> LeadOut:
    return LeadOut.model_validate(sales.get_lead(db, lead_id))


@router.patch("/leads/{lead_id}")
def update_lead(lead_id: uuid.UUID, data: LeadUpdate, db: DbSession, user: CurrentUser) -> LeadOut:
    return LeadOut.model_validate(sales.update_lead(db, lead_id, data, user))


@router.post("/leads/{lead_id}/qualify")
def qualify_lead(lead_id: uuid.UUID, db: DbSession, user: CurrentUser, llm: LLM) -> LeadOut:
    """Lead Qualifier: hot / warm / cold with a reason and the lead fields it relied on."""
    return LeadOut.model_validate(sales.qualify_lead(db, llm, lead_id, TaskContext(actor=user)))


@router.get("/leads/{lead_id}/emails")
def list_lead_emails(lead_id: uuid.UUID, db: DbSession) -> list[OutboundEmailOut]:
    return [OutboundEmailOut.model_validate(e) for e in outreach.list_for_lead(db, lead_id)]


@router.post("/leads/{lead_id}/emails", status_code=201)
def draft_lead_email(
    lead_id: uuid.UUID, db: DbSession, user: CurrentUser, llm: LLM
) -> OutboundEmailOut:
    """Outreach Writer drafts a first email. Nothing is sent until a sales manager approves."""
    email = outreach.draft_for_lead(db, llm, lead_id, TaskContext(actor=user))
    return OutboundEmailOut.model_validate(email)


@router.patch("/emails/{email_id}")
def edit_email(
    email_id: uuid.UUID, data: EmailDraftUpdate, db: DbSession, user: CurrentUser
) -> OutboundEmailOut:
    return OutboundEmailOut.model_validate(
        outbound.update_draft(db, email_id, Department.sales, data, user)
    )


@router.post("/emails/{email_id}/request-approval")
def request_email_approval(
    email_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> OutboundEmailOut:
    return OutboundEmailOut.model_validate(outreach.request_approval(db, email_id, user))


@router.post("/emails/{email_id}/retry")
def retry_email(
    email_id: uuid.UUID, db: DbSession, user: CurrentUser, mailer: Mailer
) -> OutboundEmailOut:
    return OutboundEmailOut.model_validate(
        outbound.retry(db, email_id, Department.sales, user, mailer)
    )
