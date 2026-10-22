"""Tests for the analytics bucketing.

The dashboard, the bot and the API must bucket the same trade the same way.
This file locks down the four buckets that decide what the trader sees:

  - the breakeven band — a scratch is neither a win nor a loss
  - the close day     — a trade belongs to the day it closed
  - the streak runs   — consecutive wins and losses, broken by a scratch
  - the R buckets     — the distribution chart's binning
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session

from app.database import engine
from app.models import Tag, Trade, TradeTagLink
from app.routers.analytics import _closed_trades, _r_bucket, _streak_runs


def _closed(
    ticket: str,
    net: float | None,
    *,
    opened: datetime,
    closed: datetime | None = None,
    r: float | None = None,
    symbol: str = "GOLD",
    direction: str = "buy",
    size: float = 0.1,
    tags: list[str] | None = None,
) -> Trade:
    """A CLOSED trade row with an explicit net, ready for the session."""
    return Trade(
        ticket=ticket,
        symbol=symbol,
        direction=direction,
        size=size,
        entry_price=4000.0,
        initial_sl=3990.0,
        exit_price=4010.0,
        timestamp_open=opened,
        timestamp_close=closed if closed is not None else opened,
        net_pnl=net,
        gross_pnl=net,
        r_multiple=r,
        status="CLOSED",
        tags=[Tag(name=name, category="setup") for name in (tags or [])],
    )


def _store(trades: list[Trade]) -> None:
    with Session(engine) as session:
        for trade in trades:
            session.add(trade)
        session.commit()


# --- the breakeven bucket --------------------------------------------------


def test_a_scratch_trade_is_neither_a_win_nor_a_loss(client):
    _store([_closed("BE-1", 3.0, opened=datetime(2026, 9, 1, 10, 0))])
    summary = client.get("/api/analytics/summary").json()
    assert summary["wins"] == 0
    assert summary["losses"] == 0
    assert summary["breakeven"] == 1
    assert summary["total_trades"] == 1


def test_a_trade_without_a_net_counts_as_unpriced(client):
    """An unpriced trade is not a scratch — its outcome is unknown.

    Counting it as a breakeven would drag the win rate down over a trade
    that was never priced.
    """
    _store([_closed("NONE-1", None, opened=datetime(2026, 9, 1, 10, 0))])
    summary = client.get("/api/analytics/summary").json()
    assert summary["unpriced"] == 1
    assert summary["breakeven"] == 0
    assert summary["wins"] == 0
    assert summary["losses"] == 0
    assert summary["net_pnl"] == 0.0
    assert summary["win_rate"] == 0.0


def test_the_breakeven_band_holds_at_the_api_boundary(client):
    """Exactly $5 is a scratch; a cent more is a win."""
    _store(
        [
            _closed("EDGE-1", 5.0, opened=datetime(2026, 9, 1, 10, 0)),
            _closed("EDGE-2", 5.01, opened=datetime(2026, 9, 1, 11, 0)),
            _closed("EDGE-3", -5.0, opened=datetime(2026, 9, 1, 12, 0)),
            _closed("EDGE-4", -5.01, opened=datetime(2026, 9, 1, 13, 0)),
        ]
    )
    summary = client.get("/api/analytics/summary").json()
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["breakeven"] == 2


def test_the_breakeven_count_is_reported_next_to_the_rate(client):
    _store(
        [
            _closed("RATE-1", 200.0, opened=datetime(2026, 9, 1, 10, 0)),
            _closed("RATE-2", -100.0, opened=datetime(2026, 9, 1, 11, 0)),
            _closed("RATE-3", 0.0, opened=datetime(2026, 9, 1, 12, 0)),
        ]
    )
    kpi = client.get("/api/analytics/kpi-dashboard").json()["win_rate"]
    assert kpi["rate"] == 50.0
    assert kpi["wins"] == 1
    assert kpi["losses"] == 1
    assert kpi["breakeven"] == 1


# --- the close-day bucket --------------------------------------------------


def test_a_trade_lands_on_the_day_it_closed(client):
    """Opened on the 27th, closed on the 28th — the 28th owns it."""
    _store(
        [
            _closed(
                "DAY-1",
                100.0,
                opened=datetime(2026, 9, 27, 23, 30),
                closed=datetime(2026, 9, 28, 0, 15),
            )
        ]
    )
    days = client.get("/api/analytics/calendar", params={"year": 2026}).json()["days"]
    assert days == [
        {
            "date": "2026-09-28",
            "net_pnl": 100.0,
            "trade_count": 1,
            "unpriced": 0,
            "by_currency": {"USD": 100.0},
        }
    ]


def test_a_trade_closed_at_2330_stays_on_that_day(client):
    _store(
        [_closed("LATE-1", -50.0, opened=datetime(2026, 9, 28, 23, 0), closed=datetime(2026, 9, 28, 23, 30))]
    )
    days = client.get("/api/analytics/calendar", params={"year": 2026}).json()["days"]
    assert [d["date"] for d in days] == ["2026-09-28"]
    assert days[0]["net_pnl"] == -50.0


def test_a_day_totals_every_trade_closed_on_it(client):
    _store(
        [
            _closed("SUM-1", 100.0, opened=datetime(2026, 9, 28, 8, 0)),
            _closed("SUM-2", -40.0, opened=datetime(2026, 9, 28, 9, 0)),
            _closed("SUM-3", 5.0, opened=datetime(2026, 9, 28, 10, 0)),
        ]
    )
    days = client.get("/api/analytics/calendar", params={"year": 2026}).json()["days"]
    assert len(days) == 1
    assert days[0]["trade_count"] == 3
    assert days[0]["net_pnl"] == 65.0


def test_the_calendar_ignores_another_year(client):
    _store([_closed("OLD-1", 100.0, opened=datetime(2025, 9, 28, 10, 0))])
    days = client.get("/api/analytics/calendar", params={"year": 2026}).json()["days"]
    assert days == []


def test_the_monthly_calendar_buckets_on_the_close_day(client):
    _store(
        [
            _closed(
                "MC-1",
                120.0,
                opened=datetime(2026, 9, 30, 23, 45),
                closed=datetime(2026, 10, 1, 0, 10),
            )
        ]
    )
    sept = client.get(
        "/api/analytics/monthly-calendar", params={"year": 2026, "month": 9}
    ).json()
    assert sept["days"]["2026-09-30"]["trade_count"] == 0
    assert sept["summary"]["trading_days"] == 0

    october = client.get(
        "/api/analytics/monthly-calendar", params={"year": 2026, "month": 10}
    ).json()
    assert october["days"]["2026-10-01"]["trade_count"] == 1
    assert october["days"]["2026-10-01"]["outcome"] == "win"


def test_a_scratch_day_is_a_breakeven_day(client):
    _store([_closed("MC-BE", 2.0, opened=datetime(2026, 10, 2, 10, 0))])
    body = client.get(
        "/api/analytics/monthly-calendar", params={"year": 2026, "month": 10}
    ).json()
    assert body["days"]["2026-10-02"]["outcome"] == "be"
    assert body["summary"]["breakeven_days"] == 1


def test_the_closed_trade_query_orders_by_close_time():
    """The equity curve walks the trades in close order, nulls last."""
    with Session(engine) as session:
        session.add(_closed("ORD-3", 10.0, opened=datetime(2026, 9, 3, 10, 0)))
        session.add(_closed("ORD-1", 10.0, opened=datetime(2026, 9, 1, 10, 0)))
        session.add(_closed("ORD-2", 10.0, opened=datetime(2026, 9, 2, 10, 0)))
        session.commit()

        trades = _closed_trades(session)

    assert [t.ticket for t in trades] == ["ORD-1", "ORD-2", "ORD-3"]


def test_the_closed_trade_query_skips_open_trades():
    with Session(engine) as session:
        session.add(_closed("CLOSED-1", 10.0, opened=datetime(2026, 9, 1, 10, 0)))
        open_trade = _closed("OPEN-1", 10.0, opened=datetime(2026, 9, 2, 10, 0))
        open_trade.status = "OPEN"
        session.add(open_trade)
        session.commit()

        trades = _closed_trades(session)

    assert [t.ticket for t in trades] == ["CLOSED-1"]


# --- the streak runs -------------------------------------------------------


def test_streak_runs_split_the_sign_sequence():
    win_runs, loss_runs = _streak_runs([1, 1, 1, -1, -1, 0, 1])
    assert win_runs == [3, 1]
    assert loss_runs == [2]


def test_a_scratch_breaks_a_streak():
    """Two wins, a scratch, one win — the scratch ends the first run."""
    win_runs, _loss_runs = _streak_runs([1, 1, 0, 1])
    assert win_runs == [2, 1]


def test_a_scratch_ends_the_streak_the_api_reports(client):
    """The dashboard must not draw a streak across a scratch trade."""
    _store(
        [
            _closed("SCR-1", 100.0, opened=datetime(2026, 9, 1, 10, 0)),
            _closed("SCR-2", 100.0, opened=datetime(2026, 9, 2, 10, 0)),
            _closed("SCR-3", 0.0, opened=datetime(2026, 9, 3, 10, 0)),
            _closed("SCR-4", 100.0, opened=datetime(2026, 9, 4, 10, 0)),
        ]
    )
    body = client.get("/api/analytics/activity-and-streaks").json()
    assert body["max_win_streak"] == 2
    assert body["winning_trades"] == 3
    assert body["losing_trades"] == 0
    # The scratch is counted as a breakeven, never as a loss.
    assert body["closed_trades"] == 4


def test_streak_runs_of_an_empty_history():
    assert _streak_runs([]) == ([], [])


def test_the_api_reports_the_longest_win_and_loss_streak(client):
    _store(
        [
            _closed("ST-1", 100.0, opened=datetime(2026, 9, 1, 10, 0)),
            _closed("ST-2", 100.0, opened=datetime(2026, 9, 2, 10, 0)),
            _closed("ST-3", 100.0, opened=datetime(2026, 9, 3, 10, 0)),
            _closed("ST-4", -100.0, opened=datetime(2026, 9, 4, 10, 0)),
            _closed("ST-5", -100.0, opened=datetime(2026, 9, 5, 10, 0)),
        ]
    )
    body = client.get("/api/analytics/activity-and-streaks").json()
    assert body["max_win_streak"] == 3
    assert body["max_loss_streak"] == 2
    assert body["avg_win_streak"] == 3.0
    assert body["avg_loss_streak"] == 2.0
    assert body["winning_trades"] == 3
    assert body["losing_trades"] == 2


def test_the_streak_of_consecutive_days_needs_consecutive_days(client):
    """Two winning days a week apart are not a winning-week streak."""
    _store(
        [
            _closed("DAYSTREAK-1", 100.0, opened=datetime(2026, 9, 1, 10, 0)),
            _closed("DAYSTREAK-2", 100.0, opened=datetime(2026, 9, 2, 10, 0)),
            _closed("DAYSTREAK-3", 100.0, opened=datetime(2026, 9, 9, 10, 0)),
        ]
    )
    body = client.get("/api/analytics/activity-and-streaks").json()
    assert body["max_winning_days"] == 2
    assert body["max_losing_days"] == 0


# --- the R buckets ---------------------------------------------------------


def test_the_r_bucket_rounds_to_the_nearest_integer():
    assert _r_bucket(-1.06) == "-1R"
    assert _r_bucket(0.97) == "1R"
    assert _r_bucket(1.0) == "1R"
    assert _r_bucket(0.0) == "0R"


def test_the_r_bucket_clamps_the_extremes():
    assert _r_bucket(-2.0) == "-2R"
    assert _r_bucket(-2.4) == "-2R"
    assert _r_bucket(-9.0) == "-2R"
    assert _r_bucket(3.0) == "3R+"
    assert _r_bucket(12.5) == "3R+"


def test_the_r_distribution_counts_every_bucket(client):
    _store(
        [
            _closed("R-1", 100.0, opened=datetime(2026, 9, 1, 10, 0), r=1.0),
            _closed("R-2", 100.0, opened=datetime(2026, 9, 1, 11, 0), r=0.4),
            _closed("R-3", -100.0, opened=datetime(2026, 9, 1, 12, 0), r=-1.0),
            _closed("R-4", 100.0, opened=datetime(2026, 9, 1, 13, 0), r=4.5),
            _closed("R-5", 100.0, opened=datetime(2026, 9, 1, 14, 0), r=None),
        ]
    )
    buckets = {
        row["label"]: row["count"]
        for row in client.get("/api/analytics/r-distribution").json()["buckets"]
    }
    assert buckets == {
        "-2R": 0,
        "-1R": 1,
        "0R": 1,
        "1R": 1,
        "2R": 0,
        "3R+": 1,
    }


# --- the tag aggregation ---------------------------------------------------


def test_the_tag_performance_uses_the_same_breakeven_rule(client):
    with Session(engine) as session:
        tag = Tag(name="fvg", category="setup")
        session.add(tag)
        session.commit()
        tag_id = tag.id
        for i, net in enumerate([200.0, -100.0, 1.0]):
            trade = _closed(f"TAG-{i}", net, opened=datetime(2026, 9, 1, 10, 0))
            session.add(trade)
            session.commit()
            session.add(TradeTagLink(trade_id=trade.id, tag_id=tag_id))
        session.commit()

    row = client.get("/api/analytics/tag-performance").json()["tags"][0]
    assert row["name"] == "fvg"
    assert row["trade_count"] == 3
    assert row["net_pnl"] == 101.0
    # 1 win, 1 loss, 1 scratch -> 50% over the decided trades only.
    assert row["win_rate"] == 50.0
