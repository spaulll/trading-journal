"""LLM weekend-review summaries (PLAN-v2 insights).

The manual trigger (POST /api/insights/weekend-review) and the Monday-morning
scheduler job share `app.services.weekly_review`: gather the week's trade
notes (thesis / review_notes / !mistake tags) plus daily notes (pre_market /
eod_review), send them to an OpenAI-compatible chat API, and store the
markdown summary in `insight_report` for history tracking.

Secrets live in backend/.env (LLM_BASE_URL / LLM_API_KEY / LLM_MODEL) and
never leave the server — the frontend only receives rendered markdown.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.database import get_session
from app.models import InsightReport, InsightReportRead, WeekendReviewRequest
from app.services.weekly_review import generate_weekend_review

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.post("/weekend-review")
def weekend_review(payload: WeekendReviewRequest, session: Session = Depends(get_session)):
    try:
        result = generate_weekend_review(session, payload.date_from, payload.date_to)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result["status"] == "empty":
        return result
    return {
        "status": "ok",
        "date_from": result["date_from"],
        "date_to": result["date_to"],
        "report": InsightReportRead.model_validate(result["report"].model_dump()),
    }


@router.get("/reports", response_model=list[InsightReportRead])
def list_reports(
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    rows = session.exec(
        select(InsightReport).order_by(InsightReport.created_at.desc()).limit(limit)
    ).all()
    return [InsightReportRead.model_validate(r.model_dump()) for r in rows]


@router.delete("/reports/{report_id}")
def delete_report(report_id: int, session: Session = Depends(get_session)):
    report = session.get(InsightReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="No such report")
    session.delete(report)
    session.commit()
    return {"deleted": report_id}
