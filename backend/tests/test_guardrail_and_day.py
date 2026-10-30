"""The day a trade belongs to, and the guardrail that reads it.

Two defects motivated these tests:

  - the daily-loss guardrail only looked at trades *opened* in the trading
    day, so a loser carried over from yesterday vanished from today's total;
  - the ledger's day filter used raw ``T00:00:00`` bounds, which is UTC
    midnight — not the configured trading-day boundary.

Both now go through the same rule: a trade belongs to the day it **closes**
(or the day it opened, while it is still running).
"""

from __future__ import annotations

from datetime import datetime

from app.models import Trade
from app.services.trading_day import set_trading_day


def _trade(
    session,
    ticket: str,
    opened: datetime,
    closed: datetime | None = None,
    net: float | None = 0.0,
) -> Trade:
    trade = Trade(
        ticket=ticket,
        symbol="GOLD",
        direction="buy",
        size=1.0,
        entry_price=2000.0,
        entry_time=opened,
        exit_time=closed,
        timestamp_open=opened,
        timestamp_close=closed,
        status="CLOSED" if closed else "OPEN",
        quote_currency="USD",
        net_pnl=net,
        fees=0.0,
    )
    session.add(trade)
    session.commit()
    session.refresh(trade)
    return trade


# --- the guardrail ---------------------------------------------------------


def test_a_loss_carried_into_today_counts_today(session, monkeypatch):
    """Opened yesterday, closed today: it is today's loss."""
    import app.routers.trades as trades_router

    # 06:00 UTC on the 29th is 11:30 IST, well inside the 29th.
    monkeypatch.setattr(trades_router, "_now", lambda: datetime(2026, 9, 29, 6, 0))
    _trade(
        session,
        "CARRY-1",
        datetime(2026, 9, 28, 10, 0),
        datetime(2026, 9, 29, 5, 0),
        net=-300.0,
    )

    guard = trades_router._guardrail_status(session)
    assert guard["day"] == "2026-09-29"
    assert guard["daily_pnl"] == -300.0
    assert guard["breached"] is True
    # It was opened yesterday, so it does not count toward "3 trades today".
    assert guard["trades"] == 0


def test_the_trade_count_still_counts_opens_today(session, monkeypatch):
    import app.routers.trades as trades_router

    monkeypatch.setattr(trades_router, "_now", lambda: datetime(2026, 9, 29, 6, 0))
    _trade(session, "TODAY-1", datetime(2026, 9, 29, 4, 0), datetime(2026, 9, 29, 5, 0))

    guard = trades_router._guardrail_status(session)
    assert guard["trades"] == 1
    assert guard["daily_pnl"] == 0.0


def test_an_unpriced_close_is_not_counted_as_zero(session, monkeypatch):
    """No USD value is unknown, not break-even.

    The total stays on priced trades and the day is flagged as incomplete,
    so a missing FX rate cannot quietly hide a loss.
    """
    import app.routers.trades as trades_router

    monkeypatch.setattr(trades_router, "_now", lambda: datetime(2026, 9, 29, 6, 0))
    _trade(
        session,
        "UNPRICED-1",
        datetime(2026, 9, 29, 4, 0),
        datetime(2026, 9, 29, 5, 0),
        net=None,
    )

    guard = trades_router._guardrail_status(session)
    assert guard["daily_pnl"] == 0.0
    assert guard["unpriced"] == 1
    assert guard["data_incomplete"] is True
    assert guard["breached"] is False


# --- the day filter --------------------------------------------------------


def test_the_day_filter_uses_the_close_day_not_utc_midnight(client, session):
    """5 PM New York splits two closes that share a UTC date."""
    client.put(
        "/api/settings/trading-day",
        json={"boundary_hour": 17, "timezone": "America/New_York"},
    )
    _trade(
        session,
        "BEFORE-RESET",
        datetime(2026, 10, 6, 14, 0),
        datetime(2026, 10, 6, 17, 43),
        net=120.0,
    )
    _trade(
        session,
        "AFTER-RESET",
        datetime(2026, 10, 6, 20, 0),
        datetime(2026, 10, 6, 21, 43),
        net=-80.0,
    )

    sixth = client.get("/api/trades", params={"day": "2026-10-06"}).json()
    seventh = client.get("/api/trades", params={"day": "2026-10-07"}).json()
    assert [row["ticket"] for row in sixth["items"]] == ["BEFORE-RESET"]
    assert [row["ticket"] for row in seventh["items"]] == ["AFTER-RESET"]

    ids = client.get("/api/trades/ids", params={"day": "2026-10-07"}).json()
    assert ids["total"] == 1


def test_a_day_range_is_inclusive_at_both_ends(client, session):
    client.put(
        "/api/settings/trading-day",
        json={"boundary_hour": 17, "timezone": "America/New_York"},
    )
    _trade(session, "OCT-6", datetime(2026, 10, 6, 12, 0), datetime(2026, 10, 6, 17, 43))
    _trade(session, "OCT-7", datetime(2026, 10, 6, 18, 0), datetime(2026, 10, 6, 21, 43))
    _trade(session, "OCT-8", datetime(2026, 10, 7, 20, 0), datetime(2026, 10, 7, 22, 0))

    rows = client.get(
        "/api/trades", params={"day_from": "2026-10-06", "day_to": "2026-10-07"}
    ).json()
    assert {row["ticket"] for row in rows["items"]} == {"OCT-6", "OCT-7"}


def test_the_day_filter_finds_a_trade_still_open(client, session):
    client.put(
        "/api/settings/trading-day",
        json={"boundary_hour": 17, "timezone": "America/New_York"},
    )
    _trade(session, "RUNNING-1", datetime(2026, 10, 6, 14, 0), None)

    day = client.get("/api/trades", params={"day": "2026-10-06"}).json()
    assert [row["ticket"] for row in day["items"]] == ["RUNNING-1"]


def test_the_day_filter_moves_with_the_boundary(client, session):
    _trade(
        session,
        "LATE-1",
        datetime(2026, 10, 6, 14, 0),
        datetime(2026, 10, 6, 18, 30),
        net=10.0,
    )

    # Kolkata midnight: 18:30 UTC is 00:00 the next morning.
    assert [
        row["ticket"]
        for row in client.get("/api/trades", params={"day": "2026-10-07"}).json()["items"]
    ] == ["LATE-1"]

    # 5 PM New York: 18:30 UTC is 14:30 in New York, still the same day.
    set_trading_day(session, 17, "America/New_York")
    session.commit()
    assert [
        row["ticket"]
        for row in client.get("/api/trades", params={"day": "2026-10-06"}).json()["items"]
    ] == ["LATE-1"]
