"""Purchase order delivery tracking and supplier follow-ups for late orders.

Code decides what is late (expected delivery date vs today). The Supplier Follow-up Writer only
drafts the chase email; editing, approval and sending are shared (services/outbound.py).
"""

import uuid
from datetime import date, timedelta

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.runner import TaskContext, call_tool, run_agent
from app.agents.supplier_followup import SupplierFollowUpWriter
from app.config import SELLER_COMPANY
from app.errors import ApiError
from app.llm import LLMClient
from app.models import OutboundEmail, PurchaseOrder, PurchaseRequest, User, Vendor
from app.models.base import utcnow
from app.models.enums import Department, PurchaseOrderStatus
from app.money import format_minor
from app.schemas.outreach import EmailDraft, SupplierFollowUpInput
from app.services import audit, outbound

WRITER = SupplierFollowUpWriter()
KIND = "supplier_followup"
_EMAIL = TypeAdapter(EmailStr)


def start_tracking(order: PurchaseOrder, vendor: Vendor, today: date | None = None) -> None:
    """On approval: ordered today, expected after the vendor's usual lead time."""
    today = today or utcnow().date()
    order.ordered_on = today
    order.expected_delivery = today + timedelta(days=vendor.lead_time_days)


def get_order(db: Session, order_id: uuid.UUID) -> PurchaseOrder:
    order = db.get(PurchaseOrder, order_id)
    if order is None:
        raise ApiError(404, "not_found", "Purchase order not found")
    return order


def _open_order(db: Session, order_id: uuid.UUID) -> PurchaseOrder:
    order = get_order(db, order_id)
    if order.status != PurchaseOrderStatus.approved:
        raise ApiError(409, "not_ordered", "Only approved purchase orders are tracked")
    if order.delivered_on is not None:
        raise ApiError(409, "already_delivered", "This order was already delivered")
    return order


def mark_delivered(db: Session, order_id: uuid.UUID, actor: User) -> PurchaseOrder:
    order = _open_order(db, order_id)
    order.delivered_on = utcnow().date()
    audit.record(
        db,
        action="purchase_order.delivered",
        entity="purchase_order",
        entity_id=order.id,
        actor_id=actor.id,
        detail={"days_late": max((order.delivered_on - order.expected_delivery).days, 0)}
        if order.expected_delivery
        else {},
    )
    db.commit()
    return order


def set_expected_delivery(
    db: Session, order_id: uuid.UUID, expected: date, actor: User
) -> PurchaseOrder:
    """The supplier confirmed a (new) date."""
    order = _open_order(db, order_id)
    previous = order.expected_delivery
    order.expected_delivery = expected
    audit.record(
        db,
        action="purchase_order.delivery_date_changed",
        entity="purchase_order",
        entity_id=order.id,
        actor_id=actor.id,
        detail={"from": previous.isoformat() if previous else None, "to": expected.isoformat()},
    )
    db.commit()
    return order


def _vendor_email(vendor: Vendor) -> str:
    try:
        return str(_EMAIL.validate_python(vendor.contact or ""))
    except ValidationError as exc:
        raise ApiError(
            409, "no_vendor_email", f"{vendor.name} has no contact email address on file"
        ) from exc


def _facts(db: Session, order: PurchaseOrder, vendor: Vendor) -> SupplierFollowUpInput:
    if order.delivery_status != "late" or order.ordered_on is None:
        raise ApiError(409, "not_late", "Only late orders need a follow-up")
    assert order.expected_delivery is not None
    request = db.get(PurchaseRequest, order.request_id) if order.request_id else None
    return SupplierFollowUpInput(
        po_number=order.po_number,
        vendor_name=vendor.name,
        item=request.item if request else None,
        quantity=request.quantity if request else None,
        amount=format_minor(order.amount_minor, order.currency),
        ordered_on=order.ordered_on,
        expected_delivery=order.expected_delivery,
        days_late=order.days_late,
        buyer_company=SELLER_COMPANY,
    )


def compose_body(vendor: Vendor, draft: EmailDraft, sender: User) -> str:
    return (
        f"Hello {vendor.name} team,\n\n{draft.body}\n\n"
        f"Best regards,\n{sender.full_name}\nProcurement, {SELLER_COMPANY}"
    )


def draft_followup(
    db: Session, llm: LLMClient, order_id: uuid.UUID, ctx: TaskContext
) -> OutboundEmail:
    order = get_order(db, order_id)
    vendor = db.get(Vendor, order.vendor_id)
    assert vendor is not None
    to_address = _vendor_email(vendor)
    facts = call_tool(
        db,
        WRITER,
        "get_order",
        {"po_number": order.po_number},
        lambda: _facts(db, order, vendor),
        ctx,
    )
    draft: EmailDraft = run_agent(db, WRITER, facts, llm, ctx)
    return call_tool(
        db,
        WRITER,
        "save_email_draft",
        {"po_number": order.po_number},
        lambda: outbound.new_draft(
            db,
            kind=KIND,
            department=Department.procurement,
            to_address=to_address,
            subject=draft.subject,
            body=compose_body(vendor, draft, ctx.actor),
            actor=ctx.actor,
            model=llm.model,
            po_id=order.id,
        ),
        ctx,
    )


def list_for_order(db: Session, order_id: uuid.UUID) -> list[OutboundEmail]:
    get_order(db, order_id)
    stmt = (
        select(OutboundEmail)
        .where(OutboundEmail.po_id == order_id)
        .order_by(OutboundEmail.created_at.desc())
    )
    return list(db.scalars(stmt))


def request_approval(db: Session, email_id: uuid.UUID, actor: User) -> OutboundEmail:
    email = outbound.get_email(db, email_id, Department.procurement)
    order = db.get(PurchaseOrder, email.po_id) if email.po_id else None
    vendor = db.get(Vendor, order.vendor_id) if order else None
    context = {
        "po_id": str(order.id) if order else None,
        "po_number": order.po_number if order else None,
        "company": vendor.name if vendor else None,
        "days_late": order.days_late if order else None,
    }
    return outbound.request_approval(db, email_id, Department.procurement, actor, context)
