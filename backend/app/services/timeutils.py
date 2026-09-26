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

from datetime import datetime, timezone
from typing import Optional


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
