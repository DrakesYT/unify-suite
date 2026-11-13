import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.agents.runner import TaskContext
from app.config import PAGE_LIMIT_DEFAULT, PAGE_LIMIT_MAX, UPLOAD_MAX_BYTES
from app.db import DbSession
from app.deps import CurrentUser, require_department
from app.llm import LLM
from app.mailer import Mailer
from app.models.enums import AnomalyKind, Department, InvoiceStatus, MatchStatus
from app.schemas.common import Page
from app.schemas.finance import (
    AnomalyOut,
    InvoiceOut,
    InvoiceRejectIn,
    InvoiceUploadResult,
    ReceivableOut,
)
from app.schemas.outreach import EmailDraftUpdate, OutboundEmailOut
from app.services import finance, outbound, receivables
from app.services.uploads import save_upload

router = APIRouter(
    prefix="/api/finance",
    tags=["finance"],
    dependencies=[Depends(require_department(Department.finance))],
)
Limit = Annotated[int, Query(ge=1, le=PAGE_LIMIT_MAX)]


@router.post("/invoices/upload", status_code=201)
def upload_invoice(
    file: Annotated[UploadFile, File(description="Invoice as PDF or TXT, max 10 MB")],
    db: DbSession,
    user: CurrentUser,
    llm: LLM,
) -> InvoiceUploadResult:
    data = file.file.read(UPLOAD_MAX_BYTES + 1)  # one byte over the limit is enough to refuse it
    upload = save_upload(
        db, filename=file.filename or "upload", data=data, department=Department.finance, actor=user
    )
    return finance.process_invoice_upload(db, llm, upload, TaskContext(actor=user))


@router.get("/invoices")
def list_invoices(
    db: DbSession,
    limit: Limit = PAGE_LIMIT_DEFAULT,
    cursor: str | None = None,
    status: InvoiceStatus | None = None,
    match_status: MatchStatus | None = None,
) -> Page[InvoiceOut]:
    rows, next_cursor = finance.list_invoices(db, limit, cursor, status, match_status)
    return Page(items=[InvoiceOut.model_validate(r) for r in rows], next_cursor=next_cursor)


@router.post("/invoices/{invoice_id}/reject")
def reject_invoice(
    invoice_id: uuid.UUID, body: InvoiceRejectIn, db: DbSession, user: CurrentUser
) -> InvoiceOut:
    """Settle an invoice that needs a human check and will not be paid (finance manager)."""
    return InvoiceOut.model_validate(finance.reject_invoice(db, invoice_id, body.reason, user))


@router.get("/anomalies")
def list_anomalies(
    db: DbSession,
    limit: Limit = PAGE_LIMIT_DEFAULT,
    cursor: str | None = None,
    kind: AnomalyKind | None = None,
) -> Page[AnomalyOut]:
    rows, next_cursor = finance.list_anomalies(db, limit, cursor, kind)
    return Page(items=[AnomalyOut.model_validate(r) for r in rows], next_cursor=next_cursor)


# --- receivables: overdue customer orders and payment reminders ---------------------------------


@router.get("/receivables")
def list_receivables(db: DbSession) -> list[ReceivableOut]:
    """Unpaid customer orders with their due date, days overdue and any hold (all computed)."""
    return receivables.list_open(db)


@router.post("/receivables/{order_id}/paid")
def mark_paid(order_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ReceivableOut:
    return receivables.mark_paid(db, order_id, user)


@router.get("/receivables/{order_id}/emails")
def list_reminders(order_id: uuid.UUID, db: DbSession) -> list[OutboundEmailOut]:
    return [OutboundEmailOut.model_validate(e) for e in receivables.list_for_order(db, order_id)]


@router.post("/receivables/{order_id}/emails", status_code=201)
def draft_reminder(
    order_id: uuid.UUID, db: DbSession, user: CurrentUser, llm: LLM
) -> OutboundEmailOut:
    """Payment Reminder Writer drafts a reminder. Sent only after a finance manager approves."""
    email = receivables.draft_reminder(db, llm, order_id, TaskContext(actor=user))
    return OutboundEmailOut.model_validate(email)


@router.patch("/emails/{email_id}")
def edit_email(
    email_id: uuid.UUID, data: EmailDraftUpdate, db: DbSession, user: CurrentUser
) -> OutboundEmailOut:
    email = outbound.update_draft(db, email_id, Department.finance, data, user)
    return OutboundEmailOut.model_validate(email)


@router.post("/emails/{email_id}/request-approval")
def request_email_approval(
    email_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> OutboundEmailOut:
    return OutboundEmailOut.model_validate(receivables.request_approval(db, email_id, user))


@router.post("/emails/{email_id}/retry")
def retry_email(
    email_id: uuid.UUID, db: DbSession, user: CurrentUser, mailer: Mailer
) -> OutboundEmailOut:
    email = outbound.retry(db, email_id, Department.finance, user, mailer)
    return OutboundEmailOut.model_validate(email)
