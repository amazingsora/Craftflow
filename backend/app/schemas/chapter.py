from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ChapterCreate(BaseModel):
    title: str
    content: Optional[str] = ""
    order_index: Optional[int] = None  # auto-appended to end if omitted


class ChapterUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    order_index: Optional[int] = None


class ChapterBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    order_index: int
    title: str
    created_at: datetime
    updated_at: datetime


class ChapterResponse(ChapterBrief):
    content: Optional[str]
