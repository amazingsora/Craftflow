# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
"""角色 CRUD + 圖片資產管理（本檔為 api/ 第二大，30 個端點）。

端點分四組，主角色與變體（variant slot）各一套、結構對稱：
  - 角色本體      : CRUD、summarize（AI 摘要）
  - portrait      : 單張代表圖
  - concept-images: 使用者上傳的概念圖（最多 3 張）
  - ai-images     : AI 生成的人設圖（最多 8 張）+ generation-info 反查生成參數

generation-info：存圖時回填 GenerationHistory.saved_filename，讓「已存的圖 → 當初的
prompt/seed/參數」可反查（見 models/generation_history.py）。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.api._upload_utils import (
    ensure_image_type, file_response_or_404, remove_file_if_exists, save_upload,
)
from app.core.config import UPLOAD_DIR
from app.core.database import get_db
from app.core import state
from app.models.character import Character
from app.models.generation_history import GenerationHistory
from app.models.project import Project
from app.schemas.character import CharacterCreate, CharacterUpdate, CharacterResponse
from app.schemas.generation_history import GenerationHistoryResponse
from app.services.ai import character_service
from app.services.ai.ollama_client import is_error as _ollama_is_error
from app.services.ai.variant_helpers import (
    _get_variants,
    _slot_index,
)

router = APIRouter(tags=["characters"])
DbDep = Annotated[Session, Depends(get_db)]

_PORTRAIT_DIR = UPLOAD_DIR / "portraits"


# [CN-110] 以 X-History-Id 回填 saved_filename，讓「已存的圖 → 當初的 prompt/seed/參數/耗時」可反查
def _bind_history_to_file(db: Session, history_id: Optional[int], filename: str) -> None:
    """把 history 記錄綁到成品檔名。永不 raise —— 綁定失敗不該讓存圖失敗。"""
    if not history_id:
        return
    try:
        rec = db.get(GenerationHistory, history_id)
        if rec is not None:
            rec.saved_filename = filename
    except Exception:  # noqa: BLE001 — resilient errors（CLAUDE.md 規則 3）
        pass


def _history_for_file(db: Session, filename: str) -> GenerationHistory:
    rec = (db.query(GenerationHistory)
             .filter(GenerationHistory.saved_filename == filename)
             .order_by(GenerationHistory.id.desc())
             .first())
    if not rec:
        raise HTTPException(status_code=404, detail="這張圖沒有留下生成資訊（可能存於本功能上線前）")
    return rec


def _get_character_or_404(db: Session, character_id: int) -> Character:
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


def _nth_image(existing: list[str], index: int, label: str = "AI 圖") -> str:
    if index < 0 or index >= len(existing):
        raise HTTPException(status_code=404, detail=f"{label}不存在")
    return existing[index]


_nth_ai_image = _nth_image  # 舊名（tests/test_generation_info_link.py 引用）


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
    character = _get_character_or_404(db, character_id)
    return character


@router.put("/characters/{character_id}", response_model=CharacterResponse)
def update_character(character_id: int, data: CharacterUpdate, db: DbDep):
    character = _get_character_or_404(db, character_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(character, key, value)
    db.commit()
    db.refresh(character)
    return character


@router.delete("/characters/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_character(character_id: int, db: DbDep):
    character = _get_character_or_404(db, character_id)
    db.delete(character)
    db.commit()


# 主角色／變體共用（2026-09-24 整合）：兩者只差欄位來源（Character 屬性 vs variant dict）
_SUMMARY_FIELDS = ("core_traits", "behavior_rules", "voice_style", "notes")


def _summarize_or_503(name: str, fields: dict, model: Optional[str]) -> str:
    used_model = model or state.get_text_model()
    summary = character_service.generate_summary(name=name, model=used_model, **fields)
    if not summary or _ollama_is_error(summary):
        raise HTTPException(
            status_code=503,
            detail=f"Ollama 回傳錯誤（模型：{used_model}）：{summary or '空回應'}",
        )
    return summary


@router.post("/characters/{character_id}/summarize", response_model=CharacterResponse)
def summarize_character(character_id: int, db: DbDep, model: Optional[str] = None):
    """AI organises the character's raw notes into a structured profile summary."""
    character = _get_character_or_404(db, character_id)
    character.ai_summary = _summarize_or_503(
        character.name,
        {f: getattr(character, f) for f in _SUMMARY_FIELDS},
        model,
    )
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
    character = _get_character_or_404(db, character_id)
    ensure_image_type(file)
    filename = save_upload(file, _PORTRAIT_DIR, f"{character_id}_")
    remove_file_if_exists(_PORTRAIT_DIR, character.portrait_path)
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
    return file_response_or_404(_PORTRAIT_DIR / character.portrait_path, "Portrait file missing")


