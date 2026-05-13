from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.chapter import Chapter
    from app.models.character import Character
    from app.models.illustration import Illustration


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    author: Mapped[str] = mapped_column(String(100))
    synopsis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cover_image_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    chapters: Mapped[list[Chapter]] = relationship(
        "Chapter", back_populates="project",
        cascade="all, delete-orphan", order_by="Chapter.order_index",
    )
    characters: Mapped[list[Character]] = relationship(
        "Character", back_populates="project", cascade="all, delete-orphan",
    )
    illustrations: Mapped[list[Illustration]] = relationship(
        "Illustration", back_populates="project", cascade="all, delete-orphan",
    )
