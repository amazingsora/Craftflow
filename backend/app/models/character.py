from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, ForeignKey, JSON, Integer, Column, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.faction import Faction

# Association table for Character ↔ Faction many-to-many
character_factions = Table(
    "character_factions",
    Base.metadata,
    Column("character_id", Integer, ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
    Column("faction_id", Integer, ForeignKey("factions.id", ondelete="CASCADE"), primary_key=True),
)


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    aliases: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    core_traits: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    behavior_rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    voice_style: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    forbidden_actions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    portrait_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
    ai_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    concept_images: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    ai_generated_images: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    birthday: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project: Mapped[Project] = relationship("Project", back_populates="characters")
    factions: Mapped[list[Faction]] = relationship(
        "Faction", secondary=character_factions, back_populates="characters"
    )

    @property
    def faction_ids(self) -> list[int]:
        return [f.id for f in self.factions]
