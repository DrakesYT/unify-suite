"""Company settings set in the app by the people responsible for them.

The quarterly sales target is set by an executive (the CEO) or an admin. Until someone sets it,
the deployment default applies (SALES_QUARTER_TARGET, SALES_TARGET_CURRENCY). Every change is
audited with the old and new value.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import ApiError
from app.models import AppSetting, User
from app.models.enums import Role
from app.money import minor_unit_exponent, to_minor
from app.services import audit

SALES_TARGET = "sales_quarter_target"
TARGET_EDITORS = frozenset({Role.admin, Role.executive})


@dataclass(frozen=True)
class SalesTarget:
    amount_minor: int
    currency: str
    set_by: str | None  # None while the deployment default applies
    set_at: datetime | None


def sales_target(db: Session) -> SalesTarget:
    row = db.get(AppSetting, SALES_TARGET)
    if row is not None:
        setter = db.get(User, row.updated_by_id) if row.updated_by_id else None
        return SalesTarget(
            amount_minor=int(row.value["amount_minor"]),
            currency=str(row.value["currency"]),
            set_by=setter.full_name if setter else None,
            set_at=row.updated_at,
        )
    settings = get_settings()
    currency = settings.sales_target_currency
    amount = settings.sales_quarter_target * 10 ** minor_unit_exponent(currency)
    return SalesTarget(amount_minor=amount, currency=currency, set_by=None, set_at=None)


def set_sales_target(db: Session, user: User, amount: Decimal, currency: str) -> SalesTarget:
    """Code decides who may: an executive or an admin (the dashboard only hides the button)."""
    if user.role not in TARGET_EDITORS:
        raise ApiError(403, "forbidden", "Only an executive or an admin can set the sales target")
    try:
        amount_minor = to_minor(amount, currency)
    except ValueError as exc:
        raise ApiError(422, "invalid_amount", str(exc)) from exc
    old = sales_target(db)
    row = db.get(AppSetting, SALES_TARGET)
    if row is None:
        row = AppSetting(key=SALES_TARGET, value={})
        db.add(row)
    row.value = {"amount_minor": amount_minor, "currency": currency}
    row.updated_by_id = user.id
    audit.record(
        db,
        action="setting.sales_target_changed",
        entity="app_setting",
        entity_id=SALES_TARGET,
        actor_id=user.id,
        detail={
            "from": {"amount_minor": old.amount_minor, "currency": old.currency},
            "to": {"amount_minor": amount_minor, "currency": currency},
        },
    )
    db.commit()
    return sales_target(db)
