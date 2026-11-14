import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, JsonType, TimestampMixin, str_enum
from app.models.enums import TicketCategory, TicketStatus, Urgency


class Ticket(IdMixin, TimestampMixin, Base):
    __tablename__ = "tickets"

    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[TicketCategory | None] = mapped_column(
        str_enum(TicketCategory, "ticket_category"), index=True
    )
    urgency: Mapped[Urgency | None] = mapped_column(str_enum(Urgency, "ticket_urgency"), index=True)
    status: Mapped[TicketStatus] = mapped_column(
        str_enum(TicketStatus, "ticket_status"), default=TicketStatus.open, index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"), index=True)
    investigation: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    # Who in Support owns the ticket (None: nobody has picked it up yet).
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
