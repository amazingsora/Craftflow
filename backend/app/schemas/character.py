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


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    aliases: Optional[list[str]] = None
    core_traits: Optional[str] = None
    behavior_rules: Optional[str] = None
    voice_style: Optional[str] = None
    forbidden_actions: Optional[str] = None
    notes: Optional[str] = None


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
    created_at: datetime
    updated_at: datetime
