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
    height: Optional[int] = None
    birthday: Optional[str] = None
    ai_prompt: Optional[str] = None
    outfit: Optional[str] = None
    gender: Optional[str] = None
    art_style_id: Optional[int] = None
    lora_name: Optional[str] = None
    lora_weight: Optional[float] = None


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
    height: Optional[int] = None
    birthday: Optional[str] = None
    ai_prompt: Optional[str] = None
    outfit: Optional[str] = None
    gender: Optional[str] = None
    art_style_id: Optional[int] = None
    lora_name: Optional[str] = None
    lora_weight: Optional[float] = None
    concept_images: Optional[list[str]] = None
    ai_generated_images: Optional[list[str]] = None
    tab_names: Optional[list[str]] = None
    variants: Optional[list] = None


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
    height: Optional[int] = None
    birthday: Optional[str] = None
    ai_prompt: Optional[str] = None
    outfit: Optional[str] = None
    gender: Optional[str] = None
    faction_ids: list[int] = []
    art_style_id: Optional[int] = None
    lora_name: Optional[str] = None
    lora_weight: Optional[float] = None
    tab_names: Optional[list] = None
    variants: Optional[list] = None
    created_at: datetime
    updated_at: datetime
