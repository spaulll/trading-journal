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


def get_session():  # noqa: ANN202
    with Session(engine) as session:
        yield session
