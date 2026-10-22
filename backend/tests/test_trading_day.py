"""Tests for the trading day boundary.

A trading day runs from the boundary hour in the configured timezone to the
same hour the next day. A close at 23:30 UTC is 05:00 the next morning in
Asia/Kolkata, so with a midnight boundary it belongs to the *next* trading
day — the rule every day bucket in the app has to agree on.
"""

from __future__ import annotations

from datetime import date, datetime

from app.models import Trade
from app.services.scheduler import _trades_today, eod_summary_text
from app.services.telegram_bot import daily_stats_text
from app.services.trading_day import (
    TradingDay,
    TradingDayError,
    get_trading_day,
    set_trading_day,
)


def test_the_default_boundary_is_local_midnight():
    setting = TradingDay()
    assert setting.boundary_hour == 0
    assert setting.timezone == "Asia/Kolkata"


def test_a_close_at_half_past_eleven_utc_belongs_to_the_next_local_day():
    setting = TradingDay(boundary_hour=0, timezone="Asia/Kolkata")
    # 23:30 UTC is 05:00 the next morning in Kolkata.
    assert setting.day_of(datetime(2026, 10, 22, 23, 30)) == date(2026, 10, 23)
    # 18:30 UTC is 00:00 the next morning in Kolkata.
    assert setting.day_of(datetime(2026, 10, 22, 18, 30)) == date(2026, 10, 23)
    # 18:29 UTC is still the evening of the 22nd in Kolkata.
    assert setting.day_of(datetime(2026, 10, 22, 18, 29)) == date(2026, 10, 22)


def test_a_boundary_hour_moves_the_rollover():
    setting = TradingDay(boundary_hour=5, timezone="Asia/Kolkata")
    # 02:30 local is before the 05:00 boundary, so it belongs to the
    # trading day that started the day before.
    assert setting.day_of(datetime(2026, 10, 22, 21, 0)) == date(2026, 10, 22)
    # 23:20 UTC is 04:50 IST on the 23rd — still before the 05:00 boundary,
    # so it belongs to the trading day that started on the 22nd.
    assert setting.day_of(datetime(2026, 10, 22, 23, 20)) == date(2026, 10, 22)
    # 23:30 UTC is exactly 05:00 IST, the boundary: the 23rd has begun.
    assert setting.day_of(datetime(2026, 10, 22, 23, 30)) == date(2026, 10, 23)


def test_the_bounds_of_a_trading_day():
    setting = TradingDay(boundary_hour=0, timezone="Asia/Kolkata")
    start, end = setting.bounds(date(2026, 10, 22))
    # The day starts at 00:00 IST = 18:30 UTC the day before.
    assert start == datetime(2026, 10, 21, 18, 30)
    assert end == datetime(2026, 10, 22, 18, 30)


def test_a_dst_day_is_not_forced_to_twenty_four_hours():
    setting = TradingDay(boundary_hour=0, timezone="America/New_York")
    # 2026-03-08 is the spring-forward day: 23 hours long.
    start, end = setting.bounds(date(2026, 3, 8))
    assert start == datetime(2026, 3, 8, 5, 0)  # 00:00 EST
    assert end == datetime(2026, 3, 9, 4, 0)  # 00:00 EDT
    # 2026-11-01 is the fall-back day: 25 hours long.
    start, end = setting.bounds(date(2026, 11, 1))
    assert start == datetime(2026, 11, 1, 4, 0)  # 00:00 EDT
    assert end == datetime(2026, 11, 2, 5, 0)  # 00:00 EST


