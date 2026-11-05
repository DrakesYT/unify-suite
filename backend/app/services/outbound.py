"""Outbound email for every department: edit a draft, ask a manager, send only once approved.

Agents only draft (see services/outreach.py and services/supplier_followup.py). Sending happens
in `apply_decision` for an approved `send_email` request, or in `retry` after a failed send.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.agents.runner import TaskContext, ToolUser, call_tool
from app.config import get_settings
from app.errors import ApiError
from app.mailer import EmailError, EmailSender, OutgoingEmail
from app.models import ApprovalRequest, OutboundEmail, User
from app.models.base import utcnow
from app.models.enums import ApprovalStatus, Department, EmailStatus, Role
from app.schemas.outreach import EmailDraftUpdate
from app.services import approvals, audit

ACTION = "send_email"
# One "mailer" per department, so the send is permission-checked against that department.
MAILERS = {
    d: ToolUser(name="mailer", department=d, tools=frozenset({"send_email"})) for d in Department
}


def new_draft(
    db: Session,
    *,
    kind: str,
    department: Department,
    to_address: str,
    subject: str,
    body: str,
    actor: User,
    model: str,
    lead_id: uuid.UUID | None = None,
    po_id: uuid.UUID | None = None,
) -> OutboundEmail:
    """Store an agent's draft (called inside the agent's `save_email_draft` tool)."""
    email = OutboundEmail(
        kind=kind,
        department=department,
        lead_id=lead_id,
        po_id=po_id,
        to_address=to_address,
        subject=subject,
        body=body,
        created_by_id=actor.id,
        drafted_by_model=model,
    )
    db.add(email)
    db.flush()
    audit.record(
        db,
        action="email.drafted",
        entity="outbound_email",
        entity_id=email.id,
        actor_id=actor.id,
        detail={"kind": kind},
    )
    return email


def get_email(db: Session, email_id: uuid.UUID, department: Department) -> OutboundEmail:
    email = db.get(OutboundEmail, email_id)
    if email is None or email.department != department:
        raise ApiError(404, "not_found", "Email not found")
    return email


def update_draft(
    db: Session, email_id: uuid.UUID, department: Department, data: EmailDraftUpdate, actor: User
) -> OutboundEmail:
    email = get_email(db, email_id, department)
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


def request_approval(
    db: Session,
    email_id: uuid.UUID,
    department: Department,
    actor: User,
    context: dict[str, Any],
) -> OutboundEmail:
    """Emailing someone outside the company is a commitment: a manager of that department decides.

    `context` adds what the manager needs to judge it (e.g. the company name).
    """
    email = get_email(db, email_id, department)
    if email.status != EmailStatus.draft:
        raise ApiError(409, "not_a_draft", f"This email is already {email.status}")
    approval = approvals.create_approval(
        db,
        action=ACTION,
        payload=context
        | {
            "email_id": str(email.id),
            "to": email.to_address,
            "subject": email.subject,
            "body": email.body,
        },
        required_role=Role.manager,
        department=department,
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
    db: Session,
    email_id: uuid.UUID,
    department: Department,
    actor: User,
    mailer: EmailSender | None,
) -> OutboundEmail:
    """Re-send an approved email whose first attempt failed (the approval is not asked again)."""
    email = get_email(db, email_id, department)
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

    mailer_tool = MAILERS[email.department]
    try:
        call_tool(db, mailer_tool, "send_email", {"email_id": str(email_id)}, _send, ctx)
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
