import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/

# 本機執行時自動載入 .env（Docker 執行時 env 已由 docker-compose 注入，此行無害）
load_dotenv(BASE_DIR.parent / ".env")
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "craftflow.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

API_PREFIX = "/api/v1"
APP_TITLE = "Craftflow API"
APP_VERSION = "0.1.0"

# AI 服務設定（由環境變數覆寫，預設值適用於本機直跑環境）
# Docker 環境需在 .env 明確設定 host.docker.internal
OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://localhost:11434")
COMFYUI_BASE = os.getenv("COMFYUI_BASE", "http://localhost:8188")
COMFYUI_CHECKPOINT = os.getenv("COMFYUI_CHECKPOINT", "")  # overrides ckpt_name in all workflows
# 啟動預設模型（可在前端「設定」頁面即時切換，無需重啟或修改 .env）
DEFAULT_TEXT_MODEL = os.getenv("TEXT_MODEL", "llama3.2:3b")
DEFAULT_VISION_MODEL = os.getenv("VISION_MODEL", "moondream")

# ── LoRA 訓練設定 ─────────────────────────────────────────────────
TRAINING_RUNNER_MODE = os.getenv("TRAINING_RUNNER_MODE", "local")  # "local" | "remote"
KOHYA_PATH = Path(os.getenv("KOHYA_PATH", r"C:\kohya_ss"))
# Python 執行檔：預設用系統 python（已有 PyTorch），可改為 kohya 內部 venv
KOHYA_PYTHON = Path(os.getenv("KOHYA_PYTHON", "python"))
TRAINING_IMAGES_DIR = Path(os.getenv("TRAINING_IMAGES_DIR", str(BASE_DIR.parent / "data" / "training_images")))
COMFYUI_LORAS_DIR = Path(os.getenv("COMFYUI_LORAS_DIR", r"C:\ComfyUI\models\loras"))

CUSTOM_WORKFLOWS_DIR = Path(os.getenv("CUSTOM_WORKFLOWS_DIR", str(BASE_DIR.parent / "data" / "custom_workflows")))

# ── 資料安全（章節版本快照 + DB 備份）──────────────────────────────────────
CHAPTER_REVISIONS_KEEP = int(os.getenv("CHAPTER_REVISIONS_KEEP", "20"))  # 每章保留快照數
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", str(BASE_DIR.parent / "data" / "backups")))
BACKUP_KEEP = int(os.getenv("BACKUP_KEEP", "7"))                         # 保留備份份數
BACKUP_INTERVAL_HOURS = float(os.getenv("BACKUP_INTERVAL_HOURS", "24"))  # 0 = 停用定時備份

# ── VRAM Guardian（條件式卸載）────────────────────────────────────────────
# 切換 Ollama/ComfyUI 前先查實際 VRAM；兩者放得下就不卸載（省去模型重載 10~30s）。
# VRAM_COEXIST_ENABLED=false 退回舊行為（切換時一律卸載另一方）。
VRAM_COEXIST_ENABLED: bool = os.getenv("VRAM_COEXIST_ENABLED", "true").lower() == "true"
COMFYUI_REQUIRED_VRAM_GB = float(os.getenv("COMFYUI_REQUIRED_VRAM_GB", "8"))   # SDXL fp16 + CLIP/VAE
OLLAMA_REQUIRED_VRAM_GB = float(os.getenv("OLLAMA_REQUIRED_VRAM_GB", "7"))     # 7B Q4/Q8 vision/text

# ── Personal Style Preset（個人風格預設，.env 啟用 / git 預設關閉）────────────
# PERSONAL_STYLE_ENABLED=true  → 角色生圖時附加 PERSONAL_STYLE_EXTRA_TAGS
# PERSONAL_NEGATIVE_ENABLED=true → 取代預設負向提示詞（art_style 未設定 negative 時）
PERSONAL_STYLE_ENABLED: bool = os.getenv("PERSONAL_STYLE_ENABLED", "false").lower() == "true"
PERSONAL_STYLE_EXTRA_TAGS: str = os.getenv("PERSONAL_STYLE_EXTRA_TAGS", "")
PERSONAL_NEGATIVE_ENABLED: bool = os.getenv("PERSONAL_NEGATIVE_ENABLED", "false").lower() == "true"
PERSONAL_NEGATIVE: str = os.getenv("PERSONAL_NEGATIVE", "")
# 畫風 tags 加權係數（G1-3）：!=1.0 時，角色生圖把 style_extra 每個 tag 包成 (tag:weight)
# 並前置到 identity 區塊（與角色身分同級優先），讓畫風由 prompt 承擔、CN 可安心降權。
# 1.0（預設）= 維持現行末端 append、不加權，git 預設零行為變更。
PERSONAL_STYLE_WEIGHT: float = float(os.getenv("PERSONAL_STYLE_WEIGHT", "1.0"))

# ── Prompt 擴寫 stage2（G1-2，.env 啟用 / git 預設關閉）────────────────────────
# PROMPT_UPSAMPLE_ENABLED=true → compile() 翻譯+sanitize 後，多一次 LLM 呼叫把稀疏
#   tags 擴寫成更密的 danbooru tags（V37 booru upsampler 規則）。additive 合併、原始
#   tags 為 identity 錨不可被覆蓋；FLUX（自然語言）不套用。
#   ⚠️ 預設關閉——需先手動 A/B 驗證(G1-1)再開，避免未驗證污染線上出圖。
PROMPT_UPSAMPLE_ENABLED: bool = os.getenv("PROMPT_UPSAMPLE_ENABLED", "false").lower() == "true"
PROMPT_UPSAMPLE_MODEL: str = os.getenv("PROMPT_UPSAMPLE_MODEL", "")  # 空 = 沿用 compile() 的 text model
# 擴寫後 body tag 數上限（token 預算，G1-4）：擴寫會膨脹 tags，超限時從擴寫尾端砍，
# 受保護的原始翻譯 tags（identity/subject）一律保留。0（預設）= 停用。
PROMPT_MAX_BODY_TAGS: int = int(os.getenv("PROMPT_MAX_BODY_TAGS", "0"))

# ── 生圖微調旋鈕 ──────────────────────────────────────────────
# flat_draft(線稿/平塗概念圖)當 IPA 參考會把成像拉平 → 自動把 IPA 權重乘此係數(下限0.1)。1.0=不降。
IPA_FLAT_DRAFT_SCALE: float = float(os.getenv("IPA_FLAT_DRAFT_SCALE", "0.5"))
