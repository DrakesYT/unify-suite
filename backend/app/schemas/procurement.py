import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

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
    comparison: dict[str, Any] | None
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
    ordered_on: date | None
    expected_delivery: date | None
    delivered_on: date | None
    delivery_status: Literal["not_ordered", "no_date", "on_track", "late", "delivered"]
    days_late: int


class DeliveryDateIn(BaseModel):
    expected_delivery: date


class QuoteCreate(BaseModel):
    vendor_id: uuid.UUID
    unit_price_minor: MinorAmount


class QuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    request_id: uuid.UUID
    vendor_id: uuid.UUID
    unit_price_minor: int
    currency: str
    created_at: datetime


class RankedVendor(BaseModel):
    rank: int
    vendor_id: uuid.UUID
    vendor_name: str
    total_minor: int
    currency: str
    lead_time_days: int
    on_time_rate: Decimal
    price_score: Decimal
    lead_time_score: Decimal
    delivery_score: Decimal
    score: Decimal = Field(description="0-100, higher is better")
    over_budget: bool


class VendorComparison(BaseModel):
    request_id: uuid.UUID
    ranking: list[RankedVendor]
    reason: str | None = Field(description="Why the top vendor wins (written by the comparator)")
    reason_error: str | None = None
    compared_at: datetime


class OrderFromRequest(BaseModel):
    vendor_id: uuid.UUID | None = Field(
        default=None, description="Defaults to the chosen vendor, then the top-ranked one"
    )


class OrderWithApproval(BaseModel):
    order: PurchaseOrderOut
    approval_id: uuid.UUID


class ComparisonFacts(BaseModel):
    """Vendor Comparator input: the ranking code already computed, in plain terms."""

    item: str
    quantity: int
    budget: str
    ranking: list[dict[str, str | int | bool]]


class ComparisonReason(BaseModel):
    reason: Annotated[str, Field(min_length=20, max_length=900)] = Field(
        description="Two or three sentences on why the top-ranked vendor is recommended"
    )
