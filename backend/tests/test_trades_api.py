"""Tests for the trades API: the backfill writer, the bulk account move
and the filter surface.

History is imported through the backfill endpoint and the ledger reads
through the filters. Both used to drift: a backfilled trade lost its
session, a duplicate ticket was counted twice, and a bulk move reported
a count that did not match the rows it touched.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session

from app.database import engine
from app.models import Trade


def _account(client, alias: str = "ftmo100k") -> dict:
    response = client.post("/api/accounts", json={"alias": alias, "firm": "FTMO"})
    assert response.status_code == 201, response.text
    return response.json()


def _record(**overrides) -> dict:
    payload = {
        "symbol": "gold",
        "direction": "buy",
        "size": 0.1,
        "entry_price": 4000.0,
        "exit_price": 4015.0,
        "initial_sl": 3990.0,
        "entry_time": "2026-09-20T10:00:00",
        "exit_time": "2026-09-20T10:45:00",
        "gross_pnl": 150.0,
    }
    payload.update(overrides)
    return payload


def _open(client, symbol: str = "GOLD", **overrides) -> dict:
    payload = {
        "symbol": symbol,
        "direction": "buy",
        "size": 0.1,
        "entry_price": 4000.0,
        "initial_sl": 3990.0,
    }
    payload.update(overrides)
    response = client.post("/api/trades/open", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# --- the backfill writer ---------------------------------------------------


def test_a_backfilled_trade_is_stored_closed(client):
    response = client.post("/api/trades/backfill", json=_record())
    assert response.status_code == 200, response.text
    body = response.json()

    assert len(body["inserted"]) == 1
    assert body["skipped"] == []
    assert body["total"] == 1

    trade = client.get(f"/api/trades/{_id_of(client, body['inserted'][0])}").json()
    assert trade["status"] == "CLOSED"
    assert trade["symbol"] == "GOLD"
    assert trade["ticket"] == body["inserted"][0]


def _id_of(client, ticket: str) -> int:
    rows = client.get("/api/trades").json()["items"]
    for row in rows:
        if row["ticket"] == ticket:
            return row["id"]
    raise AssertionError(f"no trade with ticket {ticket}")


def test_a_backfilled_trade_resolves_its_session_and_duration(client):
    """The 10:00 UTC entry is the London killzone; the hold was 45 minutes."""
    ticket = client.post("/api/trades/backfill", json=_record()).json()["inserted"][0]
    trade = client.get(f"/api/trades/{_id_of(client, ticket)}").json()

    assert trade["session"] == "London"
    assert trade["duration_minutes"] == 45
    assert trade["entry_time"] is not None
    assert trade["exit_time"] is not None


def test_a_backfilled_trade_computes_the_net_from_the_gross_and_fees(client):
    ticket = client.post(
        "/api/trades/backfill", json=_record(gross_pnl=150.0, fees=3.5)
    ).json()["inserted"][0]
    trade = client.get(f"/api/trades/{_id_of(client, ticket)}").json()

    assert trade["gross_pnl"] == 150.0
    assert trade["fees"] == 3.5
    assert trade["net_pnl"] == 146.5


def test_a_backfilled_trade_computes_the_r_multiple(client):
    ticket = client.post("/api/trades/backfill", json=_record()).json()["inserted"][0]
    trade = client.get(f"/api/trades/{_id_of(client, ticket)}").json()

    # +15 price points on a 10-point stop = 1.5R.
    assert trade["r_multiple"] == 1.5


def test_a_backfilled_trade_keeps_an_explicit_r_multiple(client):
    ticket = client.post(
        "/api/trades/backfill", json=_record(r_multiple=-0.5)
    ).json()["inserted"][0]
    trade = client.get(f"/api/trades/{_id_of(client, ticket)}").json()
    assert trade["r_multiple"] == -0.5


def test_a_backfilled_trade_carries_its_tags(client):
    ticket = client.post(
        "/api/trades/backfill", json=_record(tags=["#fvg", "!early"])
    ).json()["inserted"][0]
    trade = client.get(f"/api/trades/{_id_of(client, ticket)}").json()

    names = {t["name"]: t["category"] for t in trade["tags"]}
    assert names == {"fvg": "setup", "early": "mistake"}


def test_a_backfill_batch_inserts_every_record(client):
    body = client.post(
        "/api/trades/backfill",
        json={"records": [_record(ticket="BF-1"), _record(ticket="BF-2")]},
    ).json()

    assert sorted(body["inserted"]) == ["BF-1", "BF-2"]
    assert body["skipped"] == []
    assert body["total"] == 2


def test_a_duplicate_backfill_ticket_is_skipped_not_duplicated(client):
    client.post("/api/trades/backfill", json=_record(ticket="DUP-1"))
    body = client.post("/api/trades/backfill", json=_record(ticket="DUP-1")).json()

    assert body["inserted"] == []
    assert body["skipped"] == ["DUP-1"]
    assert body["total"] == 1


def test_a_backfill_generates_a_ticket_when_none_is_given(client):
    ticket = client.post("/api/trades/backfill", json=_record()).json()["inserted"][0]
    assert ticket.startswith("GOLD-")
    assert ticket == "GOLD-20260920T1000"


def test_a_backfill_refuses_a_bad_direction(client):
    response = client.post("/api/trades/backfill", json=_record(direction="sideways"))
    assert response.status_code == 422


def test_a_backfill_refuses_a_non_positive_size(client):
    response = client.post("/api/trades/backfill", json=_record(size=0))
    assert response.status_code == 422


def test_a_backfill_refuses_a_close_before_the_open(client):
    response = client.post(
        "/api/trades/backfill",
        json=_record(entry_time="2026-09-20T12:00:00", exit_time="2026-09-20T10:00:00"),
    )
    assert response.status_code == 422


def test_a_backfill_refuses_an_empty_batch(client):
    response = client.post("/api/trades/backfill", json={"records": []})
    assert response.status_code == 422


def test_a_backfill_refuses_a_batch_over_the_limit(client):
    records = [_record(ticket=f"BIG-{i}") for i in range(501)]
    response = client.post("/api/trades/backfill", json={"records": records})
    assert response.status_code == 422


def test_a_backfill_rejects_an_unknown_account(client):
    response = client.post("/api/trades/backfill", json=_record(account_id=4242))
    assert response.status_code == 404


def test_a_backfilled_trade_does_not_trip_the_guardrail(client):
    """History carries its own date — it must not breach today's cap."""
    client.post(
        "/api/trades/backfill",
        json=_record(
            gross_pnl=-5000.0,
            entry_time="2020-01-02T10:00:00",
            exit_time="2020-01-02T10:45:00",
        ),
    )
    assert client.get("/api/daily-notes").json() == []


