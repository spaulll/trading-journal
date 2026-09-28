"""Read-only app settings for the web UI (broker clock offset)."""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session
from app.services import broker_clock

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/broker-offset")
def get_broker_offset(session: Session = Depends(get_session)):
    minutes = broker_clock.get_offset_minutes(session)
    return {
        "offset_minutes": minutes,
        "label": broker_clock.format_label(minutes) if minutes is not None else None,
    }
