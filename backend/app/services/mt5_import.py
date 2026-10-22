"""MT5 statement import (HTML report or CSV export).

MetaTrader 5 can save its account history as an HTML report or export a
table to CSV. This module turns either one into journal trades and hands
them to the API, which owns the database write.

Two table shapes are understood:

``positions``
    One row per position: entry time/price and exit time/price side by
    side (the HTML report's *Positions* section, and the CSV export of the
    same table). The position ticket is the trade ticket.

``deals``
    One row per deal (in / out / in-out). Positions are reconstructed by
    matching each out deal with the earliest open deal on the opposite
    side of the same symbol — the statement has no position column to
    group by. The entry deal's ticket becomes the trade ticket.

Money
-----
MT5 reports ``Profit`` (the trade's own result) plus ``Commission`` and
``Swap`` (both usually negative). The journal's invariant is
``net = gross - fees``, so the statement's ``Profit`` is the gross and
``fees = -(commission + swap)``. A swap credit makes ``fees`` negative,
which is exactly what the invariant needs: the trader was paid.

Times are imported as the broker wrote them (naive), not converted: the
statement carries no zone, and inventing one would shift every trade.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Optional

from sqlmodel import Session, select

from app.models import Account, Trade
from app.services.session_resolver import duration_minutes, normalize_session
from app.services.symbol_registry import (
    apply_trade_risk,
    compute_r_multiple,
)
from app.services.trade_money import quote_currency_for, set_trade_pnl

# Every timestamp shape MT5 has been seen to write. Dotted dates are the
# report default; the dashed ones appear in hand-cleaned exports.
_TIME_FORMATS = (
    "%Y.%m.%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%Y.%m.%d",
    "%Y-%m-%d",
    "%d.%m.%Y",
)

_DATE_RE = re.compile(r"^\s*(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}|\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})")

# The broker fields an import owns. Everything else on the trade — the
# thesis, the review, the tags, the screenshots — is the trader's and is
# never touched by a re-import.
SYNC_FIELDS = (
    "symbol",
    "direction",
    "size",
    "entry_price",
    "initial_sl",
    "tp",
    "exit_price",
    "entry_time",
    "exit_time",
    "gross_pnl",
    "fees",
)

# Fields a statement may simply not carry (a deal export has no stop, a
# hand-cut CSV may have no profit column). A missing column must not erase
# what the trader already recorded, so these are only compared and written
# when the row says the statement has them.
_OPTIONAL = ("initial_sl", "tp", "gross_pnl", "fees")


class StatementError(ValueError):
    """The file is not a readable MT5 statement."""


@dataclass
class ParsedStatement:
    format: str  # "html" | "csv"
    rows: list[dict] = field(default_factory=list)
    account_login: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


# --- small value readers ----------------------------------------------------


def _norm_header(cell: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(cell or "").strip().lower())


def _num(cell: object) -> Optional[float]:
    """Read a broker number: blanks, dashes and thousands separators."""
    text = str(cell or "").replace("\u00a0", " ").strip()
    if not text or text in ("-", "—", "–", "n/a", "N/A"):
        return None
    text = text.replace("\u2212", "-").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        # A lone comma is the decimal mark in a European export.
        text = text.replace(",", ".")
    try:
        return float(text.lstrip("+"))
    except ValueError:
        return None


def _when(cell: object) -> Optional[datetime]:
    text = str(cell or "").replace("\u00a0", " ").strip()
    if not text:
        return None
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    # MT5 sometimes appends a timezone name to the stamp.
    head = text.split()[0] if text.split() else ""
    if head != text:
        return _when(head)
    return None


def _is_date(cell: object) -> bool:
    return bool(_DATE_RE.match(str(cell or "")))


def _pick(header: list[str], *names: str) -> Optional[int]:
    wanted = {_norm_header(n) for n in names}
    for idx, cell in enumerate(header):
        if _norm_header(cell) in wanted:
            return idx
    return None


def _pick_nth(header: list[str], name: str, occurrence: int) -> Optional[int]:
    """Index of the n-th column with this header (0-based occurrence).

    The Positions table repeats ``Time`` and ``Price`` for the entry and
    the exit leg; the second occurrence is the exit.
    """
    wanted = _norm_header(name)
    seen = 0
    for idx, cell in enumerate(header):
        if _norm_header(cell) == wanted:
            if seen == occurrence:
                return idx
            seen += 1
    return None


def _cell(row: list[str], idx: Optional[int]) -> str:
    if idx is None or idx < 0 or idx >= len(row):
        return ""
    return row[idx]


# --- HTML table extraction --------------------------------------------------


class _TableExtractor(HTMLParser):
    """Collect every ``<table>`` as a list of rows of cell text.

    MT5's report nests tables (a summary table inside the page), so the
    parser keeps a frame per open table. Nested tables are emitted as their
    own table and do not corrupt the parent.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._frames: list[dict] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        tag = tag.lower()
        if tag == "table":
            self._frames.append({"rows": [], "row": None, "cell": None})
            return
        if not self._frames:
            return
        frame = self._frames[-1]
        if tag == "tr":
            frame["row"] = []
        elif tag in ("td", "th") and frame["row"] is not None:
            frame["cell"] = []
        elif tag == "br" and frame["cell"] is not None:
            frame["cell"].append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if not self._frames:
            return
        frame = self._frames[-1]
        if tag in ("td", "th") and frame["cell"] is not None:
            text = " ".join("".join(frame["cell"]).split())
            if frame["row"] is not None:
                frame["row"].append(text)
            frame["cell"] = None
        elif tag == "tr" and frame["row"] is not None:
            if frame["row"]:
                frame["rows"].append(frame["row"])
            frame["row"] = None
        elif tag == "table":
            done = self._frames.pop()
            if done["row"]:
                done["rows"].append(done["row"])
            if done["rows"]:
                self.tables.append(done["rows"])

    def handle_data(self, data: str) -> None:
        if not self._frames:
            return
        cell = self._frames[-1]["cell"]
        if cell is not None:
            cell.append(data)


