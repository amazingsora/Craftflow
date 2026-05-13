from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class IllustrationUpdate(BaseModel):
    caption: Optional[str] = None
    linked_chapter_id: Optional[int] = None
    linked_character_id: Optional[int] = None
    ai_description: Optional[str] = None


class IllustrationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    file_path: str
    thumbnail_path: Optional[str]
    linked_chapter_id: Optional[int]
    linked_character_id: Optional[int]
    caption: Optional[str]
    ai_description: Optional[str]
    created_at: datetime
