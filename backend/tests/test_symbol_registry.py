"""Tests for the symbol registry and the money math that depends on it.

A price distance is not money. Ten points on EURUSD and ten points on
NAS100 are wildly different dollars, and the contract size is what tells
them apart. These tests lock down that arithmetic, the risk it produces
and the R it scores.

The cases here are the defects this phase exists to prevent:
  - a symbol with no contract, priced as a guess instead of left unpriced
  - a backfilled trade with no P&L, stored with no P&L
  - a trailed stop, scored against the stop the plan never used
  - an unpriced trade, silently counted as a scratch
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlmodel import Session

from app.database import engine
from app.models import Trade
from app.services.analytics_rules import split_outcomes
from app.services.symbol_registry import (
    DEFAULT_SPECS,
    compute_r_multiple,
    direction_sign,
    effective_stop,
    estimate_gross_pnl,
    find_spec,
    list_specs,
    normalize_symbol,
    price_gross,
    risk_amount,
    seed_specs,
)


# --- the registry ----------------------------------------------------------


def test_the_registry_is_seeded_with_the_default_specs():
    with Session(engine) as session:
        specs = list_specs(session)
    assert len(specs) == len(DEFAULT_SPECS)
    symbols = {s.symbol for s in specs}
    for expected in ("EURUSD", "AUDUSD", "GOLD", "XAGUSD", "BTCUSD", "NAS100", "DE40"):
        assert expected in symbols


def test_a_seeded_symbol_keeps_its_contract_size():
    with Session(engine) as session:
        assert find_spec(session, "EURUSD").contract_size == 100000.0
        assert find_spec(session, "GOLD").contract_size == 100.0
        assert find_spec(session, "XAGUSD").contract_size == 5000.0
        assert find_spec(session, "BTCUSD").contract_size == 1.0
        assert find_spec(session, "NAS100").contract_size == 1.0


def test_an_unregistered_symbol_has_no_spec():
    with Session(engine) as session:
        assert find_spec(session, "NOT_A_SYMBOL") is None
        assert find_spec(session, "") is None
        assert find_spec(session, None) is None


def test_the_symbol_lookup_ignores_case_and_a_trailing_dot():
    with Session(engine) as session:
        assert find_spec(session, "eurusd").symbol == "EURUSD"
        assert find_spec(session, "EURUSD.").symbol == "EURUSD"
        assert find_spec(session, "  eurusd  ").symbol == "EURUSD"


def test_normalize_symbol_canonicalises_the_key():
    assert normalize_symbol(" eurusd. ") == "EURUSD"
    assert normalize_symbol(None) == ""


def test_a_disabled_spec_is_not_found():
    """A disabled symbol keeps its history but prices nothing new."""
    with Session(engine) as session:
        spec = find_spec(session, "EURUSD")
        spec.enabled = False
        session.add(spec)
        session.commit()
        assert find_spec(session, "EURUSD") is None
        assert estimate_gross_pnl(session, "buy", "EURUSD", 0.1, 1.1, 1.2) is None


def test_seeding_never_overwrites_a_user_edited_contract_size():
    with Session(engine) as session:
        spec = find_spec(session, "EURUSD")
        spec.contract_size = 12345.0
        session.add(spec)
        session.commit()

        assert seed_specs(session) == 0

        session.expire_all()
        assert find_spec(session, "EURUSD").contract_size == 12345.0


def test_seeding_adds_a_symbol_that_is_missing():
    with Session(engine) as session:
        added = seed_specs(
            session,
            ({"symbol": "TEST1", "display": "Test", "contract_size": 10.0,
              "pip_size": 0.1, "quote_currency": "USD", "category": "index"},),
        )
        session.commit()
        assert added == 1
        assert find_spec(session, "TEST1").contract_size == 10.0


# --- contract sizing -------------------------------------------------------


@pytest.mark.parametrize(
    "symbol,size,entry,exit_price,expected",
    [
        # FX: 100k units per lot, so 10 pips on 0.1 lot is $10.
        ("EURUSD", 0.1, 1.1000, 1.1010, 10.0),
        ("AUDUSD", 0.1, 0.6500, 0.6520, 20.0),
        ("NZDUSD", 1.0, 0.6000, 0.6010, 100.0),
        ("USDCHF", 0.5, 0.9000, 0.8990, -50.0),
        ("USDCAD", 0.1, 1.3500, 1.3510, 10.0),
        # Metals: 100 oz for gold-family, 5000 oz for silver.
        ("GOLD", 0.1, 4000.0, 4010.0, 100.0),
        ("XAGUSD", 0.1, 30.0, 31.0, 500.0),
        ("PAXG", 1.0, 4000.0, 4010.0, 1000.0),
        # Crypto: one coin per lot.
        ("BTCUSD", 1.0, 98000.0, 98100.0, 100.0),
        ("ETHUSD", 2.0, 3000.0, 3010.0, 20.0),
        ("SOLUSD", 10.0, 150.0, 155.0, 50.0),
        # Index CFDs: one contract per lot.
        ("NAS100", 1.0, 19800.0, 19850.0, 50.0),
        ("US30", 0.5, 42000.0, 41900.0, -50.0),
        ("SPX500", 1.0, 5800.0, 5810.0, 10.0),
        ("DE40", 2.0, 20000.0, 20010.0, 20.0),
    ],
)
def test_every_registered_symbol_prices_from_its_contract_size(
    client, symbol, size, entry, exit_price, expected
):
    """The whole verification list, priced from the registry."""
    response = client.get(
        "/api/symbols/preview",
        params={
            "symbol": symbol,
            "direction": "buy",
            "size": size,
            "entry": entry,
            "exit": exit_price,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["registered"] is True
    assert body["gross_pnl"] == expected


def test_a_short_prices_the_other_way():
    with Session(engine) as session:
        spec = find_spec(session, "EURUSD")
        # Selling at 1.1000 and covering at 1.0900 is a gain; buying is a loss.
        assert price_gross(spec, "sell", 0.1, 1.1000, 1.0900) == 100.0
        assert price_gross(spec, "buy", 0.1, 1.1000, 1.0900) == -100.0


def test_a_jpy_pair_is_converted_into_dollars():
    """USDJPY quotes in yen, so the P&L is converted at the exit rate."""
    with Session(engine) as session:
        spec = find_spec(session, "USDJPY")
        assert spec.quote_currency == "JPY"
        # 1.0 yen x 100k x 0.1 lot = 10,000 yen, at 151 yen per dollar.
        assert price_gross(spec, "buy", 0.1, 150.0, 151.0) == round(10000.0 / 151.0, 2)


def test_an_unregistered_symbol_is_never_guessed():
    with Session(engine) as session:
        assert estimate_gross_pnl(session, "buy", "NOT_A_SYMBOL", 0.1, 1.0, 2.0) is None
        assert price_gross(None, "buy", 0.1, 1.0, 2.0) is None


def test_a_missing_leg_is_never_guessed():
    with Session(engine) as session:
        spec = find_spec(session, "EURUSD")
        assert price_gross(spec, "buy", 0.1, 1.1, None) is None
        assert price_gross(spec, "buy", None, 1.1, 1.2) is None
        assert price_gross(spec, "buy", 0, 1.1, 1.2) is None
        assert price_gross(spec, "buy", -1, 1.1, 1.2) is None


def test_the_direction_predicate_agrees_across_the_math():
    assert direction_sign("buy") == 1
    assert direction_sign("long") == 1
    assert direction_sign("sell") == -1
    assert direction_sign("short") == -1
    assert direction_sign("sideways") == 0
    assert direction_sign(None) == 0


# --- the risk --------------------------------------------------------------


def test_the_risk_is_the_stop_distance_in_dollars():
    with Session(engine) as session:
        spec = find_spec(session, "EURUSD")
        # 100 pips x 100k x 0.1 lot = $100
        assert risk_amount(spec, 0.1, 1.1000, 1.0900) == 100.0
        assert risk_amount(spec, 0.1, 1.1000, 1.0900) == risk_amount(
            spec, 0.1, 1.0900, 1.1000
        )


def test_the_risk_of_an_unknown_symbol_is_unknown():
    assert risk_amount(None, 0.1, 1.1, 1.0) is None


def test_a_zero_stop_distance_has_no_risk():
    with Session(engine) as session:
        spec = find_spec(session, "EURUSD")
        assert risk_amount(spec, 0.1, 1.1, 1.1) is None


def test_the_trade_records_its_planned_and_carried_risk(client):
    trade = client.post(
        "/api/trades/open",
        json={
            "symbol": "EURUSD",
            "direction": "buy",
            "size": 0.1,
            "entry_price": 1.1000,
            "initial_sl": 1.0900,
        },
    ).json()
    assert trade["initial_risk"] == 100.0
    assert trade["realized_risk"] == 100.0
    assert trade["risk_unit"] == "USD"


def test_a_trailed_stop_shrinks_the_carried_risk(client):
    trade = client.post(
        "/api/trades/open",
        json={
            "symbol": "EURUSD",
            "direction": "buy",
            "size": 0.1,
            "entry_price": 1.1000,
            "initial_sl": 1.0900,
        },
    ).json()
    moved = client.post(
        f"/api/trades/{trade['id']}/tsl", json={"current_sl": 1.0950}
    ).json()
    assert moved["initial_risk"] == 100.0
    assert moved["realized_risk"] == 50.0


def test_an_unpriced_symbol_records_no_risk(client):
    trade = client.post(
        "/api/trades/open",
        json={
            "symbol": "NOT_A_SYMBOL",
            "direction": "buy",
            "size": 0.1,
            "entry_price": 1.0,
            "initial_sl": 0.9,
        },
    ).json()
    assert trade["initial_risk"] is None
    assert trade["realized_risk"] is None
    assert trade["risk_unit"] is None


def test_a_backfilled_trade_records_its_risk(client):
    body = client.post(
        "/api/trades/backfill",
        json={
            "symbol": "NAS100",
            "direction": "buy",
            "size": 0.5,
            "entry_price": 19800.0,
            "exit_price": 19850.0,
            "initial_sl": 19750.0,
            "entry_time": "2026-09-20T10:00:00",
            "exit_time": "2026-09-20T10:45:00",
        },
    ).json()
    trade = client.get("/api/trades").json()["items"][0]
    assert trade["initial_risk"] == 25.0
    assert trade["realized_risk"] == 25.0
    assert trade["risk_unit"] == "USD"
    assert body["inserted"]


# --- the R -----------------------------------------------------------------


def test_the_r_uses_the_planned_stop_when_nothing_moved():
    assert compute_r_multiple("buy", 4000.0, 3990.0, 3990.0, 4020.0) == 2.0
    assert compute_r_multiple("sell", 4000.0, 4010.0, 4010.0, 3980.0) == 2.0


def test_a_trailed_stop_produces_a_different_r():
    """The R follows the risk the trade actually carried."""
    planned = compute_r_multiple("buy", 4000.0, 3990.0, 3990.0, 4020.0)
    trailed = compute_r_multiple("buy", 4000.0, 3990.0, 3995.0, 4020.0)
    assert planned == 2.0
    assert trailed == 4.0


def test_a_widened_stop_also_changes_the_r():
    assert compute_r_multiple("buy", 4000.0, 3990.0, 3985.0, 4020.0) == 20 / 15


def test_a_breakeven_stop_falls_back_to_the_planned_stop():
    """A stop at the entry carries no risk — the planned R stands."""
    assert compute_r_multiple("buy", 4000.0, 3990.0, 4000.0, 4020.0) == 2.0


def test_the_effective_stop_picks_the_carried_stop():
    assert effective_stop("buy", 4000.0, 3990.0, 3995.0) == 3995.0
    assert effective_stop("buy", 4000.0, 3990.0, None) == 3990.0
    assert effective_stop("buy", 4000.0, 3990.0, 4000.0) == 3990.0
    assert effective_stop("sell", 4000.0, 4010.0, 4005.0) == 4005.0
    assert effective_stop("sell", 4000.0, 4010.0, 4000.0) == 4010.0


def test_an_r_needs_a_stop_and_an_exit():
    assert compute_r_multiple("buy", 4000.0, None, None, 4020.0) is None
    assert compute_r_multiple("buy", 4000.0, 3990.0, 3990.0, None) is None
    assert compute_r_multiple("sideways", 4000.0, 3990.0, 3990.0, 4020.0) is None


def test_the_closed_trade_scores_the_r_it_carried(client):
    trade = client.post(
        "/api/trades/open",
        json={
            "symbol": "GOLD",
            "direction": "buy",
            "size": 0.1,
            "entry_price": 4000.0,
            "initial_sl": 3990.0,
        },
    ).json()
    client.post(f"/api/trades/{trade['id']}/tsl", json={"current_sl": 3995.0})
    closed = client.patch(
        f"/api/trades/{trade['id']}", json={"exit_price": 4020.0}
    ).json()
    assert closed["r_multiple"] == 4.0
    assert closed["initial_risk"] == 100.0
    assert closed["realized_risk"] == 50.0


# --- the symbols API -------------------------------------------------------


def test_the_registry_endpoint_lists_the_specs(client):
    response = client.get("/api/symbols")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(DEFAULT_SPECS)
    eur = next(s for s in body if s["symbol"] == "EURUSD")
    assert eur["contract_size"] == 100000.0
    assert eur["quote_currency"] == "USD"
    assert eur["category"] == "fx"


def test_a_symbol_can_be_registered_and_edited(client):
    created = client.post(
        "/api/symbols",
        json={
            "symbol": "newthing",
            "display": "New Thing",
            "contract_size": 250.0,
            "pip_size": 0.25,
            "quote_currency": "usd",
            "category": "index",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["symbol"] == "NEWTHING"
    assert body["quote_currency"] == "USD"

    patched = client.patch(f"/api/symbols/{body['id']}", json={"contract_size": 500.0})
    assert patched.status_code == 200
    assert patched.json()["contract_size"] == 500.0


def test_a_duplicate_symbol_is_rejected(client):
    response = client.post("/api/symbols", json={"symbol": "EURUSD"})
    assert response.status_code == 409


def test_an_unknown_category_is_rejected(client):
    response = client.post("/api/symbols", json={"symbol": "FOO", "category": "bogus"})
    assert response.status_code == 422


def test_a_non_positive_contract_size_is_rejected(client):
    response = client.post("/api/symbols", json={"symbol": "FOO", "contract_size": 0})
    assert response.status_code == 422


def test_editing_a_missing_spec_is_a_404(client):
    response = client.patch("/api/symbols/999999", json={"contract_size": 1.0})
    assert response.status_code == 404


def test_the_preview_endpoint_prices_a_position(client):
    response = client.get(
        "/api/symbols/preview",
        params={
            "symbol": "EURUSD",
            "direction": "buy",
            "size": 0.1,
            "entry": 1.1000,
            "exit": 1.1200,
            "sl": 1.0900,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["registered"] is True
    assert body["gross_pnl"] == 200.0
    assert body["r_multiple"] == 2.0
    assert body["initial_risk"] == 100.0
    assert body["realized_risk"] == 100.0
    assert body["risk_unit"] == "USD"
    assert body["pips"] == 200.0
    assert body["risk_pips"] == 100.0


def test_the_preview_endpoint_reports_an_unregistered_symbol(client):
    response = client.get(
        "/api/symbols/preview",
        params={"symbol": "NOT_A_SYMBOL", "size": 0.1, "entry": 1.0, "exit": 2.0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["registered"] is False
    assert body["gross_pnl"] is None
    assert body["r_multiple"] is None
    assert body["initial_risk"] is None


# --- the close and backfill paths -----------------------------------------


def test_a_closed_trade_is_priced_from_the_registry(client):
    trade = client.post(
        "/api/trades/open",
        json={
            "symbol": "AUDUSD",
            "direction": "buy",
            "size": 0.1,
            "entry_price": 0.6500,
            "initial_sl": 0.6480,
        },
    ).json()
    closed = client.patch(
        f"/api/trades/{trade['id']}", json={"exit_price": 0.6520}
    ).json()
    assert closed["gross_pnl"] == 20.0
    assert closed["net_pnl"] == 20.0


def test_a_backfill_with_no_pnl_is_priced(client):
    client.post(
        "/api/trades/backfill",
        json={
            "symbol": "SOLUSD",
            "direction": "buy",
            "size": 10.0,
            "entry_price": 150.0,
            "exit_price": 155.0,
            "initial_sl": 145.0,
            "entry_time": "2026-09-20T10:00:00",
            "exit_time": "2026-09-20T10:45:00",
        },
    )
    trade = client.get("/api/trades").json()["items"][0]
    assert trade["gross_pnl"] == 50.0
    assert trade["net_pnl"] == 50.0


def test_a_backfill_of_an_unregistered_symbol_stays_unpriced(client):
    client.post(
        "/api/trades/backfill",
        json={
            "symbol": "NOT_A_SYMBOL",
            "direction": "buy",
            "size": 1.0,
            "entry_price": 1.0,
            "exit_price": 2.0,
            "entry_time": "2026-09-20T10:00:00",
            "exit_time": "2026-09-20T10:45:00",
        },
    )
    trade = client.get("/api/trades").json()["items"][0]
    assert trade["gross_pnl"] is None
    assert trade["net_pnl"] is None


def test_an_explicit_gross_is_never_overwritten_by_the_estimator(client):
    trade = client.post(
        "/api/trades/open",
        json={
            "symbol": "EURUSD",
            "direction": "buy",
            "size": 0.1,
            "entry_price": 1.1000,
            "initial_sl": 1.0900,
        },
    ).json()
    closed = client.patch(
        f"/api/trades/{trade['id']}",
        json={"exit_price": 1.1200, "gross_pnl": 42.0},
    ).json()
    assert closed["gross_pnl"] == 42.0


# --- the unpriced rules ----------------------------------------------------


def test_an_unpriced_trade_is_not_a_breakeven():
    counts = split_outcomes([200.0, None, -100.0, 3.0])
    assert counts.wins == 1
    assert counts.losses == 1
    assert counts.breakeven == 1
    assert counts.unpriced == 1
    assert counts.decided == 2
    assert counts.priced == 3


def test_an_unpriced_trade_does_not_break_a_streak(client):
    """The bug: a trade that was never priced ended a run of wins."""
    with Session(engine) as session:
        for ticket, net in (("W1", 200.0), ("U1", None), ("W2", 100.0)):
            session.add(
                Trade(
                    ticket=ticket,
                    symbol="EURUSD",
                    direction="buy",
                    size=0.1,
                    entry_price=1.1,
                    initial_sl=1.09,
                    exit_price=1.12,
                    net_pnl=net,
                    status="CLOSED",
                    timestamp_open=datetime(2026, 9, 1, 10, 0),
                    timestamp_close=datetime(2026, 9, 1, 11, 0),
                )
            )
        session.commit()

    body = client.get("/api/analytics/activity-and-streaks").json()
    assert body["max_win_streak"] == 2
    assert body["winning_trades"] == 2
    assert body["unpriced_trades"] == 1


def test_an_unpriced_trade_is_reported_next_to_the_rate(client):
    with Session(engine) as session:
        session.add(
            Trade(
                ticket="U1",
                symbol="NOT_A_SYMBOL",
                direction="buy",
                size=0.1,
                entry_price=1.0,
                initial_sl=0.9,
                exit_price=1.2,
                net_pnl=None,
                status="CLOSED",
                timestamp_open=datetime(2026, 9, 1, 10, 0),
                timestamp_close=datetime(2026, 9, 1, 11, 0),
            )
        )
        session.commit()

    summary = client.get("/api/analytics/summary").json()
    assert summary["unpriced"] == 1
    assert summary["breakeven"] == 0
    assert summary["total_trades"] == 1


# --- the migration ---------------------------------------------------------


def test_the_startup_seeds_the_registry(tmp_path):
    """A fresh journal gets the default contracts on the first run.

    The test harness re-seeds the registry between tests, so this covers
    the application startup path on its own.
    """
    import sqlite3

    from sqlmodel import create_engine

    from app import database as database_module

    db_path = tmp_path / "fresh.db"
    url = f"sqlite:///{db_path}"
    original = database_module.engine
    original_url = database_module.DATABASE_URL
    fresh_engine = create_engine(url, connect_args={"check_same_thread": False})
    database_module.engine = fresh_engine
    database_module.DATABASE_URL = url
    try:
        # The whole startup path, so the wiring in create_db_and_tables is
        # covered too — not just the seeding function.
        database_module.create_db_and_tables()
    finally:
        database_module.engine = original
        database_module.DATABASE_URL = original_url
        fresh_engine.dispose()

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT symbol, contract_size FROM symbol_spec").fetchall()
    seeded = {symbol: size for symbol, size in rows}
    assert seeded["EURUSD"] == 100000.0
    assert seeded["GOLD"] == 100.0
    assert seeded["NAS100"] == 1.0
    assert len(seeded) == len(DEFAULT_SPECS)


def test_the_startup_seeding_is_idempotent(tmp_path):
    """A restart must not duplicate a contract."""
    import sqlite3

    from sqlmodel import create_engine

    from app import database as database_module

    db_path = tmp_path / "restart.db"
    url = f"sqlite:///{db_path}"
    original = database_module.engine
    original_url = database_module.DATABASE_URL
    fresh_engine = create_engine(url, connect_args={"check_same_thread": False})
    database_module.engine = fresh_engine
    database_module.DATABASE_URL = url
    try:
        database_module.create_db_and_tables()
        database_module.create_db_and_tables()
    finally:
        database_module.engine = original
        database_module.DATABASE_URL = original_url
        fresh_engine.dispose()

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT count(*) FROM symbol_spec").fetchone()[0]
    assert count == len(DEFAULT_SPECS)


def test_the_risk_columns_are_added_to_a_pre_existing_trade_table(tmp_path):
    """A journal created before Phase 3 gets the columns and the values."""
    import sqlite3

    db_path = tmp_path / "legacy.db"
    url = f"sqlite:///{db_path}"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE trade (
                id INTEGER NOT NULL PRIMARY KEY, ticket VARCHAR NOT NULL,
                timestamp_open DATETIME, timestamp_close DATETIME, entry_time DATETIME,
                exit_time DATETIME, duration_minutes INTEGER, session VARCHAR,
                direction VARCHAR, symbol VARCHAR, size FLOAT, entry_price FLOAT,
                initial_sl FLOAT, current_sl FLOAT, tp FLOAT, exit_price FLOAT,
                gross_pnl FLOAT, fees FLOAT NOT NULL, net_pnl FLOAT, r_multiple FLOAT,
                status VARCHAR NOT NULL, thesis VARCHAR, review_notes VARCHAR,
                account_id INTEGER, created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL)"""
        )
        conn.execute(
            """INSERT INTO trade (ticket, symbol, direction, size, entry_price,
               initial_sl, current_sl, fees, status, created_at, updated_at)
               VALUES ('OLD-1', 'EURUSD', 'buy', 0.1, 1.1000, 1.0900, 1.0950,
               0.0, 'CLOSED', '2026-01-01', '2026-01-01')"""
        )
        conn.commit()

    # The migration runs against the app engine, so point it at the legacy
    # file for the duration of this test.
    from app import database as database_module

    original = database_module.engine
    original_url = database_module.DATABASE_URL
    from sqlmodel import SQLModel, create_engine

    legacy_engine = create_engine(url, connect_args={"check_same_thread": False})
    database_module.engine = legacy_engine
    database_module.DATABASE_URL = url
    try:
        SQLModel.metadata.create_all(legacy_engine)
        # The real startup order: the registry is seeded before the risk
        # backfill runs, so the backfill can price the old rows.
        database_module._migrate_symbol_spec()
        database_module._migrate_trade_risk_columns()
    finally:
        database_module.engine = original
        database_module.DATABASE_URL = original_url
        legacy_engine.dispose()

    with sqlite3.connect(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(trade)")}
        assert {"initial_risk", "realized_risk", "risk_unit"} <= cols
        row = conn.execute(
            "SELECT initial_risk, realized_risk, risk_unit FROM trade"
        ).fetchone()
    # 100 pips x 100k x 0.1 = $100 planned; the trailed stop halves it.
    assert row[0] == 100.0
    assert row[1] == 50.0
    assert row[2] == "USD"
