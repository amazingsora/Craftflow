from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


GENRES = ['玄幻', '奇幻', '現代都市', '科幻', '古風', 'BL/GL', '輕小說', '其他']
STATUSES = ['構思中', '撰寫中', '修稿中', '完稿']


class ProjectCreate(BaseModel):
    title: str
    author: str
    synopsis: Optional[str] = None
    genre: Optional[str] = None
    status: Optional[str] = '構思中'


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    synopsis: Optional[str] = None
    cover_image_path: Optional[str] = None
    genre: Optional[str] = None
    status: Optional[str] = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    author: str
    synopsis: Optional[str]
    cover_image_path: Optional[str]
    genre: Optional[str]
    status: Optional[str]
    created_at: datetime
    updated_at: datetime
