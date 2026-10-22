"""Tests for the plan adherence score.

The score reads the pre-market note and compares it with the trades the day
actually took. A plan that named one setup and a day that traded another
has to score low — that is the whole point.
"""

from __future__ import annotations


def _record(**overrides) -> dict:
    payload = {
        "symbol": "gold",
        "direction": "buy",
        "size": 0.5,
        "entry_price": 4000.0,
        "exit_price": 4015.0,
        "initial_sl": 3990.0,
        "entry_time": "2026-09-20T10:00:00",
        "exit_time": "2026-09-20T10:45:00",
        "gross_pnl": 150.0,
    }
    payload.update(overrides)
    return payload


def _note(client, day: str, pre_market: str) -> None:
    response = client.put(f"/api/daily-notes/{day}", json={"pre_market": pre_market})
    assert response.status_code == 200, response.text


def test_a_day_without_a_plan_has_no_score(client):
    response = client.get("/api/daily-notes/2026-09-20/adherence")
    assert response.status_code == 200
    body = response.json()
    assert body["has_plan"] is False
    assert body["score"] is None
    assert body["notes"]


def test_a_plan_that_was_traded_scores_high(client):
    _note(client, "2026-09-20", "Plan: #fvg on gold, 0.5 lots.")
    client.post("/api/trades/backfill", json=_record(ticket="PLAN-1", tags=["#fvg"], size=0.5))

    body = client.get("/api/daily-notes/2026-09-20/adherence").json()
    assert body["has_plan"] is True
    assert body["planned_setups"] == ["fvg"]
    assert body["traded_setups"] == ["fvg"]
    assert body["setup_match"] == 1.0
    assert body["planned_size"] == 0.5
    assert body["size_match"] == 1.0
    assert body["trades"] == 1
    assert body["score"] == 100.0


def test_a_plan_that_was_ignored_scores_low(client):
    _note(client, "2026-09-20", "Plan: #fvg on gold, 0.5 lots.")
    client.post("/api/trades/backfill", json=_record(ticket="OTHER-1", tags=["#breakout"], size=0.1))

    body = client.get("/api/daily-notes/2026-09-20/adherence").json()
    assert body["setup_match"] == 0.0
    assert body["size_match"] == 0.0
    assert body["score"] is not None
    assert body["score"] < 30
    # The reason is spelled out, not just scored.
    assert any("fvg" in note for note in body["notes"])


def test_a_plan_with_no_trades_scores_low(client):
    _note(client, "2026-09-20", "Plan: #fvg on gold.")

    body = client.get("/api/daily-notes/2026-09-20/adherence").json()
    assert body["trades"] == 0
    assert body["score"] is not None
    assert body["score"] < 30


def test_the_plan_names_a_setup_it_writes_without_a_marker(client):
    client.post("/api/trades/backfill", json=_record(ticket="PLAN-2", tags=["#fvg"]))

    _note(client, "2026-09-20", "Plan: fvg only, no other setups.")
    body = client.get("/api/daily-notes/2026-09-20/adherence").json()
    assert body["planned_setups"] == ["fvg"]
    assert body["setup_match"] == 1.0


def test_the_size_is_read_from_the_plan(client):
    _note(client, "2026-09-20", "Plan: 0.25 lots on gold.")
    client.post("/api/trades/backfill", json=_record(ticket="PLAN-3", size=0.25))

    body = client.get("/api/daily-notes/2026-09-20/adherence").json()
    assert body["planned_size"] == 0.25
    assert body["size_match"] == 1.0


def test_only_the_days_trades_are_counted(client):
    _note(client, "2026-09-20", "Plan: #fvg on gold.")
    client.post(
        "/api/trades/backfill",
        json=_record(
            ticket="OTHER-DAY",
            tags=["#fvg"],
            entry_time="2026-09-21T10:00:00",
            exit_time="2026-09-21T10:45:00",
        ),
    )

    body = client.get("/api/daily-notes/2026-09-20/adherence").json()
    assert body["trades"] == 0
