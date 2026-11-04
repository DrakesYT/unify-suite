import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, JsonType, UtcDateTime, utcnow


class AuditLog(IdMixin, Base):
    """Append-only: a database trigger rejects UPDATE and DELETE on PostgreSQL."""

    __tablename__ = "audit_logs"

    at: Mapped[datetime] = mapped_column(
        UtcDateTime(), default=utcnow, server_default=func.now(), index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity: Mapped[str] = mapped_column(String(60), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