def _header_index(rows: list[list[str]]) -> Optional[int]:
    """First row that names a Symbol plus a Position/Deal/Type column."""
    for idx, row in enumerate(rows):
        norms = {_norm_header(c) for c in row}
        if "symbol" in norms and ({"position", "deal", "type"} & norms):
            return idx
    return None


# --- row layouts ------------------------------------------------------------


def _position_layout(header: list[str]) -> Optional[dict]:
    symbol = _pick(header, "symbol")
    side = _pick(header, "type")
    volume = _pick(header, "volume", "lots", "size")
    entry_price = _pick_nth(header, "price", 0)
    if symbol is None or side is None or volume is None or entry_price is None:
        return None
    return {
        "kind": "positions",
        "ticket": _pick(header, "position", "order", "deal", "ticket"),
        "symbol": symbol,
        "side": side,
        "volume": volume,
        "entry_price": entry_price,
        "exit_price": _pick_nth(header, "price", 1),
        "entry_time": _pick_nth(header, "time", 0),
        "exit_time": _pick_nth(header, "time", 1),
        "sl": _pick(header, "sl", "stoploss"),
        "tp": _pick(header, "tp", "takeprofit"),
        "commission": _pick(header, "commission"),
        "swap": _pick(header, "swap"),
        "profit": _pick(header, "profit"),
    }


def _deal_layout(header: list[str]) -> Optional[dict]:
    symbol = _pick(header, "symbol")
    side = _pick(header, "type")
    volume = _pick(header, "volume", "lots", "size")
    price = _pick(header, "price")
    if symbol is None or side is None or volume is None or price is None:
        return None
    return {
        "kind": "deals",
        "ticket": _pick(header, "position", "deal", "ticket"),
        "symbol": symbol,
        "side": side,
        "volume": volume,
        "price": price,
        "time": _pick(header, "time"),
        "direction": _pick(header, "direction", "entryexit"),
        "commission": _pick(header, "commission"),
        "swap": _pick(header, "swap"),
        "profit": _pick(header, "profit"),
    }


