"""Tests for the pure Telegram parsers.

The bot is the only live ingestion path, so a parser regression silently
loses a trade. Everything here is pure: no network, no database.

Covered:
  - ``parse_open``   — the `buy SYMBOL, SIZE, ENTRY, SL, [TP], [tags]` line
  - ``parse_past``   — the historical `past buy ...` backfill line
  - ``parse_close``  — the `close SYMBOL, EXIT, ...` line
  - ``parse_tsl``    — the stop-loss move line
  - ``extract_alias`` — the `@account` routing suffix
  - zone suffixes    — UTC / GMT / IST / MT5 offsets
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.services.telegram_bot import (
    BotParseError,
    _split_zone,
    _suffix_offset,
    extract_alias,
    parse_close,
    parse_open,
    parse_past,
    parse_tsl,
)
from app.services.timeutils import IST_OFFSET


# --- parse_open -------------------------------------------------------------


def test_parse_open_reads_a_full_line():
    parsed = parse_open("buy gold, 0.1, 4000, 3990, 4020, #fvg")
    assert parsed["direction"] == "buy"
    assert parsed["symbol"] == "GOLD"
    assert parsed["size"] == 0.1
    assert parsed["entry_price"] == 4000.0
    assert parsed["initial_sl"] == 3990.0
    assert parsed["tp"] == 4020.0
    assert parsed["tags"] == ["#fvg"]
    assert parsed["entry_time"] is None


def test_parse_open_accepts_a_sell_and_uppercases_the_symbol():
    parsed = parse_open("sell eurusd, 0.5, 1.1000, 1.1050, 1.0900")
    assert parsed["direction"] == "sell"
    assert parsed["symbol"] == "EURUSD"


def test_parse_open_treats_the_fourth_number_as_take_profit():
    parsed = parse_open("buy gold, 0.1, 4000, 3990, 4020")
    assert parsed["tp"] == 4020.0
    assert parsed["tags"] == []


def test_parse_open_without_a_take_profit_keeps_the_tags():
    """Without a TP the fourth field is a tag, not a price."""
    parsed = parse_open("buy gold, 0.1, 4000, 3990, #fvg !early")
    assert parsed["tp"] is None
    assert parsed["tags"] == ["#fvg", "!early"]


def test_parse_open_rejects_a_line_with_too_few_numbers():
    with pytest.raises(BotParseError):
        parse_open("buy gold, 0.1, 4000")


def test_parse_open_rejects_an_unknown_direction():
    with pytest.raises(BotParseError):
        parse_open("long gold, 0.1, 4000, 3990, 4020")


def test_parse_open_rejects_a_non_numeric_size():
    with pytest.raises(BotParseError):
        parse_open("buy gold, lots, 4000, 3990, 4020")


# --- the `time:` flag -------------------------------------------------------


def test_parse_open_reads_an_explicit_utc_entry_time():
    parsed = parse_open("buy gold, 0.1, 4000, 3990, 4020, time: 2026-09-28 16:01")
    assert parsed["entry_time"] == datetime(2026, 9, 28, 16, 1)


def test_parse_open_keeps_the_seconds_of_an_explicit_entry_time():
    """MT5 exports carry seconds — dropping them shifts the entry minute."""
    parsed = parse_open("buy gold, 0.1, 4000, 3990, 4020, time: 2026-09-28 16:01:33")
    assert parsed["entry_time"] == datetime(2026, 9, 28, 16, 1, 33)


def test_parse_open_converts_an_ist_entry_time_to_utc():
    parsed = parse_open("buy gold, 0.1, 4000, 3990, 4020, time: 2026-09-28 16:01 IST")
    assert parsed["entry_time"] == datetime(2026, 9, 28, 10, 31)


def test_parse_open_reads_a_bare_entry_time_as_utc():
    """`time: 10:30` with no zone is UTC, not local."""
    parsed = parse_open("buy gold, 0.1, 4000, 3990, 4020, time: 10:30")
    assert parsed["entry_time"] is not None
    assert (parsed["entry_time"].hour, parsed["entry_time"].minute) == (10, 30)


def test_parse_open_resolves_a_bare_entry_time_against_the_broker_clock():
    parsed = parse_open(
        "buy gold, 0.1, 4000, 3990, 4020, time: 10:30 MT5",
        broker_offset=timedelta(hours=3),
    )
    assert parsed["entry_time"] is not None
    assert (parsed["entry_time"].hour, parsed["entry_time"].minute) == (7, 30)


def test_parse_open_refuses_a_broker_zone_without_a_calibrated_clock():
    with pytest.raises(BotParseError):
        parse_open("buy gold, 0.1, 4000, 3990, 4020, time: 10:30 MT5")


def test_parse_open_rejects_an_unknown_time_zone():
    with pytest.raises(BotParseError):
        parse_open("buy gold, 0.1, 4000, 3990, 4020, time: 2026-09-28 16:01 CET")


def test_parse_open_rejects_an_impossible_entry_time():
    with pytest.raises(BotParseError):
        parse_open("buy gold, 0.1, 4000, 3990, 4020, time: 25:00")


def test_parse_open_keeps_the_time_flag_out_of_the_numbers():
    """The flag must not shift the size/entry/SL positions."""
    parsed = parse_open("buy gold, 0.1, 4000, 3990, 4020, time: 2026-09-28 16:01")
    assert (parsed["size"], parsed["entry_price"], parsed["initial_sl"]) == (0.1, 4000.0, 3990.0)


# --- parse_past ------------------------------------------------------------


def test_parse_past_reads_a_single_day_backfill():
    parsed = parse_past(
        "past buy gold, 0.1, 4000, 3990, 4020, exit: 4015, pnl: 150, date: 2026-09-20 14:30"
    )
    assert parsed["direction"] == "buy"
    assert parsed["symbol"] == "GOLD"
    assert parsed["entry_price"] == 4000.0
    assert parsed["initial_sl"] == 3990.0
    assert parsed["tp"] == 4020.0
    assert parsed["exit_price"] == 4015.0
    assert parsed["gross_pnl"] == 150.0
    assert parsed["fees"] == 0.0
    assert parsed["entry_time"] == datetime(2026, 9, 20, 14, 30)
    # `date:` alone keeps the old behaviour: open == close.
    assert parsed["exit_time"] == datetime(2026, 9, 20, 14, 30)


def test_parse_past_reads_a_separate_close_time():
    parsed = parse_past(
        "past sell gold, 0.1, 4000, 3990, exit: 3985, pnl: -150, "
        "date: 2026-09-20 14:30, exit_date: 2026-09-20 15:00, fee: 3.5"
    )
    assert parsed["direction"] == "sell"
    assert parsed["exit_price"] == 3985.0
    assert parsed["gross_pnl"] == -150.0
    assert parsed["fees"] == 3.5
    assert parsed["entry_time"] == datetime(2026, 9, 20, 14, 30)
    assert parsed["exit_time"] == datetime(2026, 9, 20, 15, 0)


def test_parse_past_converts_an_ist_open_time_to_utc():
    parsed = parse_past(
        "past buy gold, 0.1, 4000, 3990, exit: 4015, pnl: 150, date: 2026-09-20 14:30 IST"
    )
    assert parsed["entry_time"] == datetime(2026, 9, 20, 9, 0)
    assert parsed["exit_time"] == datetime(2026, 9, 20, 9, 0)


def test_parse_past_lets_the_close_inherit_the_open_zone():
    """A close time without a zone is read in the open's zone."""
    parsed = parse_past(
        "past buy gold, 0.1, 4000, 3990, exit: 4015, pnl: 150, "
        "date: 2026-09-20 14:30 IST, exit_date: 2026-09-20 15:00"
    )
    assert parsed["entry_time"] == datetime(2026, 9, 20, 9, 0)
    assert parsed["exit_time"] == datetime(2026, 9, 20, 9, 30)


