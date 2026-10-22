"""Plan adherence — did the day follow the pre-market note?

The pre-market note is free text, so the score is a reading of it, not a
proof. The rule is deliberately conservative:

- the setups the plan names are the ones it writes with a marker (``#fvg``)
  or with a word that is already a tag in the journal;
- the size the plan states is the number it writes next to "lots" or "size";
- the day is scored against those, and the parts the plan did not state are
  left out of the score rather than counted as a miss.

A plan that named one setup and a day that traded another scores low — that
is the whole point of the score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date as date_type
from typing import Optional, Sequence

# A marker in the note: #fvg or !late.
_MARKER = re.compile(r"[#!]([A-Za-z0-9_\-]{2,})")
# A size in the note: "0.5 lots", "size 0.5", "0.2 lot".
_SIZE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:lots?|sizes?|contracts?|units?)\b", re.I)
_SIZE_LABELLED = re.compile(r"\b(?:size|lots?)\s*[:=]?\s*(\d+(?:\.\d+)?)", re.I)


@dataclass(frozen=True)
class Adherence:
    """How the day lined up with the plan."""

    day: date_type
    has_plan: bool
    score: Optional[float] = None
    planned_setups: list[str] = field(default_factory=list)
    traded_setups: list[str] = field(default_factory=list)
    setup_match: Optional[float] = None
    planned_size: Optional[float] = None
    size_match: Optional[float] = None
    trades: int = 0
    discipline_breach: bool = False
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "day": self.day.isoformat(),
            "has_plan": self.has_plan,
            "score": self.score,
            "planned_setups": self.planned_setups,
            "traded_setups": self.traded_setups,
            "setup_match": self.setup_match,
            "planned_size": self.planned_size,
            "size_match": self.size_match,
            "trades": self.trades,
            "discipline_breach": self.discipline_breach,
            "notes": self.notes,
        }


def extract_planned_setups(note: str, known_tags: Sequence[str] = ()) -> list[str]:
    """The setups the plan names.

    A marker (``#fvg``) always counts. A plain word only counts when it is
    already a tag in the journal — otherwise every note would plan every
    word it contains.
    """
    text = (note or "").strip()
    if not text:
        return []
    planned: list[str] = []

    def add(name: str) -> None:
        name = name.strip().lower()
        if name and name not in planned:
            planned.append(name)

    for match in _MARKER.finditer(text):
        add(match.group(1))
    for name in known_tags:
        clean = (name or "").strip().lower()
        # Short words are too easy to hit by accident ("a", "late" in
        # "later"), so a plain mention only counts from three letters up.
        if len(clean) < 3:
            continue
        if re.search(rf"\b{re.escape(clean)}\b", text, re.I):
            add(clean)
    return planned


def extract_planned_size(note: str) -> Optional[float]:
    """The size the plan states, if it states one."""
    text = (note or "").strip()
    if not text:
        return None
    for pattern in (_SIZE, _SIZE_LABELLED):
        match = pattern.search(text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


def score_adherence(
    day: date_type,
    note: Optional[str],
    trades: Sequence,
    known_tags: Sequence[str] = (),
    discipline_breach: bool = False,
) -> Adherence:
    """Score the day against the plan.

    ``trades`` are the day's trades — the ones that closed on it plus the
    ones still open on it.
    """
    text = (note or "").strip()
    planned = extract_planned_setups(text, known_tags)
    planned_size = extract_planned_size(text)

    traded: list[str] = []
    for trade in trades:
        for tag in getattr(trade, "tags", []) or []:
            name = (getattr(tag, "name", "") or "").strip().lower()
            if name and name not in traded:
                traded.append(name)
    traded.sort()

    notes: list[str] = []
    if not text:
        return Adherence(
            day=day,
            has_plan=False,
            trades=len(trades),
            traded_setups=traded,
            discipline_breach=discipline_breach,
            notes=["No pre-market plan for this day."],
        )

    components: list[tuple[float, float]] = []  # (weight, value)

    setup_match: Optional[float] = None
    if planned:
        hit = [name for name in planned if name in traded]
        setup_match = round(len(hit) / len(planned), 4)
        components.append((0.5, setup_match))
        if hit:
            notes.append(f"Traded {len(hit)} of {len(planned)} planned setups ({', '.join(hit)}).")
        else:
            notes.append(
                f"The plan named {', '.join(planned)}; the day traded "
                f"{', '.join(traded) if traded else 'nothing'}."
            )
    else:
        notes.append("The plan names no setup, so setups are not scored.")

    size_match: Optional[float] = None
    if planned_size is not None:
        sizes = [getattr(t, "size", None) for t in trades]
        known = [s for s in sizes if s is not None]
        matched = [s for s in known if abs(float(s) - planned_size) < 1e-9]
        size_match = round(len(matched) / len(known), 4) if known else 0.0
        components.append((0.15, size_match))
        if known:
            notes.append(
                f"{len(matched)} of {len(known)} trades matched the planned size of {planned_size}."
            )
        else:
            notes.append(f"The plan stated a size of {planned_size}; the day traded nothing to compare.")

    # Execution is "the day acted on the plan", not "the day traded": a
    # trade of the wrong setup is not an execution of the plan.
    if setup_match is None:
        executed = bool(trades)
    else:
        executed = setup_match > 0
    components.append((0.2, 1.0 if executed else 0.0))
    if trades:
        notes.append(f"{len(trades)} trade(s) taken on the day.")
    else:
        notes.append("No trades were taken on the day.")

    components.append((0.15, 0.0 if discipline_breach else 1.0))
    if discipline_breach:
        notes.append("The day was flagged as a discipline breach.")

    total_weight = sum(w for w, _ in components)
    score = round(100 * sum(w * v for w, v in components) / total_weight, 1) if total_weight else None

    return Adherence(
        day=day,
        has_plan=True,
        score=score,
        planned_setups=planned,
        traded_setups=traded,
        setup_match=setup_match,
        planned_size=planned_size,
        size_match=size_match,
        trades=len(trades),
        discipline_breach=discipline_breach,
        notes=notes,
    )
