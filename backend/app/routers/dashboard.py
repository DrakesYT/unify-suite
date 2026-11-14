from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.db import DbSession
from app.deps import CurrentUser, require_roles
from app.models.enums import Role
from app.schemas.dashboard import ActivityItem, Charts, Kpis, Overview, SearchHit
from app.services import dashboard, overview, search

# Cross-department numbers: managers, executives and admins (employees see their own pages).
router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_roles(Role.admin, Role.manager, Role.executive))],
)

# The top-bar search is for everyone; it only finds what the caller may read.
search_router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("/kpis")
def kpis(db: DbSession) -> Kpis:
    return dashboard.kpis(db)


@router.get("/charts")
def charts(db: DbSession) -> Charts:
    return dashboard.charts(db)


@router.get("/overview")
def get_overview(db: DbSession) -> Overview:
    """Every dashboard panel in one read: hiring board, deals, tickets, money, insights."""
    return overview.overview(db)


@router.get("/activity")
def activity(
    db: DbSession, limit: Annotated[int, Query(ge=1, le=100)] = dashboard.FEED_SIZE
) -> list[ActivityItem]:
    """FR-DASH-02: the latest audit events, newest first."""
    return dashboard.recent_activity(db, limit)


@router.get("/audit")
def audit_log(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: datetime | None = None,
    q: Annotated[str | None, Query(max_length=80)] = None,
) -> list[ActivityItem]:
    """The append-only audit log: who did what, newest first, filterable and pageable."""
    return dashboard.audit_page(db, limit, before, q)


@search_router.get("")
def find(
    db: DbSession, user: CurrentUser, q: Annotated[str, Query(min_length=2, max_length=80)]
) -> list[SearchHit]:
    return search.search(db, user, q)