def test_parse_past_reads_a_single_flag_range():
    parsed = parse_past(
        "past buy gold, 0.1, 4000, 3990, 4020, exit: 4015, pnl: 150, "
        "date: 2026-09-20 14:30 to 2026-09-20 15:00"
    )
    assert parsed["entry_time"] == datetime(2026, 9, 20, 14, 30)
    assert parsed["exit_time"] == datetime(2026, 9, 20, 15, 0)


def test_parse_past_keeps_the_seconds_of_a_history_stamp():
    parsed = parse_past(
        "past buy gold, 0.1, 4000, 3990, exit: 4015, pnl: 150, date: 2026-09-20 14:30:45"
    )
    assert parsed["entry_time"] == datetime(2026, 9, 20, 14, 30, 45)


def test_parse_past_requires_the_exit_price():
    with pytest.raises(BotParseError):
        parse_past("past buy gold, 0.1, 4000, 3990, date: 2026-09-20 14:30")


def test_parse_past_requires_the_pnl():
    with pytest.raises(BotParseError):
        parse_past("past buy gold, 0.1, 4000, 3990, exit: 4015, date: 2026-09-20 14:30")


def test_parse_past_requires_the_date():
    with pytest.raises(BotParseError):
        parse_past("past buy gold, 0.1, 4000, 3990, exit: 4015, pnl: 150")


