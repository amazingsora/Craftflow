from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class CharacterCreate(BaseModel):
    name: str
    aliases: Optional[list[str]] = []
    core_traits: Optional[str] = None
    behavior_rules: Optional[str] = None
    voice_style: Optional[str] = None
    forbidden_actions: Optional[str] = None
    notes: Optional[str] = None
    color: Optional[str] = None
    age: Optional[int] = None
    birthday: Optional[str] = None
    ai_prompt: Optional[str] = None


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    aliases: Optional[list[str]] = None
    core_traits: Optional[str] = None
    behavior_rules: Optional[str] = None
    voice_style: Optional[str] = None
    forbidden_actions: Optional[str] = None
    notes: Optional[str] = None
    ai_summary: Optional[str] = None
    portrait_path: Optional[str] = None
    color: Optional[str] = None
    age: Optional[int] = None
    birthday: Optional[str] = None
    ai_prompt: Optional[str] = None
    concept_images: Optional[list[str]] = None
    ai_generated_images: Optional[list[str]] = None


class CharacterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    aliases: Optional[list]
    core_traits: Optional[str]
    behavior_rules: Optional[str]
    voice_style: Optional[str]
    forbidden_actions: Optional[str]
    notes: Optional[str]
    ai_summary: Optional[str]
    portrait_path: Optional[str]
    color: Optional[str]
    concept_images: Optional[list] = []
    ai_generated_images: Optional[list] = []
    age: Optional[int] = None
    birthday: Optional[str] = None
    ai_prompt: Optional[str] = None
    faction_ids: list[int] = []
    created_at: datetime
    updated_at: datetime
