"""Background scheduler: stale-trade nudges + EOD recap + weekly review.

Jobs (AsyncIOScheduler, started in app.main lifespan):
  - check_stale_trades every 15 minutes (STALE_TRADE_HOURS env)
  - send_eod_recap daily at EOD_PROMPT_HOUR (server-local hour)
  - send_weekly_review Monday morning (WEEKLY_REVIEW_DOW/HOUR/MINUTE, EOD_TZ)
    — generates, stores and pushes the review.

EOD prompt message ids are tracked so replies to the recap are saved
into daily_notes.eod_review (see maybe_handle_eod_reply, called from
telegram_bot._process_update).
"""

import logging
import os
import re
from datetime import date as date_type
from datetime import datetime
from datetime import timezone
from typing import Optional

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import Session, select

from app.models import DailyNote, Trade
from app.services.trade_money import usd_net

log = logging.getLogger("scheduler")

STALE_INTERVAL_MINUTES = 15

# Trade ids already nudged (per process lifetime; cleared when closed).
_alerted_stale: set[int] = set()
# EOD prompt message ids per calendar date, for reply matching.
_eod_prompt_msg_id: dict[date_type, int] = {}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _eod_tz():
    """EOD prompt timezone (EOD_TZ, default UTC). Falls back to UTC on bad names."""
    name = os.getenv("EOD_TZ", "UTC").strip() or "UTC"
    try:
        return pytz.timezone(name)
    except Exception:
        log.warning("bad EOD_TZ %r — falling back to UTC", name)
        return pytz.UTC


def _as_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _fmt_duration(opened: datetime, now: datetime) -> str:
    secs = max(0, int((now - opened).total_seconds()))
    hours, rem = divmod(secs, 3600)
    mins = rem // 60
    if hours:
        return f"{hours}h {mins:02d}m"
    return f"{mins}m"


def stale_keyboard(trade_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "🛡️ Update TSL", "callback_data": f"tsl:{trade_id}"},
                {"text": "🏁 Close Trade", "callback_data": f"close:{trade_id}"},
            ],
            [{"text": "🔕 Snooze 2h", "callback_data": f"snooze:{trade_id}"}],
        ]
    }


async def check_stale_trades() -> dict:
    """Nudge for OPEN trades older than STALE_TRADE_HOURS. Returns stats."""
    from app.database import engine
    from app.services import telegram_bot

    stale_hours = _env_float("STALE_TRADE_HOURS", 4.0)
    now = _now()
    nudged: list[int] = []
    with Session(engine) as session:
        opens = session.exec(select(Trade).where(Trade.status == "OPEN")).all()
        # Drop ids that are no longer open (closed since last run).
        open_ids = {t.id for t in opens}
        _alerted_stale.intersection_update(open_ids)
        for trade in opens:
            opened = _as_naive_utc(trade.timestamp_open) or _as_naive_utc(trade.created_at)
            if opened is None:
                continue
            age_hours = (now.replace(tzinfo=None) - opened).total_seconds() / 3600
            if age_hours < stale_hours:
                continue
            if trade.id in _alerted_stale:
                continue
            if telegram_bot.is_snoozed(trade.id):
                continue
            dur = _fmt_duration(opened, now.replace(tzinfo=None))
            try:
                await telegram_bot.notify(
                    f"⏳ STALE TRADE: {trade.direction.upper()} {trade.symbol} {trade.size} "
                    f"has been open for {dur}. Did you exit on MT5?",
                    stale_keyboard(trade.id),
                )
            except Exception:
                log.exception("stale nudge failed for trade %s", trade.id)
                continue
            _alerted_stale.add(trade.id)
            nudged.append(trade.id)
    return {"nudged": nudged}


