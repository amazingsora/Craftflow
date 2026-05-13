from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    title: str
    author: str
    synopsis: Optional[str] = None


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    synopsis: Optional[str] = None
    cover_image_path: Optional[str] = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    author: str
    synopsis: Optional[str]
    cover_image_path: Optional[str]
    created_at: datetime
    updated_at: datetime
