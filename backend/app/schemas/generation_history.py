from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class GenerationHistoryBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    endpoint: str
    character_id: Optional[int]
    variant_slot: Optional[int]
    seed: int
    workflow: str
    style: Optional[str]
    created_at: datetime


class GenerationHistoryResponse(GenerationHistoryBrief):
    positive: Optional[str]
    negative: Optional[str]
    params: Optional[dict]
