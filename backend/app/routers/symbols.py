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
from app.models import SymbolSpec, SymbolSpecCreate, SymbolSpecRead, SymbolSpecUpdate
from app.services.symbol_registry import (
    SYMBOL_CATEGORIES,
    list_specs,
    normalize_symbol,
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
