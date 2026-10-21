"""Symbol contract registry API.

The registry is the single source of truth for how big a lot is. The trade
modals read it so the browser never re-derives a dollar amount the server
would compute differently.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.database import get_session
from app.models import (
    SymbolPreview,
    SymbolSpec,
    SymbolSpecCreate,
    SymbolSpecRead,
    SymbolSpecUpdate,
)
from app.services.symbol_registry import (
    SYMBOL_CATEGORIES,
    compute_r_multiple,
    effective_stop,
    find_spec,
    list_specs,
    normalize_symbol,
    price_gross,
    risk_amount,
)

router = APIRouter(prefix="/api/symbols", tags=["symbols"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _validate(payload: SymbolSpecCreate | SymbolSpecUpdate) -> None:
    """Reject a spec that cannot price anything."""
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "category" in data and data["category"] not in SYMBOL_CATEGORIES:
        raise HTTPException(
            status_code=422, detail=f"category must be one of {sorted(SYMBOL_CATEGORIES)}"
        )
    if "contract_size" in data and data["contract_size"] <= 0:
        raise HTTPException(status_code=422, detail="contract_size must be positive")
    if "pip_size" in data and data["pip_size"] <= 0:
        raise HTTPException(status_code=422, detail="pip_size must be positive")


@router.get("/preview", response_model=SymbolPreview)
def preview_symbol(
    symbol: str = Query(description="Symbol to price"),
    direction: str = Query(default="buy", description="buy or sell"),
    size: Optional[float] = Query(default=None),
    entry: Optional[float] = Query(default=None),
    exit: Optional[float] = Query(default=None, description="Exit (or take profit) price"),
    sl: Optional[float] = Query(default=None, description="Stop loss price"),
    current_sl: Optional[float] = Query(default=None, description="Trailed stop price"),
    session: Session = Depends(get_session),
):
    """The server's answer for one position: gross, R and risk.

    The browser asks instead of re-deriving, so the preview it shows is
    the same number the server will store when the trade closes.
    """
    key = normalize_symbol(symbol)
    spec = find_spec(session, key)
    if spec is None:
        return SymbolPreview(
            symbol=key,
            registered=False,
            display=key,
            category="",
            contract_size=None,
            pip_size=None,
            quote_currency="",
            gross_pnl=None,
            r_multiple=None,
            initial_risk=None,
            realized_risk=None,
            risk_unit=None,
            distance=None,
            pips=None,
            risk_distance=None,
            risk_pips=None,
        )

    gross = price_gross(spec, direction, size, entry, exit)
    r = compute_r_multiple(direction, entry, sl, current_sl, exit)
    initial_risk = risk_amount(spec, size, entry, sl)
    stop = effective_stop(direction, entry, sl, current_sl)
    realized_risk = risk_amount(spec, size, entry, stop)
    distance = abs(exit - entry) if exit is not None and entry is not None else None
    risk_distance = abs(entry - sl) if sl is not None and entry is not None else None
    return SymbolPreview(
        symbol=spec.symbol,
        registered=True,
        display=spec.display,
        category=spec.category,
        contract_size=spec.contract_size,
        pip_size=spec.pip_size,
        quote_currency=spec.quote_currency,
        gross_pnl=gross,
        r_multiple=round(r, 4) if r is not None else None,
        initial_risk=initial_risk,
        realized_risk=realized_risk,
        risk_unit="USD" if initial_risk is not None else None,
        distance=round(distance, 10) if distance is not None else None,
        pips=round(distance / spec.pip_size, 2)
        if distance is not None and spec.pip_size
        else None,
        risk_distance=round(risk_distance, 10) if risk_distance is not None else None,
        risk_pips=round(risk_distance / spec.pip_size, 2)
        if risk_distance is not None and spec.pip_size
        else None,
    )


@router.get("", response_model=list[SymbolSpecRead])
def list_symbol_specs(
    include_disabled: bool = Query(default=False),
    session: Session = Depends(get_session),
):
    """Every registered symbol, for the trade modals."""
    return list_specs(session, include_disabled)


@router.post("", response_model=SymbolSpecRead, status_code=201)
def create_symbol_spec(payload: SymbolSpecCreate, session: Session = Depends(get_session)):
    """Register a symbol that has no contract yet."""
    symbol = normalize_symbol(payload.symbol)
    if not symbol:
        raise HTTPException(status_code=422, detail="symbol is required")
    if session.exec(select(SymbolSpec).where(SymbolSpec.symbol == symbol)).first() is not None:
        raise HTTPException(status_code=409, detail=f"symbol already registered: {symbol}")
    _validate(payload)
    spec = SymbolSpec(
        symbol=symbol,
        display=(payload.display or symbol).strip(),
        contract_size=payload.contract_size,
        pip_size=payload.pip_size,
        quote_currency=(payload.quote_currency or "USD").strip().upper(),
        category=payload.category,
        enabled=payload.enabled,
    )
    session.add(spec)
    session.commit()
    session.refresh(spec)
    return spec


@router.patch("/{spec_id}", response_model=SymbolSpecRead)
def update_symbol_spec(
    spec_id: int, payload: SymbolSpecUpdate, session: Session = Depends(get_session)
):
    """Change a contract size, a pip, a category or the enabled flag."""
    spec = session.get(SymbolSpec, spec_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="Symbol spec not found")
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "symbol" in data:
        symbol = normalize_symbol(data["symbol"])
        if not symbol:
            raise HTTPException(status_code=422, detail="symbol is required")
        clash = session.exec(select(SymbolSpec).where(SymbolSpec.symbol == symbol)).first()
        if clash is not None and clash.id != spec.id:
            raise HTTPException(status_code=409, detail=f"symbol already registered: {symbol}")
        data["symbol"] = symbol
    if "quote_currency" in data:
        data["quote_currency"] = str(data["quote_currency"]).strip().upper()
    _validate(payload)
    for key, value in data.items():
        setattr(spec, key, value)
    spec.updated_at = _now()
    session.add(spec)
    session.commit()
    session.refresh(spec)
    return spec
