"""Prop-cash ledger: one dated row per movement, separate from trading P&L.

The ledger is deliberately simpler than the trade ledger:

  - the amount is always positive and the kind owns the direction;
  - the USD view is derived on the row's own date, never stored;
  - an unpriced row is surfaced, not counted as zero;
  - adding, editing or deleting a row never touches trade analytics.
"""

from __future__ import annotations

import pytest

from app.models import cash_direction


def _entry(client, **overrides) -> dict:
    payload = {
        "firm": "FTMO",
        "kind": "evaluation",
        "amount": 540.0,
        "currency": "USD",
        "occurred_on": "2026-01-05",
        "note": None,
    }
    payload.update(overrides)
    response = client.post("/api/cash", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _rate(client, day: str, base: str, quote: str, rate: float) -> None:
    response = client.post(
        "/api/fx-rates",
        json={"date": day, "base": base, "quote": quote, "rate": rate},
    )
    assert response.status_code == 201, response.text


def _summary(client, **params) -> dict:
    response = client.get("/api/cash/summary", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _trade(client) -> dict:
    response = client.post(
        "/api/trades/backfill",
        json={
            "symbol": "gold",
            "direction": "buy",
            "size": 0.1,
            "entry_price": 4000.0,
            "exit_price": 4015.0,
            "initial_sl": 3990.0,
            "entry_time": "2026-09-20T10:00:00",
            "exit_time": "2026-09-20T10:45:00",
            "gross_pnl": 150.0,
        },
    )
    assert response.status_code == 200, response.text
    return client.get("/api/trades").json()["items"][0]


def test_cash_direction_is_the_only_sign_rule():
    assert cash_direction("refund") == 1
    assert cash_direction("payout") == 1
    assert cash_direction("evaluation") == -1
    assert cash_direction("reset") == -1
    assert cash_direction("activation") == -1
    assert cash_direction("platform_fee") == -1
    with pytest.raises(ValueError):
        cash_direction("bonus")


def test_the_totals_follow_the_kind_and_match_the_roi_example(client):
    fee_a = _entry(client, kind="evaluation", amount=540.0, occurred_on="2026-01-05")
    fee_b = _entry(client, kind="reset", amount=540.0, occurred_on="2026-01-20")
    receipt_a = _entry(client, kind="payout", amount=4000.0, occurred_on="2026-02-10")
    receipt_b = _entry(client, kind="refund", amount=4000.0, occurred_on="2026-02-25")

    for row in (fee_a, fee_b, receipt_a, receipt_b):
        assert row["amount_usd"] == row["amount"]
        assert row["fx_missing"] is False

    summary = _summary(client)
    assert summary["currency"] == "USD"
    assert summary["spent"] == 1080.0
    assert summary["received"] == 8000.0
    assert summary["net"] == 6920.0
    assert summary["roi"] == 7.41
    assert summary["unpriced"] == 0
    assert summary["by_firm"] == [
        {
            "firm": "FTMO",
            "spent": 1080.0,
            "received": 8000.0,
            "net": 6920.0,
            "roi": 7.41,
            "entries": 4,
            "unpriced": 0,
        }
    ]


def test_a_row_converts_on_its_own_date_and_an_unpriced_row_stays_out(client):
    _rate(client, "2026-03-01", "EUR", "USD", 1.1)
    _rate(client, "2026-03-10", "EUR", "USD", 1.2)

    first = _entry(
        client,
        firm="FundedNext",
        kind="evaluation",
        amount=100.0,
        currency="EUR",
        occurred_on="2026-03-05",
    )
    second = _entry(
        client,
        firm="FundedNext",
        kind="evaluation",
        amount=100.0,
        currency="EUR",
        occurred_on="2026-03-10",
    )
    missing = _entry(
        client,
        firm="FundedNext",
        kind="evaluation",
        amount=100.0,
        currency="EUR",
        occurred_on="2026-02-01",
    )

    # The 5 March row uses the 1 March rate (earlier than its date); the
    # 10 March row uses the 10 March rate rather than the nearest earlier one.
    assert first["amount_usd"] == 110.0
    assert second["amount_usd"] == 120.0
    assert missing["amount_usd"] is None
    assert missing["fx_missing"] is True

    summary = _summary(client)
    assert summary["spent"] == 230.0
    assert summary["received"] == 0.0
    assert summary["net"] == -230.0
    assert summary["unpriced"] == 1
    assert summary["by_firm"][0]["entries"] == 3
    assert summary["by_firm"][0]["unpriced"] == 1

    # A late-arriving historical rate reprices the row on read; no row was
    # rewritten and the previously priced rows keep their own dates.
    _rate(client, "2026-01-31", "EUR", "USD", 1.05)
    summary = _summary(client)
    assert summary["spent"] == 335.0
    assert summary["unpriced"] == 0
    rows = client.get("/api/cash", params={"firm": "FundedNext"}).json()
    assert all(row["fx_missing"] is False for row in rows)


def test_editing_and_deleting_recompute_the_totals(client):
    fee = _entry(client, kind="evaluation", amount=540.0, occurred_on="2026-01-05")
    payout = _entry(client, kind="payout", amount=4000.0, occurred_on="2026-02-10")
    assert _summary(client)["net"] == 3460.0

    response = client.patch(f"/api/cash/{fee['id']}", json={"amount": 600.0})
    assert response.status_code == 200, response.text
    assert response.json()["amount_usd"] == 600.0
    summary = _summary(client)
    assert summary["spent"] == 600.0
    assert summary["net"] == 3400.0

    assert client.delete(f"/api/cash/{payout['id']}").status_code == 200
    summary = _summary(client)
    assert summary["received"] == 0.0
    assert summary["spent"] == 600.0
    assert summary["net"] == -600.0
    assert summary["roi"] == 0.0

    assert client.delete(f"/api/cash/{fee['id']}").status_code == 200
    summary = _summary(client)
    assert summary["spent"] == 0.0
    assert summary["received"] == 0.0
    assert summary["net"] == 0.0
    assert summary["roi"] is None
    assert summary["by_firm"] == []
    assert summary["unpriced"] == 0
    assert client.get("/api/cash").json() == []

    assert client.patch("/api/cash/9999", json={"amount": 1.0}).status_code == 404
    assert client.delete("/api/cash/9999").status_code == 404


def test_the_list_filters_and_orders_newest_first(client):
    _entry(client, firm="FTMO", kind="evaluation", amount=540.0, occurred_on="2025-12-31")
    _entry(client, firm="FTMO", kind="payout", amount=4000.0, occurred_on="2026-01-10")
    _entry(
        client,
        firm="FundedNext",
        kind="evaluation",
        amount=100.0,
        occurred_on="2026-02-01",
    )

    all_rows = client.get("/api/cash").json()
    assert [row["occurred_on"] for row in all_rows] == [
        "2026-02-01",
        "2026-01-10",
        "2025-12-31",
    ]

    assert len(client.get("/api/cash", params={"firm": "ftmo"}).json()) == 2
    assert len(client.get("/api/cash", params={"kind": "evaluation"}).json()) == 2
    assert len(client.get("/api/cash", params={"year": 2026}).json()) == 2
    assert (
        len(
            client.get(
                "/api/cash",
                params={"firm": "FTMO", "kind": "evaluation", "year": 2026},
            ).json()
        )
        == 0
    )

    summary = _summary(client, firm="ftmo")
    assert summary["spent"] == 540.0
    assert summary["received"] == 4000.0
    assert summary["net"] == 3460.0


def test_bad_amounts_kinds_and_currencies_are_rejected(client):
    base = {
        "firm": "FTMO",
        "kind": "evaluation",
        "amount": 540.0,
        "currency": "USD",
        "occurred_on": "2026-01-05",
    }
    for override in (
        {"amount": 0},
        {"amount": -1},
        {"amount": "not-a-number"},
        {"kind": "bonus"},
        {"firm": "   "},
        {"currency": "US"},
    ):
        payload = {**base, **override}
        response = client.post("/api/cash", json=payload)
        assert response.status_code == 422, (override, response.text)

    row = _entry(client)
    assert client.patch(f"/api/cash/{row['id']}", json={"amount": 0}).status_code == 422
    assert client.patch(f"/api/cash/{row['id']}", json={"kind": "bonus"}).status_code == 422
    assert client.get("/api/cash").json()[0]["amount"] == 540.0


def test_cash_entries_do_not_touch_trade_pnl_or_equity(client):
    trade = _trade(client)
    summary_before = client.get("/api/analytics/summary").json()
    equity_before = client.get("/api/analytics/equity-curve").json()

    _entry(client, kind="evaluation", amount=540.0, occurred_on="2026-01-05")
    _entry(client, kind="payout", amount=4000.0, occurred_on="2026-02-10")

    trade_after = client.get("/api/trades").json()["items"][0]
    summary_after = client.get("/api/analytics/summary").json()
    equity_after = client.get("/api/analytics/equity-curve").json()

    assert trade_after["id"] == trade["id"]
    assert trade_after["net_pnl"] == trade["net_pnl"]
    assert trade_after["net_pnl_usd"] == trade["net_pnl_usd"]
    assert summary_after == summary_before
    assert equity_after == equity_before
