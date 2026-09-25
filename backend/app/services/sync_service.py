"""Bot CSV sync engine (PLAN Task 1.3).

Reads the Telegram logger CSV at TG_BOT_CSV_PATH, dedupes on `trade_id`,
maps `#tags` -> setup and `!tags` -> mistake, and backfills missing
`net_pnl` (gross_pnl - fees) and `r_multiple` before storing.
"""

import math
import os
import re
from datetime import datetime
from typing import Optional

import pandas as pd
from sqlmodel import Session, select

from app.models import Tag, Trade

TAG_RE = re.compile(r"[#!][\w\-/]+")


def get_csv_path() -> str:
    return os.getenv("TG_BOT_CSV_PATH", "./data/trades.csv")


def parse_tags(raw: object) -> list[tuple[str, str]]:
    """Split a tags cell into (name, category) pairs.

    `#fvg` -> ("fvg", "setup"), `!early` -> ("early", "mistake").
    Bare words without a prefix default to setup.
    """
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return []
    text = str(raw)
    found = [(m[1:].lower(), "setup" if m[0] == "#" else "mistake") for m in TAG_RE.findall(text)]
    if found:
        return found
    bare = [w.strip().lower() for w in text.replace(",", " ").split() if w.strip()]
    return [(w, "setup") for w in bare]


def _to_datetime(value: object) -> Optional[datetime]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        ts = pd.to_datetime(text)
        if pd.isna(ts):
            return None
        return ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
    except (ValueError, TypeError):
        return None


def _to_float(value: object) -> Optional[float]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip().lstrip("+")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_str(value: object) -> Optional[str]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def compute_r_multiple(
    direction: Optional[str],
    entry: Optional[float],
    stop: Optional[float],
    exit_price: Optional[float],
) -> Optional[float]:
    if entry is None or stop is None or exit_price is None:
        return None
    risk = abs(entry - stop)
    if risk == 0:
        return None
    if (direction or "").lower().startswith("sell"):
        return (entry - exit_price) / risk
    return (exit_price - entry) / risk


def get_or_create_tag(session: Session, name: str, category: str) -> Tag:
    tag = session.exec(select(Tag).where(Tag.name == name)).first()
    if tag is None:
        tag = Tag(name=name, category=category)
        session.add(tag)
        session.flush()
    return tag


def row_to_trade_fields(row: pd.Series) -> dict:
    get = lambda col: row[col] if col in row.index else None  # noqa: E731
    direction = _to_str(get("direction"))
    entry = _to_float(get("entry_price"))
    stop = _to_float(get("initial_sl"))
    exit_price = _to_float(get("exit_price"))
    gross = _to_float(get("gross_pnl"))
    fees = _to_float(get("fees"))
    timestamp_close = _to_datetime(get("timestamp_close"))

    net = _to_float(get("net_pnl"))
    if net is None and gross is not None:
        net = gross - (fees or 0.0)

    r_multiple = _to_float(get("r_multiple"))
    if r_multiple is None:
        r_multiple = compute_r_multiple(direction, entry, stop, exit_price)

    status = _to_str(get("status"))
    if status is None:
        status = "CLOSED" if (timestamp_close is not None or exit_price is not None) else "OPEN"
    status = status.upper()

    return {
        "timestamp_open": _to_datetime(get("timestamp_open")),
        "timestamp_close": timestamp_close,
        "direction": direction.lower() if direction else None,
        "symbol": _to_str(get("symbol")),
        "size": _to_float(get("size")),
        "entry_price": entry,
        "initial_sl": stop,
        "current_sl": _to_float(get("current_sl")),
        "tp": _to_float(get("tp")),
        "exit_price": exit_price,
        "gross_pnl": gross,
        "fees": fees,
        "net_pnl": net,
        "r_multiple": r_multiple,
        "status": status,
        "thesis": _to_str(get("thesis")),
        "review_notes": _to_str(get("review_notes")),
    }


def _apply_tags(session: Session, trade: Trade, raw: object) -> None:
    trade.tags = [get_or_create_tag(session, name, cat) for name, cat in parse_tags(raw)]


def sync_trades(session: Session, csv_path: Optional[str] = None) -> dict:
    """Upsert every CSV row keyed by `trade_id`.

    Returns {"inserted": int, "updated": int, "total": int}.
    Raises FileNotFoundError when the CSV is absent.
    """
    path = csv_path or get_csv_path()
    if not os.path.exists(path):
        raise FileNotFoundError(f"Bot CSV not found: {path}")

    df = pd.read_csv(path, dtype=str).fillna(value=float("nan"))
    inserted_ids: set[str] = set()
    updated_ids: set[str] = set()

    for _, row in df.iterrows():
        trade_id = _to_str(row["trade_id"]) if "trade_id" in row.index else None
        if not trade_id:
            continue
        fields = row_to_trade_fields(row)
        trade = session.exec(select(Trade).where(Trade.trade_id == trade_id)).first()
        if trade is None:
            trade = Trade(trade_id=trade_id, **fields)
            session.add(trade)
            session.flush()
            _apply_tags(session, trade, row["tags"] if "tags" in row.index else None)
            inserted_ids.add(trade_id)
        else:
            for key, value in fields.items():
                # Keep existing values unless the row carries a fresh one —
                # except status/close fields, which always reflect the latest row.
                if value is not None or key in (
                    "status",
                    "timestamp_close",
                    "exit_price",
                    "net_pnl",
                    "r_multiple",
                ):
                    setattr(trade, key, value)
            _apply_tags(session, trade, row["tags"] if "tags" in row.index else None)
            session.add(trade)
            updated_ids.add(trade_id)

    session.commit()
    total = len(session.exec(select(Trade)).all())
    return {"inserted": len(inserted_ids), "updated": len(updated_ids), "total": total}
