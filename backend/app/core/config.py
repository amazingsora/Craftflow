# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
"""所有環境變數旋鈕的單一入口（讀專案根 .env）。

分區：路徑 / AI 服務位址 / LoRA 訓練 / 資料安全（快照·備份）/ VRAM Guardian /
Personal Style / Prompt 擴寫 / 生圖微調。

慣例：
  - 每個旋鈕都要有預設值，缺 .env 也能啟動。
  - 新增旋鈕時預設值必須是「零行為變更」，需要實驗的功能預設關閉。
  - 執行期可切換的設定（checkpoint/workflow/模型）不在這裡，在 core/state.py。
"""
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
# true = ComfyUI 沒讓出顯存就**不轉移 focus 到 ollama**（request_focus 回 False）。
# 預設 false：現行呼叫端都忽略回傳值，維持零行為變更，先讓 log 累積實證再決定開不開。
VRAM_STRICT_FREE: bool = os.getenv("VRAM_STRICT_FREE", "false").lower() == "true"
# 2026-09-21 訂正：舊版只要 reserved 有「下降」就算成功，實測 15.2G 只還 0.1G
# 也被判定為 True —— 那不是釋放，是量測雜訊。改為要求最低歸還量。
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

# [CN-010] prompt 擴寫 stage2，預設關閉（需先手動 A/B 驗證），FLUX 不套用
PROMPT_UPSAMPLE_ENABLED: bool = os.getenv("PROMPT_UPSAMPLE_ENABLED", "false").lower() == "true"
PROMPT_UPSAMPLE_MODEL: str = os.getenv("PROMPT_UPSAMPLE_MODEL", "")  # 空 = 沿用 compile() 的 text model
# 擴寫後 body tag 數上限（token 預算，G1-4）：擴寫會膨脹 tags，超限時從擴寫尾端砍，
# 受保護的原始翻譯 tags（identity/subject）一律保留。0（預設）= 停用。
PROMPT_MAX_BODY_TAGS: int = int(os.getenv("PROMPT_MAX_BODY_TAGS", "0"))

# [CN-011] 編譯快取：命中則完全不呼叫 Ollama，省掉整段 11GB 卸載/重載。預設 0=停用
PROMPT_CACHE_TTL_SEC: int = int(os.getenv("PROMPT_CACHE_TTL_SEC", "0"))

# ── 生圖微調旋鈕 ──────────────────────────────────────────────
# flat_draft(線稿/平塗概念圖)當 IPA 參考會把成像拉平 → 自動把 IPA 權重乘此係數(下限0.1)。1.0=不降。
IPA_FLAT_DRAFT_SCALE: float = float(os.getenv("IPA_FLAT_DRAFT_SCALE", "0.5"))