def _fees_of(row: list[str], layout: dict) -> float:
    commission = _num(_cell(row, layout.get("commission"))) or 0.0
    swap = _num(_cell(row, layout.get("swap"))) or 0.0
    return round(-(commission + swap), 2)


def _ticket_of(raw: str, fallback: str, seen: set[str]) -> str:
    """A stable, unique ticket for the statement row."""
    ticket = (raw or "").strip()
    if not ticket or ticket in ("-", "—"):
        ticket = fallback
    base, n = ticket, 2
    while ticket in seen:
        ticket = f"{base}-{n}"
        n += 1
    seen.add(ticket)
    return ticket


def _position_row(row: list[str], layout: dict, seen: set[str]) -> Optional[dict]:
    symbol = _cell(row, layout["symbol"]).strip().upper().rstrip(".")
    side = _cell(row, layout["side"]).strip().lower()
    size = _num(_cell(row, layout["volume"]))
    entry = _num(_cell(row, layout["entry_price"]))
    exit_price = _num(_cell(row, layout["exit_price"]))
    entry_time = _when(_cell(row, layout["entry_time"]))
    exit_time = _when(_cell(row, layout["exit_time"]))
    if not symbol or side not in ("buy", "sell") or size is None or size <= 0:
        return None
    if entry is None:
        return None
    # An open position is not a ledger row: the journal tracks it live.
    if exit_price is None or exit_time is None:
        return None
    stamp = entry_time or exit_time
    fallback = f"MT5-{symbol}-{stamp.strftime('%Y%m%dT%H%M%S') if stamp else 'unknown'}"
    ticket = _ticket_of(_cell(row, layout["ticket"]), fallback, seen)
    gross = _num(_cell(row, layout["profit"]))
    return {
        "ticket": ticket,
        "symbol": symbol,
        "direction": side,
        "size": size,
        "entry_price": entry,
        "initial_sl": _num(_cell(row, layout["sl"])),
        "tp": _num(_cell(row, layout["tp"])),
        "exit_price": exit_price,
        "entry_time": entry_time,
        "exit_time": exit_time,
        "gross_pnl": gross,
        "fees": _fees_of(row, layout),
        # Which broker columns this table actually has.
        "_has_sl": layout.get("sl") is not None,
        "_has_tp": layout.get("tp") is not None,
        "_has_gross": layout.get("profit") is not None,
        "_has_fees": layout.get("commission") is not None or layout.get("swap") is not None,
    }


def _deal_row(row: list[str], layout: dict) -> Optional[dict]:
    symbol = _cell(row, layout["symbol"]).strip().upper().rstrip(".")
    side = _cell(row, layout["side"]).strip().lower()
    direction = _norm_header(_cell(row, layout["direction"]))
    size = _num(_cell(row, layout["volume"]))
    price = _num(_cell(row, layout["price"]))
    when = _when(_cell(row, layout["time"]))
    if not symbol or side not in ("buy", "sell") or size is None or size <= 0 or price is None:
        return None
    if direction not in ("in", "out", "inout", ""):
        return None
    return {
        "deal": _cell(row, layout["ticket"]).strip(),
        "symbol": symbol,
        "side": side,
        "direction": "inout" if direction == "inout" else (direction or "in"),
        "size": size,
        "price": price,
        "time": when,
        "commission": _num(_cell(row, layout["commission"])) or 0.0,
        "swap": _num(_cell(row, layout["swap"])) or 0.0,
        "profit": _num(_cell(row, layout["profit"])),
    }


