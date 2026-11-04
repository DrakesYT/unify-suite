import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Must be set before the app is imported; tests override get_db so this DB is never contacted.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:1/test")

from app.db import get_db
from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_engine("sqlite://")

    def _sqlite_db() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _sqlite_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
