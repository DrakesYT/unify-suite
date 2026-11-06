import uuid
from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin, UtcDateTime


class UserSession(IdMixin, TimestampMixin, Base):
    """One sign-in. The access token names it, so signing out (or a role switch) ends that token
    on the server at once instead of leaving it valid until it expires."""

    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
