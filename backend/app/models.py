"""SQLModel relational models (PLAN-v2 Task 1.2).

v2 schema: Trade.ticket replaces v1 Trade.trade_id, adds updated_at;
new DailyNote table for pre-market / EOD reviews and guardrail flags.
Fresh DB per v2 kickoff decision — no in-place migration.
"""

from datetime import date as date_type
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TradeTagLink(SQLModel, table=True):
    __tablename__ = "trade_tag_link"
    trade_id: Optional[int] = Field(default=None, foreign_key="trade.id", primary_key=True)
    tag_id: Optional[int] = Field(default=None, foreign_key="tag.id", primary_key=True)


class Tag(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    category: str = Field(default="setup")  # setup | mistake
    created_at: datetime = Field(default_factory=_utcnow)

    trades: list["Trade"] = Relationship(back_populates="tags", link_model=TradeTagLink)


class Trade(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ticket: str = Field(unique=True, index=True)  # MT5 deal ID / bot ID
    timestamp_open: Optional[datetime] = Field(default=None, index=True)
    timestamp_close: Optional[datetime] = None
    # Explicit lifecycle timestamps (backfill sets these directly; live flow
    # mirrors timestamp_open/timestamp_close).
    entry_time: Optional[datetime] = Field(default=None, index=True)
    exit_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    session: Optional[str] = Field(default=None, index=True)  # Asia | London | New York | Outside
    direction: Optional[str] = None  # buy | sell
    symbol: Optional[str] = Field(default=None, index=True)
    size: Optional[float] = None
    entry_price: Optional[float] = None
    initial_sl: Optional[float] = None
    current_sl: Optional[float] = None
    tp: Optional[float] = None
    exit_price: Optional[float] = None
    gross_pnl: Optional[float] = None
    fees: float = Field(default=0.0)
    net_pnl: Optional[float] = None
    r_multiple: Optional[float] = None
    status: str = Field(default="OPEN", index=True)  # OPEN | CLOSED
    thesis: Optional[str] = None
    review_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    tags: list[Tag] = Relationship(back_populates="trades", link_model=TradeTagLink)
    screenshots: list["Screenshot"] = Relationship(back_populates="trade")


class Screenshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    trade_id: int = Field(foreign_key="trade.id", index=True)
    immich_asset_id: str = Field(index=True)
    label: str = Field(default="setup")  # entry | exit | setup | mistake
    # Trade-aware Immich naming + dedupe (backfilled for legacy rows).
    original_filename: Optional[str] = None
    stored_filename: Optional[str] = None
    sha256: Optional[str] = Field(default=None, index=True)
    byte_size: Optional[int] = None
    created_at: datetime = Field(default_factory=_utcnow)

    trade: Optional[Trade] = Relationship(back_populates="screenshots")


class DailyNote(SQLModel, table=True):
    __tablename__ = "daily_note"
    id: Optional[int] = Field(default=None, primary_key=True)
    date: date_type = Field(unique=True, index=True)
    pre_market: Optional[str] = None
    eod_review: Optional[str] = None
    discipline_breach: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# --- Read schemas (responses embed tags + screenshot metadata) ---


class TagRead(SQLModel):
    id: int
    name: str
    category: str


class ScreenshotRead(SQLModel):
    id: int
    trade_id: int
    immich_asset_id: str
    label: str
    original_filename: Optional[str] = None
    stored_filename: Optional[str] = None
    sha256: Optional[str] = None
    byte_size: Optional[int] = None
    created_at: datetime


class TradeRead(SQLModel):
    id: int
    ticket: str
    # Deprecated v1 alias — equals ticket. Kept so the current
    # frontend (TradeDto.trade_id) keeps working until Phase 5.
    trade_id: str
    timestamp_open: Optional[datetime] = None
    timestamp_close: Optional[datetime] = None
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    session: Optional[str] = None
    direction: Optional[str] = None
    symbol: Optional[str] = None
    size: Optional[float] = None
    entry_price: Optional[float] = None
    initial_sl: Optional[float] = None
    current_sl: Optional[float] = None
    tp: Optional[float] = None
    exit_price: Optional[float] = None
    gross_pnl: Optional[float] = None
    fees: Optional[float] = None
    net_pnl: Optional[float] = None
    r_multiple: Optional[float] = None
    status: str
    thesis: Optional[str] = None
    review_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    tags: list[TagRead] = []
    screenshots: list[ScreenshotRead] = []


class TradePatch(SQLModel):
    timestamp_open: Optional[datetime] = None
    timestamp_close: Optional[datetime] = None
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    direction: Optional[str] = None
    symbol: Optional[str] = None
    size: Optional[float] = None
    entry_price: Optional[float] = None
    initial_sl: Optional[float] = None
    current_sl: Optional[float] = None
    tp: Optional[float] = None
    exit_price: Optional[float] = None
    gross_pnl: Optional[float] = None
    fees: Optional[float] = None
    net_pnl: Optional[float] = None
    r_multiple: Optional[float] = None
    status: Optional[str] = None
    thesis: Optional[str] = None
    review_notes: Optional[str] = None
    # Raw tag tokens, e.g. ["#fvg", "!early"] — bare names default to setup.
    tags: Optional[list[str]] = None


class TradeOpenRequest(SQLModel):
    symbol: str
    direction: str  # buy | sell
    size: float
    entry_price: float
    initial_sl: float
    tp: Optional[float] = None
    ticket: Optional[str] = None
    timestamp_open: Optional[datetime] = None
    entry_time: Optional[datetime] = None  # explicit entry (bot `time:` flag); defaults to now
    session: Optional[str] = None  # manual override; otherwise auto-resolved
    thesis: Optional[str] = None
    tags: Optional[list[str]] = None


class TradeCloseRequest(SQLModel):
    exit_price: float
    gross_pnl: Optional[float] = None
    fees: Optional[float] = None
    mistake_tags: Optional[list[str]] = None
    review_notes: Optional[str] = None
    timestamp_close: Optional[datetime] = None


class TradeTSLRequest(SQLModel):
    current_sl: float


class BackfillRecord(SQLModel):
    """Single historical trade (or one item of a batch POST)."""

    symbol: str
    direction: str  # buy | sell
    size: float
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    initial_sl: Optional[float] = None
    tp: Optional[float] = None
    gross_pnl: Optional[float] = None
    fees: Optional[float] = None
    net_pnl: Optional[float] = None
    r_multiple: Optional[float] = None
    ticket: Optional[str] = None
    session: Optional[str] = None  # manual override; otherwise auto-resolved
    thesis: Optional[str] = None
    review_notes: Optional[str] = None
    tags: Optional[list[str]] = None


class BackfillRequest(SQLModel):
    records: list[BackfillRecord]


class DailyNoteRead(SQLModel):
    id: int
    date: date_type
    pre_market: Optional[str] = None
    eod_review: Optional[str] = None
    discipline_breach: bool = False
    created_at: datetime
    updated_at: datetime


class DailyNoteUpsert(SQLModel):
    date: date_type
    pre_market: Optional[str] = None
    eod_review: Optional[str] = None
    discipline_breach: Optional[bool] = None
