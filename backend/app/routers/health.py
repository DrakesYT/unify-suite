import logging

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import DbSession
from app.errors import ApiError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(db: DbSession) -> dict[str, str]:
    """Liveness + database check. Used by Docker, Coolify and the frontend status pill."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error("health_db_failed", extra={"error_type": type(exc).__name__})
        raise ApiError(503, "db_unavailable", "Database is not reachable") from exc
    return {"status": "ok", "db": "ok"}
