"""Broker clock calibration (bot `/brokertime` + web previews).

The trader reads wall times off MT5 (broker server clock, an unknown zone).
Calibration stores the broker's UTC offset in minutes in AppSetting, derived
from two readings of the same instant (MT5 wall + IST wall). All trade
timestamps stay naive UTC in storage — this offset only translates at the
input/display edges.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session

from app.models import AppSetting

BROKER_OFFSET_KEY = "broker_offset_minutes"
IST_OFFSET = timedelta(hours=5, minutes=30)
MAX_OFFSET = timedelta(hours=18)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_offset_minutes(session: Session) -> Optional[int]:
    row = session.get(AppSetting, BROKER_OFFSET_KEY)
    if row is None:
        return None
    try:
        return int(row.value)
    except (TypeError, ValueError):
        return None


def set_offset_minutes(session: Session, minutes: int) -> None:
    row = session.get(AppSetting, BROKER_OFFSET_KEY)
    if row is None:
        row = AppSetting(key=BROKER_OFFSET_KEY, value=str(minutes))
    else:
        row.value = str(minutes)
        row.updated_at = _now()
    session.add(row)


def format_label(minutes: int) -> str:
    """+210 → 'UTC+3:30', -300 → 'UTC-5:00'."""
    sign = "+" if minutes >= 0 else "-"
    total = abs(minutes)
    return f"UTC{sign}{total // 60}:{total % 60:02d}"


def calibrate(mt5_wall: datetime, ist_wall: datetime) -> int:
    """Offset minutes from two same-instant readings (both naive wall clocks)."""
    offset = (mt5_wall - ist_wall) + IST_OFFSET
    if abs(offset) > MAX_OFFSET:
        raise ValueError(f"Implausible broker offset {offset} — check both times are the same instant")
    return int(round(offset.total_seconds() / 60))


def broker_to_naive_utc(wall: datetime, offset_minutes: int) -> datetime:
    return wall - timedelta(minutes=offset_minutes)


def naive_utc_to_broker(wall_utc_naive: datetime, offset_minutes: int) -> datetime:
    return wall_utc_naive + timedelta(minutes=offset_minutes)
