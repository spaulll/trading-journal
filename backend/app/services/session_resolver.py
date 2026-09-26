"""Automatic trading-session resolver (killzones, UTC).

Sessions:
  Asia      00:00 - 06:00 UTC
  London    07:00 - 13:00 UTC
  New York  13:00 - 22:00 UTC
  Outside   anything else (06:00-07:00, 22:00-24:00 gaps included)

All inputs normalize via app.services.timeutils.as_naive_utc (naive-UTC policy).
"""

from datetime import datetime
from typing import Optional, Union

from app.services.timeutils import as_naive_utc

ASIA = "Asia"
LONDON = "London"
NEW_YORK = "New York"
OUTSIDE = "Outside"

VALID_SESSIONS = (ASIA, LONDON, NEW_YORK, OUTSIDE)


def resolve_session(entry: Optional[Union[datetime, str]]) -> str:
    """Map an entry timestamp (UTC) to its killzone session."""
    dt: Optional[datetime] = None
    if isinstance(entry, datetime):
        dt = as_naive_utc(entry)
    elif isinstance(entry, str) and entry.strip():
        try:
            dt = as_naive_utc(datetime.fromisoformat(entry.strip().replace("Z", "+00:00")))
        except ValueError:
            return OUTSIDE
    if dt is None:
        return OUTSIDE
    h = dt.hour + dt.minute / 60
    if 0 <= h < 6:
        return ASIA
    if 7 <= h < 13:
        return LONDON
    if 13 <= h < 22:
        return NEW_YORK
    return OUTSIDE


def normalize_session(value: Optional[str], entry: Optional[datetime] = None) -> str:
    """Accept a manual session override, else auto-resolve from entry time."""
    if value:
        for valid in VALID_SESSIONS:
            if value.strip().lower() == valid.lower().replace(" ", "") or value.strip().lower() == valid.lower():
                return valid
    return resolve_session(entry)


def duration_minutes(entry: Optional[datetime], exit: Optional[datetime]) -> Optional[int]:
    """Whole minutes between entry and exit; None when either is missing."""
    if entry is None or exit is None:
        return None

    o, c = as_naive_utc(entry), as_naive_utc(exit)
    assert o is not None and c is not None
    secs = (c - o).total_seconds()
    if secs < 0:
        return None
    return int(secs // 60)
