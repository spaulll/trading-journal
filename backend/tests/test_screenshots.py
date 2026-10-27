"""Deleting a screenshot must delete the Immich asset too.

The journal row is metadata for an asset that only exists in Immich, so the
order matters: a successful remote delete removes the row, a failed one keeps
it so the trader can retry instead of losing the only copy.
"""

from __future__ import annotations

import httpx
from sqlmodel import Session

from app.database import engine
from app.models import Screenshot
from app.services import immich_client


def _open(client) -> dict:
    response = client.post(
        "/api/trades/open",
        json={
            "symbol": "GOLD",
            "direction": "buy",
            "size": 0.1,
            "entry_price": 4000.0,
            "initial_sl": 3990.0,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _shot(trade_id: int, asset_id: str = "asset-1") -> int:
    with Session(engine) as db:
        shot = Screenshot(
            trade_id=trade_id,
            immich_asset_id=asset_id,
            label="entry",
            original_filename="chart.png",
            sha256="deadbeef",
        )
        db.add(shot)
        db.commit()
        db.refresh(shot)
        assert shot.id is not None
        return shot.id


def test_delete_removes_the_asset_and_the_row(client, monkeypatch):
    trade = _open(client)
    shot_id = _shot(trade["id"])
    calls: list[list[str]] = []

    async def fake_delete(asset_ids: list[str]) -> None:
        calls.append(asset_ids)

    monkeypatch.setattr(immich_client, "delete_assets", fake_delete)

    response = client.delete(f"/api/screenshots/{shot_id}")

    assert response.status_code == 200, response.text
    assert response.json() == {"deleted": shot_id, "immich_deleted": True}
    assert calls == [["asset-1"]]
    assert client.get(f"/api/trades/{trade['id']}").json()["screenshots"] == []


def test_failed_immich_delete_keeps_the_row(client, monkeypatch):
    trade = _open(client)
    shot_id = _shot(trade["id"])

    async def boom(asset_ids: list[str]) -> None:
        raise httpx.ConnectError("immich is down")

    monkeypatch.setattr(immich_client, "delete_assets", boom)

    response = client.delete(f"/api/screenshots/{shot_id}")

    assert response.status_code == 502
    with Session(engine) as db:
        assert db.get(Screenshot, shot_id) is not None
    screenshots = client.get(f"/api/trades/{trade['id']}").json()["screenshots"]
    assert [s["id"] for s in screenshots] == [shot_id]


def test_unknown_screenshot_is_404(client):
    response = client.delete("/api/screenshots/999999")
    assert response.status_code == 404


def test_shared_asset_is_not_deleted_while_another_trade_uses_it(client, monkeypatch):
    """Immich dedupes identical bytes — one asset can back several trades."""
    first = _open(client)
    second = _open(client)
    first_shot = _shot(first["id"], asset_id="shared-asset")
    _shot(second["id"], asset_id="shared-asset")

    calls: list[list[str]] = []

    async def fake_delete(asset_ids: list[str]) -> None:
        calls.append(asset_ids)

    monkeypatch.setattr(immich_client, "delete_assets", fake_delete)

    response = client.delete(f"/api/screenshots/{first_shot}")

    assert response.status_code == 200, response.text
    assert response.json() == {"deleted": first_shot, "immich_deleted": False}
    assert calls == []
    assert client.get(f"/api/trades/{first['id']}").json()["screenshots"] == []
    assert len(client.get(f"/api/trades/{second['id']}").json()["screenshots"]) == 1
