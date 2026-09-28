"""Integrated Telegram bot client (PLAN-v2 Tasks 2.1–2.3).

Long-polls the Bot API with httpx inside the FastAPI lifespan (see
app.main). Only updates from TG_ALLOWED_USER_ID are honored.

Text syntax:
    Open:  buy gold, 0.1, 4000, 3990, 4020, #fvg
    TSL:   tsl gold, 4005
    Close: close gold, 4015, +150, fee: 3.5, !early, notes
Commands: /start, /help, /open, /stats_daily, /cancel.

Photos are downloaded via getFile and streamed straight into
immich_client (never touch local disk), then recorded in screenshots.
"""

import asyncio
import html
import logging
import os
import re
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from sqlmodel import Session, select

from app.models import Screenshot, Trade
from app.services.timeutils import as_naive_utc

log = logging.getLogger("telegram_bot")


def esc(value: Any) -> str:
    """Escape user/exception-derived text for HTML parse_mode messages."""
    return html.escape(str(value), quote=False)

API_BASE = "https://api.telegram.org"
FILE_BASE = "https://api.telegram.org/file"

# Pending interactive states per chat: {"action": "tsl"|"close"|"photo",
# "trade_id": int} or {"action": "photo_pick", "file_id": str}.
_pending: dict[int, dict] = {}
# Stale-alert snoozes from inline buttons (Phase 3 scheduler honors these).
_snoozed_until: dict[int, datetime] = {}


class BotParseError(ValueError):
    pass


def is_configured() -> bool:
    return bool(os.getenv("TG_BOT_TOKEN", "").strip())


def _token() -> str:
    token = os.getenv("TG_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TG_BOT_TOKEN is not configured")
    return token


def _allowed_user() -> Optional[str]:
    uid = os.getenv("TG_ALLOWED_USER_ID", "").strip()
    return uid or None


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Pure parsers (unit-testable, no I/O) ---


def _split_args(body: str) -> list[str]:
    return [p.strip() for p in body.split(",")]


def _to_float(token: str, what: str) -> float:
    try:
        return float(token.strip().lstrip("+"))
    except ValueError:
        raise BotParseError(f"Bad {what}: <code>{esc(token.strip())}</code>") from None


def _parse_explicit_time(tail: str) -> tuple[Optional[datetime], str]:
    """Pull an optional `time: HH:MM` / `time: YYYY-MM-DD HH:MM` flag from tail.

    Returns (entry_time or None, tail with the flag removed).
    """
    m = re.search(
        r"time\s*:\s*(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}|\d{1,2}:\d{2})", tail, re.IGNORECASE
    )
    if not m:
        return None, tail
    raw = m.group(1).strip()
    try:
        if re.match(r"^\d{4}-", raw):
            entry = datetime.strptime(raw, "%Y-%m-%d %H:%M")
        else:
            hh, mm = raw.split(":")
            now = datetime.now(timezone.utc)
            entry = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0,
                                tzinfo=None)
    except ValueError:
        raise BotParseError(f"Bad time value: <code>{esc(raw)}</code> (use HH:MM or YYYY-MM-DD HH:MM)")
    if not (0 <= entry.hour <= 23 and 0 <= entry.minute <= 59):
        raise BotParseError(f"Bad time value: <code>{esc(raw)}</code>")
    return entry, (tail[: m.start()] + tail[m.end():]).strip(" ,")


def parse_open(text: str) -> dict:
    """`buy gold, 0.1, 4000, 3990, 4020, #fvg ...` (+ optional `time:` flag)."""
    m = re.match(r"(?i)^\s*(buy|sell)\s+([a-z0-9\-/.]+)\s*,(.*)$", text.strip(), re.DOTALL)
    if not m:
        raise BotParseError("Open syntax: <code>buy SYMBOL, SIZE, ENTRY, SL, [TP], [#tags]</code>")
    direction, symbol, rest = m.group(1).lower(), m.group(2).upper(), m.group(3)
    entry_time, rest = _parse_explicit_time(rest)
    parts = _split_args(rest)
    if len(parts) < 3:
        raise BotParseError("Open needs at least SIZE, ENTRY and SL")
    size = _to_float(parts[0], "size")
    entry = _to_float(parts[1], "entry")
    sl = _to_float(parts[2], "SL")
    tp: Optional[float] = None
    tag_start = 3
    if len(parts) > 3 and not re.match(r"^[#!]", parts[3].strip()) and re.match(
        r"^[+-]?[\d.]+$", parts[3].strip()
    ):
        tp = _to_float(parts[3], "TP")
        tag_start += 1
    tail = " ".join(parts[tag_start:])
    return {
        "direction": direction,
        "symbol": symbol,
        "size": size,
        "entry_price": entry,
        "initial_sl": sl,
        "tp": tp,
        "entry_time": entry_time,
        "tags": tail.split() if tail else [],
        "thesis": None,
    }


