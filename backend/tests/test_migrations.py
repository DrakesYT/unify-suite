"""The migrations build exactly the schema the models describe, and can be undone.

Runs on SQLite always. Set TEST_POSTGRES_URL to an empty scratch PostgreSQL database to also
run it there, including the append-only audit log check.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Connection, create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from app.models import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]
TARGETS = ["sqlite"] + (["postgresql"] if os.environ.get("TEST_POSTGRES_URL") else [])


@pytest.fixture(params=TARGETS)
def connection(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Connection]:
    url = (
        f"sqlite:///{tmp_path / 'migrate.db'}"
        if request.param == "sqlite"
        else os.environ["TEST_POSTGRES_URL"]
    )
    engine = create_engine(url)
    with engine.connect() as conn:
        yield conn
    engine.dispose()


def _alembic(conn: Connection, *args: str) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.attributes["connection"] = conn
    config.attributes["configure_logger"] = False
    getattr(command, args[0])(config, *args[1:])
    conn.commit()


def test_upgrade_matches_models_and_downgrade_removes_everything(connection: Connection) -> None:
    _alembic(connection, "upgrade", "head")

    diff = compare_metadata(
        MigrationContext.configure(connection, opts={"compare_type": True}), Base.metadata
    )
    assert diff == []
    assert set(Base.metadata.tables) <= set(inspect(connection).get_table_names())

    _alembic(connection, "downgrade", "base")
    assert inspect(connection).get_table_names() == ["alembic_version"]


@pytest.mark.skipif("postgresql" not in TARGETS, reason="needs TEST_POSTGRES_URL")
def test_audit_log_is_append_only_on_postgres() -> None:
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    with engine.connect() as conn:
        _alembic(conn, "upgrade", "head")
        conn.execute(
            text(
                "INSERT INTO audit_logs (id, action, entity, detail) "
                "VALUES (gen_random_uuid(), 'test', 'test', '{}')"
            )
        )
        conn.commit()
        for statement in ("UPDATE audit_logs SET action = 'changed'", "DELETE FROM audit_logs"):
            with pytest.raises(DBAPIError, match="append-only"):
                conn.execute(text(statement))
            conn.rollback()
        _alembic(conn, "downgrade", "base")
    engine.dispose()
