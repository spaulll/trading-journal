"""The trading day boundary — one rule for every day bucket in the app.

A trading day runs from ``boundary_hour`` in ``timezone`` to the same hour
the next day. A close at 23:30 UTC is 05:00 the next morning in
Asia/Kolkata, so with a midnight boundary it belongs to the *next* trading
day — not to the UTC day it happens to be stored in.

Every day bucket in the app (the guardrails, the daily stats, the calendar,
the streaks, the EOD prompt) reads the boundary from here, so one setting
moves all of them together. The timestamps stay naive UTC in storage; the
boundary only decides which day a moment belongs to.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlmodel import Session

from app.models import AppSetting

TRADING_DAY_KEY = "trading_day"
DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_BOUNDARY_HOUR = 0


class TradingDayError(ValueError):
    """The boundary asked for cannot be used."""


@dataclass(frozen=True)
class TradingDay:
    """Where the trading day rolls over."""

    boundary_hour: int = DEFAULT_BOUNDARY_HOUR
    timezone: str = DEFAULT_TIMEZONE

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def day_of(self, moment: datetime) -> date_type:
        """The trading day a naive-UTC moment belongs to.

        A moment before the boundary hour belongs to the trading day that
        started the day before.
        """
        local = moment.replace(tzinfo=timezone.utc).astimezone(self.zone)
        day = local.date()
        if local.hour < self.boundary_hour:
            day = day - timedelta(days=1)
        return day

    def bounds(self, day: date_type) -> tuple[datetime, datetime]:
        """The naive-UTC bounds of one trading day: [start, end).

        The end is the *next* local boundary, not start + 24h: on a DST
        transition the trading day is 23 or 25 hours long.
        """
        return self._start_utc(day), self._start_utc(day + timedelta(days=1))

    def _start_utc(self, day: date_type) -> datetime:
        """The naive-UTC instant the trading day starts."""
        local_start = datetime(
            day.year, day.month, day.day, self.boundary_hour, 0, tzinfo=self.zone
        )
        return local_start.astimezone(timezone.utc).replace(tzinfo=None)

    def label(self) -> str:
        """How the boundary reads to the trader."""
        return f"{self.boundary_hour:02d}:00 {self.timezone}"


def _valid_hour(value: object) -> int:
    try:
        hour = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise TradingDayError("boundary_hour must be a whole number of hours")
    if not 0 <= hour <= 23:
        raise TradingDayError("boundary_hour must be between 0 and 23")
    return hour


def _valid_zone(value: object) -> str:
    name = str(value or "").strip()
    if not name:
        raise TradingDayError("timezone must be an IANA zone, e.g. Asia/Kolkata")
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise TradingDayError(f"unknown timezone: {name}")
    return name


def get_trading_day(session: Session) -> TradingDay:
    """The stored boundary, or the default one."""
    row = session.get(AppSetting, TRADING_DAY_KEY)
    if row is None:
        return TradingDay()
    try:
        payload = json.loads(row.value or "{}")
    except json.JSONDecodeError:
        return TradingDay()
    if not isinstance(payload, dict):
        return TradingDay()
    try:
        hour = _valid_hour(payload.get("boundary_hour", DEFAULT_BOUNDARY_HOUR))
        zone = _valid_zone(payload.get("timezone", DEFAULT_TIMEZONE))
    except TradingDayError:
        return TradingDay()
    return TradingDay(boundary_hour=hour, timezone=zone)


def set_trading_day(
    session: Session, boundary_hour: object, zone_name: object
) -> TradingDay:
    """Store the boundary. The caller commits."""
    hour = _valid_hour(boundary_hour)
    zone = _valid_zone(zone_name)
    setting = TradingDay(boundary_hour=hour, timezone=zone)
    row = session.get(AppSetting, TRADING_DAY_KEY)
    if row is None:
        row = AppSetting(key=TRADING_DAY_KEY, value="")
    row.value = json.dumps({"boundary_hour": hour, "timezone": zone})
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    return setting


def trading_day_of(session: Session, moment: datetime) -> date_type:
    """The trading day a naive-UTC moment belongs to."""
    return get_trading_day(session).day_of(moment)


def trading_day_bounds(session: Session, day: date_type) -> tuple[datetime, datetime]:
    """The naive-UTC bounds of one trading day."""
    return get_trading_day(session).bounds(day)


def current_trading_day(session: Session, now: Optional[datetime] = None) -> date_type:
    """The trading day that is running right now."""
    moment = now or datetime.now(timezone.utc).replace(tzinfo=None)
    return get_trading_day(session).day_of(moment)
