"""
Art AI endpoints:
  POST /api/v1/illustrations/{id}/analyze    — sketch / finished / color critique
  POST /api/v1/illustrations/{id}/describe   — auto-fill ai_description field
  POST /api/v1/illustrations/{id}/ask        — freeform art Q&A with image context
  POST /api/v1/art/ask                       — freeform art Q&A (text only or with upload)
  POST /api/v1/characters/{id}/describe-portrait — describe portrait → visual profile
"""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import UPLOAD_DIR
from app.core.database import get_db
from app.models.character import Character
from app.models.illustration import Illustration
from app.services.ai import art_service, character_service
from app.services.ai.ollama_client import DEFAULT_VISION_MODEL
from app.services.ai.vram_manager import guardian

router = APIRouter(tags=["ai-art"])
DbDep = Annotated[Session, Depends(get_db)]

VALID_MODES = {"sketch_critique", "finished_critique", "line_color"}


class AnalyzeIllustrationRequest(BaseModel):
    mode: str = "sketch_critique"   # sketch_critique | finished_critique | line_color
    model: str = DEFAULT_VISION_MODEL


class ArtAskRequest(BaseModel):
    question: str
    model: str = DEFAULT_VISION_MODEL


class DescribePortraitRequest(BaseModel):
    model: str = DEFAULT_VISION_MODEL


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/illustrations/{illustration_id}/analyze")
async def analyze_illustration(illustration_id: int, req: AnalyzeIllustrationRequest, db: DbDep):
    if req.mode not in VALID_MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {VALID_MODES}")

    illus = _get_illustration(illustration_id, db)
    image_path = str(UPLOAD_DIR / illus.file_path)

    await guardian.request_focus("ollama")

    if req.mode == "sketch_critique":
        result = await run_in_threadpool(art_service.critique_sketch, image_path, model=req.model)
    elif req.mode == "finished_critique":
        result = await run_in_threadpool(art_service.critique_finished, image_path, model=req.model)
    else:
        result = await run_in_threadpool(art_service.advise_color, image_path, model=req.model)

    return {
        "illustration_id": illustration_id,
        "mode": result.mode,
        "content": result.content,
        "success": result.success,
        "warnings": result.warnings,
    }


@router.post("/illustrations/{illustration_id}/describe")
async def describe_illustration(illustration_id: int, db: DbDep, model: str = DEFAULT_VISION_MODEL):
    illus = _get_illustration(illustration_id, db)
    image_path = str(UPLOAD_DIR / illus.file_path)

    await guardian.request_focus("ollama")
    description = await run_in_threadpool(art_service.describe_illustration, image_path, model=model)
    illus.ai_description = description
    db.commit()

    return {"illustration_id": illustration_id, "ai_description": description}


@router.post("/illustrations/{illustration_id}/ask")
async def ask_with_illustration(illustration_id: int, req: ArtAskRequest, db: DbDep):
    illus = _get_illustration(illustration_id, db)
    image_path = str(UPLOAD_DIR / illus.file_path)

    await guardian.request_focus("ollama")
    answer = await run_in_threadpool(
        art_service.composition_ask,
        question=req.question,
        image_path=image_path,
        model=req.model,
    )
    return {"illustration_id": illustration_id, "question": req.question, "answer": answer}


@router.post("/art/ask")
async def art_ask_freeform(
    question: str,
    model: str = DEFAULT_VISION_MODEL,
    image: Annotated[Optional[UploadFile], File()] = None,
):
    """
    Freeform art Q&A. Optionally attach an image for context.
    """
    image_bytes = None
    if image:
        image_bytes = await image.read()

    await guardian.request_focus("ollama")
    answer = await run_in_threadpool(
        art_service.composition_ask,
        question=question,
        image_bytes=image_bytes,
        model=model,
    )
    return {"question": question, "answer": answer}


@router.post("/characters/{character_id}/describe-portrait")
async def describe_character_portrait(
    character_id: int,
    req: DescribePortraitRequest,
    db: DbDep,
    illustration_id: Optional[int] = None,
):
    """
    Describe a character's portrait illustration and save to character notes.
    If illustration_id is provided, uses that; otherwise uses first portrait in DB.
    """
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    if illustration_id:
        illus = db.get(Illustration, illustration_id)
        if not illus:
            raise HTTPException(status_code=404, detail="Illustration not found")
    else:
        illus = (
            db.query(Illustration)
            .filter(Illustration.linked_character_id == character_id)
            .first()
        )
        if not illus:
            raise HTTPException(
                status_code=404,
                detail="No portrait linked to this character. Link one via PUT /illustrations/{id} or provide illustration_id.",
            )

    image_path = str(UPLOAD_DIR / illus.file_path)
    await guardian.request_focus("ollama")
    description = await run_in_threadpool(
        character_service.describe_portrait, image_path, character.name, model=req.model
    )

    existing = character.notes or ""
    sep = "\n\n---\n" if existing else ""
    character.notes = existing + sep + f"[視覺設定（AI）]\n{description}"
    db.commit()

    return {
        "character_id": character_id,
        "character_name": character.name,
        "illustration_id": illus.id,
        "visual_description": description,
    }


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_illustration(illustration_id: int, db: Session) -> Illustration:
    illus = db.get(Illustration, illustration_id)
    if not illus:
        raise HTTPException(status_code=404, detail="Illustration not found")
    file_path = UPLOAD_DIR / illus.file_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Illustration file not found on disk")
    return illus
