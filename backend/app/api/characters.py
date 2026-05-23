from __future__ import annotations

import copy
import shutil
import uuid
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import UPLOAD_DIR
from app.core.database import get_db
from app.core import state
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
def summarize_character(character_id: int, db: DbDep, model: Optional[str] = None):
    """AI organises the character's raw notes into a structured profile summary."""
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    used_model = model or state.get_text_model()
    summary = character_service.generate_summary(
        name=character.name,
        core_traits=character.core_traits,
        behavior_rules=character.behavior_rules,
        voice_style=character.voice_style,
        notes=character.notes,
        model=used_model,
    )
    if not summary or summary.startswith("["):
        raise HTTPException(
            status_code=503,
            detail=f"Ollama 回傳錯誤（模型：{used_model}）：{summary or '空回應'}",
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


# ── Concept Images (multi, max 3) ─────────────────────────────────────────────

_MAX_CONCEPT = 3
_AI_IMAGE_DIR = UPLOAD_DIR / "ai_images"


@router.post("/characters/{character_id}/concept-images", response_model=CharacterResponse)
async def upload_concept_image(
    character_id: int,
    file: Annotated[UploadFile, File(...)],
    db: DbDep,
):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    if file.content_type not in _ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unsupported type: {file.content_type}")
    existing = list(character.concept_images or [])
    if len(existing) >= _MAX_CONCEPT:
        raise HTTPException(status_code=400, detail=f"最多只能上傳 {_MAX_CONCEPT} 張概念圖")

    _PORTRAIT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename).suffix if file.filename else ".png"
    filename = f"concept_{character_id}_{uuid.uuid4().hex}{suffix}"
    dest = _PORTRAIT_DIR / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    character.concept_images = [*existing, filename]
    db.commit()
    db.refresh(character)
    return character


@router.delete("/characters/{character_id}/concept-images/{index}", response_model=CharacterResponse)
def delete_concept_image(character_id: int, index: int, db: DbDep):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    existing = list(character.concept_images or [])
    if index < 0 or index >= len(existing):
        raise HTTPException(status_code=404, detail="概念圖不存在")

    filename = existing[index]
    path = _PORTRAIT_DIR / filename
    path.unlink(missing_ok=True)

    character.concept_images = [f for i, f in enumerate(existing) if i != index]
    db.commit()
    db.refresh(character)
    return character


@router.get("/characters/{character_id}/concept-images/{index}")
def get_concept_image(character_id: int, index: int, db: DbDep):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    existing = list(character.concept_images or [])
    if index < 0 or index >= len(existing):
        raise HTTPException(status_code=404, detail="概念圖不存在")
    path = _PORTRAIT_DIR / existing[index]
    if not path.exists():
        raise HTTPException(status_code=404, detail="概念圖檔案不存在")
    return FileResponse(str(path))


# ── AI Generated Images (max 3) ───────────────────────────────────────────────

_MAX_AI_IMAGES = 8


@router.post("/characters/{character_id}/ai-images", response_model=CharacterResponse)
async def save_ai_image(
    character_id: int,
    file: Annotated[UploadFile, File(...)],
    db: DbDep,
):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    existing = list(character.ai_generated_images or [])
    if len(existing) >= _MAX_AI_IMAGES:
        raise HTTPException(status_code=400, detail=f"最多只能儲存 {_MAX_AI_IMAGES} 張 AI 生成圖")

    _AI_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename).suffix if file.filename else ".png"
    filename = f"ai_{character_id}_{uuid.uuid4().hex}{suffix}"
    dest = _AI_IMAGE_DIR / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    character.ai_generated_images = [*existing, filename]
    db.commit()
    db.refresh(character)
    return character


@router.delete("/characters/{character_id}/ai-images/{index}", response_model=CharacterResponse)
def delete_ai_image(character_id: int, index: int, db: DbDep):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    existing = list(character.ai_generated_images or [])
    if index < 0 or index >= len(existing):
        raise HTTPException(status_code=404, detail="AI 圖不存在")

    filename = existing[index]
    path = _AI_IMAGE_DIR / filename
    path.unlink(missing_ok=True)

    character.ai_generated_images = [f for i, f in enumerate(existing) if i != index]
    db.commit()
    db.refresh(character)
    return character


