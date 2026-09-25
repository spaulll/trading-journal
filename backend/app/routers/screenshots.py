"""Screenshot upload + Immich proxy endpoints (PLAN Task 2.2)."""

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlmodel import Session

from app.database import get_session
from app.models import Screenshot, ScreenshotRead, Trade
from app.services import immich_client

router = APIRouter(tags=["screenshots"])

MAX_BYTES = 15 * 1024 * 1024
LABELS = {"entry", "exit", "setup", "mistake"}
THUMB_CACHE_HEADERS = {"Cache-Control": "public, max-age=86400"}


@router.post("/api/trades/{trade_id}/screenshots", response_model=ScreenshotRead)
async def upload_screenshot(
    trade_id: int,
    file: UploadFile = File(...),
    label: str = Form(default="setup"),
    session: Session = Depends(get_session),
):
    trade = session.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    if label not in LABELS:
        raise HTTPException(status_code=422, detail=f"label must be one of {sorted(LABELS)}")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=415, detail="Only image uploads are accepted")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Empty file")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds 15 MB limit")

    try:
        asset_id = await immich_client.upload_asset(
            data, file.filename or "screenshot.png", file.content_type or "image/png"
        )
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=f"Immich upload failed: {exc}")

    try:
        album_name = immich_client.month_album_name(trade.timestamp_open)
        album_id = await immich_client.resolve_monthly_album(album_name)
        await immich_client.add_assets_to_album(album_id, [asset_id], album_name)
    except (httpx.HTTPError, RuntimeError) as exc:
        # Avoid orphaning the asset when the album step fails.
        try:
            await immich_client.delete_assets([asset_id])
        except httpx.HTTPError:
            pass
        raise HTTPException(status_code=502, detail=f"Immich album attach failed: {exc}")

    shot = Screenshot(trade_id=trade.id, immich_asset_id=asset_id, label=label)
    session.add(shot)
    session.commit()
    session.refresh(shot)
    return ScreenshotRead.model_validate(shot.model_dump())


@router.get("/api/screenshots/{asset_id}/thumbnail")
async def proxy_thumbnail(asset_id: str):
    try:
        content, content_type = await immich_client.fetch_thumbnail(asset_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=f"Immich fetch failed: {exc}")
    return Response(content=content, media_type=content_type, headers=THUMB_CACHE_HEADERS)


@router.get("/api/screenshots/{asset_id}/full")
async def proxy_full(asset_id: str):
    try:
        content, content_type = await immich_client.fetch_original(asset_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Asset not found")
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=f"Immich fetch failed: {exc}")
    return Response(content=content, media_type=content_type)
