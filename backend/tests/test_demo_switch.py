"""Demo role switcher: only between seeded demo accounts, never to or from a real account."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, User
from app.models.enums import Department, Role

AuthHeader = Callable[[User], dict[str, str]]
MakeUser = Callable[..., User]


def _demo(make_user: MakeUser, handle: str, role: Role, dept: Department) -> User:
    return make_user(role, dept, email=f"{handle}@demo.example.com")


def test_demo_user_lists_and_switches_to_another_demo_account(
    client: TestClient, db: Session, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    ceo = _demo(make_user, "ceo", Role.executive, Department.finance)
    clerk = _demo(make_user, "finance.clerk", Role.employee, Department.finance)
    make_user(Role.manager, Department.sales)  # a real account: never listed

    listed = client.get("/api/auth/demo-accounts", headers=auth_header(ceo))
    assert listed.status_code == 200, listed.text
    assert {u["email"] for u in listed.json()} == {ceo.email, clerk.email}

    res = client.post(
        "/api/auth/demo-switch", json={"email": clerk.email}, headers=auth_header(ceo)
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["user"]["email"] == clerk.email
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["role"] == "employee"

    log = db.scalar(select(AuditLog).where(AuditLog.action == "auth.demo_switch"))
    assert log is not None and log.actor_id == ceo.id
    assert log.detail == {"from": ceo.email, "to": clerk.email}


def test_real_accounts_cannot_switch_or_list(
    client: TestClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    real = make_user(Role.manager, Department.finance)
    clerk = _demo(make_user, "finance.clerk", Role.employee, Department.finance)

    assert client.get("/api/auth/demo-accounts", headers=auth_header(real)).status_code == 403
    res = client.post(
        "/api/auth/demo-switch", json={"email": clerk.email}, headers=auth_header(real)
    )
    assert res.status_code == 403


def test_demo_user_cannot_reach_a_real_or_admin_or_disabled_account(
    client: TestClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    ceo = _demo(make_user, "ceo", Role.executive, Department.finance)
    real = make_user(Role.manager, Department.sales)
    admin = _demo(make_user, "boss", Role.admin, Department.finance)
    gone = make_user(
        Role.manager, Department.hr, email="hr.manager@demo.example.com", is_active=False
    )

    for target in (real, admin, gone):
        res = client.post(
            "/api/auth/demo-switch", json={"email": target.email}, headers=auth_header(ceo)
        )
        assert res.status_code == 404, target.email


def test_a_demo_admin_cannot_use_the_switcher(
    client: TestClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    admin = _demo(make_user, "boss", Role.admin, Department.finance)
    assert client.get("/api/auth/demo-accounts", headers=auth_header(admin)).status_code == 403
