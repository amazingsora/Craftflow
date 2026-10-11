"""執行期全域設定，持久化到 data/runtime_state.json（import 時載入、setter 即落檔）。
讀寫失敗只記 warning，不中斷流程。"""
import json
import logging
from pathlib import Path

from app.core.config import (
    COMFYUI_CHECKPOINT as _default,
    DEFAULT_VISION_MODEL as _default_vision,
    DEFAULT_TEXT_MODEL as _default_text,
    BASE_DIR,
)

logger = logging.getLogger(__name__)

_STATE_FILE: Path = BASE_DIR.parent / "data" / "runtime_state.json"

_active_checkpoint: str = _default
_active_workflow: str = "text_to_image.json"
_active_lora: dict = {"name": "", "strength": 0.8}  # name="" means disabled
_active_vision_model: str = ""  # "" = use DEFAULT_VISION_MODEL from config
_active_text_model: str = ""   # "" = use DEFAULT_TEXT_MODEL from config


def _save_state() -> None:
    """落檔（atomic：tmp → replace）；失敗只記 warning。"""
    try:
        data = {
            "checkpoint": _active_checkpoint,
            "workflow": _active_workflow,
            "lora": _active_lora,
            "vision_model": _active_vision_model,
            "text_model": _active_text_model,
        }
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STATE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_STATE_FILE)
    except Exception as e:
        logger.warning("[state] 持久化失敗（忽略）：%s", e)


def _load_state() -> None:
    """import 時載入；檔案不存在/損毀 → 保留預設，不 crash。"""
    global _active_checkpoint, _active_workflow, _active_lora
    global _active_vision_model, _active_text_model
    try:
        if not _STATE_FILE.exists():
            return
        data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("[state] 讀取持久化狀態失敗，使用預設：%s", e)
        return
    if not isinstance(data, dict):
        return
    if isinstance(data.get("checkpoint"), str) and data["checkpoint"]:
        _active_checkpoint = data["checkpoint"]
    if isinstance(data.get("workflow"), str) and data["workflow"]:
        _active_workflow = data["workflow"]
    lora = data.get("lora")
    if isinstance(lora, dict) and "name" in lora:
        try:
            _active_lora = {
                "name": str(lora.get("name", "")),
                "strength": max(0.0, min(1.0, float(lora.get("strength", 0.8)))),
            }
        except (TypeError, ValueError):
            pass
    if isinstance(data.get("vision_model"), str):
        _active_vision_model = data["vision_model"]
    if isinstance(data.get("text_model"), str):
        _active_text_model = data["text_model"]


_load_state()


def get_checkpoint() -> str:
    return _active_checkpoint


def set_checkpoint(name: str) -> None:
    global _active_checkpoint
    _active_checkpoint = name
    _save_state()


def get_workflow() -> str:
    return _active_workflow


def set_workflow(name: str) -> None:
    global _active_workflow
    _active_workflow = name
    _save_state()


def get_lora() -> dict:
    return _active_lora


def set_lora(name: str, strength: float = 0.8) -> None:
    global _active_lora
    _active_lora = {"name": name, "strength": max(0.0, min(1.0, strength))}
    _save_state()


def get_vision_model() -> str:
    return _active_vision_model or _default_vision


def set_vision_model(model: str) -> None:
    global _active_vision_model
    _active_vision_model = model
    _save_state()


def get_text_model() -> str:
    return _active_text_model or _default_text


def set_text_model(model: str) -> None:
    global _active_text_model
    _active_text_model = model
    _save_state()
