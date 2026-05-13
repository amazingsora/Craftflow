from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.analysis_report import AnalysisReport
from app.schemas.analysis_report import AnalysisReportResponse

router = APIRouter(tags=["analysis"])
DbDep = Annotated[Session, Depends(get_db)]


@router.get("/chapters/{chapter_id}/analysis", response_model=list[AnalysisReportResponse])
def list_analysis_reports(chapter_id: int, db: DbDep):
    return (
        db.query(AnalysisReport)
        .filter(AnalysisReport.chapter_id == chapter_id)
        .order_by(AnalysisReport.created_at.desc())
        .all()
    )
