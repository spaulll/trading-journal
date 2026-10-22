"""Daily FX rates and the single currency-conversion rule.

A trade's P&L is stated in its quote currency — yen for USDJPY, dollars for
EURUSD. Analytics and guardrails need one comparable number, so every
conversion goes through this module:

- a stored :class:`~app.models.FxRate` row is the source of truth;
- a direct quote, an inverse quote, or a cross through the reporting base
  currency all resolve to the same rate;
- a missing day falls back to the most recent earlier rate and says how
  stale the rate was, instead of silently using 1.0;
- a currency with no rate at all reports ``missing`` so the caller can
  leave the USD amount unknown rather than invent one.

``rate`` always means *quote units per 1.0 base* — the market convention.
The env knobs live here so no caller hardcodes a currency: ``FX_RATE_SOURCE``
labels new rows, ``FX_BASE_CURRENCY`` is the reporting currency.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date as date_type
from typing import Optional

from sqlmodel import Session, select

from app.models import FxRate

# Pivot used to cross two currencies that have no direct quote. USD is the
# reporting currency of the journal, so most quotes share it.
CROSS_PIVOT = "USD"


def reporting_currency() -> str:
    """Currency every total is reported in (``FX_BASE_CURRENCY``)."""
    return normalize_currency(os.getenv("FX_BASE_CURRENCY", CROSS_PIVOT)) or CROSS_PIVOT


def default_source() -> str:
    """Label written on a rate that came from the manual API."""
    return (os.getenv("FX_RATE_SOURCE", "manual").strip() or "manual").lower()


def normalize_currency(raw: object, fallback: Optional[str] = None) -> str:
    """Uppercase ISO-ish code, or the fallback when unusable.

    Accepts 3-5 letters so ``USDT`` is not rejected, but not arbitrary text:
    a code is a key in the rate table, not a free-form label.
    """
    text = str(raw or "").strip().upper()
    if 3 <= len(text) <= 5 and text.isalpha():
        return text
    return (fallback or "").strip().upper()


@dataclass(frozen=True)
class RateQuote:
    """An effective rate plus where it came from / how stale it is."""

    base: str
    quote: str
    requested_date: date_type
    rate: Optional[float] = None
    as_of: Optional[date_type] = None
    source: str = "missing"  # identity | direct | inverse | cross | missing
    via: Optional[str] = None
    fallback: bool = False
    fallback_days: int = 0
    missing: bool = True


@dataclass(frozen=True)
class Conversion:
    """A converted amount with the same provenance as its rate."""

    amount: Optional[float]
    source_currency: str
    target_currency: str
    rate: Optional[float] = None
    as_of: Optional[date_type] = None
    requested_date: Optional[date_type] = None
    source: str = "missing"
    via: Optional[str] = None
    fallback: bool = False
    fallback_days: int = 0
    missing: bool = True


def _latest_rate(
    session: Session, base: str, quote: str, on_date: date_type
) -> Optional[FxRate]:
    """Most recent stored rate for the pair on or before ``on_date``."""
    return session.exec(
        select(FxRate)
        .where(
            FxRate.base == base,
            FxRate.quote == quote,
            FxRate.date <= on_date,
        )
        .order_by(FxRate.date.desc(), FxRate.id.desc())
    ).first()


def _leg(
    session: Session, base: str, quote: str, on_date: date_type
) -> Optional[tuple[float, date_type]]:
    """Resolve one pair directly or through its inverse."""
    row = _latest_rate(session, base, quote, on_date)
    if row is not None and row.rate:
        return float(row.rate), row.date
    inverse = _latest_rate(session, quote, base, on_date)
    if inverse is not None and inverse.rate:
        return 1.0 / float(inverse.rate), inverse.date
    return None


def lookup_rate(
    session: Session, base: object, quote: object, on_date: date_type
) -> RateQuote:
    """The effective rate for ``base -> quote`` on ``on_date``.

    Direct, inverse and cross-through-USD all count. The most recent earlier
    rate is used when the day itself is missing; ``fallback_days`` reports
    the gap so a stale rate is never mistaken for a fresh one.
    """
    src = normalize_currency(base, reporting_currency())
    dst = normalize_currency(quote, reporting_currency())
    if src == dst:
        return RateQuote(
            base=src,
            quote=dst,
            requested_date=on_date,
            rate=1.0,
            as_of=on_date,
            source="identity",
            missing=False,
        )

    direct = _latest_rate(session, src, dst, on_date)
    if direct is not None and direct.rate:
        return RateQuote(
            base=src,
            quote=dst,
            requested_date=on_date,
            rate=float(direct.rate),
            as_of=direct.date,
            source="direct",
            fallback=direct.date != on_date,
            fallback_days=max(0, (on_date - direct.date).days),
            missing=False,
        )

    inverse = _latest_rate(session, dst, src, on_date)
    if inverse is not None and inverse.rate:
        return RateQuote(
            base=src,
            quote=dst,
            requested_date=on_date,
            rate=1.0 / float(inverse.rate),
            as_of=inverse.date,
            source="inverse",
            fallback=inverse.date != on_date,
            fallback_days=max(0, (on_date - inverse.date).days),
            missing=False,
        )

    # Cross through the reporting currency. ``_leg`` resolves either side of
    # the pivot as a direct or an inverse quote, so USDJPY + USDINR can price
    # JPY -> INR without a stored JPY/INR row.
    pivot = CROSS_PIVOT
    if pivot not in (src, dst):
        left = _leg(session, src, pivot, on_date)
        right = _leg(session, pivot, dst, on_date)
        if left is not None and right is not None:
            as_of = min(left[1], right[1])
            return RateQuote(
                base=src,
                quote=dst,
                requested_date=on_date,
                rate=left[0] * right[0],
                as_of=as_of,
                source="cross",
                via=pivot,
                fallback=as_of != on_date,
                fallback_days=max(0, (on_date - as_of).days),
                missing=False,
            )

    return RateQuote(base=src, quote=dst, requested_date=on_date, missing=True)


def convert_amount(
    session: Session,
    amount: Optional[float],
    source: object,
    target: object,
    on_date: Optional[date_type] = None,
    *,
    fallback_rate: Optional[float] = None,
    fallback_source: str = "symbol",
) -> Conversion:
    """Convert ``amount`` from one currency to another on ``on_date``.

    ``fallback_rate`` is the last-resort rate a caller may know from the
    trade itself (the exit price of USDJPY is the USD/JPY rate). It is only
    consulted when the table has nothing, and the result is labelled with
    ``fallback_source`` so the provenance is never hidden.

    A ``None`` amount stays ``None`` and is not an error: an unpriced trade
    has no amount to convert.
    """
    when = on_date or date_type.today()
    src = normalize_currency(source, reporting_currency())
    dst = normalize_currency(target, reporting_currency())
    if amount is None:
        return Conversion(
            amount=None,
            source_currency=src,
            target_currency=dst,
            requested_date=when,
            missing=False,
        )

    quote = lookup_rate(session, src, dst, when)
    if quote.missing and fallback_rate is not None and fallback_rate:
        quote = RateQuote(
            base=src,
            quote=dst,
            requested_date=when,
            rate=float(fallback_rate),
            as_of=when,
            source=fallback_source,
            missing=False,
        )
    if quote.missing or quote.rate is None:
        return Conversion(
            amount=None,
            source_currency=src,
            target_currency=dst,
            requested_date=when,
            rate=None,
            as_of=quote.as_of,
            source="missing",
            via=quote.via,
            fallback=quote.fallback,
            fallback_days=quote.fallback_days,
            missing=True,
        )
    return Conversion(
        amount=round(float(amount) * quote.rate, 2),
        source_currency=src,
        target_currency=dst,
        rate=quote.rate,
        as_of=quote.as_of,
        requested_date=when,
        source=quote.source,
        via=quote.via,
        fallback=quote.fallback,
        fallback_days=quote.fallback_days,
        missing=False,
    )


def upsert_rate(
    session: Session,
    when: date_type,
    base: object,
    quote: object,
    rate: float,
    source: Optional[str] = None,
) -> FxRate:
    """Create or update the rate for one day and pair.

    Re-posting the same triple edits the row rather than duplicating it,
    so a correction is one call and the unique index stays satisfiable.
    """
    src = normalize_currency(base)
    dst = normalize_currency(quote)
    row = session.exec(
        select(FxRate).where(
            FxRate.date == when,
            FxRate.base == src,
            FxRate.quote == dst,
        )
    ).first()
    if row is None:
        row = FxRate(
            date=when,
            base=src,
            quote=dst,
            rate=float(rate),
            source=(source or default_source()).strip().lower() or "manual",
        )
    else:
        row.rate = float(rate)
        row.source = (source or row.source or default_source()).strip().lower() or "manual"
    session.add(row)
    session.flush()
    return row


def to_effective(quote: RateQuote) -> dict:
    """Plain-dict view for the API response."""
    return {
        "base": quote.base,
        "quote": quote.quote,
        "requested_date": quote.requested_date,
        "rate": quote.rate,
        "as_of": quote.as_of,
        "source": quote.source,
        "via": quote.via,
        "fallback": quote.fallback,
        "fallback_days": quote.fallback_days,
        "missing": quote.missing,
    }
