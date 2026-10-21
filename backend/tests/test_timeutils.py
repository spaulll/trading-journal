"""Tests for the datetime policy and the session resolver.

The whole ledger buckets on **naive UTC**. A timestamp that arrives aware
and a timestamp that arrives naive must land in the same day bucket, and a
close at 23:30 UTC must belong to that UTC day — not to the local one.

Covered:
  - ``as_naive_utc`` / ``utcnow_naive`` — the naive-UTC policy
  - ``trade_close_day`` — the close-day bucket
  - ``split_zone_suffix`` / ``wall_to_naive_utc`` — wall-clock input
  - ``resolve_session`` / ``normalize_session`` / ``duration_minutes``
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.session_resolver import (
    ASIA,
    LONDON,
    NEW_YORK,
    OUTSIDE,
    duration_minutes,
    normalize_session,
    resolve_session,
)
from app.services.timeutils import (
    IST_OFFSET,
    as_naive_utc,
    split_zone_suffix,
    trade_close_day,
    utcnow_naive,
    wall_to_naive_utc,
)


class _Trade:
    """Minimal stand-in for the Trade row the helpers read."""

    def __init__(self, timestamp_open=None, timestamp_close=None):
        self.timestamp_open = timestamp_open
        self.timestamp_close = timestamp_close


# --- the naive-UTC policy --------------------------------------------------


def test_as_naive_utc_converts_an_aware_timestamp():
    aware = datetime(2026, 9, 28, 16, 1, tzinfo=timezone.utc)
    assert as_naive_utc(aware) == datetime(2026, 9, 28, 16, 1)


def test_as_naive_utc_converts_a_non_utc_offset_to_utc():
    aware = datetime(2026, 9, 28, 21, 31, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert as_naive_utc(aware) == datetime(2026, 9, 28, 16, 1)


def test_as_naive_utc_leaves_a_naive_timestamp_alone():
    naive = datetime(2026, 9, 28, 16, 1)
    assert as_naive_utc(naive) is naive


def test_as_naive_utc_passes_none_through():
    assert as_naive_utc(None) is None


def test_utcnow_naive_is_naive():
    now = utcnow_naive()
    assert now.tzinfo is None


# --- the close-day bucket --------------------------------------------------


def test_trade_close_day_uses_the_close_timestamp():
    trade = _Trade(
        timestamp_open=datetime(2026, 9, 27, 10, 0),
        timestamp_close=datetime(2026, 9, 28, 23, 30),
    )
    assert trade_close_day(trade) == datetime(2026, 9, 28, 23, 30)


def test_trade_close_day_falls_back_to_the_open_timestamp():
    trade = _Trade(timestamp_open=datetime(2026, 9, 27, 10, 0))
    assert trade_close_day(trade) == datetime(2026, 9, 27, 10, 0)


def test_trade_close_day_normalizes_an_aware_close():
    trade = _Trade(
        timestamp_open=datetime(2026, 9, 27, 10, 0),
        timestamp_close=datetime(2026, 9, 28, 21, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))),
    )
    assert trade_close_day(trade) == datetime(2026, 9, 28, 16, 0)


def test_trade_close_day_is_none_without_any_timestamp():
    assert trade_close_day(_Trade()) is None


def test_a_late_close_stays_in_its_own_utc_day():
    """23:30 UTC belongs to that day — the bucket never slides to the next."""
    trade = _Trade(timestamp_close=datetime(2026, 9, 28, 23, 30))
    assert trade_close_day(trade).date() == datetime(2026, 9, 28).date()


# --- wall-clock input ------------------------------------------------------


def test_split_zone_suffix_reads_the_ist_offset():
    assert split_zone_suffix("16:01 IST") == ("16:01", IST_OFFSET)


def test_split_zone_suffix_defaults_to_utc():
    assert split_zone_suffix("16:01") == ("16:01", timedelta(0))


def test_split_zone_suffix_reads_utc_and_gmt():
    assert split_zone_suffix("16:01 UTC") == ("16:01", timedelta(0))
    assert split_zone_suffix("16:01 gmt") == ("16:01", timedelta(0))


def test_split_zone_suffix_rejects_an_unknown_zone():
    with pytest.raises(ValueError):
        split_zone_suffix("16:01 CET")


def test_wall_to_naive_utc_shifts_a_wall_clock_back():
    wall = datetime(2026, 9, 28, 16, 1)
    assert wall_to_naive_utc(wall, IST_OFFSET) == datetime(2026, 9, 28, 10, 31)


def test_wall_to_naive_utc_is_a_no_op_for_utc():
    wall = datetime(2026, 9, 28, 16, 1)
    assert wall_to_naive_utc(wall, timedelta(0)) == wall


# --- the session resolver --------------------------------------------------


@pytest.mark.parametrize(
    "hour,minute,expected",
    [
        (0, 0, ASIA),
        (5, 59, ASIA),
        (6, 0, OUTSIDE),  # the 06:00-07:00 gap
        (6, 59, OUTSIDE),
        (7, 0, LONDON),
        (12, 59, LONDON),
        (13, 0, NEW_YORK),
        (21, 59, NEW_YORK),
        (22, 0, OUTSIDE),
        (23, 59, OUTSIDE),
    ],
)
def test_resolve_session_maps_an_entry_time_to_its_killzone(hour, minute, expected):
    entry = datetime(2026, 9, 28, hour, minute)
    assert resolve_session(entry) == expected


def test_resolve_session_normalizes_an_aware_entry():
    entry = datetime(2026, 9, 28, 8, 0, tzinfo=timezone.utc)
    assert resolve_session(entry) == LONDON


def test_resolve_session_reads_an_iso_string():
    assert resolve_session("2026-09-28T08:00:00") == LONDON
    assert resolve_session("2026-09-28T08:00:00Z") == LONDON


def test_resolve_session_falls_back_to_outside_for_junk():
    assert resolve_session("not a timestamp") == OUTSIDE
    assert resolve_session("") == OUTSIDE
    assert resolve_session(None) == OUTSIDE


def test_normalize_session_accepts_a_manual_override():
    assert normalize_session("london", datetime(2026, 9, 28, 8, 0)) == LONDON
    assert normalize_session("New York", datetime(2026, 9, 28, 8, 0)) == NEW_YORK
    assert normalize_session("newyork", datetime(2026, 9, 28, 8, 0)) == NEW_YORK


def test_normalize_session_resolves_the_session_when_no_override_is_given():
    assert normalize_session(None, datetime(2026, 9, 28, 8, 0)) == LONDON
    assert normalize_session("", datetime(2026, 9, 28, 2, 0)) == ASIA


def test_normalize_session_ignores_an_unknown_override():
    assert normalize_session("tokyo", datetime(2026, 9, 28, 8, 0)) == LONDON


def test_duration_minutes_counts_whole_minutes():
    entry = datetime(2026, 9, 28, 10, 0)
    exit_at = datetime(2026, 9, 28, 10, 45, 30)
    assert duration_minutes(entry, exit_at) == 45


def test_duration_minutes_is_none_when_a_leg_is_missing():
    assert duration_minutes(None, datetime(2026, 9, 28, 10, 0)) is None
    assert duration_minutes(datetime(2026, 9, 28, 10, 0), None) is None


def test_duration_minutes_is_none_for_an_inverted_pair():
    entry = datetime(2026, 9, 28, 10, 0)
    exit_at = datetime(2026, 9, 28, 9, 0)
    assert duration_minutes(entry, exit_at) is None


def test_duration_minutes_mixes_aware_and_naive_legs():
    entry = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
    exit_at = datetime(2026, 9, 28, 10, 30)
    assert duration_minutes(entry, exit_at) == 30
