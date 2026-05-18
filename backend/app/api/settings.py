"""
Runtime settings endpoints (in-memory, reset on restart):
  GET  /api/v1/settings/checkpoints  — list available checkpoints from ComfyUI
  GET  /api/v1/settings/checkpoint   — active checkpoint name
  POST /api/v1/settings/checkpoint   — switch active checkpoint
  GET  /api/v1/settings/loras        — list available LoRA models from ComfyUI
"""
from __future__ import annotations

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import COMFYUI_BASE
from app.core import state

router = APIRouter(prefix="/settings", tags=["settings"])


def _fetch_checkpoints() -> list[str]:
    try:
        r = requests.get(f"{COMFYUI_BASE}/object_info/CheckpointLoaderSimple", timeout=8)
        r.raise_for_status()
        data = r.json()
        return data["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"無法從 ComfyUI 取得模型清單：{e}")


@router.get("/checkpoints", summary="列出 ComfyUI 可用 checkpoint")
def list_checkpoints():
    checkpoints = _fetch_checkpoints()
    return {"checkpoints": checkpoints, "active": state.get_checkpoint()}


@router.get("/checkpoint", summary="取得目前使用的 checkpoint")
def get_checkpoint():
    return {"checkpoint": state.get_checkpoint()}


class SetCheckpointRequest(BaseModel):
    checkpoint: str


@router.post("/checkpoint", summary="切換 checkpoint（執行期，重啟後回到 .env 設定）")
def set_checkpoint(req: SetCheckpointRequest):
    if not req.checkpoint.strip():
        raise HTTPException(status_code=400, detail="checkpoint 不可為空")
    state.set_checkpoint(req.checkpoint.strip())
    return {"checkpoint": state.get_checkpoint()}


@router.get("/loras", summary="列出 ComfyUI 可用 LoRA 模型")
def list_loras():
    try:
        r = requests.get(f"{COMFYUI_BASE}/object_info/LoraLoader", timeout=8)
        r.raise_for_status()
        data = r.json()
        loras = data["LoraLoader"]["input"]["required"]["lora_name"][0]
        return {"loras": loras}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"無法從 ComfyUI 取得 LoRA 清單：{e}")
