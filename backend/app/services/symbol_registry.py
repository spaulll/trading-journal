"""Symbol contract registry — the one place that knows how big a lot is.

A price distance is not money. Ten points on EURUSD and ten points on NAS100
are wildly different dollars, and the only way to know which is which is the
contract size: the number of quote-currency units one lot controls.

    dollars = price_distance x contract_size x size

``contract_size`` therefore means "units per 1.0 lot" and is 100000 for FX
majors, 100 for gold ounces, 5000 for silver ounces, 1 for crypto coins and
1 for index contracts.

Quote currency
--------------
``quote_currency`` names the currency the price is quoted in. USD instruments
need no conversion. A JPY-quoted instrument (USDJPY) is converted at the
exit rate, so the P&L is stated in dollars rather than yen. Phase 4 replaces
this with the daily FX rate table.

Fallback
--------
A symbol that is not in the registry has no contract, so it cannot be
priced. The pricing helpers return ``None`` for it — never a guess. The
ledger flags such a trade as unpriced instead of scoring it as a scratch.
"""

from __future__ import annotations

from typing import Optional

from sqlmodel import Session, select

from app.models import SymbolSpec

# Canonical categories. A spec outside this set is rejected by the API.
SYMBOL_CATEGORIES = ("fx", "metal", "crypto", "index", "future")

# The seeded registry. Contract sizes follow the broker convention the
# frontend already used for its risk preview; pip_size is the price
# increment the instrument quotes in.
DEFAULT_SPECS: tuple[dict, ...] = (
    # --- FX majors: 100k units per lot -------------------------------
    {"symbol": "EURUSD", "display": "EUR/USD", "contract_size": 100000.0,
     "pip_size": 0.0001, "quote_currency": "USD", "category": "fx"},
    {"symbol": "GBPUSD", "display": "GBP/USD", "contract_size": 100000.0,
     "pip_size": 0.0001, "quote_currency": "USD", "category": "fx"},
    {"symbol": "AUDUSD", "display": "AUD/USD", "contract_size": 100000.0,
     "pip_size": 0.0001, "quote_currency": "USD", "category": "fx"},
    {"symbol": "NZDUSD", "display": "NZD/USD", "contract_size": 100000.0,
     "pip_size": 0.0001, "quote_currency": "USD", "category": "fx"},
    {"symbol": "USDCHF", "display": "USD/CHF", "contract_size": 100000.0,
     "pip_size": 0.0001, "quote_currency": "USD", "category": "fx"},
    {"symbol": "USDCAD", "display": "USD/CAD", "contract_size": 100000.0,
     "pip_size": 0.0001, "quote_currency": "USD", "category": "fx"},
    {"symbol": "USDJPY", "display": "USD/JPY", "contract_size": 100000.0,
     "pip_size": 0.01, "quote_currency": "JPY", "category": "fx"},
    # --- Metals -------------------------------------------------------
    {"symbol": "GOLD", "display": "Gold (XAU/USD)", "contract_size": 100.0,
     "pip_size": 0.01, "quote_currency": "USD", "category": "metal"},
    {"symbol": "XAUUSD", "display": "Gold (XAU/USD)", "contract_size": 100.0,
     "pip_size": 0.01, "quote_currency": "USD", "category": "metal"},
    {"symbol": "XAGUSD", "display": "Silver (XAG/USD)", "contract_size": 5000.0,
     "pip_size": 0.001, "quote_currency": "USD", "category": "metal"},
    {"symbol": "PAXG", "display": "PAX Gold (PAXG/USD)", "contract_size": 100.0,
     "pip_size": 0.01, "quote_currency": "USD", "category": "metal"},
    # --- Crypto: one coin per lot -------------------------------------
    {"symbol": "BTCUSD", "display": "Bitcoin (BTC/USD)", "contract_size": 1.0,
     "pip_size": 1.0, "quote_currency": "USD", "category": "crypto"},
    {"symbol": "BTC", "display": "Bitcoin (BTC/USD)", "contract_size": 1.0,
     "pip_size": 1.0, "quote_currency": "USD", "category": "crypto"},
    {"symbol": "XBTUSD", "display": "Bitcoin (BTC/USD)", "contract_size": 1.0,
     "pip_size": 1.0, "quote_currency": "USD", "category": "crypto"},
    {"symbol": "ETHUSD", "display": "Ethereum (ETH/USD)", "contract_size": 1.0,
     "pip_size": 0.1, "quote_currency": "USD", "category": "crypto"},
    {"symbol": "SOLUSD", "display": "Solana (SOL/USD)", "contract_size": 1.0,
     "pip_size": 0.01, "quote_currency": "USD", "category": "crypto"},
    # --- Index CFDs: one contract per lot, one point per dollar -------
    {"symbol": "NAS100", "display": "Nasdaq 100", "contract_size": 1.0,
     "pip_size": 1.0, "quote_currency": "USD", "category": "index"},
    {"symbol": "US30", "display": "Dow Jones 30", "contract_size": 1.0,
     "pip_size": 1.0, "quote_currency": "USD", "category": "index"},
    {"symbol": "SPX500", "display": "S&P 500", "contract_size": 1.0,
     "pip_size": 1.0, "quote_currency": "USD", "category": "index"},
    {"symbol": "DE40", "display": "DAX 40", "contract_size": 1.0,
     "pip_size": 1.0, "quote_currency": "USD", "category": "index"},
)


