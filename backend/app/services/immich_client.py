"""Async Immich API client (PLAN Task 2.1).

Server-side only — IMMICH_API_KEY never leaves the backend.
Monthly albums are named "YYYY-MM Trades" from the trade's entry time
and resolved album_ids are cached in memory.

Trade-aware uploads:
- filename ``YYYYMMDD-HHMM_SYMBOL_DIR_TICKET_label.ext`` (sortable, unique)
- ``fileCreatedAt/fileModifiedAt`` = trade execution date (label-aware:
  exit/mistake prefer close time, everything else open time)
- deterministic ``deviceAssetId`` so retries dedupe server-side instead
  of creating orphans (verified: Immich returns ``{"status":"duplicate"}``
  with the same id on re-upload, v3.2.2)
- ``exifInfo.description`` set best-effort via PATCH /api/assets/{id}
"""

import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

log = logging.getLogger("immich_client")

_thumbnail_cache: dict = {}
_album_cache: dict[str, str] = {}

DEVICE_ID = "trading-journal"
CLOSE_LABELS = {"exit", "mistake"}


def get_settings() -> tuple[str, str]:
    base = os.getenv("IMMICH_BASE_URL", "http://localhost:2283").rstrip("/")
    key = os.getenv("IMMICH_API_KEY", "")
    if not key:
        raise RuntimeError("IMMICH_API_KEY is not configured")
    return base, key


def month_album_name(ts: Optional[datetime]) -> str:
    ts = ts or datetime.now(timezone.utc)
    return f"{ts.year:04d}-{ts.month:02d} Trades"


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def open_moment(trade: Any) -> datetime:
    """Entry time for album routing — never the close time."""
    for cand in (getattr(trade, "entry_time", None), getattr(trade, "timestamp_open", None)):
        utc = _as_utc(cand)
        if utc is not None:
            return utc
    return datetime.now(timezone.utc)


def trade_moment(trade: Any, label: str) -> datetime:
    """Execution date for fileCreatedAt: close time for exit/mistake, else open."""
    if (label or "").lower() in CLOSE_LABELS:
        for cand in (getattr(trade, "exit_time", None), getattr(trade, "timestamp_close", None)):
            utc = _as_utc(cand)
            if utc is not None:
                return utc
    return open_moment(trade)


def _sanitize(value: str, fallback: str = "trade") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip()).strip("_")
    return cleaned or fallback


def trade_filename(trade: Any, label: str, ext: str) -> str:
    """YYYYMMDD-HHMM_SYMBOL_DIR_TICKET_label.ext — sortable + unique."""
    moment = trade_moment(trade, label)
    stamp = moment.strftime("%Y%m%d-%H%M")
    symbol = _sanitize(str(getattr(trade, "symbol", "") or "chart").upper(), "CHART")[:16]
    direction = _sanitize(str(getattr(trade, "direction", "") or "").lower(), "trade")[:8]
    ticket = _sanitize(str(getattr(trade, "ticket", "") or "noticket"))[:32]
    safe_label = _sanitize((label or "setup").lower(), "setup")[:12]
    safe_ext = re.sub(r"[^a-z0-9]", "", (ext or "png").lower()) or "png"
    return f"{stamp}_{symbol}_{direction}_{ticket}_{safe_label}.{safe_ext}"


def describe_trade(trade: Any, label: str) -> str:
    """One-line Immich description: symbol/dir/size, prices, PnL, R, ticket."""
    sym = getattr(trade, "symbol", "?") or "?"
    direction = (getattr(trade, "direction", "") or "?").upper()
    size = getattr(trade, "size", None)
    entry, exit_p = getattr(trade, "entry_price", None), getattr(trade, "exit_price", None)
    net, rmult = getattr(trade, "net_pnl", None), getattr(trade, "r_multiple", None)
    ticket = getattr(trade, "ticket", "?") or "?"
    bits = f"{direction} {sym}" + (f" {size}" if size is not None else "")
    if entry is not None:
        bits += f" @ {entry}" + (f" -> {exit_p}" if exit_p is not None else "")
    if net is not None:
        bits += f" | net {net:+.2f}"
    if rmult is not None:
        bits += f" ({rmult:+.2f}R)"
    return f"{bits} | {label} | ticket {ticket}"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def device_asset_id(ticket: str, label: str, digest: str) -> str:
    """Deterministic deviceAssetId — retry-safe, same bytes = same id."""
    return f"tj-{_sanitize(str(ticket or 'noticket'))[:32]}-{_sanitize((label or 'setup').lower())[:12]}-{digest[:16]}"


def sniff_image(data: bytes, filename: str, content_type: str) -> tuple[str, str]:
    """Return (ext, content_type) from magic bytes; fall back to hints."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    low = (filename or "").lower()
    if low.endswith(".png") or content_type == "image/png":
        return "png", "image/png"
    if low.endswith(".webp") or content_type == "image/webp":
        return "webp", "image/webp"
    return "jpg", "image/jpeg"


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
    device_asset_id: Optional[str] = None,
    device_id: Optional[str] = None,
) -> str:
    """Upload image bytes to Immich. Returns the asset id.

    Deterministic ids (trade helper below) make retries idempotent:
    Immich answers ``{"status":"duplicate"}`` with the existing id.
    """
    moment = (_as_utc(created_at) or datetime.now(timezone.utc)).isoformat()
    dev = device_id or DEVICE_ID
    daid = device_asset_id or f"{dev}-{sha256_hex(data)[:16]}"
    files = {"assetData": (filename, data, content_type)}
    form = {
        "deviceAssetId": daid,
        "deviceId": dev,
        "fileCreatedAt": moment,
        "fileModifiedAt": moment,
    }
    async with _client() as client:
        resp = await client.post("/api/assets", files=files, data=form)
        resp.raise_for_status()
        return resp.json()["id"]


async def update_asset_description(asset_id: str, description: str) -> None:
    """Best-effort exifInfo.description — never raises (PATCH, fallback PUT)."""
    async with _client() as client:
        try:
            resp = await client.patch(f"/api/assets/{asset_id}", json={"description": description})
            resp.raise_for_status()
            return
        except httpx.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status not in (404, 405, 422):
                log.warning("immich PATCH description failed (%s): %s", asset_id, exc)
            if status == 404:
                return
        try:
            resp = await client.put(f"/api/assets/{asset_id}", json={"description": description})
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("immich PUT description failed (%s): %s", asset_id, exc)


async def upload_trade_screenshot(
    data: bytes,
    trade: Any,
    label: str,
    original_filename: str = "",
    content_type: str = "",
) -> tuple[str, str, datetime]:
    """Full trade-aware upload: rename, date, deterministic id, description.

    Returns (asset_id, stored_filename, moment). Description failures are
    swallowed — the asset itself is what matters.
    """
    digest = sha256_hex(data)
    ext, ctype = sniff_image(data, original_filename, content_type)
    stored = trade_filename(trade, label, ext)
    moment = trade_moment(trade, label)
    daid = device_asset_id(str(getattr(trade, "ticket", "")), label, digest)
    asset_id = await upload_asset(data, stored, ctype, moment, daid, DEVICE_ID)
    try:
        await update_asset_description(asset_id, describe_trade(trade, label))
    except Exception:  # update_asset_description already swallows HTTP errors
        log.exception("immich description update crashed (%s)", asset_id)
    return asset_id, stored, moment


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
