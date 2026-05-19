from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Text, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TrainingJob(Base):
    __tablename__ = "training_jobs"

    id:              Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    name:            Mapped[str]           = mapped_column(String(100), nullable=False)
    # 狀態: pending / running / done / failed / stopped
    status:          Mapped[str]           = mapped_column(String(20), default="pending")

    # 訓練設定
    base_checkpoint: Mapped[str]           = mapped_column(String(255), nullable=False)
    trigger_word:    Mapped[str]           = mapped_column(String(100), nullable=False)
    lora_rank:       Mapped[int]           = mapped_column(Integer, default=32)
    learning_rate:   Mapped[float]         = mapped_column(Float, default=1e-4)
    epochs:          Mapped[int]           = mapped_column(Integer, default=10)
    resolution:      Mapped[int]           = mapped_column(Integer, default=1024)

    # 輸出 — 訓練完成後的 .safetensors 路徑（相對 ComfyUI loras 目錄）
    output_lora_name: Mapped[Optional[str]] = mapped_column(String(255))

    # 綁定畫風模型（完成後自動掛上去）
    art_style_id:    Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("art_styles.id"), nullable=True)

    # 進度快照（最新一次的 step/total/loss）
    current_step:    Mapped[int]           = mapped_column(Integer, default=0)
    total_steps:     Mapped[int]           = mapped_column(Integer, default=0)
    last_loss:       Mapped[Optional[float]] = mapped_column(Float)
    log_tail:        Mapped[Optional[str]] = mapped_column(Text)   # 最後 N 行 log

    started_at:      Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at:     Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at:      Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)
    updated_at:      Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
