import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.agents.runner import TaskContext
from app.config import PAGE_LIMIT_DEFAULT, PAGE_LIMIT_MAX
from app.db import DbSession
from app.deps import CurrentUser, require_department
from app.llm import LLM
from app.mailer import Mailer
from app.models.enums import Department, PurchaseRequestStatus
from app.schemas.common import Page
from app.schemas.outreach import EmailDraftUpdate, OutboundEmailOut
from app.schemas.procurement import (
    DeliveryDateIn,
    OrderFromRequest,
    OrderWithApproval,
    PurchaseOrderCreate,
    PurchaseOrderOut,
    PurchaseRequestCreate,
    PurchaseRequestOut,
    PurchaseRequestUpdate,
    QuoteCreate,
    QuoteOut,
    VendorComparison,
    VendorCreate,
    VendorOut,
    VendorUpdate,
)
from app.services import deliveries, outbound, procurement


class CompareIn(BaseModel):
    request_id: uuid.UUID


router = APIRouter(
    prefix="/api/procurement",
    tags=["procurement"],
    dependencies=[Depends(require_department(Department.procurement))],
)
Limit = Annotated[int, Query(ge=1, le=PAGE_LIMIT_MAX)]


@router.get("/vendors")
def list_vendors(
    db: DbSession, limit: Limit = PAGE_LIMIT_DEFAULT, cursor: str | None = None
) -> Page[VendorOut]:
    rows, next_cursor = procurement.list_vendors(db, limit, cursor)
    return Page(items=[VendorOut.model_validate(r) for r in rows], next_cursor=next_cursor)


@router.post("/vendors", status_code=201)
def create_vendor(data: VendorCreate, db: DbSession, user: CurrentUser) -> VendorOut:
    return VendorOut.model_validate(procurement.create_vendor(db, data, user))


@router.get("/vendors/{vendor_id}")
def get_vendor(vendor_id: uuid.UUID, db: DbSession) -> VendorOut:
    return VendorOut.model_validate(procurement.get_vendor(db, vendor_id))


@router.patch("/vendors/{vendor_id}")
def update_vendor(
    vendor_id: uuid.UUID, data: VendorUpdate, db: DbSession, user: CurrentUser
) -> VendorOut:
    return VendorOut.model_validate(procurement.update_vendor(db, vendor_id, data, user))


@router.get("/requests")
def list_requests(
    db: DbSession,
    limit: Limit = PAGE_LIMIT_DEFAULT,
    cursor: str | None = None,
    status: PurchaseRequestStatus | None = None,
) -> Page[PurchaseRequestOut]:
    rows, next_cursor = procurement.list_requests(db, limit, cursor, status)
    return Page(items=[PurchaseRequestOut.model_validate(r) for r in rows], next_cursor=next_cursor)


@router.post("/requests", status_code=201)
def create_request(
    data: PurchaseRequestCreate, db: DbSession, user: CurrentUser
) -> PurchaseRequestOut:
    return PurchaseRequestOut.model_validate(procurement.create_request(db, data, user))


@router.get("/requests/{request_id}")
def get_request(request_id: uuid.UUID, db: DbSession) -> PurchaseRequestOut:
    return PurchaseRequestOut.model_validate(procurement.get_request(db, request_id))


@router.patch("/requests/{request_id}")
def update_request(
    request_id: uuid.UUID, data: PurchaseRequestUpdate, db: DbSession, user: CurrentUser
) -> PurchaseRequestOut:
    return PurchaseRequestOut.model_validate(procurement.update_request(db, request_id, data, user))


@router.get("/orders")
def list_orders(
    db: DbSession, limit: Limit = PAGE_LIMIT_DEFAULT, cursor: str | None = None
) -> Page[PurchaseOrderOut]:
    rows, next_cursor = procurement.list_orders(db, limit, cursor)
    return Page(items=[PurchaseOrderOut.model_validate(r) for r in rows], next_cursor=next_cursor)


@router.post("/orders", status_code=201)
def create_order(data: PurchaseOrderCreate, db: DbSession, user: CurrentUser) -> OrderWithApproval:
    """New purchase orders stay pending_approval until a procurement manager approves them."""
    order, approval = procurement.create_order_for_approval(db, data, user)
    return OrderWithApproval(order=PurchaseOrderOut.model_validate(order), approval_id=approval.id)