def eod_summary_text(session: Session, today: date_type) -> str:
    """Aggregate the trading day's closed trades for the EOD recap."""
    from app.services.trading_day import trading_day_bounds

    day_start, day_end = trading_day_bounds(session, today)
    closes = [
        t
        for t in session.exec(select(Trade).where(Trade.status == "CLOSED")).all()
        if day_start <= (_as_naive_utc(t.timestamp_close) or datetime.min) < day_end
    ]
    nets = [usd_net(t) or 0.0 for t in closes]
    wins = sum(1 for n in nets if n > 5.0)
    total = len(closes)
    pnl = sum(nets)
    wr = f"{wins / total * 100:.0f}%" if total else "n/a"
    lines = [
        f"🌙 EOD Recap {today.isoformat()}: {total} closed, {wr} win rate, {pnl:+.2f} net.",
    ]
    missing = [t for t in closes if not t.tags or not t.review_notes]
    if missing:
        tickets = ", ".join(t.ticket for t in missing)
        lines.append(f"📝 Missing tags/notes: {tickets}.")
    lines.append("Reply to this message with your EOD reflection to save today's journal review.")
    return "\n".join(lines)


def _trades_today(session: Session, today: date_type) -> tuple[list, list]:
    """Trades opened / closed on `today` (configured trading-day bounds)."""
    from app.services.trading_day import trading_day_bounds

    day_start, day_end = trading_day_bounds(session, today)
    all_trades = session.exec(select(Trade)).all()
    opened = [
        t
        for t in all_trades
        if day_start
        <= (_as_naive_utc(t.entry_time) or _as_naive_utc(t.timestamp_open) or datetime.min)
        < day_end
    ]
    closed = [
        t
        for t in all_trades
        if t.status == "CLOSED"
        and day_start <= (_as_naive_utc(t.timestamp_close) or datetime.min) < day_end
    ]
    return opened, closed


async def send_eod_recap() -> dict:
    """Send the daily EOD prompt and remember its message id for replies.

    Skipped entirely on days with no trade activity (nothing opened or
    closed) — no message, no journal row.
    """
    from app.database import engine
    from app.services import telegram_bot

    with Session(engine) as session:
        from app.services.trading_day import current_trading_day

        today = current_trading_day(session)
        opened, _closed = _trades_today(session, today)
        if not opened and not _closed:
            return {"sent": False, "reason": "no_trades"}
        text = eod_summary_text(session, today)
        note = session.exec(select(DailyNote).where(DailyNote.date == today)).first()
        if note is None:
            note = DailyNote(date=today)
            session.add(note)
            session.commit()
        try:
            msg_id = await telegram_bot.notify(text)
        except Exception:
            log.exception("EOD recap send failed")
            return {"sent": False}
    if msg_id is not None:
        _eod_prompt_msg_id[today] = msg_id
        return {"sent": True, "message_id": msg_id}
    return {"sent": False}


async def maybe_handle_eod_reply(chat_id: int, msg: dict, session: Session) -> bool:
    """Save replies to the EOD prompt into daily_notes.eod_review."""
    from app.services import telegram_bot

    reply = msg.get("reply_to_message") or {}
    replied_id = reply.get("message_id")
    if replied_id is None:
        return False
    matched: Optional[date_type] = next(
        (d for d, mid in _eod_prompt_msg_id.items() if mid == replied_id), None
    )
    if matched is None:
        return False
    text = (msg.get("text") or "").strip()
    if not text:
        return False
    note = session.exec(select(DailyNote).where(DailyNote.date == matched)).first()
    if note is None:
        note = DailyNote(date=matched)
    stamp = _now().strftime("%H:%M")
    note.eod_review = f"{note.eod_review}\n[{stamp}] {text}".strip() if note.eod_review else text
    note.updated_at = _now()
    session.add(note)
    session.commit()
    await telegram_bot.send_text(chat_id, f"✅ EOD review saved for {matched.isoformat()}.")
    return True


# Telegram rejects a message longer than 4096 UTF-16 units; leave headroom
# for emoji and entities, and split on line boundaries where possible.
TG_TEXT_LIMIT = 3500

