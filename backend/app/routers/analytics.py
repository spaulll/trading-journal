"""Analytics endpoints (PLAN Task 4.1, PLAN-v2 Task 4.1).

v1 endpoints (summary, equity-curve, r-distribution, tag-performance,
calendar) power the current dashboard. v2 TradeZella endpoints
(kpi-dashboard, monthly-calendar, activity-and-streaks, long-short-stats,
radar-profiles) power the Phase 4 widgets.
"""

from collections import defaultdict
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from math import floor
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.database import get_session
from app.models import Tag, Trade, TradeTagLink
from app.services.timeutils import as_naive_utc, trade_close_day

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _closed_trades(session: Session, account_id: Optional[int] = None) -> list[Trade]:
    statement = (
        select(Trade)
        .where(Trade.status == "CLOSED")
        .order_by(Trade.timestamp_close.asc(), Trade.id.asc())
    )
    if account_id is not None:
        statement = statement.where(Trade.account_id == account_id)
    trades = list(session.exec(statement).all())
    # Rows without a close timestamp sort first under ASC with NULLs;
    # keep chronological order by pushing NULL timestamps to the end.
    trades.sort(key=lambda t: (t.timestamp_close is None, t.timestamp_close, t.id or 0))
    return trades


# --- v2 shared helpers (TradeZella widgets) ---

TARGET_RR = 2.0

# Killzone hour bounds (UTC) — [start, end).
SESSION_BOUNDS = {"london": (7, 13), "new_york": (13, 22), "asia": (0, 6)}


def _as_naive(dt: Optional[datetime]) -> Optional[datetime]:
    """Back-compat alias — single source is app.services.timeutils.as_naive_utc."""
    return as_naive_utc(dt)


def _close_day(t: Trade) -> Optional[datetime]:
    """Back-compat alias — single source is app.services.timeutils.trade_close_day."""
    return trade_close_day(t)


def _session_of(t: Trade) -> str:
    stored = (t.session or "").strip().lower()
    if stored in ("london", "new_york", "newyork", "asia", "outside"):
        return "new_york" if stored == "newyork" else stored
    ts = _as_naive(t.entry_time) or _as_naive(t.timestamp_open) or _as_naive(t.timestamp_close)
    if ts is None:
        return "outside"
    for name, (start, end) in SESSION_BOUNDS.items():
        if start <= ts.hour < end:
            return name
    return "outside"


# Breakeven rule (shared everywhere): |net_pnl| <= BE_TOLERANCE counts as
# breakeven, not a win/loss. Small wins/losses within the tolerance band
# (commissions/slippage dust, scratch exits) must not flip the outcome
# donut, monthly calendar, or long/short stats. Tolerance is $5 —
# any trade netting 0–$5 profit or 0–$5 loss is BE.
BE_TOLERANCE = 5.0


def _is_win(net: float) -> bool:
    return net > BE_TOLERANCE


def _is_loss(net: float) -> bool:
    return net < -BE_TOLERANCE


def _is_be(net: float) -> bool:
    return abs(net) <= BE_TOLERANCE


def _sign(net: float) -> int:
    if _is_win(net):
        return 1
    if _is_loss(net):
        return -1
    return 0


def _normalize_direction(raw: object) -> str | None:
    """Map stored direction to long/short buckets. UI Long ↔ `buy`, Short ↔ `sell`.
    Accepts `long`/`short` aliases; unknown/empty values return None and are ignored."""
    s = str(raw or "").strip().lower()
    if s in ("buy", "long"):
        return "buy"
    if s in ("sell", "short"):
        return "sell"
    return None


def _win_loss_counts(nets: list[float]) -> tuple[int, int, int]:
    wins = sum(1 for n in nets if _is_win(n))
    losses = sum(1 for n in nets if _is_loss(n))
    return wins, losses, len(nets) - wins - losses


def _profit_factor(nets: list[float]) -> Optional[float]:
    gross_profit = sum(n for n in nets if _is_win(n))
    gross_loss = abs(sum(n for n in nets if _is_loss(n)))
    return round(gross_profit / gross_loss, 3) if gross_loss else None


