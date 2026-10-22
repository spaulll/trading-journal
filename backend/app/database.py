"""SQLite engine with WAL concurrency pragmas (PLAN Task 1.1).

All paths come from env — never hardcode /opt here.
  DATABASE_URL   e.g. sqlite:////root/trading-journal/backend/journal.db
"""

import os

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

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
    _migrate_symbol_spec()
    _migrate_trade_currency_columns()
    _migrate_trade_risk_columns()
    _migrate_fx_rate_indexes()


def _migrate_trade_currency_columns() -> None:
    """Add the quote-currency columns and label the historical rows.

    A row written before Phase 4 was priced in USD (the old estimator
    converted yen into dollars on the way in). It keeps that meaning and
    gets ``quote_currency = 'USD'`` — relabelling history as JPY while
    leaving the stored amount in dollars would corrupt every total. New
    rows are stamped with their symbol's real quote currency by
    ``app.services.trade_money``.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return
    wanted = {
        "quote_currency": "VARCHAR",
        "gross_pnl_usd": "FLOAT",
        "net_pnl_usd": "FLOAT",
    }
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(trade)")}
        for name, ddl in wanted.items():
            if name not in cols:
                conn.exec_driver_sql(f"ALTER TABLE trade ADD COLUMN {name} {ddl}")
        conn.exec_driver_sql(
            "UPDATE trade SET quote_currency = 'USD' "
            "WHERE quote_currency IS NULL OR quote_currency = ''"
        )
        conn.exec_driver_sql(
            "UPDATE trade SET gross_pnl_usd = gross_pnl "
            "WHERE gross_pnl_usd IS NULL AND gross_pnl IS NOT NULL "
            "AND quote_currency = 'USD'"
        )
        conn.exec_driver_sql(
            "UPDATE trade SET net_pnl_usd = net_pnl "
            "WHERE net_pnl_usd IS NULL AND net_pnl IS NOT NULL "
            "AND quote_currency = 'USD'"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_trade_quote_currency ON trade (quote_currency)"
        )


def _migrate_fx_rate_indexes() -> None:
    """Guarantee the per-day triple is unique on a pre-existing database."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    with engine.begin() as conn:
        try:
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_fx_rate_triple "
                "ON fx_rate (date, base, quote)"
            )
        except Exception:
            pass
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_fx_rate_date ON fx_rate (date)"
        )


def _migrate_trade_risk_columns() -> None:
    """Add the risk columns to a pre-existing trade table and fill them.

    The columns record how many dollars a trade risked. Existing rows get
    them filled in from the symbol registry so the history is not half
    populated; a trade with no stop keeps a null risk, because an unknown
    risk is not a zero risk.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return
    wanted = {
        "initial_risk": "FLOAT",
        "realized_risk": "FLOAT",
        "risk_unit": "VARCHAR",
    }
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(trade)")}
        for name, ddl in wanted.items():
            if name not in cols:
                conn.exec_driver_sql(f"ALTER TABLE trade ADD COLUMN {name} {ddl}")
    _backfill_trade_risk()


def _backfill_trade_risk() -> None:
    """Fill the risk columns for trades that predate them.

    The select deliberately names the handful of columns it needs instead
    of loading the whole ``Trade`` entity: this pass can run against a
    table that still lacks a column the ORM model gained later (the
    currency columns on a Phase-3 database, for instance), and a
    ``SELECT *`` would fail before the ALTER could fix it.
    """
    from sqlalchemy import update

    from app.models import Trade
    from app.services.symbol_registry import find_spec, risk_amount

    with Session(engine) as session:
        rows = session.exec(
            select(
                Trade.id,
                Trade.symbol,
                Trade.size,
                Trade.entry_price,
                Trade.initial_sl,
                Trade.current_sl,
            ).where(
                Trade.initial_risk.is_(None),
                Trade.entry_price.is_not(None),
                Trade.initial_sl.is_not(None),
            )
        ).all()
        if not rows:
            return
        for row in rows:
            spec = find_spec(session, row.symbol)
            initial = risk_amount(spec, row.size, row.entry_price, row.initial_sl)
            stop = row.current_sl or row.initial_sl
            session.exec(
                update(Trade)
                .where(Trade.id == row.id)
                .values(
                    initial_risk=initial,
                    realized_risk=risk_amount(spec, row.size, row.entry_price, stop),
                    risk_unit="USD" if initial is not None else None,
                )
            )
        session.commit()


def _migrate_symbol_spec() -> None:
    """Create the symbol registry and seed the default contract specs.

    The table itself is created by ``create_all`` above; this pass seeds
    it. Seeding only ever *adds* a symbol that is missing — a contract
    size the user edited in the UI survives every restart.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return
    from app.services.symbol_registry import seed_specs

    with Session(engine) as session:
        seed_specs(session)
        session.commit()


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
