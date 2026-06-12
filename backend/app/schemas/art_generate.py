"""art_generate request models。

自 api/art_generate.py 下沉（2026-06-13 A1 Step 4）：
解除 services 對 api 層型別的依賴（_build_txt2img 吃 GenerateRequest）。
"""
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


class GenerateAsyncRequest(GenerateRequest):
    batch_size: int = 1  # 1~8，>1 時同 seed 批次出多張（挑圖用）