def parse_past(text: str) -> dict:
    """`past buy gold, 0.1, 4000, 3990, 4020, exit: 4015, pnl: 150, date: 2026-09-20 14:30`."""
    m = re.match(r"(?i)^\s*past\s+(buy|sell)\s+([a-z0-9\-/.]+)\s*,(.*)$", text.strip(), re.DOTALL)
    if not m:
        raise BotParseError(
            "Backfill syntax: <code>past buy SYMBOL, SIZE, ENTRY, SL, TP, exit: EXIT, pnl: PNL, date: YYYY-MM-DD HH:MM</code>"
        )
    direction, symbol, rest = m.group(1).lower(), m.group(2).upper(), m.group(3)

    def grab(flag: str) -> Optional[str]:
        found = re.search(rf"{flag}\s*:\s*([^\s,][^,]*)", rest, re.IGNORECASE)
        return found.group(1).strip() if found else None

    exit_raw, pnl_raw, date_raw = grab("exit"), grab("pnl"), grab("date")
    fee_raw = grab("fee")
    if exit_raw is None or pnl_raw is None or date_raw is None:
        raise BotParseError("Backfill needs <code>exit:</code>, <code>pnl:</code> and <code>date: YYYY-MM-DD HH:MM</code>")
    try:
        entry_time = datetime.strptime(date_raw.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        raise BotParseError(f"Bad date: <code>{esc(date_raw.strip())}</code> (use YYYY-MM-DD HH:MM)") from None

    cleaned = re.sub(r"(?i)\b(exit|pnl|fee|date)\s*:\s*[^\s,][^,]*", "", rest)
    parts = _split_args(cleaned)
    if len(parts) < 3:
        raise BotParseError("Backfill needs at least SIZE, ENTRY and SL")
    tp: Optional[float] = None
    tag_start = 3
    if len(parts) > 3 and re.match(r"^[+-]?[\d.]+$", parts[3].strip()):
        tp = _to_float(parts[3], "TP")
        tag_start += 1
    tail = " ".join(parts[tag_start:])
    return {
        "direction": direction,
        "symbol": symbol,
        "size": _to_float(parts[0], "size"),
        "entry_price": _to_float(parts[1], "entry"),
        "initial_sl": _to_float(parts[2], "SL"),
        "tp": tp,
        "exit_price": _to_float(exit_raw, "exit"),
        "gross_pnl": _to_float(pnl_raw, "pnl"),
        "fees": _to_float(fee_raw, "fee") if fee_raw else 0.0,
        "entry_time": entry_time,
        "exit_time": entry_time,
        "tags": tail.split() if tail else [],
    }


def parse_tsl(text: str) -> dict:
    """`tsl gold, 4005`."""
    m = re.match(r"(?i)^\s*tsl\s+([a-z0-9\-/.]+)\s*,\s*([+-]?[\d.]+)\s*$", text.strip())
    if not m:
        raise BotParseError("TSL syntax: <code>tsl SYMBOL, NEW_SL</code>")
    return {"symbol": m.group(1).upper(), "current_sl": _to_float(m.group(2), "SL")}


def parse_close(text: str) -> dict:
    """`close gold, 4015, +150, fee: 3.5, !early, notes...`."""
    m = re.match(r"(?i)^\s*close\s+([a-z0-9\-/.]+)\s*,(.*)$", text.strip(), re.DOTALL)
    if not m:
        raise BotParseError("Close syntax: <code>close SYMBOL, EXIT, [GROSS], [fee: X], [!tags], [notes]</code>")
    symbol, rest = m.group(1).upper(), m.group(2)
    parts = _split_args(rest)
    if not parts:
        raise BotParseError("Close needs at least an EXIT price")
    exit_price = _to_float(parts[0], "exit")
    gross: Optional[float] = None
    fees: Optional[float] = None
    tag_tokens: list[str] = []
    notes: list[str] = []
    for part in parts[1:]:
        fee_m = re.match(r"(?i)^fee\s*:\s*([+-]?[\d.]+)$", part.strip())
        if fee_m:
            fees = _to_float(fee_m.group(1), "fee")
        elif re.match(r"^[+-]?[\d.]+$", part.strip()) and gross is None:
            gross = _to_float(part, "gross PnL")
        elif re.match(r"^[#!]", part.strip()):
            tag_tokens.extend(part.split())
        elif part.strip():
            notes.append(part.strip())
    return {
        "symbol": symbol,
        "exit_price": exit_price,
        "gross_pnl": gross,
        "fees": fees,
        "mistake_tags": tag_tokens,
        "review_notes": " ".join(notes) or None,
    }


# --- Telegram HTTP layer ---


def _api() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=f"{API_BASE}/bot{_token()}", timeout=45.0)


