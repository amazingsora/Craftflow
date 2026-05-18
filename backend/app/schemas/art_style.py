from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class LoraEntry(BaseModel):
    model: str
    weight: float = 0.8


class ArtStyleCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    base_style: Optional[str] = "sdxl"
    quality_prefix: Optional[str] = ""
    negative: Optional[str] = ""
    extra_tags: Optional[str] = ""
    loras: Optional[list[LoraEntry]] = []


class ArtStyleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    base_style: Optional[str] = None
    quality_prefix: Optional[str] = None
    negative: Optional[str] = None
    extra_tags: Optional[str] = None
    loras: Optional[list[LoraEntry]] = None


class ArtStyleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = ""
    base_style: str
    quality_prefix: Optional[str] = ""
    negative: Optional[str] = ""
    extra_tags: Optional[str] = ""
    loras: list[LoraEntry] = []
    created_at: datetime
    updated_at: datetime
