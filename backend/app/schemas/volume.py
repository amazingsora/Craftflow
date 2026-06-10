from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

from app.schemas.chapter import ChapterBrief


class VolumeCreate(BaseModel):
    subtitle: Optional[str] = None
    order_index: Optional[int] = None


class VolumeUpdate(BaseModel):
    subtitle: Optional[str] = None
    order_index: Optional[int] = None


class VolumeBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    order_index: int
    subtitle: Optional[str]
    created_at: datetime
    updated_at: datetime


class VolumeResponse(VolumeBrief):
    chapters: list[ChapterBrief] = []


class ReorderItem(BaseModel):
    id: int
    order_index: int