async def send_text(
    chat_id: int,
    text: str,
    reply_markup: Optional[dict] = None,
    parse_mode: Optional[str] = "HTML",
) -> int:
    """Send a message; returns the Telegram message_id (for reply tracking)."""
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    async with _api() as client:
        resp = await client.post("/sendMessage", json=payload)
        resp.raise_for_status()
        return int(resp.json()["result"]["message_id"])


async def notify(text: str, reply_markup: Optional[dict] = None) -> Optional[int]:
    """Phase 3 scheduler entry point — alerts the owner chat."""
    uid = _allowed_user()
    if not uid:
        log.warning("notify skipped: TG_ALLOWED_USER_ID not set")
        return None
    return await send_text(int(uid), text, reply_markup)


def trade_actions_keyboard(trade_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "🛡️ Move to BE", "callback_data": f"be:{trade_id}"},
                {"text": "📈 Update TSL", "callback_data": f"tsl:{trade_id}"},
            ],
            [
                {"text": "🏁 Close Trade", "callback_data": f"close:{trade_id}"},
                {"text": "📸 Attach Chart", "callback_data": f"photo:{trade_id}"},
            ],
        ]
    }


def trade_picker_keyboard(trades: list, prefix: str) -> dict:
    rows = [
        [{"text": f"{t.symbol} ({t.ticket})", "callback_data": f"{prefix}:{t.id}"}]
        for t in trades
    ]
    return {"inline_keyboard": rows}


def describe_trade(t: Trade) -> str:
    return (
        f"{t.direction.upper()} {t.symbol} {t.size} @ {t.entry_price} "
        f"(SL {t.current_sl}, TP {t.tp}) 🎫 {t.ticket}"
    )


# --- DB helpers (session-per-update) ---


def _open_trades(session: Session) -> list:
    from app.models import Trade

    return list(
        session.exec(
            select(Trade).where(Trade.status == "OPEN").order_by(Trade.timestamp_open.desc())
        ).all()
    )


def resolve_open_trade(session: Session, symbol: str):
    from app.models import Trade

    return session.exec(
        select(Trade)
        .where(Trade.status == "OPEN", Trade.symbol == symbol.upper())
        .order_by(Trade.timestamp_open.desc())
    ).first()


async def _answer_callback(callback_id: str, text: str = "") -> None:
    async with _api() as client:
        await client.post("/answerCallbackQuery", json={"callback_query_id": callback_id, "text": text})


# --- Command handlers ---


async def handle_open_command(chat_id: int, session: Session) -> None:
    trades = _open_trades(session)
    if not trades:
        await send_text(chat_id, "📭 No active open trades.")
        return
    lines = [f"• {describe_trade(t)}" for t in trades]
    await send_text(
        chat_id,
        "📂 Open trades:\n" + "\n".join(lines),
        trade_picker_keyboard(trades, "close"),
    )


