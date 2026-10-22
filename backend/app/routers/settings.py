"""App settings for the web UI: the broker clock and the trading day."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, SQLModel

from app.database import get_session
from app.services import broker_clock
from app.services.trading_day import (
    DEFAULT_BOUNDARY_HOUR,
    DEFAULT_TIMEZONE,
    TradingDayError,
    current_trading_day,
    get_trading_day,
    set_trading_day,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class TradingDayPatch(SQLModel):
    boundary_hour: Optional[int] = None
    timezone: Optional[str] = None


@router.get("/broker-offset")
def get_broker_offset(session: Session = Depends(get_session)):
    minutes = broker_clock.get_offset_minutes(session)
    return {
        "offset_minutes": minutes,
        "label": broker_clock.format_label(minutes) if minutes is not None else None,
    }


@router.get("/trading-day")
def read_trading_day(session: Session = Depends(get_session)):
    """Where the trading day rolls over."""
    setting = get_trading_day(session)
    return {
        "boundary_hour": setting.boundary_hour,
        "timezone": setting.timezone,
        "label": setting.label(),
        # The day bucket the UI should call "today" — not the browser's
        # calendar date, which can be a different trading day.
        "today": current_trading_day(session).isoformat(),
        "default_boundary_hour": DEFAULT_BOUNDARY_HOUR,
        "default_timezone": DEFAULT_TIMEZONE,
    }


@router.put("/trading-day")
def write_trading_day(
    patch: TradingDayPatch, session: Session = Depends(get_session)
):
    """Move the trading day boundary.

    Every day bucket in the app follows it: the guardrails, the daily stats,
    the calendar, the streaks and the EOD prompt.
    """
    current = get_trading_day(session)
    try:
        setting = set_trading_day(
            session,
            current.boundary_hour if patch.boundary_hour is None else patch.boundary_hour,
            current.timezone if patch.timezone is None else patch.timezone,
        )
    except TradingDayError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return {
        "boundary_hour": setting.boundary_hour,
        "timezone": setting.timezone,
        "label": setting.label(),
        "today": current_trading_day(session).isoformat(),
        "default_boundary_hour": DEFAULT_BOUNDARY_HOUR,
        "default_timezone": DEFAULT_TIMEZONE,
    }
