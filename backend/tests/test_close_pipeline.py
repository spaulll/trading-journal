"""Regression tests for the trade close pipeline and the guardrail.

Every case here is a defect that shipped once:
  - a drawer close that left the close timestamp null
  - a guardrail that only ran on the bot close path
  - a ticket that collided when two trades opened in the same second
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models import Trade
from app.services.telegram_bot import daily_stats_text


def _open(client, symbol: str = "GOLD", **overrides) -> dict:
    payload = {
        "symbol": symbol,
        "direction": "buy",
        "size": 0.1,
        "entry_price": 4000.0,
        "initial_sl": 3990.0,
        "tp": 4020.0,
    }
    payload.update(overrides)
    response = client.post("/api/trades/open", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# --- the close pipeline ----------------------------------------------------


def test_patch_close_writes_the_full_close_record(client):
    """Saving an exit from the drawer must record when the trade closed."""
    trade = _open(client)
    response = client.patch(f"/api/trades/{trade['id']}", json={"exit_price": 4020.0})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "CLOSED"
    assert body["timestamp_close"] is not None
    assert body["exit_time"] is not None
    assert body["duration_minutes"] is not None
    assert body["net_pnl"] == 200.0
    assert body["r_multiple"] == 2.0


def test_patch_close_keeps_the_close_record_when_the_client_sends_status(client):
    """A client that also sends status=CLOSED must not lose the close record."""
    trade = _open(client)
    response = client.patch(
        f"/api/trades/{trade['id']}", json={"exit_price": 4020.0, "status": "CLOSED"}
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "CLOSED"
    assert body["timestamp_close"] is not None
    assert body["exit_time"] is not None
    assert body["duration_minutes"] is not None


def test_patch_close_keeps_an_explicit_exit_time(client):
    trade = _open(client)
    stamp = "2026-09-28T16:39:06"
    response = client.patch(
        f"/api/trades/{trade['id']}", json={"exit_price": 4020.0, "exit_time": stamp}
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["timestamp_close"] == stamp
    assert body["exit_time"] == stamp


def test_patch_keeps_an_open_trade_open_when_asked(client):
    """An explicit status=OPEN is a deliberate choice, not a close."""
    trade = _open(client)
    response = client.patch(
        f"/api/trades/{trade['id']}", json={"exit_price": 4020.0, "status": "OPEN"}
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "OPEN"
    assert body["timestamp_close"] is None


def test_a_closed_trade_shows_up_in_the_daily_stats(client, session):
    """The bug this guards: a closed trade was invisible to the bot."""
    trade = _open(client)
    client.patch(f"/api/trades/{trade['id']}", json={"exit_price": 4020.0})

    today = datetime.now(timezone.utc).date()
    text = daily_stats_text(session, today)

    assert trade["ticket"] in text
    assert "1 closed" in text


def test_a_closed_trade_is_bucketed_on_its_close_day(client):
    trade = _open(client)
    client.patch(f"/api/trades/{trade['id']}", json={"exit_price": 4020.0})

    response = client.get("/api/analytics/calendar")
    assert response.status_code == 200
    days = response.json()["days"]
    closed_on = {d["date"] for d in days}
    today = datetime.now(timezone.utc).date().isoformat()
    assert today in closed_on


# --- the guardrail ---------------------------------------------------------


def test_guardrail_flags_a_breach_on_a_drawer_close(client, session):
    """A loss past the daily cap must flag the day, not just the bot close."""
    trade = _open(client)
    response = client.patch(
        f"/api/trades/{trade['id']}", json={"exit_price": 3600.0, "gross_pnl": -400.0}
    )
    assert response.status_code == 200, response.text

    notes = client.get("/api/daily-notes").json()
    assert notes, "the breach day was never flagged"
    assert notes[0]["discipline_breach"] is True


def test_guardrail_ignores_a_plain_edit(client):
    """Editing an open trade is not a close and must not flag a breach."""
    trade = _open(client)
    response = client.patch(f"/api/trades/{trade['id']}", json={"thesis": "waiting"})
    assert response.status_code == 200, response.text

    assert client.get("/api/daily-notes").json() == []


def test_guardrail_ignores_a_winning_close(client):
    trade = _open(client)
    response = client.patch(f"/api/trades/{trade['id']}", json={"exit_price": 4020.0})
    assert response.status_code == 200, response.text

    assert client.get("/api/daily-notes").json() == []


# --- tickets ---------------------------------------------------------------


def test_two_opens_in_the_same_second_get_unique_tickets(client):
    """The generated ticket had second precision and collided on the index."""
    first = _open(client, symbol="NAS100")
    second = _open(client, symbol="NAS100")

    assert first["ticket"] != second["ticket"]
    assert first["id"] != second["id"]


def test_an_explicit_duplicate_ticket_is_rejected(client):
    """An explicit ticket that already exists is still a conflict."""
    _open(client, symbol="EURUSD", ticket="FIXED-1")
    response = client.post(
        "/api/trades/open",
        json={
            "symbol": "EURUSD",
            "direction": "buy",
            "size": 0.1,
            "entry_price": 1.1,
            "initial_sl": 1.09,
            "ticket": "FIXED-1",
        },
    )
    assert response.status_code == 409


def test_trades_keep_their_ticket_after_a_close(client, session):
    trade = _open(client)
    client.patch(f"/api/trades/{trade['id']}", json={"exit_price": 4020.0})

    stored = session.get(Trade, trade["id"])
    assert stored is not None
    assert stored.ticket == trade["ticket"]