async def do_open(chat_id: int, session: Session, args: dict) -> None:
    from app.models import Trade
    from app.routers.trades import _flag_breach_day, _generate_ticket, _guardrail_breached
    from app.services.migrate_csv import get_or_create_tag, normalize_tag_list
    from app.services.session_resolver import normalize_session

    if args["size"] <= 0:
        await send_text(chat_id, "❌ Size must be positive.")
        return
    ticket = _generate_ticket(args["symbol"])
    opened_at = args.get("entry_time") or _now()
    trade = Trade(
        ticket=ticket,
        timestamp_open=opened_at,
        entry_time=opened_at,
        session=normalize_session(None, opened_at),
        direction=args["direction"],
        symbol=args["symbol"],
        size=args["size"],
        entry_price=args["entry_price"],
        initial_sl=args["initial_sl"],
        current_sl=args["initial_sl"],
        tp=args["tp"],
        fees=0.0,
        status="OPEN",
    )
    session.add(trade)
    session.flush()
    pairs = normalize_tag_list(args["tags"])
    breached = _guardrail_breached(session)
    if breached:
        if not any(n == "discipline_breach" for n, _ in pairs):
            pairs.append(("discipline_breach", "mistake"))
        _flag_breach_day(session)
    trade.tags = [get_or_create_tag(session, n, c) for n, c in pairs]
    trade.updated_at = _now()
    session.add(trade)
    session.commit()
    session.refresh(trade)
    await send_text(
        chat_id,
        f"✅ OPEN {describe_trade(trade)}",
        trade_actions_keyboard(trade.id),
    )
    if breached:
        await send_text(
            chat_id,
            "🚨 GUARDRAIL BREACH: daily limit hit. Walk away from the screen! "
            "Trade tagged !discipline_breach.",
        )


async def do_tsl(chat_id: int, session: Session, symbol: str, new_sl: float) -> None:
    trade = resolve_open_trade(session, symbol)
    if trade is None:
        await send_text(chat_id, f"❌ No OPEN {symbol.upper()} trade to trail.")
        return
    trade.current_sl = new_sl
    trade.updated_at = _now()
    session.add(trade)
    session.commit()
    await send_text(chat_id, f"🛡️ TSL updated: {describe_trade(trade)}")


async def do_close(chat_id: int, session: Session, args: dict) -> None:
    from app.routers.trades import _flag_breach_day, _guardrail_breached
    from app.services.migrate_csv import (
        compute_r_multiple,
        estimate_gross_pnl,
        get_or_create_tag,
        normalize_tag_list,
    )

    trade = resolve_open_trade(session, args["symbol"])
    if trade is None:
        await send_text(chat_id, f"❌ No OPEN {args['symbol'].upper()} trade to close.")
        return
    fees = args["fees"] if args["fees"] is not None else (trade.fees or 0.0)
    if args["gross_pnl"] is not None:
        gross = args["gross_pnl"]
    else:
        gross = estimate_gross_pnl(
            trade.direction, trade.symbol, trade.size, trade.entry_price, args["exit_price"]
        )
        if gross is None:
            gross = trade.gross_pnl
    net = (gross - (fees or 0.0)) if gross is not None else None
    r = compute_r_multiple(trade.direction, trade.entry_price, trade.initial_sl, args["exit_price"])
    trade.exit_price = args["exit_price"]
    trade.gross_pnl = gross
    trade.fees = fees or 0.0
    trade.net_pnl = net
    trade.r_multiple = r
    trade.timestamp_close = _now()
    trade.status = "CLOSED"
    trade.updated_at = _now()
    if args["review_notes"]:
        trade.review_notes = args["review_notes"]
    if args["mistake_tags"]:
        have = {(t.name, t.category) for t in trade.tags}
        for name, _c in normalize_tag_list(args["mistake_tags"]):
            if (name, "mistake") not in have:
                trade.tags.append(get_or_create_tag(session, name, "mistake"))
    session.add(trade)
    session.flush()
    breached = _guardrail_breached(session)
    if breached:
        _flag_breach_day(session)
    session.commit()
    r_txt = f"{r:+.2f}R" if r is not None else "n/a"
    net_txt = f"{net:+.2f}" if net is not None else "n/a"
    await send_text(chat_id, f"🏁 CLOSED {trade.symbol} {net_txt} ({r_txt}) 🎫 {trade.ticket}")
    if breached:
        await send_text(chat_id, "🚨 GUARDRAIL BREACH: daily loss limit hit. Walk away from the screen!")


START = (
    "👋 Welcome to your Trading Journal bot!\n"
    "I log your trades, nudge you on stale positions and send a nightly EOD recap.\n"
    "Just type a trade (<code>buy gold, 0.1, 4000, 3990, 4020</code>) "
    "or send /help for the full syntax."
)

