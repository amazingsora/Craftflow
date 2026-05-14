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
from app.models.project import Project
from app.schemas.character import CharacterCreate, CharacterUpdate, CharacterResponse
from app.services.ai import character_service

router = APIRouter(tags=["characters"])
DbDep = Annotated[Session, Depends(get_db)]

_PORTRAIT_DIR = UPLOAD_DIR / "portraits"
_ALLOWED = {"image/jpeg", "image/png", "image/webp"}


@router.get("/characters/default-project")
def get_default_project(db: DbDep):
    """Return the first project or auto-create one if none exist."""
    project = db.query(Project).order_by(Project.id).first()
    if not project:
        project = Project(title="我的創作", author="創作者")
        db.add(project)
        db.commit()
        db.refresh(project)
    return {"id": project.id, "title": project.title}


@router.get("/projects/{project_id}/characters", response_model=list[CharacterResponse])
def list_characters(project_id: int, db: DbDep):
    return db.query(Character).filter(Character.project_id == project_id).all()


@router.post(
    "/projects/{project_id}/characters",
    response_model=CharacterResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_character(project_id: int, data: CharacterCreate, db: DbDep):
    character = Character(project_id=project_id, **data.model_dump())
    db.add(character)
    db.commit()
    db.refresh(character)
    return character


@router.get("/characters/{character_id}", response_model=CharacterResponse)
def get_character(character_id: int, db: DbDep):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


@router.put("/characters/{character_id}", response_model=CharacterResponse)
def update_character(character_id: int, data: CharacterUpdate, db: DbDep):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(character, key, value)
    db.commit()
    db.refresh(character)
    return character


@router.delete("/characters/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_character(character_id: int, db: DbDep):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    db.delete(character)
    db.commit()


@router.post("/characters/{character_id}/summarize", response_model=CharacterResponse)
def summarize_character(character_id: int, db: DbDep, model: str = "dolphin-llama3"):
    """AI organises the character's raw notes into a structured profile summary."""
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    summary = character_service.generate_summary(
        name=character.name,
        core_traits=character.core_traits,
        behavior_rules=character.behavior_rules,
        voice_style=character.voice_style,
        notes=character.notes,
        model=model,
    )
    character.ai_summary = summary
    db.commit()
    db.refresh(character)
    return character


@router.post("/characters/{character_id}/portrait", response_model=CharacterResponse)
async def upload_portrait(
    character_id: int,
    file: Annotated[UploadFile, File(...)],
    db: DbDep,
):
    """Upload a concept image for this character."""
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    if file.content_type not in _ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unsupported type: {file.content_type}")

    _PORTRAIT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename).suffix if file.filename else ".png"
    filename = f"{character_id}_{uuid.uuid4().hex}{suffix}"
    dest = _PORTRAIT_DIR / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # Remove old portrait file if present
    if character.portrait_path:
        old = _PORTRAIT_DIR / character.portrait_path
        if old.exists():
            old.unlink(missing_ok=True)

    character.portrait_path = filename
    db.commit()
    db.refresh(character)
    return character


@router.get("/characters/{character_id}/portrait")
def get_portrait(character_id: int, db: DbDep):
    """Serve the character's portrait image."""
    character = db.get(Character, character_id)
    if not character or not character.portrait_path:
        raise HTTPException(status_code=404, detail="Portrait not found")
    path = _PORTRAIT_DIR / character.portrait_path
    if not path.exists():
        raise HTTPException(status_code=404, detail="Portrait file missing")
    return FileResponse(str(path))
