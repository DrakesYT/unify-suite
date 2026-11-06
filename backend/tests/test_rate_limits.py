"""Rate limits: wrong passwords are throttled (without locking anyone else out) and every user and
IP has an AI budget, so a shared demo password can't run up the model bill."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ratelimit
from app.config import AI_RUNS_PER_USER, LOGIN_FAILURES_PER_ACCOUNT
from app.errors import ApiError
from app.llm.fake import FakeLLMClient
from app.models import AuditLog, User
from app.models.enums import Department, Role
from app.ratelimit import RateLimiter
from app.schemas.auth import LoginRequest
from app.services import users
from tests.conftest import TEST_PASSWORD

MakeUser = Callable[..., User]
AuthHeader = Callable[[User], dict[str, str]]


def _login(client: TestClient, email: str, password: str):  # type: ignore[no-untyped-def]
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_the_window_slides() -> None:
    now = [1000.0]
    limiter = RateLimiter(limit=2, window_s=60, clock=lambda: now[0])

    limiter.hit("k")
    limiter.hit("k")
    assert limiter.retry_after("k") == 60
    now[0] += 30
    assert limiter.retry_after("k") == 30
    now[0] += 30
    assert limiter.retry_after("k") == 0  # the first hits have aged out
    assert limiter.retry_after("other") == 0


def test_wrong_passwords_are_throttled_even_for_the_right_password_next(
    client: TestClient, make_user: MakeUser, db: Session
) -> None:
    user = make_user()
    for _ in range(LOGIN_FAILURES_PER_ACCOUNT):
        assert _login(client, user.email, "wrong-password").status_code == 401

    res = _login(client, user.email, TEST_PASSWORD)

    assert res.status_code == 429
    assert res.json()["error"]["code"] == "rate_limited"
    assert int(res.headers["Retry-After"]) > 0
    assert db.scalar(select(AuditLog).where(AuditLog.action == "auth.login_throttled"))


def test_throttling_one_place_does_not_lock_the_account_for_everyone(
    make_user: MakeUser, db: Session
) -> None:
    """The demo accounts are shared: a stranger typing wrong passwords must not lock judges out."""
    user = make_user()
    wrong = LoginRequest(email=user.email, password="wrong-password")
    for _ in range(LOGIN_FAILURES_PER_ACCOUNT):
        with pytest.raises(ApiError):
            users.login(db, wrong, "203.0.113.7")

    with pytest.raises(ApiError) as blocked:
        users.login(db, LoginRequest(email=user.email, password=TEST_PASSWORD), "203.0.113.7")
    signed_in, _ = users.login(
        db, LoginRequest(email=user.email, password=TEST_PASSWORD), "198.51.100.20"
    )

    assert blocked.value.status_code == 429
    assert signed_in.id == user.id


def test_one_ip_trying_many_accounts_is_throttled(make_user: MakeUser, db: Session) -> None:
    ip = "203.0.113.9"
    for n in range(ratelimit.login_failures_by_ip.limit):
        with pytest.raises(ApiError):
            users.login(db, LoginRequest(email=f"guess{n}@unify.example.com", password="x"), ip)

    with pytest.raises(ApiError) as blocked:
        users.login(db, LoginRequest(email="another@unify.example.com", password="x"), ip)
    assert blocked.value.status_code == 429


def test_a_good_sign_in_clears_the_count(make_user: MakeUser, db: Session) -> None:
    user = make_user()
    for _ in range(LOGIN_FAILURES_PER_ACCOUNT - 1):
        with pytest.raises(ApiError):
            users.login(db, LoginRequest(email=user.email, password="nope-nope"), "192.0.2.1")
    users.login(db, LoginRequest(email=user.email, password=TEST_PASSWORD), "192.0.2.1")

    for _ in range(LOGIN_FAILURES_PER_ACCOUNT - 1):  # a fresh allowance, not one try left
        with pytest.raises(ApiError) as wrong:
            users.login(db, LoginRequest(email=user.email, password="nope-nope"), "192.0.2.1")
        assert wrong.value.status_code == 401


def test_the_ai_budget_runs_out_and_says_when_it_returns(
    client: TestClient, fake_llm: FakeLLMClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    manager = make_user(Role.manager, Department.sales)
    headers = auth_header(manager)
    fake_llm.replies += [{"route": "none", "target": None, "reply": "Hello."}] * AI_RUNS_PER_USER
    for _ in range(AI_RUNS_PER_USER):
        assert (
            client.post("/api/ai/chat", json={"message": "hi"}, headers=headers).status_code == 200
        )

    res = client.post("/api/ai/chat", json={"message": "hi"}, headers=headers)

    assert res.status_code == 429
    assert "AI requests" in res.json()["error"]["message"]
    assert int(res.headers["Retry-After"]) > 0
    # Pages without the model keep working.
    assert client.get("/api/ai/brief?writer=code", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 200


def test_switching_demo_roles_does_not_multiply_the_budget(
    client: TestClient, fake_llm: FakeLLMClient, make_user: MakeUser, auth_header: AuthHeader
) -> None:
    people = [
        make_user(Role.manager, dept, email=f"m.{dept}@demo.example.com")
        for dept in (Department.sales, Department.hr, Department.finance)
    ]
    per_ip = ratelimit.ai_runs_by_ip.limit
    fake_llm.replies += [{"route": "none", "target": None, "reply": "Hello."}] * per_ip
    statuses = []
    for n in range(per_ip + 1):
        headers = auth_header(people[n % len(people)])
        statuses.append(
            client.post("/api/ai/chat", json={"message": "hi"}, headers=headers).status_code
        )

    assert statuses[:per_ip] == [200] * per_ip
    assert statuses[-1] == 429
