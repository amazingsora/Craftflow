import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "craftflow.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

API_PREFIX = "/api/v1"
APP_TITLE = "Craftflow API"
APP_VERSION = "0.1.0"

# AI 服務設定（由環境變數覆寫，預設值適用於 Docker 環境）
OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://host.docker.internal:11434")
COMFYUI_BASE = os.getenv("COMFYUI_BASE", "http://host.docker.internal:8188")
COMFYUI_CHECKPOINT = os.getenv("COMFYUI_CHECKPOINT", "")  # overrides ckpt_name in all workflows
DEFAULT_TEXT_MODEL = os.getenv("TEXT_MODEL", "dolphin-llama3")
DEFAULT_VISION_MODEL = os.getenv("VISION_MODEL", "qwen2.5vl:7b")
