import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import AnomalyKind, InvoiceStatus, MatchStatus, PurchaseOrderStatus
from app.money import to_minor
from app.schemas.common import Currency


class InvoiceText(BaseModel):
    """Invoice Processor input: the text of one uploaded invoice."""

    text: Annotated[str, Field(min_length=1)]


class InvoiceFields(BaseModel):
    """Invoice Processor output. Validated before anything is saved."""

    number: Annotated[str, Field(min_length=1, max_length=60, description="Invoice number")]
    invoice_date: date = Field(description="Invoice date, YYYY-MM-DD")
    vendor_name: Annotated[str, Field(min_length=1, max_length=160, description="Who issued it")]
    total_amount: Annotated[
        Decimal, Field(ge=0, description="Total due as a decimal string, e.g. '1234.50'")
    ]
    currency: Currency
    po_number: Annotated[str, Field(max_length=40)] | None = Field(
        default=None, description="Purchase order number referenced on the invoice, if any"
    )

    @model_validator(mode="after")
    def _amount_fits_currency(self) -> "InvoiceFields":
        to_minor(self.total_amount, self.currency)  # raises if e.g. USD has 3 decimals
        return self

    @property
    def amount_minor(self) -> int:
        return to_minor(self.total_amount, self.currency)


class PoSnapshot(BaseModel):
    id: uuid.UUID
    po_number: str
    vendor_id: uuid.UUID
    vendor_name: str
    amount_minor: int
    currency: str
    # None in runs stored before the PO status was recorded; treated as not approved.
    status: PurchaseOrderStatus | None = None


class FieldDifference(BaseModel):
    field: str
    invoice: Any
    po: Any


class MatchResult(BaseModel):
    status: MatchStatus
    differences: list[FieldDifference] = []


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: str
    vendor_id: uuid.UUID
    purchase_order_id: uuid.UUID | None
    po_number: str | None
    invoice_date: date
    amount_minor: int
    currency: str
    status: InvoiceStatus
    match_status: MatchStatus | None
    file_id: uuid.UUID | None
    created_at: datetime


class AnomalyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: AnomalyKind
    invoice_id: uuid.UUID | None
    existing_invoice_id: uuid.UUID | None
    upload_id: uuid.UUID | None
    detail: dict[str, Any]
    created_at: datetime


class InvoiceUploadResult(BaseModel):
    upload_id: uuid.UUID
    extracted: InvoiceFields
    match: MatchResult | None = Field(description="None when flagged before matching")
    invoice: InvoiceOut | None = Field(description="None when the invoice was not saved")
    anomalies: list[AnomalyOut]
    suspicious_text: list[str] = Field(
        default=[], description="Lines of the document that try to give the AI instructions"
    )


class ReceivableOut(BaseModel):
    """An unpaid customer order and where it stands (all computed by code)."""

    order_id: uuid.UUID
    order_number: str
    customer_name: str
    customer_company: str | None
    customer_email: str | None
    amount_minor: int
    currency: str
    ordered_on: date
    due_on: date
    days_overdue: int
    status: Literal["not_due", "overdue", "on_hold"]
    hold_reason: str | None