def _streak_runs(signs: list[int]) -> tuple[list[int], list[int]]:
    """Split a sign sequence (+1/-1/0) into win-run and loss-run lengths."""
    win_runs, loss_runs = [], []
    cur, cur_sign = 0, 0
    for s in signs + [0]:
        if s != 0 and s == cur_sign:
            cur += 1
        else:
            if cur_sign > 0:
                win_runs.append(cur)
            elif cur_sign < 0:
                loss_runs.append(cur)
            cur_sign, cur = (s, 1) if s != 0 else (0, 0)
    return win_runs, loss_runs


def _downsample(values: list[float], limit: int = 30) -> list[float]:
    if len(values) <= limit:
        return values
    step = len(values) / limit
    return [values[min(len(values) - 1, int(i * step))] for i in range(limit)]


def _equity_points(trades: list[Trade]) -> list[dict]:
    points: list[dict] = []
    equity = 0.0
    peak = 0.0
    for t in trades:
        net = t.net_pnl if t.net_pnl is not None else 0.0
        equity += net
        peak = max(peak, equity)
        ts = t.timestamp_close or t.timestamp_open or t.created_at
        points.append(
            {
                "timestamp": ts.isoformat() if isinstance(ts, datetime) else str(ts),
                "equity": round(equity, 2),
                "drawdown": round(equity - peak, 2),
                "net_pnl": net,
                "trade_id": t.ticket,
            }
        )
    return points


@router.get("/summary")
def summary(account_id: Optional[int] = Query(default=None), session: Session = Depends(get_session)):
    trades = _closed_trades(session, account_id)
    nets = [t.net_pnl if t.net_pnl is not None else 0.0 for t in trades]
    total = len(trades)
    wins = [n for n in nets if _is_win(n)]
    losses = [n for n in nets if _is_loss(n)]
    net_pnl = round(sum(nets), 2)
    win_rate = round(len(wins) / total * 100, 2) if total else 0.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = round(gross_profit / gross_loss, 3) if gross_loss else None
    expectancy = round(net_pnl / total, 2) if total else 0.0
    avg_win = round(gross_profit / len(wins), 2) if wins else 0.0
    avg_loss = round(sum(losses) / len(losses), 2) if losses else 0.0

    points = _equity_points(trades)
    max_dd = min((p["drawdown"] for p in points), default=0.0)

    open_stmt = select(Trade).where(Trade.status == "OPEN")
    if account_id is not None:
        open_stmt = open_stmt.where(Trade.account_id == account_id)
    open_count = len(session.exec(open_stmt).all())
    return {
        "total_trades": total,
        "open_trades": open_count,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": total - len(wins) - len(losses),
        "net_pnl": net_pnl,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "max_drawdown": max_dd,
    }


@router.get("/equity-curve")
def equity_curve(account_id: Optional[int] = Query(default=None), session: Session = Depends(get_session)):
    return {"points": _equity_points(_closed_trades(session, account_id))}


_R_BUCKETS = ["-2R", "-1R", "0R", "1R", "2R", "3R+"]


def _r_bucket(r: float) -> str:
    bucket = floor(r + 0.5)  # nearest integer, so -1.06 -> -1R, 0.97 -> 1R
    if bucket <= -2:
        return "-2R"
    if bucket >= 3:
        return "3R+"
    return f"{bucket}R"


@router.get("/r-distribution")
def r_distribution(account_id: Optional[int] = Query(default=None), session: Session = Depends(get_session)):
    counts: dict[str, int] = {b: 0 for b in _R_BUCKETS}
    for t in _closed_trades(session, account_id):
        if t.r_multiple is None:
            continue
        counts[_r_bucket(t.r_multiple)] += 1
    return {"buckets": [{"label": b, "count": counts[b]} for b in _R_BUCKETS]}


@router.get("/tag-performance")
def tag_performance(account_id: Optional[int] = Query(default=None), session: Session = Depends(get_session)):
    tags = session.exec(select(Tag)).all()
    rows = []
    for tag in tags:
        link_stmt = select(Trade).where(
                Trade.id.in_(
                    select(TradeTagLink.trade_id).where(TradeTagLink.tag_id == tag.id)
                ),
                Trade.status == "CLOSED",
            )
        if account_id is not None:
            link_stmt = link_stmt.where(Trade.account_id == account_id)
        link_rows = session.exec(link_stmt).all()
        nets = [t.net_pnl if t.net_pnl is not None else 0.0 for t in link_rows]
        wins = sum(1 for n in nets if _is_win(n))
        rows.append(
            {
                "name": tag.name,
                "category": tag.category,
                "trade_count": len(link_rows),
                "net_pnl": round(sum(nets), 2),
                "win_rate": round(wins / len(nets) * 100, 2) if nets else 0.0,
            }
        )
    rows.sort(key=lambda r: r["net_pnl"], reverse=True)
    return {"tags": rows}


