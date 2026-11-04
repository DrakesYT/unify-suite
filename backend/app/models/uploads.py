import uuid

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin, str_enum
from app.models.enums import Department


class Upload(IdMixin, TimestampMixin, Base):
    """An uploaded file. The bytes live on disk outside the web root; this row describes them."""

    __tablename__ = "uploads"

    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_path: Mapped[str] = mapped_column(String(500))
    department: Mapped[Department] = mapped_column(
        str_enum(Department, "upload_department"), index=True
    )
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
