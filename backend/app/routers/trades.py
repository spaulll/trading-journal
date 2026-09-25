"""Core trade CRUD API + bot sync endpoint (PLAN Task 1.3 / 1.4)."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, delete, select

from app.database import get_session
from app.models import Screenshot, ScreenshotRead, Tag, TagRead, Trade, TradePatch, TradeRead, TradeTagLink
from app.services.sync_service import get_or_create_tag, parse_tags, sync_trades

router = APIRouter(prefix="/api/trades", tags=["trades"])


def to_trade_read(trade: Trade) -> TradeRead:
    return TradeRead(
        **trade.model_dump(exclude={"tags", "screenshots"}),
        tags=[TagRead.model_validate(t.model_dump()) for t in trade.tags],
        screenshots=[ScreenshotRead.model_validate(s.model_dump()) for s in trade.screenshots],
    )


@router.post("/sync-bot")
def sync_bot(session: Session = Depends(get_session)):
    try:
        return sync_trades(session)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("", response_model=list[TradeRead])
def list_trades(
    status: Optional[str] = Query(default=None, description="OPEN or CLOSED"),
    symbol: Optional[str] = None,
    tag: Optional[str] = Query(default=None, description="Tag name without #/! prefix"),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    session: Session = Depends(get_session),
):
    statement = select(Trade).order_by(Trade.created_at.desc())
    if status:
        statement = statement.where(Trade.status == status.upper())
    if symbol:
        statement = statement.where(Trade.symbol == symbol)
    if date_from:
        statement = statement.where(Trade.timestamp_open >= date_from)
    if date_to:
        statement = statement.where(Trade.timestamp_open <= date_to)
    trades = session.exec(statement).all()
    if tag:
        wanted = tag.lower().lstrip("#!")
        trades = [t for t in trades if any(x.name == wanted for x in t.tags)]
    return [to_trade_read(t) for t in trades]


@router.get("/{trade_id}", response_model=TradeRead)
def get_trade(trade_id: int, session: Session = Depends(get_session)):
    trade = session.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    return to_trade_read(trade)


@router.patch("/{trade_id}", response_model=TradeRead)
def patch_trade(trade_id: int, patch: TradePatch, session: Session = Depends(get_session)):
    trade = session.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    data = patch.model_dump(exclude_unset=True, exclude={"tags"})
    if "status" in data and data["status"]:
        data["status"] = data["status"].upper()
    for key, value in data.items():
        setattr(trade, key, value)
    if patch.tags is not None:
        trade.tags = [
            get_or_create_tag(session, name, category)
            for name, category in parse_tags(" ".join(patch.tags))
        ]
    session.add(trade)
    session.commit()
    session.refresh(trade)
    return to_trade_read(trade)


@router.delete("/{trade_id}")
def delete_trade(trade_id: int, session: Session = Depends(get_session)):
    trade = session.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    session.exec(delete(TradeTagLink).where(TradeTagLink.trade_id == trade_id))
    session.exec(delete(Screenshot).where(Screenshot.trade_id == trade_id))
    session.delete(trade)
    session.commit()
    return {"deleted": trade_id}
