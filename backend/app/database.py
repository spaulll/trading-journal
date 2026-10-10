"""SQLite engine with WAL concurrency pragmas (PLAN Task 1.1).

All paths come from env — never hardcode /opt here.
  DATABASE_URL   e.g. sqlite:////root/trading-journal/backend/journal.db
"""

import os

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./journal.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=_connect_args)

if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ANN001, ANN202
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.close()


def create_db_and_tables() -> None:
    from app import models  # noqa: F401 — register table models

    SQLModel.metadata.create_all(engine)
    _migrate_screenshot_columns()
    _migrate_account_columns()


def _migrate_account_columns() -> None:
    """Create account table + trade.account_id on pre-existing DBs.

    Leaves existing trades with NULL account_id — the user reassigns
    them manually from the web UI. No backfill, no default account.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.exec_driver_sql(
            """CREATE TABLE IF NOT EXISTS account (
            id INTEGER NOT NULL PRIMARY KEY,
            firm VARCHAR NOT NULL,
            alias VARCHAR NOT NULL,
            login VARCHAR,
            phase VARCHAR NOT NULL,
            start_balance FLOAT NOT NULL,
            daily_loss_limit FLOAT NOT NULL,
            daily_loss_pct FLOAT NOT NULL DEFAULT 0.0,
            daily_basis VARCHAR NOT NULL,
            max_loss_limit FLOAT NOT NULL,
            max_loss_pct FLOAT NOT NULL DEFAULT 0.0,
            max_mode VARCHAR NOT NULL,
            trailing_ref VARCHAR NOT NULL,
            profit_target FLOAT,
            profit_target_pct FLOAT,
            status VARCHAR NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL)"""
        )
        try:
            conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS ix_account_alias ON account (alias)")
        except Exception:
            pass
        try:
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_account_firm ON account (firm)")
        except Exception:
            pass
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(account)")}
        if "daily_loss_pct" not in cols:
            conn.exec_driver_sql("ALTER TABLE account ADD COLUMN daily_loss_pct FLOAT NOT NULL DEFAULT 0.0")
        if "max_loss_pct" not in cols:
            conn.exec_driver_sql("ALTER TABLE account ADD COLUMN max_loss_pct FLOAT NOT NULL DEFAULT 0.0")
        if "profit_target_pct" not in cols:
            conn.exec_driver_sql("ALTER TABLE account ADD COLUMN profit_target_pct FLOAT")
        # One-time backfill: % = $ / start * 100 for rows created with $ limits.
        try:
            conn.exec_driver_sql(
                """UPDATE account SET daily_loss_pct =
                   CASE WHEN start_balance > 0 AND (daily_loss_pct IS NULL OR daily_loss_pct = 0)
                   THEN daily_loss_limit * 100.0 / start_balance ELSE daily_loss_pct END,
                   max_loss_pct =
                   CASE WHEN start_balance > 0 AND (max_loss_pct IS NULL OR max_loss_pct = 0)
                   THEN max_loss_limit * 100.0 / start_balance ELSE max_loss_pct END,
                   profit_target_pct =
                   CASE WHEN start_balance > 0 AND profit_target_pct IS NULL AND profit_target IS NOT NULL
                   THEN profit_target * 100.0 / start_balance ELSE profit_target_pct END"""
            )
        except Exception:
            pass
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(trade)")}
        if "account_id" not in cols:
            conn.exec_driver_sql("ALTER TABLE trade ADD COLUMN account_id INTEGER")
        try:
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_trade_account_id ON trade (account_id)")
        except Exception:
            pass


def _migrate_screenshot_columns() -> None:
    """Add trade-aware screenshot columns to pre-existing DBs."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    from sqlalchemy import text

    wanted = {
        "original_filename": "VARCHAR",
        "stored_filename": "VARCHAR",
        "sha256": "VARCHAR",
        "byte_size": "INTEGER",
    }
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(screenshot)")}
        for name, ddl in wanted.items():
            if name not in cols:
                conn.exec_driver_sql(f"ALTER TABLE screenshot ADD COLUMN {name} {ddl}")
        if "sha256" in {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(screenshot)")}:
            try:
                conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS ix_screenshot_sha256 ON screenshot (sha256)"
                )
            except Exception:
                pass


def get_session():  # noqa: ANN202
    with Session(engine) as session:
        yield session