# ── 概念圖（max 3）／AI 人設圖（max 8）：主角色與變體 slot 共用 ─────────────────
# 2026-09-24 重複碼整合：原 10 支端點（主角色 5 + 變體 5）逐支展開「查角色 → 取清單 →
# 驗 index → 存／刪／讀檔」，彼此相似度 86–97%，差別只在清單位置（Character 欄位 vs
# variants[slot]）與檔名前綴。行為（錯誤訊息、檢查順序、檔名格式）逐字保留。

_MAX_CONCEPT = 3
_MAX_AI_IMAGES = 8
_AI_IMAGE_DIR = UPLOAD_DIR / "ai_images"


@dataclass(frozen=True)
class _ImageKind:
    field: str          # Character／variant dict 上的清單欄位名
    directory: Path
    max_count: int
    file_tag: str       # 檔名片段：concept / ai
    label: str          # 錯誤訊息用
    full_detail: str    # 數量已滿的 400 訊息
    check_type: bool    # 上傳時驗 content-type（沿用原行為：AI 圖不驗）


_CONCEPT = _ImageKind("concept_images", _PORTRAIT_DIR, _MAX_CONCEPT, "concept", "概念圖",
                      f"最多只能上傳 {_MAX_CONCEPT} 張概念圖", check_type=True)
_AI = _ImageKind("ai_generated_images", _AI_IMAGE_DIR, _MAX_AI_IMAGES, "ai", "AI 圖",
                 f"最多只能儲存 {_MAX_AI_IMAGES} 張 AI 生成圖", check_type=False)


def _image_list(character: Character, slot: Optional[int], kind: _ImageKind) -> list[str]:
    """slot=None → 主角色；1..N → 變體（經 _slot_index 驗證）。回傳可修改的副本。"""
    if slot is None:
        return list(getattr(character, kind.field) or [])
    return list(_get_variants(character)[_slot_index(slot)].get(kind.field) or [])


def _set_image_list(character: Character, slot: Optional[int], kind: _ImageKind, files: list[str]) -> None:
    if slot is None:
        setattr(character, kind.field, files)
        return
    variants = _get_variants(character)
    variants[_slot_index(slot)][kind.field] = files
    character.variants = variants
    flag_modified(character, 'variants')


def _add_image(db: Session, character_id: int, slot: Optional[int], kind: _ImageKind,
               file: UploadFile, history_id: Optional[int] = None) -> Character:
    character = _get_character_or_404(db, character_id)
    if kind.check_type:
        ensure_image_type(file)
    existing = _image_list(character, slot, kind)
    if len(existing) >= kind.max_count:
        raise HTTPException(status_code=400, detail=kind.full_detail)
    slot_tag = "" if slot is None else f"v{slot}_"
    filename = save_upload(file, kind.directory, f"{slot_tag}{kind.file_tag}_{character_id}_")
    _set_image_list(character, slot, kind, [*existing, filename])
    _bind_history_to_file(db, history_id, filename)
    db.commit()
    db.refresh(character)
    return character


def _remove_image(db: Session, character_id: int, slot: Optional[int], kind: _ImageKind,
                  index: int) -> Character:
    character = _get_character_or_404(db, character_id)
    existing = _image_list(character, slot, kind)
    (kind.directory / _nth_image(existing, index, kind.label)).unlink(missing_ok=True)
    _set_image_list(character, slot, kind, [f for i, f in enumerate(existing) if i != index])
    db.commit()
    db.refresh(character)
    return character


def _serve_image(db: Session, character_id: int, slot: Optional[int], kind: _ImageKind, index: int):
    existing = _image_list(_get_character_or_404(db, character_id), slot, kind)
    return file_response_or_404(kind.directory / _nth_image(existing, index, kind.label),
                                f"{kind.label}檔案不存在")


def _ai_image_generation_info(db: Session, character_id: int, slot: Optional[int], index: int):
    existing = _image_list(_get_character_or_404(db, character_id), slot, _AI)
    return _history_for_file(db, _nth_image(existing, index, _AI.label))


@router.post("/characters/{character_id}/concept-images", response_model=CharacterResponse)
async def upload_concept_image(
    character_id: int,
    file: Annotated[UploadFile, File(...)],
    db: DbDep,
):
    return _add_image(db, character_id, None, _CONCEPT, file)


@router.delete("/characters/{character_id}/concept-images/{index}", response_model=CharacterResponse)
def delete_concept_image(character_id: int, index: int, db: DbDep):
    return _remove_image(db, character_id, None, _CONCEPT, index)


@router.get("/characters/{character_id}/concept-images/{index}")
def get_concept_image(character_id: int, index: int, db: DbDep):
    return _serve_image(db, character_id, None, _CONCEPT, index)


@router.post("/characters/{character_id}/ai-images", response_model=CharacterResponse)
async def save_ai_image(
    character_id: int,
    file: Annotated[UploadFile, File(...)],
    db: DbDep,
    history_id: Annotated[Optional[int], Form()] = None,
):
    return _add_image(db, character_id, None, _AI, file, history_id)


