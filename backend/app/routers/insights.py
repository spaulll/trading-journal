"""LLM weekend-review summaries (PLAN-v2 insights).

Manual trigger only: POST /api/insights/weekend-review gathers the week's
trade notes (thesis / review_notes / !mistake tags) plus daily notes
(pre_market / eod_review), sends them to an OpenAI-compatible chat API, and
stores the markdown summary in `insight_report` for history tracking.

Secrets live in backend/.env (LLM_BASE_URL / LLM_API_KEY / LLM_MODEL) and
never leave the server — the frontend only receives rendered markdown.
"""

import os
from datetime import date as date_type
from datetime import timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.database import get_session
from app.models import DailyNote, InsightReport, InsightReportRead, Trade, WeekendReviewRequest
from app.services.timeutils import trade_close_day

router = APIRouter(prefix="/api/insights", tags=["insights"])


def _llm_settings() -> tuple[str, str, str]:
    base = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    if not key:
        raise HTTPException(
            status_code=503,
            detail="LLM_API_KEY is not configured — add it to backend/.env",
        )
    return base, key, model


def default_week(today: Optional[date_type] = None) -> tuple[date_type, date_type]:
    """Last completed Mon–Fri trading week for `today`.

    Weekend (Sat/Sun) → the Mon–Fri that just ended. Weekday → the
    previous week's Mon–Fri, so a mid-week click never summarizes a
    partial week by default.
    """
    today = today or date_type.today()
    wd = today.weekday()  # Mon=0 … Sun=6
    monday = today - timedelta(days=wd) if wd >= 5 else today - timedelta(days=wd + 7)
    return monday, monday + timedelta(days=4)


def _collect_week(
    session: Session, date_from: date_type, date_to: date_type
) -> tuple[list[Trade], list[DailyNote]]:
    trades = [
        t
        for t in session.exec(select(Trade).where(Trade.status == "CLOSED")).all()
        if (d := trade_close_day(t)) is not None and date_from <= d.date() <= date_to
    ]
    notes = session.exec(
        select(DailyNote)
        .where(DailyNote.date >= date_from)
        .where(DailyNote.date <= date_to)
        .order_by(DailyNote.date.asc())
    ).all()
    return trades, notes


def _has_content(trades: list[Trade], notes: list[DailyNote]) -> bool:
    if any((n.pre_market or "").strip() or (n.eod_review or "").strip() for n in notes):
        return True
    for t in trades:
        if (t.thesis or "").strip() or (t.review_notes or "").strip():
            return True
        if any(tag.category == "mistake" for tag in t.tags):
            return True
    return False


def _stats_block(trades: list[Trade]) -> str:
    wins = sum(1 for t in trades if (t.net_pnl or 0) > 0)
    losses = sum(1 for t in trades if (t.net_pnl or 0) < 0)
    net = sum(t.net_pnl or 0 for t in trades)
    r_vals = [t.r_multiple for t in trades if t.r_multiple is not None]
    avg_r = sum(r_vals) / len(r_vals) if r_vals else None
    mistakes: dict[str, int] = {}
    sessions: dict[str, int] = {}
    for t in trades:
        for tag in t.tags:
            if tag.category == "mistake":
                mistakes[tag.name] = mistakes.get(tag.name, 0) + 1
        if t.session:
            sessions[t.session] = sessions.get(t.session, 0) + 1
    lines = [
        f"Closed trades: {len(trades)} ({wins}W / {losses}L / {len(trades) - wins - losses}BE)",
        f"Net PnL: {net:+.2f}",
        f"Avg R: {avg_r:+.2f}" if avg_r is not None else "Avg R: n/a",
    ]
    if mistakes:
        top = sorted(mistakes.items(), key=lambda kv: -kv[1])
        lines.append("Mistake tags: " + ", ".join(f"!{k} x{v}" for k, v in top))
    if sessions:
        lines.append("Sessions: " + ", ".join(f"{k} x{v}" for k, v in sorted(sessions.items())))
    return "\n".join(lines)


