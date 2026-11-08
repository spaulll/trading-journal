"""Regression tests for the trade close pipeline and the guardrail.

Every case here is a defect that shipped once:
  - a drawer close that left the close timestamp null
  - a guardrail that only ran on the bot close path
  - a ticket that collided when two trades opened in the same second
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlmodel import select

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


# --- non-USD quote currencies -----------------------------------------------
#
# A manual P&L / fee entry mirrors what the broker statement shows: account
# currency, USD. For a JPY-quoted pair (USDJPY) the stored quote-currency
# amount must be derived from that USD input, not stored verbatim.


def _open_jpy(client) -> dict:
    return _open(
        client,
        symbol="USDJPY",
        direction="sell",
        size=0.2,
        entry_price=158.326,
        initial_sl=158.6,
        tp=157.493,
    )


def test_close_usdjpy_explicit_usd_money_is_converted_to_quote(client):
    """close usdjpy, 158.49, -20.7, fee: 1 — USD in, JPY stored."""
    trade = _open_jpy(client)
    tsl = client.post(f"/api/trades/{trade['id']}/tsl", json={"current_sl": 158.49})
    assert tsl.status_code == 200, tsl.text
    response = client.post(
        f"/api/trades/{trade['id']}/close",
        json={"exit_price": 158.49, "gross_pnl": -20.7, "fees": 1.0},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["gross_pnl"] == pytest.approx(-3280.74, abs=0.01)
    assert body["fees"] == pytest.approx(158.49, abs=0.01)
    assert body["net_pnl"] == pytest.approx(-3439.23, abs=0.01)
    assert body["gross_pnl_usd"] == pytest.approx(-20.70, abs=0.01)
    assert body["net_pnl_usd"] == pytest.approx(-21.70, abs=0.01)
    assert body["r_multiple"] == -1.0


def test_close_usdjpy_estimates_gross_when_left_blank(client):
    """Leave gross blank: the price-based estimate is the safe default."""
    trade = _open_jpy(client)
    tsl = client.post(f"/api/trades/{trade['id']}/tsl", json={"current_sl": 158.49})
    assert tsl.status_code == 200, tsl.text
    response = client.post(
        f"/api/trades/{trade['id']}/close",
        json={"exit_price": 158.49, "fees": 1.0},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["gross_pnl"] == pytest.approx(-3280.0, abs=0.01)
    assert body["fees"] == pytest.approx(158.49, abs=0.01)
    assert body["net_pnl"] == pytest.approx(-3438.49, abs=0.01)
    assert body["net_pnl_usd"] == pytest.approx(-21.70, abs=0.02)
    assert body["r_multiple"] == -1.0


def test_patch_fees_on_jpy_pair_converts_usd_to_quote(client):
    trade = _open_jpy(client)
    response = client.patch(f"/api/trades/{trade['id']}", json={"fees": 1.0})
    assert response.status_code == 200, response.text
    # The trade is still open, so the implied rate comes from the entry
    # price (158.326) — the close-day exit price is not known yet.
    assert response.json()["fees"] == pytest.approx(158.33, abs=0.01)


def test_backfill_usdjpy_pnl_in_usd_converts_to_quote(client, session):
    payload = {
        "symbol": "USDJPY",
        "direction": "sell",
        "size": 0.2,
        "entry_price": 158.326,
        "exit_price": 158.49,
        "initial_sl": 158.6,
        "entry_time": "2026-11-06T13:04:33",
        "exit_time": "2026-11-06T19:25:34",
        "gross_pnl": -20.7,
        "fees": 1.0,
    }
    response = client.post("/api/trades/backfill", json=payload)
    assert response.status_code == 200, response.text
    ticket = response.json()["inserted"][0]
    trade = session.exec(select(Trade).where(Trade.ticket == ticket)).first()
    assert trade is not None
    assert trade.gross_pnl == pytest.approx(-3280.74, abs=0.01)
    assert trade.fees == pytest.approx(158.49, abs=0.01)
    assert trade.net_pnl == pytest.approx(-3439.23, abs=0.01)
    assert trade.gross_pnl_usd == pytest.approx(-20.70, abs=0.01)
    assert trade.net_pnl_usd == pytest.approx(-21.70, abs=0.01)


def test_close_gold_explicit_usd_money_passes_through(client):
    """USD-quoted symbols are untouched: identity conversion."""
    trade = _open(client)
    response = client.post(
        f"/api/trades/{trade['id']}/close",
        json={"exit_price": 4015.0, "gross_pnl": 150.0, "fees": 0.5},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["gross_pnl"] == 150.0
    assert body["fees"] == 0.5
    assert body["net_pnl"] == 149.5
    assert body["gross_pnl_usd"] == 150.0
    assert body["net_pnl_usd"] == 149.5


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


# --- every close path writes the same record --------------------------------


def test_the_bot_close_writes_the_same_record_as_the_api(client, session):
    """Telegram, the API and the drawer must all leave the same shape.

    The bot close used to set only timestamp_close, so a trade closed
    from Telegram had no exit time and no holding duration.
    """
    import asyncio

    from app.services.telegram_bot import do_close_on_trade

    sent: list[tuple[int, str]] = []
    trade = _open(client)

    async def fake_send(chat_id: int, text: str, *args, **kwargs) -> int:
        sent.append((chat_id, text))
        return 1

    import app.services.telegram_bot as bot

    original = bot.send_text
    bot.send_text = fake_send
    try:
        asyncio.run(
            do_close_on_trade(
                1,
                session,
                trade["id"],
                {
                    "exit_price": 4020.0,
                    "gross_pnl": 200.0,
                    "fees": 0.0,
                    "review_notes": None,
                    "mistake_tags": [],
                },
            )
        )
    finally:
        bot.send_text = original

    session.expire_all()
    stored = session.get(Trade, trade["id"])
    assert stored is not None
    assert stored.status == "CLOSED"
    assert stored.timestamp_close is not None
    assert stored.exit_time == stored.timestamp_close
    assert stored.duration_minutes is not None
    assert stored.duration_minutes >= 0
    assert stored.net_pnl == 200.0
    assert stored.r_multiple == 2.0
