"""Central datetime policy (Phase 6).

Policy: store and compare trade timestamps as **naive UTC** everywhere.

- SQLite has no timezone type — naive UTC keeps ISO lexicographic ordering
  correct and avoids naive-vs-aware comparison crashes in Python.
- Live callers may send aware ISO-8601 (`...Z` / `+00:00`); history (CSV) is
  naive. All write paths normalize via :func:`as_naive_utc` before storage.
- All read paths (guardrails, calendar, monthly-calendar, streaks, session
  buckets) bucket via :func:`as_naive_utc` / :func:`trade_close_day` so day
  boundaries are always UTC midnights.

Helpers here are the single source of truth — routers must import from this
module instead of defining local ``_as_naive`` copies.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import re


def as_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert aware → naive UTC; pass naive/None through unchanged."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def utcnow_naive() -> datetime:
    """Current UTC time as naive datetime (for storage)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def trade_close_day(trade) -> Optional[datetime]:
    """Naive-UTC close day for a trade (close → open fallback)."""
    return as_naive_utc(getattr(trade, "timestamp_close", None)) or as_naive_utc(
        getattr(trade, "timestamp_open", None)
    )


# --- User-facing time input (bot `time:` / `date:` flags) ---
#
# The trader types wall-clock times with an optional zone suffix:
# `time: 2026-09-28 16:01 IST` or `time: 16:01 UTC`. Bare times are UTC
# (back-compat). IST is a fixed +05:30 (no DST). Everything is converted
# to naive UTC before storage — display converts back to IST client-side.

IST_OFFSET = timedelta(hours=5, minutes=30)

_ZONE_OFFSETS = {
    "utc": timedelta(0),
    "gmt": timedelta(0),
    "ist": IST_OFFSET,
}


def split_zone_suffix(raw: str) -> tuple[str, timedelta]:
    """Split a trailing zone word off `raw`.

    Returns (remainder, utc_offset). Bare input → UTC offset. Raises
    ValueError on an unknown suffix (callers surface it as a parse error).
    """
    text = (raw or "").strip()
    m = re.search(r"\s+([A-Za-z]{1,8})\s*$", text)
    if not m:
        return text, timedelta(0)
    zone = m.group(1).lower()
    if zone not in _ZONE_OFFSETS:
        raise ValueError(f"Unknown timezone {m.group(1)!r} — use IST or UTC")
    return text[: m.start()].strip(), _ZONE_OFFSETS[zone]


def wall_to_naive_utc(wall: datetime, offset: timedelta) -> datetime:
    """Interpret naive `wall` clock in the stated zone → naive UTC."""
    return wall - offset
