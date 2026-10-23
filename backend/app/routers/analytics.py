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
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.database import get_session
from app.models import Account, SymbolSpec, Tag, Trade, TradeTagLink
from app.services import analytics_rules
from app.services.analytics_rules import (
    BE_TOLERANCE,
    is_breakeven as _is_be,
    is_loss as _is_loss,
    is_win as _is_win,
    sign as _sign,
)
from app.services.analytics_stats import (
    drawdown_curve,
    mean_confidence,
    min_sample_size,
    ruin_probability,
)
from app.services.timeutils import as_naive_utc, trade_close_day, utcnow_naive
from app.services.trade_filters import TradeFilters, apply_trade_filters
from app.services.trading_day import day_of_trade, get_trading_day
from app.services.trade_money import currency_breakdown, usd_net

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


# Breakeven rule and win-rate denominator live in app.services.analytics_rules
# so the API, the Telegram bot and the frontend share one definition.


def _normalize_direction(raw: object) -> str | None:
    """Map stored direction to long/short buckets. UI Long ↔ `buy`, Short ↔ `sell`.
    Accepts `long`/`short` aliases; unknown/empty values return None and are ignored."""
    s = str(raw or "").strip().lower()
    if s in ("buy", "long"):
        return "buy"
    if s in ("sell", "short"):
        return "sell"
    return None


def _profit_factor(nets: list[float]) -> Optional[float]:
    gross_profit = sum(n for n in nets if _is_win(n))
    gross_loss = abs(sum(n for n in nets if _is_loss(n)))
    return round(gross_profit / gross_loss, 3) if gross_loss else None


def _symbol_key(t: Trade) -> str:
    """The grouping key for a symbol — blank rows are their own bucket."""
    return (t.symbol or "").strip().upper() or "UNKNOWN"


def _r_values(trades: list[Trade]) -> list[float]:
    return [t.r_multiple for t in trades if t.r_multiple is not None]


def _avg_r(trades: list[Trade]) -> Optional[float]:
    values = _r_values(trades)
    return round(sum(values) / len(values), 3) if values else None


def _net_stats(trades: list[Trade]) -> dict:
    """Outcome counts and money figures for one bucket of closed trades.

    Uses the shared breakeven band and win-rate denominator, and the USD net
    for every total, so a bucket can never disagree with the dashboard
    ribbon. An unpriced trade is counted as unknown, never as a zero.
    """
    nets = [usd_net(t) for t in trades]
    counts = analytics_rules.split_outcomes(nets)
    known = [n for n in nets if n is not None]
    net = round(sum(known), 2)
    return {
        "trade_count": len(trades),
        "priced": counts.priced,
        "unpriced": counts.unpriced,
        "wins": counts.wins,
        "losses": counts.losses,
        "breakeven": counts.breakeven,
        "net_pnl": net,
        "win_rate": analytics_rules.win_rate(counts.wins, counts.losses),
        # Per priced trade — the same expectancy the summary reports.
        "expectancy": round(net / counts.priced, 2) if counts.priced else 0.0,
    }


def _bucket(trades: list[Trade]) -> dict:
    """One comparable performance row: counts, money, R and currencies."""
    known = [n for n in (usd_net(t) for t in trades) if n is not None]
    return {
        **_net_stats(trades),
        "profit_factor": _profit_factor(known),
        "avg_r": _avg_r(trades),
        "r_trades": len(_r_values(trades)),
        "by_currency": currency_breakdown(trades),
    }