def test_a_backfilled_trade_lands_in_the_ledger(client):
    client.post("/api/trades/backfill", json=_record(ticket="HIST-1"))
    rows = client.get("/api/trades").json()["items"]
    assert [row["ticket"] for row in rows] == ["HIST-1"]


# --- the bulk account move -------------------------------------------------


def test_a_bulk_move_assigns_the_trades(client):
    account = _account(client)
    first = _open(client)
    second = _open(client, symbol="EURUSD")

    response = client.post(
        "/api/trades/bulk-account",
        json={"trade_ids": [first["id"], second["id"]], "account_id": account["id"]},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"updated": 2, "skipped": [], "requested": 2}

    for trade_id in (first["id"], second["id"]):
        assert client.get(f"/api/trades/{trade_id}").json()["account_id"] == account["id"]


def test_a_bulk_move_can_send_the_trades_back_to_unassigned(client):
    account = _account(client)
    trade = _open(client)
    client.post(
        "/api/trades/bulk-account",
        json={"trade_ids": [trade["id"]], "account_id": account["id"]},
    )

    response = client.post(
        "/api/trades/bulk-account", json={"trade_ids": [trade["id"]], "account_id": None}
    )
    assert response.status_code == 200
    assert response.json() == {"updated": 1, "skipped": [], "requested": 1}
    assert client.get(f"/api/trades/{trade['id']}").json()["account_id"] is None


def test_a_bulk_move_skips_a_trade_that_does_not_exist(client):
    """A missing row is skipped — the count says what actually moved."""
    account = _account(client)
    trade = _open(client)

    response = client.post(
        "/api/trades/bulk-account",
        json={"trade_ids": [trade["id"], 999999], "account_id": account["id"]},
    )
    assert response.status_code == 200
    assert response.json() == {"updated": 1, "skipped": [999999], "requested": 2}


def test_a_bulk_move_needs_a_list_of_ids(client):
    account = _account(client)
    response = client.post("/api/trades/bulk-account", json={"account_id": account["id"]})
    assert response.status_code == 422


def test_a_bulk_move_refuses_an_empty_list(client):
    account = _account(client)
    response = client.post(
        "/api/trades/bulk-account", json={"trade_ids": [], "account_id": account["id"]}
    )
    assert response.status_code == 422


def test_a_bulk_move_refuses_a_batch_over_the_limit(client):
    account = _account(client)
    response = client.post(
        "/api/trades/bulk-account",
        json={"trade_ids": list(range(501)), "account_id": account["id"]},
    )
    assert response.status_code == 422


