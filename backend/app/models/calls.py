import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, JsonType, TimestampMixin, UtcDateTime, str_enum
from app.models.enums import Department


class CallTranscript(IdMixin, TimestampMixin, Base):
    """A sales or support call, as text, linked to one lead or one ticket.

    The Call Analyzer writes `analysis` (summary, sentiment, action items, each backed by a quote
    that code found in the transcript). Talk share is counted by code, never stored.
    """

    __tablename__ = "call_transcripts"
    __table_args__ = (
        CheckConstraint(
            "(lead_id IS NULL) <> (ticket_id IS NULL)", name="exactly_one_lead_or_ticket"
        ),
    )

    title: Mapped[str] = mapped_column(String(200))
    department: Mapped[Department] = mapped_column(
        str_enum(Department, "call_department"), index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"), index=True)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tickets.id"), index=True)
    upload_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uploads.id"), index=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    analysis: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    analyzed_by_model: Mapped[str | None] = mapped_column(String(80))
    analyzed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    analysis_error: Mapped[str | None] = mapped_column(String(300))
