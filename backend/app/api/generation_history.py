"""生圖歷史查詢 API（P3-2）— 供前端「還原參數重跑」。"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.generation_history import GenerationHistory
from app.schemas.generation_history import GenerationHistoryBrief, GenerationHistoryResponse

router = APIRouter(tags=["generation-history"])
DbDep = Annotated[Session, Depends(get_db)]

_MAX_LIMIT = 200


@router.get("/generation-history", response_model=list[GenerationHistoryBrief])
def list_history(
    db: DbDep,
    character_id: Optional[int] = None,
    endpoint: Optional[str] = None,
    limit: int = 50,
):
    q = db.query(GenerationHistory)
    if character_id is not None:
        q = q.filter(GenerationHistory.character_id == character_id)
    if endpoint:
        q = q.filter(GenerationHistory.endpoint == endpoint)
    return q.order_by(GenerationHistory.id.desc()).limit(min(limit, _MAX_LIMIT)).all()


@router.get("/generation-history/{history_id}", response_model=GenerationHistoryResponse)
def get_history(history_id: int, db: DbDep):
    rec = db.get(GenerationHistory, history_id)
    if not rec:
        raise HTTPException(status_code=404, detail="History not found")
    return rec


@router.delete("/generation-history/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_history(history_id: int, db: DbDep):
    rec = db.get(GenerationHistory, history_id)
    if not rec:
        raise HTTPException(status_code=404, detail="History not found")
    db.delete(rec)
    db.commit()
