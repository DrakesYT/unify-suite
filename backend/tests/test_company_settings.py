"""The quarterly sales target: set in the app by an executive or an admin, audited, and used by the
dashboard; the deployment default applies until someone sets it."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, User
from app.models.enums import Department, Role

API = "/api/settings/sales-target"
MakeUser = Callable[..., User]
AuthHeader = Callable[[User], dict[str, str]]


def test_the_deployment_default_applies_until_someone_sets_it(
    client: TestClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    res = client.get(API, headers=auth_header(make_user(Role.manager, Department.sales)))

    assert res.status_code == 200
    assert res.json() == {
        "amount_minor": 250_000 * 100,
        "currency": "USD",
        "set_by": None,
        "set_at": None,
    }


@pytest.mark.parametrize("role", [Role.executive, Role.admin])
def test_an_executive_or_admin_sets_it_and_the_dashboard_uses_it(
    client: TestClient, make_user: MakeUser, auth_header: AuthHeader, db: Session, role: Role
) -> None:
    boss = make_user(role, Department.finance)
    headers = auth_header(boss)

    res = client.put(API, json={"amount": "400000", "currency": "usd"}, headers=headers)

    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["amount_minor"], body["currency"], body["set_by"]) == (
        40_000_000,
        "USD",
        boss.full_name,
    )
    assert body["set_at"] is not None
    crm = client.get("/api/dashboard/overview", headers=headers).json()["crm"]
    assert crm["target"]["target_minor"] == 40_000_000
    assert crm["target"]["set_by"] == boss.full_name
    log = db.scalar(select(AuditLog).where(AuditLog.action == "setting.sales_target_changed"))
    assert log is not None and log.actor_id == boss.id
    assert log.detail == {
        "from": {"amount_minor": 25_000_000, "currency": "USD"},
        "to": {"amount_minor": 40_000_000, "currency": "USD"},
    }


@pytest.mark.parametrize(("role", "status"), [(Role.manager, 403), (Role.employee, 403)])
def test_others_cannot_change_it(
    client: TestClient, make_user: MakeUser, auth_header: AuthHeader, role: Role, status: int
) -> None:
    res = client.put(
        API,
        json={"amount": "1"},
        headers=auth_header(make_user(role, Department.sales)),
    )

    assert res.status_code == status
    assert res.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("amount", ["0", "-5", "100.123", "1000000000001"])
def test_a_bad_amount_is_refused(
    client: TestClient, make_user: MakeUser, auth_header: AuthHeader, amount: str
) -> None:
    headers = auth_header(make_user(Role.executive, Department.finance))

    res = client.put(API, json={"amount": amount}, headers=headers)

    assert res.status_code == 422


def test_a_new_value_replaces_the_old_one(
    client: TestClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    headers = auth_header(make_user(Role.admin, Department.finance))
    client.put(API, json={"amount": "100000"}, headers=headers)

    client.put(API, json={"amount": "150000.50"}, headers=headers)

    assert client.get(API, headers=headers).json()["amount_minor"] == 15_000_050
