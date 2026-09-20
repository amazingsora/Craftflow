"""FastAPI 進入點 — logging 設定、16 個 router 掛載、啟動健檢、全域例外處理。

log 落檔在 repo-root 的 `data/logs/backend.log`（刻意在 backend/ 之外，避免 uvicorn --reload
的 watchfiles 每寫一行就洗版）。啟動時 `_startup_healthcheck` 檢查預期 workflow 在位。
路由清單見 doc/MODULE_MAP.md §2。
"""
import logging
import logging.handlers
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

# log 落檔放在 repo-root 的 data/logs（在 backend/ 之外），避免落在 uvicorn --reload
# 的監看樹內、每寫一行就觸發 watchfiles「change detected」洗版（reload 不會真的發生，
# 但 INFO log 會在排除規則前就印出）。
_LOG_DIR = Path(__file__).resolve().parent.parent / "data" / "logs"
_log_handlers = [logging.StreamHandler()]
try:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    _log_handlers.append(logging.handlers.RotatingFileHandler(
        _LOG_DIR / "backend.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"))
except Exception:
    pass  # 落檔失敗不影響啟動，至少保留 console
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
                    handlers=_log_handlers)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import API_PREFIX, APP_TITLE, APP_VERSION
from app.core.backup import backup_loop
from app.core.database import init_db
from app.api import projects, chapters, volumes, characters, illustrations, analysis, ai_text, ai_art, status, art_generate, factions, settings, art_styles, training, export, generation_history


def _startup_healthcheck():
    """啟動時檢查預期工作流檔在位，缺則明確 WARNING（避免功能靜默退化，如方案3 外擴）。"""
    from app.core.config import CUSTOM_WORKFLOWS_DIR
    log = logging.getLogger("startup")
    expected = ["canvas_expand_sdxl.json", "canvas_expand_flux.json"]
    missing = [f for f in expected if not (CUSTOM_WORKFLOWS_DIR / f).exists()]
    if missing:
        log.warning("[healthcheck] 預期工作流缺失於 %s：%s → 相關功能將靜默退化，請確認",
                    CUSTOM_WORKFLOWS_DIR, ", ".join(missing))
    else:
        log.info("[healthcheck] 預期工作流齊備（%d 檔）", len(expected))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _startup_healthcheck()
    import asyncio
    backup_task = asyncio.create_task(backup_loop())
    yield
    backup_task.cancel()


app = FastAPI(title=APP_TITLE, version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Phase 1: local only, tighten in Phase 4
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix=API_PREFIX)
app.include_router(volumes.router, prefix=API_PREFIX)
app.include_router(chapters.router, prefix=API_PREFIX)
app.include_router(characters.router, prefix=API_PREFIX)
app.include_router(illustrations.router, prefix=API_PREFIX)
app.include_router(analysis.router, prefix=API_PREFIX)
app.include_router(ai_text.router, prefix=API_PREFIX)
app.include_router(ai_art.router, prefix=API_PREFIX)
app.include_router(status.router, prefix=API_PREFIX)
app.include_router(art_generate.router, prefix=API_PREFIX)
app.include_router(factions.router, prefix=API_PREFIX)
app.include_router(settings.router, prefix=API_PREFIX)
app.include_router(art_styles.router, prefix=API_PREFIX)
app.include_router(training.router, prefix=API_PREFIX)
app.include_router(export.router, prefix=API_PREFIX)
app.include_router(generation_history.router, prefix=API_PREFIX)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}: {exc}"},
    )


@app.get("/")
def health_check():
    return {"status": "ok", "version": APP_VERSION, "docs": "/docs"}