def _pair_deals(deals: list[dict], warnings: list[str]) -> list[dict]:
    """Reconstruct positions from a flat deal list (FIFO per symbol/side).

    An ``out`` deal closes the oldest open deal on the opposite side. A
    partial close consumes only part of that entry, so the next out deal
    matches the same entry again; each consumed slice becomes its own ledger
    row. Summing the rows still gives the position's profit, and the
    ``entry deal / exit deal`` ticket stays stable across re-imports. A
    position with no matching close is left out: it is still open, and the
    live journal owns it.
    """
    open_deals: dict[str, list[dict]] = {}
    pairs: list[dict] = []
    unpaired = 0
    partial_unmatched = 0
    eps = 1e-9

    for deal in sorted(deals, key=lambda d: d["time"] or datetime.min):
        stack = open_deals.setdefault(deal["symbol"], [])
        if deal["direction"] == "inout":
            pairs.append(
                {
                    "entry": deal,
                    "exit": deal,
                    "closed_in_place": True,
                    "size": deal["size"],
                }
            )
            continue
        if deal["direction"] == "in":
            stack.append({**deal, "remaining": deal["size"]})
            continue

        opposite = "sell" if deal["side"] == "buy" else "buy"
        remaining = deal["size"]
        matched = False
        while remaining > eps:
            match_at = next(
                (
                    i
                    for i, d in enumerate(stack)
                    if d["side"] == opposite and d["remaining"] > eps
                ),
                None,
            )
            if match_at is None:
                break
            entry = stack[match_at]
            take = min(remaining, entry["remaining"])
            pairs.append(
                {
                    "entry": entry,
                    "exit": deal,
                    "closed_in_place": False,
                    "size": take,
                    # Split the entry's and exit's money by the volume each
                    # slice actually carried, so a partial close is not
                    # charged the whole entry commission twice.
                    "entry_share": take / entry["size"],
                    "exit_share": take / deal["size"],
                }
            )
            entry["remaining"] = round(entry["remaining"] - take, 8)
            remaining = round(remaining - take, 8)
            if entry["remaining"] <= eps:
                stack.pop(match_at)
            matched = True

        if not matched:
            unpaired += 1
        elif remaining > eps:
            partial_unmatched += 1

    rows: list[dict] = []
    for pair in pairs:
        entry, exit_ = pair["entry"], pair["exit"]
        if entry["time"] is None or exit_["time"] is None:
            # A deal with no stamp cannot be placed on the calendar.
            continue
        if pair["closed_in_place"]:
            # In-out is one deal: its profit is the whole result, counted once.
            gross = round(exit_["profit"] or 0.0, 2)
            fees = round(-((exit_["commission"] or 0.0) + (exit_["swap"] or 0.0)), 2)
        else:
            gross = round(
                (entry["profit"] or 0.0) * pair["entry_share"]
                + (exit_["profit"] or 0.0) * pair["exit_share"],
                2,
            )
            fees = round(
                -(
                    (entry["commission"] or 0.0) * pair["entry_share"]
                    + (exit_["commission"] or 0.0) * pair["exit_share"]
                    + (entry["swap"] or 0.0) * pair["entry_share"]
                    + (exit_["swap"] or 0.0) * pair["exit_share"]
                ),
                2,
            )
        deal_id = entry["deal"]
        ticket = (
            f"MT5-{deal_id}"
            if pair["closed_in_place"] or entry["deal"] == exit_["deal"]
            else f"MT5-{entry['deal']}-{exit_['deal']}"
        )
        rows.append(
            {
                "ticket": ticket,
                "symbol": entry["symbol"],
                "direction": entry["side"],
                "size": pair["size"],
                "entry_price": entry["price"],
                "initial_sl": None,
                "tp": None,
                "exit_price": exit_["price"],
                "entry_time": entry["time"],
                "exit_time": exit_["time"],
                "gross_pnl": gross,
                "fees": fees,
                "_has_sl": False,
                "_has_tp": False,
                "_has_gross": True,
                "_has_fees": True,
            }
        )
    if unpaired:
        warnings.append(f"{unpaired} deal(s) had no matching entry and were skipped.")
    if partial_unmatched:
        warnings.append(
            f"{partial_unmatched} deal(s) closed more volume than the open entry; "
            "the unmatched part was skipped."
        )
    return rows


# --- statement readers ------------------------------------------------------


