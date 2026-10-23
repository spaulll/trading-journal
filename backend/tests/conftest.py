"""Shared pytest fixtures for the trading-journal backend.

Every test runs against a throwaway SQLite database so the real
``journal.db`` is never touched. The ``DATABASE_URL`` override has to be in
place *before* ``app.database`` is imported, because that module reads the
environment at import time to build the engine.

``load_dotenv()`` in ``app.main`` does not override variables that are already
set, so the override below wins over ``backend/.env``.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# --- environment overrides, applied before any app import -------------------

_TMP_DIR = Path(tempfile.gettempdir()) / "trading-journal-tests"
_TMP_DIR.mkdir(parents=True, exist_ok=True)
_TMP_DB = _TMP_DIR / "journal.db"

os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
# Never start the Telegram poller or the scheduler during tests.
os.environ["TG_BOT_TOKEN"] = ""
os.environ["TG_ALLOWED_USER_ID"] = ""
# Deterministic guardrail caps so tests can assert on breaches.
os.environ["MAX_DAILY_LOSS"] = "-250.0"
os.environ["MAX_DAILY_TRADES"] = "3"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app.database import create_db_and_tables, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.symbol_registry import seed_specs  # noqa: E402

# Tables truncated between tests, in dependency order.
_TABLES = (
    "trade_tag_link",
    "screenshot",
    "trade",
    "tag",
    "daily_note",
    "account_rule",
    "account_event",
    "cash_entry",
    "account",
    "app_setting",
    "import_run",
    "insight_report",
    "symbol_spec",
    "fx_rate",
)


@pytest.fixture(scope="session", autouse=True)
def _database():
    """Create the schema once for the whole run, then drop the files."""
    create_db_and_tables()
    yield
    engine.dispose()
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(_TMP_DB) + suffix)
        if path.exists():
            path.unlink()


@pytest.fixture(autouse=True)
def _reset_db():
    """Truncate every table before each test, then restore the seed data."""
    with engine.begin() as conn:
        for table in _TABLES:
            conn.exec_driver_sql(f"DELETE FROM {table}")
    # The symbol registry is seeded data, not a fixture of the test: a test
    # that truncates it would price every trade as unpriced. Re-seed it so
    # each test starts from the shipped default registry.
    with Session(engine) as db:
        seed_specs(db)
        db.commit()
    yield


@pytest.fixture
def client() -> TestClient:
    """HTTP client for the app.

    Used without a context manager on purpose: the FastAPI lifespan starts the
    APScheduler and the Telegram poller, neither of which belongs in a test.
    """
    return TestClient(app)


@pytest.fixture
def session() -> Session:
    """Direct database session for assertions that bypass the API."""
    with Session(engine) as db:
        yield db
