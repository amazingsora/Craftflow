"""
AI text analysis endpoints:
  POST /api/v1/chapters/{id}/analyze     — rhythm + consistency analysis
  POST /api/v1/chapters/{id}/rewrite     — generate rewrite suggestions
  POST /api/v1/characters/{id}/extract   — extract traits from chapter text
  POST /api/v1/characters/{id}/ask       — character design Q&A
"""
from __future__ import annotations

from typing import Annotated, Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.analysis_report import AnalysisReport
from app.models.chapter import Chapter
from app.models.character import Character
from app.services.ai import rhythm_service, rewrite_service, consistency_service, character_service
from app.services.ai.ollama_client import DEFAULT_TEXT_MODEL

router = APIRouter(tags=["ai-text"])
DbDep = Annotated[Session, Depends(get_db)]


# ── Schema ────────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    mode: str = "gentle"          # gentle | pro
    enable_semantic: bool = False
    model: str = DEFAULT_TEXT_MODEL


class RewriteRequest(BaseModel):
    mode: str = "gentle"
    model: str = DEFAULT_TEXT_MODEL


class ExtractRequest(BaseModel):
    chapter_id: int
    model: str = DEFAULT_TEXT_MODEL


class CharacterAskRequest(BaseModel):
    question: str
    model: str = DEFAULT_TEXT_MODEL


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/chapters/{chapter_id}/analyze")
def analyze_chapter(chapter_id: int, req: AnalyzeRequest, db: DbDep):
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
    consistency_results, warnings = consistency_service.analyze(
        chapter.content,
        profiles,
        enable_semantic=req.enable_semantic and req.mode == "pro",
        model=req.model,
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
def rewrite_chapter(chapter_id: int, req: RewriteRequest, db: DbDep):
    chapter = db.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    if not chapter.content:
        raise HTTPException(status_code=400, detail="Chapter has no content")

    rhythm = rhythm_service.analyze(chapter.content)
    paragraphs = [p.strip() for p in chapter.content.split("\n\n") if p.strip()]

    to_rewrite = [
        (p.index, paragraphs[p.index - 1], f"Rhythm issue: {p.status}")
        for p in rhythm.paragraphs
        if p.status != "NORMAL" and 1 <= p.index <= len(paragraphs)
    ]

    if not to_rewrite:
        return {"chapter_id": chapter_id, "message": "No rhythm issues found, no rewrite needed.", "suggestions": []}

    suggestions = rewrite_service.batch_rewrite(to_rewrite, mode=req.mode, model=req.model)

    import json
    report_content = json.dumps(
        [{"paragraph_index": s.paragraph_index, "original": s.original,
          "suggestion": s.suggestion, "reason": s.reason}
         for s in suggestions],
        ensure_ascii=False,
    )
    report = AnalysisReport(chapter_id=chapter_id, report_type="rewrite", content=report_content)
    db.add(report)
    db.commit()

    return {
        "chapter_id": chapter_id,
        "suggestions": [
            {"paragraph_index": s.paragraph_index, "original": s.original,
             "suggestion": s.suggestion, "reason": s.reason}
            for s in suggestions
        ],
        "report_id": report.id,
    }


@router.post("/characters/{character_id}/extract")
def extract_character_traits(character_id: int, req: ExtractRequest, db: DbDep):
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

    extracted = character_service.extract_from_text(chapter.content, character.name, model=req.model)
    return {
        "character_id": character_id,
        "character_name": character.name,
        "chapter_id": req.chapter_id,
        "extracted": extracted,
        "hint": "Review and apply fields you agree with via PUT /api/v1/characters/{id}",
    }


@router.post("/characters/{character_id}/ask")
def character_design_ask(character_id: int, req: CharacterAskRequest, db: DbDep):
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    profile = {
        "core_traits": character.core_traits,
        "behavior_rules": character.behavior_rules,
        "voice_style": character.voice_style,
        "notes": character.notes,
    }
    answer = character_service.design_chat(
        question=req.question,
        character_name=character.name,
        existing_profile=profile,
        model=req.model,
    )
    return {"character_id": character_id, "character_name": character.name, "answer": answer}


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_lines(text: Optional[str]) -> List[str]:
    if not text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]
