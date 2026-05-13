# Craftflow — Claude Instructions

## Architecture Mandates
- **Local-First:** AI runs on Ollama + ComfyUI. No cloud API unless explicitly told.
- **Human-in-the-Loop:** Never overwrite original creative content. Output goes to analysis reports only.
- **Docker → Host:** Always use `host.docker.internal` (not `localhost`) for Ollama/ComfyUI.

## Stack
| Layer | Tech |
|---|---|
| Backend | FastAPI · SQLAlchemy 2.0 · Pydantic v2 · SQLite |
| Frontend | React 18 · Vite · Vanilla CSS |
| LLM | `dolphin-llama3` (text/translate) · `qwen2.5vl:7b` (vision) |
| Image | ComfyUI @ `host.docker.internal:8188` |
| Ollama | `host.docker.internal:11434` |

## Layout
```
/backend/app/   → api/ models/ schemas/ services/ai/ core/
/frontend/src/  → components/ (ComposeTab, GenerateTab, ProcessTab)
/tools/Craftflow/ → legacy CLI (migration target → services/ai/)
/doc/           → dev logs, product plan
```

## Coding Rules
1. **Surgical updates** — change only what's needed; no unrelated refactors.
2. **Progressive feedback** — slow AI tasks must have backend status + frontend progress UI.
3. **Resilient errors** — Ollama/ComfyUI failures must not crash the app.
4. Read before editing. Explain *why* before changing.

## Workflow
Research → Propose → Explain risk → Apply
