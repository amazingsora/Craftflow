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

## Doc Update Rules

### 每日開發記錄（`doc/YYYY-MM-DD_開發記錄.md`）
- 當天所有工作、技術討論、決策、待確認事項，**全部只寫當天日期的檔案**
- 跨日開發：新的一天開新檔案，開頭用「承接 YYYY-MM-DD」說明脈絡，不回頭修改舊檔
- 會話開始時若有未完成的工作，先讀最新一筆開發記錄確認當前狀態

### 功能規劃文件（`doc/YYYY-MM-DD_*規劃.md`）
- 只更新 **進度 checkbox**（`🔲` → `✅`）和**狀態欄**
- 技術細節、討論內容、調查結果一律寫進當日開發記錄，不塞入規劃文件
- 規劃文件當 spec 和 checklist 用，保持精簡

### 禁止事項
- 不在舊日期的檔案裡補寫新內容
- 不把當日討論的技術細節分散在多個文件
