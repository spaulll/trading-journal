"""The ledger's filter surface — one definition for the list, ids, export and summary.

The ledger used to download every trade and filter it in the browser. The
filters live here now, in SQL, so the browser asks the server for the rows
it is going to show.

Every entry point that answers "which trades?" builds its statement from the
same :class:`TradeFilters` and the same helpers, so a filter can never mean
one thing in the table and another in the export or the summary:

- :func:`apply_trade_filters` adds the clauses (and the tag join) to a
  ``select(Trade)``;
- :func:`filtered_count` counts the rows that survive the filter, without
  loading them;
- :func:`sort_trades` applies the ledger's sort keys.

The day bounds come in two flavours because the journal asks a different
question from the table: ``date_from``/``date_to`` bound the *open*
timestamp, ``closed_from``/``closed_to`` the *close* timestamp.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Optional

from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.models import Tag, Trade, TradeTagLink

# The sort keys the ledger offers. Anything else falls back to "newest".
SORT_KEYS = ("newest", "oldest", "net-desc", "net-asc", "r-desc")


@dataclass(frozen=True)
class TradeFilters:
    """The ledger's filter state, already normalised by the caller."""

    status: Optional[str] = None
    symbol: Optional[str] = None
    # Free text: a substring of the symbol or the ticket.
    query: Optional[str] = None
    tag: Optional[str] = None
    # A drill-down wants the tag itself; the free-text tag box keeps its
    # substring search.
    tag_exact: bool = False
    # Open-day bounds.
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    # Close-day bounds.
    closed_from: Optional[datetime] = None
    closed_to: Optional[datetime] = None
    account_id: Optional[int] = None
    unassigned: bool = False

    def without_status(self) -> "TradeFilters":
        """The same filter with the status dropped — the base for tab counts."""
        return replace(self, status=None)

    def with_status(self, status: Optional[str]) -> "TradeFilters":
        return replace(self, status=status)


def _tag_term(tag: Optional[str]) -> str:
    """The tag a filter asks for: no ``#``/``!`` prefix, lower case."""
    return (tag or "").strip().lstrip("#!").lower()


def apply_trade_filters(statement, filters: TradeFilters):  # noqa: ANN001 — SQLAlchemy statement
    """Add the filter clauses — and the tag join — to a Trade select."""
    wanted_tag = _tag_term(filters.tag)
    if wanted_tag:
        # The join comes first: a where clause on Tag must not turn into a
        # cross join against every tag in the table.
        statement = statement.join(
            TradeTagLink, TradeTagLink.trade_id == Trade.id
        ).join(Tag, Tag.id == TradeTagLink.tag_id)
    if filters.status:
        statement = statement.where(Trade.status == filters.status.upper())
    if filters.symbol:
        statement = statement.where(Trade.symbol == filters.symbol.upper())
    if filters.query:
        text = filters.query.strip()
        if text:
            statement = statement.where(
                or_(Trade.symbol.ilike(f"%{text}%"), Trade.ticket.ilike(f"%{text}%"))
            )
    if wanted_tag:
        if filters.tag_exact:
            # A drill-down means the trades that carry this tag, not every
            # tag that merely contains its name: `#ema` must not pull in
            # `#ema_reclaim` and make the row count disagree with the tag page.
            statement = statement.where(func.lower(Tag.name) == wanted_tag)
        else:
            # The ledger's tag box is a search box: a partial name finds the
            # tags that contain it.
            statement = statement.where(Tag.name.ilike(f"%{wanted_tag}%"))
    if filters.date_from:
        statement = statement.where(Trade.timestamp_open >= filters.date_from)
    if filters.date_to:
        statement = statement.where(Trade.timestamp_open <= filters.date_to)
    if filters.closed_from:
        statement = statement.where(Trade.timestamp_close >= filters.closed_from)
    if filters.closed_to:
        statement = statement.where(Trade.timestamp_close <= filters.closed_to)
    if filters.account_id is not None:
        statement = statement.where(Trade.account_id == filters.account_id)
    elif filters.unassigned:
        statement = statement.where(Trade.account_id.is_(None))
    return statement


def filtered_count(session: Session, filters: TradeFilters) -> int:
    """How many trades survive the filter — without loading them."""
    statement = apply_trade_filters(select(Trade.id), filters).subquery()
    return int(session.exec(select(func.count()).select_from(statement)).one())


def filtered_ids(session: Session, filters: TradeFilters) -> list[int]:
    """The ids of every trade that survives the filter, in ledger order."""
    statement = apply_trade_filters(select(Trade.id), filters)
    return [int(row) for row in session.exec(statement).all()]


def sort_trades(statement, sort: Optional[str]):  # noqa: ANN001 — SQLAlchemy statement
    """Order the ledger rows.

    A missing number sorts last in every order — an unpriced trade has no
    net to compare, and it must not outrank a priced one.
    """
    key = (sort or "newest").strip().lower()
    if key == "oldest":
        return statement.order_by(
            func.coalesce(Trade.timestamp_open, Trade.created_at).asc(), Trade.id.asc()
        )
    if key == "net-desc":
        return statement.order_by(
            Trade.net_pnl_usd.is_(None), Trade.net_pnl_usd.desc(), Trade.id.desc()
        )
    if key == "net-asc":
        return statement.order_by(
            Trade.net_pnl_usd.is_(None), Trade.net_pnl_usd.asc(), Trade.id.desc()
        )
    if key == "r-desc":
        return statement.order_by(
            Trade.r_multiple.is_(None), Trade.r_multiple.desc(), Trade.id.desc()
        )
    return statement.order_by(
        func.coalesce(Trade.timestamp_open, Trade.created_at).desc(), Trade.id.desc()
    )
