"""Cursor pagination: newest first, ordered by (created_at, id) so pages never overlap."""

import base64
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, or_
from sqlalchemy.orm import Session

from app.errors import ApiError


def _encode(created_at: datetime, row_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()}|{row_id}".encode()).decode()


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        created, row_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(created), uuid.UUID(row_id)
    except ValueError as exc:
        raise ApiError(422, "invalid_cursor", "The cursor is not valid") from exc


def paginate[M](
    db: Session, stmt: Select[tuple[M]], model: Any, limit: int, cursor: str | None
) -> tuple[list[M], str | None]:
    if cursor:
        created_at, row_id = _decode(cursor)
        stmt = stmt.where(
            or_(
                model.created_at < created_at,
                and_(model.created_at == created_at, model.id < row_id),
            )
        )
    rows = list(
        db.scalars(stmt.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1))
    )
    if len(rows) <= limit:
        return rows, None
    last = rows[limit - 1]
    return rows[:limit], _encode(last.created_at, last.id)  # type: ignore[attr-defined]