def test_the_boundary_is_stored_and_read_back(client):
    response = client.put(
        "/api/settings/trading-day", json={"boundary_hour": 5, "timezone": "Asia/Kolkata"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["boundary_hour"] == 5
    assert body["timezone"] == "Asia/Kolkata"

    read = client.get("/api/settings/trading-day").json()
    assert read["boundary_hour"] == 5
    assert read["timezone"] == "Asia/Kolkata"


def test_an_unknown_timezone_is_refused(client):
    response = client.put(
        "/api/settings/trading-day", json={"boundary_hour": 5, "timezone": "Mars/Olympus"}
    )
    assert response.status_code == 422
    assert "timezone" in response.json()["detail"]


def test_an_impossible_hour_is_refused(client):
    response = client.put("/api/settings/trading-day", json={"boundary_hour": 99})
    assert response.status_code == 422
    assert "boundary_hour" in response.json()["detail"]


def test_the_stored_boundary_survives_a_bad_value(session):
    from app.models import AppSetting

    session.add(
        AppSetting(key="trading_day", value="{not json")
    )
    session.commit()
    # A broken row falls back to the default rather than breaking the app.
    assert get_trading_day(session).boundary_hour == 0


def test_setting_the_boundary_rejects_a_bad_hour(session):
    try:
        set_trading_day(session, 30, "Asia/Kolkata")
    except TradingDayError as exc:
        assert "boundary_hour" in str(exc)
    else:
        raise AssertionError("an impossible hour must be refused")


# --- the boundary across the day buckets -----------------------------------
#
# Every bucket has to agree on which day a trade belongs to. A close at
# 23:20 UTC is 04:50 the next morning in Asia/Kolkata: with a midnight
# boundary it is tomorrow, with a 05:00 boundary it is still today.

LATE_CLOSE = datetime(2026, 9, 28, 23, 20)  # 04:50 IST on the 29th
EARLY_CLOSE = datetime(2026, 9, 28, 18, 29)  # 23:59 IST on the 28th


def _trade(ticket: str, net: float, *, opened: datetime, closed: datetime) -> Trade:
    return Trade(
        ticket=ticket,
        symbol="GOLD",
        direction="buy",
        size=0.1,
        entry_price=4000.0,
        initial_sl=3990.0,
        exit_price=4010.0,
        timestamp_open=opened,
        timestamp_close=closed,
        net_pnl=net,
        gross_pnl=net,
        r_multiple=1.0,
        status="CLOSED",
    )


def _store(session, trades: list[Trade]) -> None:
    for trade in trades:
        session.add(trade)
    session.commit()


def _two_days(session) -> None:
    _store(
        session,
        [
            _trade(
                "EARLY-1",
                100.0,
                opened=datetime(2026, 9, 28, 17, 0),
                closed=EARLY_CLOSE,
            ),
            _trade(
                "LATE-1",
                -40.0,
                opened=datetime(2026, 9, 28, 22, 0),
                closed=LATE_CLOSE,
            ),
        ],
    )


def test_the_default_boundary_puts_the_late_close_on_the_next_day(client, session):
    _two_days(session)

    days = client.get("/api/analytics/calendar", params={"year": 2026}).json()["days"]
    assert [(d["date"], d["net_pnl"], d["trade_count"]) for d in days] == [
        ("2026-09-28", 100.0, 1),
        ("2026-09-29", -40.0, 1),
    ]

    streaks = client.get("/api/analytics/activity-and-streaks").json()
    assert streaks["trading_days"] == 2
    assert streaks["max_winning_days"] == 1
    assert streaks["max_losing_days"] == 1

    september = client.get(
        "/api/analytics/monthly-calendar", params={"year": 2026, "month": 9}
    ).json()
    assert september["days"]["2026-09-28"]["trade_count"] == 1
    assert september["days"]["2026-09-29"]["trade_count"] == 1
    assert september["summary"]["trading_days"] == 2

    # The weekday profile follows the same trading day: the 23:20 UTC close
    # was Monday in UTC but is Tuesday in Kolkata.
    radar = client.get("/api/analytics/radar-profiles").json()
    by_weekday = {row["day"]: row for row in radar["weekday"]}
    assert by_weekday["Mon"]["trades"] == 1
    assert by_weekday["Tue"]["trades"] == 1


def test_moving_the_boundary_moves_the_day_buckets(client, session):
    response = client.put(
        "/api/settings/trading-day",
        json={"boundary_hour": 5, "timezone": "Asia/Kolkata"},
    )
    assert response.status_code == 200, response.text
    _two_days(session)

    # 23:20 UTC is 04:50 IST — before the 05:00 boundary, so both closes
    # belong to the 28th now.
    days = client.get("/api/analytics/calendar", params={"year": 2026}).json()["days"]
    assert [(d["date"], d["net_pnl"], d["trade_count"]) for d in days] == [
        ("2026-09-28", 60.0, 2)
    ]

    streaks = client.get("/api/analytics/activity-and-streaks").json()
    assert streaks["trading_days"] == 1

    september = client.get(
        "/api/analytics/monthly-calendar", params={"year": 2026, "month": 9}
    ).json()
    assert september["days"]["2026-09-28"]["trade_count"] == 2
    assert september["days"]["2026-09-29"]["trade_count"] == 0


def test_daily_stats_follow_the_boundary(client, session):
    _two_days(session)

    today = daily_stats_text(session, date(2026, 9, 28))
    assert "EARLY-1" in today and "LATE-1" not in today
    assert "(00:00 Asia/Kolkata)" in today

    tomorrow = daily_stats_text(session, date(2026, 9, 29))
    assert "LATE-1" in tomorrow and "EARLY-1" not in tomorrow

    client.put(
        "/api/settings/trading-day",
        json={"boundary_hour": 5, "timezone": "Asia/Kolkata"},
    )
    session.expire_all()
    today = daily_stats_text(session, date(2026, 9, 28))
    assert "EARLY-1" in today and "LATE-1" in today
    assert "(05:00 Asia/Kolkata)" in today
    assert "LATE-1" not in daily_stats_text(session, date(2026, 9, 29))


def test_the_eod_recap_follows_the_boundary(client, session):
    _two_days(session)

    recap = eod_summary_text(session, date(2026, 9, 29))
    assert "LATE-1" in recap and "EARLY-1" not in recap
    opened, closed = _trades_today(session, date(2026, 9, 29))
    assert [t.ticket for t in opened] == ["LATE-1"]
    assert [t.ticket for t in closed] == ["LATE-1"]

    client.put(
        "/api/settings/trading-day",
        json={"boundary_hour": 5, "timezone": "Asia/Kolkata"},
    )
    session.expire_all()
    recap = eod_summary_text(session, date(2026, 9, 28))
    assert "EARLY-1" in recap and "LATE-1" in recap


def test_the_guardrail_counts_the_trading_day(session, monkeypatch):
    import app.routers.trades as trades_router

    monkeypatch.setattr(trades_router, "_now", lambda: datetime(2026, 9, 29, 0, 30))
    _two_days(session)

    guard = trades_router._guardrail_status(session)
    assert guard["day"] == "2026-09-29"
    assert guard["trades"] == 1
    assert guard["daily_pnl"] == -40.0

    # With the 05:00 boundary the same instant is still the 28th, and this
    # trade no longer belongs to the guardrail's day.
    set_trading_day(session, 5, "Asia/Kolkata")
    session.commit()
    guard = trades_router._guardrail_status(session)
    assert guard["trades"] == 0
    assert guard["daily_pnl"] == 0.0


def test_day_adherence_reads_the_trading_day(client, session):
    _two_days(session)
    client.put("/api/daily-notes/2026-09-29", json={"pre_market": "Plan: GOLD long"})

    assert client.get("/api/daily-notes/2026-09-29/adherence").json()["trades"] == 1

    client.put(
        "/api/settings/trading-day",
        json={"boundary_hour": 5, "timezone": "Asia/Kolkata"},
    )
    assert client.get("/api/daily-notes/2026-09-28/adherence").json()["trades"] == 2
    assert client.get("/api/daily-notes/2026-09-29/adherence").json()["trades"] == 0


def test_the_settings_response_names_the_current_trading_day(client, monkeypatch):
    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 29, 23, 0, tzinfo=tz)

    monkeypatch.setattr("app.services.trading_day.datetime", _FixedDatetime)

    # 23:00 UTC is 04:30 IST on the 30th: midnight has passed there, the
    # 05:00 boundary has not.
    assert client.get("/api/settings/trading-day").json()["today"] == "2026-09-30"
    moved = client.put(
        "/api/settings/trading-day",
        json={"boundary_hour": 5, "timezone": "Asia/Kolkata"},
    )
    assert moved.json()["today"] == "2026-09-29"
