"""Browser sessions: an HttpOnly cookie, a CSRF header on writes, sign-out that ends the token."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import CSRF_HEADER, CSRF_HEADER_VALUE, SESSION_COOKIE
from app.models import User, UserSession
from app.models.enums import Department, Role
from app.security import create_access_token
from app.services import sessions
from tests.conftest import TEST_PASSWORD

MakeUser = Callable[..., User]
CSRF = {CSRF_HEADER: CSRF_HEADER_VALUE}


def _sign_in(client: TestClient, user: User) -> str:
    res = client.post("/api/auth/login", json={"email": user.email, "password": TEST_PASSWORD})
    assert res.status_code == 200, res.text
    return res.cookies[SESSION_COOKIE]


def test_the_cookie_alone_signs_the_browser_in(client: TestClient, make_user: MakeUser) -> None:
    user = make_user(Role.manager, Department.sales)
    _sign_in(client, user)

    res = client.get("/api/auth/me")  # no Authorization header: the cookie jar carries it

    assert res.status_code == 200
    assert res.json()["email"] == user.email


def test_a_cookie_write_without_the_csrf_header_is_blocked(
    client: TestClient, make_user: MakeUser
) -> None:
    make_user(Role.manager, Department.sales)
    _sign_in(client, make_user(Role.employee, Department.sales, email="rep@unify.example.com"))
    lead = {"name": "Ayesha Khan", "company": "Indus Textiles", "email": "ayesha@indus.example.com"}

    blocked = client.post("/api/sales/leads", json=lead)
    allowed = client.post("/api/sales/leads", json=lead, headers=CSRF)

    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "csrf_check_failed"
    assert allowed.status_code in (200, 201), allowed.text


def test_bearer_clients_need_no_csrf_header(
    client: TestClient, make_user: MakeUser, auth_header: Callable[[User], dict[str, str]]
) -> None:
    user = make_user(Role.employee, Department.sales)
    lead = {"name": "Bilal Ahmed", "company": "Karachi Logistics", "email": "b@kl.example.com"}

    res = client.post("/api/sales/leads", json=lead, headers=auth_header(user))

    assert res.status_code in (200, 201), res.text


def test_sign_out_ends_the_token_on_the_server(client: TestClient, make_user: MakeUser) -> None:
    user = make_user()
    token = _sign_in(client, user)

    res = client.post("/api/auth/logout", headers=CSRF)

    assert res.status_code == 204
    assert (
        'unify_session=""' in res.headers["set-cookie"] or "Max-Age=0" in res.headers["set-cookie"]
    )
    # Even a copy of the old token taken before sign-out no longer works.
    stale = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert stale.status_code == 401
    assert stale.json()["error"]["code"] == "invalid_token"


def test_sign_out_needs_the_csrf_header_too(client: TestClient, make_user: MakeUser) -> None:
    _sign_in(client, make_user())

    assert client.post("/api/auth/logout").status_code == 403
    assert client.get("/api/auth/me").status_code == 200  # still signed in


def test_a_demo_switch_ends_the_previous_token(client: TestClient, make_user: MakeUser) -> None:
    ceo = make_user(Role.executive, Department.finance, email="ceo@demo.example.com")
    clerk = make_user(Role.employee, Department.finance, email="clerk@demo.example.com")
    old = _sign_in(client, ceo)

    res = client.post("/api/auth/demo-switch", json={"email": clerk.email}, headers=CSRF)

    assert res.status_code == 200, res.text
    assert client.get("/api/auth/me").json()["email"] == clerk.email  # the new cookie
    stale = client.get("/api/auth/me", headers={"Authorization": f"Bearer {old}"})
    assert stale.status_code == 401


def test_a_token_cannot_borrow_another_users_session(
    client: TestClient, make_user: MakeUser, db: Session
) -> None:
    alice = make_user(Role.employee, Department.sales, email="alice@unify.example.com")
    mallory = make_user(Role.employee, Department.hr, email="mallory@unify.example.com")
    sessions.start(db, mallory)
    db.commit()
    mallory_session = db.query(UserSession).filter_by(user_id=mallory.id).one()

    token = create_access_token(alice.id, mallory_session.id)
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 401


def test_api_answers_are_never_cached(client: TestClient, make_user: MakeUser) -> None:
    _sign_in(client, make_user())

    for res in (client.get("/api/auth/me"), client.get("/api/health"), client.get("/api/nope")):
        assert res.headers["Cache-Control"] == "no-store", res.url
