"""Sales outreach: the Outreach Writer drafts, a sales manager approves, the mailer sends.

Nothing leaves the building without a human decision: sending happens only in `apply_decision`
for an approved `send_email` request.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.outreach_writer import OutreachWriter
from app.agents.runner import TaskContext, ToolUser, call_tool, run_agent
from app.config import SELLER_COMPANY, get_settings
from app.errors import ApiError
from app.llm import LLMClient
from app.mailer import EmailError, EmailSender, OutgoingEmail
from app.models import ApprovalRequest, Lead, OutboundEmail, User
from app.models.base import utcnow
from app.models.enums import ApprovalStatus, Department, EmailStatus, Role
from app.money import format_minor
from app.schemas.outreach import EmailDraftUpdate, OutreachDraft, OutreachInput
from app.services import approvals, audit
from app.services.sales import get_lead

WRITER = OutreachWriter()
MAILER = ToolUser(name="mailer", department=Department.sales, tools=frozenset({"send_email"}))
ACTION = "send_email"
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


def compose_body(lead: Lead, draft: OutreachDraft, sender: User) -> str:
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
    draft: OutreachDraft = run_agent(db, WRITER, facts, llm, ctx)

    def _save() -> OutboundEmail:
        email = OutboundEmail(
            kind=KIND,
            department=Department.sales,
            lead_id=lead.id,
            to_address=lead.email,
            subject=draft.subject,
            body=compose_body(lead, draft, ctx.actor),
            created_by_id=ctx.actor.id,
            drafted_by_model=llm.model,
        )
        db.add(email)
        db.flush()
        audit.record(
            db,
            action="email.drafted",
            entity="outbound_email",
            entity_id=email.id,
            actor_id=ctx.actor.id,
            detail={"lead_id": str(lead.id)},
        )
        return email

    return call_tool(db, WRITER, "save_email_draft", {"lead_id": str(lead.id)}, _save, ctx)


def list_for_lead(db: Session, lead_id: uuid.UUID) -> list[OutboundEmail]:
    get_lead(db, lead_id)
    stmt = (
        select(OutboundEmail)
        .where(OutboundEmail.lead_id == lead_id)
        .order_by(OutboundEmail.created_at.desc())
    )
    return list(db.scalars(stmt))


def get_email(db: Session, email_id: uuid.UUID) -> OutboundEmail:
    email = db.get(OutboundEmail, email_id)
    if email is None or email.department != Department.sales:
        raise ApiError(404, "not_found", "Email not found")
    return email


def update_draft(
    db: Session, email_id: uuid.UUID, data: EmailDraftUpdate, actor: User
) -> OutboundEmail:
    email = get_email(db, email_id)
    if email.status != EmailStatus.draft:
        raise ApiError(409, "not_a_draft", f"This email is already {email.status}")
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in changes.items():
        setattr(email, key, value.strip())
    audit.record(
        db,
        action="email.edited",
        entity="outbound_email",
        entity_id=email.id,
        actor_id=actor.id,
        detail={"fields": sorted(changes)},
    )
    db.commit()
    return email


def request_approval(db: Session, email_id: uuid.UUID, actor: User) -> OutboundEmail:
    """Sending an email to a customer is an external commitment: a sales manager decides."""
    email = get_email(db, email_id)
    if email.status != EmailStatus.draft:
        raise ApiError(409, "not_a_draft", f"This email is already {email.status}")
    lead = db.get(Lead, email.lead_id) if email.lead_id else None
    approval = approvals.create_approval(
        db,
        action=ACTION,
        payload={
            "email_id": str(email.id),
            "lead_id": str(email.lead_id) if email.lead_id else None,
            "company": lead.company if lead else None,
            "to": email.to_address,
            "subject": email.subject,
            "body": email.body,
        },
        required_role=Role.manager,
        department=Department.sales,
        requested_by_id=actor.id,
    )
    email.status = EmailStatus.pending_approval
    email.approval_id = approval.id
    db.commit()
    return email


def apply_decision(
    db: Session, approval: ApprovalRequest, actor: User, mailer: EmailSender | None
) -> None:
    """Approved → send now. Rejected → the email is closed and never sent."""
    if approval.action != ACTION:
        return
    email = db.get(OutboundEmail, uuid.UUID(approval.payload["email_id"]))
    if email is None or email.status != EmailStatus.pending_approval:
        return
    if approval.status == ApprovalStatus.approved:
        send(db, email, mailer, TaskContext(actor=actor))
    else:
        email.status = EmailStatus.rejected
        db.commit()


def retry(
    db: Session, email_id: uuid.UUID, actor: User, mailer: EmailSender | None
) -> OutboundEmail:
    """Re-send an approved email whose first attempt failed (the approval is not asked again)."""
    email = get_email(db, email_id)
    approval = db.get(ApprovalRequest, email.approval_id) if email.approval_id else None
    if email.status != EmailStatus.failed or approval is None:
        raise ApiError(409, "nothing_to_retry", "Only approved emails that failed can be retried")
    if approval.status != ApprovalStatus.approved:
        raise ApiError(409, "not_approved", "This email was not approved")
    return send(db, email, mailer, TaskContext(actor=actor))


def send(
    db: Session, email: OutboundEmail, mailer: EmailSender | None, ctx: TaskContext
) -> OutboundEmail:
    """Send one approved email. A failure is recorded on the email, never raised to the caller."""
    email_id = email.id
    redirect = get_settings().email_redirect_to
    delivered_to = redirect or email.to_address
    text = email.body
    if redirect and redirect != email.to_address:
        text = f"[UNIFY SUITE demo: originally addressed to {email.to_address}]\n\n{text}"

    def _send() -> dict[str, str]:
        if mailer is None:
            raise EmailError("email sending is not configured on this server")
        message_id = mailer.send(OutgoingEmail(to=delivered_to, subject=email.subject, text=text))
        email.status = EmailStatus.sent
        email.delivered_to = delivered_to
        email.provider_message_id = message_id
        email.sent_at = utcnow()
        email.error = None
        audit.record(
            db,
            action="email.sent",
            entity="outbound_email",
            entity_id=email.id,
            actor_id=ctx.actor.id,
            detail={"delivered_to": delivered_to, "redirected": bool(redirect)},
        )
        return {"delivered_to": delivered_to, "message_id": message_id}

    try:
        call_tool(db, MAILER, "send_email", {"email_id": str(email_id)}, _send, ctx)
    except EmailError as exc:
        failed = db.get(OutboundEmail, email_id)
        assert failed is not None
        failed.status = EmailStatus.failed
        failed.error = str(exc)[:300]
        audit.record(
            db,
            action="email.failed",
            entity="outbound_email",
            entity_id=email_id,
            actor_id=ctx.actor.id,
            detail={"error": failed.error},
        )
        db.commit()
        return failed
    db.commit()
    return email
