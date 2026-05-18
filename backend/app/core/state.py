from app.core.config import COMFYUI_CHECKPOINT as _default

_active_checkpoint: str = _default


def get_checkpoint() -> str:
    return _active_checkpoint


def set_checkpoint(name: str) -> None:
    global _active_checkpoint
    _active_checkpoint = name
