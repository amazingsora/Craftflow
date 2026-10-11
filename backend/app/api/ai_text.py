"""AI text analysis endpoints [FD-003]"""
from __future__ import annotations

from typing import Annotated, Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db
from app.models.analysis_report import AnalysisReport
from app.models.chapter import Chapter
from app.models.character import Character
from app.services.ai import rhythm_service, rewrite_service, consistency_service, character_service
from app.core import state
from app.services.ai import ollama_client
from app.services.ai.vram_manager import guardian

router = APIRouter(tags=["ai-text"])
DbDep = Annotated[Session, Depends(get_db)]


# ── Schema ────────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    mode: str = "gentle"          # gentle | pro
    enable_semantic: bool = False
    model: Optional[str] = None  # None → 設定頁選的文字模型


class RewriteRequest(BaseModel):
    mode: str = "gentle"
    model: Optional[str] = None  # None → 設定頁選的文字模型


class ExtractRequest(BaseModel):
    chapter_id: int
    model: Optional[str] = None  # None → 設定頁選的文字模型


class CharacterAskRequest(BaseModel):
    question: str
    model: Optional[str] = None  # None → 設定頁選的文字模型


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/chapters/{chapter_id}/analyze")
async def analyze_chapter(chapter_id: int, req: AnalyzeRequest, db: DbDep):
    chapter = db.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    if not chapter.content:
        raise HTTPException(status_code=400, detail="Chapter has no content")

    # 1. Rhythm
    rhythm = rhythm_service.analyze(chapter.content)
    rhythm_data = [
        {"index": p.index, "char_count": p.char_count, "status": p.status,
         "score": p.score, "preview": p.preview}
        for p in rhythm.paragraphs
    ]

    # 2. Consistency (uses characters from DB)
    db_chars = db.query(Character).filter(Character.project_id == chapter.project_id).all()
    await guardian.request_focus("ollama")
    profiles = [
        consistency_service.CharacterProfile(
            name=c.name,
            aliases=c.aliases or [],
            forbidden_actions=_parse_lines(c.forbidden_actions),
            behavior_rules=c.behavior_rules,
            voice_style=c.voice_style,
        )
        for c in db_chars
    ]
    consistency_results, warnings = await run_in_threadpool(
        consistency_service.analyze,
        chapter.content,
        profiles,
        enable_semantic=req.enable_semantic and req.mode == "pro",
        model=_model(req.model),
    )
    consistency_data = [
        {
            "paragraph_index": pc.index,
            "preview": pc.preview,
            "mentioned_characters": pc.mentioned_characters,
            "issues": [
                {"type": i.type, "severity": i.severity, "target": i.target,
                 "description": i.description, "evidence": i.evidence, "source": i.source}
                for i in pc.issues
            ],
        }
        for pc in consistency_results
    ]

    # 3. Save report to DB
    import json
    report_content = json.dumps({"rhythm": rhythm_data, "consistency": consistency_data, "warnings": warnings}, ensure_ascii=False)
    report = AnalysisReport(chapter_id=chapter_id, report_type="analysis", content=report_content)
    db.add(report)
    db.commit()

    return {
        "chapter_id": chapter_id,
        "rhythm_summary": rhythm.summary,
        "rhythm": rhythm_data,
        "consistency": consistency_data,
        "warnings": warnings,
        "report_id": report.id,
    }


@router.post("/chapters/{chapter_id}/rewrite")
async def rewrite_chapter(chapter_id: int, req: RewriteRequest, db: DbDep):
    chapter = db.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    if not chapter.content:
        raise HTTPException(status_code=400, detail="Chapter has no content")

    await guardian.request_focus("ollama")
    rhythm = rhythm_service.analyze(chapter.content)
    paragraphs = [p.strip() for p in chapter.content.split("\n\n") if p.strip()]

    to_rewrite = [
        (p.index, paragraphs[p.index - 1], f"Rhythm issue: {p.status}")
        for p in rhythm.paragraphs
        if p.status != "NORMAL" and 1 <= p.index <= len(paragraphs)
    ]

    if not to_rewrite:
        return {"chapter_id": chapter_id, "message": "No rhythm issues found, no rewrite needed.", "suggestions": []}

    suggestions = await run_in_threadpool(
        rewrite_service.batch_rewrite, to_rewrite, mode=req.mode, model=_model(req.model)
    )

    # [CN-123] Ollama 錯誤字串不可當建議內容；分流到 error 欄位
    items = [_suggestion_dict(s) for s in suggestions]
    if items and all(i["error"] for i in items):
        raise HTTPException(status_code=503, detail=f"改寫失敗（文字模型 {_model(req.model)}）：{items[0]['error']}")

    import json
    report_content = json.dumps(items, ensure_ascii=False)
    report = AnalysisReport(chapter_id=chapter_id, report_type="rewrite", content=report_content)
    db.add(report)
    db.commit()

    return {
        "chapter_id": chapter_id,
        "suggestions": items,
        "report_id": report.id,
    }


@router.post("/characters/{character_id}/extract")
async def extract_character_traits(character_id: int, req: ExtractRequest, db: DbDep):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    chapter = db.get(Chapter, req.chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    if chapter.project_id != character.project_id:
        raise HTTPException(status_code=400, detail="Chapter and character belong to different projects")
    if not chapter.content:
        raise HTTPException(status_code=400, detail="Chapter has no content")

    await guardian.request_focus("ollama")
    extracted = await run_in_threadpool(
        character_service.extract_from_text, chapter.content, character.name, model=_model(req.model)
    )
    return {
        "character_id": character_id,
        "character_name": character.name,
        "chapter_id": req.chapter_id,
        "extracted": extracted,
        "hint": "Review and apply fields you agree with via PUT /api/v1/characters/{id}",
    }


@router.post("/characters/{character_id}/ask")
async def character_design_ask(character_id: int, req: CharacterAskRequest, db: DbDep):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    profile = {
        "core_traits": character.core_traits,
        "behavior_rules": character.behavior_rules,
        "voice_style": character.voice_style,
        "notes": character.notes,
    }
    await guardian.request_focus("ollama")
    answer = await run_in_threadpool(
        character_service.design_chat,
        question=req.question,
        character_name=character.name,
        existing_profile=profile,
        model=_model(req.model),
    )
    return {"character_id": character_id, "character_name": character.name, "answer": answer}


# ── helpers ───────────────────────────────────────────────────────────────────

def _model(requested: Optional[str]) -> str:
    return requested or state.get_text_model()


def _suggestion_dict(s) -> dict:
    err = s.suggestion if (not s.suggestion or ollama_client.is_error(s.suggestion)) else None
    return {"paragraph_index": s.paragraph_index, "original": s.original,
            "suggestion": "" if err else s.suggestion, "reason": s.reason,
            "error": (err or "模型回傳空字串") if err is not None else None}

def _parse_lines(text: Optional[str]) -> List[str]:
    if not text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]
