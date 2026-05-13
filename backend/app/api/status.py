"""
GET /api/v1/status  — overall system health check
GET /api/v1/status/ollama   — Ollama availability + installed models
GET /api/v1/status/comfyui  — ComfyUI availability
"""
from __future__ import annotations

import requests
from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import OLLAMA_BASE, COMFYUI_BASE
from app.core.database import engine

router = APIRouter(prefix="/status", tags=["status"])


@router.get("/")
def system_status():
    ollama = _check_ollama()
    comfyui = _check_comfyui()
    db = _check_db()

    overall = "ok" if db["ok"] else "degraded"
    if not ollama["available"]:
        overall = "degraded"

    return {
        "status": overall,
        "services": {
            "database": db,
            "ollama": ollama,
            "comfyui": comfyui,
        },
        "hints": _hints(ollama, comfyui, db),
    }


@router.get("/ollama")
def ollama_status():
    return _check_ollama()


@router.get("/comfyui")
def comfyui_status():
    return _check_comfyui()


# ── helpers ───────────────────────────────────────────────────────────────────

def _check_ollama() -> dict:
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        return {"available": True, "models": models}
    except requests.exceptions.ConnectionError:
        return {"available": False, "models": [], "error": "Ollama is not running. Run: ollama serve"}
    except Exception as e:
        return {"available": False, "models": [], "error": str(e)}


def _check_comfyui() -> dict:
    try:
        r = requests.get(f"{COMFYUI_BASE}/system_stats", timeout=3)
        r.raise_for_status()
        return {"available": True}
    except requests.exceptions.ConnectionError:
        return {"available": False, "error": "ComfyUI is not running. Run: run_nvidia_gpu.bat"}
    except Exception as e:
        return {"available": False, "error": str(e)}


def _check_db() -> dict:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _hints(ollama: dict, comfyui: dict, db: dict) -> list[str]:
    hints = []
    if not ollama["available"]:
        hints.append("Ollama 未啟動，AI 文字和視覺功能無法使用。請執行 `ollama serve`。")
    elif not ollama["models"]:
        hints.append("Ollama 已啟動但沒有模型。請執行 `ollama pull qwen2-vl`。")
    if not comfyui["available"]:
        hints.append("ComfyUI 未啟動，風格強化與線稿化功能無法使用。")
    if not db["ok"]:
        hints.append("資料庫連線失敗，請確認 craftflow.db 存在且無損。")
    return hints
