"""Low-level Ollama HTTP client [FD-072]"""
from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Optional

import requests
from PIL import Image

from app.core.config import (
    OLLAMA_BASE,
    DEFAULT_TEXT_MODEL,
    DEFAULT_VISION_MODEL,
    OLLAMA_KEEP_ALIVE_SEC,
)
from app.services.http_local import SESSION

TIMEOUT_TEXT = 300
TIMEOUT_VISION = 300

_VISION_MAX_PX = 768   # single-image: enough detail, acceptable speed
_VISION_MULTI_MAX_PX = 448  # multi-image: reduce patches ~66% to avoid quadratic slowdown


def _resize_for_vision(image_bytes: bytes, max_px: int = _VISION_MAX_PX) -> bytes:
    """Resize image so its longest side is at most max_px. Returns original on failure."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        if max(w, h) <= max_px:
            return image_bytes
        scale = max_px / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        fmt = img.format or "PNG"
        img.save(buf, format=fmt)
        return buf.getvalue()
    except Exception:
        return image_bytes


def _apply_keep_alive(payload: dict, keep_alive: Optional[int]) -> dict:
    """keep_alive=None → 用 OLLAMA_KEEP_ALIVE_SEC（預設 0＝用完即退 VRAM）；負值＝不送欄位。"""
    v = OLLAMA_KEEP_ALIVE_SEC if keep_alive is None else keep_alive
    if v >= 0:
        payload["keep_alive"] = v
    return payload


def generate(
    prompt: str,
    model: str = DEFAULT_TEXT_MODEL,
    options: Optional[dict] = None,
    keep_alive: Optional[int] = None,
) -> str:
    """Text generation via Ollama /api/generate [FD-073]"""
    # think=false: disable Qwen3 thinking mode so response is never empty.
    # Non-Qwen3 models ignore this field.
    payload: dict = {"model": model, "prompt": prompt, "stream": False, "think": False}
    if options:
        payload["options"] = options
    _apply_keep_alive(payload, keep_alive)
    return _post_generate(payload, TIMEOUT_TEXT, "Ollama")


def analyze_image(
    image_path: str,
    prompt: str,
    model: str = DEFAULT_VISION_MODEL,
    keep_alive: Optional[int] = None,
) -> str:
    try:
        image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        payload: dict = {"model": model, "prompt": prompt, "images": [image_b64], "stream": False}
        _apply_keep_alive(payload, keep_alive)
        return _post_generate(payload, TIMEOUT_VISION, "Vision")
    except Exception as e:
        return f"[Vision error at {OLLAMA_BASE}: {e}]"


def analyze_image_bytes(
    image_bytes: bytes,
    prompt: str,
    model: str = DEFAULT_VISION_MODEL,
    options: Optional[dict] = None,
    keep_alive: Optional[int] = None,
) -> str:
    # 單張＝多張版的特例（payload 相同）
    return analyze_multi_images_bytes([image_bytes], prompt, model=model, options=options, keep_alive=keep_alive)


def analyze_multi_images_bytes(
    images_bytes: list[bytes],
    prompt: str,
    model: str = DEFAULT_VISION_MODEL,
    options: Optional[dict] = None,
    keep_alive: Optional[int] = None,
) -> str:
    """一次請求送多張圖，讓視覺模型交互參照 [FD-074]"""
    try:
        max_px = _VISION_MULTI_MAX_PX if len(images_bytes) > 1 else _VISION_MAX_PX
        encoded = [
            base64.b64encode(_resize_for_vision(b, max_px=max_px)).decode()
            for b in images_bytes
        ]
        payload: dict = {"model": model, "prompt": prompt, "images": encoded, "stream": False, "think": False}
        if options:
            payload["options"] = options
        _apply_keep_alive(payload, keep_alive)
        return _post_generate(payload, TIMEOUT_VISION, "Vision")
    except Exception as e:
        return f"[Vision error at {OLLAMA_BASE}: {e}]"


def _post_generate(payload: dict, timeout: int, label: str) -> str:
    try:
        r = SESSION.post(f"{OLLAMA_BASE}/api/generate", json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return f"[{label} unavailable at {OLLAMA_BASE}: run `ollama serve`]"
    except Exception as e:
        return f"[{label} error at {OLLAMA_BASE}: {e}]"


def is_error(response: str) -> bool:
    """True if `response` is one of this module's error strings (e.g. "[Vision error ...]") [FD-075]"""
    return bool(response) and response.startswith("[")


def is_available() -> bool:
    try:
        SESSION.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        return True
    except Exception:
        return False
