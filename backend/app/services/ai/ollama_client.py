"""
Low-level Ollama HTTP client.
Wraps both text generation and vision (image) analysis.
All errors are caught and returned as strings rather than raised,
so callers can decide how to surface them to the user.
"""
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
    """keep_alive=None → 取 config 的 OLLAMA_KEEP_ALIVE_SEC（預設 0＝用完即退 VRAM）。

    SYNC-006 N14（2026-09-20）：舊版 None 代表「不送這個欄位」，於是吃 Ollama 自己的
    5 分鐘預設。char-gen 主線（compiler.py / vision_extract.py）早就自己傳 0，但
    art_service / character_service / training 那幾條沒傳 —— 9B 模型就這樣在 16G 卡上
    待 5 分鐘跟 ComfyUI 搶顯存，是主 KSampler 掉到 12.69 s/it 的上游成因之一。
    設 OLLAMA_KEEP_ALIVE_SEC=-1 可回到舊行為（負值＝不送欄位，交還 Ollama 預設）。
    """
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
    """
    Text generation via Ollama /api/generate.

    options examples:
      {"temperature": 0.3, "num_predict": 200}  — stable tag output
      {"temperature": 0.8}                       — creative writing

    keep_alive: seconds to keep model in VRAM after request (0 = unload immediately).
    """
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
    # 單張＝多張版的特例（len==1 時 max_px 同為 _VISION_MAX_PX，payload 逐欄相同）；2026-09-24 重複碼整合
    return analyze_multi_images_bytes([image_bytes], prompt, model=model, options=options, keep_alive=keep_alive)


def analyze_multi_images_bytes(
    images_bytes: list[bytes],
    prompt: str,
    model: str = DEFAULT_VISION_MODEL,
    options: Optional[dict] = None,
    keep_alive: Optional[int] = None,
) -> str:
    """
    Send multiple images in one Ollama request so the vision model can
    cross-reference them.  images_bytes must be non-empty.
    Each image is resized to _VISION_MULTI_MAX_PX (smaller than single-image)
    to prevent quadratic patch growth from causing extreme slowdown.
    """
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
        return f"[{label} unavailable at {OLLAMA_BASE}: run `ollama serve` and ensure OLLAMA_HOST=0.0.0.0]"
    except Exception as e:
        return f"[{label} error at {OLLAMA_BASE}: {e}]"


def is_error(response: str) -> bool:
    """
    True if `response` is one of this module's error strings (e.g. "[Vision error ...]").
    Centralizes the `.startswith("[")` convention used across callers so the
    error-marker format only needs to change in one place.
    """
    return bool(response) and response.startswith("[")


def is_available() -> bool:
    try:
        SESSION.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        return True
    except Exception:
        return False
