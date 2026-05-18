from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ArtStyle(Base):
    __tablename__ = "art_styles"

    id:             Mapped[int]           = mapped_column(primary_key=True, autoincrement=True)
    name:           Mapped[str]           = mapped_column(String(100), unique=True, nullable=False)
    description:    Mapped[Optional[str]] = mapped_column(Text, default="")
    base_style:     Mapped[str]           = mapped_column(String(30), default="sdxl")
    quality_prefix: Mapped[Optional[str]] = mapped_column(Text, default="")
    negative:       Mapped[Optional[str]] = mapped_column(Text, default="")
    extra_tags:     Mapped[Optional[str]] = mapped_column(Text, default="")
    # [{model: str, weight: float}]
    loras:          Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    created_at:     Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)
    updated_at:     Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