HELP = (
    "📒 <b>Trading Journal bot — syntax guide</b>\n"
    "\n"
    "<b>OPEN a trade:</b>\n"
    "<code>buy SYMBOL, SIZE, ENTRY, SL, [TP], [#setup tags]</code>\n"
    "e.g. <code>buy gold, 0.1, 4000, 3990, 4020, #fvg</code> (sell = short)\n"
    "Open @ a past time: add <code>time: 14:30</code> or <code>time: 2026-09-20 14:30</code>\n"
    "\n"
    "<b>MOVE the stop (trailing):</b>\n"
    "<code>tsl SYMBOL, NEW_SL</code> — e.g. <code>tsl gold, 4005</code>\n"
    "\n"
    "<b>CLOSE a trade:</b>\n"
    "<code>close SYMBOL, EXIT, [GROSS_PNL], [fee: X], [!mistake tags], [notes]</code>\n"
    "e.g. <code>close gold, 4015, +150, fee: 3.5, !early</code> "
    "(gross is estimated from price when omitted)\n"
    "\n"
    "<b>BACKFILL an old trade:</b>\n"
    "<code>past buy SYMBOL, SIZE, ENTRY, SL, TP, exit: EXIT, pnl: PNL, date: YYYY-MM-DD HH:MM</code>\n"
    "\n"
    "<b>CHART screenshots:</b> just send a photo — it attaches to your open trade "
    "(you pick one if several are open).\n"
    "\n"
    "<b>COMMANDS:</b>\n"
    "/start — greeting · /help — this guide · /open — list open trades · "
    "/stats_daily — today's stats · /cancel — drop the pending question\n"
    "\n"
    "Buttons under each confirmation: Move to BE · Update TSL · Close Trade · "
    "Attach Chart. Stale-trade nudges can be snoozed 2h; reply to the nightly "
    "EOD recap to save your journal review."
)


async def do_past(chat_id: int, session: Session, args: dict) -> None:
    from app.models import BackfillRecord
    from app.routers.trades import insert_backfill_record

    rec = BackfillRecord(
        symbol=args["symbol"],
        direction=args["direction"],
        size=args["size"],
        entry_price=args["entry_price"],
        exit_price=args["exit_price"],
        entry_time=args["entry_time"],
        exit_time=args["exit_time"],
        initial_sl=args["initial_sl"],
        tp=args["tp"],
        gross_pnl=args["gross_pnl"],
        fees=args["fees"],
        tags=args["tags"],
    )
    try:
        ticket, created = insert_backfill_record(session, rec)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        await send_text(chat_id, f"❌ Backfill failed — {esc(detail)}")
        return
    if not created:
        await send_text(chat_id, f"⏭️ Already recorded: {ticket}.")
        return
    session.commit()
    trade = session.exec(select(Trade).where(Trade.ticket == ticket)).first()
    info = ""
    if trade is not None:
        r_txt = f"{trade.r_multiple:+.2f}R" if trade.r_multiple is not None else "n/a"
        net_txt = f"{trade.net_pnl:+.2f}" if trade.net_pnl is not None else "n/a"
        dur = trade.duration_minutes if trade.duration_minutes is not None else 0
        info = f" {net_txt} ({r_txt}), {trade.session}, {dur}m"
    await send_text(chat_id, f"📚 Backfilled {args['direction'].upper()} {args['symbol']} 🎫 {ticket}.{info}")


# Breakeven tolerance mirrors the analytics API: |net| <= 1 cent is BE.
BE_TOLERANCE = 0.01


def _is_win(net: float) -> bool:
    return net > BE_TOLERANCE


def _is_loss(net: float) -> bool:
    return net < -BE_TOLERANCE


def daily_stats_text(session: Session, today: Optional[date_type] = None) -> str:
    """One-day stats over naive-UTC close days (same convention as analytics)."""
    day = today or _now().date()
    start = datetime(day.year, day.month, day.day)
    end = start + timedelta(days=1)
    closed = [
        t
        for t in session.exec(select(Trade).where(Trade.status == "CLOSED")).all()
        if start <= (as_naive_utc(t.timestamp_close) or datetime.min) < end
    ]
    nets = [t.net_pnl if t.net_pnl is not None else 0.0 for t in closed]
    wins = sum(1 for n in nets if _is_win(n))
    losses = sum(1 for n in nets if _is_loss(n))
    be = len(nets) - wins - losses
    total = len(closed)
    wr = f"{wins / total * 100:.0f}%" if total else "n/a"
    r_total = sum(t.r_multiple for t in closed if t.r_multiple is not None)
    opens = session.exec(select(Trade).where(Trade.status == "OPEN")).all()
    lines = [
        f"📊 Daily stats {day.isoformat()} (UTC): "
        f"{total} closed ({wins}W · {losses}L · {be}BE), "
        f"win rate {wr}, net {sum(nets):+.2f}, R {r_total:+.2f}."
    ]
    for t in sorted(closed, key=lambda x: x.timestamp_close or datetime.min):
        net = t.net_pnl if t.net_pnl is not None else 0.0
        r_txt = f"{t.r_multiple:+.2f}R" if t.r_multiple is not None else "n/a"
        lines.append(
            f"• {(t.direction or '').upper()} {t.symbol} {net:+.2f} ({r_txt}) 🎫 {t.ticket}"
        )
    if not closed:
        lines.append("No closed trades yet today.")
    lines.append(f"Open now: {len(opens)}.")
    return "\n".join(lines)


