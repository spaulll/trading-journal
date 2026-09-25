"""SQLModel relational models (PLAN Task 1.2)."""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class TradeTagLink(SQLModel, table=True):
    __tablename__ = "trade_tag_link"
    trade_id: Optional[int] = Field(default=None, foreign_key="trade.id", primary_key=True)
    tag_id: Optional[int] = Field(default=None, foreign_key="tag.id", primary_key=True)


class Tag(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    category: str = Field(default="setup")  # setup | mistake
    created_at: datetime = Field(default_factory=datetime.utcnow)

    trades: list["Trade"] = Relationship(back_populates="tags", link_model=TradeTagLink)


class Trade(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    trade_id: str = Field(unique=True, index=True)  # MT5 ticket or bot ID
    timestamp_open: Optional[datetime] = Field(default=None, index=True)
    timestamp_close: Optional[datetime] = None
    direction: Optional[str] = None  # buy | sell
    symbol: Optional[str] = Field(default=None, index=True)
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
    status: str = Field(default="OPEN", index=True)  # OPEN | CLOSED
    thesis: Optional[str] = None
    review_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    tags: list[Tag] = Relationship(back_populates="trades", link_model=TradeTagLink)
    screenshots: list["Screenshot"] = Relationship(back_populates="trade")


class Screenshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    trade_id: int = Field(foreign_key="trade.id", index=True)
    immich_asset_id: str = Field(index=True)
    label: str = Field(default="setup")  # entry | exit | setup | mistake
    created_at: datetime = Field(default_factory=datetime.utcnow)

    trade: Optional[Trade] = Relationship(back_populates="screenshots")


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
    created_at: datetime


class TradeRead(SQLModel):
    id: int
    trade_id: str
    timestamp_open: Optional[datetime] = None
    timestamp_close: Optional[datetime] = None
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
    tags: list[TagRead] = []
    screenshots: list[ScreenshotRead] = []


class TradePatch(SQLModel):
    timestamp_close: Optional[datetime] = None
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
