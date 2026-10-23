"""Unified trade lifecycle API (PLAN-v2 Task 1.3).

Live ingestion is the Telegram client (Phase 2) + web modals (Phase 5)
calling these endpoints. The v1 CSV sync endpoint is removed; history
imports go through app.services.migrate_csv (one-shot).
"""

import csv
import io
import json
import os
from datetime import datetime, timezone
from typing import Optional, Union

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlmodel import Session, delete, select

from app.database import get_session
from app.models import (
    BackfillRecord,
    BackfillRequest,
    DailyNote,
    ImportRun,
    RepairRequest,
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
    get_or_create_tag,
    normalize_tag_list,
    parse_tags,
)
from app.services.session_resolver import duration_minutes, normalize_session
from app.services.symbol_registry import (
    apply_trade_risk,
    compute_r_multiple,
    estimate_gross_quote_pnl,
)
from app.services.timeutils import as_naive_utc
from app.services.trading_day import get_trading_day
from app.services.trade_filters import (
    TradeFilters,
    apply_trade_filters,
    filtered_count,
    sort_trades,
)
from app.services.trade_money import (
    fx_missing,
    quote_currency_for,
    set_trade_pnl,
    sync_trade_currency,
    sync_trade_usd,
    usd_net,
)

router = APIRouter(prefix="/api/trades", tags=["trades"])

# The export writes every filtered row; the cap keeps a runaway filter from
# filling the machine's memory.
EXPORT_LIMIT = 50_000

