"""
Faction API:
  GET    /projects/{id}/factions                  — list factions with members
  POST   /projects/{id}/factions                  — create faction
  PUT    /factions/{id}                           — rename faction
  DELETE /factions/{id}                           — delete faction
  POST   /factions/{id}/thumbnail                 — upload thumbnail
  GET    /factions/{id}/thumbnail                 — serve thumbnail
  POST   /factions/{id}/members/{char_id}         — add member
  DELETE /factions/{id}/members/{char_id}         — remove member
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import UPLOAD_DIR
from app.core.database import get_db
from app.models.character import Character
from app.models.faction import Faction
from app.models.project import Project
from app.schemas.faction import FactionCreate, FactionUpdate, FactionResponse

router = APIRouter(tags=["factions"])
DbDep = Annotated[Session, Depends(get_db)]

_THUMB_DIR = UPLOAD_DIR / "faction_thumbnails"
_ALLOWED = {"image/jpeg", "image/png", "image/webp"}


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
    faction = db.get(Faction, faction_id)
    if not faction:
        raise HTTPException(status_code=404, detail="Faction not found")
    if data.name:
        faction.name = data.name.strip()
    db.commit()
    db.refresh(faction)
    return faction


@router.delete("/factions/{faction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_faction(faction_id: int, db: DbDep):
    faction = db.get(Faction, faction_id)
    if not faction:
        raise HTTPException(status_code=404, detail="Faction not found")
    db.delete(faction)
    db.commit()


@router.post("/factions/{faction_id}/thumbnail", response_model=FactionResponse)
async def upload_thumbnail(faction_id: int, file: Annotated[UploadFile, File(...)], db: DbDep):
    faction = db.get(Faction, faction_id)
    if not faction:
        raise HTTPException(status_code=404, detail="Faction not found")
    if file.content_type not in _ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unsupported type: {file.content_type}")

    _THUMB_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename).suffix if file.filename else ".png"
    filename = f"{faction_id}_{uuid.uuid4().hex}{suffix}"
    dest = _THUMB_DIR / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    if faction.thumbnail_path:
        old = _THUMB_DIR / faction.thumbnail_path
        if old.exists():
            old.unlink(missing_ok=True)

    faction.thumbnail_path = filename
    db.commit()
    db.refresh(faction)
    return faction


@router.get("/factions/{faction_id}/thumbnail")
def get_thumbnail(faction_id: int, db: DbDep):
    faction = db.get(Faction, faction_id)
    if not faction or not faction.thumbnail_path:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    path = _THUMB_DIR / faction.thumbnail_path
    if not path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail file missing")
    return FileResponse(str(path))


@router.post("/factions/{faction_id}/members/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def add_member(faction_id: int, character_id: int, db: DbDep):
    faction = db.get(Faction, faction_id)
    if not faction:
        raise HTTPException(status_code=404, detail="Faction not found")
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    if character not in faction.characters:
        faction.characters.append(character)
        db.commit()


@router.delete("/factions/{faction_id}/members/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(faction_id: int, character_id: int, db: DbDep):
    faction = db.get(Faction, faction_id)
    if not faction:
        raise HTTPException(status_code=404, detail="Faction not found")
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    if character in faction.characters:
        faction.characters.remove(character)
        db.commit()
