"""Test configuration.

Tests that need the database run against a dedicated ``<db>_test`` database on the
PostGIS server from docker compose (``docker compose up -d db``) or the CI service.
Settings are pointed at it before the app is imported.
"""

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

BASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://geomeasure:geomeasure@localhost:5433/geomeasure"
)
TEST_URL = make_url(BASE_URL).set(database=f"{make_url(BASE_URL).database}_test")

os.environ["DATABASE_URL"] = TEST_URL.render_as_string(hide_password=False)
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="geomeasure-test-uploads-")
os.environ.setdefault("REDIS_URL", "redis://localhost:6380/0")


def _create_test_database() -> None:
    admin = create_engine(make_url(BASE_URL).set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_URL.database}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{TEST_URL.database}"'))
    except Exception as exc:  # pragma: no cover - environment problem, not a test failure mode
        raise RuntimeError(
            f"Cannot reach PostGIS at {make_url(BASE_URL).render_as_string()}. "
            "Start it with `docker compose up -d db`."
        ) from exc
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def database() -> Iterator[str]:
    from alembic import command
    from alembic.config import Config

    _create_test_database()
    config = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    config.attributes["database_url"] = os.environ["DATABASE_URL"]
    command.upgrade(config, "head")
    yield os.environ["DATABASE_URL"]


@pytest.fixture
def session(database: str) -> Iterator[Session]:
    from app.db.session import get_engine, get_sessionmaker

    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE uploads CASCADE"))
    with get_sessionmaker()() as s:
        yield s


@pytest.fixture
def enqueued(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Capture Celery enqueues instead of talking to Redis."""
    from app.worker import tasks

    calls: list[str] = []
    monkeypatch.setattr(tasks.process_upload_task, "delay", calls.append)
    return calls


@pytest.fixture
def client(session: Session, enqueued: list[str]) -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as c:
        yield c
