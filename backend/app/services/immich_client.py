"""Async Immich API client (PLAN Task 2.1).

Server-side only — IMMICH_API_KEY never leaves the backend.
Monthly albums are named "YYYY-MM Trades" from the trade's timestamp_open
and resolved album_ids are cached in memory.
"""

import os
from datetime import datetime, timezone
from typing import Optional

import httpx

_thumbnail_cache: dict = {}
_album_cache: dict[str, str] = {}


def get_settings() -> tuple[str, str]:
    base = os.getenv("IMMICH_BASE_URL", "http://localhost:2283").rstrip("/")
    key = os.getenv("IMMICH_API_KEY", "")
    if not key:
        raise RuntimeError("IMMICH_API_KEY is not configured")
    return base, key


def month_album_name(ts: Optional[datetime]) -> str:
    ts = ts or datetime.now(timezone.utc)
    return f"{ts.year:04d}-{ts.month:02d} Trades"


def _client() -> httpx.AsyncClient:
    base, key = get_settings()
    return httpx.AsyncClient(
        base_url=base,
        headers={"x-api-key": key, "Accept": "application/json"},
        timeout=60.0,
    )


async def resolve_monthly_album(name: str) -> str:
    """Return the album id for `name`, creating it when absent."""
    if name in _album_cache:
        return _album_cache[name]
    async with _client() as client:
        resp = await client.get("/api/albums")
        resp.raise_for_status()
        for album in resp.json():
            if album.get("albumName") == name:
                _album_cache[name] = album["id"]
                return album["id"]
        created = await client.post("/api/albums", json={"albumName": name})
        created.raise_for_status()
        album_id = created.json()["id"]
        _album_cache[name] = album_id
        return album_id


async def upload_asset(
    data: bytes,
    filename: str,
    content_type: str,
    created_at: Optional[datetime] = None,
) -> str:
    """Upload image bytes to Immich. Returns the asset id."""
    import uuid

    moment = (created_at or datetime.now(timezone.utc)).isoformat()
    device_id = f"trading-journal-{uuid.uuid4().hex[:12]}"
    files = {"assetData": (filename, data, content_type)}
    form = {
        "deviceAssetId": f"{device_id}-asset",
        "deviceId": device_id,
        "fileCreatedAt": moment,
        "fileModifiedAt": moment,
    }
    async with _client() as client:
        resp = await client.post("/api/assets", files=files, data=form)
        resp.raise_for_status()
        return resp.json()["id"]


async def add_assets_to_album(album_id: str, asset_ids: list[str], album_name: Optional[str] = None) -> None:
    """Attach assets; on a stale cached album id, re-resolve once and retry."""
    async with _client() as client:
        resp = await client.put(f"/api/albums/{album_id}/assets", json={"ids": asset_ids})
        if resp.status_code in (400, 404) and album_name:
            _album_cache.pop(album_name, None)
            album_id = await resolve_monthly_album(album_name)
            resp = await client.put(f"/api/albums/{album_id}/assets", json={"ids": asset_ids})
        resp.raise_for_status()


async def delete_assets(asset_ids: list[str]) -> None:
    """Best-effort orphan cleanup (force = skip trash)."""
    async with _client() as client:
        resp = await client.request("DELETE", "/api/assets", json={"ids": asset_ids, "force": True})
        resp.raise_for_status()


async def fetch_thumbnail(asset_id: str) -> tuple[bytes, str]:
    async with _client() as client:
        resp = await client.get(f"/api/assets/{asset_id}/thumbnail")
        if resp.status_code in (400, 404):
            raise FileNotFoundError(asset_id)
        resp.raise_for_status()
        return resp.content, resp.headers.get("content-type", "image/webp")


async def fetch_original(asset_id: str) -> tuple[bytes, str]:
    async with _client() as client:
        resp = await client.get(f"/api/assets/{asset_id}/original")
        if resp.status_code in (400, 404):
            raise FileNotFoundError(asset_id)
        resp.raise_for_status()
        return resp.content, resp.headers.get("content-type", "application/octet-stream")
