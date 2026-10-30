"""App settings for the web UI: the broker clock and the trading day."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, SQLModel

from app.database import get_session
from app.services import broker_clock
from app.services.broker_clock import (
    DST_RULES,
    MAX_OFFSET_MINUTES,
    BrokerClock,
    format_label,
    normalize_firm,
)
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


class BrokerClockPatch(SQLModel):
    firm: Optional[str] = None
    base_offset_minutes: int
    dst: str = "none"


class BrokerClockOverride(SQLModel):
    firm: Optional[str] = None
    offset_minutes: int
    effective_from: Optional[str] = None


# --- broker clock ----------------------------------------------------------


def _clock_payload(
    firm: str, clock: Optional[BrokerClock], configured: bool, now: datetime
) -> dict:
    if clock is None:
        return {
            "firm": firm,
            "configured": False,
            "base_offset_minutes": None,
            "dst": None,
            "dst_label": None,
            "overrides": [],
            "offset_minutes": None,
            "label": None,
            "manual": False,
            "next_change": None,
        }
    upcoming = clock.next_change(now)
    return {
        "firm": firm,
        "configured": configured,
        "base_offset_minutes": clock.base_offset_minutes,
        "dst": clock.dst,
        "dst_label": broker_clock.dst_rule_label(clock.dst),
        "overrides": [
            {"effective_from": when.isoformat(), "offset_minutes": minutes}
            for when, minutes in sorted(clock.overrides)
        ],
        "offset_minutes": clock.offset_for(now),
        "label": format_label(clock.offset_for(now)),
        "manual": clock.is_manual_at(now),
        "next_change": None
        if upcoming is None
        else {
            "at": upcoming[0].isoformat(),
            "offset_minutes": upcoming[1],
            "label": format_label(upcoming[1]),
        },
    }


@router.get("/broker-clock")
def read_broker_clock(session: Session = Depends(get_session)):
    """Every firm's clock, resolved for right now."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    configured = {
        normalize_firm(firm): clock
        for firm, clock in broker_clock.configured_clocks(session)
    }
    firms = broker_clock.known_firms(session)
    clocks = []
    for firm in firms:
        clock = broker_clock.get_clock(session, firm)
        clocks.append(
            _clock_payload(firm, clock, normalize_firm(firm) in configured, now)
        )
    if not clocks:
        # No accounts and no config yet: describe the fallback so the page
        # still has something to render.
        clocks.append(
            _clock_payload(
                "",
                broker_clock.get_clock(session),
                broker_clock.DEFAULT_FIRM in configured,
                now,
            )
        )
    return {
        "now": now.isoformat(),
        "dst_rules": [
            {"value": rule, "label": broker_clock.dst_rule_label(rule)}
            for rule in DST_RULES
        ],
        "clocks": clocks,
    }


@router.put("/broker-clock")
def write_broker_clock(
    patch: BrokerClockPatch, session: Session = Depends(get_session)
):
    """Set a firm's rule: standard offset + which DST calendar it follows."""
    if not -MAX_OFFSET_MINUTES <= patch.base_offset_minutes <= MAX_OFFSET_MINUTES:
        raise HTTPException(status_code=422, detail="base_offset_minutes is implausible")
    if patch.dst not in DST_RULES:
        raise HTTPException(
            status_code=422, detail=f"dst must be one of {', '.join(DST_RULES)}"
        )
    try:
        clock = broker_clock.set_clock(
            session, patch.firm, patch.base_offset_minutes, patch.dst
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return _clock_payload(
        (patch.firm or "").strip(),
        clock,
        True,
        now,
    )


@router.post("/broker-clock/override")
def write_broker_clock_override(
    patch: BrokerClockOverride, session: Session = Depends(get_session)
):
    """Pin the offset from a date — the manual correction, not the routine."""
    if not -MAX_OFFSET_MINUTES <= patch.offset_minutes <= MAX_OFFSET_MINUTES:
        raise HTTPException(status_code=422, detail="offset_minutes is implausible")
    when: Optional[datetime] = None
    if patch.effective_from:
        try:
            when = datetime.fromisoformat(
                patch.effective_from.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail="effective_from must be an ISO datetime"
            ) from exc
        if when.tzinfo is not None:
            when = when.astimezone(timezone.utc).replace(tzinfo=None)
    clock = broker_clock.set_override(session, patch.firm, patch.offset_minutes, when)
    session.commit()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return _clock_payload((patch.firm or "").strip(), clock, True, now)


@router.delete("/broker-clock/override")
def delete_broker_clock_override(
    firm: Optional[str] = None, session: Session = Depends(get_session)
):
    """Drop every manual correction and go back to the automatic rule."""
    clock = broker_clock.clear_overrides(session, firm)
    session.commit()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return _clock_payload((firm or "").strip(), clock, True, now)


@router.get("/broker-offset")
def get_broker_offset(session: Session = Depends(get_session)):
    """Legacy single-offset view: the default firm's offset right now."""
    minutes = broker_clock.get_offset_minutes(session)
    return {
        "offset_minutes": minutes,
        "label": format_label(minutes) if minutes is not None else None,
    }


# --- trading day -----------------------------------------------------------


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
