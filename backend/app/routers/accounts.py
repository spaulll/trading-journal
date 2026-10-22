"""Prop-firm accounts CRUD + per-account prop status."""

import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.database import get_session
from app.models import Account, AccountCreate, AccountRead, AccountUpdate, Trade
from app.services.fx import convert_amount, normalize_currency
from app.services.trade_money import usd_net
from app.services.trading_day import get_trading_day

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]{1,23}$")
PHASES = {"challenge1", "phase1", "phase2", "funded", "personal"}
DAILY_BASIS = {"balance", "equity"}
MAX_MODES = {"static", "trailing"}
TRAILING_REFS = {"balance_peak", "equity_peak"}
STATUSES = {"active", "breach", "passed", "archived"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_alias(raw: str) -> str:
    alias = (raw or "").strip().lower()
    if not ALIAS_RE.match(alias):
        raise HTTPException(
            status_code=422,
            detail="alias must be lowercase a-z0-9-_ , 2-24 chars (e.g. ftmo100k-f1)",
        )
    return alias


def _normalize_base(raw: object, fallback: str = "USD") -> str:
    """The currency an account's balance is declared in.

    An omitted currency falls back to USD (the old schema had no column);
    a currency that was explicitly supplied must be a code. Coercing
    ``yen!`` to USD would hide a typo and quietly move the balance.
    """
    if raw is None or not str(raw).strip():
        return normalize_currency(fallback, "USD")
    currency = normalize_currency(raw)
    if not currency:
        raise HTTPException(
            status_code=422,
            detail="base_currency must be a 3-5 letter currency code (e.g. USD, JPY)",
        )
    return currency


def to_account_read(acc: Account, session: Session) -> AccountRead:
    open_trades = len(
        session.exec(
            select(Trade).where(Trade.account_id == acc.id, Trade.status == "OPEN")
        ).all()
    )
    total = len(
        session.exec(select(Trade).where(Trade.account_id == acc.id)).all()
    )
    data = acc.model_dump()
    data["open_trades"] = open_trades
    data["total_trades"] = total
    return AccountRead(**data)


@router.get("", response_model=list[AccountRead])
def list_accounts(
    include_archived: bool = Query(default=False),
    session: Session = Depends(get_session),
):
    stmt = select(Account).order_by(Account.firm.asc(), Account.alias.asc())
    if not include_archived:
        stmt = stmt.where(Account.status != "archived")
    accounts = list(session.exec(stmt).all())
    return [to_account_read(a, session) for a in accounts]


@router.post("", response_model=AccountRead, status_code=201)
def create_account(payload: AccountCreate, session: Session = Depends(get_session)):
    alias = _normalize_alias(payload.alias)
    if session.exec(select(Account).where(Account.alias == alias)).first() is not None:
        raise HTTPException(status_code=409, detail=f"alias already exists: {alias}")
    phase = (payload.phase or "personal").strip().lower()
    if phase not in PHASES:
        raise HTTPException(status_code=422, detail=f"phase must be one of {sorted(PHASES)}")
    if payload.daily_basis not in DAILY_BASIS:
        raise HTTPException(status_code=422, detail="daily_basis must be balance or equity")
    if payload.max_mode not in MAX_MODES:
        raise HTTPException(status_code=422, detail="max_mode must be static or trailing")
    if payload.trailing_ref not in TRAILING_REFS:
        raise HTTPException(status_code=422, detail="trailing_ref must be balance_peak or equity_peak")
    if (payload.status or "active") not in STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(STATUSES)}")
    if payload.start_balance < 0:
        raise HTTPException(status_code=422, detail="start_balance must be >= 0")
    for key in ("daily_loss_pct", "max_loss_pct"):
        if not 0 <= getattr(payload, key):
            raise HTTPException(status_code=422, detail=f"{key} must be >= 0")
        if getattr(payload, key) > 100:
            raise HTTPException(status_code=422, detail=f"{key} must be <= 100")
    if payload.profit_target_pct is not None and not 0 <= payload.profit_target_pct <= 100:
        raise HTTPException(status_code=422, detail="profit_target_pct must be 0-100")
    acc = Account(
        firm=(payload.firm or "").strip(),
        alias=alias,
        login=(payload.login or "").strip() or None,
        phase=phase,
        start_balance=payload.start_balance,
        base_currency=_normalize_base(payload.base_currency),
        daily_loss_pct=payload.daily_loss_pct,
        daily_basis=payload.daily_basis,
        max_loss_pct=payload.max_loss_pct,
        max_mode=payload.max_mode,
        trailing_ref=payload.trailing_ref,
        profit_target_pct=payload.profit_target_pct,
        status=payload.status or "active",
    )
    session.add(acc)
    session.commit()
    session.refresh(acc)
    return to_account_read(acc, session)


