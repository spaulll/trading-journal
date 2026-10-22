"""Daily FX rates API.

Rates are entered manually (``FX_RATE_SOURCE=manual``) and read by every
conversion. ``GET /api/fx-rates/effective`` answers the question a caller
actually has — "what rate would a conversion use on this day?" — including
the fallback age, instead of making the client re-implement the lookup.
"""

from datetime import date as date_type
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.database import get_session
from app.models import FxEffectiveRate, FxRate, FxRateCreate, FxRateRead
from app.services.fx import (
    CROSS_PIVOT,
    default_source,
    lookup_rate,
    normalize_currency,
    reporting_currency,
    upsert_rate,
)

router = APIRouter(prefix="/api/fx-rates", tags=["fx-rates"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pair(base: object, quote: object) -> tuple[str, str]:
    src = normalize_currency(base)
    dst = normalize_currency(quote)
    if not src or not dst:
        raise HTTPException(
            status_code=422, detail="base and quote must be 3-5 letter currency codes"
        )
    if src == dst:
        raise HTTPException(status_code=422, detail="base and quote must differ")
    return src, dst


@router.get("", response_model=list[FxRateRead])
def list_rates(
    base: Optional[str] = Query(default=None),
    quote: Optional[str] = Query(default=None),
    date_from: Optional[date_type] = Query(default=None),
    date_to: Optional[date_type] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    session: Session = Depends(get_session),
):
    """Stored rates, newest first, filtered by pair and day range."""
    statement = select(FxRate)
    if base:
        statement = statement.where(FxRate.base == normalize_currency(base))
    if quote:
        statement = statement.where(FxRate.quote == normalize_currency(quote))
    if date_from:
        statement = statement.where(FxRate.date >= date_from)
    if date_to:
        statement = statement.where(FxRate.date <= date_to)
    statement = statement.order_by(FxRate.date.desc(), FxRate.base.asc(), FxRate.quote.asc())
    return list(session.exec(statement.limit(limit)).all())


@router.get("/effective", response_model=FxEffectiveRate)
def effective_rate(
    base: str = Query(default=None, description="From currency (default: FX_BASE_CURRENCY)"),
    quote: str = Query(description="To currency"),
    date: Optional[date_type] = Query(default=None, description="Defaults to today"),
    session: Session = Depends(get_session),
):
    """The rate a conversion would use, with its age and provenance.

    ``fallback`` is true when the requested day had no row and an earlier
    one was used; ``fallback_days`` is how many days old that rate is.
    ``missing`` means no rate exists at all and the amount must stay
    unknown.
    """
    when = date or date_type.today()
    src = base or reporting_currency()
    lookup = lookup_rate(session, src, quote, when)
    return FxEffectiveRate(**lookup.__dict__)


@router.post("", response_model=FxRateRead, status_code=201)
def store_rate(payload: FxRateCreate, session: Session = Depends(get_session)):
    """Create or correct one daily rate.

    Posting the same ``(date, base, quote)`` twice edits the row, so a
    fat-fingered rate is fixed by resending it — no delete step, no
    duplicate rows.
    """
    if payload.rate is None or payload.rate <= 0:
        raise HTTPException(status_code=422, detail="rate must be positive")
    base, quote = _pair(payload.base, payload.quote)
    when = payload.date or date_type.today()
    row = upsert_rate(
        session,
        when,
        base,
        quote,
        payload.rate,
        source=payload.source or default_source(),
    )
    session.commit()
    session.refresh(row)
    return row


@router.get("/pivot")
def pivot() -> dict:
    """The currency used to cross two pairs with no direct quote."""
    return {"pivot": CROSS_PIVOT, "reporting": reporting_currency()}