def normalize_symbol(raw: object) -> str:
    """Canonical lookup key for a symbol.

    Uppercase, trimmed, and stripped of the trailing dot some bots append
    (``EURUSD.`` is the same instrument as ``EURUSD``).
    """
    return str(raw or "").strip().upper().rstrip(".")


def find_spec(session: Session, symbol: object) -> Optional[SymbolSpec]:
    """The enabled spec for a symbol, or None when it is not registered."""
    key = normalize_symbol(symbol)
    if not key:
        return None
    spec = session.exec(select(SymbolSpec).where(SymbolSpec.symbol == key)).first()
    if spec is None or not spec.enabled:
        return None
    return spec


def list_specs(session: Session, include_disabled: bool = False) -> list[SymbolSpec]:
    """Every spec, ordered by category then symbol."""
    statement = select(SymbolSpec)
    if not include_disabled:
        statement = statement.where(SymbolSpec.enabled == True)  # noqa: E712
    statement = statement.order_by(SymbolSpec.category.asc(), SymbolSpec.symbol.asc())
    return list(session.exec(statement).all())


def seed_specs(session: Session, specs: tuple[dict, ...] = DEFAULT_SPECS) -> int:
    """Insert the default specs that are missing. Never overwrites a row.

    A user-edited contract size survives a restart; only symbols that were
    never registered are added. Returns the number of rows inserted.
    """
    existing = {row.symbol for row in session.exec(select(SymbolSpec)).all()}
    added = 0
    for spec in specs:
        symbol = normalize_symbol(spec["symbol"])
        if not symbol or symbol in existing:
            continue
        session.add(SymbolSpec(**{**spec, "symbol": symbol}))
        existing.add(symbol)
        added += 1
    if added:
        session.flush()
    return added


# --- the money math --------------------------------------------------------


def direction_sign(direction: object) -> int:
    """+1 for a long, -1 for a short, 0 when the direction is unusable.

    One predicate for every price calculation, so the gross P&L and the
    R-multiple can never disagree about which way the trade went.
    """
    text = str(direction or "").strip().lower()
    if text.startswith("buy") or text.startswith("long"):
        return 1
    if text.startswith("sell") or text.startswith("short"):
        return -1
    return 0


def to_usd(amount: float, quote_currency: str, rate: Optional[float]) -> Optional[float]:
    """Convert an amount quoted in `quote_currency` into dollars.

    `rate` is the price that quotes one USD in the quote currency — the
    USDJPY rate for a JPY-quoted pair. It is only consulted when the quote
    currency is not USD. Phase 4 replaces this with the daily FX table.
    """
    if str(quote_currency or "USD").upper() == "USD":
        return amount
    if rate is None or rate == 0:
        return None
    return amount / rate


def price_gross(
    spec: Optional[SymbolSpec],
    direction: object,
    size: Optional[float],
    entry: Optional[float],
    exit_price: Optional[float],
) -> Optional[float]:
    """Dollar gross P&L for one position.

    The price distance is turned into money with the contract size, then
    converted into the quote currency's dollars. Returns None whenever the
    trade cannot be priced — an unregistered symbol, a missing leg, a
    non-positive size — so an unpriced trade stays unpriced instead of
    being guessed at.
    """
    if spec is None or size is None or entry is None or exit_price is None:
        return None
    if size <= 0:
        return None
    sign = direction_sign(direction)
    if sign == 0:
        return None
    distance = (exit_price - entry) * sign
    quote_amount = distance * size * spec.contract_size
    usd = to_usd(quote_amount, spec.quote_currency, exit_price)
    return round(usd, 2) if usd is not None else None


def risk_amount(
    spec: Optional[SymbolSpec],
    size: Optional[float],
    entry: Optional[float],
    stop: Optional[float],
) -> Optional[float]:
    """Dollar risk of a stop distance, in the quote currency's dollars.

    For a USD-quoted instrument this is the plain contract arithmetic. A
    JPY-quoted pair is converted at the entry rate, because that is the
    rate the risk was committed at.
    """
    if spec is None or size is None or entry is None or stop is None:
        return None
    if size <= 0:
        return None
    distance = abs(entry - stop)
    if distance == 0:
        return None
    quote_amount = distance * size * spec.contract_size
    usd = to_usd(quote_amount, spec.quote_currency, entry)
    return round(usd, 2) if usd is not None else None


def estimate_gross_pnl(
    session: Session,
    direction: object,
    symbol: object,
    size: Optional[float],
    entry: Optional[float],
    exit_price: Optional[float],
) -> Optional[float]:
    """Dollar gross P&L for a symbol, priced from the registry.

    None when the symbol is not registered — an unknown instrument has no
    contract, so it has no price. Callers must keep None rather than
    guess.
    """
    spec = find_spec(session, symbol)
    if spec is None:
        return None
    return price_gross(spec, direction, size, entry, exit_price)