def _trade_lines(trades: list[Trade]) -> str:
    out = []
    for t in sorted(trades, key=lambda x: trade_close_day(x) or x.timestamp_open):
        day = trade_close_day(t)
        tags = " ".join(
            f"{'!' if tag.category == 'mistake' else '#'}{tag.name}" for tag in t.tags
        )
        bits = [
            f"{day.date() if day else '?'}",
            f"{t.symbol or '?'} {t.direction or ''}".strip(),
            f"net {t.net_pnl if t.net_pnl is not None else '?'}",
            f"R {t.r_multiple if t.r_multiple is not None else '?'}",
        ]
        if tags:
            bits.append(f"tags: {tags}")
        if (t.thesis or "").strip():
            bits.append(f"thesis: {t.thesis.strip()[:500]}")
        if (t.review_notes or "").strip():
            bits.append(f"review: {t.review_notes.strip()[:500]}")
        out.append("- " + " | ".join(bits))
    return "\n".join(out)


def _notes_block(notes: list[DailyNote]) -> str:
    out = []
    for n in notes:
        parts = [str(n.date)]
        if n.discipline_breach:
            parts.append("[discipline breach]")
        if (n.pre_market or "").strip():
            parts.append(f"plan: {n.pre_market.strip()[:800]}")
        if (n.eod_review or "").strip():
            parts.append(f"eod: {n.eod_review.strip()[:800]}")
        if len(parts) > 1 + (1 if n.discipline_breach else 0):
            out.append("- " + " | ".join(parts))
    return "\n".join(out)


SYSTEM_PROMPT = (
    "You are a trading coach reviewing a retail trader's week. "
    "Be direct, specific, and reference their actual trades and notes — "
    "no generic advice. Format the response in markdown using ONLY "
    "### headings, **bold**, and - bullet lists: no tables, no code "
    "blocks, no horizontal rules. Use exactly these sections: "
    "### Top errors (bullets with trade evidence), "
    "### What worked (bullets of strengths to keep), "
    "### One fix for next week (a single concrete behavior change). "
    "Keep it under 350 words."
)


def _build_prompt(trades: list[Trade], notes: list[DailyNote]) -> str:
    parts = ["WEEK STATS (all accounts blended):", _stats_block(trades)]
    trade_lines = _trade_lines(trades)
    if trade_lines:
        parts += ["", "TRADES (with notes and tags):", trade_lines]
    notes_text = _notes_block(notes)
    if notes_text:
        parts += ["", "DAILY NOTES (plan vs evening review):", notes_text]
    parts.append(
        "\nSummarize this trader's errors and strengths for the week, "
        "and give one concrete fix for next week."
    )
    return "\n".join(parts)


def _call_llm(prompt: str) -> str:
    base, key, model = _llm_settings()
    try:
        max_tokens = int(os.getenv("LLM_MAX_TOKENS", "1200"))
    except ValueError:
        max_tokens = 1200
    try:
        timeout_s = float(os.getenv("LLM_TIMEOUT_S", "120"))
    except ValueError:
        timeout_s = 120.0
    try:
        resp = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": max_tokens,
            },
            timeout=timeout_s,
        )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {e}") from e
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502, detail=f"LLM API error ({resp.status_code}): {resp.text[:300]}"
        )
    try:
        text = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as e:
        raise HTTPException(status_code=502, detail="LLM API returned an unexpected shape") from e
    return (text or "").strip()


@router.post("/weekend-review")
def weekend_review(payload: WeekendReviewRequest, session: Session = Depends(get_session)):
    date_from, date_to = payload.date_from, payload.date_to
    if date_from is None or date_to is None:
        date_from, date_to = default_week()
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be <= date_to")
    trades, notes = _collect_week(session, date_from, date_to)
    if not _has_content(trades, notes):
        return {
            "status": "empty",
            "date_from": date_from,
            "date_to": date_to,
            "detail": "No trade notes, mistake tags, or daily notes this week — nothing to summarize.",
        }
    _base, _key, model = _llm_settings()  # fail fast before the call, no secret leakage
    markdown = _call_llm(_build_prompt(trades, notes))
    report = InsightReport(date_from=date_from, date_to=date_to, markdown=markdown, model=model)
    session.add(report)
    session.commit()
    session.refresh(report)
    return {
        "status": "ok",
        "date_from": date_from,
        "date_to": date_to,
        "report": InsightReportRead.model_validate(report.model_dump()),
    }


@router.get("/reports", response_model=list[InsightReportRead])
def list_reports(
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    rows = session.exec(
        select(InsightReport).order_by(InsightReport.created_at.desc()).limit(limit)
    ).all()
    return [InsightReportRead.model_validate(r.model_dump()) for r in rows]
