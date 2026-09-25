"""Integrated Telegram bot client (PLAN-v2 Tasks 2.1–2.3).

Long-polls the Bot API with httpx inside the FastAPI lifespan (see
app.main). Only updates from TG_ALLOWED_USER_ID are honored.

Text syntax:
    Open:  buy gold, 0.1, 4000, 3990, 4020, #fvg
    TSL:   tsl gold, 4005
    Close: close gold, 4015, +150, fee: 3.5, !early, notes
Commands: /open, /cancel, /start (help).

Photos are downloaded via getFile and streamed straight into
immich_client (never touch local disk), then recorded in screenshots.
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from sqlmodel import Session, select

from app.models import Screenshot, Trade

log = logging.getLogger("telegram_bot")

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
        raise BotParseError(f"Bad {what}: {token!r}") from None


def parse_open(text: str) -> dict:
    """`buy gold, 0.1, 4000, 3990, 4020, #fvg ...`."""
    m = re.match(r"(?i)^\s*(buy|sell)\s+([a-z0-9\-/.]+)\s*,(.*)$", text.strip(), re.DOTALL)
    if not m:
        raise BotParseError("Open syntax: `buy SYMBOL, SIZE, ENTRY, SL, [TP], [#tags]`")
    direction, symbol, rest = m.group(1).lower(), m.group(2).upper(), m.group(3)
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
        "tags": tail.split() if tail else [],
        "thesis": None,
    }


def parse_tsl(text: str) -> dict:
    """`tsl gold, 4005`."""
    m = re.match(r"(?i)^\s*tsl\s+([a-z0-9\-/.]+)\s*,\s*([+-]?[\d.]+)\s*$", text.strip())
    if not m:
        raise BotParseError("TSL syntax: `tsl SYMBOL, NEW_SL`")
    return {"symbol": m.group(1).upper(), "current_sl": _to_float(m.group(2), "SL")}


def parse_close(text: str) -> dict:
    """`close gold, 4015, +150, fee: 3.5, !early, notes...`."""
    m = re.match(r"(?i)^\s*close\s+([a-z0-9\-/.]+)\s*,(.*)$", text.strip(), re.DOTALL)
    if not m:
        raise BotParseError("Close syntax: `close SYMBOL, EXIT, [GROSS], [fee: X], [!tags], [notes]`")
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
    parse_mode: Optional[str] = None,
) -> None:
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    async with _api() as client:
        resp = await client.post("/sendMessage", json=payload)
        resp.raise_for_status()


async def notify(text: str, reply_markup: Optional[dict] = None) -> None:
    """Phase 3 scheduler entry point — alerts the owner chat."""
    uid = _allowed_user()
    if not uid:
        log.warning("notify skipped: TG_ALLOWED_USER_ID not set")
        return
    await send_text(int(uid), text, reply_markup)


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

    if args["size"] <= 0:
        await send_text(chat_id, "❌ Size must be positive.")
        return
    ticket = _generate_ticket(args["symbol"])
    trade = Trade(
        ticket=ticket,
        timestamp_open=_now(),
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
    from app.services.migrate_csv import compute_r_multiple, get_or_create_tag, normalize_tag_list

    trade = resolve_open_trade(session, args["symbol"])
    if trade is None:
        await send_text(chat_id, f"❌ No OPEN {args['symbol'].upper()} trade to close.")
        return
    fees = args["fees"] if args["fees"] is not None else (trade.fees or 0.0)
    gross = args["gross_pnl"] if args["gross_pnl"] is not None else trade.gross_pnl
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


HELP = (
    "📒 Trading Journal bot\n"
    "Open: `buy gold, 0.1, 4000, 3990, 4020, #fvg`\n"
    "TSL: `tsl gold, 4005`\n"
    "Close: `close gold, 4015, +150, fee: 3.5, !early, notes`\n"
    "Commands: /open · /cancel"
)


async def handle_text(chat_id: int, text: str, session: Session) -> None:
    body = text.strip()
    low = body.lower()

    if low in ("/start", "help"):
        await send_text(chat_id, HELP)
        return
    if low == "/cancel":
        _pending.pop(chat_id, None)
        await send_text(chat_id, "Cancelled.")
        return
    if low == "/open":
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
        if re.match(r"(?i)^\s*(buy|sell)\s", body):
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
        resp = await client.get(f"/file/bot{_token()}/{file_path}")
        resp.raise_for_status()
        return resp.content


async def attach_photo_to_trade(chat_id: int, session: Session, trade_id: int, file_id: str) -> None:
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
    filename = file_path.rsplit("/", 1)[-1] or "chart.jpg"
    content_type = "image/jpeg"
    if filename.lower().endswith(".png"):
        content_type = "image/png"
    elif filename.lower().endswith(".webp"):
        content_type = "image/webp"
    asset_id = await immich_client.upload_asset(data, filename, content_type)
    album_name = immich_client.month_album_name(trade.timestamp_open)
    album_id = await immich_client.resolve_monthly_album(album_name)
    await immich_client.add_assets_to_album(album_id, [asset_id], album_name)
    shot = Screenshot(trade_id=trade.id, immich_asset_id=asset_id, label="setup")
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
            await send_text(chat_id, f"❌ Screenshot upload failed: {exc}")
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
            await send_text(chat_id, f"❌ Screenshot upload failed: {exc}")
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
            await send_text(chat_id, f"❌ Screenshot upload failed: {exc}")
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
            f"🏁 Reply with exit details for {trade.symbol} — e.g. `4315, +120, fee: 2.5, !early` — or /cancel.",
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
            if text.strip() and re.match(r"(?i)^\s*(buy|sell|tsl|close|/open|/cancel)", text.strip()):
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


async def run_polling() -> None:
    """Long-poll getUpdates until cancelled. No-op when unconfigured."""
    if not is_configured():
        log.warning("TG_BOT_TOKEN not set — Telegram polling disabled")
        return
    log.info("Telegram polling started")
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