@router.get("/calendar")
def calendar(
    year: Optional[int] = Query(default=None, description="Defaults to current year"),
    account_id: Optional[int] = Query(default=None),
    session: Session = Depends(get_session),
):
    target_year = year or datetime.now().year
    daily: dict[str, dict] = defaultdict(lambda: {"net_pnl": 0.0, "trade_count": 0})
    for t in _closed_trades(session, account_id):
        # Naive-UTC close day (same helper as monthly-calendar / streaks) so
        # day boundaries never mix aware vs naive timestamps.
        day = _close_day(t)
        if day is None or day.year != target_year:
            continue
        key = day.date().isoformat()
        daily[key]["net_pnl"] += t.net_pnl if t.net_pnl is not None else 0.0
        daily[key]["trade_count"] += 1
    days = [
        {"date": date, "net_pnl": round(v["net_pnl"], 2), "trade_count": v["trade_count"]}
        for date, v in sorted(daily.items())
    ]
    return {"year": target_year, "days": days}


# --- v2 TradeZella endpoints (Phase 4) ---


@router.get("/kpi-dashboard")
def kpi_dashboard(account_id: Optional[int] = Query(default=None), session: Session = Depends(get_session)):
    trades = _closed_trades(session, account_id)
    nets = [t.net_pnl if t.net_pnl is not None else 0.0 for t in trades]
    net_pnl = round(sum(nets), 2)
    wins, losses, be = _win_loss_counts(nets)
    total = len(trades)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    last30 = sum(
        (t.net_pnl or 0.0)
        for t in trades
        if (_close_day(t) or datetime.min) >= now - timedelta(days=30)
    )
    prev30 = sum(
        (t.net_pnl or 0.0)
        for t in trades
        if now - timedelta(days=60) <= (_close_day(t) or datetime.min) < now - timedelta(days=30)
    )
    change_pct = round((last30 - prev30) / abs(prev30) * 100, 2) if prev30 else None

    equity = _downsample([round(v, 2) for v in _cumulative(nets)])

    rr_vals = [t.r_multiple for t in trades if t.r_multiple is not None]
    avg_rr = round(sum(rr_vals) / len(rr_vals), 3) if rr_vals else 0.0

    sessions: dict[str, dict] = {}
    total_net_abs = sum(abs(t.net_pnl or 0.0) for t in trades) or None
    for name in ("london", "new_york", "asia", "outside"):
        bucket = [t for t in trades if _session_of(t) == name]
        bnets = [t.net_pnl or 0.0 for t in bucket]
        bwins = sum(1 for n in bnets if _is_win(n))
        bnet = round(sum(bnets), 2)
        sessions[name] = {
            "net_pnl": bnet,
            "trade_count": len(bucket),
            "win_rate": round(bwins / len(bucket) * 100, 2) if bucket else 0.0,
            "return_pct": round(bnet / total_net_abs * 100, 2) if total_net_abs else 0.0,
        }

    return {
        "net_pnl": net_pnl,
        "net_pnl_change_pct": change_pct,
        "sparkline": equity,
        "avg_realized_rr": {"current": avg_rr, "target": TARGET_RR},
        "win_rate": {
            "rate": round(wins / total * 100, 2) if total else 0.0,
            "wins": wins,
            "losses": losses,
            "breakeven": be,
        },
        "profit_factor": _profit_factor(nets),
        "sessions": sessions,
    }


def _cumulative(nets: list[float]) -> list[float]:
    out, run = [], 0.0
    for n in nets:
        run += n
        out.append(run)
    return out