def _setup_tag_map(session: Session) -> tuple[list[str], dict[int, list[str]]]:
    """Setup-category tag names, and the setup tags carried by each trade.

    One query for the tags and one for the links — a trade with two setups
    appears under both, which is the point of a setup × symbol matrix. A
    mistake tag never becomes a row: only ``category == "setup"`` counts.
    """
    tags = session.exec(
        select(Tag).where(Tag.category == "setup").order_by(Tag.name.asc())
    ).all()
    names = [tag.name for tag in tags]
    by_id = {tag.id: tag.name for tag in tags}
    mapping: dict[int, list[str]] = defaultdict(list)
    for link in session.exec(select(TradeTagLink)).all():
        name = by_id.get(link.tag_id)
        if name is not None and link.trade_id is not None:
            mapping[link.trade_id].append(name)
    return names, mapping


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
        # An unpriced trade has no known P&L, so it is not a point on the
        # curve — plotting it as zero would assert a result we do not have.
        if usd_net(t) is None:
            continue
        net = usd_net(t)
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
def summary(
    account_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None, description="OPEN or CLOSED"),
    symbol: Optional[str] = None,
    query: Optional[str] = Query(default=None, alias="q", description="Free text: symbol or ticket"),
    tag: Optional[str] = Query(default=None, description="Tag name without #/! prefix"),
    tag_exact: bool = Query(default=False, description="Match the tag name exactly"),
    date_from: Optional[datetime] = Query(default=None, description="Open-day lower bound"),
    date_to: Optional[datetime] = Query(default=None, description="Open-day upper bound"),
    closed_from: Optional[datetime] = Query(default=None, description="Close-day lower bound"),
    closed_to: Optional[datetime] = Query(default=None, description="Close-day upper bound"),
    unassigned: bool = Query(default=False, description="Only trades with no account"),
    session: Session = Depends(get_session),
):
    """The ledger's summary — the same filter the table shows.

    The figures describe the *closed* trades inside the filter, because that
    is what the dashboard's ribbon reports: the realized net, the win rate
    and the average R. The open count comes from the same filter, so the
    "open now" figure moves with the account and the date range.
    """
    filters = TradeFilters(
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
    base = filters.without_status()
    closed_stmt = apply_trade_filters(
        select(Trade).where(Trade.status == "CLOSED"), base
    )
    trades = session.exec(closed_stmt).all()
    nets = [usd_net(t) for t in trades]
    total = len(trades)
    counts = analytics_rules.split_outcomes(nets)
    # An unpriced trade has no known P&L, so it contributes nothing to the
    # total and it is not part of the expectancy denominator.
    known = [n for n in nets if n is not None]
    wins = [n for n in known if _is_win(n)]
    losses = [n for n in known if _is_loss(n)]
    net_pnl = round(sum(known), 2)
    rate = analytics_rules.win_rate(counts.wins, counts.losses)
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = round(gross_profit / gross_loss, 3) if gross_loss else None
    expectancy = round(net_pnl / counts.priced, 2) if counts.priced else 0.0
    avg_win = round(gross_profit / len(wins), 2) if wins else 0.0
    avg_loss = round(sum(losses) / len(losses), 2) if losses else 0.0
    r_values = [t.r_multiple for t in trades if t.r_multiple is not None]
    avg_r = round(sum(r_values) / len(r_values), 3) if r_values else None

    points = _equity_points(trades)
    max_dd = min((p["drawdown"] for p in points), default=0.0)

    open_stmt = apply_trade_filters(select(Trade).where(Trade.status == "OPEN"), base)
    open_count = len(session.exec(open_stmt).all())
    return {
        "total_trades": total,
        "open_trades": open_count,
        "wins": counts.wins,
        "losses": counts.losses,
        "breakeven": counts.breakeven,
        "unpriced": counts.unpriced,
        "net_pnl": net_pnl,
        "win_rate": rate,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "avg_r": avg_r,
        "max_drawdown": max_dd,
        # The overall figure is USD; this is the quote-currency audit trail.
        "by_currency": currency_breakdown(trades),
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
        nets = [usd_net(t) for t in link_rows]
        counts = analytics_rules.split_outcomes(nets)
        known = [n for n in nets if n is not None]
        rows.append(
            {
                "name": tag.name,
                "category": tag.category,
                "trade_count": len(link_rows),
                "unpriced": counts.unpriced,
                "net_pnl": round(sum(known), 2),
                "win_rate": analytics_rules.win_rate(counts.wins, counts.losses),
                "by_currency": currency_breakdown(link_rows),
            }
        )
    rows.sort(key=lambda r: r["net_pnl"], reverse=True)
    return {"tags": rows}


@router.get("/symbol-performance")
def symbol_performance(
    account_id: Optional[int] = Query(default=None),
    session: Session = Depends(get_session),
):
    """Per-symbol results — what each instrument actually pays.

    Net, win rate, expectancy, realised R and trade count, on the same
    breakeven band and win-rate denominator as the dashboard. An
    unregistered symbol keeps its trades and is marked ``registered: false``;
    its unpriced trades stay out of the money and the rate, never scored as
    zero results.
    """
    trades = _closed_trades(session, account_id)
    buckets: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        buckets[_symbol_key(trade)].append(trade)
    specs = {spec.symbol: spec for spec in session.exec(select(SymbolSpec)).all()}

    rows = []
    for symbol, bucket in buckets.items():
        spec = specs.get(symbol)
        rows.append(
            {
                "symbol": symbol,
                "display": spec.display if spec and spec.display else symbol,
                "registered": spec is not None,
                "category": spec.category if spec else None,
                "contract_size": spec.contract_size if spec else None,
                **_bucket(bucket),
            }
        )
    rows.sort(key=lambda row: (-row["net_pnl"], row["symbol"]))
    return {"symbols": rows, "totals": _bucket(trades)}


@router.get("/setup-matrix")
def setup_matrix(
    account_id: Optional[int] = Query(default=None),
    session: Session = Depends(get_session),
):
    """Setup × symbol results — which playbook works on which instrument.

    Rows are the setup tags; columns are the symbols those trades touched.
    A trade with two setup tags contributes to both rows on purpose, so the
    row totals overlap. The column totals count every trade once (including
    the ``Untagged`` row when a closed trade carries no setup), which is why
    they reconcile with ``grand_total``.
    """
    trades = _closed_trades(session, account_id)
    setups, tag_map = _setup_tag_map(session)
    symbols = sorted({_symbol_key(t) for t in trades})

    def cells_for(bucket: list[Trade]) -> list[dict]:
        cells = []
        for symbol in symbols:
            cell_trades = [t for t in bucket if _symbol_key(t) == symbol]
            if not cell_trades:
                continue
            cells.append({"symbol": symbol, **_net_stats(cell_trades)})
        return cells

    rows = []
    for setup in setups:
        bucket = [t for t in trades if setup in tag_map.get(t.id or -1, [])]
        if not bucket:
            continue
        rows.append(
            {
                "setup": setup,
                "label": setup,
                "is_untagged": False,
                **_net_stats(bucket),
                "cells": cells_for(bucket),
            }
        )
    rows.sort(key=lambda row: (-row["net_pnl"], row["setup"]))

    untagged = [t for t in trades if not tag_map.get(t.id or -1)]
    if untagged:
        rows.append(
            {
                "setup": None,
                "label": "Untagged",
                "is_untagged": True,
                **_net_stats(untagged),
                "cells": cells_for(untagged),
            }
        )

    columns = [
        {
            "symbol": symbol,
            **_net_stats([t for t in trades if _symbol_key(t) == symbol]),
        }
        for symbol in symbols
    ]
    return {
        "setups": [row["setup"] for row in rows if row["setup"] is not None],
        "symbols": symbols,
        "rows": rows,
        "column_totals": columns,
        "grand_total": _net_stats(trades),
    }


@router.get("/setup-confidence")
def setup_confidence(
    tag: Optional[str] = Query(default=None, description="Setup tag name, with or without #"),
    account_id: Optional[int] = Query(default=None),
    min_sample: Optional[int] = Query(
        default=None, ge=1, description="Override MIN_SAMPLE_SIZE for this request"
    ),
    session: Session = Depends(get_session),
):
    """Expectancy per setup with a 95% confidence interval.

    A setup with three trades can post a spectacular average by luck. The
    interval says how much of that average is signal: rows are ranked by the
    *lower* bound, and a setup below the configured minimum sample is marked
    ``sufficient: false`` and sorted after every ranked one — visible, never
    presented as a winner.
    """
    trades = _closed_trades(session, account_id)
    names, tag_map = _setup_tag_map(session)
    threshold = min_sample if min_sample is not None else min_sample_size()
    wanted = (tag or "").strip().lstrip("#!").lower() or None

    rows = []
    for name in names:
        if wanted is not None and name.lower() != wanted:
            continue
        bucket = [t for t in trades if name in tag_map.get(t.id or -1, [])]
        nets = [usd_net(t) for t in bucket]
        counts = analytics_rules.split_outcomes(nets)
        known = [n for n in nets if n is not None]
        interval = mean_confidence(known)
        decided = counts.wins + counts.losses
        rows.append(
            {
                "name": name,
                "category": "setup",
                "trade_count": len(bucket),
                "priced": counts.priced,
                "unpriced": counts.unpriced,
                "wins": counts.wins,
                "losses": counts.losses,
                "breakeven": counts.breakeven,
                "decided": decided,
                "win_rate": analytics_rules.win_rate(counts.wins, counts.losses),
                "net_pnl": round(sum(known), 2),
                "expectancy": interval["mean"] if interval["mean"] is not None else 0.0,
                "std_dev": interval["std_dev"],
                "standard_error": interval["standard_error"],
                "ci_low": interval["ci_low"],
                "ci_high": interval["ci_high"],
                "ci_level": interval["ci_level"],
                "sufficient": decided >= threshold,
            }
        )

    def rank(row: dict) -> tuple:
        low = row["ci_low"]
        return (
            0 if row["sufficient"] else 1,
            -(low if low is not None else float("-inf")),
            -row["trade_count"],
            row["name"],
        )

    rows.sort(key=rank)
    return {
        "min_sample": threshold,
        "ci_level": 0.95,
        "tags": rows,
        "insufficient": sum(1 for row in rows if not row["sufficient"]),
    }


@router.get("/drawdown")
def drawdown(
    group_by: Literal["account", "setup"] = Query(default="account"),
    account_id: Optional[int] = Query(default=None),
    session: Session = Depends(get_session),
):
    """Peak-to-trough drawdown, broken out by account or by setup.

    Every group walks its own trades in close order and starts from zero, so
    the figures answer "what would this book have drawn down on its own".
    A trade with two setup tags appears in both setup groups — the point is
    to see each playbook's damage; the ``overall`` row counts every trade
    once.
    """
    trades = _closed_trades(session, account_id)

    groups: dict[str, list[Trade]] = defaultdict(list)
    labels: dict[str, str] = {}
    if group_by == "account":
        accounts = {acc.id: acc for acc in session.exec(select(Account)).all()}
        for trade in trades:
            if trade.account_id is None:
                key, label = "unassigned", "Unassigned"
            else:
                key = str(trade.account_id)
                acc = accounts.get(trade.account_id)
                label = f"@{acc.alias}" if acc is not None else f"Account #{trade.account_id}"
            groups[key].append(trade)
            labels[key] = label
    else:
        _setups, tag_map = _setup_tag_map(session)
        for trade in trades:
            names = tag_map.get(trade.id or -1, [])
            if not names:
                groups["untagged"].append(trade)
                labels["untagged"] = "Untagged"
            for name in names:
                groups[name].append(trade)
                labels[name] = f"#{name}"

    def curve_row(key: str, label: str, bucket: list[Trade]) -> dict:
        known = [net for net in (usd_net(t) for t in bucket) if net is not None]
        return {
            "key": key,
            "label": label,
            **_net_stats(bucket),
            **drawdown_curve(known),
            "by_currency": currency_breakdown(bucket),
        }

    rows = [curve_row(key, labels[key], bucket) for key, bucket in groups.items()]
    # Worst drawdown first — that is the group worth looking at.
    rows.sort(key=lambda row: (row["max_drawdown"], -row["net_pnl"], row["label"]))
    return {
        "group_by": group_by,
        "overall": curve_row("all", "All trades", trades),
        "groups": rows,
    }


def _account_size_usd(session: Session, account_id: Optional[int]) -> tuple[Optional[float], str]:
    """The capital a ruin estimate is measured against, in USD.

    Reuses the prop-status balance math, which converts each account's own
    base currency into USD at the close-day rate. An account with no
    resolvable FX rate is left out instead of being counted at 1:1.
    """
    from app.routers.accounts import _prop_numbers

    statement = select(Account)
    if account_id is not None:
        statement = statement.where(Account.id == account_id)
    total = 0.0
    found = 0
    for account in session.exec(statement).all():
        try:
            numbers = _prop_numbers(account, session, "USD")
        except HTTPException:
            continue
        total += numbers["balance"]
        found += 1
    if not found:
        return None, "missing"
    return round(total, 2), "account_balance"


@router.get("/risk-of-ruin")
def risk_of_ruin(
    tag: Optional[str] = Query(default=None, description="Setup tag name, with or without #"),
    account_id: Optional[int] = Query(default=None),
    account_size: Optional[float] = Query(
        default=None, gt=0, description="Override the account balance used as capital"
    ),
    risk_per_trade: Optional[float] = Query(
        default=None, gt=0, description="Override every setup's average risk per trade"
    ),
    min_sample: Optional[int] = Query(
        default=None, ge=1, description="Override MIN_SAMPLE_SIZE for this request"
    ),
    session: Session = Depends(get_session),
):
    """Risk of ruin per setup, against the current account size.

    The account size is the balance of the selected account (or every
    account, in USD), and each setup is sized at the risk it actually
    carried — its average ``realized_risk``, falling back to the planned
    ``initial_risk``. The estimate is the diffusion approximation: a book
    with no edge ruins almost surely, and a smaller risk per trade buys more
    units of survivability. ``?account_size=`` and ``?risk_per_trade=``
    answer "what if" without changing the journal.
    """
    trades = _closed_trades(session, account_id)
    names, tag_map = _setup_tag_map(session)
    threshold = min_sample if min_sample is not None else min_sample_size()
    wanted = (tag or "").strip().lstrip("#!").lower() or None

    if account_size is not None:
        size, size_source = float(account_size), "explicit"
    else:
        size, size_source = _account_size_usd(session, account_id)

    rows = []
    for name in names:
        if wanted is not None and name.lower() != wanted:
            continue
        bucket = [t for t in trades if name in tag_map.get(t.id or -1, [])]
        if not bucket:
            continue

        nets = [usd_net(t) for t in bucket]
        counts = analytics_rules.split_outcomes(nets)
        known = [n for n in nets if n is not None]
        win_nets = [n for n in known if _is_win(n)]
        loss_nets = [n for n in known if _is_loss(n)]
        avg_win = round(sum(win_nets) / len(win_nets), 2) if win_nets else None
        avg_loss = round(abs(sum(loss_nets) / len(loss_nets)), 2) if loss_nets else None
        payoff = round(avg_win / avg_loss, 3) if (avg_win is not None and avg_loss) else None
        decided = counts.wins + counts.losses
        win_rate = analytics_rules.win_rate(counts.wins, counts.losses)
        p = counts.wins / decided if decided else 0.0
        edge_r = round(p * payoff - (1.0 - p), 4) if payoff is not None else None

        if risk_per_trade is not None:
            risk, risk_source = float(risk_per_trade), "explicit"
        else:
            realized = [t.realized_risk for t in bucket if t.realized_risk and t.realized_risk > 0]
            planned = [t.initial_risk for t in bucket if t.initial_risk and t.initial_risk > 0]
            if realized:
                risk, risk_source = round(sum(realized) / len(realized), 2), "realized"
            elif planned:
                risk, risk_source = round(sum(planned) / len(planned), 2), "initial"
            else:
                risk, risk_source = None, "missing"

        units = round(size / risk, 2) if (size is not None and risk) else None
        probability = ruin_probability(win_rate, payoff, units)
        rows.append(
            {
                "name": name,
                "trade_count": len(bucket),
                "decided": decided,
                "wins": counts.wins,
                "losses": counts.losses,
                "breakeven": counts.breakeven,
                "unpriced": counts.unpriced,
                "win_rate": win_rate,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "payoff_ratio": payoff,
                "expectancy_r": edge_r,
                "net_pnl": round(sum(known), 2),
                "avg_r": _avg_r(bucket),
                "risk_per_trade": risk,
                "risk_source": risk_source,
                "risk_units": units,
                "risk_of_ruin": round(probability, 6) if probability is not None else None,
                "sufficient": decided >= threshold,
            }
        )

    def rank(row: dict) -> tuple:
        probability = row["risk_of_ruin"]
        return (
            0 if row["sufficient"] else 1,
            0 if probability is not None else 1,
            probability if probability is not None else 2.0,
            row["name"],
        )

    rows.sort(key=rank)
    return {
        "account_size": size,
        "account_size_source": size_source,
        "risk_per_trade_override": risk_per_trade,
        "min_sample": threshold,
        "method": "diffusion",
        "detail": None
        if size is not None
        else "No account balance available — pass ?account_size=",
        "setups": rows,
        "insufficient": sum(1 for row in rows if not row["sufficient"]),
    }


@router.get("/calendar")
def calendar(
    year: Optional[int] = Query(default=None, description="Defaults to current year"),
    account_id: Optional[int] = Query(default=None),
    session: Session = Depends(get_session),
):
    setting = get_trading_day(session)
    target_year = year or setting.day_of(utcnow_naive()).year
    daily: dict[str, dict] = defaultdict(
        lambda: {"net_pnl": 0.0, "trade_count": 0, "unpriced": 0, "by_currency": {}}
    )
    for t in _closed_trades(session, account_id):
        # The configured trading day (same helper as monthly-calendar /
        # streaks) — a 23:30 UTC close can belong to the next local day.
        day = day_of_trade(setting, t)
        if day is None or day.year != target_year:
            continue
        key = day.isoformat()
        daily[key]["trade_count"] += 1
        if usd_net(t) is None:
            daily[key]["unpriced"] += 1
        else:
            daily[key]["net_pnl"] += usd_net(t)
        if t.net_pnl is not None:
            cur = (t.quote_currency or "USD").upper()
            daily[key]["by_currency"][cur] = round(
                daily[key]["by_currency"].get(cur, 0.0) + t.net_pnl, 2
            )
    days = [
        {
            "date": date,
            "net_pnl": round(v["net_pnl"], 2),
            "trade_count": v["trade_count"],
            "unpriced": v["unpriced"],
            "by_currency": v["by_currency"],
        }
        for date, v in sorted(daily.items())
    ]
    return {"year": target_year, "days": days}


# --- v2 TradeZella endpoints (Phase 4) ---


@router.get("/kpi-dashboard")
def kpi_dashboard(account_id: Optional[int] = Query(default=None), session: Session = Depends(get_session)):
    trades = _closed_trades(session, account_id)
    nets = [usd_net(t) for t in trades]
    known = [n for n in nets if n is not None]
    net_pnl = round(sum(known), 2)
    counts = analytics_rules.split_outcomes(nets)
    total = len(trades)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    last30 = sum(
        (usd_net(t) or 0.0)
        for t in trades
        if (_close_day(t) or datetime.min) >= now - timedelta(days=30)
    )
    prev30 = sum(
        (usd_net(t) or 0.0)
        for t in trades
        if now - timedelta(days=60) <= (_close_day(t) or datetime.min) < now - timedelta(days=30)
    )
    change_pct = round((last30 - prev30) / abs(prev30) * 100, 2) if prev30 else None

    equity = _downsample([round(v, 2) for v in _cumulative(known)])

    rr_vals = [t.r_multiple for t in trades if t.r_multiple is not None]
    avg_rr = round(sum(rr_vals) / len(rr_vals), 3) if rr_vals else 0.0

    sessions: dict[str, dict] = {}
    total_net_abs = sum(abs(usd_net(t) or 0.0) for t in trades) or None
    for name in ("london", "new_york", "asia", "outside"):
        bucket = [t for t in trades if _session_of(t) == name]
        bnets = [usd_net(t) for t in bucket]
        bcounts = analytics_rules.split_outcomes(bnets)
        bknown = [n for n in bnets if n is not None]
        bnet = round(sum(bknown), 2)
        sessions[name] = {
            "net_pnl": bnet,
            "trade_count": len(bucket),
            "unpriced": bcounts.unpriced,
            "win_rate": analytics_rules.win_rate(bcounts.wins, bcounts.losses),
            "return_pct": round(bnet / total_net_abs * 100, 2) if total_net_abs else 0.0,
            "by_currency": currency_breakdown(bucket),
        }

    return {
        "net_pnl": net_pnl,
        "net_pnl_change_pct": change_pct,
        "sparkline": equity,
        "avg_realized_rr": {"current": avg_rr, "target": TARGET_RR},
        "win_rate": {
            "rate": analytics_rules.win_rate(counts.wins, counts.losses),
            "wins": counts.wins,
            "losses": counts.losses,
            "breakeven": counts.breakeven,
            "unpriced": counts.unpriced,
        },
        "profit_factor": _profit_factor(known),
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
    setting = get_trading_day(session)
    this_day = setting.day_of(utcnow_naive())
    y, m = year or this_day.year, month or this_day.month
    month_start = date_type(y, m, 1)
    month_end = date_type(y + (m == 12), (m % 12) + 1, 1)

    daily: dict[str, dict] = defaultdict(
        lambda: {"net_pnl": 0.0, "trade_count": 0, "priced": 0, "unpriced": 0, "by_currency": {}}
    )
    for t in _closed_trades(session, account_id):
        day = day_of_trade(setting, t)
        if day is None or not (month_start <= day < month_end):
            continue
        key = day.isoformat()
        daily[key]["trade_count"] += 1
        if usd_net(t) is None:
            daily[key]["unpriced"] += 1
        else:
            daily[key]["priced"] += 1
            daily[key]["net_pnl"] += usd_net(t)
        if t.net_pnl is not None:
            cur = (t.quote_currency or "USD").upper()
            daily[key]["by_currency"][cur] = round(
                daily[key]["by_currency"].get(cur, 0.0) + t.net_pnl, 2
            )

    days: dict[str, dict] = {}
    day_cursor = month_start
    while day_cursor < month_end:
        key = day_cursor.isoformat()
        v = daily.get(
            key,
            {"net_pnl": 0.0, "trade_count": 0, "priced": 0, "unpriced": 0, "by_currency": {}},
        )
        net = round(v["net_pnl"], 2)
        if v["trade_count"] == 0:
            outcome = "inactive"
        elif v["priced"] == 0:
            # Trades, but none of them priced — the day's result is unknown,
            # not a breakeven.
            outcome = "unpriced"
        elif _is_win(net):
            outcome = "win"
        elif _is_loss(net):
            outcome = "loss"
        else:
            outcome = "be"
        days[key] = {
            "net_pnl": net,
            "trade_count": v["trade_count"],
            "unpriced": v["unpriced"],
            "outcome": outcome,
            "by_currency": v["by_currency"],
        }
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
    unpriced_days = sum(1 for d in active if d["outcome"] == "unpriced")
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
            "unpriced_days": unpriced_days,
        },
        "outcome": {
            "wins": won,
            "losses": lost,
            "breakeven": be_days,
            "unpriced": unpriced_days,
        },
    }


@router.get("/activity-and-streaks")
def activity_and_streaks(account_id: Optional[int] = Query(default=None), session: Session = Depends(get_session)):
    trades = _closed_trades(session, account_id)
    nets = [usd_net(t) for t in trades]
    counts = analytics_rules.split_outcomes(nets)
    # An unpriced trade has no outcome, so it takes no part in a streak —
    # an unknown result must not break a run of known ones.
    signs = [_sign(n) for n in nets if n is not None]
    win_runs, loss_runs = _streak_runs(signs)

    setting = get_trading_day(session)
    daily: dict[str, float] = defaultdict(float)
    volume: dict[str, float] = defaultdict(float)
    for t in trades:
        day = day_of_trade(setting, t)
        if day is None:
            continue
        key = day.isoformat()
        daily[key] += usd_net(t) if usd_net(t) is not None else 0.0
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

    _open_stmt = select(Trade).where(Trade.status == "OPEN")
    if account_id is not None:
        _open_stmt = _open_stmt.where(Trade.account_id == account_id)
    open_count = len(session.exec(_open_stmt).all())
    best = max(trades, key=lambda t: usd_net(t) or 0.0, default=None)
    worst = min(trades, key=lambda t: usd_net(t) or 0.0, default=None)
    return {
        "total_trades": len(trades),
        "open_trades": open_count,
        "closed_trades": len(trades),
        "winning_trades": counts.wins,
        "losing_trades": counts.losses,
        "unpriced_trades": counts.unpriced,
        "max_win_streak": max(win_runs, default=0),
        "max_loss_streak": max(loss_runs, default=0),
        "avg_win_streak": round(sum(win_runs) / len(win_runs), 2) if win_runs else 0.0,
        "avg_loss_streak": round(sum(loss_runs) / len(loss_runs), 2) if loss_runs else 0.0,
        "max_winning_days": max_wdays,
        "max_losing_days": max_ldays,
        "trading_days": len(ordered_days),
        "avg_daily_volume": round(sum(volume.values()) / len(volume), 3) if volume else 0.0,
        "best_trade": {"ticket": best.ticket, "net_pnl": usd_net(best)} if best else None,
        "worst_trade": {"ticket": worst.ticket, "net_pnl": usd_net(worst)} if worst else None,
        "by_currency": currency_breakdown(trades),
    }


def _direction_stats(trades: list[Trade]) -> dict:
    nets = [usd_net(t) for t in trades]
    counts = analytics_rules.split_outcomes(nets)
    signs = [_sign(n) for n in nets if n is not None]
    win_runs, loss_runs = _streak_runs(signs)
    known = [n for n in nets if n is not None]
    win_nets = [n for n in known if _is_win(n)]
    loss_nets = [n for n in known if _is_loss(n)]

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

    best = max(trades, key=lambda t: usd_net(t) or 0.0, default=None)
    worst = min(trades, key=lambda t: usd_net(t) or 0.0, default=None)
    return {
        "trades": len(trades),
        "wins": counts.wins,
        "losses": counts.losses,
        "breakeven": counts.breakeven,
        "unpriced": counts.unpriced,
        "win_rate": analytics_rules.win_rate(counts.wins, counts.losses),
        "avg_win": round(sum(win_nets) / len(win_nets), 2) if win_nets else 0.0,
        "avg_loss": round(sum(loss_nets) / len(loss_nets), 2) if loss_nets else 0.0,
        "best": {"ticket": best.ticket, "net_pnl": usd_net(best)} if best else None,
        "worst": {"ticket": worst.ticket, "net_pnl": usd_net(worst)} if worst else None,
        "avg_win_duration_min": avg_dur(lambda t: _is_win(usd_net(t) or 0.0)),
        "avg_loss_duration_min": avg_dur(lambda t: _is_loss(usd_net(t) or 0.0)),
        "max_win_streak": max(win_runs, default=0),
        "max_loss_streak": max(loss_runs, default=0),
        "by_currency": currency_breakdown(trades),
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
    setting = get_trading_day(session)
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekday = []
    for i, name in enumerate(day_names):
        bucket = [
            t for t in trades if (d := day_of_trade(setting, t)) is not None and d.weekday() == i
        ]
        nets = [usd_net(t) for t in bucket]
        counts = analytics_rules.split_outcomes(nets)
        known = [n for n in nets if n is not None]
        weekday.append(
            {
                "day": name,
                "trades": len(bucket),
                "wins": counts.wins,
                "unpriced": counts.unpriced,
                "win_rate": analytics_rules.win_rate(counts.wins, counts.losses),
                "net_pnl": round(sum(known), 2),
                "by_currency": currency_breakdown(bucket),
            }
        )
    total_net = sum(usd_net(t) or 0.0 for t in trades)
    sessions = []
    for name in ("london", "new_york", "asia", "outside"):
        bucket = [t for t in trades if _session_of(t) == name]
        nets = [usd_net(t) for t in bucket]
        counts = analytics_rules.split_outcomes(nets)
        known = [n for n in nets if n is not None]
        net = round(sum(known), 2)
        sessions.append(
            {
                "session": name,
                "trades": len(bucket),
                "unpriced": counts.unpriced,
                "win_rate": analytics_rules.win_rate(counts.wins, counts.losses),
                "net_pnl": net,
                "profit_pct": round(net / total_net * 100, 2) if total_net else 0.0,
                "by_currency": currency_breakdown(bucket),
            }
        )
    return {"weekday": weekday, "sessions": sessions}
