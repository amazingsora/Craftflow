# Craftflow — Claude Instructions

## Architecture Mandates
- **Local-First:** AI on Ollama + ComfyUI；無雲端 API（除非明確指示）。
- **Human-in-the-Loop:** 絕不覆蓋原始創作內容；產出只進分析報告。
- **Docker → Host:** Ollama/ComfyUI 一律用 `host.docker.internal`（非 `localhost`）。

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
/backend/app/     → api/ models/ schemas/ services/ai/ core/
/frontend/src/    → components/ (ComposeTab, GenerateTab, ProcessTab)
/tools/Craftflow/ → legacy CLI (migration target → services/ai/)
/doc/             → dev logs, product plan
```

## Coding Rules
1. **Surgical updates** — 只改必要處，無關的不重構。
2. **Progressive feedback** — 慢速 AI 任務需後端狀態 + 前端進度 UI。
3. **Resilient errors** — Ollama/ComfyUI 失敗不可讓 app crash。
4. 改前先讀；動手前先說明 *why*。

## Workflow
Research → Propose → Explain risk → Apply

## Doc Rules
- **每日開發記錄** `doc/YYYY-MM-DD_開發記錄.md`：當天所有工作/討論/決策/待辦只寫當天檔；跨日開新檔，開頭「承接 YYYY-MM-DD」，不改舊檔；會話開始先讀最新一筆確認狀態。
- **規劃文件** `doc/YYYY-MM-DD_*規劃.md`：只更新進度 checkbox（🔲→✅）與狀態欄；當 spec/checklist 用，保持精簡。
- **禁止**：在舊日期檔補寫新內容；把技術細節分散到多個檔案。
