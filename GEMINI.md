# Craftflow — Gemini Instructions

## Architecture Mandates
- **Local-First:** AI runs on Ollama + ComfyUI. No cloud API unless explicitly told.
- **Human-in-the-Loop:** Never overwrite original creative content. AI output goes to analysis reports / separate fields only.
- **Docker → Host:** Use `host.docker.internal` from containers; `localhost` when running Python directly.

## Stack
| Layer | Tech |
|---|---|
| Backend | FastAPI · SQLAlchemy 2.0 · Pydantic v2 · SQLite · Python 3.11 |
| Frontend | React 18 · Vite 5 · Vanilla CSS-in-JS |
| LLM | `dolphin-llama3` (text/translate) · `qwen2.5vl:7b` (vision, globally switchable) |
| Image | ComfyUI @ `host.docker.internal:8188` (SDXL · CN Union ProMax · IPA) |
| Ollama | `host.docker.internal:11434` |
| LoRA training | kohya_ss (subprocess) |

## Architecture Map
```
backend/main.py   16 routers, prefix /api/v1
backend/app/
  api/       routes: projects volumes chapters characters factions illustrations
             art_styles art_generate(3075 lines, A1 split planned) ai_art ai_text
             analysis training export generation_history settings status
  services/  export_service comfyui_client
    ai/      art_service character_service consistency_service image_edit_service
             generation_jobs(async img job) generation_recorder(seed/params→DB)
             vram_manager(conditional unload) ollama_client prompt_engine/ lora_trainer/
  models/ schemas/  ORM+Pydantic (chapter_revision=snapshots; generation_history=reproducibility)
  core/      config(.env/PERSONAL_STYLE) database backup(periodic VACUUM INTO)
             state(runtime globals, reset on restart)
frontend/src/
  App.jsx        sidebar shell (196px) + service status + bottom history + settings modal
  components/    ProcessTab GenerateTab ComposeTab NovelTab CharacterTab(2431 lines, A2)
                 ArtStyleTab SettingsTab TrainingTab
  index.css      dual-theme tokens: :root=light default, [data-theme="dark"]; localStorage craftflow_theme
data/custom_workflows/  ComfyUI workflows (API format required; Standard_V35 / _EyeFix=eye-detail A/B)
tools/Craftflow/        legacy CLI (migration target → services/ai/)
doc/                    daily dev logs · planning docs
```

## Quick Mechanics
- Art style = art_styles DB (LoRA+tags); `.env` PERSONAL_STYLE_* hardcodes personal style tags (applied only when the character style has empty extra_tags)
- Global checkpoint/workflow/LoRA/model switches live in core/state (runtime only, restart → .env)
- Generation: sync `/art/generate` + async `/art/generate-async` (job+polling); params recorded in generation_history

## Coding Rules
1. **Surgical updates** — change only what's needed; no unrelated refactors.
2. **Progressive feedback** — slow AI tasks must have backend status + frontend progress UI.
3. **Resilient errors** — Ollama/ComfyUI failures must not crash the app.
4. Read before editing. Explain *why* before changing.
5. **Permission First** — No code changes without explicit directive.

## Workflow
Research → Propose → Explain risk → Apply

## Sandbox / Environment Pitfalls (learned the hard way)
- repo=LF, Windows working tree=CRLF: sandbox git status shows ALL files as modified (false); normalize files with `sed 's/\r$//'` before staging or you commit a full line-ending rewrite
- File-tool writes to the mounted folder may TRUNCATE file tails: write important files via shell and verify the tail afterwards (proven 06-10/06-12)
- Sandbox cannot write SQLite directly (no lock support on mount); provide commands for the user to run locally
- `vite.config.js.timestamp-*.mjs` are Vite temp files, gitignored — never commit

## Doc Rules
- **Daily dev log** `doc/YYYY-MM-DD_開發記錄.md`: all work/decisions/todos of the day go ONLY in that day's file; new day = new file starting with「承接 YYYY-MM-DD」; never edit old files; start each session by reading the latest log.
- **Planning docs** `doc/YYYY-MM-DD_*規劃.md`: only update progress checkboxes (🔲→✅) and status columns; keep terse, used as spec/checklist.
- **Forbidden**: backfilling old-dated files; scattering technical details across multiple files.