def _rows_from_table(
    table: list[list[str]], seen: set[str], warnings: list[str]
) -> list[dict]:
    header_at = _header_index(table)
    if header_at is None:
        return []
    header, body = table[header_at], table[header_at + 1 :]

    # A deals table names a Direction column (in / out); a positions table
    # puts the entry and the exit leg side by side and has no Direction.
    if _pick(header, "direction", "entryexit") is not None:
        deal_layout = _deal_layout(header)
        if deal_layout is None:
            return []
        deals = []
        for row in body:
            if not _is_date(_cell(row, deal_layout.get("time"))):
                continue
            parsed = _deal_row(row, deal_layout)
            if parsed is not None:
                deals.append(parsed)
        return _pair_deals(deals, warnings)

    layout = _position_layout(header)
    if layout is None:
        return []
    out = []
    for row in body:
        if not _is_date(_cell(row, layout.get("entry_time"))):
            continue
        parsed = _position_row(row, layout, seen)
        if parsed is not None:
            out.append(parsed)
    return out


def _account_login(text: str) -> Optional[str]:
    patterns = (
        r"Account\s*(?:number|no\.?|#)?\s*[:\-]?\s*(\d{5,})",
        r"Login\s*[:\-]?\s*(\d{5,})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _parse_html(text: str) -> ParsedStatement:
    parser = _TableExtractor()
    parser.feed(text)
    seen: set[str] = set()
    rows: list[dict] = []
    warnings: list[str] = []
    for table in parser.tables:
        rows.extend(_rows_from_table(table, seen, warnings))
    return ParsedStatement(
        format="html",
        rows=rows,
        account_login=_account_login(text),
        warnings=warnings,
    )


def _sniff_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:20])
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,\t").delimiter
    except csv.Error:
        counts = {sep: sample.count(sep) for sep in (";", ",", "\t")}
        return max(counts, key=counts.get) if max(counts.values()) else ","


def _parse_csv(text: str) -> ParsedStatement:
    delimiter = _sniff_delimiter(text)
    table = [
        [cell.strip().strip('"') for cell in row]
        for row in csv.reader(io.StringIO(text), delimiter=delimiter)
    ]
    seen: set[str] = set()
    warnings: list[str] = []
    rows = _rows_from_table(table, seen, warnings)
    return ParsedStatement(format="csv", rows=rows, account_login=None, warnings=warnings)


def parse_statement(text: str, filename: str = "") -> ParsedStatement:
    """Read an MT5 HTML report or CSV export into normalized trade rows."""
    raw = (text or "").lstrip("\ufeff")
    if not raw.strip():
        raise StatementError("The file is empty.")
    name = (filename or "").lower()
    if "<table" in raw.lower() or name.endswith((".htm", ".html")):
        parsed = _parse_html(raw)
    else:
        parsed = _parse_csv(raw)
    if not parsed.rows:
        raise StatementError(
            "No closed positions were found. In MT5, open History, select "
            "Positions (or Deals) for the period, then save the report."
        )
    return parsed


def decode_statement(data: bytes) -> str:
    """Decode an uploaded statement; broker reports are not always UTF-8."""
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


# --- database write ---------------------------------------------------------


def resolve_account_id(
    session: Session, account_id: Optional[int], login: Optional[str]
) -> Optional[int]:
    """Account from the explicit import choice, else the statement's login."""
    if account_id is not None:
        return account_id
    if not login:
        return None
    account = session.exec(select(Account).where(Account.login == login)).first()
    return account.id if account is not None else None


def _same(left: object, right: object) -> bool:
    if isinstance(left, float) and isinstance(right, float):
        return abs(left - right) < 1e-6
    return left == right


_OPTIONAL_FLAG = {
    "initial_sl": "_has_sl",
    "tp": "_has_tp",
    "gross_pnl": "_has_gross",
    "fees": "_has_fees",
}


def _statement_fields(row: dict) -> list[str]:
    """The fields this row actually states (a deal row has no stop or target)."""
    return [
        name
        for name in SYNC_FIELDS
        if name not in _OPTIONAL_FLAG or row.get(_OPTIONAL_FLAG[name])
    ]


