from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TrainingImage(Base):
    __tablename__ = "training_images"

    id:         Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename:   Mapped[str]           = mapped_column(String(255), nullable=False)
    filepath:   Mapped[str]           = mapped_column(String(500), nullable=False)
    caption:    Mapped[Optional[str]] = mapped_column(Text, default="")
    width:      Mapped[Optional[int]] = mapped_column(Integer)
    height:     Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
