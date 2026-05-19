from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Training Image ─────────────────────────────────────────────────────────────

class TrainingImageResponse(BaseModel):
    id:         int
    filename:   str
    caption:    str = ""
    width:      Optional[int]
    height:     Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class TrainingImageUpdate(BaseModel):
    caption: str


# ── Training Job ───────────────────────────────────────────────────────────────

class TrainingJobCreate(BaseModel):
    name:            str            = Field(..., min_length=1, max_length=100)
    base_checkpoint: str
    trigger_word:    str            = Field(..., min_length=1, max_length=100)
    lora_rank:       int            = Field(32, ge=1, le=128)
    learning_rate:   float          = Field(1e-4, gt=0)
    epochs:          int            = Field(10, ge=1, le=200)
    resolution:      int            = Field(1024, ge=512, le=2048)
    art_style_id:    Optional[int]  = None


class TrainingJobResponse(BaseModel):
    id:               int
    name:             str
    status:           str
    base_checkpoint:  str
    trigger_word:     str
    lora_rank:        int
    learning_rate:    float
    epochs:           int
    resolution:       int
    art_style_id:     Optional[int]
    output_lora_name: Optional[str]
    current_step:     int
    total_steps:      int
    last_loss:        Optional[float]
    started_at:       Optional[datetime]
    finished_at:      Optional[datetime]
    created_at:       datetime

    model_config = {"from_attributes": True}
