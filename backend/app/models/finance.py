import uuid
from datetime import date
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, JsonType, TimestampMixin, str_enum
from app.models.enums import AnomalyKind, InvoiceStatus, MatchStatus, PaymentStatus


class Invoice(IdMixin, TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("vendor_id", "number"),
        CheckConstraint("amount_minor >= 0", name="amount_non_negative"),
    )

    number: Mapped[str] = mapped_column(String(60))
    vendor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vendors.id"), index=True)
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("purchase_orders.id"), index=True
    )
    po_number: Mapped[str | None] = mapped_column(String(40))  # as printed on the invoice
    invoice_date: Mapped[date]
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[InvoiceStatus] = mapped_column(
        str_enum(InvoiceStatus, "invoice_status"), default=InvoiceStatus.received, index=True
    )
    match_status: Mapped[MatchStatus | None] = mapped_column(
        str_enum(MatchStatus, "invoice_match_status"), index=True
    )
    file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("uploads.id"), index=True)


class Transaction(IdMixin, TimestampMixin, Base):
    __tablename__ = "transactions"

    txn_date: Mapped[date] = mapped_column(index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    counterparty: Mapped[str] = mapped_column(String(160))
    matched_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("invoices.id"), index=True
    )


class InvoiceAnomaly(IdMixin, TimestampMixin, Base):
    """Something Finance should look at. Duplicates are recorded here instead of being inserted."""

    __tablename__ = "invoice_anomalies"

    kind: Mapped[AnomalyKind] = mapped_column(str_enum(AnomalyKind, "anomaly_kind"), index=True)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoices.id"), index=True)
    existing_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("invoices.id"), index=True
    )
    upload_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("uploads.id"), index=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)


class Payment(IdMixin, TimestampMixin, Base):
    """A payment submitted for an invoice. Only created after a manager approved it."""

    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("amount_minor >= 0", name="amount_non_negative"),)

    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"), unique=True)
    approval_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("approval_requests.id"), index=True)
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_executions.id"), index=True
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[PaymentStatus] = mapped_column(
        str_enum(PaymentStatus, "payment_status"), default=PaymentStatus.submitted, index=True
    )
