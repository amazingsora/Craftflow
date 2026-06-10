from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.chapter import Chapter
    from app.models.volume import Volume
    from app.models.character import Character
    from app.models.illustration import Illustration
    from app.models.faction import Faction


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    author: Mapped[str] = mapped_column(String(100))
    synopsis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cover_image_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    genre: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default='構思中')
    art_style_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("art_styles.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    chapters: Mapped[list[Chapter]] = relationship(
        "Chapter", back_populates="project",
        cascade="all, delete-orphan", order_by="Chapter.order_index",
    )
    volumes: Mapped[list[Volume]] = relationship(
        "Volume", back_populates="project",
        cascade="all, delete-orphan", order_by="Volume.order_index",
    )
    characters: Mapped[list[Character]] = relationship(
        "Character", back_populates="project", cascade="all, delete-orphan",
    )
    illustrations: Mapped[list[Illustration]] = relationship(
        "Illustration", back_populates="project", cascade="all, delete-orphan",
    )
    factions: Mapped[list[Faction]] = relationship(
        "Faction", back_populates="project", cascade="all, delete-orphan",
    )
