"""Faction API [FD-019]"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from app.api._upload_utils import (
    ensure_image_type, file_response_or_404, remove_file_if_exists, save_upload,
)
from app.core.config import UPLOAD_DIR
from app.core.database import get_db
from app.models.character import Character
from app.models.faction import Faction
from app.models.project import Project
from app.schemas.faction import FactionCreate, FactionUpdate, FactionResponse

router = APIRouter(tags=["factions"])
DbDep = Annotated[Session, Depends(get_db)]

_THUMB_DIR = UPLOAD_DIR / "faction_thumbnails"


def _get_faction_or_404(db: Session, faction_id: int) -> Faction:
    faction = db.get(Faction, faction_id)
    if not faction:
        raise HTTPException(status_code=404, detail="Faction not found")
    return faction


def _get_faction_and_character(db: Session, faction_id: int, character_id: int) -> tuple[Faction, Character]:
    faction = _get_faction_or_404(db, faction_id)
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return faction, character


@router.get("/projects/{project_id}/factions", response_model=list[FactionResponse])
def list_factions(project_id: int, db: DbDep):
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return db.query(Faction).filter(Faction.project_id == project_id).order_by(Faction.created_at).all()


@router.post("/projects/{project_id}/factions", response_model=FactionResponse, status_code=status.HTTP_201_CREATED)
def create_faction(project_id: int, data: FactionCreate, db: DbDep):
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    faction = Faction(project_id=project_id, name=data.name.strip())
    db.add(faction)
    db.commit()
    db.refresh(faction)
    return faction


@router.put("/factions/{faction_id}", response_model=FactionResponse)
def update_faction(faction_id: int, data: FactionUpdate, db: DbDep):
    faction = _get_faction_or_404(db, faction_id)
    if data.name:
        faction.name = data.name.strip()
    db.commit()
    db.refresh(faction)
    return faction


@router.delete("/factions/{faction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_faction(faction_id: int, db: DbDep):
    faction = _get_faction_or_404(db, faction_id)
    db.delete(faction)
    db.commit()


@router.post("/factions/{faction_id}/thumbnail", response_model=FactionResponse)
async def upload_thumbnail(faction_id: int, file: Annotated[UploadFile, File(...)], db: DbDep):
    faction = _get_faction_or_404(db, faction_id)
    ensure_image_type(file)
    filename = save_upload(file, _THUMB_DIR, f"{faction_id}_")
    remove_file_if_exists(_THUMB_DIR, faction.thumbnail_path)
    faction.thumbnail_path = filename
    db.commit()
    db.refresh(faction)
    return faction


@router.get("/factions/{faction_id}/thumbnail")
def get_thumbnail(faction_id: int, db: DbDep):
    faction = db.get(Faction, faction_id)
    if not faction or not faction.thumbnail_path:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return file_response_or_404(_THUMB_DIR / faction.thumbnail_path, "Thumbnail file missing")


@router.post("/factions/{faction_id}/members/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def add_member(faction_id: int, character_id: int, db: DbDep):
    faction, character = _get_faction_and_character(db, faction_id, character_id)
    if character not in faction.characters:
        faction.characters.append(character)
        db.commit()


@router.delete("/factions/{faction_id}/members/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(faction_id: int, character_id: int, db: DbDep):
    faction, character = _get_faction_and_character(db, faction_id, character_id)
    if character in faction.characters:
        faction.characters.remove(character)
        db.commit()
