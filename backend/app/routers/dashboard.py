from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.db import DbSession
from app.deps import require_roles
from app.models.enums import Role
from app.schemas.dashboard import ActivityItem, Charts, Kpis
from app.services import dashboard

# Cross-department numbers: managers, executives and admins (employees see their own pages).
router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_roles(Role.admin, Role.manager, Role.executive))],
)


@router.get("/kpis")
def kpis(db: DbSession) -> Kpis:
    return dashboard.kpis(db)


@router.get("/charts")
def charts(db: DbSession) -> Charts:
    return dashboard.charts(db)


@router.get("/activity")
def activity(
    db: DbSession, limit: Annotated[int, Query(ge=1, le=100)] = dashboard.FEED_SIZE
) -> list[ActivityItem]:
    """FR-DASH-02: the latest audit events, newest first."""
    return dashboard.recent_activity(db, limit)
