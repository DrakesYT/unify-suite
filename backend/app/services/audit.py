import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    *,
    action: str,
    entity: str,
    entity_id: uuid.UUID | str | None = None,
    actor_id: uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Add an audit row to the caller's transaction (the caller commits)."""
    db.add(
        AuditLog(
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            actor_id=actor_id,
            detail=detail or {},
        )
    )
