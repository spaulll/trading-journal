"""SQLModel relational models (PLAN-v2 Task 1.2).

v2 schema: Trade.ticket replaces v1 Trade.trade_id, adds updated_at;
new DailyNote table for pre-market / EOD reviews and guardrail flags.
Fresh DB per v2 kickoff decision — no in-place migration.
"""

from datetime import date as date_type
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TradeTagLink(SQLModel, table=True):
    __tablename__ = "trade_tag_link"
    trade_id: Optional[int] = Field(default=None, foreign_key="trade.id", primary_key=True)
    tag_id: Optional[int] = Field(default=None, foreign_key="tag.id", primary_key=True)


class FxRate(SQLModel, table=True):
    """One daily FX quote: 1 ``base`` buys ``rate`` units of ``quote``.

    Rates are stored per day and looked up with a backwards fallback, so a
    weekend or a forgotten entry does not make a trade unpriceable — a
    missing day uses the most recent earlier rate and the conversion
    reports how stale that rate was.
    """

    __tablename__ = "fx_rate"
    __table_args__ = (
        UniqueConstraint("date", "base", "quote", name="uq_fx_rate_triple"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    date: date_type = Field(index=True)
    base: str = Field(index=True)
    quote: str = Field(index=True)
    rate: float  # quote units per 1.0 base
    source: str = Field(default="manual")  # manual | provider name
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Tag(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    category: str = Field(default="setup")  # setup | mistake
    created_at: datetime = Field(default_factory=_utcnow)

    trades: list["Trade"] = Relationship(back_populates="tags", link_model=TradeTagLink)


class Trade(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ticket: str = Field(unique=True, index=True)  # MT5 deal ID / bot ID
    account_id: Optional[int] = Field(default=None, foreign_key="account.id", index=True)
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
    # The P&L above is stated in the trade's quote currency (JPY for
    # USDJPY). These two are the same amounts converted to USD at the
    # close-day FX rate — the single number analytics and guardrails use.
    quote_currency: Optional[str] = Field(default=None, index=True)
    gross_pnl_usd: Optional[float] = None
    net_pnl_usd: Optional[float] = None
    r_multiple: Optional[float] = None
    # Dollar risk, from the symbol registry's contract size.
    # initial_risk  — the risk the plan committed to (the initial stop).
    # realized_risk — the risk actually carried (the current stop).
    initial_risk: Optional[float] = None
    realized_risk: Optional[float] = None
    risk_unit: Optional[str] = None  # USD for now; Phase 4 adds currencies
    status: str = Field(default="OPEN", index=True)  # OPEN | CLOSED
    thesis: Optional[str] = None
    review_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    tags: list[Tag] = Relationship(back_populates="trades", link_model=TradeTagLink)
    screenshots: list["Screenshot"] = Relationship(back_populates="trade")
    account: Optional["Account"] = Relationship(back_populates="trades")


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


class SymbolSpec(SQLModel, table=True):
    """Contract specification for one tradable symbol.

    The registry is the single source of truth for how big a lot is. A
    price distance alone says nothing about money: 10 points on EURUSD and
    10 points on NAS100 are wildly different dollars. `contract_size`
    bridges the gap — it is the number of quote-currency units one lot
    controls, so `price_distance x contract_size x size` is the money.

    `quote_currency` names the currency the price is quoted in. A USD
    instrument needs no conversion; a JPY-quoted one is converted at the
    exit rate (Phase 4 replaces this with the daily FX table).
    """

    __tablename__ = "symbol_spec"
    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True, unique=True)  # uppercase canonical name
    display: str = Field(default="")  # label for the UI
    contract_size: float = Field(default=1.0)  # quote-currency units per 1.0 lot
    pip_size: float = Field(default=0.01)  # price increment (one pip)
    quote_currency: str = Field(default="USD", index=True)
    category: str = Field(default="fx", index=True)  # fx | metal | crypto | index | future
    enabled: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class DailyNote(SQLModel, table=True):
    __tablename__ = "daily_note"
    id: Optional[int] = Field(default=None, primary_key=True)
    date: date_type = Field(unique=True, index=True)
    pre_market: Optional[str] = None
    eod_review: Optional[str] = None
    discipline_breach: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Account(SQLModel, table=True):
    __tablename__ = "account"
    id: Optional[int] = Field(default=None, primary_key=True)
    firm: str = Field(default="", index=True)  # e.g. FTMO, FundedNext
    alias: str = Field(unique=True, index=True)  # lowercase handle, e.g. ftmo100k-f1
    login: Optional[str] = Field(default=None, index=True)  # MT5 login, optional
    phase: str = Field(default="personal", index=True)  # challenge1 | phase2 | funded | personal
    start_balance: float = Field(default=0.0)
    # Currency the start balance and the prop limits are declared in.
    base_currency: str = Field(default="USD", index=True)
    # Limits are PERCENT (0-100) off the balance anchor — $ values are
    # derived at read time so every size (1k/5k/10k/100k) just works.
    # Legacy absolute-$ columns (daily_loss_limit, max_loss_limit,
    # profit_target) are ignored by new code, kept for old rows.
    daily_loss_limit: float = Field(default=0.0)
    daily_loss_pct: float = Field(default=0.0)
    daily_basis: str = Field(default="balance")  # balance (closed) | equity (incl. floating)
    max_loss_limit: float = Field(default=0.0)
    max_loss_pct: float = Field(default=0.0)
    max_mode: str = Field(default="static")  # static | trailing
    trailing_ref: str = Field(default="balance_peak")  # balance_peak | equity_peak
    profit_target: Optional[float] = Field(default=None)
    profit_target_pct: Optional[float] = Field(default=None)
    # Challenge lifecycle: the days the firm requires and the rule that no
    # single day may carry too much of the profit. The deadline is what lets
    # the journal warn before the days requirement becomes unreachable.
    min_trading_days: int = Field(default=0)
    consistency_pct: Optional[float] = Field(default=None)
    deadline: Optional[date_type] = Field(default=None, index=True)
    status: str = Field(default="active", index=True)  # active | breach | passed | archived
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    trades: list["Trade"] = Relationship(back_populates="account")


class AccountRule(SQLModel, table=True):
    """Per-account challenge rule snapshot.

    ``target`` and ``current`` use the rule's own unit (percent or trading
    days). ``met_at`` is the first time the rule resolved — the profit
    target was reached, the loss limit was breached, the days requirement
    was met. It is a milestone, not a live status, so a later trade cannot
    erase the moment the rule was satisfied.
    """

    __tablename__ = "account_rule"
    __table_args__ = (
        UniqueConstraint("account_id", "kind", name="uq_account_rule_kind"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    kind: str = Field(index=True)  # profit_target | max_loss | daily_loss | min_days | consistency
    target: float = Field(default=0.0)
    current: Optional[float] = Field(default=None)
    met_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class AccountEvent(SQLModel, table=True):
    """One thing that happened to a prop account.

    ``payload`` is JSON text so a rule event can carry the target and the
    reading that resolved it without a wide table. Events are append-only:
    the timeline is the account's history, not a mutable status.
    """

    __tablename__ = "account_event"
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    kind: str = Field(index=True)  # rule_met | rule_breached | status_changed
    payload: str = Field(default="{}")
    occurred_at: datetime = Field(default_factory=_utcnow, index=True)


# The cash ledger records money that actually moved. The amount is always
# positive; the kind owns the direction so no caller can double-negate a fee.
CASH_INFLOW_KINDS = frozenset({"refund", "payout"})
CASH_OUTFLOW_KINDS = frozenset(
    {"evaluation", "reset", "activation", "platform_fee"}
)
CASH_KINDS = CASH_INFLOW_KINDS | CASH_OUTFLOW_KINDS


def cash_direction(kind: str) -> int:
    """+1 for money in, -1 for money out. Unknown kinds are rejected."""
    if kind in CASH_INFLOW_KINDS:
        return 1
    if kind in CASH_OUTFLOW_KINDS:
        return -1
    raise ValueError(f"unknown cash kind: {kind}")


class CashEntry(SQLModel, table=True):
    """One dated prop-cash movement in its own currency.

    ``amount_usd`` is deliberately not stored: it is derived on every read
    from the rate for ``occurred_on``, so correcting a rate reprices
    history. A row with no usable rate is reported as unpriced instead of
    being counted as zero.
    """

    __tablename__ = "cash_entry"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_cash_entry_amount_positive"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    firm: str = Field(index=True)
    kind: str = Field(index=True)  # evaluation | reset | activation | platform_fee | refund | payout
    amount: float
    currency: str = Field(default="USD", index=True)
    occurred_on: date_type = Field(index=True)
    note: Optional[str] = None
    # Informational only: the ledger stays firm-level, not account-level.
    account_id: Optional[int] = Field(
        default=None, foreign_key="account.id", index=True
    )
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class AppSetting(SQLModel, table=True):
    """Process-wide key-value settings (e.g. broker clock offset)."""

    __tablename__ = "app_setting"
    key: str = Field(primary_key=True)
    value: str = Field(default="")
    updated_at: datetime = Field(default_factory=_utcnow)


class ImportRun(SQLModel, table=True):
    """One broker-statement import attempt, success or failure.

    A bad file has to be diagnosable after the fact, so every attempt is
    kept: the file name, the detected format, what happened to each
    ticket, and the error when the statement could not be read. ``detail``
    is capped JSON text — warnings plus per-ticket actions — so the table
    needs no JSON column and a huge statement cannot bloat the row.
    """

    __tablename__ = "import_run"
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str = Field(default="mt5", index=True)
    filename: str = Field(default="")
    format: Optional[str] = None  # html | csv | None when unreadable
    account_id: Optional[int] = Field(default=None, index=True)
    rows: int = Field(default=0)
    added: int = Field(default=0)
    updated: int = Field(default=0)
    unchanged: int = Field(default=0)
    skipped: int = Field(default=0)
    error: Optional[str] = None
    detail: str = Field(default="")
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class InsightReport(SQLModel, table=True):
    """Stored LLM weekend-review summaries (one row per generated week)."""

    __tablename__ = "insight_report"
    id: Optional[int] = Field(default=None, primary_key=True)
    date_from: date_type = Field(index=True)
    date_to: date_type = Field(index=True)
    markdown: str = Field(default="")
    model: str = Field(default="")
    created_at: datetime = Field(default_factory=_utcnow)


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
    account_id: Optional[int] = None
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
    quote_currency: Optional[str] = None
    gross_pnl_usd: Optional[float] = None
    net_pnl_usd: Optional[float] = None
    # True when the quote-currency P&L exists but no FX rate could convert
    # it to USD. Analytical totals treat such a trade as unpriced.
    fx_missing: bool = False
    r_multiple: Optional[float] = None
    initial_risk: Optional[float] = None
    realized_risk: Optional[float] = None
    risk_unit: Optional[str] = None
    status: str
    thesis: Optional[str] = None
    review_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    tags: list[TagRead] = []
    screenshots: list[ScreenshotRead] = []


class TradePatch(SQLModel):
    account_id: Optional[int] = None
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
    quote_currency: Optional[str] = None
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
    account_id: Optional[int] = None
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
    account_id: Optional[int] = None
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


class RepairRequest(SQLModel):
    """Dry-run unless ``apply`` is true."""

    apply: bool = False


class SymbolSpecRead(SQLModel):
    id: int
    symbol: str
    display: str
    contract_size: float
    pip_size: float
    quote_currency: str
    category: str
    enabled: bool


class SymbolSpecCreate(SQLModel):
    symbol: str
    display: str = ""
    contract_size: float = 1.0
    pip_size: float = 0.01
    quote_currency: str = "USD"
    category: str = "fx"
    enabled: bool = True


class SymbolSpecUpdate(SQLModel):
    symbol: Optional[str] = None
    display: Optional[str] = None
    contract_size: Optional[float] = None
    pip_size: Optional[float] = None
    quote_currency: Optional[str] = None
    category: Optional[str] = None
    enabled: Optional[bool] = None


class SymbolPreview(SQLModel):
    """The server's answer for one position: gross, R and risk."""

    symbol: str
    registered: bool
    display: str
    category: str
    contract_size: Optional[float] = None
    pip_size: Optional[float] = None
    quote_currency: str = ""
    gross_pnl: Optional[float] = None
    gross_pnl_usd: Optional[float] = None
    r_multiple: Optional[float] = None
    initial_risk: Optional[float] = None
    realized_risk: Optional[float] = None
    risk_unit: Optional[str] = None
    distance: Optional[float] = None
    pips: Optional[float] = None
    risk_distance: Optional[float] = None
    risk_pips: Optional[float] = None


class FxRateRead(SQLModel):
    id: int
    date: date_type
    base: str
    quote: str
    rate: float
    source: str
    created_at: datetime
    updated_at: datetime


class FxRateCreate(SQLModel):
    date: Optional[date_type] = None
    base: str
    quote: str
    rate: float
    source: Optional[str] = None


class FxEffectiveRate(SQLModel):
    """The rate a conversion would actually use, with its provenance."""

    base: str
    quote: str
    requested_date: date_type
    rate: Optional[float] = None
    as_of: Optional[date_type] = None
    source: str = "missing"  # identity | direct | inverse | cross | missing
    via: Optional[str] = None
    fallback: bool = False
    fallback_days: int = 0
    missing: bool = True


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


class InsightReportRead(SQLModel):
    id: int
    date_from: date_type
    date_to: date_type
    markdown: str
    model: str
    created_at: datetime


class WeekendReviewRequest(SQLModel):
    date_from: Optional[date_type] = None
    date_to: Optional[date_type] = None


class AccountRead(SQLModel):
    id: int
    firm: str
    alias: str
    login: Optional[str] = None
    phase: str
    start_balance: float
    base_currency: str = "USD"
    daily_loss_pct: float
    daily_basis: str
    max_loss_pct: float
    max_mode: str
    trailing_ref: str
    profit_target_pct: Optional[float] = None
    min_trading_days: int = 0
    consistency_pct: Optional[float] = None
    deadline: Optional[date_type] = None
    status: str
    created_at: datetime
    updated_at: datetime
    open_trades: int = 0
    total_trades: int = 0
    days_traded: int = 0


class AccountRuleRead(SQLModel):
    id: int
    account_id: int
    kind: str
    label: str
    unit: str
    target: float
    current: Optional[float] = None
    status: str  # pending | met | breached | missed
    met_at: Optional[datetime] = None
    warning: Optional[str] = None
    days_left: Optional[int] = None


class AccountEventRead(SQLModel):
    id: Optional[int] = None
    account_id: int
    kind: str
    label: str
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


class CashEntryRead(SQLModel):
    id: int
    firm: str
    kind: str
    amount: float
    currency: str
    occurred_on: date_type
    note: Optional[str] = None
    account_id: Optional[int] = None
    # Converted on occurred_on into FX_BASE_CURRENCY. None means no usable
    # rate, which is why the row is flagged rather than treated as zero.
    amount_usd: Optional[float] = None
    fx_missing: bool = False
    created_at: datetime
    updated_at: datetime


class CashEntryCreate(SQLModel):
    firm: str
    kind: str
    amount: float
    currency: str = "USD"
    occurred_on: date_type
    note: Optional[str] = None
    account_id: Optional[int] = None


class CashEntryUpdate(SQLModel):
    firm: Optional[str] = None
    kind: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    occurred_on: Optional[date_type] = None
    note: Optional[str] = None
    account_id: Optional[int] = None


class CashFirmSummary(SQLModel):
    firm: str
    spent: float
    received: float
    net: float
    roi: Optional[float] = None
    entries: int = 0
    unpriced: int = 0


class CashSummary(SQLModel):
    currency: str
    spent: float
    received: float
    net: float
    roi: Optional[float] = None
    by_firm: list[CashFirmSummary] = Field(default_factory=list)
    unpriced: int = 0


class AccountCreate(SQLModel):
    firm: str = ""
    alias: str
    login: Optional[str] = None
    phase: str = "personal"
    start_balance: float = 0.0
    base_currency: str = "USD"
    daily_loss_pct: float = 0.0
    daily_basis: str = "balance"
    max_loss_pct: float = 0.0
    max_mode: str = "static"
    trailing_ref: str = "balance_peak"
    profit_target_pct: Optional[float] = None
    min_trading_days: int = 0
    consistency_pct: Optional[float] = None
    deadline: Optional[date_type] = None
    status: str = "active"


class AccountUpdate(SQLModel):
    firm: Optional[str] = None
    alias: Optional[str] = None
    login: Optional[str] = None
    phase: Optional[str] = None
    start_balance: Optional[float] = None
    base_currency: Optional[str] = None
    daily_loss_pct: Optional[float] = None
    daily_basis: Optional[str] = None
    max_loss_pct: Optional[float] = None
    max_mode: Optional[str] = None
    trailing_ref: Optional[str] = None
    profit_target_pct: Optional[float] = None
    min_trading_days: Optional[int] = None
    consistency_pct: Optional[float] = None
    deadline: Optional[date_type] = None
    status: Optional[str] = None
