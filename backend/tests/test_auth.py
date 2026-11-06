"""FR-AUTH-01: email + password login returns a JWT valid for 8 hours."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import SESSION_COOKIE, get_settings
from app.models import AuditLog, User
from app.models.enums import Department, Role
from app.security import create_access_token
from app.services import sessions
from tests.conftest import TEST_PASSWORD

MakeUser = Callable[..., User]


def _login(client: TestClient, email: str, password: str = TEST_PASSWORD):  # type: ignore[no-untyped-def]
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_valid_login_sets_an_8_hour_httponly_session_cookie(
    client: TestClient, make_user: MakeUser
) -> None:
    user = make_user(Role.manager, Department.finance)

    res = _login(client, user.email)

    assert res.status_code == 200
    body = res.json()
    assert "access_token" not in body  # the token never reaches page scripts
    assert body["expires_in"] == 8 * 3600
    assert body["user"] == {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": "manager",
        "department": "finance",
    }
    cookie = res.headers["set-cookie"]
    for flag in ("HttpOnly", "SameSite=strict", "Path=/api", "Max-Age=28800"):
        assert flag.lower() in cookie.lower(), flag
    claims = jwt.decode(
        res.cookies[SESSION_COOKIE],
        get_settings().jwt_secret.get_secret_value(),
        algorithms=["HS256"],
    )
    assert claims["sub"] == str(user.id)
    assert claims["exp"] - claims["iat"] == 8 * 3600
    assert claims["sid"]


def test_wrong_password_returns_401(client: TestClient, make_user: MakeUser) -> None:
    user = make_user()

    res = _login(client, user.email, "wrong-password")

    assert res.status_code == 401
    assert res.json() == {
        "error": {"code": "invalid_credentials", "message": "Email or password is incorrect"}
    }
    assert res.headers["WWW-Authenticate"] == "Bearer"


def test_unknown_email_gets_the_same_401(client: TestClient) -> None:
    res = _login(client, "nobody@unify.example.com")

    assert res.status_code == 401
    assert res.json()["error"]["code"] == "invalid_credentials"


def test_email_is_case_insensitive(client: TestClient, make_user: MakeUser) -> None:
    user = make_user()

    assert _login(client, user.email.upper()).status_code == 200


def test_overlong_password_is_rejected_not_crashed(client: TestClient, make_user: MakeUser) -> None:
    user = make_user()

    assert _login(client, user.email, "x" * 100).status_code == 401


def test_disabled_account_cannot_log_in(client: TestClient, make_user: MakeUser) -> None:
    user = make_user(is_active=False)

    res = _login(client, user.email)

    assert res.status_code == 403
    assert res.json()["error"]["code"] == "account_disabled"


def test_login_attempts_are_audited(client: TestClient, make_user: MakeUser, db: Session) -> None:
    user = make_user()
    _login(client, user.email)
    _login(client, user.email, "wrong-password")

    rows = db.scalars(select(AuditLog).order_by(AuditLog.at)).all()
    assert [(r.action, r.actor_id) for r in rows] == [
        ("auth.login", user.id),
        ("auth.login_failed", None),
    ]
    assert TEST_PASSWORD not in str(rows[1].detail)


def test_me_returns_the_signed_in_user(
    client: TestClient, make_user: MakeUser, auth_header: Callable[[User], dict[str, str]]
) -> None:
    user = make_user(Role.executive, Department.hr)

    res = client.get("/api/auth/me", headers=auth_header(user))

    assert res.status_code == 200
    assert res.json()["email"] == user.email


def test_me_without_token_is_401(client: TestClient) -> None:
    res = client.get("/api/auth/me")

    assert res.status_code == 401
    assert res.json()["error"]["code"] == "not_authenticated"


def test_me_rejects_bad_expired_and_disabled_tokens(
    client: TestClient, make_user: MakeUser, db: Session
) -> None:
    user = make_user()
    old = datetime.now(UTC) - timedelta(hours=9)
    expired = sessions.start(db, user, now=old)
    unknown_session = create_access_token(user.id, uuid.uuid4())
    forged = jwt.encode(
        {"sub": str(user.id), "sid": str(uuid.uuid4()), "iat": 0, "exp": 9999999999},
        "x" * 32,
        "HS256",
    )
    db.commit()

    for token in ("not-a-jwt", expired, unknown_session, forged):
        res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401, token
        assert res.json()["error"]["code"] == "invalid_token"

    valid = sessions.start(db, user)
    user.is_active = False
    db.commit()
    assert (
        client.get("/api/auth/me", headers={"Authorization": f"Bearer {valid}"}).status_code == 401
    )
