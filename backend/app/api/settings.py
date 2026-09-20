# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
"""
Runtime settings endpoints (in-memory, reset on restart):
  GET  /api/v1/settings/checkpoints   — list available checkpoints from ComfyUI
  GET  /api/v1/settings/checkpoint    — active checkpoint name
  POST /api/v1/settings/checkpoint    — switch active checkpoint
  GET  /api/v1/settings/workflows     — list workflow JSON files
  GET  /api/v1/settings/workflow      — active workflow filename
  POST /api/v1/settings/workflow      — switch active workflow
  GET  /api/v1/settings/capabilities  — IPA/CN capability for current mode+checkpoint
  GET  /api/v1/settings/loras         — list LoRA models + active global LoRA
  GET  /api/v1/settings/lora          — active global LoRA {name, strength}
  POST /api/v1/settings/lora          — set global LoRA
"""
from __future__ import annotations

import json
from pathlib import Path
import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import COMFYUI_BASE, OLLAMA_BASE, CUSTOM_WORKFLOWS_DIR, DEFAULT_VISION_MODEL, DEFAULT_TEXT_MODEL
from app.core import state
from app.services.ai.wf_node_ops import _wf_has_controlnet
from app.services.ai.capability import resolve_capability, resolve_checkpoint_for_workflow
from app.services.http_local import SESSION

_CUSTOM_DIR = CUSTOM_WORKFLOWS_DIR
_SYSTEM_DIR = Path("/app/tools/Craftflow/diffusion/workflows")
if not _SYSTEM_DIR.exists():
    _SYSTEM_DIR = Path(__file__).resolve().parents[3] / "tools" / "Craftflow" / "diffusion" / "workflows"

router = APIRouter(prefix="/settings", tags=["settings"])


def _fetch_checkpoints() -> list[str]:
    try:
        r = SESSION.get(f"{COMFYUI_BASE}/object_info/CheckpointLoaderSimple", timeout=8)
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


_IPA_NODE_TYPES = {"IPAdapterAdvanced", "IPAdapter"}


def _wf_has_ipa(name: str) -> bool:
    """Return True if the workflow JSON contains any IP-Adapter node."""
    for base in (_CUSTOM_DIR, _SYSTEM_DIR):
        path = base / name
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    wf = json.load(f)
                return any(
                    isinstance(n, dict) and n.get("class_type") in _IPA_NODE_TYPES
                    for n in wf.values()
                )
            except Exception:
                return False
    return False


# UI 格式（ComfyUI「Save」匯出，非「Save (API format)」）含頂層 "nodes" 陣列，
# 無法直接送進 /prompt，會在生圖時回 422。提早在列表/切換階段偵測並給明確指引。
_UI_FORMAT_HINT = (
    " 是 ComfyUI UI 格式（含 'nodes' 陣列），無法直接使用。"
    "請在 ComfyUI 重新匯出：Settings → Enable Dev mode options → Save (API format)。"
)


def _wf_is_ui_format(name: str) -> bool:
    """Return True if the workflow JSON is a ComfyUI UI-format export (invalid for /prompt)."""
    for base in (_CUSTOM_DIR, _SYSTEM_DIR):
        path = base / name
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    wf = json.load(f)
                return isinstance(wf.get("nodes"), list)
            except Exception:
                return False
    return False


def _wf_load_dict(name: str) -> dict:
    """Load workflow JSON as dict; returns {} on error."""
    for base in (_CUSTOM_DIR, _SYSTEM_DIR):
        path = base / name
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
    return {}


@router.get("/workflows", summary="列出使用者自訂 workflow JSON 檔案")
def list_workflows():
    _CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    workflows = sorted(p.name for p in _CUSTOM_DIR.glob("*.json"))
    return {
        "workflows": workflows,
        "active": state.get_workflow(),
        "dir": str(_CUSTOM_DIR),
        "ipa_support": {w: _wf_has_ipa(w) for w in workflows},
        "cn_support":  {w: _wf_has_controlnet(_wf_load_dict(w)) for w in workflows},
        # invalid=true 代表該檔是 UI 格式、不可用，前端可標記並提示重新匯出
        "invalid": {w: _wf_is_ui_format(w) for w in workflows},
    }