def test_parse_past_rejects_a_close_before_the_open():
    with pytest.raises(BotParseError):
        parse_past(
            "past buy gold, 0.1, 4000, 3990, exit: 4015, pnl: 150, "
            "date: 2026-09-20 15:00, exit_date: 2026-09-20 14:00"
        )


def test_parse_past_rejects_an_unparsable_date():
    with pytest.raises(BotParseError):
        parse_past(
            "past buy gold, 0.1, 4000, 3990, exit: 4015, pnl: 150, date: last tuesday"
        )


# --- parse_close -----------------------------------------------------------


def test_parse_close_reads_the_exit_price():
    parsed = parse_close("close gold, 4015")
    assert parsed["symbol"] == "GOLD"
    assert parsed["exit_price"] == 4015.0
    assert parsed["gross_pnl"] is None
    assert parsed["fees"] is None
    assert parsed["mistake_tags"] == []
    assert parsed["review_notes"] is None


def test_parse_close_reads_the_gross_pnl_and_the_fees():
    parsed = parse_close("close gold, 4015, +150, fee: 3.5")
    assert parsed["exit_price"] == 4015.0
    assert parsed["gross_pnl"] == 150.0
    assert parsed["fees"] == 3.5


def test_parse_close_reads_a_negative_gross_pnl():
    parsed = parse_close("close gold, 4015, -150")
    assert parsed["gross_pnl"] == -150.0


def test_parse_close_splits_the_tags_from_the_notes():
    parsed = parse_close("close gold, 4015, +150, fee: 3.5, !early, waited for the retest")
    assert parsed["mistake_tags"] == ["!early"]
    assert parsed["review_notes"] == "waited for the retest"


def test_parse_close_requires_an_exit_price():
    with pytest.raises(BotParseError):
        parse_close("close gold")


def test_parse_close_rejects_an_unknown_verb():
    with pytest.raises(BotParseError):
        parse_close("exit gold, 4015")


# --- parse_tsl -------------------------------------------------------------


def test_parse_tsl_reads_the_new_stop():
    parsed = parse_tsl("tsl gold, 4005")
    assert parsed["symbol"] == "GOLD"
    assert parsed["current_sl"] == 4005.0


def test_parse_tsl_rejects_a_line_without_a_price():
    with pytest.raises(BotParseError):
        parse_tsl("tsl gold")


# --- account alias routing -------------------------------------------------


def test_extract_alias_pulls_the_alias_off_the_line():
    cleaned, alias = extract_alias("buy gold, 0.1, 4000, 3990, 4020 @ftmo100k")
    assert alias == "ftmo100k"
    assert cleaned == "buy gold, 0.1, 4000, 3990, 4020"


def test_extract_alias_lowercases_the_alias():
    _, alias = extract_alias("buy gold @FTMO100k")
    assert alias == "ftmo100k"


def test_extract_alias_lets_the_last_alias_win():
    _, alias = extract_alias("buy gold @acc1 @acc2")
    assert alias == "acc2"


def test_extract_alias_returns_none_without_an_alias():
    cleaned, alias = extract_alias("buy gold, 0.1, 4000, 3990, 4020")
    assert alias is None
    assert cleaned == "buy gold, 0.1, 4000, 3990, 4020"


def test_extract_alias_handles_an_empty_line():
    cleaned, alias = extract_alias("")
    assert alias is None
    assert cleaned == ""


# --- zone suffixes ---------------------------------------------------------


def test_split_zone_defaults_to_utc():
    assert _split_zone("2026-09-28 16:01", None) == ("2026-09-28 16:01", timedelta(0))


def test_split_zone_reads_the_ist_offset():
    assert _split_zone("2026-09-28 16:01 IST", None) == ("2026-09-28 16:01", IST_OFFSET)


def test_split_zone_reads_the_broker_offset():
    offset = timedelta(minutes=210)
    assert _split_zone("2026-09-28 16:01 MT5", offset) == ("2026-09-28 16:01", offset)


def test_split_zone_rejects_an_unknown_zone():
    with pytest.raises(BotParseError):
        _split_zone("2026-09-28 16:01 CET", None)


def test_split_zone_needs_a_calibrated_broker_clock():
    with pytest.raises(BotParseError):
        _split_zone("2026-09-28 16:01 MT5", None)


def test_suffix_offset_accepts_gmt_as_utc():
    assert _suffix_offset("gmt", None) == timedelta(0)
    assert _suffix_offset("UTC", None) == timedelta(0)
