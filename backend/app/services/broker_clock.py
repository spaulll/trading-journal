"""The broker clock — a rule, not a single number.

The MT5 server shows its own wall clock. It is not UTC, it is not IST, and it
moves once or twice a year when the broker follows a daylight-saving rule.
A journal that stores one integer ("the broker is three hours ahead") is
correct until the first switch and silently wrong afterwards.

So the clock is stored as a *rule*:

    base_offset_minutes   the standard (winter) offset, e.g. 120
    dst                   "us" | "eu" | "none" — which calendar the broker follows
    overrides             dated manual corrections, newest wins

``offset_for(moment)`` answers "how far ahead of UTC was the broker at this
instant", using the moment's own date — which is what a backfilled trade
needs. ``next_change()`` answers "when does this rule move next", which is
what the misc page shows.

Storage stays naive UTC everywhere; this module only translates at the edges.

Per firm
--------
A broker clock belongs to a broker server, not to an account, so the key is
the account's ``firm`` string. ``DEFAULT_FIRM`` is the fallback for trades
with no account. A legacy ``broker_offset_minutes`` setting is read as the
default firm's fixed offset, so an install that has never opened the misc
page keeps working exactly as before.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from app.models import Account, AppSetting
from app.services.timeutils import as_naive_utc

BROKER_CLOCK_KEY = "broker_clock"
LEGACY_OFFSET_KEY = "broker_offset_minutes"
DEFAULT_FIRM = "__default__"

IST_OFFSET = timedelta(hours=5, minutes=30)
MAX_OFFSET_MINUTES = 18 * 60

DST_RULES = ("us", "eu", "none")
# The zone is only used for its DST *calendar*: the base offset is ours.
_DST_ZONES = {
    "us": "America/New_York",
    "eu": "Europe/Athens",
}
_DST_RULE_LABELS = {
    "us": "US schedule (second Sunday in March → first Sunday in November)",
    "eu": "EU schedule (last Sunday in March → last Sunday in October)",
    "none": "No daylight saving — fixed offset all year",
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive(moment: datetime) -> datetime:
    converted = as_naive_utc(moment)
    assert converted is not None
    return converted


def normalize_firm(firm: Optional[str]) -> str:
    """The storage key for a firm name ("GFT" → "gft")."""
    return (firm or "").strip().lower() or DEFAULT_FIRM


def format_label(minutes: int) -> str:
    """+210 → 'UTC+3:30', -300 → 'UTC-5:00'."""
    sign = "+" if minutes >= 0 else "-"
    total = abs(int(minutes))
    return f"UTC{sign}{total // 60}:{total % 60:02d}"


def _in_dst(rule: str, moment: datetime) -> bool:
    if rule == "none":
        return False
    zone = ZoneInfo(_DST_ZONES[rule])
    local = moment.replace(tzinfo=timezone.utc).astimezone(zone)
    return bool(local.dst())


def _dst_transitions(rule: str, start: datetime, days: int = 400) -> list[datetime]:
    """Every DST change after ``start`` within the search window."""
    if rule == "none":
        return []
    changes: list[datetime] = []
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    previous: Optional[bool] = None
    for offset in range(days + 2):
        current_day = day + timedelta(days=offset)
        state = _in_dst(rule, current_day)
        if previous is not None and state != previous:
            # The change happened between yesterday 00:00 and today 00:00:
            # narrow it down hour by hour across that window.
            window_start = current_day - timedelta(days=1)
            for hour in range(25):
                probe = window_start + timedelta(hours=hour)
                if _in_dst(rule, probe) != previous:
                    changes.append(probe)
                    break
        previous = state
    return changes


@dataclass(frozen=True)
class BrokerClock:
    """How far ahead of UTC a broker runs, on any given date."""

    base_offset_minutes: int = 120
    dst: str = "none"
    overrides: tuple[tuple[datetime, int], ...] = ()

    def __post_init__(self) -> None:
        if self.dst not in DST_RULES:
            raise ValueError(f"dst must be one of {DST_RULES}")
        if not -MAX_OFFSET_MINUTES <= self.base_offset_minutes <= MAX_OFFSET_MINUTES:
            raise ValueError("base_offset_minutes is implausible")
        for when, minutes in self.overrides:
            if not -MAX_OFFSET_MINUTES <= minutes <= MAX_OFFSET_MINUTES:
                raise ValueError("override offset is implausible")
            if when.tzinfo is not None:
                raise ValueError("override dates must be naive UTC")

    # --- resolution -------------------------------------------------------

    def auto_offset_for(self, moment: datetime) -> int:
        """The rule's answer, ignoring manual corrections."""
        moment = _naive(moment)
        return self.base_offset_minutes + (60 if _in_dst(self.dst, moment) else 0)

    def offset_for(self, moment: datetime) -> int:
        """The offset in force at ``moment``. A manual correction pins."""
        moment = _naive(moment)
        pinned: Optional[int] = None
        for when, minutes in sorted(self.overrides):
            if when <= moment:
                pinned = minutes
        return pinned if pinned is not None else self.auto_offset_for(moment)

    def is_manual_at(self, moment: datetime) -> bool:
        moment = _naive(moment)
        return any(when <= moment for when, _ in self.overrides)

    def next_change(self, after: Optional[datetime] = None) -> Optional[tuple[datetime, int]]:
        """The next instant the offset differs from what it is now."""
        moment = _naive(after or _now())
        current = self.offset_for(moment)

        candidates: list[datetime] = [
            when for when, _ in self.overrides if when > moment
        ]
        candidates.extend(_dst_transitions(self.dst, moment))

        upcoming = sorted(
            when for when in candidates if when > moment and self.offset_for(when) != current
        )
        if not upcoming:
            return None
        when = upcoming[0]
        return when, self.offset_for(when)

    # --- serialisation ----------------------------------------------------

    def to_payload(self) -> dict:
        return {
            "base_offset_minutes": self.base_offset_minutes,
            "dst": self.dst,
            "overrides": [
                {"effective_from": when.isoformat(), "offset_minutes": minutes}
                for when, minutes in sorted(self.overrides)
            ],
        }


