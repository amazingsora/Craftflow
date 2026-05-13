"""
Low-level Ollama HTTP client.
Wraps both text generation and vision (image) analysis.
All errors are caught and returned as strings rather than raised,
so callers can decide how to surface them to the user.
"""
from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Optional

import requests

from app.core.config import OLLAMA_BASE, DEFAULT_TEXT_MODEL, DEFAULT_VISION_MODEL

TIMEOUT_TEXT = 300
TIMEOUT_VISION = 300


def generate(
    prompt: str,
    model: str = DEFAULT_TEXT_MODEL,
    options: Optional[dict] = None,
) -> str:
    """
    Text generation via Ollama /api/generate.

    options examples:
      {"temperature": 0.3, "num_predict": 200}  — stable tag output
      {"temperature": 0.8}                       — creative writing
    """
    payload: dict = {"model": model, "prompt": prompt, "stream": False}
    if options:
        payload["options"] = options
    try:
        r = requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json=payload,
            timeout=TIMEOUT_TEXT,
        )
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return f"[Ollama unavailable at {OLLAMA_BASE}: run `ollama serve` and ensure OLLAMA_HOST=0.0.0.0]"
    except Exception as e:
        return f"[Ollama error at {OLLAMA_BASE}: {e}]"


def analyze_image(image_path: str, prompt: str, model: str = DEFAULT_VISION_MODEL) -> str:
    try:
        image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        r = requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json={"model": model, "prompt": prompt, "images": [image_b64], "stream": False},
            timeout=TIMEOUT_VISION,
        )
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return f"[Vision unavailable at {OLLAMA_BASE}: run `ollama serve` and ensure OLLAMA_HOST=0.0.0.0]"
    except Exception as e:
        return f"[Vision error at {OLLAMA_BASE}: {e}]"


def analyze_image_bytes(image_bytes: bytes, prompt: str, model: str = DEFAULT_VISION_MODEL) -> str:
    start = time.time()
    try:
        image_b64 = base64.b64encode(image_bytes).decode()
        r = requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json={"model": model, "prompt": prompt, "images": [image_b64], "stream": False},
            timeout=TIMEOUT_VISION,
        )
        print(f"DEBUG: Ollama HTTP POST took {time.time() - start:.2f}s", flush=True)
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return f"[Vision unavailable at {OLLAMA_BASE}: run `ollama serve` and ensure OLLAMA_HOST=0.0.0.0]"
    except Exception as e:
        return f"[Vision error at {OLLAMA_BASE}: {e}]"


def is_available() -> bool:
    try:
        requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        return True
    except Exception:
        return False
