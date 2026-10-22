"""Prop-challenge rules: snapshots, milestones, and deadline warnings.

The account columns hold the firm's limits. This module turns them into the
five rules the journal tracks, reads the live numbers from the same prop
calculator the dashboard uses, and persists the moment a rule resolves.

``met_at`` is a milestone, not a status. A profit target, a minimum-days
requirement and a max-loss breach never un-happen; a consistency reading and
a daily-loss breach are live, so they can reset. The response's ``status``
is what the UI and the Telegram bot show.
"""

from __future__ import annotations

import json
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlmodel import Session, select

from app.models import (
    Account,
    AccountEvent,
    AccountEventRead,
    AccountRule,
    AccountRuleRead,
    Trade,
)
from app.services.trading_day import day_of_trade, get_trading_day
from app.services.timeutils import as_naive_utc

RULE_KINDS = ("profit_target", "max_loss", "daily_loss", "min_days", "consistency")
RULE_LABELS = {
    "profit_target": "Profit target",
    "max_loss": "Max loss",
    "daily_loss": "Daily loss",
    "min_days": "Trading days",
    "consistency": "Consistency",
}
RULE_UNITS = {
    "profit_target": "%",
    "max_loss": "%",
    "daily_loss": "%",
    "min_days": "days",
    "consistency": "%",
}
BREACH_KINDS = {"max_loss", "daily_loss"}


