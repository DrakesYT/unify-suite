import os
import tempfile
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Must be set before the app is imported; tests override get_db so this DB is never contacted.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:1/test")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-0123")
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="unify-test-uploads-")
os.environ.pop("LLM_API_KEY", None)  # tests never call the real model unless they opt in

from app import security
from app.agents import runner
from app.db import get_db
from app.llm import get_llm
from app.llm.fake import FakeLLMClient
from app.main import app
from app.models import Base, User
from app.models.enums import Department, Role

TEST_PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def _fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production uses 12 rounds; 4 keeps the suite fast and tests the same code path."""
    monkeypatch.setattr(security, "BCRYPT_ROUNDS", 4)


@pytest.fixture(autouse=True)
def _no_retry_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the retry count, skip the 2 s / 8 s waits."""
    monkeypatch.setattr(runner, "AGENT_RETRY_DELAYS_S", (0, 0))


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _test_db() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _test_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(db: Session) -> Callable[..., User]:
    def _make(
        role: Role = Role.employee,
        department: Department = Department.sales,
        email: str | None = None,
        is_active: bool = True,
    ) -> User:
        user = User(
            email=email or f"{role}.{department}@unify.example.com",
            full_name=f"{role.title()} {department.title()}",
            role=role,
            department=department,
            password_hash=security.hash_password(TEST_PASSWORD),
            is_active=is_active,
        )
        db.add(user)
        db.commit()
        return user

    return _make


@pytest.fixture
def auth_header() -> Callable[[User], dict[str, str]]:
    def _header(user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {security.create_access_token(user.id)}"}

    return _header


@pytest.fixture
def fake_llm(client: TestClient) -> FakeLLMClient:
    """A scripted model wired into the app. Queue replies on `fake_llm.replies`."""
    fake = FakeLLMClient()
    app.dependency_overrides[get_llm] = lambda: fake
    return fake
