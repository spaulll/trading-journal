"""Integrated Telegram bot client (PLAN-v2 Tasks 2.1–2.3).

Long-polls the Bot API with httpx inside the FastAPI lifespan (see
app.main). Only updates from TG_ALLOWED_USER_ID are honored.

Text syntax:
    Open:  buy gold, 0.1, 4000, 3990, 4020, #fvg
    TSL:   tsl gold, 4005
    Close: close gold, 4015, +150, fee: 3.5, !early, notes
Commands: /start, /help, /open, /stats_daily, /brokertime, /cancel.

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
from app.services.timeutils import as_naive_utc, wall_to_naive_utc
from app.services.broker_clock import IST_OFFSET

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


# --- Account alias routing (@alias suffix, last-suffix-wins) ---

ALIAS_TOKEN_RE = re.compile(r"@([A-Za-z0-9][A-Za-z0-9\-_]{1,23})")
LAST_ALIAS_KEY = "tg_last_account_alias"


def extract_alias(text: str) -> tuple[str, Optional[str]]:
    """Pull trailing @alias tokens. Last token wins; tokens stripped."""
    found = ALIAS_TOKEN_RE.findall(text or "")
    alias = found[-1].lower() if found else None
    cleaned = ALIAS_TOKEN_RE.sub("", text or "").strip()
    cleaned = re.sub(r"[ \t]+", " ", cleaned).strip(" ,")
    return cleaned, alias


def get_account_by_alias(session: Session, alias: str):
    from app.models import Account

    return session.exec(
        select(Account).where(Account.alias == (alias or "").strip().lower())
    ).first()


def list_account_aliases(session: Session) -> list[str]:
    from app.models import Account

    return [
        a.alias
        for a in session.exec(
            select(Account).where(Account.status != "archived").order_by(Account.alias.asc())
        ).all()
    ]


def get_last_alias(session: Session) -> Optional[str]:
    from app.models import AppSetting

    row = session.get(AppSetting, LAST_ALIAS_KEY)
    val = (row.value or "").strip().lower() if row else ""
    return val or None


def set_last_alias(session: Session, alias: str) -> None:
    from app.models import AppSetting

    alias = (alias or "").strip().lower()
    if not alias:
        return
    row = session.get(AppSetting, LAST_ALIAS_KEY)
    if row is None:
        row = AppSetting(key=LAST_ALIAS_KEY, value=alias)
    else:
        row.value = alias
        row.updated_at = _now()
    session.add(row)
    session.commit()


def account_alias_of(session: Session, account_id: Optional[int]) -> str:
    if account_id is None:
        return "unassigned"
    from app.models import Account

    acc = session.get(Account, account_id)
    return acc.alias if acc else "unassigned"


def open_trades_for_symbol(session: Session, symbol: str) -> list:
    from app.models import Trade

    return list(
        session.exec(
            select(Trade)
            .where(Trade.status == "OPEN", Trade.symbol == symbol.upper())
            .order_by(Trade.timestamp_open.desc())
        ).all()
    )


# --- Pure parsers (unit-testable, no I/O) ---


def _split_args(body: str) -> list[str]:
    return [p.strip() for p in body.split(",")]


def _to_float(token: str, what: str) -> float:
    try:
        return float(token.strip().lstrip("+"))
    except ValueError:
        raise BotParseError(f"Bad {what}: <code>{esc(token.strip())}</code>") from None


def _suffix_offset(suffix: str, broker_offset: Optional[timedelta]) -> timedelta:
    """UTC offset for a `time:`/`date:` zone suffix ('' = UTC)."""
    if not suffix:
        return timedelta(0)
    low = suffix.lower()
    if low in ("utc", "gmt"):
        return timedelta(0)
    if low == "ist":
        return IST_OFFSET
    if low in ("mt5", "broker"):
        if broker_offset is None:
            raise BotParseError(
                "Broker clock not set — send <code>/brokertime</code> to calibrate it first."
            )
        return broker_offset
    raise BotParseError(f"Bad time zone: <code>{esc(suffix)}</code> (use MT5, IST or UTC)")


def _split_zone(raw: str, broker_offset: Optional[timedelta]) -> tuple[str, timedelta]:
    """Split 'YYYY-MM-DD HH:MM [ZONE]' into (datetime part, offset)."""
    text = (raw or "").strip()
    m = re.search(r"\s+([A-Za-z][A-Za-z0-9]{0,7})\s*$", text)
    if not m:
        return text, timedelta(0)
    return text[: m.start()].strip(), _suffix_offset(m.group(1), broker_offset)


def _broker_offset(session: Session) -> Optional[timedelta]:
    """Calibrated broker offset from AppSetting (None when never set)."""
    from app.services import broker_clock as _bc

    minutes = _bc.get_offset_minutes(session)
    return timedelta(minutes=minutes) if minutes is not None else None


def _parse_wall_datetime(raw: str) -> datetime:
    """Parse `YYYY-MM-DD HH:MM[:SS]`, seconds optional (MT5 exports include them)."""
    text = (raw or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"Bad datetime: {text!r}")


def _parse_explicit_time(
    tail: str, broker_offset: Optional[timedelta] = None
) -> tuple[Optional[datetime], str]:
    """Pull an optional `time: ...` flag from tail.

    Shapes: `time: HH:MM[:SS] [ZONE]` or `time: YYYY-MM-DD HH:MM[:SS] [ZONE]`.
    ZONE is MT5, IST or UTC (case-insensitive); bare times are UTC. HH:MM
    resolves against today in the stated zone. Returns (entry_time as
    naive UTC or None, tail with the flag removed).
    """
    from app.services.timeutils import wall_to_naive_utc

    m = re.search(
        r"time\s*:\s*(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}(?::\d{2})?|\d{1,2}:\d{2}(?::\d{2})?)(?:\s+([A-Za-z][A-Za-z0-9]{0,7}))?",
        tail,
        re.IGNORECASE,
    )
    if not m:
        return None, tail
    raw, suffix = m.group(1).strip(), (m.group(2) or "").strip()
    offset = _suffix_offset(suffix, broker_offset)
    try:
        if re.match(r"^\d{4}-", raw):
            wall = _parse_wall_datetime(raw)
        else:
            segs = raw.split(":")
            hh, mm = int(segs[0]), int(segs[1])
            ss = int(segs[2]) if len(segs) > 2 else 0
            # Date base in the stated zone so `23:55 IST` near midnight lands
            # on the right day.
            base = datetime.now(timezone.utc) + offset
            wall = base.replace(hour=hh, minute=mm, second=ss, microsecond=0,
                                tzinfo=None)
    except ValueError:
        raise BotParseError(f"Bad time value: <code>{esc(raw)}</code> (use HH:MM or YYYY-MM-DD HH:MM)")
    if not (0 <= wall.hour <= 23 and 0 <= wall.minute <= 59):
        raise BotParseError(f"Bad time value: <code>{esc(raw)}</code>")
    return wall_to_naive_utc(wall, offset), (tail[: m.start()] + tail[m.end():]).strip(" ,")


def parse_open(text: str, broker_offset: Optional[timedelta] = None) -> dict:
    """`buy gold, 0.1, 4000, 3990, 4020, #fvg ...` (+ optional `time:` flag)."""
    m = re.match(r"(?i)^\s*(buy|sell)\s+([a-z0-9\-/.]+)\s*,(.*)$", text.strip(), re.DOTALL)
    if not m:
        raise BotParseError("Open syntax: <code>buy SYMBOL, SIZE, ENTRY, SL, [TP], [#tags]</code>")
    direction, symbol, rest = m.group(1).lower(), m.group(2).upper(), m.group(3)
    entry_time, rest = _parse_explicit_time(rest, broker_offset)
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


def parse_past(text: str, broker_offset: Optional[timedelta] = None) -> dict:
    """`past buy gold, 0.1, 4000, 3990, 4020, exit: 4015, pnl: 150, date: 2026-09-20 14:30`.

    `date:` is the OPEN time; add `exit_date:` for the CLOSE time (MT5 history
    shows both). `date:` alone keeps the old behaviour (open == close).
    Each timestamp is `YYYY-MM-DD HH:MM[:SS] [MT5|IST|UTC]`; a close time
    without a zone inherits the open's zone.
    """
    m = re.match(r"(?i)^\s*past\s+(buy|sell)\s+([a-z0-9\-/.]+)\s*,(.*)$", text.strip(), re.DOTALL)
    if not m:
        raise BotParseError(
            "Backfill syntax: <code>past buy SYMBOL, SIZE, ENTRY, SL, [TP], exit: EXIT, pnl: PNL, date: YYYY-MM-DD HH:MM[:SS] [MT5|IST|UTC]</code>"
        )
    direction, symbol, rest = m.group(1).lower(), m.group(2).upper(), m.group(3)

    def grab(flag: str) -> Optional[str]:
        found = re.search(rf"\b{flag}\s*:\s*([^\s,][^,]*)", rest, re.IGNORECASE)
        return found.group(1).strip() if found else None

    exit_raw, pnl_raw = grab("exit"), grab("pnl")
    fee_raw = grab("fee")
    open_raw = grab("date") or grab("open") or grab("entry_date") or grab("open_date")
    close_raw = grab("exit_date") or grab("close_date") or grab("exit_time") or grab("close_time")
    if exit_raw is None or pnl_raw is None or open_raw is None:
        raise BotParseError("Backfill needs <code>exit:</code>, <code>pnl:</code> and <code>date: YYYY-MM-DD HH:MM[:SS]</code>")
    if close_raw is None:
        # Single-flag range: `date: OPEN to CLOSE`.
        split = re.split(r"\s+(?:to|->|→)\s+", open_raw, maxsplit=1, flags=re.IGNORECASE)
        if len(split) == 2 and re.match(r"^\d{4}-", split[1].strip()):
            open_raw, close_raw = split[0].strip(), split[1].strip()
    from app.services.timeutils import wall_to_naive_utc

    def _parse_stamp(raw: str, default_offset: Optional[timedelta]) -> datetime:
        part, offset = _split_zone(raw, broker_offset)
        if re.search(r"\s+[A-Za-z][A-Za-z0-9]{0,7}\s*$", raw.strip()) is None and default_offset is not None:
            offset = default_offset  # close without zone inherits open's zone
        return wall_to_naive_utc(_parse_wall_datetime(part), offset)

    try:
        open_part, open_offset = _split_zone(open_raw, broker_offset)
        entry_time = wall_to_naive_utc(_parse_wall_datetime(open_part), open_offset)
        exit_time = _parse_stamp(close_raw, open_offset) if close_raw is not None else entry_time
    except ValueError as exc:
        shown = open_raw if close_raw is None else f"{open_raw} / {close_raw}"
        raise BotParseError(f"Bad date: <code>{esc(shown.strip())}</code> (use YYYY-MM-DD HH:MM[:SS] [MT5|IST|UTC])") from exc
    if exit_time < entry_time:
        raise BotParseError("Close time precedes open time — check <code>date:</code> and <code>exit_date:</code>")

    cleaned = re.sub(r"(?i)\b(exit_date|close_date|entry_date|open_date|exit_time|close_time|exit|pnl|fee|date|open)\s*:\s*[^\s,][^,]*", "", rest)
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
        "exit_time": exit_time,
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


def closed_trade_actions_keyboard(trade_id: int) -> dict:
    """Single-button keyboard for CLOSED/backfilled trades (BE/TSL/Close N/A)."""
    return {
        "inline_keyboard": [
            [{"text": "📸 Attach Chart", "callback_data": f"photo:{trade_id}"}],
        ]
    }


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


def resolve_open_trade(session: Session, symbol: str, account_id: Optional[int] = None):
    from app.models import Trade

    stmt = (
        select(Trade)
        .where(Trade.status == "OPEN", Trade.symbol == symbol.upper())
        .order_by(Trade.timestamp_open.desc())
    )
    if account_id is not None:
        stmt = stmt.where(Trade.account_id == account_id)
    return session.exec(stmt).first()


async def _answer_callback(callback_id: str, text: str = "") -> None:
    async with _api() as client:
        await client.post("/answerCallbackQuery", json={"callback_query_id": callback_id, "text": text})


async def edit_text(
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: Optional[dict] = None,
    parse_mode: Optional[str] = "HTML",
) -> None:
    """Edit a previously sent message (account pagination/detail views)."""
    payload: dict[str, Any] = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    async with _api() as client:
        resp = await client.post("/editMessageText", json=payload)
        resp.raise_for_status()


# --- Accounts browser (/accounts, paginated inline navigation) ---

ACCOUNTS_PAGE_SIZE = 5


STATUS_EMOJI = {"active": "🟢", "passed": "✅", "breach": "🚨", "archived": "🗄️"}


def _bar(pct: Optional[float], width: int = 10) -> str:
    """Target progress bar: ▓▓▓░░░░░░░ 32%. Empty when pct is None."""
    if pct is None:
        return ""
    clamped = max(0.0, min(100.0, pct))
    filled = 0 if clamped <= 0 else max(1, int(round(clamped / (100 / width))))
    return "▓" * filled + "░" * (width - filled) + f" {clamped:.1f}%"


def _fmt_left(v) -> str:
    """Compact number for TG lines: 500.0 → 500, else 2dp."""
    if v is None:
        return "—"
    return f"{v:,.0f}" if float(v) == int(float(v)) else f"{v:,.2f}"


def accounts_page_content(session: Session, page: int = 0) -> tuple[str, Optional[dict]] | None:
    """Render one list page. Returns None when no accounts exist."""
    from sqlmodel import select

    from app.models import Account, Trade
    from app.routers.accounts import _prop_numbers

    accs = list(
        session.exec(
            select(Account).where(Account.status != "archived").order_by(Account.alias.asc())
        ).all()
    )
    if not accs:
        return None
    pages = max(1, (len(accs) + ACCOUNTS_PAGE_SIZE - 1) // ACCOUNTS_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    chunk = accs[page * ACCOUNTS_PAGE_SIZE : (page + 1) * ACCOUNTS_PAGE_SIZE]

    lines = [f"🏦 <b>Prop Accounts</b> · {len(accs)}" + (f"  <i>({page + 1}/{pages})</i>" if pages > 1 else "")]
    for a in chunk:
        p = _prop_numbers(a, session)
        dot = STATUS_EMOJI.get(p["status"], "⚪")
        tgt = f"{p['target_pct']:.1f}%" if p["target_pct"] is not None else "—"
        lines.append(
            f"{dot} <b>@{esc(a.alias)}</b>  <i>{esc(a.firm or '—')} · {esc(a.phase)}</i>\n"
            f"   💰 {p['balance']:,.2f} <i>({p['total_net']:+,.2f})</i>  ·  "
            f"📉 Daily left <b>{_fmt_left(p['daily_left'])}</b>  ·  🎯 {tgt}"
        )
    unassigned = len(session.exec(select(Trade).where(Trade.account_id.is_(None))).all())
    if unassigned:
        lines.append(f"\n📦 <i>{unassigned} unassigned — move them via Trades → filter → Move</i>")

    rows = [[{"text": f"@{a.alias}", "callback_data": f"acc:{a.id}"}] for a in chunk]
    if pages > 1:
        nav = []
        if page > 0:
            nav.append({"text": "◀ Prev", "callback_data": f"accs:{page - 1}"})
        if page < pages - 1:
            nav.append({"text": "Next ▶", "callback_data": f"accs:{page + 1}"})
        rows.append(nav)
    return "\n".join(lines), {"inline_keyboard": rows}


def account_detail_content(session: Session, account_id: int) -> tuple[str, Optional[dict]] | None:
    """Full prop snapshot for one account. None when not found."""
    from app.models import Account

    acc = session.get(Account, account_id)
    if acc is None:
        return None
    from app.routers.accounts import _prop_numbers

    p = _prop_numbers(acc, session)
    open_n = p.get("open_trades", 0)
    total_n = p.get("total_trades", 0)
    state = "🚨 <b>BREACH</b>" if p["breached"] else f"{STATUS_EMOJI.get(p['status'], '⚪')} {esc(p['status']).upper()}"
    tgt_line = (
        f"🎯 Target  <b>{_bar(p['target_pct'])}</b>  <i>goal {p['profit_target']:,.2f} ({p['profit_target_pct']}%)</i>"
        if p["profit_target_pct"] is not None
        else "🎯 Target  <i>—</i>"
    )
    text = (
        f"🏦 <b>@{esc(p['alias'])}</b>\n"
        f"<i>{esc(acc.firm or '—')} · {esc(acc.phase)}</i> — {state}\n"
        f"━━━━━━━━━━━━\n"
        f"💰 Balance  <b>{p['balance']:,.2f}</b> <i>({p['total_net']:+,.2f} total)</i>\n"
        f"📉 Daily  {p['daily_pnl']:+,.2f} today · left <b>{_fmt_left(p['daily_left'])}</b> "
        f"<i>({p['daily_loss_pct']}% {esc(p['daily_basis'])})</i>\n"
        f"🛡️ Max  {esc(p['max_mode'])} {p['max_loss_pct']}% · floor "
        f"{p['max_floor']:,.2f} · left <b>{_fmt_left(p['max_left'])}</b>\n"
        f"{tgt_line}\n"
        f"📊 Trades  {open_n} open · {total_n} total"
    )
    return text, {"inline_keyboard": [[{"text": "◀ All accounts", "callback_data": "accs:0"}]]}


async def handle_accounts(chat_id: int, session: Session) -> None:
    rendered = accounts_page_content(session, 0)
    if rendered is None:
        await send_text(chat_id, "📭 No accounts yet — add one in the web UI under Accounts.")
        return
    text, keyboard = rendered
    await send_text(chat_id, text, keyboard)


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
        account_id=args.get("account_id"),
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
    acct = f" @{args.get('account_alias')}" if args.get("account_alias") else ""
    await send_text(
        chat_id,
        f"✅ OPEN {describe_trade(trade)}{acct}",
        trade_actions_keyboard(trade.id),
    )
    if breached:
        await send_text(
            chat_id,
            "🚨 GUARDRAIL BREACH: daily limit hit. Walk away from the screen! "
            "Trade tagged !discipline_breach.",
        )


async def do_tsl(
    chat_id: int,
    session: Session,
    symbol: str,
    new_sl: float,
    account_id: Optional[int] = None,
) -> None:
    candidates = open_trades_for_symbol(session, symbol)
    if not candidates:
        await send_text(chat_id, f"❌ No OPEN {symbol.upper()} trade to trail.")
        return
    if account_id is not None:
        candidates = [t for t in candidates if t.account_id == account_id]
        if not candidates:
            await send_text(chat_id, f"❌ No OPEN {symbol.upper()} trade on that account.")
            return
    if len(candidates) > 1:
        _pending[chat_id] = {"action": "tsl_pick", "symbol": symbol.upper(), "new_sl": new_sl}
        rows = [
            [
                {
                    "text": f"{t.symbol} @{account_alias_of(session, t.account_id)} ({t.ticket})",
                    "callback_data": f"tslid:{t.id}",
                }
            ]
            for t in candidates
        ]
        await send_text(
            chat_id,
            f"Multiple OPEN {symbol.upper()} — pick the account:",
            {"inline_keyboard": rows},
        )
        return
    trade = candidates[0]
    trade.current_sl = new_sl
    trade.updated_at = _now()
    session.add(trade)
    session.commit()
    await send_text(chat_id, f"🛡️ TSL updated: {describe_trade(trade)}")


async def do_close(chat_id: int, session: Session, args: dict) -> None:
    account_id = args.get("account_id")
    candidates = open_trades_for_symbol(session, args["symbol"])
    if not candidates:
        await send_text(chat_id, f"❌ No OPEN {args['symbol'].upper()} trade to close.")
        return
    if account_id is not None:
        candidates = [t for t in candidates if t.account_id == account_id]
        if not candidates:
            await send_text(chat_id, f"❌ No OPEN {args['symbol'].upper()} trade on that account.")
            return
    if len(candidates) > 1:
        _pending[chat_id] = {"action": "close_pick", "args": args}
        rows = [
            [
                {
                    "text": f"{t.symbol} @{account_alias_of(session, t.account_id)} ({t.ticket})",
                    "callback_data": f"closeid:{t.id}",
                }
            ]
            for t in candidates
        ]
        await send_text(
            chat_id,
            f"Multiple OPEN {args['symbol'].upper()} — pick the account:",
            {"inline_keyboard": rows},
        )
        return
    await do_close_on_trade(chat_id, session, candidates[0].id, args)


async def do_close_on_trade(chat_id: int, session: Session, trade_id: int, args: dict) -> None:
    from app.models import Trade
    from app.routers.trades import _flag_breach_day, _guardrail_breached
    from app.services.migrate_csv import (
        compute_r_multiple,
        estimate_gross_pnl,
        get_or_create_tag,
        normalize_tag_list,
    )

    trade = session.get(Trade, trade_id)
    if trade is None or trade.status != "OPEN":
        await send_text(chat_id, "❌ That trade is no longer open.")
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
    "<b>Accounts:</b> append <code>@alias</code> (e.g. <code>@ftmo100k-f1</code>). "
    "No suffix = last used account. Close/TSL without suffix + same symbol on 2 accounts → buttons.\n"
    "\n"
    "<b>OPEN a trade:</b>\n"
    "<code>buy SYMBOL, SIZE, ENTRY, SL, [TP], [#setup tags] [@alias]</code>\n"
    "e.g. <code>buy gold, 0.1, 4000, 3990, 4020, #fvg @ftmo100k-f1</code> (sell = short)\n"
    "Open @ a past time: add <code>time: 14:30</code> or <code>time: 2026-09-20 14:30</code>\n"
    "Times take an optional zone: <code>time: 2026-09-28 16:01 IST</code> (bare = UTC).\n"
    "Broker times work too once calibrated: <code>time: 2026-09-28 19:31 MT5</code> — see /brokertime.\n"
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
    "<code>past buy SYMBOL, SIZE, ENTRY, SL, [TP], exit: EXIT, pnl: PNL, date: OPEN [, exit_date: CLOSE]</code>\n"
    "e.g. <code>past sell gold, 0.05, 450.25, 450.87, exit: 450.43, pnl: -0.90, date: 2026-09-28 16:10:05 MT5, exit_date: 2026-09-28 16:39:06 MT5</code>\n"
    "(<code>date:</code> alone = open and close at the same time; seconds and MT5 zone supported)\n"
    "\n"
    "<b>CHART screenshots:</b> just send a photo — it attaches to your open trade "
    "(you pick one if several are open). Backfilled trades show a "
    "📸 Attach Chart button — tap it, then send the photo.\n"
    "\n"
    "<b>COMMANDS:</b>\n"
    "/start — greeting · /help — this guide · /open — list open trades · "
    "/accounts — prop accounts + status · "
    "/stats_daily — today's stats · /brokertime — set broker clock · /cancel — drop the pending question\n"
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
        account_id=args.get("account_id"),
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
    keyboard: Optional[dict] = None
    if trade is not None:
        r_txt = f"{trade.r_multiple:+.2f}R" if trade.r_multiple is not None else "n/a"
        net_txt = f"{trade.net_pnl:+.2f}" if trade.net_pnl is not None else "n/a"
        dur = trade.duration_minutes if trade.duration_minutes is not None else 0
        info = f" {net_txt} ({r_txt}), {trade.session}, {dur}m"
        keyboard = closed_trade_actions_keyboard(trade.id)
    await send_text(chat_id, f"📚 Backfilled {args['direction'].upper()} {args['symbol']} 🎫 {ticket}.{info}", keyboard)


# Breakeven tolerance mirrors the analytics API: |net| <= $5 is BE.
BE_TOLERANCE = 5.0


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


BROKER_SETUP_RE = re.compile(
    r"^MT5\s+(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}(?::\d{2})?)\s+IST\s+(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}(?::\d{2})?)\s*$",
    re.IGNORECASE,
)

BROKER_GUIDE = (
    "🕰️ <b>Broker clock setup</b>\n"
    "Send both readings of the <b>same instant</b>:\n"
    "<code>/brokertime MT5 YYYY-MM-DD HH:MM IST YYYY-MM-DD HH:MM</code>\n"
    "e.g. <code>/brokertime MT5 2026-09-28 19:31 IST 2026-09-28 21:31</code>\n"
    "After that, <code>time: … MT5</code> just works — no manual conversion."
)


async def handle_broker_clock(chat_id: int, text: str, session: Session) -> None:
    from app.services import broker_clock as _bc

    current = _bc.get_offset_minutes(session)
    status = (
        f"Current: <b>{_bc.format_label(current)}</b>."
        if current is not None
        else "Not set yet — <code>MT5</code> times will be rejected until set."
    )
    args = re.sub(r"^/\S+\s*", "", text.strip())
    if not args:
        await send_text(chat_id, BROKER_GUIDE + "\n" + status)
        return
    m = BROKER_SETUP_RE.match(args)
    if not m:
        await send_text(chat_id, f"❌ Couldn't parse that.\n{BROKER_GUIDE}\n{status}")
        return
    try:
        mt5_wall = _parse_wall_datetime(m.group(1))
        ist_wall = _parse_wall_datetime(m.group(2))
        minutes = _bc.calibrate(mt5_wall, ist_wall)
    except ValueError as exc:
        await send_text(chat_id, f"❌ {esc(exc)}")
        return
    _bc.set_offset_minutes(session, minutes)
    session.commit()
    utc_wall = mt5_wall - timedelta(minutes=minutes)
    await send_text(
        chat_id,
        f"🕰️ Broker clock: <b>{_bc.format_label(minutes)}</b> — "
        f"MT5 {mt5_wall.strftime('%H:%M')} = IST {ist_wall.strftime('%H:%M')} = "
        f"{utc_wall.strftime('%H:%M')} UTC on {mt5_wall.date().isoformat()}.",
    )


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
    if cmd == "/accounts":
        await handle_accounts(chat_id, session)
        return
    if cmd == "/brokertime":
        await handle_broker_clock(chat_id, body, session)
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
                cleaned_body, body_alias = extract_alias(body)
                args = parse_close(f"close {state['symbol']}, {cleaned_body}")
            except BotParseError as exc:
                await send_text(chat_id, f"❌ {exc} — or /cancel.")
                return
            trade_id = state["trade_id"]
            _pending.pop(chat_id, None)
            if body_alias is not None:
                acc = get_account_by_alias(session, body_alias)
                if acc is None:
                    await send_text(chat_id, f"❌ Unknown account @{esc(body_alias)}.")
                    return
                args["account_id"] = acc.id
                await do_close(chat_id, session, args)
            else:
                await do_close_on_trade(chat_id, session, trade_id, args)
            return
        if action == "photo":
            await send_text(chat_id, "📸 Send the chart image now — or /cancel.")
            return

    try:
        if re.match(r"(?i)^\s*past\s", body):
            cleaned, alias = extract_alias(body)
            account_id, account_alias = await _resolve_alias_for_text(chat_id, session, alias)
            if account_id is False:  # unknown alias, error already sent
                return
            parsed = parse_past(cleaned, _broker_offset(session))
            parsed["account_id"] = account_id
            parsed["account_alias"] = account_alias
            await do_past(chat_id, session, parsed)
        elif re.match(r"(?i)^\s*(buy|sell)\s", body):
            cleaned, alias = extract_alias(body)
            account_id, account_alias = await _resolve_alias_for_text(chat_id, session, alias)
            if account_id is False:
                return
            parsed = parse_open(cleaned, _broker_offset(session))
            parsed["account_id"] = account_id
            parsed["account_alias"] = account_alias
            await do_open(chat_id, session, parsed)
        elif re.match(r"(?i)^\s*tsl\s", body):
            cleaned, alias = extract_alias(body)
            account_id, _ = await _resolve_alias_for_text(chat_id, session, alias)
            if account_id is False:
                return
            args = parse_tsl(cleaned)
            await do_tsl(chat_id, session, args["symbol"], args["current_sl"], account_id)
        elif re.match(r"(?i)^\s*close\s", body):
            cleaned, alias = extract_alias(body)
            account_id, _ = await _resolve_alias_for_text(chat_id, session, alias)
            if account_id is False:
                return
            args = parse_close(cleaned)
            args["account_id"] = account_id
            await do_close(chat_id, session, args)
        else:
            await send_text(chat_id, "❓ Unknown command. " + HELP)
    except BotParseError as exc:
        await send_text(chat_id, f"❌ {exc}")


async def _resolve_alias_for_text(
    chat_id: int, session: Session, alias: Optional[str]
) -> tuple[Optional[int] | bool, Optional[str]]:
    """Map @alias (or last alias) to account_id. Returns (False, None) on unknown."""
    if alias is not None:
        acc = get_account_by_alias(session, alias)
        if acc is None:
            valid = list_account_aliases(session)
            hint = ", ".join(f"@{a}" for a in valid) if valid else "no accounts yet — create one in /accounts"
            await send_text(chat_id, f"❌ Unknown account @{esc(alias)}. Valid: {esc(hint)}")
            return False, None
        set_last_alias(session, acc.alias)
        assert acc.id is not None
        return acc.id, acc.alias
    last = get_last_alias(session)
    if last is None:
        return None, None
    acc = get_account_by_alias(session, last)
    if acc is None:
        return None, None
    assert acc.id is not None
    return acc.id, acc.alias


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


async def handle_callback(
    chat_id: int, callback_id: str, data: str, session: Session, message_id: Optional[int] = None
) -> None:
    from app.models import Trade

    # Accounts browser: paginated list (accs:N) and per-account detail (acc:ID).
    # Edits the same message; falls back to a new message if edit fails.
    if data.startswith("accs:") or data.startswith("acc:"):
        try:
            kind, raw = data.split(":", 1)
            num = int(raw)
        except ValueError:
            await _answer_callback(callback_id, "Bad button payload")
            return
        await _answer_callback(callback_id)
        try:
            rendered = (
                accounts_page_content(session, num)
                if kind == "accs"
                else account_detail_content(session, num)
            )
            if rendered is None:
                await send_text(
                    chat_id,
                    "📭 No accounts yet — add one in the web UI under Accounts."
                    if kind == "accs"
                    else "❌ Account not found.",
                )
                return
            text, keyboard = rendered
            if message_id is not None:
                try:
                    await edit_text(chat_id, message_id, text, keyboard)
                    return
                except Exception:
                    log.warning("editMessageText failed, sending fresh message", exc_info=True)
            await send_text(chat_id, text, keyboard)
        except Exception:
            log.exception("accounts browser failed")
            await send_text(chat_id, "❌ Couldn't load accounts.")
        return

    # Account-disambiguation picks carry the close/tsl intent in _pending.
    if data.startswith("closeid:") or data.startswith("tslid:"):
        try:
            _action, raw_id = data.split(":", 1)
            picked_id = int(raw_id)
        except ValueError:
            await _answer_callback(callback_id, "Bad button payload")
            return
        state = _pending.get(chat_id)
        if not state or state.get("action") not in ("close_pick", "tsl_pick"):
            await _answer_callback(callback_id, "Nothing pending")
            return
        _pending.pop(chat_id, None)
        await _answer_callback(callback_id, "Got it")
        if _action == "closeid":
            await do_close_on_trade(chat_id, session, picked_id, state["args"])
        else:
            trade = session.get(Trade, picked_id)
            if trade is None or trade.status != "OPEN":
                await send_text(chat_id, "❌ That trade is no longer open.")
                return
            trade.current_sl = state["new_sl"]
            trade.updated_at = _now()
            session.add(trade)
            session.commit()
            await send_text(chat_id, f"🛡️ TSL updated: {describe_trade(trade)}")
        return

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
        message_id = (cb.get("message") or {}).get("message_id")
        with Session(engine) as session:
            await handle_callback(chat_id, cb["id"], cb.get("data", ""), session, message_id)
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
            if text.strip() and re.match(r"(?i)^\s*(buy|sell|tsl|close|past|/open|/accounts|/cancel|/start|/help|/stats_daily|/stats)", text.strip()):
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
# register_commands() runs on every backend start, so new entries here land
# in Telegram's command list automatically after a restart.
COMMAND_MENU = [
    {"command": "start", "description": "Greet and get started"},
    {"command": "help", "description": "Full trade entry syntax guide"},
    {"command": "open", "description": "List your open trades"},
    {"command": "accounts", "description": "Prop accounts + status"},
    {"command": "stats_daily", "description": "Show today's trading stats"},
    {"command": "brokertime", "description": "Set broker clock offset (MT5 vs IST)"},
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