@router.get("/characters/{character_id}/ai-images/{index}")
def get_ai_image(character_id: int, index: int, db: DbDep):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    existing = list(character.ai_generated_images or [])
    if index < 0 or index >= len(existing):
        raise HTTPException(status_code=404, detail="AI 圖不存在")
    path = _AI_IMAGE_DIR / existing[index]
    if not path.exists():
        raise HTTPException(status_code=404, detail="AI 圖檔案不存在")
    return FileResponse(str(path))


# ── Variant helpers ───────────────────────────────────────────────────────────

_MAX_VARIANT_SLOTS = 2  # slots 1 and 2 (Tab 2 and Tab 3)

_EMPTY_VARIANT: dict = {
    "color": None, "core_traits": None, "behavior_rules": None,
    "voice_style": None, "notes": None, "ai_prompt": None, "ai_summary": None,
    "age": None, "height": None, "birthday": None, "gender": None,
    "concept_images": [], "ai_generated_images": [],
}


def _get_variants(character: Character) -> list[dict]:
    """Return a mutable 2-element list of variant dicts (never None)."""
    raw = list(character.variants or [])
    while len(raw) < _MAX_VARIANT_SLOTS:
        raw.append(copy.deepcopy(_EMPTY_VARIANT))
    return raw


def _slot_index(slot: int) -> int:
    if slot < 1 or slot > _MAX_VARIANT_SLOTS:
        raise HTTPException(status_code=400, detail=f"slot must be 1–{_MAX_VARIANT_SLOTS}")
    return slot - 1


# ── Variant text-field CRUD ───────────────────────────────────────────────────

class VariantUpdate(BaseModel):
    color: Optional[str] = None
    core_traits: Optional[str] = None
    behavior_rules: Optional[str] = None
    voice_style: Optional[str] = None
    notes: Optional[str] = None
    ai_prompt: Optional[str] = None
    ai_summary: Optional[str] = None
    age: Optional[int] = None
    height: Optional[int] = None
    birthday: Optional[str] = None
    gender: Optional[str] = None


@router.get("/characters/{character_id}/variants/{slot}")
def get_variant(character_id: int, slot: int, db: DbDep):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    idx = _slot_index(slot)
    return _get_variants(character)[idx]


@router.put("/characters/{character_id}/variants/{slot}", response_model=CharacterResponse)
def update_variant(character_id: int, slot: int, data: VariantUpdate, db: DbDep):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    idx = _slot_index(slot)
    variants = _get_variants(character)
    variants[idx].update({k: v for k, v in data.model_dump(exclude_unset=True).items()})
    character.variants = variants
    flag_modified(character, 'variants')
    db.commit()
    db.refresh(character)
    return character


# ── Variant concept images ────────────────────────────────────────────────────

@router.post("/characters/{character_id}/variants/{slot}/concept-images", response_model=CharacterResponse)
async def upload_variant_concept_image(
    character_id: int, slot: int,
    file: Annotated[UploadFile, File(...)], db: DbDep,
):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    if file.content_type not in _ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unsupported type: {file.content_type}")
    idx = _slot_index(slot)
    variants = _get_variants(character)
    existing = list(variants[idx].get("concept_images") or [])
    if len(existing) >= _MAX_CONCEPT:
        raise HTTPException(status_code=400, detail=f"最多只能上傳 {_MAX_CONCEPT} 張概念圖")

    _PORTRAIT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename).suffix if file.filename else ".png"
    filename = f"v{slot}_concept_{character_id}_{uuid.uuid4().hex}{suffix}"
    dest = _PORTRAIT_DIR / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    variants[idx]["concept_images"] = [*existing, filename]
    character.variants = variants
    flag_modified(character, 'variants')
    db.commit()
    db.refresh(character)
    return character


@router.delete("/characters/{character_id}/variants/{slot}/concept-images/{index}", response_model=CharacterResponse)
def delete_variant_concept_image(character_id: int, slot: int, index: int, db: DbDep):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    idx = _slot_index(slot)
    variants = _get_variants(character)
    existing = list(variants[idx].get("concept_images") or [])
    if index < 0 or index >= len(existing):
        raise HTTPException(status_code=404, detail="概念圖不存在")
    (_PORTRAIT_DIR / existing[index]).unlink(missing_ok=True)
    variants[idx]["concept_images"] = [f for i, f in enumerate(existing) if i != index]
    character.variants = variants
    flag_modified(character, 'variants')
    db.commit()
    db.refresh(character)
    return character


