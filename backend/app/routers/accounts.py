"""Prop-firm accounts CRUD + per-account prop status."""

import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.database import get_session
from app.models import Account, AccountCreate, AccountRead, AccountUpdate, Trade

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


def _prop_numbers(acc: Account, session: Session) -> dict:
    """Per-account prop headroom. Naive-UTC day basis, % off start balance.

    $ limits derive from pct × anchor: daily off start balance, max off
    start (static) or peak closed balance (trailing), target off start.
    """
    from app.services.timeutils import as_naive_utc

    start = acc.start_balance or 0.0
    daily_loss_usd = round(start * (acc.daily_loss_pct or 0.0) / 100, 2)
    max_pct = acc.max_loss_pct or 0.0

    trades = list(
        session.exec(
            select(Trade)
            .where(Trade.account_id == acc.id, Trade.status == "CLOSED")
            .order_by(Trade.timestamp_close.asc(), Trade.id.asc())
        ).all()
    )
    nets = [t.net_pnl if t.net_pnl is not None else 0.0 for t in trades]
    total_net = round(sum(nets), 2)
    balance = round((acc.start_balance or 0.0) + total_net, 2)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    day_start = datetime(now.year, now.month, now.day)
    daily_pnl = 0.0
    for t in trades:
        closed_at = as_naive_utc(t.timestamp_close)
        if closed_at is None or closed_at < day_start:
            continue
        daily_pnl += t.net_pnl or 0.0
    daily_pnl = round(daily_pnl, 2)

    # Max DD anchor: static = start balance, trailing = peak closed balance.
    peak = acc.start_balance or 0.0
    run = acc.start_balance or 0.0
    for n in nets:
        run += n
        peak = max(peak, run)
    anchor = peak if acc.max_mode == "trailing" else (acc.start_balance or 0.0)
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
    return {
        "account_id": acc.id,
        "alias": acc.alias,
        "balance": balance,
        "total_net": total_net,
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
    }


@router.get("/{account_id}/prop-status")
def prop_status(account_id: int, session: Session = Depends(get_session)):
    acc = session.get(Account, account_id)
    if acc is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return _prop_numbers(acc, session)
