"""Sales outreach: the Outreach Writer drafts a first email to a qualified lead.

Editing, approval and sending are shared with every department (services/outbound.py).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.outreach_writer import OutreachWriter
from app.agents.runner import TaskContext, call_tool, run_agent
from app.config import SELLER_COMPANY
from app.errors import ApiError
from app.llm import LLMClient
from app.models import Lead, OutboundEmail, User
from app.models.enums import Department
from app.money import format_minor
from app.schemas.outreach import EmailDraft, OutreachInput
from app.services import outbound
from app.services.sales import get_lead

WRITER = OutreachWriter()
KIND = "sales_outreach"


def _facts(lead: Lead) -> OutreachInput:
    if lead.rating is None or not lead.qualification:
        raise ApiError(409, "not_qualified", "Qualify the lead before drafting an email")
    return OutreachInput(
        company=lead.company,
        status=lead.status,
        priority=lead.priority,
        value=format_minor(lead.value_minor, lead.currency),
        notes=lead.notes,
        rating=lead.rating,
        qualification_reason=lead.qualification.get("reason", ""),
        seller_company=SELLER_COMPANY,
    )


def compose_body(lead: Lead, draft: EmailDraft, sender: User) -> str:
    """The model writes the middle; code writes who it is to and who it is from."""
    first_name = lead.name.split()[0]
    return (
        f"Hi {first_name},\n\n{draft.body}\n\nBest regards,\n{sender.full_name}\n{SELLER_COMPANY}"
    )


def draft_for_lead(
    db: Session, llm: LLMClient, lead_id: uuid.UUID, ctx: TaskContext
) -> OutboundEmail:
    lead = get_lead(db, lead_id)
    facts = call_tool(db, WRITER, "get_lead", {"lead_id": str(lead.id)}, lambda: _facts(lead), ctx)
    draft: EmailDraft = run_agent(db, WRITER, facts, llm, ctx)
    return call_tool(
        db,
        WRITER,
        "save_email_draft",
        {"lead_id": str(lead.id)},
        lambda: outbound.new_draft(
            db,
            kind=KIND,
            department=Department.sales,
            to_address=lead.email,
            subject=draft.subject,
            body=compose_body(lead, draft, ctx.actor),
            actor=ctx.actor,
            model=llm.model,
            lead_id=lead.id,
        ),
        ctx,
    )


def list_for_lead(db: Session, lead_id: uuid.UUID) -> list[OutboundEmail]:
    get_lead(db, lead_id)
    stmt = (
        select(OutboundEmail)
        .where(OutboundEmail.lead_id == lead_id)
        .order_by(OutboundEmail.created_at.desc())
    )
    return list(db.scalars(stmt))


def request_approval(db: Session, email_id: uuid.UUID, actor: User) -> OutboundEmail:
    email = outbound.get_email(db, email_id, Department.sales)
    lead = db.get(Lead, email.lead_id) if email.lead_id else None
    context = {
        "lead_id": str(email.lead_id) if email.lead_id else None,
        "company": lead.company if lead else None,
    }
    return outbound.request_approval(db, email_id, Department.sales, actor, context)