@router.get("/monthly-calendar")
def monthly_calendar(
    year: Optional[int] = Query(default=None),
    month: Optional[int] = Query(default=None, ge=1, le=12),
    account_id: Optional[int] = Query(default=None),
    session: Session = Depends(get_session),
):
    now = datetime.now()
    y, m = year or now.year, month or now.month
    month_start = date_type(y, m, 1)
    month_end = date_type(y + (m == 12), (m % 12) + 1, 1)

    daily: dict[str, dict] = defaultdict(lambda: {"net_pnl": 0.0, "trade_count": 0})
    for t in _closed_trades(session, account_id):
        day = _close_day(t)
        if day is None or not (month_start <= day.date() < month_end):
            continue
        key = day.date().isoformat()
        daily[key]["net_pnl"] += t.net_pnl if t.net_pnl is not None else 0.0
        daily[key]["trade_count"] += 1

    days: dict[str, dict] = {}
    day_cursor = month_start
    while day_cursor < month_end:
        key = day_cursor.isoformat()
        v = daily.get(key, {"net_pnl": 0.0, "trade_count": 0})
        net = round(v["net_pnl"], 2)
        if v["trade_count"] == 0:
            outcome = "inactive"
        elif _is_win(net):
            outcome = "win"
        elif _is_loss(net):
            outcome = "loss"
        else:
            outcome = "be"
        days[key] = {"net_pnl": net, "trade_count": v["trade_count"], "outcome": outcome}
        day_cursor += timedelta(days=1)

    weeks = []
    for w in range(5):
        lo, hi = w * 7 + 1, w * 7 + 7
        wdays = [d for k, d in days.items() if lo <= int(k[8:10]) <= hi]
        weeks.append(
            {
                "label": f"Week {w + 1}",
                "net_pnl": round(sum(d["net_pnl"] for d in wdays), 2),
                "trade_count": sum(d["trade_count"] for d in wdays),
            }
        )

    active = [d for d in days.values() if d["trade_count"] > 0]
    won = sum(1 for d in active if d["outcome"] == "win")
    lost = sum(1 for d in active if d["outcome"] == "loss")
    be_days = sum(1 for d in active if d["outcome"] == "be")
    return {
        "year": y,
        "month": m,
        "weeks": weeks,
        "days": days,
        "summary": {
            "trading_days": len(active),
            "day_win_rate": round(won / len(active) * 100, 2) if active else 0.0,
            "winning_days": won,
            "losing_days": lost,
            "breakeven_days": be_days,
        },
        "outcome": {"wins": won, "losses": lost, "breakeven": be_days},
    }


@router.get("/activity-and-streaks")
def activity_and_streaks(account_id: Optional[int] = Query(default=None), session: Session = Depends(get_session)):
    trades = _closed_trades(session, account_id)
    nets = [t.net_pnl if t.net_pnl is not None else 0.0 for t in trades]
    signs = [_sign(n) for n in nets]
    win_runs, loss_runs = _streak_runs(signs)

    daily: dict[str, float] = defaultdict(float)
    volume: dict[str, float] = defaultdict(float)
    for t in trades:
        day = _close_day(t)
        if day is None:
            continue
        key = day.date().isoformat()
        daily[key] += t.net_pnl if t.net_pnl is not None else 0.0
        volume[key] += t.size or 0.0
    ordered_days = sorted(daily)
    day_signs = [_sign(daily[d]) for d in ordered_days]
    # Calendar-consecutive same-sign day runs (gaps and BE break the run).
    max_wdays = max_ldays = 0
    cur, cur_sign, prev = 0, 0, None
    for d, s in zip(ordered_days, day_signs):
        consecutive = prev is not None and (
            date_type.fromisoformat(d) - date_type.fromisoformat(prev)
        ).days == 1
        if s != 0 and s == cur_sign and consecutive:
            cur += 1
        else:
            cur, cur_sign = (1, s) if s != 0 else (0, 0)
        max_wdays = max(max_wdays, cur if cur_sign > 0 else 0)
        max_ldays = max(max_ldays, cur if cur_sign < 0 else 0)
        prev = d

    wins, losses, _be = _win_loss_counts(nets)
    _open_stmt = select(Trade).where(Trade.status == "OPEN")
    if account_id is not None:
        _open_stmt = _open_stmt.where(Trade.account_id == account_id)
    open_count = len(session.exec(_open_stmt).all())
    best = max(trades, key=lambda t: t.net_pnl or 0.0, default=None)
    worst = min(trades, key=lambda t: t.net_pnl or 0.0, default=None)
    return {
        "total_trades": len(trades),
        "open_trades": open_count,
        "closed_trades": len(trades),
        "winning_trades": wins,
        "losing_trades": losses,
        "max_win_streak": max(win_runs, default=0),
        "max_loss_streak": max(loss_runs, default=0),
        "avg_win_streak": round(sum(win_runs) / len(win_runs), 2) if win_runs else 0.0,
        "avg_loss_streak": round(sum(loss_runs) / len(loss_runs), 2) if loss_runs else 0.0,
        "max_winning_days": max_wdays,
        "max_losing_days": max_ldays,
        "trading_days": len(ordered_days),
        "avg_daily_volume": round(sum(volume.values()) / len(volume), 3) if volume else 0.0,
        "best_trade": {"ticket": best.ticket, "net_pnl": best.net_pnl} if best else None,
        "worst_trade": {"ticket": worst.ticket, "net_pnl": worst.net_pnl} if worst else None,
    }


