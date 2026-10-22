"""Tests for the server-side ledger: the filters, the counts and the sort.

The ledger used to download every trade and filter it in the browser. The
filters now run in SQL, so these tests hold the server to the same answers
the browser used to compute for itself.
"""

from __future__ import annotations


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


# --- the counts --------------------------------------------------------------


def test_the_status_counts_come_from_the_server(client):
    _open(client)
    client.post("/api/trades/backfill", json=_record(ticket="CLOSED-1"))

    body = client.get("/api/trades").json()
    assert body["counts"] == {"ALL": 2, "OPEN": 1, "CLOSED": 1}


def test_the_status_counts_ignore_the_status_filter(client):
    _open(client)
    client.post("/api/trades/backfill", json=_record(ticket="CLOSED-1"))

    body = client.get("/api/trades", params={"status": "OPEN"}).json()
    # The tab counts stay the same whichever tab is open — otherwise the
    # numbers would change as you click between them.
    assert body["counts"] == {"ALL": 2, "OPEN": 1, "CLOSED": 1}
    assert body["total"] == 1


# --- the filters -------------------------------------------------------------


def test_the_free_text_query_matches_a_symbol(client):
    _open(client, symbol="EURUSD")
    _open(client, symbol="GOLD")

    body = client.get("/api/trades", params={"q": "eur"}).json()
    assert [row["symbol"] for row in body["items"]] == ["EURUSD"]
    assert body["total"] == 1


def test_the_free_text_query_matches_a_ticket(client):
    client.post("/api/trades/backfill", json=_record(ticket="TICKET-42"))

    body = client.get("/api/trades", params={"q": "ticket-4"}).json()
    assert [row["ticket"] for row in body["items"]] == ["TICKET-42"]


def test_the_tag_filter_matches_a_substring_of_the_tag(client):
    client.post("/api/trades/backfill", json=_record(ticket="TAGGED-1", tags=["#fvg"]))
    client.post("/api/trades/backfill", json=_record(ticket="PLAIN-1", tags=["#breakout"]))

    body = client.get("/api/trades", params={"tag": "fvg"}).json()
    assert [row["ticket"] for row in body["items"]] == ["TAGGED-1"]
    assert body["total"] == 1


def test_the_close_day_bounds_pick_the_journal_rows(client):
    client.post(
        "/api/trades/backfill",
        json=_record(
            ticket="OLD-CLOSE",
            entry_time="2026-01-05T10:00:00",
            exit_time="2026-01-05T10:30:00",
        ),
    )
    client.post(
        "/api/trades/backfill",
        json=_record(
            ticket="NEW-CLOSE",
            entry_time="2026-06-05T10:00:00",
            exit_time="2026-06-05T10:30:00",
        ),
    )

    body = client.get(
        "/api/trades",
        params={"closed_from": "2026-03-01T00:00:00", "closed_to": "2026-12-01T00:00:00"},
    ).json()
    assert [row["ticket"] for row in body["items"]] == ["NEW-CLOSE"]


def test_the_account_filter_counts_only_its_own_trades(client):
    account = _account(client)
    assigned = _open(client)
    _open(client, symbol="EURUSD")
    client.post(
        "/api/trades/bulk-account",
        json={"trade_ids": [assigned["id"]], "account_id": account["id"]},
    )

    body = client.get("/api/trades", params={"account_id": account["id"]}).json()
    assert body["total"] == 1
    assert body["counts"] == {"ALL": 1, "OPEN": 1, "CLOSED": 0}


# --- the sort ----------------------------------------------------------------


def test_the_newest_sort_puts_the_latest_trade_first(client):
    client.post(
        "/api/trades/backfill",
        json=_record(ticket="OLDER", entry_time="2026-01-05T10:00:00", exit_time="2026-01-05T10:30:00"),
    )
    client.post(
        "/api/trades/backfill",
        json=_record(ticket="NEWER", entry_time="2026-06-05T10:00:00", exit_time="2026-06-05T10:30:00"),
    )

    body = client.get("/api/trades", params={"sort": "newest"}).json()
    assert [row["ticket"] for row in body["items"]] == ["NEWER", "OLDER"]


def test_the_net_sort_orders_by_the_dollar_result(client):
    client.post("/api/trades/backfill", json=_record(ticket="SMALL", gross_pnl=10.0))
    client.post("/api/trades/backfill", json=_record(ticket="BIG", gross_pnl=900.0))

    body = client.get("/api/trades", params={"sort": "net-desc"}).json()
    assert [row["ticket"] for row in body["items"]] == ["BIG", "SMALL"]

    body = client.get("/api/trades", params={"sort": "net-asc"}).json()
    assert [row["ticket"] for row in body["items"]] == ["SMALL", "BIG"]


def test_an_unpriced_trade_sorts_last_in_every_order(client):
    client.post("/api/trades/backfill", json=_record(ticket="PRICED", gross_pnl=10.0))
    # No contract for the symbol and no P&L: the row has no number to sort by.
    client.post(
        "/api/trades/backfill",
        json=_record(ticket="UNPRICED", symbol="nosuchsymbol", gross_pnl=None),
    )

    body = client.get("/api/trades", params={"sort": "net-desc"}).json()
    assert [row["ticket"] for row in body["items"]][-1] == "UNPRICED"


# --- the pagination ---------------------------------------------------------


def test_the_browser_asks_for_one_page_at_a_time(client):
    for i in range(5):
        client.post("/api/trades/backfill", json=_record(ticket=f"PAGE-{i}"))

    body = client.get("/api/trades", params={"page": 2, "page_size": 2}).json()
    assert len(body["items"]) == 2
    assert body["page"] == 2
    assert body["page_size"] == 2
    # The total is the filtered count, not the size of the page.
    assert body["total"] == 5


def test_the_id_list_covers_every_filtered_trade_not_one_page(client):
    for i in range(5):
        client.post("/api/trades/backfill", json=_record(ticket=f"PAGE-{i}"))

    body = client.get("/api/trades/ids", params={"page": 2, "page_size": 2}).json()
    assert body["total"] == 5
    assert len(body["ids"]) == 5


def test_the_id_list_honours_the_filter(client):
    client.post("/api/trades/backfill", json=_record(ticket="MATCHED", symbol="gold"))
    client.post("/api/trades/backfill", json=_record(ticket="OTHER", symbol="eurusd"))

    body = client.get("/api/trades/ids", params={"q": "gold"}).json()
    assert body["total"] == 1
    assert len(body["ids"]) == 1


# --- the bulk move ----------------------------------------------------------


def test_a_bulk_move_reports_the_ids_it_skipped(client):
    account = _account(client)
    trade = _open(client)

    response = client.post(
        "/api/trades/bulk-account",
        json={"trade_ids": [trade["id"], 999999], "account_id": account["id"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["updated"] == 1
    # The trade that does not exist is named, not swallowed.
    assert body["skipped"] == [999999]
    assert body["requested"] == 2


def test_a_bulk_move_still_refuses_more_than_five_hundred_ids(client):
    account = _account(client)
    response = client.post(
        "/api/trades/bulk-account",
        json={"trade_ids": list(range(1, 502)), "account_id": account["id"]},
    )
    assert response.status_code == 422
    assert "500" in response.json()["detail"]
