import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin, UtcDateTime, str_enum
from app.models.enums import Department, EmailStatus


class OutboundEmail(IdMixin, TimestampMixin, Base):
    """An email an agent drafted. It is sent only after a manager approves it."""

    __tablename__ = "outbound_emails"

    kind: Mapped[str] = mapped_column(String(40))
    department: Mapped[Department] = mapped_column(str_enum(Department, "department"), index=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"), index=True)
    po_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id"), index=True)
    to_address: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[EmailStatus] = mapped_column(
        str_enum(EmailStatus, "email_status"), default=EmailStatus.draft, index=True
    )
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approval_requests.id"), index=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    drafted_by_model: Mapped[str | None] = mapped_column(String(80))
    # Where it really went (differs from to_address while demo redirection is on).
    delivered_to: Mapped[str | None] = mapped_column(String(254))
    provider_message_id: Mapped[str | None] = mapped_column(String(120))
    sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    error: Mapped[str | None] = mapped_column(String(300))
