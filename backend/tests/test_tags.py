"""Tests for the tag management API: listing, renaming, recategorising, merging.

A tag is a word the trader repeats. Renaming one has to reach every trade
that carried it, and merging one into another has to move the links and
leave the old name behind.
"""

from __future__ import annotations


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


def _tag_id(client, name: str) -> int:
    for tag in client.get("/api/tags").json():
        if tag["name"] == name:
            return int(tag["id"])
    raise AssertionError(f"no tag named {name}")


def test_the_tag_list_carries_the_counts_and_the_performance(client):
    client.post("/api/trades/backfill", json=_record(ticket="TAGGED-1", tags=["#fvg"]))
    client.post("/api/trades/backfill", json=_record(ticket="TAGGED-2", tags=["#fvg"]))
    client.post("/api/trades/backfill", json=_record(ticket="PLAIN-1"))

    tags = {tag["name"]: tag for tag in client.get("/api/tags").json()}
    assert tags["fvg"]["trade_count"] == 2
    assert tags["fvg"]["net_pnl"] == 300.0
    assert tags["fvg"]["win_rate"] == 100.0
    assert tags["fvg"]["category"] == "setup"


def test_a_renamed_tag_reaches_every_trade_that_carried_it(client):
    client.post("/api/trades/backfill", json=_record(ticket="TAGGED-1", tags=["#fvg"]))
    client.post("/api/trades/backfill", json=_record(ticket="TAGGED-2", tags=["#fvg"]))
    tag_id = _tag_id(client, "fvg")

    response = client.patch(f"/api/tags/{tag_id}", json={"name": "breakout"})
    assert response.status_code == 200
    assert response.json()["name"] == "breakout"

    rows = client.get("/api/trades", params={"tag": "breakout"}).json()
    assert rows["total"] == 2
    # The old name is gone.
    assert client.get("/api/trades", params={"tag": "fvg"}).json()["total"] == 0


def test_a_rename_cannot_take_an_existing_name(client):
    client.post("/api/trades/backfill", json=_record(ticket="TAGGED-1", tags=["#fvg"]))
    client.post("/api/trades/backfill", json=_record(ticket="TAGGED-2", tags=["#breakout"]))
    fvg = _tag_id(client, "fvg")
    breakout = _tag_id(client, "breakout")

    response = client.patch(f"/api/tags/{fvg}", json={"name": "breakout"})
    assert response.status_code == 409
    assert "breakout" in response.json()["detail"]
    # Nothing moved.
    assert client.get("/api/trades", params={"tag": "fvg"}).json()["total"] == 1


def test_a_tag_can_move_between_the_taxonomies(client):
    client.post("/api/trades/backfill", json=_record(ticket="TAGGED-1", tags=["#fvg"]))
    tag_id = _tag_id(client, "fvg")

    response = client.patch(f"/api/tags/{tag_id}", json={"category": "mistake"})
    assert response.status_code == 200
    assert response.json()["category"] == "mistake"

    bad = client.patch(f"/api/tags/{tag_id}", json={"category": "whatever"})
    assert bad.status_code == 422


def test_a_merge_moves_the_trades_and_removes_the_old_name(client):
    client.post("/api/trades/backfill", json=_record(ticket="TAGGED-1", tags=["#fvg"]))
    client.post("/api/trades/backfill", json=_record(ticket="TAGGED-2", tags=["#breakout"]))
    client.post(
        "/api/trades/backfill",
        json=_record(ticket="BOTH-1", tags=["#fvg", "#breakout"]),
    )
    fvg = _tag_id(client, "fvg")
    breakout = _tag_id(client, "breakout")

    response = client.post(
        "/api/tags/merge", json={"source_id": fvg, "target_id": breakout}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["merged"] == "fvg"
    assert body["into"] == "breakout"
    assert body["trades"] == 2

    # The old name is gone, and every trade that carried it now carries the
    # target — the trade with both tags carries it once.
    names = [tag["name"] for tag in client.get("/api/tags").json()]
    assert "fvg" not in names
    rows = client.get("/api/trades", params={"tag": "breakout"}).json()
    assert rows["total"] == 3
    for row in rows["items"]:
        assert [tag["name"] for tag in row["tags"]] == ["breakout"]


def test_a_merge_cannot_fold_a_tag_into_itself(client):
    client.post("/api/trades/backfill", json=_record(ticket="TAGGED-1", tags=["#fvg"]))
    fvg = _tag_id(client, "fvg")

    response = client.post("/api/tags/merge", json={"source_id": fvg, "target_id": fvg})
    assert response.status_code == 422


def test_a_merge_of_a_missing_tag_is_not_found(client):
    client.post("/api/trades/backfill", json=_record(ticket="TAGGED-1", tags=["#fvg"]))
    fvg = _tag_id(client, "fvg")

    response = client.post("/api/tags/merge", json={"source_id": fvg, "target_id": 999999})
    assert response.status_code == 404
