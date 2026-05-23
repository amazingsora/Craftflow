"""
Runtime settings endpoints (in-memory, reset on restart):
  GET  /api/v1/settings/checkpoints  — list available checkpoints from ComfyUI
  GET  /api/v1/settings/checkpoint   — active checkpoint name
  POST /api/v1/settings/checkpoint   — switch active checkpoint
  GET  /api/v1/settings/workflows    — list workflow JSON files
  GET  /api/v1/settings/workflow     — active workflow filename
  POST /api/v1/settings/workflow     — switch active workflow
  GET  /api/v1/settings/loras        — list LoRA models + active global LoRA
  GET  /api/v1/settings/lora         — active global LoRA {name, strength}
  POST /api/v1/settings/lora         — set global LoRA
"""
from __future__ import annotations

from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import COMFYUI_BASE, OLLAMA_BASE, CUSTOM_WORKFLOWS_DIR, DEFAULT_VISION_MODEL, DEFAULT_TEXT_MODEL
from app.core import state

_CUSTOM_DIR = CUSTOM_WORKFLOWS_DIR
_SYSTEM_DIR = Path("/app/tools/Craftflow/diffusion/workflows")
if not _SYSTEM_DIR.exists():
    _SYSTEM_DIR = Path(__file__).resolve().parents[3] / "tools" / "Craftflow" / "diffusion" / "workflows"

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


@router.get("/workflows", summary="列出使用者自訂 workflow JSON 檔案")
def list_workflows():
    _CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    workflows = sorted(p.name for p in _CUSTOM_DIR.glob("*.json"))
    return {"workflows": workflows, "active": state.get_workflow(), "dir": str(_CUSTOM_DIR)}


@router.get("/workflow", summary="取得目前使用的 workflow")
def get_workflow():
    return {"workflow": state.get_workflow()}


class SetWorkflowRequest(BaseModel):
    workflow: str


@router.post("/workflow", summary="切換 workflow（執行期，重啟後回到預設）")
def set_workflow(req: SetWorkflowRequest):
    name = req.workflow.strip()
    if not name:
        raise HTTPException(status_code=400, detail="workflow 不可為空")
    exists = (_CUSTOM_DIR / name).exists() or (_SYSTEM_DIR / name).exists()
    if not exists:
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' 不存在")
    state.set_workflow(name)
    return {"workflow": state.get_workflow()}


@router.get("/vision-models", summary="列出 Ollama 已安裝的模型")
def list_vision_models():
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        return {"models": models, "default": DEFAULT_VISION_MODEL}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"無法連接 Ollama：{e}")


@router.get("/vision-model", summary="取得目前全域視覺模型")
def get_vision_model():
    return {"model": state.get_vision_model(), "default": DEFAULT_VISION_MODEL}


class SetVisionModelRequest(BaseModel):
    model: str


@router.post("/vision-model", summary="切換全域視覺模型（執行期，重啟後回到 .env 設定）")
def set_vision_model(req: SetVisionModelRequest):
    if not req.model.strip():
        raise HTTPException(status_code=400, detail="model 不可為空")
    state.set_vision_model(req.model.strip())
    return {"model": state.get_vision_model()}


@router.get("/text-model", summary="取得目前全域翻譯文字模型")
def get_text_model():
    return {"model": state.get_text_model(), "default": DEFAULT_TEXT_MODEL}


class SetTextModelRequest(BaseModel):
    model: str


@router.post("/text-model", summary="切換全域翻譯文字模型（執行期，重啟後回到 .env 設定）")
def set_text_model(req: SetTextModelRequest):
    if not req.model.strip():
        raise HTTPException(status_code=400, detail="model 不可為空")
    state.set_text_model(req.model.strip())
    return {"model": state.get_text_model()}


@router.get("/loras", summary="列出 ComfyUI 可用 LoRA 模型")
def list_loras():
    try:
        r = requests.get(f"{COMFYUI_BASE}/object_info/LoraLoader", timeout=8)
        r.raise_for_status()
        data = r.json()
        loras = data["LoraLoader"]["input"]["required"]["lora_name"][0]
        return {"loras": loras, "active": state.get_lora()}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"無法從 ComfyUI 取得 LoRA 清單：{e}")


@router.get("/lora", summary="取得目前全局 LoRA 設定")
def get_lora():
    return state.get_lora()


class SetLoraRequest(BaseModel):
    name: str
    strength: float = 0.8


@router.post("/lora", summary="設定全局 LoRA（執行期，重啟後重置）")
def set_lora(req: SetLoraRequest):
    state.set_lora(req.name.strip(), req.strength)
    return state.get_lora()
