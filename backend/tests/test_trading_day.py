"""Tests for the trading day boundary.

A trading day runs from the boundary hour in the configured timezone to the
same hour the next day. A close at 23:30 UTC is 05:00 the next morning in
Asia/Kolkata, so with a midnight boundary it belongs to the *next* trading
day — the rule every day bucket in the app has to agree on.
"""

from __future__ import annotations

from datetime import date, datetime

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