async def handle_stats_daily(chat_id: int, session: Session) -> None:
    await send_text(chat_id, daily_stats_text(session))


def _command_key(body: str) -> str:
    """Base slash-command: lowercase, `@BotName` mention and args stripped."""
    head = body.split()[0] if body.split() else ""
    return head.split("@")[0].lower()


async def handle_text(chat_id: int, text: str, session: Session) -> None:
    body = text.strip()
    low = body.lower()

    cmd = _command_key(body)
    if cmd == "/start":
        await send_text(chat_id, START)
        return
    if cmd == "/help" or low == "help":
        await send_text(chat_id, HELP)
        return
    if cmd in ("/stats_daily", "/stats"):
        await handle_stats_daily(chat_id, session)
        return
    if cmd == "/cancel":
        _pending.pop(chat_id, None)
        await send_text(chat_id, "Cancelled.")
        return
    if cmd == "/open":
        await handle_open_command(chat_id, session)
        return

    state = _pending.get(chat_id)
    if state:
        action = state["action"]
        if action == "tsl":
            try:
                new_sl = _to_float(body, "SL")
            except BotParseError as exc:
                await send_text(chat_id, f"❌ {exc} — or /cancel.")
                return
            trade = session.get(Trade, state["trade_id"])
            if trade is None or trade.status != "OPEN":
                _pending.pop(chat_id, None)
                await send_text(chat_id, "❌ That trade is no longer open.")
                return
            trade.current_sl = new_sl
            trade.updated_at = _now()
            session.add(trade)
            session.commit()
            _pending.pop(chat_id, None)
            await send_text(chat_id, f"🛡️ TSL updated: {describe_trade(trade)}")
            return
        if action == "close":
            try:
                args = parse_close(f"close {state['symbol']}, {body}")
            except BotParseError as exc:
                await send_text(chat_id, f"❌ {exc} — or /cancel.")
                return
            _pending.pop(chat_id, None)
            await do_close(chat_id, session, args)
            return
        if action == "photo":
            await send_text(chat_id, "📸 Send the chart image now — or /cancel.")
            return

    try:
        if re.match(r"(?i)^\s*past\s", body):
            await do_past(chat_id, session, parse_past(body))
        elif re.match(r"(?i)^\s*(buy|sell)\s", body):
            await do_open(chat_id, session, parse_open(body))
        elif re.match(r"(?i)^\s*tsl\s", body):
            args = parse_tsl(body)
            await do_tsl(chat_id, session, args["symbol"], args["current_sl"])
        elif re.match(r"(?i)^\s*close\s", body):
            await do_close(chat_id, session, parse_close(body))
        else:
            await send_text(chat_id, "❓ Unknown command. " + HELP)
    except BotParseError as exc:
        await send_text(chat_id, f"❌ {exc}")


# --- Photo pipeline (Task 2.3) ---


async def _download_telegram_file(file_path: str) -> bytes:
    async with httpx.AsyncClient(base_url=FILE_BASE, timeout=60.0) as client:
        resp = await client.get(f"/bot{_token()}/{file_path}")
        resp.raise_for_status()
        return resp.content


