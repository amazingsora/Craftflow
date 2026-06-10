"""
生圖參數記錄 helper（P3-1）。

record_generation() 永不 raise：記錄失敗只記 log，絕不影響生成流程
（resilient errors）。回傳 history id（失敗回 None），供 X-History-Id header。
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.generation_history import GenerationHistory

logger = logging.getLogger(__name__)


def record_generation(
    db: Session,
    *,
    endpoint: str,
    seed: int,
    workflow: str,
    style: Optional[str] = None,
    positive: Optional[str] = None,
    negative: Optional[str] = None,
    character_id: Optional[int] = None,
    variant_slot: Optional[int] = None,
    params: Optional[dict] = None,
) -> Optional[int]:
    try:
        rec = GenerationHistory(
            endpoint=endpoint,
            seed=seed,
            workflow=workflow,
            style=style,
            positive=positive,
            negative=negative,
            character_id=character_id,
            variant_slot=variant_slot,
            params=params or {},
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec.id
    except Exception as e:
        logger.warning("[gen-history] 記錄失敗（不影響生成）：%s", e)
        try:
            db.rollback()
        except Exception:
            pass
        return None