def _changed_fields(trade: Trade, row: dict) -> dict:
    changes: dict = {}
    for key in _statement_fields(row):
        incoming = row.get(key)
        current = getattr(trade, key, None)
        if not _same(current, incoming):
            changes[key] = {"from": current, "to": incoming}
    return changes


def _apply_row(session: Session, trade: Trade, row: dict, account_id: Optional[int]) -> None:
    """Write the broker-owned fields of one statement row onto a trade."""
    entry_time = row["entry_time"]
    exit_time = row["exit_time"]
    trade.timestamp_open = entry_time
    trade.entry_time = entry_time
    trade.timestamp_close = exit_time
    trade.exit_time = exit_time
    trade.duration_minutes = duration_minutes(entry_time, exit_time)
    trade.direction = row["direction"]
    trade.symbol = row["symbol"]
    trade.size = row["size"]
    trade.entry_price = row["entry_price"]
    trade.exit_price = row["exit_price"]
    # A column the statement does not have must not erase what the trader
    # entered by hand (a deal export carries no stop; a trimmed CSV no target).
    if row.get("_has_sl"):
        trade.initial_sl = row.get("initial_sl")
        trade.current_sl = row.get("initial_sl")
    if row.get("_has_tp"):
        trade.tp = row.get("tp")
    trade.status = "CLOSED"
    trade.quote_currency = quote_currency_for(session, trade.symbol)
    # Quote P&L and its USD view move together; net = gross - fees.
    gross = row.get("gross_pnl") if row.get("_has_gross") else trade.gross_pnl
    fees = row.get("fees") if row.get("_has_fees") else (trade.fees or 0.0)
    set_trade_pnl(session, trade, gross, fees)
    trade.r_multiple = compute_r_multiple(
        trade.direction,
        trade.entry_price,
        trade.initial_sl,
        trade.current_sl,
        trade.exit_price,
    )
    apply_trade_risk(session, trade)
    if not trade.session:
        trade.session = normalize_session(None, entry_time)
    # An import only claims an unassigned trade; moving a trade the trader
    # filed under another account is not the statement's call.
    if account_id is not None and trade.account_id is None:
        trade.account_id = account_id
    trade.updated_at = datetime.now(timezone.utc)


def import_rows(
    session: Session,
    rows: list[dict],
    *,
    account_id: Optional[int] = None,
    update_existing: bool = True,
) -> dict:
    """Store parsed statement rows, keyed by ticket.

    ``update_existing`` is the reconciliation switch: with it, a ticket
    already in the ledger is refreshed from the statement instead of being
    skipped. A row whose broker fields already match changes nothing.
    """
    result = {
        "added": [],
        "updated": [],
        "unchanged": [],
        "skipped": [],
        "details": [],
    }
    for row in rows:
        ticket = str(row.get("ticket") or "").strip()
        if not ticket:
            result["skipped"].append("")
            result["details"].append({"ticket": "", "action": "skipped", "reason": "no ticket"})
            continue
        existing = session.exec(select(Trade).where(Trade.ticket == ticket)).first()
        if existing is not None:
            if not update_existing:
                result["skipped"].append(ticket)
                result["details"].append(
                    {"ticket": ticket, "action": "skipped", "reason": "ticket already exists"}
                )
                continue
            changes = _changed_fields(existing, row)
            if not changes:
                result["unchanged"].append(ticket)
                result["details"].append({"ticket": ticket, "action": "unchanged"})
                continue
            _apply_row(session, existing, row, account_id)
            session.add(existing)
            result["updated"].append(ticket)
            result["details"].append(
                {"ticket": ticket, "action": "updated", "changes": changes}
            )
            continue

        trade = Trade(ticket=ticket, account_id=account_id, status="CLOSED")
        _apply_row(session, trade, row, account_id)
        session.add(trade)
        result["added"].append(ticket)
        result["details"].append({"ticket": ticket, "action": "added"})
    session.commit()
    result["counts"] = {
        "added": len(result["added"]),
        "updated": len(result["updated"]),
        "unchanged": len(result["unchanged"]),
        "skipped": len(result["skipped"]),
        "rows": len(rows),
    }
    return result