def _from_payload(payload: object) -> Optional[BrokerClock]:
    if not isinstance(payload, dict):
        return None
    try:
        base = int(payload.get("base_offset_minutes", 120))
        rule = str(payload.get("dst", "none")).strip().lower()
        overrides: list[tuple[datetime, int]] = []
        for item in payload.get("overrides", []) or []:
            if not isinstance(item, dict):
                continue
            when = datetime.fromisoformat(str(item["effective_from"]))
            if when.tzinfo is not None:
                when = when.astimezone(timezone.utc).replace(tzinfo=None)
            overrides.append((when, int(item["offset_minutes"])))
        return BrokerClock(
            base_offset_minutes=base,
            dst=rule,
            overrides=tuple(sorted(overrides)),
        )
    except (KeyError, TypeError, ValueError):
        return None


# --- storage ---------------------------------------------------------------


def _read_raw(session: Session) -> dict[str, dict]:
    row = session.get(AppSetting, BROKER_CLOCK_KEY)
    if row is None or not row.value:
        return {}
    try:
        payload = json.loads(row.value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(k): v for k, v in payload.items() if isinstance(v, dict)}


def _write_raw(session: Session, raw: dict[str, dict]) -> None:
    row = session.get(AppSetting, BROKER_CLOCK_KEY)
    if row is None:
        row = AppSetting(key=BROKER_CLOCK_KEY, value="")
    row.value = json.dumps(raw, sort_keys=True)
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)


def _legacy_clock(session: Session) -> Optional[BrokerClock]:
    row = session.get(AppSetting, LEGACY_OFFSET_KEY)
    if row is None:
        return None
    try:
        return BrokerClock(base_offset_minutes=int(row.value), dst="none")
    except (TypeError, ValueError):
        return None


def configured_clocks(session: Session) -> list[tuple[str, BrokerClock]]:
    """Every stored clock, keyed by its firm name."""
    clocks: list[tuple[str, BrokerClock]] = []
    for key, payload in sorted(_read_raw(session).items()):
        clock = _from_payload(payload)
        if clock is None:
            continue
        firm = str(payload.get("firm") or ("" if key == DEFAULT_FIRM else key))
        clocks.append((firm, clock))
    if not clocks:
        legacy = _legacy_clock(session)
        if legacy is not None:
            clocks.append(("", legacy))
    return clocks


def get_clock(session: Session, firm: Optional[str] = None) -> Optional[BrokerClock]:
    """The clock for ``firm``, falling back to the default then the only one."""
    raw = _read_raw(session)
    if firm:
        payload = raw.get(normalize_firm(firm))
        if payload is not None:
            clock = _from_payload(payload)
            if clock is not None:
                return clock
    payload = raw.get(DEFAULT_FIRM)
    if payload is not None:
        clock = _from_payload(payload)
        if clock is not None:
            return clock
    stored = [
        clock
        for clock in (_from_payload(item) for item in raw.values())
        if clock is not None
    ]
    if len(stored) == 1:
        return stored[0]
    return _legacy_clock(session)


