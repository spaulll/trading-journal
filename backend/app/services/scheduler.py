"""Background scheduler: stale-trade nudges + EOD recap (PLAN-v2 Phase 3).

Jobs (AsyncIOScheduler, started in app.main lifespan):
  - check_stale_trades every 15 minutes (STALE_TRADE_HOURS env)
  - send_eod_recap daily at EOD_PROMPT_HOUR (server-local hour)

EOD prompt message ids are tracked so replies to the recap are saved
into daily_notes.eod_review (see maybe_handle_eod_reply, called from
telegram_bot._process_update).
"""

import logging
import os
from datetime import date as date_type
from datetime import datetime
from datetime import timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import Session, select

from app.models import DailyNote, Trade

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
    """Aggregate today's closed trades for the EOD recap."""
    day_start = datetime(today.year, today.month, today.day)
    closes = [
        t
        for t in session.exec(select(Trade).where(Trade.status == "CLOSED")).all()
        if (_as_naive_utc(t.timestamp_close) or datetime.min) >= day_start
    ]
    nets = [t.net_pnl or 0.0 for t in closes]
    wins = sum(1 for n in nets if n > 0)
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


async def send_eod_recap() -> dict:
    """Send the daily EOD prompt and remember its message id for replies."""
    from app.database import engine
    from app.services import telegram_bot

    today = _now().date()
    with Session(engine) as session:
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
    sched.add_job(
        send_eod_recap,
        "cron",
        hour=eod_hour,
        minute=0,
        id="eod_recap",
        max_instances=1,
        coalesce=True,
    )
    return sched


def job_summary(sched: AsyncIOScheduler) -> list[dict]:
    return [
        {"id": j.id, "next_run": j.next_run_time.isoformat() if j.next_run_time else None}
        for j in sched.get_jobs()
    ]