@router.get("/{account_id}", response_model=AccountRead)
def get_account(account_id: int, session: Session = Depends(get_session)):
    acc = session.get(Account, account_id)
    if acc is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return to_account_read(acc, session)


@router.patch("/{account_id}", response_model=AccountRead)
def update_account(account_id: int, patch: AccountUpdate, session: Session = Depends(get_session)):
    acc = session.get(Account, account_id)
    if acc is None:
        raise HTTPException(status_code=404, detail="Account not found")
    data = patch.model_dump(exclude_unset=True)
    if "alias" in data and data["alias"] is not None:
        alias = _normalize_alias(data["alias"])
        clash = session.exec(
            select(Account).where(Account.alias == alias, Account.id != account_id)
        ).first()
        if clash is not None:
            raise HTTPException(status_code=409, detail=f"alias already exists: {alias}")
        acc.alias = alias
        data.pop("alias")
    if "phase" in data and data["phase"] is not None:
        phase = str(data["phase"]).strip().lower()
        if phase not in PHASES:
            raise HTTPException(status_code=422, detail=f"phase must be one of {sorted(PHASES)}")
        acc.phase = phase
        data.pop("phase")
    for key in ("daily_basis", "max_mode", "trailing_ref", "status", "firm", "login"):
        if key in data and data[key] is not None:
            val = data.pop(key)
            if key == "daily_basis" and val not in DAILY_BASIS:
                raise HTTPException(status_code=422, detail="daily_basis must be balance or equity")
            if key == "max_mode" and val not in MAX_MODES:
                raise HTTPException(status_code=422, detail="max_mode must be static or trailing")
            if key == "trailing_ref" and val not in TRAILING_REFS:
                raise HTTPException(status_code=422, detail="trailing_ref must be balance_peak or equity_peak")
            if key == "status" and val not in STATUSES:
                raise HTTPException(status_code=422, detail=f"status must be one of {sorted(STATUSES)}")
            setattr(acc, key, val.strip() if isinstance(val, str) else val)
    if "base_currency" in data and data["base_currency"] is not None:
        acc.base_currency = _normalize_base(data.pop("base_currency"))
    for key in ("start_balance", "daily_loss_pct", "max_loss_pct", "profit_target_pct"):
        if key in data and data[key] is not None:
            if key == "start_balance" and data[key] < 0:
                raise HTTPException(status_code=422, detail=f"{key} must be >= 0")
            if key != "start_balance" and not 0 <= data[key] <= 100:
                raise HTTPException(status_code=422, detail=f"{key} must be 0-100")
            setattr(acc, key, data[key])
    acc.updated_at = _now()
    session.add(acc)
    session.commit()
    session.refresh(acc)
    return to_account_read(acc, session)


@router.delete("/{account_id}")
def delete_account(
    account_id: int,
    reassign_to: Optional[int] = None,
    session: Session = Depends(get_session),
):
    """Delete an account. Trades keep NULL unless reassign_to is given."""
    acc = session.get(Account, account_id)
    if acc is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if reassign_to is not None:
        target = session.get(Account, reassign_to)
        if target is None:
            raise HTTPException(status_code=404, detail="reassign_to account not found")
        for t in session.exec(select(Trade).where(Trade.account_id == account_id)).all():
            t.account_id = reassign_to
            t.updated_at = _now()
            session.add(t)
    else:
        for t in session.exec(select(Trade).where(Trade.account_id == account_id)).all():
            t.account_id = None
            t.updated_at = _now()
            session.add(t)
    session.delete(acc)
    session.commit()
    return {"deleted": account_id}


