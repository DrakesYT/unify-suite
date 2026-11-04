from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db import get_db
from app.main import app


def test_health_ok_when_db_reachable(client: TestClient) -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "db": "ok"}


def test_health_503_with_error_envelope_when_db_down(client: TestClient) -> None:
    class BrokenSession:
        def execute(self, *_args: object, **_kwargs: object) -> None:
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    def _broken_db() -> Iterator[BrokenSession]:
        yield BrokenSession()

    app.dependency_overrides[get_db] = _broken_db
    res = client.get("/api/health")
    assert res.status_code == 503
    assert res.json() == {
        "error": {"code": "db_unavailable", "message": "Database is not reachable"}
    }


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    res = client.get("/api/does-not-exist")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


def test_request_id_is_echoed_or_generated(client: TestClient) -> None:
    assert (
        client.get("/api/health", headers={"X-Request-ID": "abc-123"}).headers["X-Request-ID"]
        == "abc-123"
    )
    # Unsafe values (log injection) are replaced with a generated ID.
    generated = client.get("/api/health", headers={"X-Request-ID": "bad\nvalue"}).headers[
        "X-Request-ID"
    ]
    assert generated != "bad\nvalue"
    assert len(generated) == 32
