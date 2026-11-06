import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JsonType, TimestampMixin


class AppSetting(TimestampMixin, Base):
    """A company-wide setting people change in the app (e.g. the quarterly sales target)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JsonType)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
