"""Multi-currency ledger: quote P&L, daily rates and USD reporting.

Phase 4 exists so a JPY or INR account cannot silently corrupt a dollar
total. These tests pin the three rules that make that true:

  - a trade keeps its broker-booked amount in its quote currency and a
    converted amount in ``*_usd``, written together;
  - a daily rate may be direct, inverse or a cross, and a missing day
    falls back to the most recent earlier rate *and says so*;
  - every total (analytics, prop headroom) sums the USD view, while the
    quote-currency breakdown stays visible.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from sqlmodel import SQLModel, create_engine

# --- helpers ---------------------------------------------------------------


def _rate(client, day: str, base: str, quote: str, rate: float, **overrides) -> dict:
    payload = {"date": day, "base": base, "quote": quote, "rate": rate}
    payload.update(overrides)
    response = client.post("/api/fx-rates", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _account(client, **overrides) -> dict:
    payload = {"alias": "jpy-account", "firm": "FTMO", "base_currency": "JPY"}
    payload.update(overrides)
    response = client.post("/api/accounts", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _open(client, **overrides) -> dict:
    payload = {
        "symbol": "USDJPY",
        "direction": "buy",
        "size": 0.1,
        "entry_price": 150.0,
        "initial_sl": 149.5,
        "entry_time": "2024-03-10T09:00:00",
        "ticket": "JPY-OPEN-1",
    }
    payload.update(overrides)
    response = client.post("/api/trades/open", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _backfill(client, **overrides) -> dict:
    payload = {
        "symbol": "USDJPY",
        "direction": "buy",
        "size": 0.1,
        "entry_price": 150.0,
        "exit_price": 150.5,
        "entry_time": "2024-03-10T09:00:00",
        "exit_time": "2024-03-10T10:00:00",
        "gross_pnl": 5000.0,
    }
    payload.update(overrides)
    response = client.post("/api/trades/backfill", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _trade(client, ticket: str) -> dict:
    response = client.get("/api/trades")
    assert response.status_code == 200, response.text
    matches = [t for t in response.json()["items"] if t["ticket"] == ticket]
    assert len(matches) == 1, response.text
    return matches[0]


# --- the rate table --------------------------------------------------------


def test_a_rate_is_stored_and_read_back(client):
    stored = _rate(client, "2024-03-10", "usd", "jpy", 150.0)
    assert stored["base"] == "USD"
    assert stored["quote"] == "JPY"
    assert stored["rate"] == 150.0
    assert stored["source"] == "manual"

    listed = client.get("/api/fx-rates", params={"base": "USD", "quote": "JPY"}).json()
    assert [row["rate"] for row in listed] == [150.0]


def test_posting_the_same_day_edits_the_rate(client):
    _rate(client, "2024-03-10", "USD", "JPY", 150.0)
    _rate(client, "2024-03-10", "USD", "JPY", 151.0)

    listed = client.get("/api/fx-rates").json()
    assert len(listed) == 1
    assert listed[0]["rate"] == 151.0


def test_a_rate_must_be_positive_and_a_real_pair(client):
    bad_rate = client.post(
        "/api/fx-rates",
        json={"date": "2024-03-10", "base": "USD", "quote": "JPY", "rate": 0},
    )
    assert bad_rate.status_code == 422

    same = client.post(
        "/api/fx-rates",
        json={"date": "2024-03-10", "base": "USD", "quote": "USD", "rate": 1},
    )
    assert same.status_code == 422

    junk = client.post(
        "/api/fx-rates",
        json={"date": "2024-03-10", "base": "US!", "quote": "JPY", "rate": 150},
    )
    assert junk.status_code == 422


# --- lookup: direct, inverse, cross, fallback ------------------------------


def test_direct_inverse_and_cross_rates_resolve(client):
    _rate(client, "2024-03-10", "USD", "JPY", 150.0)
    _rate(client, "2024-03-10", "USD", "INR", 83.0)

    direct = client.get(
        "/api/fx-rates/effective",
        params={"base": "USD", "quote": "JPY", "date": "2024-03-10"},
    ).json()
    assert direct["rate"] == 150.0
    assert direct["source"] == "direct"
    assert direct["missing"] is False

    inverse = client.get(
        "/api/fx-rates/effective",
        params={"base": "JPY", "quote": "USD", "date": "2024-03-10"},
    ).json()
    assert inverse["source"] == "inverse"
    assert round(inverse["rate"], 6) == round(1 / 150.0, 6)

    cross = client.get(
        "/api/fx-rates/effective",
        params={"base": "JPY", "quote": "INR", "date": "2024-03-10"},
    ).json()
    assert cross["source"] == "cross"
    assert cross["via"] == "USD"
    assert round(cross["rate"], 6) == round(83.0 / 150.0, 6)

    identity = client.get(
        "/api/fx-rates/effective",
        params={"base": "JPY", "quote": "JPY", "date": "2024-03-10"},
    ).json()
    assert identity["rate"] == 1.0
    assert identity["source"] == "identity"


def test_a_missing_day_falls_back_and_reports_its_age(client):
    _rate(client, "2024-03-08", "USD", "JPY", 150.0)

    effective = client.get(
        "/api/fx-rates/effective",
        params={"base": "USD", "quote": "JPY", "date": "2024-03-11"},
    ).json()
    assert effective["rate"] == 150.0
    assert effective["as_of"] == "2024-03-08"
    assert effective["fallback"] is True
    assert effective["fallback_days"] == 3
    assert effective["missing"] is False


def test_a_currency_with_no_rate_at_all_is_reported_missing(client):
    _rate(client, "2024-03-10", "USD", "JPY", 150.0)

    effective = client.get(
        "/api/fx-rates/effective",
        params={"base": "GBP", "quote": "JPY", "date": "2024-03-10"},
    ).json()
    assert effective["missing"] is True
    assert effective["rate"] is None


# --- a JPY trade is dollars everywhere ------------------------------------


def test_a_usdjpy_trade_on_a_jpy_account_reports_usd_net_everywhere(client):
    account = _account(client, start_balance=1_000_000.0)
    _rate(client, "2024-03-10", "USD", "JPY", 150.0)
    opened = _open(client, account_id=account["id"], ticket="JPY-1")
    assert opened["quote_currency"] == "JPY"

    closed = client.post(
        f"/api/trades/{opened['id']}/close",
        json={"exit_price": 150.5, "gross_pnl": 5000.0, "fees": 0.0},
    )
    assert closed.status_code == 200, closed.text
    body = closed.json()
    # The broker booked 5,000 yen; the ledger also knows that is $33.33.
    assert body["gross_pnl"] == 5000.0
    assert body["net_pnl"] == 5000.0
    assert body["net_pnl_usd"] == 33.33
    assert body["gross_pnl_usd"] == 33.33
    assert body["fx_missing"] is False

    summary = client.get("/api/analytics/summary").json()
    assert summary["net_pnl"] == 33.33
    assert summary["by_currency"] == {"JPY": 5000.0}
    assert summary["unpriced"] == 0

    prop = client.get(f"/api/accounts/{account['id']}/prop-status").json()
    assert prop["base_currency"] == "JPY"
    assert prop["start_balance"] == 1_000_000.0
    assert prop["total_net"] == 5000.0
    assert prop["balance"] == 1_005_000.0
    assert prop["total_net_usd"] == 33.33

    in_usd = client.get(
        f"/api/accounts/{account['id']}/prop-status", params={"base": "USD"}
    ).json()
    assert in_usd["base_currency"] == "USD"
    assert in_usd["account_base_currency"] == "JPY"
    assert in_usd["total_net"] == 33.33


def test_a_day_with_two_currencies_sums_in_usd_and_keeps_the_breakdown(client):
    _rate(client, "2024-03-10", "USD", "JPY", 150.0)
    _backfill(
        client,
        symbol="GOLD",
        entry_price=2000.0,
        exit_price=2010.0,
        gross_pnl=100.0,
        ticket="MIX-USD",
    )
    _backfill(client, ticket="MIX-JPY")

    day = client.get("/api/analytics/calendar", params={"year": 2024}).json()["days"]
    assert len(day) == 1
    assert day[0]["date"] == "2024-03-10"
    assert day[0]["net_pnl"] == 133.33
    assert day[0]["trade_count"] == 2
    assert day[0]["unpriced"] == 0
    assert day[0]["by_currency"] == {"JPY": 5000.0, "USD": 100.0}


def test_a_usdjpy_trade_without_a_stored_rate_uses_its_exit_price(client):
    """USDJPY at 150.50 *is* the USD/JPY rate, so it can price itself.

    The exit price quotes yen per dollar; the conversion needs dollars per
    yen, so the stored rate must be the inverse. Using it upright would
    turn a 5,000-yen win into roughly $750,000.
    """
    _backfill(client, ticket="JPY-IMPLIED")

    trade = _trade(client, "JPY-IMPLIED")
    assert trade["quote_currency"] == "JPY"
    assert trade["net_pnl_usd"] == round(5000.0 / 150.5, 2)
    assert trade["fx_missing"] is False


def test_a_trade_whose_rate_is_missing_is_unpriced_not_zero(client):
    # A rupee-quoted cross whose own price does not imply the USD rate:
    # no FX row means no USD amount, never a zero.
    created = client.post(
        "/api/symbols",
        json={
            "symbol": "EURINR",
            "display": "EUR/INR",
            "contract_size": 100000.0,
            "pip_size": 0.01,
            "quote_currency": "INR",
            "category": "fx",
        },
    )
    assert created.status_code == 201, created.text
    _backfill(client, symbol="EURINR", ticket="INR-1", gross_pnl=8300.0)

    trade = _trade(client, "INR-1")
    assert trade["quote_currency"] == "INR"
    assert trade["net_pnl"] == 8300.0
    assert trade["net_pnl_usd"] is None
    assert trade["fx_missing"] is True

    summary = client.get("/api/analytics/summary").json()
    assert summary["unpriced"] == 1
    assert summary["net_pnl"] == 0.0
    # The quote-currency breakdown still shows the booked amount.
    assert summary["by_currency"] == {"INR": 8300.0}

    curve = client.get("/api/analytics/equity-curve").json()["points"]
    assert curve == []


def test_the_account_reports_a_fallback_rate_on_the_trade_conversion(client):
    account = _account(client, start_balance=1_000_000.0)
    _rate(client, "2024-03-08", "USD", "JPY", 150.0)
    _backfill(
        client,
        account_id=account["id"],
        ticket="JPY-FALLBACK",
        entry_time="2024-03-11T09:00:00",
        exit_time="2024-03-11T10:00:00",
    )

    # Reported in the account's yen base the trade needs no conversion, so
    # the fallback only appears when the same figure is asked for in USD.
    in_yen = client.get(f"/api/accounts/{account['id']}/prop-status").json()
    assert in_yen["total_net"] == 5000.0
    assert in_yen["fx"]["fallback"] == 0

    prop = client.get(
        f"/api/accounts/{account['id']}/prop-status", params={"base": "USD"}
    ).json()
    assert prop["total_net"] == 33.33
    assert prop["total_net_usd"] == 33.33
    assert prop["fx"]["missing"] == 0
    assert prop["fx"]["fallback"] == 1
    assert prop["fx"]["max_fallback_days"] == 3


# --- the account's declared currency --------------------------------------


def test_an_account_declares_its_base_currency(client):
    account = _account(client, alias="jpy-100k", base_currency="jpy")
    assert account["base_currency"] == "JPY"

    invalid = client.post(
        "/api/accounts",
        json={"alias": "junk-base", "base_currency": "yen!"},
    )
    assert invalid.status_code == 422

    patched = client.patch(
        f"/api/accounts/{account['id']}", json={"base_currency": "EUR"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["base_currency"] == "EUR"


def test_a_usd_account_sums_a_yen_trade_in_usd(client):
    account = _account(client, alias="usd-account", base_currency="USD", start_balance=10_000.0)
    _rate(client, "2024-03-10", "USD", "JPY", 150.0)
    _backfill(client, account_id=account["id"], ticket="USD-ACCT-JPY")

    prop = client.get(f"/api/accounts/{account['id']}/prop-status").json()
    assert prop["base_currency"] == "USD"
    assert prop["total_net"] == 33.33
    assert prop["balance"] == 10_033.33
    assert prop["total_net_usd"] == 33.33

    in_yen = client.get(
        f"/api/accounts/{account['id']}/prop-status", params={"base": "JPY"}
    ).json()
    assert in_yen["base_currency"] == "JPY"
    assert in_yen["total_net"] == 5000.0


# --- the schema migration --------------------------------------------------


def test_the_currency_columns_are_added_to_a_pre_existing_trade_table():
    """A Phase-3 row kept its dollar amount and is labelled USD."""
    tmp = Path(tempfile.mkdtemp(prefix="tj-fx-migrate-"))
    db_path = tmp / "legacy.db"
    url = f"sqlite:///{db_path}"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE trade (
                id INTEGER NOT NULL PRIMARY KEY, ticket VARCHAR NOT NULL,
                status VARCHAR NOT NULL, gross_pnl FLOAT, fees FLOAT NOT NULL,
                net_pnl FLOAT, created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL)"""
        )
        conn.execute(
            """INSERT INTO trade (ticket, status, gross_pnl, fees, net_pnl,
               created_at, updated_at)
               VALUES ('OLD-USD', 'CLOSED', 120.0, 20.0, 100.0,
               '2026-01-01', '2026-01-01')"""
        )
        conn.commit()

    from app import database as database_module

    original = database_module.engine
    original_url = database_module.DATABASE_URL
    legacy_engine = create_engine(url, connect_args={"check_same_thread": False})
    database_module.engine = legacy_engine
    database_module.DATABASE_URL = url
    try:
        SQLModel.metadata.create_all(legacy_engine)
        database_module._migrate_trade_currency_columns()
    finally:
        database_module.engine = original
        database_module.DATABASE_URL = original_url
        legacy_engine.dispose()

    with sqlite3.connect(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(trade)")}
        assert {"quote_currency", "gross_pnl_usd", "net_pnl_usd"} <= cols
        row = conn.execute(
            "SELECT quote_currency, gross_pnl_usd, net_pnl_usd FROM trade"
        ).fetchone()
    assert row == ("USD", 120.0, 100.0)