# A broker statement is a few hundred kilobytes; anything past this is not
# a statement and should not be parsed into memory.
MAX_STATEMENT_BYTES = 10 * 1024 * 1024


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Back-compat alias — single source is app.services.timeutils.as_naive_utc."""
    return as_naive_utc(dt)


def to_trade_read(trade: Trade) -> TradeRead:
    data = trade.model_dump(exclude={"tags", "screenshots"})
    data["trade_id"] = trade.ticket  # deprecated v1 alias
    data["fx_missing"] = fx_missing(trade)
    return TradeRead(
        **data,
        tags=[TagRead.model_validate(t.model_dump()) for t in trade.tags],
        screenshots=[ScreenshotRead.model_validate(s.model_dump()) for s in trade.screenshots],
    )


def _guardrail_status(session: Session) -> dict:
    """Trading-day PnL + open count vs caps (configured day boundary)."""
    try:
        max_loss = float(os.getenv("MAX_DAILY_LOSS", "-250.0"))
    except ValueError:
        max_loss = -250.0
    try:
        max_trades = int(os.getenv("MAX_DAILY_TRADES", "3"))
    except ValueError:
        max_trades = 3
    # The same boundary as the calendar and the daily stats: a 23:30 UTC
    # close is tomorrow in Kolkata, and the guardrail counts it there.
    # Stored rows mix naive (CSV history) and aware (live) timestamps; the
    # bounds are naive UTC and ISO lexicographic comparison in SQLite
    # classifies both correctly for a day boundary.
    setting = get_trading_day(session)
    today = setting.day_of(_now().replace(tzinfo=None))
    day_start, day_end = setting.bounds(today)
    # Trading-day basis (timestamp_open/close), not created_at — so backfilled
    # history imported today doesn't trip the guardrail.
    todays = session.exec(
        select(Trade).where(
            Trade.timestamp_open >= day_start,
            Trade.timestamp_open < day_end,
        )
    ).all()
    daily_pnl = 0.0
    for t in todays:
        if t.status != "CLOSED":
            continue
        closed_at = _as_naive_utc(t.timestamp_close)
        if closed_at is None or closed_at < day_start or closed_at >= day_end:
            continue
        daily_pnl += usd_net(t) or 0.0
    return {
        "breached": daily_pnl <= max_loss or len(todays) >= max_trades,
        "daily_pnl": round(daily_pnl, 2),
        "trades": len(todays),
        "max_loss": max_loss,
        "max_trades": max_trades,
        "day": today.isoformat(),
    }


def _guardrail_breached(session: Session) -> bool:
    return bool(_guardrail_status(session)["breached"])


def _flag_breach_day(session: Session) -> None:
    today = get_trading_day(session).day_of(_now().replace(tzinfo=None))
    note = session.exec(select(DailyNote).where(DailyNote.date == today)).first()
    if note is None:
        note = DailyNote(date=today, discipline_breach=True)
    else:
        note.discipline_breach = True
        note.updated_at = _now()
    session.add(note)


def _alert_guardrail(text: str) -> None:
    """Best-effort Telegram breach alert (never fails the API call)."""
    try:
        import asyncio

        from app.services import telegram_bot

        if telegram_bot.is_configured():
            asyncio.run(telegram_bot.notify(text))
    except Exception:
        pass


def _guardrail_breach_message(guard: dict, ticket: str, action: str) -> str:
    """One wording for every guardrail alert, whatever closed the trade."""
    return (
        f"🚨 GUARDRAIL BREACH on {action} {ticket}: "
        f"day PnL {guard['daily_pnl']:+.2f} (cap {guard['max_loss']:+.2f}), "
        f"{guard['trades']} trades (cap {guard['max_trades']}). Walk away from the screen!"
    )


def _generate_ticket(session: Session, symbol: str) -> str:
    """Unique ticket from symbol + timestamp, numeric suffix on clash.

    The stamp has second precision, so two opens of the same symbol inside
    the same second used to collide on the unique ticket index — the API
    answered 409 and the Telegram bot raised an IntegrityError. Mirrors
    _backfill_ticket.
    """
    base = f"{(symbol or 'TRADE').upper()}-{_now().strftime('%Y%m%dT%H%M%S')}"
    ticket, n = base, 2
    while session.exec(select(Trade).where(Trade.ticket == ticket)).first() is not None:
        ticket = f"{base}-{n}"
        n += 1
    return ticket


def _resolve_account_id(session: Session, account_id: Optional[int]) -> Optional[int]:
    """Validate account_id when supplied; None stays unassigned (legacy rows)."""
    if account_id is None:
        return None
    from app.models import Account

    if session.get(Account, account_id) is None:
        raise HTTPException(status_code=404, detail=f"Account not found: {account_id}")
    return account_id


@router.post("/open", response_model=TradeRead, status_code=201)
def open_trade(payload: TradeOpenRequest, session: Session = Depends(get_session)):
    direction = payload.direction.lower()
    if direction not in ("buy", "sell"):
        raise HTTPException(status_code=422, detail="direction must be buy or sell")
    if payload.size <= 0:
        raise HTTPException(status_code=422, detail="size must be positive")
    account_id = _resolve_account_id(session, payload.account_id)

    ticket = (payload.ticket or "").strip() or _generate_ticket(session, payload.symbol)
    if session.exec(select(Trade).where(Trade.ticket == ticket)).first() is not None:
        raise HTTPException(status_code=409, detail=f"ticket already exists: {ticket}")

    opened_at = as_naive_utc(payload.entry_time or payload.timestamp_open or _now())
    assert opened_at is not None
    trade = Trade(
        ticket=ticket,
        account_id=account_id,
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
        quote_currency=quote_currency_for(session, payload.symbol),
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
    # The plan's risk: the entry-to-stop distance, in dollars.
    apply_trade_risk(session, trade)
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
    # Moving the stop changes the risk actually carried.
    apply_trade_risk(session, trade)
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
        # Price the trade in its quote currency (yen for USDJPY, dollars
        # for EURUSD); the USD view is derived at the close-day FX rate.
        gross = estimate_gross_quote_pnl(
            session, trade.direction, trade.symbol, trade.size, trade.entry_price, payload.exit_price
        )
        if gross is None:
            gross = trade.gross_pnl
    r = compute_r_multiple(
        trade.direction, trade.entry_price, trade.initial_sl, trade.current_sl, payload.exit_price
    )

    trade.exit_price = payload.exit_price
    trade.r_multiple = r
    closed_at = as_naive_utc(payload.timestamp_close or _now())
    assert closed_at is not None
    trade.timestamp_close = closed_at
    trade.exit_time = closed_at
    trade.duration_minutes = duration_minutes(
        trade.entry_time or trade.timestamp_open, closed_at
    )
    if not trade.session:
        trade.session = normalize_session(None, trade.entry_time or trade.timestamp_open)
    # Quote-currency P&L and its USD equivalent, written together.
    set_trade_pnl(session, trade, gross, fees)
    # Final risk: the stop the trade was actually carried to.
    apply_trade_risk(session, trade)
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
        _alert_guardrail(_guardrail_breach_message(guard, trade.ticket, "close"))
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
    account_id = _resolve_account_id(session, rec.account_id)

    fees = rec.fees if rec.fees is not None else 0.0
    gross = rec.gross_pnl
    net = rec.net_pnl
    if gross is None and net is None:
        # The trader gave no P&L at all: price the trade in its quote
        # currency from the symbol registry. A history row with no net is
        # an unpriced trade, and an unpriced trade silently scores as a
        # scratch.
        gross = estimate_gross_quote_pnl(
            session, direction, rec.symbol, rec.size, rec.entry_price, rec.exit_price
        )
    if net is None:
        net = (gross - (fees or 0.0)) if gross is not None else None
    elif gross is None:
        # The trader reported a net but no gross: recover the gross so the
        # row keeps the net = gross - fees invariant.
        gross = net + (fees or 0.0)
    r = rec.r_multiple if rec.r_multiple is not None else compute_r_multiple(
        direction, rec.entry_price, rec.initial_sl, rec.initial_sl, rec.exit_price
    )
    trade = Trade(
        ticket=ticket,
        account_id=account_id,
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
        fees=fees or 0.0,
        quote_currency=quote_currency_for(session, rec.symbol),
        r_multiple=r,
        status="CLOSED",
        thesis=rec.thesis,
        review_notes=rec.review_notes,
    )
    session.add(trade)
    session.flush()
    # Quote-currency P&L and its USD equivalent at the close-day rate.
    set_trade_pnl(session, trade, gross, fees)
    trade.tags = [
        get_or_create_tag(session, name, cat) for name, cat in normalize_tag_list(rec.tags)
    ]
    apply_trade_risk(session, trade)
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


# --- MT5 statement import (Phase 8) ---------------------------------------


def _import_detail(result: Optional[dict], warnings: Optional[list[str]] = None) -> str:
    """Capped JSON payload for the run log — warnings plus per-ticket actions.

    The list is trimmed rather than the string, so the stored detail is
    always valid JSON however large the statement was.
    """
    details = list((result or {}).get("details") or [])
    payload = {
        "warnings": list(warnings or []),
        "details": details[:200],
        "details_total": len(details),
    }
    return json.dumps(payload, default=str)


def _record_import_run(
    session: Session,
    *,
    filename: str,
    format: Optional[str],
    account_id: Optional[int],
    result: Optional[dict] = None,
    warnings: Optional[list[str]] = None,
    rows: int = 0,
    error: Optional[str] = None,
) -> ImportRun:
    """Store one import attempt. A failed file is logged with the same care."""
    counts = (result or {}).get("counts") or {}
    run = ImportRun(
        kind="mt5",
        filename=(filename or "statement")[:255],
        format=format,
        account_id=account_id,
        rows=int(counts.get("rows", rows) or 0),
        added=int(counts.get("added", 0) or 0),
        updated=int(counts.get("updated", 0) or 0),
        unchanged=int(counts.get("unchanged", 0) or 0),
        skipped=int(counts.get("skipped", 0) or 0),
        error=error,
        detail=_import_detail(result, warnings),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _load_import_detail(raw: str) -> dict:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


@router.post("/import/mt5")
async def import_mt5_statement(
    file: UploadFile = File(..., description="MT5 HTML report or CSV export"),
    account_id: Optional[int] = Form(default=None, description="Account to file new trades under"),
    session: Session = Depends(get_session),
):
    """Import a broker statement, keyed by ticket.

    The account comes from the form when chosen, otherwise from the login
    printed in the HTML report (matched against ``Account.login``). A row
    whose ticket already exists is reconciled in place: the broker fields
    are refreshed, the trader's notes and tags are kept, and a row that
    already matches changes nothing. Re-importing the same file is a no-op.

    Every attempt lands in ``import_run`` — including a file that cannot
    be parsed — so a bad statement is diagnosable after the toast is gone.
    """
    from app.services.mt5_import import (
        StatementError,
        decode_statement,
        import_rows,
        parse_statement,
        resolve_account_id,
    )

    if account_id is not None:
        _resolve_account_id(session, account_id)

    filename = file.filename or "statement"
    raw = await file.read(MAX_STATEMENT_BYTES + 1)
    if len(raw) > MAX_STATEMENT_BYTES:
        message = "Statement exceeds the 10 MB limit"
        _record_import_run(
            session,
            filename=filename,
            format=None,
            account_id=account_id,
            error=message,
        )
        raise HTTPException(status_code=413, detail=message)

    try:
        parsed = parse_statement(decode_statement(raw), filename)
    except StatementError as exc:
        _record_import_run(
            session,
            filename=filename,
            format=None,
            account_id=account_id,
            error=str(exc),
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    target_account = resolve_account_id(session, account_id, parsed.account_login)
    result = import_rows(
        session,
        parsed.rows,
        account_id=target_account,
        update_existing=True,
    )
    run = _record_import_run(
        session,
        filename=filename,
        format=parsed.format,
        account_id=target_account,
        result=result,
        warnings=parsed.warnings,
        rows=len(parsed.rows),
    )
    return {
        "run_id": run.id,
        "filename": filename,
        "format": parsed.format,
        "account_id": target_account,
        "account_login": parsed.account_login,
        "warnings": parsed.warnings,
        **result,
    }


@router.get("/imports")
def list_import_runs(
    limit: int = Query(default=20, ge=1, le=100, description="Most recent runs to return"),
    session: Session = Depends(get_session),
):
    """The import run log, newest first — what each file did, and why it failed."""
    runs = session.exec(
        select(ImportRun)
        .order_by(ImportRun.created_at.desc(), ImportRun.id.desc())
        .limit(limit)
    ).all()
    return {
        "runs": [
            {
                "id": run.id,
                "kind": run.kind,
                "filename": run.filename,
                "format": run.format,
                "account_id": run.account_id,
                "rows": run.rows,
                "added": run.added,
                "updated": run.updated,
                "unchanged": run.unchanged,
                "skipped": run.skipped,
                "error": run.error,
                "detail": _load_import_detail(run.detail),
                "created_at": run.created_at,
            }
            for run in runs
        ]
    }


@router.post("/repair/unpriced")
def repair_unpriced(
    body: Optional[RepairRequest] = None,
    session: Session = Depends(get_session),
):
    """Fill a missing gross P&L from the symbol registry.

    Dry-run unless the body says ``{"apply": true}``. A row with no exit
    price is reported as skipped, an unregistered symbol as unpriced, and
    a net the trader supplied is kept exactly (the gross behind it is
    recovered). The repair is idempotent: only rows whose gross is missing
    are considered, so a second run changes nothing.
    """
    from app.services.trade_repair import repair_unpriced_trades

    return repair_unpriced_trades(session, apply=bool(body.apply) if body else False)


def _filters(
    status: Optional[str],
    symbol: Optional[str],
    query: Optional[str],
    tag: Optional[str],
    tag_exact: bool,
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    closed_from: Optional[datetime],
    closed_to: Optional[datetime],
    account_id: Optional[int],
    unassigned: bool,
) -> TradeFilters:
    """The filter state every ledger entry point shares."""
    return TradeFilters(
        status=status,
        symbol=symbol,
        query=query,
        tag=tag,
        tag_exact=tag_exact,
        date_from=date_from,
        date_to=date_to,
        closed_from=closed_from,
        closed_to=closed_to,
        account_id=account_id,
        unassigned=unassigned,
    )


@router.get("")
def list_trades(
    status: Optional[str] = Query(default=None, description="OPEN or CLOSED"),
    symbol: Optional[str] = None,
    query: Optional[str] = Query(default=None, alias="q", description="Free text: symbol or ticket"),
    tag: Optional[str] = Query(default=None, description="Tag name without #/! prefix"),
    tag_exact: bool = Query(default=False, description="Match the tag name exactly"),
    date_from: Optional[datetime] = Query(default=None, description="Open-day lower bound"),
    date_to: Optional[datetime] = Query(default=None, description="Open-day upper bound"),
    closed_from: Optional[datetime] = Query(default=None, description="Close-day lower bound"),
    closed_to: Optional[datetime] = Query(default=None, description="Close-day upper bound"),
    account_id: Optional[int] = Query(default=None, description="Filter to one account"),
    unassigned: bool = Query(default=False, description="Only trades with no account"),
    sort: Optional[str] = Query(default=None, description="newest | oldest | net-desc | net-asc | r-desc"),
    page: int = Query(default=1, ge=1),
    # Large default so first-page clients (Trades page, bots) see the full
    # ledger without paginating; total is always the full filtered count
    # independent of page/page_size — clients that need every row should
    # still paginate until items.length === total (see listAllTrades).
    page_size: int = Query(default=500, ge=1, le=5000),
    session: Session = Depends(get_session),
):
    """The ledger, filtered and counted on the server.

    ``total`` is the number of rows the filter matches, not the size of the
    page. ``counts`` holds the same count per status tab, computed without
    the status filter, so the tabs can show what each one would return.
    """
    filters = _filters(
        status,
        symbol,
        query,
        tag,
        tag_exact,
        date_from,
        date_to,
        closed_from,
        closed_to,
        account_id,
        unassigned,
    )
    base = filters.without_status()
    counts = {
        "ALL": filtered_count(session, base),
        "OPEN": filtered_count(session, base.with_status("OPEN")),
        "CLOSED": filtered_count(session, base.with_status("CLOSED")),
    }
    total = filtered_count(session, filters)

    statement = sort_trades(apply_trade_filters(select(Trade), filters), sort)
    start = (page - 1) * page_size
    trades = session.exec(statement.offset(start).limit(page_size)).all()
    return {
        "items": [to_trade_read(t) for t in trades],
        "total": total,
        "page": page,
        "page_size": page_size,
        "counts": counts,
    }


@router.get("/ids")
def list_trade_ids(
    status: Optional[str] = Query(default=None, description="OPEN or CLOSED"),
    symbol: Optional[str] = None,
    query: Optional[str] = Query(default=None, alias="q", description="Free text: symbol or ticket"),
    tag: Optional[str] = Query(default=None, description="Tag name without #/! prefix"),
    tag_exact: bool = Query(default=False, description="Match the tag name exactly"),
    date_from: Optional[datetime] = Query(default=None, description="Open-day lower bound"),
    date_to: Optional[datetime] = Query(default=None, description="Open-day upper bound"),
    closed_from: Optional[datetime] = Query(default=None, description="Close-day lower bound"),
    closed_to: Optional[datetime] = Query(default=None, description="Close-day upper bound"),
    account_id: Optional[int] = Query(default=None, description="Filter to one account"),
    unassigned: bool = Query(default=False, description="Only trades with no account"),
    sort: Optional[str] = Query(default=None, description="newest | oldest | net-desc | net-asc | r-desc"),
    session: Session = Depends(get_session),
):
    """The ids of every trade the filter matches — the bulk move's work list.

    The ledger shows one page, so "move everything on screen" cannot mean
    "move the rows this page holds". This answers the question the move
    button actually asks: which trades match the filter right now?
    """
    filters = _filters(
        status,
        symbol,
        query,
        tag,
        tag_exact,
        date_from,
        date_to,
        closed_from,
        closed_to,
        account_id,
        unassigned,
    )
    statement = sort_trades(apply_trade_filters(select(Trade.id), filters), sort)
    ids = [int(row) for row in session.exec(statement).all()]
    return {"ids": ids, "total": len(ids)}


@router.get("/export")
def export_trades(
    status: Optional[str] = Query(default=None, description="OPEN or CLOSED"),
    symbol: Optional[str] = None,
    query: Optional[str] = Query(default=None, alias="q", description="Free text: symbol or ticket"),
    tag: Optional[str] = Query(default=None, description="Tag name without #/! prefix"),
    tag_exact: bool = Query(default=False, description="Match the tag name exactly"),
    date_from: Optional[datetime] = Query(default=None, description="Open-day lower bound"),
    date_to: Optional[datetime] = Query(default=None, description="Open-day upper bound"),
    closed_from: Optional[datetime] = Query(default=None, description="Close-day lower bound"),
    closed_to: Optional[datetime] = Query(default=None, description="Close-day upper bound"),
    account_id: Optional[int] = Query(default=None, description="Filter to one account"),
    unassigned: bool = Query(default=False, description="Only trades with no account"),
    sort: Optional[str] = Query(default=None, description="newest | oldest | net-desc | net-asc | r-desc"),
    session: Session = Depends(get_session),
):
    """The filtered ledger as a CSV file.

    The export is the same query as the table, without the page: what the
    screen shows is what the file holds. Both the quote-currency amount and
    its USD conversion are written, so the file can be read without the
    rate that produced it.
    """
    from app.models import Account

    filters = _filters(
        status,
        symbol,
        query,
        tag,
        tag_exact,
        date_from,
        date_to,
        closed_from,
        closed_to,
        account_id,
        unassigned,
    )
    statement = sort_trades(apply_trade_filters(select(Trade), filters), sort)
    trades = session.exec(statement.limit(EXPORT_LIMIT)).all()
    aliases = {a.id: a.alias for a in session.exec(select(Account)).all()}

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "ticket",
            "status",
            "symbol",
            "direction",
            "size",
            "opened",
            "closed",
            "entry",
            "exit",
            "fees",
            "quote_currency",
            "net_quote",
            "net_usd",
            "r_multiple",
            "account",
            "tags",
        ]
    )
    for t in trades:
        writer.writerow(
            [
                t.ticket,
                t.status,
                t.symbol,
                t.direction,
                t.size,
                t.timestamp_open,
                t.timestamp_close,
                t.entry_price,
                t.exit_price,
                t.fees,
                t.quote_currency,
                t.net_pnl,
                usd_net(t),
                t.r_multiple,
                aliases.get(t.account_id, "") if t.account_id else "",
                ",".join(tag.name for tag in t.tags),
            ]
        )
    filename = f"trades-{_now().strftime('%Y-%m-%d')}.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    orig_status = (trade.status or "OPEN").upper()
    data = patch.model_dump(exclude_unset=True, exclude={"tags"})
    data.pop("ticket", None)
    if "account_id" in data:
        _resolve_account_id(session, data["account_id"])
    if "status" in data and data["status"]:
        data["status"] = data["status"].upper()
    for key, value in data.items():
        setattr(trade, key, value)
    # A symbol change also changes the currency the P&L is quoted in. Only
    # an explicit quote_currency in the same patch overrides it.
    if "symbol" in data and "quote_currency" not in data:
        sync_trade_currency(session, trade, force=True)
    if patch.tags is not None:
        trade.tags = [
            get_or_create_tag(session, name, category)
            for name, category in parse_tags(" ".join(patch.tags))
        ]
    # Entry/exit timestamps are mirrored pairs (live + backfill flows keep
    # timestamp_open/entry_time and timestamp_close/exit_time in sync).
    if "entry_time" in data and "timestamp_open" not in data:
        trade.timestamp_open = trade.entry_time
        session.add(trade)
    elif "timestamp_open" in data and "entry_time" not in data:
        trade.entry_time = trade.timestamp_open
        session.add(trade)
    if "exit_time" in data and "timestamp_close" not in data:
        trade.timestamp_close = trade.exit_time
        session.add(trade)
    elif "timestamp_close" in data and "exit_time" not in data:
        trade.exit_time = trade.timestamp_close
        session.add(trade)
    # Keep duration/session consistent when either leg moves: duration from
    # the entry/exit pair, session re-resolved from the entry time.
    if any(k in data for k in ("entry_time", "timestamp_open", "exit_time", "timestamp_close")):
        entry = trade.entry_time or trade.timestamp_open
        trade.duration_minutes = duration_minutes(entry, trade.exit_time or trade.timestamp_close)
        if any(k in data for k in ("entry_time", "timestamp_open")):
            trade.session = normalize_session(None, entry)
        session.add(trade)
    # Keep r_multiple consistent: recompute when price legs change unless the
    # caller explicitly supplied r_multiple in the same patch.
    if "r_multiple" not in data and any(
        k in data for k in ("exit_price", "entry_price", "initial_sl", "direction")
    ):
        trade.r_multiple = compute_r_multiple(
            trade.direction, trade.entry_price, trade.initial_sl, trade.current_sl, trade.exit_price
        )
        session.add(trade)
    # The risk follows the price legs: a new entry, stop or size changes the
    # dollars at risk, so the recorded risk has to move with them.
    if any(
        k in data for k in ("symbol", "size", "entry_price", "initial_sl", "current_sl")
    ):
        apply_trade_risk(session, trade)
        session.add(trade)
    # Keep gross/net consistent: re-estimate gross when price legs change
    # unless the caller explicitly supplied gross_pnl; net follows from
    # gross minus fees unless net_pnl was explicitly supplied.
    if "gross_pnl" not in data and any(
        k in data for k in ("direction", "symbol", "size", "entry_price", "exit_price")
    ):
        estimated = estimate_gross_quote_pnl(
            session, trade.direction, trade.symbol, trade.size, trade.entry_price, trade.exit_price
        )
        if estimated is not None:
            trade.gross_pnl = estimated
            session.add(trade)
    if "net_pnl" not in data and any(
        k in data
        for k in ("direction", "symbol", "size", "entry_price", "exit_price", "gross_pnl", "fees")
    ):
        if trade.gross_pnl is not None:
            trade.net_pnl = trade.gross_pnl - (trade.fees or 0.0)
            session.add(trade)
    # Auto-close: saving exit details on an OPEN trade closes it — no extra
    # manual close step. Triggers when exit_price is present (explicitly in
    # this patch or already stored) and the patch does not ask to keep the
    # trade open.
    #
    # A client that also sends status="CLOSED" must still get the full close
    # record. Skipping the fill left the trade CLOSED with a null
    # timestamp_close, so it vanished from /stats_daily and the EOD recap and
    # was bucketed into the calendar by its open day.
    keep_open = "status" in data and (trade.status or "").upper() == "OPEN"
    closed_now = False
    if orig_status == "OPEN" and trade.exit_price is not None and not keep_open:
        closed_now = True
        trade.status = "CLOSED"
        if not (trade.exit_time or trade.timestamp_close):
            now_naive = as_naive_utc(_now())
            assert now_naive is not None
            trade.exit_time = now_naive
            trade.timestamp_close = now_naive
        elif trade.exit_time and not trade.timestamp_close:
            trade.timestamp_close = trade.exit_time
        elif trade.timestamp_close and not trade.exit_time:
            trade.exit_time = trade.timestamp_close
        entry = trade.entry_time or trade.timestamp_open
        trade.duration_minutes = duration_minutes(entry, trade.exit_time or trade.timestamp_close)
        if not trade.session:
            trade.session = normalize_session(None, entry)
        # Ensure gross/net exist on the auto-close path (e.g. only exit_time
        # was added while exit_price was already stored).
        if trade.gross_pnl is None:
            estimated = estimate_gross_quote_pnl(
                session, trade.direction, trade.symbol, trade.size, trade.entry_price, trade.exit_price
            )
            if estimated is not None:
                trade.gross_pnl = estimated
        if trade.net_pnl is None and trade.gross_pnl is not None:
            trade.net_pnl = trade.gross_pnl - (trade.fees or 0.0)
        if trade.r_multiple is None:
            trade.r_multiple = compute_r_multiple(
                trade.direction, trade.entry_price, trade.initial_sl, trade.current_sl, trade.exit_price
            )
        session.add(trade)
    trade.updated_at = _now()
    # The USD view follows every edit: a fee, a leg, a close timestamp, the
    # quote currency or the symbol itself all change the conversion.
    sync_trade_usd(session, trade)
    session.add(trade)
    # Closing from the web drawer is a close like any other: the daily loss
    # and trade-count guardrails have to run here too, or a breach raised in
    # the browser never raises the alert and never flags the day note.
    guard: Optional[dict] = None
    if closed_now:
        session.flush()
        guard = _guardrail_status(session)
        if guard["breached"]:
            _flag_breach_day(session)
    session.commit()
    session.refresh(trade)
    if guard and guard["breached"]:
        _alert_guardrail(_guardrail_breach_message(guard, trade.ticket, "close"))
    return to_trade_read(trade)


@router.post("/bulk-account")
def bulk_assign_account(
    payload: dict, session: Session = Depends(get_session)
):
    """Move many trades to one account (or back to unassigned with null).

    Body: {"trade_ids": [1, 2], "account_id": 3 | null}

    The answer names the ids it could not move as well as the ones it did:
    a trade that no longer exists must not disappear silently. The batch
    limit stays at 500 — a larger move is the caller's job to split.
    """
    ids = payload.get("trade_ids") or []
    account_id = payload.get("account_id")
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=422, detail="trade_ids must be a non-empty list")
    if len(ids) > 500:
        raise HTTPException(status_code=422, detail="Batch limit is 500 trades")
    _resolve_account_id(session, account_id)
    updated = 0
    skipped: list[object] = []
    for tid in ids:
        try:
            tid_int = int(tid)
        except (TypeError, ValueError):
            skipped.append(tid)
            continue
        trade = session.get(Trade, tid_int)
        if trade is None:
            skipped.append(tid_int)
            continue
        trade.account_id = account_id
        trade.updated_at = _now()
        session.add(trade)
        updated += 1
    session.commit()
    return {"updated": updated, "skipped": skipped, "requested": len(ids)}


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
