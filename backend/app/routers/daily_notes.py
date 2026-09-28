"""Daily journal notes API (pre-market + EOD reviews).

The Telegram bot writes EOD reviews here via replies; the web Journal page
and the calendar day panel read and edit them.
"""

from datetime import date as date_type
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, SQLModel, select

from app.database import get_session
from app.models import DailyNote, DailyNoteRead

router = APIRouter(prefix="/api/daily-notes", tags=["daily-notes"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DailyNotePatch(SQLModel):
    pre_market: Optional[str] = None
    eod_review: Optional[str] = None


@router.get("", response_model=list[DailyNoteRead])
def list_notes(
    date_from: Optional[date_type] = Query(default=None),
    date_to: Optional[date_type] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(get_session),
):
    stmt = select(DailyNote).order_by(DailyNote.date.desc()).limit(limit)
    if date_from is not None:
        stmt = stmt.where(DailyNote.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(DailyNote.date <= date_to)
    return [DailyNoteRead.model_validate(n.model_dump()) for n in session.exec(stmt).all()]


@router.get("/{day}", response_model=DailyNoteRead)
def get_note(day: date_type, session: Session = Depends(get_session)):
    note = session.exec(select(DailyNote).where(DailyNote.date == day)).first()
    if note is None:
        raise HTTPException(status_code=404, detail="No note for this date")
    return DailyNoteRead.model_validate(note.model_dump())


@router.put("/{day}", response_model=DailyNoteRead)
def put_note(day: date_type, patch: DailyNotePatch, session: Session = Depends(get_session)):
    note = session.exec(select(DailyNote).where(DailyNote.date == day)).first()
    if note is None:
        note = DailyNote(date=day)
    for key, value in patch.model_dump(exclude_unset=True).items():
        setattr(note, key, value)
    note.updated_at = _now()
    session.add(note)
    session.commit()
    session.refresh(note)
    return DailyNoteRead.model_validate(note.model_dump())
