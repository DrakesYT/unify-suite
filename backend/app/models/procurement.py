import uuid
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin, str_enum
from app.models.enums import PurchaseOrderStatus, PurchaseRequestStatus


class Vendor(IdMixin, TimestampMixin, Base):
    __tablename__ = "vendors"
    __table_args__ = (
        CheckConstraint("lead_time_days >= 0", name="lead_time_non_negative"),
        CheckConstraint("on_time_rate >= 0 AND on_time_rate <= 1", name="on_time_rate_range"),
    )

    name: Mapped[str] = mapped_column(String(160), unique=True)
    contact: Mapped[str | None] = mapped_column(String(254))
    lead_time_days: Mapped[int]
    on_time_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4))  # 0.0000 to 1.0000


class PurchaseRequest(IdMixin, TimestampMixin, Base):
    __tablename__ = "purchase_requests"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("budget_minor >= 0", name="budget_non_negative"),
    )

    item: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int]
    budget_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[PurchaseRequestStatus] = mapped_column(
        str_enum(PurchaseRequestStatus, "purchase_request_status"),
        default=PurchaseRequestStatus.pending,
        index=True,
    )
    chosen_vendor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vendors.id"), index=True)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)


class PurchaseOrder(IdMixin, TimestampMixin, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (CheckConstraint("amount_minor >= 0", name="amount_non_negative"),)

    po_number: Mapped[str] = mapped_column(String(40), unique=True)
    vendor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vendors.id"), index=True)
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("purchase_requests.id"), index=True
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[PurchaseOrderStatus] = mapped_column(
        str_enum(PurchaseOrderStatus, "purchase_order_status"),
        default=PurchaseOrderStatus.pending_approval,
        index=True,
    )