def _now() -> datetime:
    """Naive UTC — the storage policy for every timestamp in the journal."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _round(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(float(value), 2)


def configured_rules(acc: Account) -> dict[str, float]:
    """The rules the account's configuration actually turns on.

    A zero percent limit means "not configured", not "zero tolerance".
    """
    rules: dict[str, float] = {}
    if acc.profit_target_pct is not None and acc.profit_target_pct > 0:
        rules["profit_target"] = float(acc.profit_target_pct)
    if (acc.max_loss_pct or 0.0) > 0:
        rules["max_loss"] = float(acc.max_loss_pct)
    if (acc.daily_loss_pct or 0.0) > 0:
        rules["daily_loss"] = float(acc.daily_loss_pct)
    if (acc.min_trading_days or 0) > 0:
        rules["min_days"] = float(acc.min_trading_days)
    if acc.consistency_pct is not None and acc.consistency_pct > 0:
        rules["consistency"] = float(acc.consistency_pct)
    return rules


def count_trading_days(session: Session, account_id: int) -> int:
    """Distinct trading days with at least one closed trade."""
    setting = get_trading_day(session)
    trades = session.exec(
        select(Trade).where(Trade.account_id == account_id, Trade.status == "CLOSED")
    ).all()
    return len(
        {
            day
            for trade in trades
            if (day := day_of_trade(setting, trade)) is not None
        }
    )


def log_account_event(
    session: Session,
    account_id: int,
    kind: str,
    payload: dict[str, Any],
    *,
    occurred_at: Optional[datetime] = None,
) -> AccountEvent:
    """Append an event. The caller owns the commit."""
    event = AccountEvent(
        account_id=account_id,
        kind=kind,
        payload=json.dumps(payload, sort_keys=True, default=str),
        occurred_at=occurred_at or _now(),
    )
    session.add(event)
    return event


def _current_value(kind: str, numbers: dict) -> Optional[float]:
    if kind == "profit_target":
        return numbers.get("return_pct")
    if kind == "max_loss":
        return numbers.get("max_loss_used_pct")
    if kind == "daily_loss":
        return numbers.get("daily_loss_used_pct")
    if kind == "min_days":
        return numbers.get("days_traded")
    if kind == "consistency":
        return numbers.get("best_day_share")
    return None


def _resolved(kind: str, current: Optional[float], target: float) -> bool:
    if current is None:
        return False
    if kind == "consistency":
        # Lower is better: a day may not carry more than ``target`` percent.
        return current <= target
    return current >= target


def _status(row: AccountRule, deadline: Optional[date_type], today: date_type) -> str:
    if row.kind == "min_days":
        if row.met_at is not None:
            return "met"
        if deadline is not None and today > deadline:
            return "missed"
        return "pending"
    if row.kind == "consistency":
        # The reading is live: a later oversized day breaks it again.
        if row.current is not None and row.current <= row.target:
            return "met"
        return "pending"
    if row.kind in BREACH_KINDS:
        return "breached" if row.met_at is not None else "pending"
    return "met" if row.met_at is not None else "pending"


def _weekdays_between(start: date_type, end: date_type) -> int:
    """Weekdays in [start, end] — an honest approximation of trading days.

    The journal does not know the firm's holiday calendar, so the warning
    counts Mon-Fri and says "weekday(s)" rather than pretending to know
    every market's schedule.
    """
    if end < start:
        return 0
    days = 0
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            days += 1
        cursor += timedelta(days=1)
    return days


def _warning(
    row: AccountRule, deadline: Optional[date_type], today: date_type
) -> tuple[Optional[str], Optional[int]]:
    if row.kind != "min_days":
        if row.kind == "consistency" and row.current is not None and row.current > row.target:
            return (
                f"Best day is {row.current:.2f}% of profit; the limit is "
                f"{row.target:.2f}%.",
                None,
            )
        if row.kind in BREACH_KINDS and row.met_at is not None:
            current = row.current if row.current is not None else 0.0
            return (
                f"Limit breached at {current:.2f}% "
                f"(limit {row.target:.2f}%).",
                None,
            )
        return None, None

    if deadline is None:
        return None, None
    days_left = (deadline - today).days
    if row.met_at is not None:
        return None, days_left
    current = int(row.current or 0)
    target = int(row.target)
    if today > deadline:
        return (
            f"Deadline passed with {current} of {target} trading days.",
            days_left,
        )
    needed = max(0, target - current)
    available = _weekdays_between(today, deadline)
    if needed > 0 and needed >= available:
        more_days = "day" if needed == 1 else "days"
        weekdays = "weekday" if available == 1 else "weekdays"
        return (
            f"At risk: {needed} more trading {more_days} needed, only "
            f"{available} {weekdays} left before {deadline.isoformat()}.",
            days_left,
        )
    return None, days_left


def sync_account_rules(session: Session, acc: Account) -> list[AccountRuleRead]:
    """Refresh every configured rule and persist newly resolved milestones.

    The live numbers come from the same ``_prop_numbers`` calculator the
    prop-status endpoint uses, so the web card, the rules endpoint and the
    Telegram view cannot drift.
    """
    from app.routers.accounts import _prop_numbers

    numbers = _prop_numbers(acc, session)
    setting = get_trading_day(session)
    now = _now()
    today = setting.day_of(now)
    configured = configured_rules(acc)

    rows = {
        row.kind: row
        for row in session.exec(
            select(AccountRule).where(AccountRule.account_id == acc.id)
        ).all()
    }

    # A limit the user switched off should disappear from the card.
    for kind, row in list(rows.items()):
        if kind not in configured:
            session.delete(row)
            rows.pop(kind)

    for kind, target in configured.items():
        row = rows.get(kind)
        if row is None:
            row = AccountRule(account_id=acc.id, kind=kind, target=target)
            session.add(row)
            rows[kind] = row
        row.target = round(target, 2)
        row.current = _round(_current_value(kind, numbers))
        row.updated_at = now

        # A daily-loss breach belongs to the day it happened. The next
        # trading day starts with a clean slate; the event log keeps history.
        if row.kind == "daily_loss" and row.met_at is not None:
            if setting.day_of(row.met_at) < today:
                row.met_at = None

        resolved = _resolved(kind, row.current, target)
        if resolved and row.met_at is None:
            row.met_at = now
            log_account_event(
                session,
                acc.id,
                "rule_breached" if kind in BREACH_KINDS else "rule_met",
                {
                    "rule": kind,
                    "label": RULE_LABELS[kind],
                    "target": row.target,
                    "current": row.current,
                    "unit": RULE_UNITS[kind],
                },
                occurred_at=now,
            )
        session.add(row)

    # Flush so new rows have ids before they are serialised.
    session.flush()
    result = [
        _serialize(rows[kind], acc, today)
        for kind in RULE_KINDS
        if kind in rows
    ]
    session.commit()
    return result


def _serialize(row: AccountRule, acc: Account, today: date_type) -> AccountRuleRead:
    warning, days_left = _warning(row, acc.deadline, today)
    return AccountRuleRead(
        id=row.id or 0,
        account_id=row.account_id,
        kind=row.kind,
        label=RULE_LABELS.get(row.kind, row.kind),
        unit=RULE_UNITS.get(row.kind, ""),
        target=row.target,
        current=row.current,
        status=_status(row, acc.deadline, today),
        met_at=row.met_at,
        warning=warning,
        days_left=days_left,
    )


def _event_label(kind: str, payload: dict[str, Any]) -> str:
    if kind == "account_created":
        return "Account created"
    if kind == "rule_met":
        return f"{payload.get('label', 'Rule')} met"
    if kind == "rule_breached":
        return f"{payload.get('label', 'Rule')} breached"
    if kind == "status_changed":
        return f"Status: {payload.get('from', '?')} → {payload.get('to', '?')}"
    return kind.replace("_", " ").capitalize()


def list_account_timeline(
    session: Session, acc: Account, limit: int = 50
) -> list[AccountEventRead]:
    """The account's history, newest first, anchored by its creation.

    Creation is synthesised from ``account.created_at`` so accounts that
    predate this table still get a complete timeline. It is always shown,
    even when the event limit only covers recent activity.
    """
    events = session.exec(
        select(AccountEvent)
        .where(AccountEvent.account_id == acc.id)
        .order_by(AccountEvent.occurred_at.desc(), AccountEvent.id.desc())
        .limit(limit)
    ).all()

    timeline: list[AccountEventRead] = []
    for event in events:
        try:
            parsed = json.loads(event.payload or "{}")
            payload = parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            payload = {"raw": event.payload}
        timeline.append(
            AccountEventRead(
                id=event.id,
                account_id=event.account_id,
                kind=event.kind,
                label=_event_label(event.kind, payload),
                payload=payload,
                occurred_at=event.occurred_at,
            )
        )

    timeline.append(
        AccountEventRead(
            id=None,
            account_id=acc.id or 0,
            kind="account_created",
            label=_event_label("account_created", {}),
            payload={"alias": acc.alias},
            occurred_at=as_naive_utc(acc.created_at) or _now(),
        )
    )
    return timeline
