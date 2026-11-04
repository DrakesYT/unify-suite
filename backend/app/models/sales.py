import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, JsonType, TimestampMixin, UtcDateTime, str_enum
from app.models.enums import LeadRating, LeadStatus, OrderStatus, Priority


class Lead(IdMixin, TimestampMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (CheckConstraint("value_minor >= 0", name="value_non_negative"),)

    name: Mapped[str] = mapped_column(String(120))
    company: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(254))
    status: Mapped[LeadStatus] = mapped_column(
        str_enum(LeadStatus, "lead_status"), default=LeadStatus.new, index=True
    )
    priority: Mapped[Priority] = mapped_column(
        str_enum(Priority, "lead_priority"), default=Priority.medium, index=True
    )
    value_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    rating: Mapped[LeadRating | None] = mapped_column(
        str_enum(LeadRating, "lead_rating"), index=True
    )
    qualification: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)


class Customer(IdMixin, TimestampMixin, Base):
    __tablename__ = "customers"

    name: Mapped[str] = mapped_column(String(120))
    company: Mapped[str | None] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(254), index=True)
    billing_terms: Mapped[str] = mapped_column(String(40), default="net_30")


class Order(IdMixin, TimestampMixin, Base):
    """A customer's order. Support reads these when investigating a ticket."""

    __tablename__ = "orders"
    __table_args__ = (CheckConstraint("amount_minor >= 0", name="amount_non_negative"),)

    order_number: Mapped[str] = mapped_column(String(40), unique=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[OrderStatus] = mapped_column(str_enum(OrderStatus, "order_status"), index=True)
    ordered_at: Mapped[datetime] = mapped_column(UtcDateTime())