async def attach_photo_to_trade(chat_id: int, session: Session, trade_id: int, file_id: str) -> None:
    from sqlmodel import select

    from app.models import Screenshot
    from app.services import immich_client

    trade = session.get(Trade, trade_id)
    if trade is None:
        await send_text(chat_id, "❌ Target trade not found.")
        return
    async with _api() as client:
        resp = await client.post("/getFile", json={"file_id": file_id})
        resp.raise_for_status()
        file_path = resp.json()["result"]["file_path"]
    data = await _download_telegram_file(file_path)
    if len(data) > 15 * 1024 * 1024:
        await send_text(chat_id, "❌ Image exceeds 15 MB limit.")
        return
    original = file_path.rsplit("/", 1)[-1] or "chart.jpg"
    digest = immich_client.sha256_hex(data)
    dup = session.exec(
        select(Screenshot).where(Screenshot.trade_id == trade.id, Screenshot.sha256 == digest)
    ).first()
    if dup is not None:
        await send_text(chat_id, "⏭️ Identical screenshot already attached to this trade.")
        return
    asset_id, stored, _moment = await immich_client.upload_trade_screenshot(
        data, trade, "setup", original, "image/jpeg"
    )
    album_name = immich_client.month_album_name(immich_client.open_moment(trade))
    album_id = await immich_client.resolve_monthly_album(album_name)
    await immich_client.add_assets_to_album(album_id, [asset_id], album_name)
    shot = Screenshot(
        trade_id=trade.id,
        immich_asset_id=asset_id,
        label="setup",
        original_filename=original[:255],
        stored_filename=stored,
        sha256=digest,
        byte_size=len(data),
    )
    session.add(shot)
    session.commit()
    await send_text(
        chat_id,
        f"📸 Screenshot attached to {trade.symbol} (Trade ID: {trade.ticket}) "
        f"in Immich album {album_name}",
    )


async def handle_photo(chat_id: int, file_id: str, session: Session) -> None:
    state = _pending.get(chat_id)
    if state and state.get("action") == "photo":
        _pending.pop(chat_id, None)
        try:
            await attach_photo_to_trade(chat_id, session, state["trade_id"], file_id)
        except Exception as exc:
            log.exception("photo attach failed")
            await send_text(chat_id, f"❌ Screenshot upload failed: {esc(exc)}")
        return
    trades = _open_trades(session)
    if not trades:
        await send_text(chat_id, "📭 No open trades — photo ignored. Open a trade first.")
        return
    if len(trades) == 1:
        try:
            await attach_photo_to_trade(chat_id, session, trades[0].id, file_id)
        except Exception as exc:
            log.exception("photo attach failed")
            await send_text(chat_id, f"❌ Screenshot upload failed: {esc(exc)}")
        return
    _pending[chat_id] = {"action": "photo_pick", "file_id": file_id}
    await send_text(
        chat_id,
        "Multiple trades open — which one gets this screenshot?",
        trade_picker_keyboard(trades, "pick"),
    )


# --- Callback queries (Task 2.2) ---


async def handle_callback(chat_id: int, callback_id: str, data: str, session: Session) -> None:
    from app.models import Trade

    try:
        action, raw_id = data.split(":", 1)
        trade_id = int(raw_id)
    except ValueError:
        await _answer_callback(callback_id, "Bad button payload")
        return

    if action == "pick":
        state = _pending.get(chat_id)
        if not state or state.get("action") != "photo_pick":
            await _answer_callback(callback_id, "Nothing to attach")
            return
        _pending.pop(chat_id, None)
        await _answer_callback(callback_id, "Attaching…")
        try:
            await attach_photo_to_trade(chat_id, session, trade_id, state["file_id"])
        except Exception as exc:
            log.exception("photo attach failed")
            await send_text(chat_id, f"❌ Screenshot upload failed: {esc(exc)}")
        return

    if action == "snooze":
        from datetime import timedelta

        _snoozed_until[trade_id] = _now() + timedelta(hours=2)
        await _answer_callback(callback_id, "Snoozed 2h")
        await send_text(chat_id, "🔕 Stale alert snoozed for 2h.")
        return

    trade = session.get(Trade, trade_id)
    if trade is None:
        await _answer_callback(callback_id, "Trade not found")
        return

    if action == "be":
        if trade.status != "OPEN" or trade.entry_price is None:
            await _answer_callback(callback_id, "Not open")
            return
        trade.current_sl = trade.entry_price
        trade.updated_at = _now()
        session.add(trade)
        session.commit()
        await _answer_callback(callback_id, "SL → breakeven")
        await send_text(chat_id, f"🛡️ Breakeven set: {describe_trade(trade)}")
    elif action == "tsl":
        _pending[chat_id] = {"action": "tsl", "trade_id": trade.id}
        await _answer_callback(callback_id)
        await send_text(chat_id, f"📈 Reply with the new SL for {trade.symbol} ({trade.ticket}) — or /cancel.")
    elif action == "close":
        _pending[chat_id] = {"action": "close", "trade_id": trade.id, "symbol": trade.symbol}
        await _answer_callback(callback_id)
        await send_text(
            chat_id,
            f"🏁 Reply with exit details for {trade.symbol} — e.g. <code>4315, +120, fee: 2.5, !early</code> — or /cancel.",
        )
    elif action == "photo":
        _pending[chat_id] = {"action": "photo", "trade_id": trade.id}
        await _answer_callback(callback_id)
        await send_text(chat_id, f"📸 Send the chart screenshot for {trade.symbol} now — or /cancel.")
    else:
        await _answer_callback(callback_id, "Unknown action")


