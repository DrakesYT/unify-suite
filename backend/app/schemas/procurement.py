import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PurchaseOrderStatus, PurchaseRequestStatus
from app.schemas.common import Currency, MinorAmount, Name

OnTimeRate = Annotated[Decimal, Field(ge=0, le=1, max_digits=5, decimal_places=4)]
LeadTime = Annotated[int, Field(ge=0, le=3650)]
Quantity = Annotated[int, Field(gt=0, le=1_000_000)]


class VendorCreate(BaseModel):
    name: Name
    contact: Annotated[str, Field(max_length=254)] | None = None
    lead_time_days: LeadTime
    on_time_rate: OnTimeRate


class VendorUpdate(BaseModel):
    name: Name | None = None
    contact: Annotated[str, Field(max_length=254)] | None = None
    lead_time_days: LeadTime | None = None
    on_time_rate: OnTimeRate | None = None


class VendorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    contact: str | None
    lead_time_days: int
    on_time_rate: Decimal
    created_at: datetime


class PurchaseRequestCreate(BaseModel):
    item: Annotated[str, Field(min_length=1, max_length=200)]
    quantity: Quantity
    budget_minor: MinorAmount
    currency: Currency
    chosen_vendor_id: uuid.UUID | None = None


class PurchaseRequestUpdate(BaseModel):
    item: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    quantity: Quantity | None = None
    budget_minor: MinorAmount | None = None
    currency: Currency | None = None
    chosen_vendor_id: uuid.UUID | None = None


class PurchaseRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item: str
    quantity: int
    budget_minor: int
    currency: str
    status: PurchaseRequestStatus
    chosen_vendor_id: uuid.UUID | None
    requested_by_id: uuid.UUID | None
    created_at: datetime


class PurchaseOrderCreate(BaseModel):
    po_number: Annotated[str, Field(min_length=1, max_length=40)]
    vendor_id: uuid.UUID
    request_id: uuid.UUID | None = None
    amount_minor: MinorAmount
    currency: Currency


class PurchaseOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    po_number: str
    vendor_id: uuid.UUID
    request_id: uuid.UUID | None
    amount_minor: int
    currency: str
    status: PurchaseOrderStatus
    created_at: datetime
