"""Prop-cash ledger CRUD.

The cash ledger answers a different question from the trade ledger: not
"did the trades make money" but "did the challenge purchase pay for
itself". Every row is a positive amount plus a kind; the kind owns the
direction, and the USD view is derived on read so a corrected rate
reprices history.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, select

from app.database import get_session
from app.models import (
    CASH_KINDS,
    Account,
    CashEntry,
    CashEntryCreate,
    CashEntryRead,
    CashEntryUpdate,
    CashFirmSummary,
    CashSummary,
    cash_direction,
)
from app.services.fx import convert_amount, normalize_currency, reporting_currency

router = APIRouter(prefix="/api/cash", tags=["cash"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_firm(raw: object) -> str:
    firm = str(raw or "").strip()
    if not firm:
        raise HTTPException(status_code=422, detail="firm must not be empty")
    return firm


def _clean_kind(raw: object) -> str:
    kind = str(raw or "").strip().lower()
    if kind not in CASH_KINDS:
        raise HTTPException(
            status_code=422,
            detail=f"kind must be one of {sorted(CASH_KINDS)}",
        )
    return kind


def _clean_amount(raw: object) -> float:
    try:
        amount = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="amount must be a positive number")
    if not math.isfinite(amount) or amount <= 0:
        raise HTTPException(status_code=422, detail="amount must be a positive number")
    return amount


def _clean_currency(raw: object) -> str:
    currency = normalize_currency(raw)
    if not currency:
        raise HTTPException(
            status_code=422,
            detail="currency must be a 3-5 letter code (e.g. USD, EUR)",
        )
    return currency


def _clean_note(raw: object) -> Optional[str]:
    note = str(raw or "").strip()
    return note or None


def _check_account(account_id: Optional[int], session: Session) -> Optional[int]:
    if account_id is None:
        return None
    if session.get(Account, account_id) is None:
        raise HTTPException(status_code=422, detail="account_id does not exist")
    return account_id


def to_cash_read(entry: CashEntry, session: Session) -> CashEntryRead:
    """Shape one row with its dated conversion into the reporting currency."""
    conversion = convert_amount(
        session,
        entry.amount,
        entry.currency,
        reporting_currency(),
        entry.occurred_on,
    )
    data = entry.model_dump()
    data["amount_usd"] = conversion.amount
    data["fx_missing"] = conversion.missing
    return CashEntryRead(**data)


def _filtered_cash(
    firm: Optional[str], kind: Optional[str], year: Optional[int]
):
    """The shared filter used by the table and the totals."""
    stmt = select(CashEntry)
    firm_filter = (firm or "").strip()
    if firm_filter:
        stmt = stmt.where(func.lower(CashEntry.firm) == firm_filter.lower())
    kind_filter = (kind or "").strip()
    if kind_filter:
        stmt = stmt.where(CashEntry.kind == _clean_kind(kind_filter))
    if year is not None:
        stmt = stmt.where(
            CashEntry.occurred_on >= date(year, 1, 1),
            CashEntry.occurred_on < date(year + 1, 1, 1),
        )
    return stmt


@router.get("", response_model=list[CashEntryRead])
def list_cash(
    firm: Optional[str] = Query(default=None),
    kind: Optional[str] = Query(default=None),
    year: Optional[int] = Query(default=None, ge=1900, le=2200),
    session: Session = Depends(get_session),
):
    """Newest movement first, optionally narrowed to a firm/kind/year."""
    stmt = _filtered_cash(firm, kind, year).order_by(
        CashEntry.occurred_on.desc(), CashEntry.id.desc()
    )
    entries = session.exec(stmt).all()
    return [to_cash_read(entry, session) for entry in entries]


@router.get("/summary", response_model=CashSummary)
def cash_summary(
    firm: Optional[str] = Query(default=None),
    kind: Optional[str] = Query(default=None),
    year: Optional[int] = Query(default=None, ge=1900, le=2200),
    session: Session = Depends(get_session),
):
    """Spent/received/net/ROI in the reporting currency, with per-firm nets.

    Unpriced rows remain visible in the table and in ``unpriced``/``entries``;
    they are never added to a money total as zero.
    """
    entries = session.exec(_filtered_cash(firm, kind, year)).all()
    target = reporting_currency()
    spent = 0.0
    received = 0.0
    unpriced = 0
    buckets: dict[str, dict[str, float | int]] = {}

    for entry in entries:
        bucket = buckets.setdefault(
            entry.firm,
            {"spent": 0.0, "received": 0.0, "entries": 0, "unpriced": 0},
        )
        bucket["entries"] = int(bucket["entries"]) + 1
        conversion = convert_amount(
            session,
            entry.amount,
            entry.currency,
            target,
            entry.occurred_on,
        )
        if conversion.missing or conversion.amount is None:
            bucket["unpriced"] = int(bucket["unpriced"]) + 1
            unpriced += 1
            continue
        amount = float(conversion.amount)
        if cash_direction(entry.kind) > 0:
            received += amount
            bucket["received"] = float(bucket["received"]) + amount
        else:
            spent += amount
            bucket["spent"] = float(bucket["spent"]) + amount

    def roi(received_total: float, spent_total: float) -> Optional[float]:
        if spent_total <= 0:
            return None
        return round(received_total / spent_total, 2)

    by_firm = [
        CashFirmSummary(
            firm=firm_name,
            spent=round(float(bucket["spent"]), 2),
            received=round(float(bucket["received"]), 2),
            net=round(float(bucket["received"]) - float(bucket["spent"]), 2),
            roi=roi(float(bucket["received"]), float(bucket["spent"])),
            entries=int(bucket["entries"]),
            unpriced=int(bucket["unpriced"]),
        )
        for firm_name, bucket in buckets.items()
    ]
    by_firm.sort(key=lambda row: (-row.net, row.firm.lower()))

    spent = round(spent, 2)
    received = round(received, 2)
    return CashSummary(
        currency=target,
        spent=spent,
        received=received,
        net=round(received - spent, 2),
        roi=roi(received, spent),
        by_firm=by_firm,
        unpriced=unpriced,
    )


@router.post("", response_model=CashEntryRead, status_code=201)
def create_cash(payload: CashEntryCreate, session: Session = Depends(get_session)):
    entry = CashEntry(
        firm=_clean_firm(payload.firm),
        kind=_clean_kind(payload.kind),
        amount=_clean_amount(payload.amount),
        currency=_clean_currency(payload.currency),
        occurred_on=payload.occurred_on,
        note=_clean_note(payload.note),
        account_id=_check_account(payload.account_id, session),
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return to_cash_read(entry, session)


@router.patch("/{entry_id}", response_model=CashEntryRead)
def update_cash(
    entry_id: int,
    patch: CashEntryUpdate,
    session: Session = Depends(get_session),
):
    entry = session.get(CashEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Cash entry not found")

    data = patch.model_dump(exclude_unset=True)
    if "firm" in data:
        if data["firm"] is None:
            raise HTTPException(status_code=422, detail="firm must not be empty")
        entry.firm = _clean_firm(data["firm"])
    if "kind" in data:
        if data["kind"] is None:
            raise HTTPException(status_code=422, detail="kind must not be empty")
        entry.kind = _clean_kind(data["kind"])
    if "amount" in data:
        if data["amount"] is None:
            raise HTTPException(status_code=422, detail="amount must be a positive number")
        entry.amount = _clean_amount(data["amount"])
    if "currency" in data:
        if data["currency"] is None:
            raise HTTPException(status_code=422, detail="currency must not be empty")
        entry.currency = _clean_currency(data["currency"])
    if "occurred_on" in data:
        if data["occurred_on"] is None:
            raise HTTPException(status_code=422, detail="occurred_on must not be empty")
        entry.occurred_on = data["occurred_on"]
    if "note" in data:
        entry.note = _clean_note(data["note"])
    if "account_id" in data:
        entry.account_id = _check_account(data["account_id"], session)

    entry.updated_at = _now()
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return to_cash_read(entry, session)


@router.delete("/{entry_id}")
def delete_cash(entry_id: int, session: Session = Depends(get_session)):
    entry = session.get(CashEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Cash entry not found")
    session.delete(entry)
    session.commit()
    return {"deleted": entry_id}
