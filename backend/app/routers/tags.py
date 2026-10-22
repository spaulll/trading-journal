"""Tag management API — the taxonomy behind the ledger.

A tag is a word the trader uses: a setup they repeated, a mistake they made.
Two things about them have to hold:

- renaming a tag reaches every trade that carried it — the link is by id, so
  the trade keeps its tag and the tag gets a new name;
- merging a tag into another moves the links and leaves no orphan rows, so
  the old name stops appearing in the ledger and in the analytics.

The list carries the numbers the taxonomy page shows: how many trades carry
the tag, what they made, and how often they won.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, SQLModel, select

from app.database import get_session
from app.models import Tag, TagRead, TradeTagLink
from app.services.analytics_rules import BE_TOLERANCE
from app.services.trade_money import usd_net

router = APIRouter(prefix="/api/tags", tags=["tags"])

CATEGORIES = ("setup", "mistake")


class TagSummary(TagRead):
    """A tag with the numbers the taxonomy page shows."""

    trade_count: int = 0
    net_pnl: float = 0.0
    win_rate: Optional[float] = None
    last_used: Optional[datetime] = None


class TagPatch(SQLModel):
    name: Optional[str] = None
    category: Optional[str] = None


class TagMerge(SQLModel):
    source_id: int
    target_id: int


def _summary(session: Session, tag: Tag) -> TagSummary:
    """The tag with its count and its performance."""
    trades = list(tag.trades)
    nets = [usd_net(t) for t in trades if t.status == "CLOSED"]
    known = [n for n in nets if n is not None]
    wins = sum(1 for n in known if n > BE_TOLERANCE)
    losses = sum(1 for n in known if n < -BE_TOLERANCE)
    decided = wins + losses
    used = [
        t.timestamp_close or t.timestamp_open or t.created_at
        for t in trades
        if (t.timestamp_close or t.timestamp_open or t.created_at) is not None
    ]
    return TagSummary(
        id=tag.id or 0,
        name=tag.name,
        category=tag.category,
        trade_count=len(trades),
        net_pnl=round(sum(known), 2),
        win_rate=round(wins / decided * 100, 1) if decided else None,
        last_used=max(used) if used else None,
    )


@router.get("", response_model=list[TagSummary])
def list_tags(session: Session = Depends(get_session)):
    """Every tag with its count and its performance."""
    tags = session.exec(select(Tag).order_by(Tag.name)).all()
    return [_summary(session, tag) for tag in tags]


@router.patch("/{tag_id}", response_model=TagRead)
def patch_tag(tag_id: int, patch: TagPatch, session: Session = Depends(get_session)):
    """Rename a tag or move it between the setup and mistake taxonomies."""
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    data = patch.model_dump(exclude_unset=True)

    if "name" in data and data["name"] is not None:
        name = str(data["name"]).strip().lower()
        if not name:
            raise HTTPException(status_code=422, detail="name must not be empty")
        clash = session.exec(select(Tag).where(Tag.name == name)).first()
        if clash is not None and clash.id != tag.id:
            raise HTTPException(status_code=409, detail=f"Tag already exists: {name}")
        tag.name = name

    if "category" in data and data["category"] is not None:
        category = str(data["category"]).strip().lower()
        if category not in CATEGORIES:
            raise HTTPException(status_code=422, detail="category must be setup or mistake")
        tag.category = category

    session.add(tag)
    session.commit()
    session.refresh(tag)
    return TagRead.model_validate(tag.model_dump())


@router.post("/merge")
def merge_tags(payload: TagMerge, session: Session = Depends(get_session)):
    """Fold one tag into another.

    The trades keep their history: a trade that carried both tags carries
    the target once, and the source name is gone from the ledger.
    """
    if payload.source_id == payload.target_id:
        raise HTTPException(status_code=422, detail="Cannot merge a tag into itself")
    source = session.get(Tag, payload.source_id)
    target = session.get(Tag, payload.target_id)
    if source is None or target is None:
        raise HTTPException(status_code=404, detail="Tag not found")

    links = session.exec(
        select(TradeTagLink).where(TradeTagLink.tag_id == source.id)
    ).all()
    trade_ids = [link.trade_id for link in links if link.trade_id is not None]
    # The source tag goes first: its links go with it, and the target's links
    # are then written from the trade ids that were carrying it.
    session.delete(source)
    session.flush()
    for trade_id in trade_ids:
        already = session.exec(
            select(TradeTagLink).where(
                TradeTagLink.trade_id == trade_id,
                TradeTagLink.tag_id == target.id,
            )
        ).first()
        if already is None:
            session.add(TradeTagLink(trade_id=trade_id, tag_id=target.id))
    session.commit()
    session.commit()
    session.refresh(target)
    return {
        "merged": source.name,
        "into": target.name,
        "trades": len(links),
        "tag": TagRead.model_validate(target.model_dump()),
    }
