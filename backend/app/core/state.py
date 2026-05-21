from app.core.config import COMFYUI_CHECKPOINT as _default, DEFAULT_VISION_MODEL as _default_vision

_active_checkpoint: str = _default
_active_workflow: str = "text_to_image.json"
_active_lora: dict = {"name": "", "strength": 0.8}  # name="" means disabled
_active_vision_model: str = ""  # "" = use DEFAULT_VISION_MODEL from config


def get_checkpoint() -> str:
    return _active_checkpoint


def set_checkpoint(name: str) -> None:
    global _active_checkpoint
    _active_checkpoint = name


def get_workflow() -> str:
    return _active_workflow


def set_workflow(name: str) -> None:
    global _active_workflow
    _active_workflow = name


def get_lora() -> dict:
    return _active_lora


def set_lora(name: str, strength: float = 0.8) -> None:
    global _active_lora
    _active_lora = {"name": name, "strength": max(0.0, min(1.0, strength))}


def get_vision_model() -> str:
    return _active_vision_model or _default_vision


def set_vision_model(model: str) -> None:
    global _active_vision_model
    _active_vision_model = model
