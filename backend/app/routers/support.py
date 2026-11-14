import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.agents.runner import TaskContext
from app.config import PAGE_LIMIT_DEFAULT, PAGE_LIMIT_MAX
from app.db import DbSession
from app.deps import CurrentUser, require_department
from app.llm import LLM
from app.mailer import Mailer
from app.models.enums import Department, TicketCategory, TicketStatus
from app.schemas.common import Page
from app.schemas.outreach import EmailDraftUpdate, OutboundEmailOut
from app.schemas.support import (
    CustomerOut,
    EscalateIn,
    EscalationOut,
    OrderOut,
    StaffOut,
    TicketCreate,
    TicketNote,
    TicketOut,
    TicketUpdate,
)
from app.schemas.workflows import ApprovalOut
from app.services import outbound, support

router = APIRouter(
    prefix="/api/support",
    tags=["support"],
    dependencies=[Depends(require_department(Department.support))],
)
Limit = Annotated[int, Query(ge=1, le=PAGE_LIMIT_MAX)]


@router.get("/customers")
def list_customers(db: DbSession) -> list[CustomerOut]:
    return [CustomerOut.model_validate(c) for c in support.list_customers(db)]


@router.get("/customers/{customer_id}/orders")
def customer_orders(customer_id: uuid.UUID, db: DbSession) -> list[OrderOut]:
    return [OrderOut.model_validate(o) for o in support.customer_orders(db, customer_id)]


@router.get("/tickets")
def list_tickets(
    db: DbSession,
    limit: Limit = PAGE_LIMIT_DEFAULT,
    cursor: str | None = None,
    status: TicketStatus | None = None,
    category: TicketCategory | None = None,
) -> Page[TicketOut]:
    rows, next_cursor = support.list_tickets(db, limit, cursor, status, category)
    return Page(items=[TicketOut.model_validate(r) for r in rows], next_cursor=next_cursor)


@router.post("/tickets", status_code=201)
def create_ticket(data: TicketCreate, db: DbSession, user: CurrentUser, llm: LLM) -> TicketOut:
    """Saves the ticket, then the Ticket Investigator sets category and urgency."""
    return TicketOut.model_validate(support.create_ticket(db, llm, data, TaskContext(actor=user)))


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: uuid.UUID, db: DbSession) -> TicketOut:
    return TicketOut.model_validate(support.get_ticket(db, ticket_id))


@router.post("/tickets/{ticket_id}/classify")
def classify_ticket(ticket_id: uuid.UUID, db: DbSession, user: CurrentUser, llm: LLM) -> TicketOut:
    ticket = support.get_ticket(db, ticket_id)
    return TicketOut.model_validate(support.classify(db, llm, ticket, TaskContext(actor=user)))


@router.post("/tickets/{ticket_id}/investigate")
def investigate_ticket(
    ticket_id: uuid.UUID, db: DbSession, user: CurrentUser, llm: LLM
) -> TicketOut:
    """Likely causes from the customer's order history; cited orders are checked by code."""
    return TicketOut.model_validate(
        support.investigate(db, llm, ticket_id, TaskContext(actor=user))
    )


@router.post("/tickets/{ticket_id}/escalate")
def escalate_ticket(
    ticket_id: uuid.UUID, body: EscalateIn, db: DbSession, user: CurrentUser
) -> EscalationOut:
    """Refund and legal tickets create an approval request for a support manager."""
    ticket, approval = support.escalate(db, ticket_id, body.note, user, body.order_number)
    return EscalationOut(
        ticket=TicketOut.model_validate(ticket),
        approval=ApprovalOut.model_validate(approval) if approval else None,
    )


@router.patch("/tickets/{ticket_id}")
def update_ticket(
    ticket_id: uuid.UUID, data: TicketUpdate, db: DbSession, user: CurrentUser
) -> TicketOut:
    return TicketOut.model_validate(support.update_ticket(db, ticket_id, data, user))


@router.post("/tickets/{ticket_id}/resolve")
def resolve_ticket(
    ticket_id: uuid.UUID, body: TicketNote, db: DbSession, user: CurrentUser
) -> TicketOut:
    """The customer's problem is dealt with. Any hold on their payment reminders ends."""
    ticket = support.set_status(db, ticket_id, TicketStatus.resolved, body.note, user)
    return TicketOut.model_validate(ticket)


@router.post("/tickets/{ticket_id}/close")
def close_ticket(
    ticket_id: uuid.UUID, body: TicketNote, db: DbSession, user: CurrentUser
) -> TicketOut:
    """Nothing (more) to do: a thank-you note, a duplicate, or a resolved ticket filed away."""
    ticket = support.set_status(db, ticket_id, TicketStatus.closed, body.note, user)
    return TicketOut.model_validate(ticket)


@router.post("/tickets/{ticket_id}/reopen")
def reopen_ticket(
    ticket_id: uuid.UUID, body: TicketNote, db: DbSession, user: CurrentUser
) -> TicketOut:
    ticket = support.set_status(db, ticket_id, TicketStatus.open, body.note, user)
    return TicketOut.model_validate(ticket)


@router.get("/staff")
def list_staff(db: DbSession) -> list[StaffOut]:
    """Who a ticket can be assigned to."""
    return [StaffOut.model_validate(u) for u in support.list_staff(db)]


# --- replies to the customer -------------------------------------------------------------------


@router.get("/tickets/{ticket_id}/emails")
def list_replies(ticket_id: uuid.UUID, db: DbSession) -> list[OutboundEmailOut]:
    return [OutboundEmailOut.model_validate(e) for e in support.list_replies(db, ticket_id)]


@router.post("/tickets/{ticket_id}/emails", status_code=201)
def draft_reply(ticket_id: uuid.UUID, db: DbSession, user: CurrentUser) -> OutboundEmailOut:
    """Start a reply from the investigation's draft. Sent only after a support manager approves."""
    return OutboundEmailOut.model_validate(support.draft_reply(db, ticket_id, user))


@router.patch("/emails/{email_id}")
def edit_email(
    email_id: uuid.UUID, data: EmailDraftUpdate, db: DbSession, user: CurrentUser
) -> OutboundEmailOut:
    email = outbound.update_draft(db, email_id, Department.support, data, user)
    return OutboundEmailOut.model_validate(email)


@router.post("/emails/{email_id}/request-approval")
def request_email_approval(
    email_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> OutboundEmailOut:
    return OutboundEmailOut.model_validate(support.request_reply_approval(db, email_id, user))


@router.post("/emails/{email_id}/retry")
def retry_email(
    email_id: uuid.UUID, db: DbSession, user: CurrentUser, mailer: Mailer
) -> OutboundEmailOut:
    email = outbound.retry(db, email_id, Department.support, user, mailer)
    return OutboundEmailOut.model_validate(email)
