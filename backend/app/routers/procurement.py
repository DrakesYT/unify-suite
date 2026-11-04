import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.config import PAGE_LIMIT_DEFAULT, PAGE_LIMIT_MAX
from app.db import DbSession
from app.deps import CurrentUser, require_department
from app.models.enums import Department, PurchaseRequestStatus
from app.schemas.common import Page
from app.schemas.procurement import (
    PurchaseOrderOut,
    PurchaseRequestCreate,
    PurchaseRequestOut,
    PurchaseRequestUpdate,
    VendorCreate,
    VendorOut,
    VendorUpdate,
)
from app.services import procurement

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


@router.get("/orders/{po_number}")
def get_order(po_number: str, db: DbSession) -> PurchaseOrderOut:
    return PurchaseOrderOut.model_validate(procurement.get_order_by_number(db, po_number))
