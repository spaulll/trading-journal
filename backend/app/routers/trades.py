"""Unified trade lifecycle API (PLAN-v2 Task 1.3).

Live ingestion is the Telegram client (Phase 2) + web modals (Phase 5)
calling these endpoints. The v1 CSV sync endpoint is removed; history
imports go through app.services.migrate_csv (one-shot).
"""

import os
from datetime import datetime, timezone
from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, delete, select

from app.database import get_session
from app.models import (
    BackfillRecord,
    BackfillRequest,
    DailyNote,
    Screenshot,
    ScreenshotRead,
    Tag,
    TagRead,
    Trade,
    TradeCloseRequest,
    TradeOpenRequest,
    TradePatch,
    TradeRead,
    TradeTagLink,
    TradeTSLRequest,
)
from app.services.migrate_csv import (
    compute_r_multiple,
    estimate_gross_pnl,
    get_or_create_tag,
    normalize_tag_list,
    parse_tags,
)
from app.services.session_resolver import duration_minutes, normalize_session

router = APIRouter(prefix="/api/trades", tags=["trades"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def to_trade_read(trade: Trade) -> TradeRead:
    data = trade.model_dump(exclude={"tags", "screenshots"})
    data["trade_id"] = trade.ticket  # deprecated v1 alias
    return TradeRead(
        **data,
        tags=[TagRead.model_validate(t.model_dump()) for t in trade.tags],
        screenshots=[ScreenshotRead.model_validate(s.model_dump()) for s in trade.screenshots],
    )


def _guardrail_status(session: Session) -> dict:
    """Trading-day PnL + open count vs caps (naive-UTC day bounds)."""
    try:
        max_loss = float(os.getenv("MAX_DAILY_LOSS", "-250.0"))
    except ValueError:
        max_loss = -250.0
    try:
        max_trades = int(os.getenv("MAX_DAILY_TRADES", "3"))
    except ValueError:
        max_trades = 3
    today = _now().date()
    # Naive UTC midnight: stored rows mix naive (CSV history) and aware
    # (live) timestamps; plain ISO lexicographic comparison in SQLite
    # classifies both correctly for a day boundary.
    day_start = datetime(today.year, today.month, today.day)
    # Trading-day basis (timestamp_open/close), not created_at — so backfilled
    # history imported today doesn't trip the guardrail.
    todays = session.exec(
        select(Trade).where(Trade.timestamp_open >= day_start)
    ).all()
    daily_pnl = 0.0
    for t in todays:
        if t.status != "CLOSED":
            continue
        closed_at = _as_naive_utc(t.timestamp_close)
        if closed_at is None or closed_at < day_start:
            continue
        daily_pnl += t.net_pnl or 0.0
    return {
        "breached": daily_pnl <= max_loss or len(todays) >= max_trades,
        "daily_pnl": round(daily_pnl, 2),
        "trades": len(todays),
        "max_loss": max_loss,
        "max_trades": max_trades,
    }


def _guardrail_breached(session: Session) -> bool:
    return bool(_guardrail_status(session)["breached"])


def _flag_breach_day(session: Session) -> None:
    today = _now().date()
    note = session.exec(select(DailyNote).where(DailyNote.date == today)).first()
    if note is None:
        note = DailyNote(date=today, discipline_breach=True)
    else:
        note.discipline_breach = True
        note.updated_at = _now()
    session.add(note)


def _as_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _alert_guardrail(text: str) -> None:
    """Best-effort Telegram breach alert (never fails the API call)."""
    try:
        import asyncio

        from app.services import telegram_bot

        if telegram_bot.is_configured():
            asyncio.run(telegram_bot.notify(text))
    except Exception:
        pass


def _generate_ticket(symbol: str) -> str:
    stamp = _now().strftime("%Y%m%dT%H%M%S")
    return f"{(symbol or 'TRADE').upper()}-{stamp}"


@router.post("/open", response_model=TradeRead, status_code=201)
def open_trade(payload: TradeOpenRequest, session: Session = Depends(get_session)):
    direction = payload.direction.lower()
    if direction not in ("buy", "sell"):
        raise HTTPException(status_code=422, detail="direction must be buy or sell")
    if payload.size <= 0:
        raise HTTPException(status_code=422, detail="size must be positive")

    ticket = (payload.ticket or "").strip() or _generate_ticket(payload.symbol)
    if session.exec(select(Trade).where(Trade.ticket == ticket)).first() is not None:
        raise HTTPException(status_code=409, detail=f"ticket already exists: {ticket}")

    opened_at = payload.entry_time or payload.timestamp_open or _now()
    trade = Trade(
        ticket=ticket,
        timestamp_open=opened_at,
        entry_time=opened_at,
        session=normalize_session(payload.session, opened_at),
        direction=direction,
        symbol=payload.symbol.upper(),
        size=payload.size,
        entry_price=payload.entry_price,
        initial_sl=payload.initial_sl,
        current_sl=payload.initial_sl,
        tp=payload.tp,
        fees=0.0,
        status="OPEN",
        thesis=payload.thesis,
    )
    session.add(trade)
    session.flush()

    tag_pairs = normalize_tag_list(payload.tags)
    guard = _guardrail_status(session)
    if guard["breached"]:
        if not any(name == "discipline_breach" for name, _ in tag_pairs):
            tag_pairs.append(("discipline_breach", "mistake"))
        _flag_breach_day(session)
    trade.tags = [get_or_create_tag(session, name, cat) for name, cat in tag_pairs]
    trade.updated_at = _now()
    session.add(trade)
    session.commit()
    session.refresh(trade)
    if guard["breached"]:
        _alert_guardrail(
            f"🚨 GUARDRAIL BREACH on open {trade.ticket}: "
            f"day PnL {guard['daily_pnl']:+.2f} (cap {guard['max_loss']:+.2f}), "
            f"{guard['trades']} trades (cap {guard['max_trades']}). Walk away from the screen!"
        )
    return to_trade_read(trade)


@router.post("/{trade_id}/tsl", response_model=TradeRead)
def update_tsl(trade_id: int, payload: TradeTSLRequest, session: Session = Depends(get_session)):
    trade = session.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade.status != "OPEN":
        raise HTTPException(status_code=422, detail="Only OPEN trades accept TSL updates")
    # initial_sl is immutable — only current_sl moves.
    trade.current_sl = payload.current_sl
    trade.updated_at = _now()
    session.add(trade)
    session.commit()
    session.refresh(trade)
    return to_trade_read(trade)


@router.post("/{trade_id}/close", response_model=TradeRead)
def close_trade(trade_id: int, payload: TradeCloseRequest, session: Session = Depends(get_session)):
    trade = session.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade.status == "CLOSED":
        raise HTTPException(status_code=422, detail="Trade is already closed")

    fees = payload.fees if payload.fees is not None else (trade.fees or 0.0)
    if payload.gross_pnl is not None:
        gross = payload.gross_pnl
    else:
        # Fallback when the client omits gross: price-based estimate for known
        # symbols (FX 100k, GOLD 100, BTC 1, USDJPY converted at exit). Keeps
        # None for unknown symbols instead of guessing — net then stays null
        # only when no deterministic value exists.
        gross = estimate_gross_pnl(
            trade.direction, trade.symbol, trade.size, trade.entry_price, payload.exit_price
        )
        if gross is None:
            gross = trade.gross_pnl
    net = (gross - (fees or 0.0)) if gross is not None else None
    r = compute_r_multiple(trade.direction, trade.entry_price, trade.initial_sl, payload.exit_price)

    trade.exit_price = payload.exit_price
    trade.gross_pnl = gross
    trade.fees = fees or 0.0
    trade.net_pnl = net
    trade.r_multiple = r
    closed_at = payload.timestamp_close or _now()
    trade.timestamp_close = closed_at
    trade.exit_time = closed_at
    trade.duration_minutes = duration_minutes(
        trade.entry_time or trade.timestamp_open, closed_at
    )
    if not trade.session:
        trade.session = normalize_session(None, trade.entry_time or trade.timestamp_open)
    trade.status = "CLOSED"
    trade.updated_at = _now()
    if payload.review_notes is not None:
        trade.review_notes = payload.review_notes
    if payload.mistake_tags:
        existing = {(t.name, t.category) for t in trade.tags}
        for name, _cat in normalize_tag_list(payload.mistake_tags):
            # Force close-flow tags into the mistake category.
            pair = (name, "mistake")
            if pair not in existing:
                trade.tags.append(get_or_create_tag(session, name, "mistake"))
                existing.add(pair)
    session.add(trade)
    session.flush()
    guard = _guardrail_status(session)
    if guard["breached"]:
        _flag_breach_day(session)
    session.commit()
    session.refresh(trade)
    if guard["breached"]:
        _alert_guardrail(
            f"🚨 GUARDRAIL BREACH on close {trade.ticket}: "
            f"day PnL {guard['daily_pnl']:+.2f} (cap {guard['max_loss']:+.2f}), "
            f"{guard['trades']} trades (cap {guard['max_trades']}). Walk away from the screen!"
        )
    return to_trade_read(trade)


@router.post("/backfill")
def backfill_trades(
    body: Union[BackfillRecord, BackfillRequest], session: Session = Depends(get_session)
):
    """Ingest single or batch historical records with explicit timestamps.

    Sessions and durations resolve automatically; screenshot uploads to these
    trades route to the matching historical "YYYY-MM Trades" Immich album
    via their entry timestamps.
    """
    records = body.records if isinstance(body, BackfillRequest) else [body]
    if not records:
        raise HTTPException(status_code=422, detail="No records provided")
    if len(records) > 500:
        raise HTTPException(status_code=422, detail="Batch limit is 500 records")

    inserted: list[str] = []
    skipped: list[str] = []
    for rec in records:
        ticket, created = insert_backfill_record(session, rec)
        (inserted if created else skipped).append(ticket)

    session.commit()
    total = len(session.exec(select(Trade)).all())
    return {"inserted": inserted, "skipped": skipped, "total": total}


def insert_backfill_record(session: Session, rec: BackfillRecord) -> tuple[str, bool]:
    """Insert one historical CLOSED trade. Returns (ticket, created)."""
    direction = (rec.direction or "").lower()
    if direction not in ("buy", "sell"):
        raise HTTPException(status_code=422, detail=f"Bad direction: {rec.direction!r}")
    if rec.size <= 0:
        raise HTTPException(status_code=422, detail="size must be positive")
    if rec.exit_time < rec.entry_time:
        raise HTTPException(status_code=422, detail="exit_time precedes entry_time")

    ticket = (rec.ticket or "").strip() or _backfill_ticket(session, rec.symbol, rec.entry_time)
    if session.exec(select(Trade).where(Trade.ticket == ticket)).first() is not None:
        return ticket, False

    fees = rec.fees if rec.fees is not None else 0.0
    gross = rec.gross_pnl
    net = rec.net_pnl if rec.net_pnl is not None else (
        (gross - (fees or 0.0)) if gross is not None else None
    )
    r = rec.r_multiple if rec.r_multiple is not None else compute_r_multiple(
        direction, rec.entry_price, rec.initial_sl, rec.exit_price
    )
    trade = Trade(
        ticket=ticket,
        timestamp_open=rec.entry_time,
        timestamp_close=rec.exit_time,
        entry_time=rec.entry_time,
        exit_time=rec.exit_time,
        duration_minutes=duration_minutes(rec.entry_time, rec.exit_time),
        session=normalize_session(rec.session, rec.entry_time),
        direction=direction,
        symbol=rec.symbol.upper(),
        size=rec.size,
        entry_price=rec.entry_price,
        initial_sl=rec.initial_sl,
        current_sl=rec.initial_sl,
        tp=rec.tp,
        exit_price=rec.exit_price,
        gross_pnl=gross,
        fees=fees or 0.0,
        net_pnl=net,
        r_multiple=r,
        status="CLOSED",
        thesis=rec.thesis,
        review_notes=rec.review_notes,
    )
    session.add(trade)
    session.flush()
    trade.tags = [
        get_or_create_tag(session, name, cat) for name, cat in normalize_tag_list(rec.tags)
    ]
    session.add(trade)
    return ticket, True


def _backfill_ticket(session: Session, symbol: str, entry: datetime) -> str:
    """Unique ticket from symbol + entry stamp, numeric suffix on clash."""
    base = f"{(symbol or 'TRADE').upper()}-{entry.strftime('%Y%m%dT%H%M')}"
    ticket, n = base, 2
    while session.exec(select(Trade).where(Trade.ticket == ticket)).first() is not None:
        ticket = f"{base}-{n}"
        n += 1
    return ticket


@router.get("")
def list_trades(
    status: Optional[str] = Query(default=None, description="OPEN or CLOSED"),
    symbol: Optional[str] = None,
    tag: Optional[str] = Query(default=None, description="Tag name without #/! prefix"),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = Query(default=1, ge=1),
    # Large default so first-page clients (Trades page, bots) see the full
    # ledger without paginating; total is always the full filtered count
    # independent of page/page_size — clients that need every row should
    # still paginate until items.length == total (see listAllTrades).
    page_size: int = Query(default=500, ge=1, le=5000),
    session: Session = Depends(get_session),
):
    statement = select(Trade).order_by(Trade.created_at.desc())
    if status:
        statement = statement.where(Trade.status == status.upper())
    if symbol:
        statement = statement.where(Trade.symbol == symbol.upper())
    if date_from:
        statement = statement.where(Trade.timestamp_open >= date_from)
    if date_to:
        statement = statement.where(Trade.timestamp_open <= date_to)
    trades = session.exec(statement).all()
    if tag:
        wanted = tag.lower().lstrip("#!")
        trades = [t for t in trades if any(x.name == wanted for x in t.tags)]

    total = len(trades)
    start = (page - 1) * page_size
    items = [to_trade_read(t) for t in trades[start : start + page_size]]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{trade_id}", response_model=TradeRead)
def get_trade(trade_id: int, session: Session = Depends(get_session)):
    trade = session.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    return to_trade_read(trade)


@router.patch("/{trade_id}", response_model=TradeRead)
def patch_trade(trade_id: int, patch: TradePatch, session: Session = Depends(get_session)):
    trade = session.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    data = patch.model_dump(exclude_unset=True, exclude={"tags"})
    data.pop("ticket", None)
    if "status" in data and data["status"]:
        data["status"] = data["status"].upper()
    for key, value in data.items():
        setattr(trade, key, value)
    if patch.tags is not None:
        trade.tags = [
            get_or_create_tag(session, name, category)
            for name, category in parse_tags(" ".join(patch.tags))
        ]
    # Keep r_multiple consistent: recompute when price legs change unless the
    # caller explicitly supplied r_multiple in the same patch.
    if "r_multiple" not in data and any(
        k in data for k in ("exit_price", "entry_price", "initial_sl", "direction")
    ):
        trade.r_multiple = compute_r_multiple(
            trade.direction, trade.entry_price, trade.initial_sl, trade.exit_price
        )
        session.add(trade)
    trade.updated_at = _now()
    session.add(trade)
    session.commit()
    session.refresh(trade)
    return to_trade_read(trade)


@router.delete("/{trade_id}")
def delete_trade(
    trade_id: int,
    delete_assets: bool = Query(default=False, description="Also delete Immich assets"),
    session: Session = Depends(get_session),
):
    trade = session.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    asset_ids = [s.immich_asset_id for s in trade.screenshots]
    session.exec(delete(TradeTagLink).where(TradeTagLink.trade_id == trade_id))
    session.exec(delete(Screenshot).where(Screenshot.trade_id == trade_id))
    session.delete(trade)
    session.commit()
    if delete_assets and asset_ids:
        # Best-effort: don't fail the delete if Immich is unreachable.
        try:
            import asyncio

            from app.services import immich_client

            asyncio.run(immich_client.delete_assets(asset_ids))
        except Exception:
            pass
    return {"deleted": trade_id}