@router.delete("/characters/{character_id}/ai-images/{index}", response_model=CharacterResponse)
def delete_ai_image(character_id: int, index: int, db: DbDep):
    return _remove_image(db, character_id, None, _AI, index)


@router.get("/characters/{character_id}/ai-images/{index}")
def get_ai_image(character_id: int, index: int, db: DbDep):
    return _serve_image(db, character_id, None, _AI, index)


@router.get("/characters/{character_id}/ai-images/{index}/generation-info",
            response_model=GenerationHistoryResponse)
def get_ai_image_generation_info(character_id: int, index: int, db: DbDep):
    """已存 AI 人設圖 → 當初的 prompt / seed / 參數 / 耗時。"""
    return _ai_image_generation_info(db, character_id, None, index)


# ── Variant text-field CRUD ───────────────────────────────────────────────────

class VariantUpdate(BaseModel):
    color: Optional[str] = None
    core_traits: Optional[str] = None
    behavior_rules: Optional[str] = None
    voice_style: Optional[str] = None
    notes: Optional[str] = None
    ai_prompt: Optional[str] = None
    outfit: Optional[str] = None
    ai_summary: Optional[str] = None
    age: Optional[int] = None
    height: Optional[int] = None
    birthday: Optional[str] = None
    gender: Optional[str] = None


@router.get("/characters/{character_id}/variants/{slot}")
def get_variant(character_id: int, slot: int, db: DbDep):
    character = _get_character_or_404(db, character_id)
    idx = _slot_index(slot)
    return _get_variants(character)[idx]


@router.put("/characters/{character_id}/variants/{slot}", response_model=CharacterResponse)
def update_variant(character_id: int, slot: int, data: VariantUpdate, db: DbDep):
    character = _get_character_or_404(db, character_id)
    idx = _slot_index(slot)
    variants = _get_variants(character)
    variants[idx].update({k: v for k, v in data.model_dump(exclude_unset=True).items()})
    character.variants = variants
    flag_modified(character, 'variants')
    db.commit()
    db.refresh(character)
    return character


# ── Variant concept／AI images（共用上方 _add_image／_remove_image／_serve_image） ──

@router.post("/characters/{character_id}/variants/{slot}/concept-images", response_model=CharacterResponse)
async def upload_variant_concept_image(
    character_id: int, slot: int,
    file: Annotated[UploadFile, File(...)], db: DbDep,
):
    return _add_image(db, character_id, slot, _CONCEPT, file)


@router.delete("/characters/{character_id}/variants/{slot}/concept-images/{index}", response_model=CharacterResponse)
def delete_variant_concept_image(character_id: int, slot: int, index: int, db: DbDep):
    return _remove_image(db, character_id, slot, _CONCEPT, index)


@router.get("/characters/{character_id}/variants/{slot}/concept-images/{index}")
def get_variant_concept_image(character_id: int, slot: int, index: int, db: DbDep):
    return _serve_image(db, character_id, slot, _CONCEPT, index)


@router.post("/characters/{character_id}/variants/{slot}/ai-images", response_model=CharacterResponse)
async def save_variant_ai_image(
    character_id: int, slot: int,
    file: Annotated[UploadFile, File(...)], db: DbDep,
    history_id: Annotated[Optional[int], Form()] = None,
):
    return _add_image(db, character_id, slot, _AI, file, history_id)


@router.delete("/characters/{character_id}/variants/{slot}/ai-images/{index}", response_model=CharacterResponse)
def delete_variant_ai_image(character_id: int, slot: int, index: int, db: DbDep):
    return _remove_image(db, character_id, slot, _AI, index)


@router.get("/characters/{character_id}/variants/{slot}/ai-images/{index}")
def get_variant_ai_image(character_id: int, slot: int, index: int, db: DbDep):
    return _serve_image(db, character_id, slot, _AI, index)


@router.get("/characters/{character_id}/variants/{slot}/ai-images/{index}/generation-info",
            response_model=GenerationHistoryResponse)
def get_variant_ai_image_generation_info(character_id: int, slot: int, index: int, db: DbDep):
    return _ai_image_generation_info(db, character_id, slot, index)


# ── Variant summarize ─────────────────────────────────────────────────────────

@router.post("/characters/{character_id}/variants/{slot}/summarize", response_model=CharacterResponse)
def summarize_variant(character_id: int, slot: int, db: DbDep, model: Optional[str] = None):
    character = _get_character_or_404(db, character_id)
    idx = _slot_index(slot)
    variants = _get_variants(character)
    v = variants[idx]
    variants[idx]["ai_summary"] = _summarize_or_503(
        character.name, {f: v.get(f) for f in _SUMMARY_FIELDS}, model,
    )
    character.variants = variants
    flag_modified(character, 'variants')
    db.commit()
    db.refresh(character)
    return character