@router.get("/capabilities", summary="取得目前 checkpoint/workflow 的 IPA/CN 能力")
def get_capabilities():
    """
    回傳目前生效的 checkpoint + workflow 能力組合。
    前端切換 checkpoint / workflow / 生成模式後應重抓此端點。
    """
    # [CN-111] 改讀工作流實際生效的模型：舊寫法在 Anima 下誤判 sdxl → UI 顯示可用、後端靜默丟棄
    wf_name = state.get_workflow()
    ckpt = resolve_checkpoint_for_workflow(wf_name)
    wf_dict = _wf_load_dict(wf_name)
    cap = resolve_capability(wf_dict, ckpt)
    return {
        "ipa_supported": cap["ipa_supported"],
        "cn_supported":  cap["cn_supported"],
        # D'-2：CN 不支援但有替代路徑時回傳其名稱（目前僅 "img2img"，Anima 用）。
        # 前端據此保留「草圖引導」控制項並改標示，而非隱藏。
        "cn_fallback":   cap.get("cn_fallback"),
        "family":        cap["family"],
    }


@router.get("/workflow", summary="取得目前使用的 workflow")
def get_workflow():
    wf = state.get_workflow()
    wf_dict = _wf_load_dict(wf)
    return {
        "workflow":      wf,
        "ipa_supported": _wf_has_ipa(wf),
        "cn_supported":  _wf_has_controlnet(wf_dict),
    }


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
    if _wf_is_ui_format(name):
        raise HTTPException(status_code=422, detail=f"Workflow '{name}'{_UI_FORMAT_HINT}")
    state.set_workflow(name)
    return {"workflow": state.get_workflow(), "ipa_supported": _wf_has_ipa(name)}


# [CN-112] 用 /api/show 的 capabilities 區隔視覺/文字模型；純文字模型會靜默忽略圖片 → 幻覺
_MODEL_CAPS_CACHE: dict[str, list[str]] = {}
# 舊版 Ollama 無 capabilities 欄位時的名稱 fallback，至少不漏判常見 VL 模型
_VISION_NAME_HINTS = ("vl", "vision", "llava", "moondream", "minicpm-v", "bakllava")


def _model_capabilities(name: str) -> list[str]:
    """查詢單一模型的 capabilities；結果以程序內快取避免重複呼叫。
    /api/show 取不到或無此欄位（舊版 Ollama）時，退回名稱推斷視覺能力。"""
    if name in _MODEL_CAPS_CACHE:
        return _MODEL_CAPS_CACHE[name]
    caps: list[str] = []
    try:
        r = SESSION.post(f"{OLLAMA_BASE}/api/show", json={"model": name}, timeout=8)
        r.raise_for_status()
        caps = r.json().get("capabilities") or []
    except Exception:
        caps = []
    if not caps:
        low = name.lower()
        caps = ["vision", "completion"] if any(h in low for h in _VISION_NAME_HINTS) else ["completion"]
    _MODEL_CAPS_CACHE[name] = caps
    return caps


def _is_vision_model(name: str) -> bool:
    return "vision" in _model_capabilities(name)


@router.get("/vision-models", summary="列出 Ollama 已安裝的模型（含能力分類）")
def list_vision_models():
    try:
        r = SESSION.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        r.raise_for_status()
        names = [m["name"] for m in r.json().get("models", [])]
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"無法連接 Ollama：{e}")
    caps = {n: _model_capabilities(n) for n in names}
    vision_models = [n for n in names if "vision" in caps[n]]
    return {
        "models": names,                    # 向後相容：完整清單（文字欄沿用）
        "vision_models": vision_models,     # 僅具視覺能力者（視覺欄專用）
        "caps": caps,                       # {name: [capabilities]}，供前端標籤
        "default": DEFAULT_VISION_MODEL,
    }


@router.get("/vision-model", summary="取得目前全域視覺模型")
def get_vision_model():
    return {"model": state.get_vision_model(), "default": DEFAULT_VISION_MODEL}


class SetVisionModelRequest(BaseModel):
    model: str


@router.post("/vision-model", summary="切換全域視覺模型（執行期，重啟後回到 .env 設定）")
def set_vision_model(req: SetVisionModelRequest):
    name = req.model.strip()
    if not name:
        raise HTTPException(status_code=400, detail="model 不可為空")
    # 守門：無視覺能力的模型設為視覺模型會導致圖片被靜默忽略、輸出幻覺
    if not _is_vision_model(name):
        raise HTTPException(
            status_code=400,
            detail=f"模型「{name}」不具備視覺能力（capabilities 無 vision），無法設為視覺模型。",
        )
    state.set_vision_model(name)
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
        r = SESSION.get(f"{COMFYUI_BASE}/object_info/LoraLoader", timeout=8)
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
