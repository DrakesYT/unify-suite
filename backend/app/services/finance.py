"""Invoice intake: extract (LLM) → load PO → match (code) → duplicate check (code) → save/flag.

Each step is its own function so Workflow B can run them as separate steps.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.invoice_processor import InvoiceProcessor
from app.agents.runner import TaskContext, call_tool, run_agent
from app.errors import ApiError
from app.llm import LLMClient
from app.models import ApprovalRequest, Invoice, InvoiceAnomaly, Payment, Upload, Vendor
from app.models.enums import AnomalyKind, ApprovalStatus, InvoiceStatus, MatchStatus
from app.schemas.finance import (
    AnomalyOut,
    FieldDifference,
    InvoiceFields,
    InvoiceOut,
    InvoiceText,
    InvoiceUploadResult,
    MatchResult,
    PoSnapshot,
)
from app.services import audit, procurement
from app.services.pagination import paginate
from app.services.uploads import read_text

AGENT = InvoiceProcessor()


def extract_invoice(db: Session, llm: LLMClient, upload: Upload, ctx: TaskContext) -> InvoiceFields:
    text = call_tool(
        db, AGENT, "read_upload", {"upload_id": str(upload.id)}, lambda: read_text(upload), ctx
    )
    return run_agent(db, AGENT, InvoiceText(text=text), llm, ctx)


def load_po(db: Session, po_number: str | None, ctx: TaskContext) -> PoSnapshot | None:
    if not po_number:
        return None
    return call_tool(
        db,
        AGENT,
        "get_po",
        {"po_number": po_number},
        lambda: procurement.po_snapshot(db, po_number),
        ctx,
    )


def match_invoice(fields: InvoiceFields, vendor: Vendor, po: PoSnapshot | None) -> MatchResult:
    """FR-FIN-02, deterministic: same vendor, currency and amount as the PO → matched."""
    if po is None:
        return MatchResult(status=MatchStatus.no_po)
    checks = [
        ("vendor", vendor.name, po.vendor_name, vendor.id == po.vendor_id),
        ("currency", fields.currency, po.currency, fields.currency == po.currency),
        (
            "amount_minor",
            fields.amount_minor,
            po.amount_minor,
            fields.amount_minor == po.amount_minor,
        ),
    ]
    differences = [
        FieldDifference(field=f, invoice=i, po=p) for f, i, p, same in checks if not same
    ]
    return MatchResult(
        status=MatchStatus.mismatch if differences else MatchStatus.matched, differences=differences
    )


def _flag(
    db: Session,
    kind: AnomalyKind,
    upload: Upload,
    ctx: TaskContext,
    *,
    invoice: Invoice | None = None,
    existing: Invoice | None = None,
    detail: dict[str, object] | None = None,
) -> InvoiceAnomaly:
    def _write() -> InvoiceAnomaly:
        anomaly = InvoiceAnomaly(
            kind=kind,
            upload_id=upload.id,
            invoice_id=invoice.id if invoice else None,
            existing_invoice_id=existing.id if existing else None,
            detail=detail or {},
        )
        db.add(anomaly)
        db.flush()
        audit.record(
            db,
            action=f"invoice.flagged.{kind}",
            entity="invoice_anomaly",
            entity_id=anomaly.id,
            actor_id=ctx.actor.id,
        )
        return anomaly

    return call_tool(
        db, AGENT, "flag_anomaly", {"kind": kind, "upload_id": str(upload.id)}, _write, ctx
    )


def record_invoice(
    db: Session, upload: Upload, fields: InvoiceFields, po: PoSnapshot | None, ctx: TaskContext
) -> tuple[MatchResult | None, Invoice | None, list[InvoiceAnomaly]]:
    """Save the invoice, or flag why it was not saved. Returns (match, invoice, anomalies)."""
    vendor = procurement.find_vendor_by_name(db, fields.vendor_name)
    if vendor is None:
        anomaly = _flag(
            db, AnomalyKind.unknown_vendor, upload, ctx, detail={"vendor_name": fields.vendor_name}
        )
        return None, None, [anomaly]

    existing = db.scalar(
        select(Invoice).where(Invoice.vendor_id == vendor.id, Invoice.number == fields.number)
    )
    if existing is not None:  # FR-FIN-03: flagged, not inserted
        same_amount = (
            existing.amount_minor == fields.amount_minor and existing.currency == fields.currency
        )
        kind = AnomalyKind.duplicate if same_amount else AnomalyKind.number_conflict
        detail = {"number": fields.number, "amount_minor": fields.amount_minor}
        return None, None, [_flag(db, kind, upload, ctx, existing=existing, detail=detail)]

    match = match_invoice(fields, vendor, po)

    def _save() -> Invoice:
        invoice = Invoice(
            number=fields.number,
            vendor_id=vendor.id,
            purchase_order_id=po.id if po else None,
            po_number=fields.po_number,
            invoice_date=fields.invoice_date,
            amount_minor=fields.amount_minor,
            currency=fields.currency,
            status=InvoiceStatus.received
            if match.status == MatchStatus.matched
            else InvoiceStatus.needs_review,
            match_status=match.status,
            file_id=upload.id,
        )
        db.add(invoice)
        db.flush()
        audit.record(
            db,
            action="invoice.saved",
            entity="invoice",
            entity_id=invoice.id,
            actor_id=ctx.actor.id,
            detail={"match_status": match.status},
        )
        return invoice

    invoice = call_tool(
        db, AGENT, "save_invoice", {"number": fields.number, "vendor": vendor.name}, _save, ctx
    )
    anomalies = []
    if match.status == MatchStatus.mismatch:
        diffs = [d.model_dump(mode="json") for d in match.differences]
        anomalies.append(
            _flag(
                db,
                AnomalyKind.po_mismatch,
                upload,
                ctx,
                invoice=invoice,
                detail={"differences": diffs},
            )
        )
    elif match.status == MatchStatus.no_po:
        anomalies.append(
            _flag(
                db,
                AnomalyKind.no_po,
                upload,
                ctx,
                invoice=invoice,
                detail={"po_number": fields.po_number},
            )
        )
    return match, invoice, anomalies


def process_invoice_upload(
    db: Session, llm: LLMClient, upload: Upload, ctx: TaskContext
) -> InvoiceUploadResult:
    """FR-FIN-01..03 for one uploaded file."""
    fields = extract_invoice(db, llm, upload, ctx)
    po = load_po(db, fields.po_number, ctx)
    match, invoice, anomalies = record_invoice(db, upload, fields, po, ctx)
    return InvoiceUploadResult(
        upload_id=upload.id,
        extracted=fields,
        match=match,
        invoice=InvoiceOut.model_validate(invoice) if invoice else None,
        anomalies=[AnomalyOut.model_validate(a) for a in anomalies],
    )


def list_invoices(
    db: Session,
    limit: int,
    cursor: str | None,
    status: InvoiceStatus | None = None,
    match_status: MatchStatus | None = None,
) -> tuple[list[Invoice], str | None]:
    stmt = select(Invoice)
    if status:
        stmt = stmt.where(Invoice.status == status)
    if match_status:
        stmt = stmt.where(Invoice.match_status == match_status)
    return paginate(db, stmt, Invoice, limit, cursor)


def list_anomalies(
    db: Session, limit: int, cursor: str | None, kind: AnomalyKind | None = None
) -> tuple[list[InvoiceAnomaly], str | None]:
    stmt = select(InvoiceAnomaly)
    if kind:
        stmt = stmt.where(InvoiceAnomaly.kind == kind)
    return paginate(db, stmt, InvoiceAnomaly, limit, cursor)


def set_invoice_status(
    db: Session, invoice_id: uuid.UUID, status: InvoiceStatus, actor_id: uuid.UUID
) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise ApiError(404, "not_found", "Invoice not found")
    invoice.status = status
    audit.record(
        db, action=f"invoice.{status}", entity="invoice", entity_id=invoice.id, actor_id=actor_id
    )
    return invoice


def submit_payment(
    db: Session,
    invoice_id: uuid.UUID,
    approval_id: uuid.UUID,
    actor_id: uuid.UUID,
    execution_id: uuid.UUID | None = None,
) -> Payment:
    """Create the payment record. Refuses unless this exact invoice has an approved request."""
    invoice = db.get(Invoice, invoice_id)
    approval = db.get(ApprovalRequest, approval_id)
    if invoice is None or approval is None:
        raise ApiError(404, "not_found", "Invoice or approval not found")
    if approval.status != ApprovalStatus.approved or approval.payload.get("invoice_id") != str(
        invoice.id
    ):
        raise ApiError(409, "not_approved", "Payment needs an approved request for this invoice")
    if db.scalar(select(Payment.id).where(Payment.invoice_id == invoice.id)) is not None:
        raise ApiError(409, "already_paid", "A payment for this invoice already exists")
    payment = Payment(
        invoice_id=invoice.id,
        approval_id=approval.id,
        execution_id=execution_id,
        amount_minor=invoice.amount_minor,
        currency=invoice.currency,
    )
    db.add(payment)
    db.flush()
    set_invoice_status(db, invoice.id, InvoiceStatus.payment_submitted, actor_id)
    audit.record(
        db, action="payment.submitted", entity="payment", entity_id=payment.id, actor_id=actor_id
    )
    return payment
