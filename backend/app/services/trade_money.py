"""Trade P&L in its quote currency and in USD — one definition.

The journal stores two views of the same result:

- ``gross_pnl`` / ``net_pnl`` — the amount the broker booked, in the
  trade's ``quote_currency`` (JPY for USDJPY, USD for EURUSD);
- ``gross_pnl_usd`` / ``net_pnl_usd`` — the same amount at the close-day
  FX rate, which is the only number analytics and the guardrails may sum.

Every writer (API close, drawer patch, Telegram close, backfill, CSV
migration) goes through :func:`set_trade_pnl`, so the two views can never
disagree. :func:`usd_net` is the read-side guard: a trade whose rate is
missing stays unpriced instead of being added as if it were zero.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session

from app.models import Account, Trade
from app.services.fx import (
    RateQuote,
    convert_amount,
    lookup_rate,
    normalize_currency,
    reporting_currency,
)
from app.services.symbol_registry import find_spec
from app.services.timeutils import as_naive_utc

REPORTING_CURRENCY = "USD"


def trade_date(trade: Trade) -> date_type:
    """The day a trade's money is converted on.

    A closed trade uses its close day; an open one uses its entry day. The
    fallback is today so a hand-built row (tests, imports) still resolves.
    """
    for ts in (
        trade.timestamp_close,
        trade.exit_time,
        trade.timestamp_open,
        trade.entry_time,
        trade.created_at,
    ):
        when = as_naive_utc(ts)
        if when is not None:
            return when.date()
    return datetime.now(timezone.utc).date()


def quote_currency_for(session: Session, symbol: object) -> str:
    """The currency the symbol's P&L is quoted in, from the registry.

    An unregistered symbol has no contract, so its P&L is never priced; the
    reporting currency is the least surprising label for the empty field.
    """
    spec = find_spec(session, symbol)
    if spec is not None:
        return normalize_currency(spec.quote_currency, REPORTING_CURRENCY)
    return normalize_currency(reporting_currency(), REPORTING_CURRENCY)


def sync_trade_currency(session: Session, trade: Trade, force: bool = False) -> None:
    """Stamp the trade with its symbol's quote currency.

    ``force`` is for a symbol change: the stored currency described the old
    symbol and would mislabel the new P&L.
    """
    if force or not normalize_currency(trade.quote_currency):
        trade.quote_currency = quote_currency_for(session, trade.symbol)


def rate_fallback(
    quote: str, price: Optional[float], symbol: str = ""
) -> Optional[float]:
    """A ``quote -> USD`` rate implied by a pair's own price.

    USDJPY at 151 is literally "151 yen per dollar", so its price states
    the *USD -> JPY* rate. The conversion needs the other direction —
    dollars per yen — so the price is inverted here. This is only a
    fallback for a pair the journal trades; a cross with no stored rate
    still stays unpriceable.
    """
    quote = normalize_currency(quote)
    symbol = str(symbol or "").strip().upper()
    if quote and quote != REPORTING_CURRENCY and symbol == f"{REPORTING_CURRENCY}{quote}":
        if price is not None and price > 0:
            return 1.0 / float(price)
    return None


def symbol_rate_fallback(trade: Trade) -> Optional[float]:
    """A ``quote -> USD`` rate implied by the trade when the table has none.

    ``exit_price`` is the close-day proxy; an open trade falls back to its
    entry price, which is the rate the position was priced at.
    """
    price = trade.exit_price
    if price is None:
        price = trade.entry_price
    return rate_fallback(
        trade.quote_currency, price, str(trade.symbol or "")
    )


def account_base_currency(session: Session, account_id: Optional[int]) -> str:
    """The deposit currency of an account, or the reporting currency.

    Manual P&L and fee entries mirror what a broker statement shows, which
    is the account's deposit currency. Accounts default to the reporting
    currency when they carry none.
    """
    if account_id is not None:
        account = session.get(Account, account_id)
        if account is not None:
            return normalize_currency(account.base_currency, REPORTING_CURRENCY)
    return REPORTING_CURRENCY


def base_input_to_quote(
    session: Session,
    base: str,
    quote: str,
    amount: Optional[float],
    when: Optional[date_type] = None,
    fallback_rate: Optional[float] = None,
) -> Optional[float]:
    """Convert a user-entered money amount into the trade's quote currency.

    Manual P&L and fee entries mirror what a broker statement shows, which
    is the account's deposit currency (``base``). The stored quote-currency
    amounts (``gross_pnl`` / ``net_pnl`` / ``fees``) must live in the
    symbol's own quote currency, so when the two differ the input is
    converted at the close-day rate — or the pair's own price when the rate
    table has nothing (``fallback_rate``). When no rate resolves at all the
    amount is kept verbatim, matching the legacy behavior: the trade then
    reports as unpriced rather than guessing. ``None`` passes through.
    """
    if amount is None:
        return None
    quote = normalize_currency(quote)
    base = normalize_currency(base, REPORTING_CURRENCY)
    if not quote or quote == base:
        return round(float(amount), 2)
    when = when or date_type.today()
    quote_rate = lookup_rate(session, quote, base, when)
    if (quote_rate.missing or quote_rate.rate is None or quote_rate.rate <= 0) and fallback_rate:
        quote_rate = RateQuote(
            base=quote,
            quote=base,
            requested_date=when,
            rate=float(fallback_rate),
            as_of=when,
            source="symbol",
            missing=False,
        )
    if quote_rate.missing or quote_rate.rate is None or quote_rate.rate <= 0:
        return round(float(amount), 2)
    return round(float(amount) / float(quote_rate.rate), 2)


def sync_trade_usd(session: Session, trade: Trade) -> None:
    """Recompute the USD view from the quote-currency amounts.

    Called after any change to a price leg, a fee, a timestamp or the quote
    currency itself. It never invents a value: when no rate resolves, the
    USD field is left ``None`` and the trade is reported as FX-missing.
    """
    quote = normalize_currency(trade.quote_currency, REPORTING_CURRENCY)
    trade.quote_currency = quote
    when = trade_date(trade)
    implied = symbol_rate_fallback(trade)

    def usd(amount: Optional[float]) -> Optional[float]:
        if amount is None:
            return None
        conversion = convert_amount(
            session,
            amount,
            quote,
            REPORTING_CURRENCY,
            when,
            fallback_rate=implied,
        )
        return conversion.amount

    trade.gross_pnl_usd = usd(trade.gross_pnl)
    trade.net_pnl_usd = usd(trade.net_pnl)


def set_trade_pnl(
    session: Session, trade: Trade, gross: Optional[float], fees: Optional[float] = None
) -> None:
    """Write the quote-currency P&L and its USD equivalent together.

    ``gross`` is in the trade's quote currency. ``net`` follows the same
    gross-minus-fees rule as everywhere else; an explicitly stored
    ``net_pnl`` is replaced so the invariant can never drift.
    """
    fee = float(fees if fees is not None else (trade.fees or 0.0))
    trade.fees = fee
    trade.gross_pnl = round(float(gross), 2) if gross is not None else None
    trade.net_pnl = round(float(gross) - fee, 2) if gross is not None else None
    sync_trade_currency(session, trade)
    sync_trade_usd(session, trade)


def usd_net(trade: Trade) -> Optional[float]:
    """The USD net P&L used by every total, or None when unpriceable.

    Legacy rows (no ``quote_currency``) were already stored in USD, so they
    keep reporting their original number. A non-USD row with no converted
    value is genuinely unknown — it must not be summed as zero.
    """
    if trade.net_pnl is None:
        return None
    quote = normalize_currency(trade.quote_currency)
    if not quote or quote == REPORTING_CURRENCY:
        return trade.net_pnl if trade.net_pnl_usd is None else trade.net_pnl_usd
    return trade.net_pnl_usd


def usd_gross(trade: Trade) -> Optional[float]:
    """USD gross P&L, with the same legacy rule as :func:`usd_net`."""
    if trade.gross_pnl is None:
        return None
    quote = normalize_currency(trade.quote_currency)
    if not quote or quote == REPORTING_CURRENCY:
        return trade.gross_pnl if trade.gross_pnl_usd is None else trade.gross_pnl_usd
    return trade.gross_pnl_usd


def fx_missing(trade: Trade) -> bool:
    """True when the quote P&L exists but its USD conversion does not."""
    return (
        trade.net_pnl is not None
        and normalize_currency(trade.quote_currency) not in ("", REPORTING_CURRENCY)
        and trade.net_pnl_usd is None
    )


def currency_breakdown(trades: list[Trade]) -> dict[str, float]:
    """Quote-currency net totals, so a bucket can show its currencies.

    The overall figure stays USD; this map is the audit trail behind it.
    """
    totals: dict[str, float] = {}
    for trade in trades:
        if trade.net_pnl is None:
            continue
        currency = normalize_currency(trade.quote_currency, REPORTING_CURRENCY)
        totals[currency] = round(totals.get(currency, 0.0) + trade.net_pnl, 2)
    return dict(sorted(totals.items()))
