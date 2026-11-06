"""Company settings. Reading follows the dashboard's audience; changing is for an executive or an
admin, checked in the service."""

from dataclasses import asdict

from fastapi import APIRouter, Depends

from app.db import DbSession
from app.deps import CurrentUser, require_roles
from app.models.enums import Role
from app.schemas.settings import SalesTargetOut, SalesTargetUpdate
from app.services import company_settings

router = APIRouter(
    prefix="/api/settings",
    tags=["settings"],
    dependencies=[Depends(require_roles(Role.admin, Role.manager, Role.executive))],
)


@router.get("/sales-target")
def get_sales_target(db: DbSession) -> SalesTargetOut:
    return SalesTargetOut(**asdict(company_settings.sales_target(db)))


@router.put("/sales-target")
def set_sales_target(data: SalesTargetUpdate, db: DbSession, user: CurrentUser) -> SalesTargetOut:
    target = company_settings.set_sales_target(db, user, data.amount, data.currency)
    return SalesTargetOut(**asdict(target))