def _prop_numbers(acc: Account, session: Session, base_override: Optional[str] = None) -> dict:
    """Per-account prop headroom, converted into the requested currency.

    The account declares a base currency; every trade's P&L is quoted in
    its own currency. Each closed trade is converted at its close-day rate
    (falling back to the most recent earlier rate), and the balance moves
    in the account's base. ``?base=`` reports the same figures in another
    currency without changing the account.

    $ limits derive from pct × anchor: daily off start balance, max off
    start (static) or peak closed balance (trailing), target off start.
    """
    from app.services.timeutils import as_naive_utc

    account_base = _normalize_base(acc.base_currency)
    target = _normalize_base(base_override or account_base, account_base)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today = now.date()

    start_row = convert_amount(
        session, acc.start_balance or 0.0, account_base, target, today
    )
    if start_row.missing:
        raise HTTPException(
            status_code=422,
            detail=f"FX rate missing: {account_base}->{target}",
        )
    start = round(start_row.amount or 0.0, 2)

    daily_loss_usd = round(start * (acc.daily_loss_pct or 0.0) / 100, 2)
    max_pct = acc.max_loss_pct or 0.0

    trades = list(
        session.exec(
            select(Trade)
            .where(Trade.account_id == acc.id, Trade.status == "CLOSED")
            .order_by(Trade.timestamp_close.asc(), Trade.id.asc())
        ).all()
    )
    # The prop daily-loss guardrail follows the configured trading day, the
    # same bucket as the props' own day rollover.
    setting = get_trading_day(session)
    day_start, day_end = setting.bounds(setting.day_of(now))
    nets: list[float] = []
    daily_pnl = 0.0
    fx_missing = 0
    fx_fallback = 0
    max_fallback_days = 0
    for t in trades:
        # An unpriced trade has no amount to convert. It is not a zero.
        if t.net_pnl is None:
            continue
        closed_at = as_naive_utc(t.timestamp_close) or as_naive_utc(t.exit_time)
        when = (closed_at or as_naive_utc(t.timestamp_open) or now).date()
        quote = normalize_currency(t.quote_currency, "USD")
        conv = convert_amount(session, t.net_pnl, quote, target, when)
        if conv.missing:
            fx_missing += 1
            continue
        if conv.fallback:
            fx_fallback += 1
            max_fallback_days = max(max_fallback_days, conv.fallback_days)
        amount = round(conv.amount or 0.0, 2)
        nets.append(amount)
        if closed_at is not None and day_start <= closed_at < day_end:
            daily_pnl += amount

    total_net = round(sum(nets), 2)
    balance = round(start + total_net, 2)
    daily_pnl = round(daily_pnl, 2)

    # Max DD anchor: static = start balance, trailing = peak closed balance.
    peak = start
    run = start
    for n in nets:
        run += n
        peak = max(peak, run)
    anchor = peak if acc.max_mode == "trailing" else start
    max_loss_usd = round(anchor * max_pct / 100, 2)
    max_floor = anchor - max_loss_usd
    max_left = round(balance - max_floor, 2) if max_pct else None
    daily_floor = -daily_loss_usd
    daily_left = round(daily_pnl - daily_floor, 2) if (acc.daily_loss_pct or 0.0) else None

    target_usd = (
        round(start * acc.profit_target_pct / 100, 2)
        if acc.profit_target_pct
        else None
    )
    target_pct = (
        round(total_net / target_usd * 100, 2)
        if target_usd
        else None
    )
    breached = bool(
        ((acc.daily_loss_pct or 0.0) and daily_pnl <= -daily_loss_usd)
        or (max_left is not None and max_left <= 0)
    )
    open_trades = len(
        session.exec(
            select(Trade).where(Trade.account_id == acc.id, Trade.status == "OPEN")
        ).all()
    )
    total_trades = len(session.exec(select(Trade).where(Trade.account_id == acc.id)).all())
    return {
        "account_id": acc.id,
        "alias": acc.alias,
        # Currency of every money figure below.
        "base_currency": target,
        "account_base_currency": account_base,
        "start_balance": start,
        "balance": balance,
        "total_net": total_net,
        # USD view, regardless of the account's own currency.
        "total_net_usd": round(
            sum(usd_net(t) or 0.0 for t in trades if usd_net(t) is not None), 2
        ),
        "daily_pnl": daily_pnl,
        "daily_loss_pct": acc.daily_loss_pct or 0.0,
        "daily_loss_limit": daily_loss_usd,
        "daily_left": daily_left,
        "daily_basis": acc.daily_basis,
        "max_loss_pct": max_pct,
        "max_loss_limit": max_loss_usd,
        "max_mode": acc.max_mode,
        "max_floor": round(max_floor, 2) if max_pct else None,
        "max_left": max_left,
        "profit_target_pct": acc.profit_target_pct,
        "profit_target": target_usd,
        "target_pct": target_pct,
        "breached": breached,
        "status": "breach" if breached else acc.status,
        "open_trades": open_trades,
        "total_trades": total_trades,
        # A missing rate is reported, never silently treated as 1:1.
        "fx": {
            "missing": fx_missing,
            "fallback": fx_fallback,
            "max_fallback_days": max_fallback_days,
        },
    }


@router.get("/{account_id}/prop-status")
def prop_status(
    account_id: int,
    base: Optional[str] = Query(
        default=None, description="Report the figures in this currency (default: account base)"
    ),
    session: Session = Depends(get_session),
):
    acc = session.get(Account, account_id)
    if acc is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return _prop_numbers(acc, session, base)
