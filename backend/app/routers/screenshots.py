"""Screenshot upload + Immich proxy endpoints (PLAN Task 2.2)."""

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlmodel import Session, SQLModel, select

from app.database import get_session
from app.models import Screenshot, ScreenshotRead, Trade
from app.services import immich_client

router = APIRouter(tags=["screenshots"])

MAX_BYTES = 15 * 1024 * 1024
LABELS = {"entry", "exit", "setup", "mistake"}
THUMB_CACHE_HEADERS = {"Cache-Control": "public, max-age=86400"}


def _is_image(data: bytes) -> bool:
    return (
        data.startswith(b"\x89PNG\r\n\x1a\n")
        or data.startswith(b"\xff\xd8\xff")
        or (data.startswith(b"RIFF") and data[8:12] == b"WEBP")
    )


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
    if not _is_image(data):
        raise HTTPException(status_code=415, detail="Unrecognized image bytes (png/jpg/webp only)")

    digest = immich_client.sha256_hex(data)
    dup = session.exec(
        select(Screenshot).where(Screenshot.trade_id == trade.id, Screenshot.sha256 == digest)
    ).first()
    if dup is not None:
        raise HTTPException(status_code=409, detail="Identical image already attached to this trade")

    original = file.filename or "screenshot.png"
    try:
        asset_id, stored, _moment = await immich_client.upload_trade_screenshot(
            data, trade, label, original, file.content_type or "image/png"
        )
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=f"Immich upload failed: {exc}")

    try:
        # Album stays on the entry month even for exit screenshots.
        album_name = immich_client.month_album_name(immich_client.open_moment(trade))
        album_id = await immich_client.resolve_monthly_album(album_name)
        await immich_client.add_assets_to_album(album_id, [asset_id], album_name)
    except (httpx.HTTPError, RuntimeError) as exc:
        # Avoid orphaning the asset when the album step fails.
        try:
            await immich_client.delete_assets([asset_id])
        except httpx.HTTPError:
            pass
        raise HTTPException(status_code=502, detail=f"Immich album attach failed: {exc}")

    shot = Screenshot(
        trade_id=trade.id,
        immich_asset_id=asset_id,
        label=label,
        original_filename=original[:255],
        stored_filename=stored,
        sha256=digest,
        byte_size=len(data),
    )
    session.add(shot)
    session.commit()
    session.refresh(shot)
    return ScreenshotRead.model_validate(shot.model_dump())


class ScreenshotLabelPatch(SQLModel):
    label: str


@router.patch("/api/screenshots/{screenshot_id}", response_model=ScreenshotRead)
def update_screenshot_label(
    screenshot_id: int, patch: ScreenshotLabelPatch, session: Session = Depends(get_session)
):
    shot = session.get(Screenshot, screenshot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="Screenshot not found")
    if patch.label not in LABELS:
        raise HTTPException(status_code=422, detail=f"label must be one of {sorted(LABELS)}")
    shot.label = patch.label
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
