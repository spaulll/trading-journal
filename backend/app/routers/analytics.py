"""Analytics endpoints (PLAN Task 4.1)."""

from collections import defaultdict
from datetime import datetime
from math import floor
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.database import get_session
from app.models import Tag, Trade, TradeTagLink

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _closed_trades(session: Session) -> list[Trade]:
    statement = (
        select(Trade)
        .where(Trade.status == "CLOSED")
        .order_by(Trade.timestamp_close.asc(), Trade.id.asc())
    )
    trades = list(session.exec(statement).all())
    # Rows without a close timestamp sort first under ASC with NULLs;
    # keep chronological order by pushing NULL timestamps to the end.
    trades.sort(key=lambda t: (t.timestamp_close is None, t.timestamp_close, t.id or 0))
    return trades


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
                "trade_id": t.trade_id,
            }
        )
    return points


@router.get("/summary")
def summary(session: Session = Depends(get_session)):
    trades = _closed_trades(session)
    nets = [t.net_pnl if t.net_pnl is not None else 0.0 for t in trades]
    total = len(trades)
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n < 0]
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

    open_count = len(
        session.exec(select(Trade).where(Trade.status == "OPEN")).all()
    )
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
def equity_curve(session: Session = Depends(get_session)):
    return {"points": _equity_points(_closed_trades(session))}


_R_BUCKETS = ["-2R", "-1R", "0R", "1R", "2R", "3R+"]


def _r_bucket(r: float) -> str:
    bucket = floor(r + 0.5)  # nearest integer, so -1.06 -> -1R, 0.97 -> 1R
    if bucket <= -2:
        return "-2R"
    if bucket >= 3:
        return "3R+"
    return f"{bucket}R"


@router.get("/r-distribution")
def r_distribution(session: Session = Depends(get_session)):
    counts: dict[str, int] = {b: 0 for b in _R_BUCKETS}
    for t in _closed_trades(session):
        if t.r_multiple is None:
            continue
        counts[_r_bucket(t.r_multiple)] += 1
    return {"buckets": [{"label": b, "count": counts[b]} for b in _R_BUCKETS]}


@router.get("/tag-performance")
def tag_performance(session: Session = Depends(get_session)):
    tags = session.exec(select(Tag)).all()
    rows = []
    for tag in tags:
        link_rows = session.exec(
            select(Trade).where(
                Trade.id.in_(
                    select(TradeTagLink.trade_id).where(TradeTagLink.tag_id == tag.id)
                ),
                Trade.status == "CLOSED",
            )
        ).all()
        nets = [t.net_pnl if t.net_pnl is not None else 0.0 for t in link_rows]
        wins = sum(1 for n in nets if n > 0)
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
    session: Session = Depends(get_session),
):
    target_year = year or datetime.now().year
    daily: dict[str, dict] = defaultdict(lambda: {"net_pnl": 0.0, "trade_count": 0})
    for t in _closed_trades(session):
        ts = t.timestamp_close or t.timestamp_open
        if ts is None or ts.year != target_year:
            continue
        key = ts.date().isoformat()
        daily[key]["net_pnl"] += t.net_pnl if t.net_pnl is not None else 0.0
        daily[key]["trade_count"] += 1
    days = [
        {"date": date, "net_pnl": round(v["net_pnl"], 2), "trade_count": v["trade_count"]}
        for date, v in sorted(daily.items())
    ]
    return {"year": target_year, "days": days}
