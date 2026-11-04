import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import PurchaseOrder, PurchaseRequest, User, Vendor
from app.models.enums import PurchaseRequestStatus
from app.schemas.finance import PoSnapshot
from app.schemas.procurement import (
    PurchaseOrderCreate,
    PurchaseRequestCreate,
    PurchaseRequestUpdate,
    VendorCreate,
    VendorUpdate,
)
from app.services import audit
from app.services.pagination import paginate


def _get[M](db: Session, model: type[M], row_id: uuid.UUID, label: str) -> M:
    row = db.get(model, row_id)
    if row is None:
        raise ApiError(404, "not_found", f"{label} not found")
    return row


def _apply(row: Any, changes: dict[str, Any]) -> dict[str, Any]:
    for key, value in changes.items():
        setattr(row, key, value)
    return {k: str(v) for k, v in changes.items()}


# --- vendors -------------------------------------------------------------------------------


def _ensure_vendor_name_free(db: Session, name: str, except_id: uuid.UUID | None = None) -> None:
    stmt = select(Vendor.id).where(func.lower(Vendor.name) == name.lower())
    if except_id:
        stmt = stmt.where(Vendor.id != except_id)
    if db.scalar(stmt) is not None:
        raise ApiError(409, "vendor_exists", "A vendor with this name already exists")


def list_vendors(db: Session, limit: int, cursor: str | None) -> tuple[list[Vendor], str | None]:
    return paginate(db, select(Vendor), Vendor, limit, cursor)


def get_vendor(db: Session, vendor_id: uuid.UUID) -> Vendor:
    return _get(db, Vendor, vendor_id, "Vendor")


def find_vendor_by_name(db: Session, name: str) -> Vendor | None:
    return db.scalar(select(Vendor).where(func.lower(Vendor.name) == name.strip().lower()))


def create_vendor(db: Session, data: VendorCreate, actor: User) -> Vendor:
    _ensure_vendor_name_free(db, data.name)
    vendor = Vendor(**data.model_dump())
    db.add(vendor)
    db.flush()
    audit.record(
        db, action="vendor.created", entity="vendor", entity_id=vendor.id, actor_id=actor.id
    )
    db.commit()
    return vendor


def update_vendor(db: Session, vendor_id: uuid.UUID, data: VendorUpdate, actor: User) -> Vendor:
    vendor = get_vendor(db, vendor_id)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes:
        _ensure_vendor_name_free(db, changes["name"], except_id=vendor.id)
    detail = _apply(vendor, changes)
    audit.record(
        db,
        action="vendor.updated",
        entity="vendor",
        entity_id=vendor.id,
        actor_id=actor.id,
        detail=detail,
    )
    db.commit()
    return vendor


# --- purchase requests ---------------------------------------------------------------------


def list_requests(
    db: Session, limit: int, cursor: str | None, status: PurchaseRequestStatus | None = None
) -> tuple[list[PurchaseRequest], str | None]:
    stmt = select(PurchaseRequest)
    if status:
        stmt = stmt.where(PurchaseRequest.status == status)
    return paginate(db, stmt, PurchaseRequest, limit, cursor)


def get_request(db: Session, request_id: uuid.UUID) -> PurchaseRequest:
    return _get(db, PurchaseRequest, request_id, "Purchase request")


def create_request(db: Session, data: PurchaseRequestCreate, actor: User) -> PurchaseRequest:
    if data.chosen_vendor_id:
        get_vendor(db, data.chosen_vendor_id)
    request = PurchaseRequest(**data.model_dump(), requested_by_id=actor.id)
    db.add(request)
    db.flush()
    audit.record(
        db,
        action="purchase_request.created",
        entity="purchase_request",
        entity_id=request.id,
        actor_id=actor.id,
    )
    db.commit()
    return request


def update_request(
    db: Session, request_id: uuid.UUID, data: PurchaseRequestUpdate, actor: User
) -> PurchaseRequest:
    request = get_request(db, request_id)
    if request.status != PurchaseRequestStatus.pending:
        raise ApiError(409, "not_editable", "Only pending requests can be edited")
    changes = data.model_dump(exclude_unset=True)
    if changes.get("chosen_vendor_id"):
        get_vendor(db, changes["chosen_vendor_id"])
    detail = _apply(request, changes)
    audit.record(
        db,
        action="purchase_request.updated",
        entity="purchase_request",
        entity_id=request.id,
        actor_id=actor.id,
        detail=detail,
    )
    db.commit()
    return request


# --- purchase orders -----------------------------------------------------------------------


def list_orders(
    db: Session, limit: int, cursor: str | None
) -> tuple[list[PurchaseOrder], str | None]:
    return paginate(db, select(PurchaseOrder), PurchaseOrder, limit, cursor)


def get_order_by_number(db: Session, po_number: str) -> PurchaseOrder:
    order = db.scalar(select(PurchaseOrder).where(PurchaseOrder.po_number == po_number))
    if order is None:
        raise ApiError(404, "not_found", "Purchase order not found")
    return order


def create_order(
    db: Session, data: PurchaseOrderCreate, actor: User | None = None
) -> PurchaseOrder:
    """New POs start as pending_approval. Used by the seed script and tests."""
    if db.scalar(select(PurchaseOrder.id).where(PurchaseOrder.po_number == data.po_number)):
        raise ApiError(409, "po_exists", "A purchase order with this number already exists")
    get_vendor(db, data.vendor_id)
    order = PurchaseOrder(**data.model_dump())
    db.add(order)
    db.flush()
    audit.record(
        db,
        action="purchase_order.created",
        entity="purchase_order",
        entity_id=order.id,
        actor_id=actor.id if actor else None,
    )
    db.commit()
    return order


def po_snapshot(db: Session, po_number: str) -> PoSnapshot | None:
    """The `get_po` tool: what an agent may see of a purchase order."""
    order = db.scalar(select(PurchaseOrder).where(PurchaseOrder.po_number == po_number.strip()))
    if order is None:
        return None
    vendor = get_vendor(db, order.vendor_id)
    return PoSnapshot(
        id=order.id,
        po_number=order.po_number,
        vendor_id=order.vendor_id,
        vendor_name=vendor.name,
        amount_minor=order.amount_minor,
        currency=order.currency,
    )
