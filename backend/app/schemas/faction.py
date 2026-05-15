from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class FactionCreate(BaseModel):
    name: str


class FactionUpdate(BaseModel):
    name: Optional[str] = None


class FactionMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    portrait_path: Optional[str]
    color: Optional[str]


class FactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    thumbnail_path: Optional[str]
    characters: List[FactionMemberResponse] = []