def get_clock_for_account(
    session: Session, account_id: Optional[int]
) -> Optional[BrokerClock]:
    """Resolve trade → account → firm → clock."""
    if account_id is not None:
        account = session.get(Account, account_id)
        if account is not None and account.firm.strip():
            clock = get_clock(session, account.firm)
            if clock is not None:
                return clock
    return get_clock(session)


def set_clock(
    session: Session,
    firm: Optional[str],
    base_offset_minutes: int,
    dst: str,
) -> BrokerClock:
    """Upsert a firm's rule. The caller commits."""
    raw = _read_raw(session)
    key = normalize_firm(firm)
    existing = _from_payload(raw.get(key)) if key in raw else None
    clock = BrokerClock(
        base_offset_minutes=int(base_offset_minutes),
        dst=str(dst),
        # Editing the rule keeps any manual corrections the trader recorded.
        overrides=existing.overrides if existing is not None else (),
    )
    display = (firm or "").strip() or ("Default" if key == DEFAULT_FIRM else key)
    raw[key] = {"firm": display, **clock.to_payload()}
    _write_raw(session, raw)
    return clock


def set_override(
    session: Session,
    firm: Optional[str],
    offset_minutes: int,
    effective_from: Optional[datetime] = None,
) -> BrokerClock:
    """Pin the offset from a date onwards (a manual correction)."""
    key = normalize_firm(firm)
    raw = _read_raw(session)
    clock = _from_payload(raw.get(key)) if key in raw else None
    if clock is None:
        clock = get_clock(session, firm) or BrokerClock()
    when = _naive(effective_from or _now())
    clock = replace(
        clock,
        overrides=tuple(sorted(clock.overrides + ((when, int(offset_minutes)),))),
    )
    display = (firm or "").strip() or ("Default" if key == DEFAULT_FIRM else key)
    raw[key] = {"firm": display, **clock.to_payload()}
    _write_raw(session, raw)
    return clock


def clear_overrides(session: Session, firm: Optional[str]) -> BrokerClock:
    key = normalize_firm(firm)
    raw = _read_raw(session)
    clock = _from_payload(raw.get(key)) if key in raw else None
    if clock is None:
        clock = get_clock(session, firm) or BrokerClock()
    clock = replace(clock, overrides=())
    display = (firm or "").strip() or ("Default" if key == DEFAULT_FIRM else key)
    raw[key] = {"firm": display, **clock.to_payload()}
    _write_raw(session, raw)
    return clock


def known_firms(session: Session) -> list[str]:
    """Firms in the account table, plus any firm that already has a clock."""
    names: list[str] = []
    seen: set[str] = set()
    for firm in session.exec(select(Account.firm)).all():
        cleaned = (firm or "").strip()
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            names.append(cleaned)
    for firm, _clock in configured_clocks(session):
        if firm and firm.lower() not in seen:
            seen.add(firm.lower())
            names.append(firm)
    return sorted(names, key=str.lower)


# --- legacy single-offset API ---------------------------------------------


def get_offset_minutes(session: Session) -> Optional[int]:
    """Offset in force right now, or None when the clock was never set."""
    clock = get_clock(session)
    if clock is None:
        return None
    return clock.offset_for(_now())


def set_offset_minutes(session: Session, minutes: int) -> None:
    """Pin the current offset — what the bot's /brokertime has always done."""
    set_override(session, None, minutes)


def calibrate(mt5_wall: datetime, ist_wall: datetime) -> int:
    """Offset minutes from two same-instant readings (both naive wall clocks)."""
    offset = (mt5_wall - ist_wall) + IST_OFFSET
    if abs(offset) > timedelta(minutes=MAX_OFFSET_MINUTES):
        raise ValueError(
            f"Implausible broker offset {offset} — check both times are the same instant"
        )
    return int(round(offset.total_seconds() / 60))


def broker_to_naive_utc(wall: datetime, offset_minutes: int) -> datetime:
    return wall - timedelta(minutes=offset_minutes)


def naive_utc_to_broker(wall_utc_naive: datetime, offset_minutes: int) -> datetime:
    return wall_utc_naive + timedelta(minutes=offset_minutes)


def dst_rule_label(rule: str) -> str:
    return _DST_RULE_LABELS.get(rule, rule)