def test_a_bulk_move_rejects_an_unknown_account(client):
    trade = _open(client)
    response = client.post(
        "/api/trades/bulk-account", json={"trade_ids": [trade["id"]], "account_id": 4242}
    )
    assert response.status_code == 404


def test_a_bulk_move_ignores_an_id_that_is_not_a_number(client):
    account = _account(client)
    trade = _open(client)
    response = client.post(
        "/api/trades/bulk-account",
        json={"trade_ids": ["not-an-id", trade["id"]], "account_id": account["id"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["updated"] == 1
    assert body["skipped"] == ["not-an-id"]
    assert body["requested"] == 2


# --- the filter surface ----------------------------------------------------


def test_the_status_filter(client):
    open_trade = _open(client)
    client.post("/api/trades/backfill", json=_record(ticket="CLOSED-1"))

    rows = client.get("/api/trades", params={"status": "OPEN"}).json()
    assert [row["ticket"] for row in rows["items"]] == [open_trade["ticket"]]
    assert rows["total"] == 1


def test_the_symbol_filter_ignores_the_case(client):
    _open(client, symbol="EURUSD")
    _open(client, symbol="GOLD")

    rows = client.get("/api/trades", params={"symbol": "eurusd"}).json()
    assert [row["symbol"] for row in rows["items"]] == ["EURUSD"]


def test_the_tag_filter_accepts_a_prefixed_name(client):
    client.post("/api/trades/backfill", json=_record(ticket="TAGGED-1", tags=["#fvg"]))
    client.post("/api/trades/backfill", json=_record(ticket="PLAIN-1"))

    rows = client.get("/api/trades", params={"tag": "#fvg"}).json()
    assert [row["ticket"] for row in rows["items"]] == ["TAGGED-1"]
    assert rows["total"] == 1


def test_the_date_filter_bounds_the_open_timestamp(client):
    client.post(
        "/api/trades/backfill",
        json=_record(ticket="OLD-1", entry_time="2026-01-05T10:00:00", exit_time="2026-01-05T10:30:00"),
    )
    client.post(
        "/api/trades/backfill",
        json=_record(ticket="NEW-1", entry_time="2026-06-05T10:00:00", exit_time="2026-06-05T10:30:00"),
    )

    rows = client.get(
        "/api/trades",
        params={"date_from": "2026-03-01T00:00:00", "date_to": "2026-12-01T00:00:00"},
    ).json()
    assert [row["ticket"] for row in rows["items"]] == ["NEW-1"]


def test_the_account_filter(client):
    account = _account(client)
    assigned = _open(client)
    _open(client, symbol="EURUSD")
    client.post(
        "/api/trades/bulk-account",
        json={"trade_ids": [assigned["id"]], "account_id": account["id"]},
    )

    rows = client.get("/api/trades", params={"account_id": account["id"]}).json()
    assert [row["ticket"] for row in rows["items"]] == [assigned["ticket"]]
    assert rows["total"] == 1


def test_the_unassigned_filter(client):
    account = _account(client)
    assigned = _open(client)
    _open(client, symbol="EURUSD")
    client.post(
        "/api/trades/bulk-account",
        json={"trade_ids": [assigned["id"]], "account_id": account["id"]},
    )

    rows = client.get("/api/trades", params={"unassigned": True}).json()
    assert len(rows["items"]) == 1
    assert rows["items"][0]["account_id"] is None
    assert rows["total"] == 1


def test_the_pagination_slices_the_filtered_rows(client):
    for i in range(5):
        client.post("/api/trades/backfill", json=_record(ticket=f"PAGE-{i}"))

    body = client.get("/api/trades", params={"page": 2, "page_size": 2}).json()
    assert len(body["items"]) == 2
    assert body["page"] == 2
    assert body["page_size"] == 2
    # The total is the filtered count, not the page size.
    assert body["total"] == 5


def test_the_trade_count_matches_the_rows(client):
    _open(client)
    _open(client, symbol="EURUSD")
    body = client.get("/api/trades").json()
    assert body["total"] == len(body["items"]) == 2


def test_a_trade_keeps_its_ticket_and_id_after_a_bulk_move(client):
    account = _account(client)
    trade = _open(client)
    client.post(
        "/api/trades/bulk-account",
        json={"trade_ids": [trade["id"]], "account_id": account["id"]},
    )

    with Session(engine) as session:
        stored = session.get(Trade, trade["id"])
        assert stored is not None
        assert stored.ticket == trade["ticket"]
        assert stored.account_id == account["id"]
        assert stored.updated_at is not None
        assert isinstance(stored.updated_at, datetime)