@router.get("/characters/{character_id}/variants/{slot}/concept-images/{index}")
def get_variant_concept_image(character_id: int, slot: int, index: int, db: DbDep):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    idx = _slot_index(slot)
    existing = list((_get_variants(character)[idx].get("concept_images")) or [])
    if index < 0 or index >= len(existing):
        raise HTTPException(status_code=404, detail="概念圖不存在")
    path = _PORTRAIT_DIR / existing[index]
    if not path.exists():
        raise HTTPException(status_code=404, detail="概念圖檔案不存在")
    return FileResponse(str(path))


# ── Variant AI images ─────────────────────────────────────────────────────────

@router.post("/characters/{character_id}/variants/{slot}/ai-images", response_model=CharacterResponse)
async def save_variant_ai_image(
    character_id: int, slot: int,
    file: Annotated[UploadFile, File(...)], db: DbDep,
):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    idx = _slot_index(slot)
    variants = _get_variants(character)
    existing = list(variants[idx].get("ai_generated_images") or [])
    if len(existing) >= _MAX_AI_IMAGES:
        raise HTTPException(status_code=400, detail=f"最多只能儲存 {_MAX_AI_IMAGES} 張 AI 生成圖")

    _AI_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename).suffix if file.filename else ".png"
    filename = f"v{slot}_ai_{character_id}_{uuid.uuid4().hex}{suffix}"
    dest = _AI_IMAGE_DIR / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    variants[idx]["ai_generated_images"] = [*existing, filename]
    character.variants = variants
    flag_modified(character, 'variants')
    db.commit()
    db.refresh(character)
    return character


@router.delete("/characters/{character_id}/variants/{slot}/ai-images/{index}", response_model=CharacterResponse)
def delete_variant_ai_image(character_id: int, slot: int, index: int, db: DbDep):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    idx = _slot_index(slot)
    variants = _get_variants(character)
    existing = list(variants[idx].get("ai_generated_images") or [])
    if index < 0 or index >= len(existing):
        raise HTTPException(status_code=404, detail="AI 圖不存在")
    (_AI_IMAGE_DIR / existing[index]).unlink(missing_ok=True)
    variants[idx]["ai_generated_images"] = [f for i, f in enumerate(existing) if i != index]
    character.variants = variants
    flag_modified(character, 'variants')
    db.commit()
    db.refresh(character)
    return character


@router.get("/characters/{character_id}/variants/{slot}/ai-images/{index}")
def get_variant_ai_image(character_id: int, slot: int, index: int, db: DbDep):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    idx = _slot_index(slot)
    existing = list((_get_variants(character)[idx].get("ai_generated_images")) or [])
    if index < 0 or index >= len(existing):
        raise HTTPException(status_code=404, detail="AI 圖不存在")
    path = _AI_IMAGE_DIR / existing[index]
    if not path.exists():
        raise HTTPException(status_code=404, detail="AI 圖檔案不存在")
    return FileResponse(str(path))


# ── Variant summarize ─────────────────────────────────────────────────────────

@router.post("/characters/{character_id}/variants/{slot}/summarize", response_model=CharacterResponse)
def summarize_variant(character_id: int, slot: int, db: DbDep, model: Optional[str] = None):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    idx = _slot_index(slot)
    variants = _get_variants(character)
    v = variants[idx]
    used_model = model or state.get_text_model()
    summary = character_service.generate_summary(
        name=character.name,
        core_traits=v.get("core_traits"),
        behavior_rules=v.get("behavior_rules"),
        voice_style=v.get("voice_style"),
        notes=v.get("notes"),
        model=used_model,
    )
    if not summary or summary.startswith("["):
        raise HTTPException(
            status_code=503,
            detail=f"Ollama 回傳錯誤（模型：{used_model}）：{summary or '空回應'}",
        )
    variants[idx]["ai_summary"] = summary
    character.variants = variants
    flag_modified(character, 'variants')
    db.commit()
    db.refresh(character)
    return character