def _direction_stats(trades: list[Trade]) -> dict:
    nets = [t.net_pnl if t.net_pnl is not None else 0.0 for t in trades]
    wins, losses, be = _win_loss_counts(nets)
    signs = [_sign(n) for n in nets]
    win_runs, loss_runs = _streak_runs(signs)
    win_nets = [n for n in nets if _is_win(n)]
    loss_nets = [n for n in nets if _is_loss(n)]

    def avg_dur(pred) -> Optional[float]:
        mins = []
        for t in trades:
            if not pred(t):
                continue
            o, c = _as_naive(t.timestamp_open), _as_naive(t.timestamp_close)
            if o is None or c is None:
                continue
            mins.append((c - o).total_seconds() / 60)
        return round(sum(mins) / len(mins), 1) if mins else None

    best = max(trades, key=lambda t: t.net_pnl or 0.0, default=None)
    worst = min(trades, key=lambda t: t.net_pnl or 0.0, default=None)
    return {
        "trades": len(trades),
        "wins": wins,
        "losses": losses,
        "breakeven": be,
        "win_rate": round(wins / len(trades) * 100, 2) if trades else 0.0,
        "avg_win": round(sum(win_nets) / len(win_nets), 2) if win_nets else 0.0,
        "avg_loss": round(sum(loss_nets) / len(loss_nets), 2) if loss_nets else 0.0,
        "best": {"ticket": best.ticket, "net_pnl": best.net_pnl} if best else None,
        "worst": {"ticket": worst.ticket, "net_pnl": worst.net_pnl} if worst else None,
        "avg_win_duration_min": avg_dur(lambda t: _is_win(t.net_pnl or 0.0)),
        "avg_loss_duration_min": avg_dur(lambda t: _is_loss(t.net_pnl or 0.0)),
        "max_win_streak": max(win_runs, default=0),
        "max_loss_streak": max(loss_runs, default=0),
    }


@router.get("/long-short-stats")
def long_short_stats(account_id: Optional[int] = Query(default=None), session: Session = Depends(get_session)):
    trades = _closed_trades(session, account_id)
    buys = [t for t in trades if _normalize_direction(t.direction) == "buy"]
    sells = [t for t in trades if _normalize_direction(t.direction) == "sell"]
    return {
        "buy": _direction_stats(buys),
        "sell": _direction_stats(sells),
        "all": _direction_stats(trades),
    }


@router.get("/radar-profiles")
def radar_profiles(account_id: Optional[int] = Query(default=None), session: Session = Depends(get_session)):
    trades = _closed_trades(session, account_id)
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekday = []
    for i, name in enumerate(day_names):
        bucket = [t for t in trades if (_close_day(t) is not None and _close_day(t).weekday() == i)]
        nets = [t.net_pnl or 0.0 for t in bucket]
        w = sum(1 for n in nets if _is_win(n))
        weekday.append(
            {
                "day": name,
                "trades": len(bucket),
                "wins": w,
                "win_rate": round(w / len(bucket) * 100, 2) if bucket else 0.0,
                "net_pnl": round(sum(nets), 2),
            }
        )
    total_net = sum(t.net_pnl or 0.0 for t in trades)
    sessions = []
    for name in ("london", "new_york", "asia", "outside"):
        bucket = [t for t in trades if _session_of(t) == name]
        nets = [t.net_pnl or 0.0 for t in bucket]
        w = sum(1 for n in nets if _is_win(n))
        net = round(sum(nets), 2)
        sessions.append(
            {
                "session": name,
                "trades": len(bucket),
                "win_rate": round(w / len(bucket) * 100, 2) if bucket else 0.0,
                "net_pnl": net,
                "profit_pct": round(net / total_net * 100, 2) if total_net else 0.0,
            }
        )
    return {"weekday": weekday, "sessions": sessions}