def is_snoozed(trade_id: int) -> bool:
    until = _snoozed_until.get(trade_id)
    return bool(until and until > _now())


# --- Polling loop ---


async def _process_update(update: dict) -> None:
    allowed = _allowed_user()
    if not allowed:
        # Fail closed: a live bot without an owner allowlist would answer
        # anyone on Telegram. Configure TG_ALLOWED_USER_ID to enable.
        log.error("ignoring update: TG_ALLOWED_USER_ID is not set")
        return
    from app.database import engine

    if "callback_query" in update:
        cb = update["callback_query"]
        from_id = str(cb.get("from", {}).get("id", ""))
        if allowed and from_id != allowed:
            log.warning("ignoring callback from unauthorized user %s", from_id)
            return
        chat_id = cb["message"]["chat"]["id"]
        with Session(engine) as session:
            await handle_callback(chat_id, cb["id"], cb.get("data", ""), session)
        return

    msg = update.get("message") or {}
    from_id = str(msg.get("from", {}).get("id", ""))
    if allowed and from_id != allowed:
        log.warning("ignoring message from unauthorized user %s", from_id)
        return
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    if chat_id is None:
        return
    with Session(engine) as session:
        photos = msg.get("photo") or []
        text = msg.get("text") or msg.get("caption") or ""
        if photos:
            await handle_photo(chat_id, photos[-1]["file_id"], session)
            # A captioned command still executes (photo already routed above).
            if text.strip() and re.match(r"(?i)^\s*(buy|sell|tsl|close|past|/open|/cancel|/start|/help|/stats_daily|/stats)", text.strip()):
                await handle_text(chat_id, text, session)
        elif text:
            # EOD review replies (Phase 3) are picked up there; ignore here
            # unless the message is a reply to the EOD prompt.
            if msg.get("reply_to_message"):
                try:
                    from app.services import scheduler as _sched  # lazy, Phase 3

                    handled = await _sched.maybe_handle_eod_reply(chat_id, msg, session)
                except ImportError:
                    handled = False
                if handled:
                    return
            await handle_text(chat_id, text, session)


# Command menu published via setMyCommands (see register_commands).
COMMAND_MENU = [
    {"command": "start", "description": "Greet and get started"},
    {"command": "help", "description": "Full trade entry syntax guide"},
    {"command": "open", "description": "List your open trades"},
    {"command": "stats_daily", "description": "Show today's trading stats"},
    {"command": "cancel", "description": "Drop the pending question"},
]


async def register_commands() -> bool:
    """Publish COMMAND_MENU via setMyCommands. Best-effort: never raises."""
    try:
        async with _api() as client:
            resp = await client.post("/setMyCommands", json={"commands": COMMAND_MENU})
            resp.raise_for_status()
            return True
    except Exception:
        log.warning("setMyCommands failed", exc_info=True)
        return False


async def run_polling() -> None:
    """Long-poll getUpdates until cancelled. No-op when unconfigured."""
    if not is_configured():
        log.warning("TG_BOT_TOKEN not set — Telegram polling disabled")
        return
    log.info("Telegram polling started")
    await register_commands()  # best-effort; polling continues regardless
    offset = 0
    backoff = 1
    try:
        async with _api() as client:
            while True:
                try:
                    resp = await client.post(
                        "/getUpdates",
                        json={"offset": offset, "timeout": 30, "allowed_updates": ["message", "callback_query"]},
                    )
                    resp.raise_for_status()
                    backoff = 1
                    for update in resp.json().get("result", []):
                        offset = max(offset, update["update_id"] + 1)
                        try:
                            await _process_update(update)
                        except Exception:
                            log.exception("update %s failed", update.get("update_id"))
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("polling error, retry in %ss", backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60)
    except asyncio.CancelledError:
        log.info("Telegram polling stopped")
