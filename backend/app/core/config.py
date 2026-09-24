# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
"""所有環境變數旋鈕的單一入口（讀專案根 .env） [FD-028]"""
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
# 允許跨來源呼叫 API 的前端位址（逗號分隔）；前端經 Vite proxy 走同源，不需要放寬
CORS_ORIGINS = [o.strip() for o in os.getenv(
    "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]
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

# [CN-001] VRAM Guardian：兩者放得下就不卸載，省模型重載 10~30s；COEXIST=false 退回舊行為
VRAM_COEXIST_ENABLED: bool = os.getenv("VRAM_COEXIST_ENABLED", "true").lower() == "true"
# [CN-002] 門檻 8→11：舊值只估 SDXL，實際常駐 10.2G → 溢位後 KSampler 2.4it/s 掉到 30s/it
COMFYUI_REQUIRED_VRAM_GB = float(os.getenv("COMFYUI_REQUIRED_VRAM_GB", "11"))  # SDXL + CN + CLIPVision + CLIP/VAE + LoRA patch
OLLAMA_REQUIRED_VRAM_GB = float(os.getenv("OLLAMA_REQUIRED_VRAM_GB", "7"))     # 7B Q4/Q8 vision/text
# [CN-003] 駐留時 free 下限 6→10：這是「增量需求」門檻（CN+IPA+CLIP+LoRA備份+activations）
COMFYUI_RESIDENT_MIN_FREE_GB = float(os.getenv("COMFYUI_RESIDENT_MIN_FREE_GB", "10"))

# [CN-004] 單次任務上限 300→1200s：逾時後 ComfyUI 仍會跑完存檔，白付 GPU 時間
COMFYUI_JOB_TIMEOUT_SEC = int(os.getenv("COMFYUI_JOB_TIMEOUT_SEC", "1200"))

# [CN-005] /free 是非同步排程，送出後須 poll 到 reserved 真的下降，否則量到的必是舊值
VRAM_FREE_WAIT_SEC: float = float(os.getenv("VRAM_FREE_WAIT_SEC", "5"))
VRAM_FREE_POLL_SEC: float = float(os.getenv("VRAM_FREE_POLL_SEC", "0.25"))
# true＝ComfyUI 沒讓出顯存就不轉移 focus 到 ollama（request_focus 回 False）
VRAM_STRICT_FREE: bool = os.getenv("VRAM_STRICT_FREE", "false").lower() == "true"
# 釋放判定的最低歸還量（小幅下降是量測雜訊，不算釋放）
VRAM_FREE_MIN_DROP_GB: float = float(os.getenv("VRAM_FREE_MIN_DROP_GB", "1.0"))
# reserved / total 超過此比例 ⇒ 顯卡已經塞滿、極可能正在用共享系統記憶體。
# 這個狀態**不會自己恢復**（被換出的頁不會自動搬回 VRAM），只能重啟 ComfyUI。
VRAM_STUCK_RATIO: float = float(os.getenv("VRAM_STUCK_RATIO", "0.92"))

# [CN-006] keep_alive 預設 0（用完即退）；-1 回到舊行為（不送欄位＝吃 Ollama 的 5 分鐘）
OLLAMA_KEEP_ALIVE_SEC: int = int(os.getenv("OLLAMA_KEEP_ALIVE_SEC", "0"))

# [CN-007] sysmem fallback 在 ComfyUI 端完全無聲，只能靠耗時警戒補 log。0=停用
COMFYUI_SLOW_JOB_WARN_SEC: int = int(os.getenv("COMFYUI_SLOW_JOB_WARN_SEC", "150"))

# [CN-008] 本組 .env 是全域基準線＋總開關，非唯一來源；PERSONAL_STYLE_ENABLED 不節制 yml
PERSONAL_STYLE_ENABLED: bool = os.getenv("PERSONAL_STYLE_ENABLED", "false").lower() == "true"
PERSONAL_STYLE_EXTRA_TAGS: str = os.getenv("PERSONAL_STYLE_EXTRA_TAGS", "")
PERSONAL_NEGATIVE_ENABLED: bool = os.getenv("PERSONAL_NEGATIVE_ENABLED", "false").lower() == "true"
PERSONAL_NEGATIVE: str = os.getenv("PERSONAL_NEGATIVE", "")
# [CN-009] 畫風 tags 加權係數：!=1.0 時包成 (tag:w) 並前置到 identity；1.0=末端 append
PERSONAL_STYLE_WEIGHT: float = float(os.getenv("PERSONAL_STYLE_WEIGHT", "1.0"))

# [CN-115] 分家族個人標籤 PERSONAL_<STYLE|NEGATIVE>_EXTRA_<家族大寫>：疊加語義、留空＝關閉。
# 呼叫時才讀（家族是動態值，測試可用 setenv 隔離）
PERSONAL_KIND_STYLE = "STYLE"
PERSONAL_KIND_NEGATIVE = "NEGATIVE"
# 測試隔離用（tests/conftest.py 依此清掉使用者 .env 的家族個人標籤）
PERSONAL_FAMILY_KEY_PREFIXES = tuple(f"PERSONAL_{k}_EXTRA_" for k in (PERSONAL_KIND_STYLE, PERSONAL_KIND_NEGATIVE))


def personal_family_extra(kind: str, family: str) -> str:
    """讀 `.env` 的 PERSONAL_<kind>_EXTRA_<FAMILY>；未設或家族為空 → ""。"""
    if not family:
        return ""
    return (os.getenv(f"PERSONAL_{kind}_EXTRA_{family.upper()}") or "").strip()

# [CN-010] prompt 擴寫 stage2，預設關閉（需先手動 A/B 驗證），FLUX 不套用
PROMPT_UPSAMPLE_ENABLED: bool = os.getenv("PROMPT_UPSAMPLE_ENABLED", "false").lower() == "true"
PROMPT_UPSAMPLE_MODEL: str = os.getenv("PROMPT_UPSAMPLE_MODEL", "")  # 空 = 沿用 compile() 的 text model
# 擴寫後 body tag 上限：超限從擴寫尾端砍、原始 tag 保留；0＝停用
PROMPT_MAX_BODY_TAGS: int = int(os.getenv("PROMPT_MAX_BODY_TAGS", "0"))

# [CN-011] 編譯快取：命中則完全不呼叫 Ollama，省掉整段 11GB 卸載/重載。預設 0=停用
PROMPT_CACHE_TTL_SEC: int = int(os.getenv("PROMPT_CACHE_TTL_SEC", "0"))

# ── 內容安全（NSFW 護欄，見 services/ai/prompt_engine/content_guard.py）────────────
# true（預設）＝一般情境剝除露骨 tag、負向補 nsfw；false＝成人內容不過濾（debug 用）。
# 未成年情境（角色 <18 或正向含 child 等標記）不受此旋鈕影響，永遠強制過濾。
NSFW_GUARD_ENABLED: bool = os.getenv("NSFW_GUARD_ENABLED", "true").lower() == "true"
# true＝回傳給前端的 PNG 去除內嵌 prompt／workflow（分享圖片不外洩）；生成資訊仍存在 DB
PNG_STRIP_METADATA: bool = os.getenv("PNG_STRIP_METADATA", "true").lower() == "true"

# ── 生圖微調旋鈕 ──────────────────────────────────────────────
# flat_draft(線稿/平塗概念圖)當 IPA 參考會把成像拉平 → 自動把 IPA 權重乘此係數(下限0.1)。1.0=不降。
IPA_FLAT_DRAFT_SCALE: float = float(os.getenv("IPA_FLAT_DRAFT_SCALE", "0.5"))
