"""Smoke test for the pytest harness itself.

Guards the two things that silently break a test suite:
  - the app must talk to the throwaway database, never the real journal.db
  - the tables must be truncated between tests
"""

from __future__ import annotations

from sqlmodel import select

from app.database import DATABASE_URL, engine
from app.models import Trade


def test_runs_against_a_temporary_database():
    assert DATABASE_URL.endswith("trading-journal-tests/journal.db")
    assert "trading-journal/backend/journal.db" not in DATABASE_URL


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_truncation_leaves_a_row_behind(session):
    """First half: a row written in this test is visible inside it."""
    session.add(Trade(ticket="SMOKE-1", symbol="GOLD", direction="buy"))
    session.commit()
    assert len(session.exec(select(Trade)).all()) == 1


def test_truncation_clears_the_next_test(session):
    """Second half: the autouse fixture wiped the previous test's row."""
    assert len(session.exec(select(Trade)).all()) == 0