@router.get("/requests/{request_id}/quotes")
def list_quotes(request_id: uuid.UUID, db: DbSession) -> list[QuoteOut]:
    return [QuoteOut.model_validate(q) for q in procurement.list_quotes(db, request_id)]


@router.post("/requests/{request_id}/quotes", status_code=201)
def add_quote(
    request_id: uuid.UUID, data: QuoteCreate, db: DbSession, user: CurrentUser
) -> QuoteOut:
    """Add or replace one vendor's unit price for this request."""
    return QuoteOut.model_validate(procurement.add_quote(db, request_id, data, user))


@router.post("/compare-vendors")
def compare_vendors(
    data: CompareIn, db: DbSession, user: CurrentUser, llm: LLM
) -> VendorComparison:
    """Ranking is computed by code (same data → same order); the comparator explains the winner."""
    return procurement.compare_vendors(db, llm, data.request_id, TaskContext(actor=user))


@router.post("/requests/{request_id}/approve")
def approve_request(request_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PurchaseRequestOut:
    request = procurement.decide_request(db, request_id, user, approve=True)
    return PurchaseRequestOut.model_validate(request)


@router.post("/requests/{request_id}/reject")
def reject_request(request_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PurchaseRequestOut:
    request = procurement.decide_request(db, request_id, user, approve=False)
    return PurchaseRequestOut.model_validate(request)


@router.post("/requests/{request_id}/order", status_code=201)
def order_from_request(
    request_id: uuid.UUID, data: OrderFromRequest, db: DbSession, user: CurrentUser
) -> OrderWithApproval:
    """FR-PRO-03: a PO from an approved request; it waits in the Approval Center."""
    order, approval = procurement.order_from_request(db, request_id, data.vendor_id, user)
    return OrderWithApproval(order=PurchaseOrderOut.model_validate(order), approval_id=approval.id)


@router.get("/orders/{po_number}")
def get_order(po_number: str, db: DbSession) -> PurchaseOrderOut:
    return PurchaseOrderOut.model_validate(procurement.get_order_by_number(db, po_number))


# --- delivery tracking and supplier follow-ups -------------------------------------------------


@router.post("/orders/{order_id}/delivered")
def mark_delivered(order_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PurchaseOrderOut:
    return PurchaseOrderOut.model_validate(deliveries.mark_delivered(db, order_id, user))


@router.patch("/orders/{order_id}/delivery")
def set_expected_delivery(
    order_id: uuid.UUID, data: DeliveryDateIn, db: DbSession, user: CurrentUser
) -> PurchaseOrderOut:
    """The supplier confirmed a new delivery date."""
    order = deliveries.set_expected_delivery(db, order_id, data.expected_delivery, user)
    return PurchaseOrderOut.model_validate(order)


@router.get("/orders/{order_id}/emails")
def list_order_emails(order_id: uuid.UUID, db: DbSession) -> list[OutboundEmailOut]:
    return [OutboundEmailOut.model_validate(e) for e in deliveries.list_for_order(db, order_id)]


@router.post("/orders/{order_id}/emails", status_code=201)
def draft_followup(
    order_id: uuid.UUID, db: DbSession, user: CurrentUser, llm: LLM
) -> OutboundEmailOut:
    """Supplier Follow-up Writer drafts a chase for a late order. Sent only after approval."""
    email = deliveries.draft_followup(db, llm, order_id, TaskContext(actor=user))
    return OutboundEmailOut.model_validate(email)


@router.patch("/emails/{email_id}")
def edit_email(
    email_id: uuid.UUID, data: EmailDraftUpdate, db: DbSession, user: CurrentUser
) -> OutboundEmailOut:
    email = outbound.update_draft(db, email_id, Department.procurement, data, user)
    return OutboundEmailOut.model_validate(email)


@router.post("/emails/{email_id}/request-approval")
def request_email_approval(
    email_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> OutboundEmailOut:
    return OutboundEmailOut.model_validate(deliveries.request_approval(db, email_id, user))


@router.post("/emails/{email_id}/retry")
def retry_email(
    email_id: uuid.UUID, db: DbSession, user: CurrentUser, mailer: Mailer
) -> OutboundEmailOut:
    email = outbound.retry(db, email_id, Department.procurement, user, mailer)
    return OutboundEmailOut.model_validate(email)
