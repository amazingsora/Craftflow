"""角色變體（variant）資料 helper；刻意無重相依，供 api 與 service 共用。"""
from __future__ import annotations

import copy

from fastapi import HTTPException

from app.models.character import Character

_MAX_VARIANT_SLOTS = 2  # slots 1 and 2 (Tab 2 and Tab 3)

_EMPTY_VARIANT: dict = {
    "color": None, "core_traits": None, "behavior_rules": None,
    "voice_style": None, "notes": None, "ai_prompt": None, "outfit": None, "ai_summary": None,
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