_TG_HEADING_RE = re.compile(r"^#{1,6}[ \t]+(.+)$", re.MULTILINE)
_TG_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def telegram_chunks(text: str, limit: int = TG_TEXT_LIMIT) -> list[str]:
    """Split text into Telegram-sized messages without cutting a line first."""
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return [c for c in chunks if c.strip()]


def weekly_review_text(report) -> str:
    """Render stored markdown as Telegram HTML for the Monday push.

    The LLM writes markdown; Telegram renders HTML only. Escape first so the
    trader's own text can never inject a tag, then turn headings and **bold**
    into Telegram's equivalents. Tables stay as plain rows.
    """
    from app.services.telegram_bot import esc

    body = esc((report.markdown or "").strip())
    body = _TG_HEADING_RE.sub(r"\n<b>\1</b>", body)
    body = _TG_BOLD_RE.sub(r"<b>\1</b>", body)
    title = f"📊 <b>Weekly review</b> · {report.date_from:%d %b} – {report.date_to:%d %b %Y}\n"
    return title + body.strip()


async def send_weekly_review() -> dict:
    """Generate, store and push the Monday review of the last completed week.

    The LLM is optional: with no key configured the job is a quiet no-op, so
    a journal that never set one does not log a failed job every week. The
    review is stored before the push, so a Telegram failure never loses it.
    """
    from app.database import engine
    from app.services import telegram_bot, weekly_review

    if not weekly_review.llm_configured():
        log.info("weekly review skipped: LLM_API_KEY is not configured")
        return {"status": "skipped", "reason": "llm_not_configured"}
    try:
        with Session(engine) as session:
            result = weekly_review.generate_weekend_review(session)
            text = weekly_review_text(result["report"]) if result["status"] == "ok" else None
    except Exception:
        log.exception("weekly review failed")
        return {"status": "error"}
    log.info(
        "weekly review %s for %s..%s",
        result["status"],
        result["date_from"],
        result["date_to"],
    )
    if text is None:
        return result

    if not telegram_bot.is_configured():
        log.warning("weekly review stored but Telegram is not configured")
        return {**result, "pushed": False, "reason": "telegram_not_configured"}

    delivered = 0
    try:
        for chunk in telegram_chunks(text):
            if await telegram_bot.notify(chunk) is not None:
                delivered += 1
    except Exception:
        log.exception("weekly review stored but the Telegram push failed")
        return {**result, "pushed": False, "chunks": delivered}
    log.info("weekly review pushed in %s message(s)", delivered)
    return {**result, "pushed": delivered > 0, "chunks": delivered}


def build_scheduler() -> AsyncIOScheduler:
    sched = AsyncIOScheduler()
    sched.add_job(
        check_stale_trades,
        "interval",
        minutes=STALE_INTERVAL_MINUTES,
        id="stale_trades",
        max_instances=1,
        coalesce=True,
    )
    eod_hour = _env_int("EOD_PROMPT_HOUR", 21)
    eod_minute = _env_int("EOD_PROMPT_MINUTE", 0)
    sched.add_job(
        send_eod_recap,
        "cron",
        hour=eod_hour,
        minute=eod_minute,
        timezone=_eod_tz(),
        id="eod_recap",
        max_instances=1,
        coalesce=True,
    )
    # Monday morning, in the same timezone the EOD prompt uses. `default_week`
    # always resolves to the Mon–Fri that just ended, so a Monday 07:00 run
    # reviews last week rather than a partial one.
    sched.add_job(
        send_weekly_review,
        "cron",
        day_of_week=os.getenv("WEEKLY_REVIEW_DOW", "mon").strip() or "mon",
        hour=_env_int("WEEKLY_REVIEW_HOUR", 7),
        minute=_env_int("WEEKLY_REVIEW_MINUTE", 0),
        timezone=_eod_tz(),
        id="weekly_review",
        max_instances=1,
        coalesce=True,
    )
    return sched


def job_summary(sched: AsyncIOScheduler) -> list[dict]:
    return [
        {"id": j.id, "next_run": j.next_run_time.isoformat() if j.next_run_time else None}
        for j in sched.get_jobs()
    ]
