"""art_generate request models（放在 schemas 讓 services 不依賴 api 層）。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class CompilePromptRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    art_style_id: Optional[int] = None


class GenerateRequest(BaseModel):
    prompt: str
    negative_prompt: str = ""   # 若為空，由偵測到的 style 或 art_style 自動填入
    width: int = 1024
    height: int = 1024
    steps: int = 20
    seed: int = -1
    art_style_id: Optional[int] = None
    character_id: Optional[int] = None  # 「以此角色生圖」帶入時有值 → 未成年護欄依角色年齡判定


class GenerateAsyncRequest(GenerateRequest):
    batch_size: int = 1  # 1~8，>1 時同 seed 批次出多張（挑圖用）
