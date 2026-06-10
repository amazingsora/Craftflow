from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GenerationHistory(Base):
    """生圖參數記錄（log 表）— 重現任一張舊圖所需的全部參數。

    character_id 為純 Integer 非 FK：歷史是日誌，角色刪除後記錄仍應保留。
    """

    __tablename__ = "generation_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    endpoint: Mapped[str] = mapped_column(String(30))  # generate | character_design | variant_design
    character_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    variant_slot: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    seed: Mapped[int] = mapped_column(Integer)
    workflow: Mapped[str] = mapped_column(String(200))
    style: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    positive: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    negative: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
