from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import API_PREFIX, APP_TITLE, APP_VERSION
from app.core.database import init_db
from app.api import projects, chapters, characters, illustrations, analysis, ai_text, ai_art, status, art_generate, factions, settings, art_styles


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title=APP_TITLE, version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Phase 1: local only, tighten in Phase 4
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix=API_PREFIX)
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


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}: {exc}"},
    )


@app.get("/")
def health_check():
    return {"status": "ok", "version": APP_VERSION, "docs": "/docs"}
