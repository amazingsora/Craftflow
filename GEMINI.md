# Craftflow — Gemini Instructions

Local-first private tool for novel writing + AI illustration (FastAPI + React + Ollama + ComfyUI, all on the local machine). AI only suggests; the creator decides.

> `CLAUDE.md` (Claude) / `AGENTS.md` (Codex) are the same rule set in other versions; on conflict, `AGENTS.md` + `CLAUDE.md` win.
> This file holds **durable** rules and pitfalls only. For "where are we today" → `python tools/session_status.py`, the latest `doc/YYYY-MM-DD_開發記錄.md`, and `doc/BACKLOG.md`.

## 0. Where to read first (save tokens)

1. `python tools/session_status.py` — git / frontend build status, open-item counts per BACKLOG area, and the latest log's「接續摘要」in one call.
2. Read single sections only when needed: `--section <heading text>` (latest log), `--section <text> --file doc/BACKLOG.md`, `--area <area heading text>`. **Never read whole logs, `ls doc/` and guess, or browse `doc/archive/`** (read the monthly 摘要 first).
3. Before touching a module: `doc/MODULE_MAP.md` → `doc/reference/CODE_NOTES.md` (`# [CN-xxx]` root causes) → source.

| Need | File |
|---|---|
| Which file / generation pipeline | `doc/MODULE_MAP.md` |
| Todo list (single source of truth) | `doc/BACKLOG.md` |
| Why code is written this way | `doc/reference/CODE_NOTES.md` |
| Full function behaviour | `doc/reference/FUNCTION_DOCS.md` (`[FD-xxx]`) |
| VRAM / coexistence / resolution | `doc/VRAM分析報告.md` |
| Doc navigation / past decisions | `doc/INDEX.md`, `doc/archive/YYYY-MM_摘要.md` |

## 1. Multi-AI collaboration (read first)

- Planning goes through root **`AGENT_SYNC.md`**: Claude → Codex → **Gemini** → Claude integrates → user decides (§2.5) → Claude executes. Full rules: `AGENT_SYNC.md` §0.
- **Gemini is a planner**: write ONLY the `§2.3 Gemini 規劃` block. **No changes to code, config or docs**, no edits to other agents' blocks.
- Express changes as "`file:line` → what to change and why", with evidence (code lines, log lines). Rebuttals go in your own block.
- End your block with `<!-- HANDOFF: Gemini DONE @ YYYY-MM-DD HH:MM -->`. No HANDOFF line from the previous agent = not finished yet.
- Write in Traditional Chinese (technical terms in English), matching the other blocks.

## 2. User's hard requirements

- **Do not inspect the DB** (`backend/craftflow.db`, not even read-only or via SQL). Provide the SQL / query idea; the user runs it and reports back.
- Conclusion first; object directly when the direction is wrong, with evidence. No flattery.
- If one real test disproves a conclusion, stop and re-verify the premise instead of stacking inferences.
- Ask when requirements are unclear; never invent classes/functions.

## 3. Architecture mandates

- **Minimal architecture, general-purpose tool** — the top criterion. Converge shared paths; no per-workflow / per-model special branches (prompt recipes are keyed by **base-model family**, never by workflow filename).
- **Local-First**: Ollama + ComfyUI only; no cloud API unless told.
- **Human-in-the-Loop**: never overwrite original creative content; AI output goes to reports / separate fields.
- **Surgical updates**, **Progressive feedback** (slow AI tasks need backend status + frontend progress), **Resilient errors** (Ollama/ComfyUI failures must not crash the app, and error strings must never be shown as results — CN-123).
- **Permission First**: no code changes without explicit directive.

## 4. Runtime environment

| Item | Value |
|---|---|
| Hardware | Windows 11 · RTX 5070 Ti 16GB |
| Backend | FastAPI · SQLAlchemy 2.0 · Pydantic v2 · SQLite · Python 3.11; `start.bat` → uvicorn `127.0.0.1:8000` |
| Frontend | React 18 · Vite 5 · CSS-in-JS; dev `:3000`. Frontend changes require `cd frontend && npm run build` (stale bundle misleads tests) |
| Ollama | `:11434`; text/vision models switched in Settings UI, persisted in `data/runtime_state.json` |
| ComfyUI | `F:\wk\ComfyUI_portable`, `:8188`, launched by `run_amazingSP_v3.bat` (no FP8 — v2's FP8 flags degrade quality) |
| Log | `data/logs/backend.log` (not `backend/logs/`) |
| Workflows | **`data/custom_workflows/`** is what runtime loads (API format; retired files in `history/`). `ComfyUI/user/default/workflows/craftflow/` holds same-name **shadow copies** — editing them does nothing |
| Tests | `cd backend && pytest` |

## 5. The two base-model families (most bugs sit on this boundary)

| | illustrious (SDXL line) | anima |
|---|---|---|
| Loader | `CheckpointLoaderSimple` | `UNETLoader` + `CLIPLoader` (Qwen encoder) |
| Model dir | `models/checkpoints/` | `models/diffusion_models/` |
| Active workflows | `Standard_V38` / `Advanced_V38` (V39 in progress) | `AnimaStandardV9_*` (`miaomiaoHarem` is primary) |
| Structure control | CN Union ProMax + IPA | no CN/IPA → LLLite → img2img fallback chain (CN-125) |
| FaceDetailer | built into workflow | injected by backend (CN-120) |

- `/settings/checkpoints` only lists `CheckpointLoaderSimple` options → Anima UNets never appear; Anima always uses Custom Workflow mode.
- Any code that acts only when it finds `CheckpointLoaderSimple` silently skips on Anima (LoRA injection did, CN-124). Node surgery must handle both loaders.
- LoRA architecture must match the base model (SDXL/Illustrious LoRA on Anima = no effect).
- `checkpoint_styles.yml` matches by **substring, first hit wins**: `animagineXL` must precede the catch-all `anima`; new checkpoints go in both `checkpoints:` and `families:`.
- Anima tag order: series/artist tags after `1girl`, before general tags; Aesthetic variants ban `score_*` in both prompts.
- **Editing prompt text inside a workflow JSON has no effect in production** (`wf_node_ops._inject_prompts` overwrites it) → change `prompt_engine/styles.py` templates or `prompt_profiles.yml`.
- Capability gating is **two layers**: frontend (`CharacterDetailView.jsx` `cnUsable` / `ipaSupported`) + API (`api/art_generate.py`). A fallback added to only one layer is dead code.

## 6. Zero-code config points (prefer these over code)

| Task | Where |
|---|---|
| Which family a checkpoint belongs to | `backend/checkpoint_styles.yml` (see ordering rule above) |
| Prompt recipe per family | `backend/prompt_profiles.yml` `families:` (new/renamed workflows need no registration); one-off experiments via art_style (DB) |
| Generation knobs (VRAM thresholds, timeouts, toggles) | root `.env`; definitions/defaults only in `core/config.py` |
| Personal negatives (e.g. halo) | `.env` `PERSONAL_NEGATIVE_EXTRA_<FAMILY>` (FAMILY = PromptStyle upper; appended). CN-115 |
| Custom series/artist tag dropdown | `data/custom_tags.json` (format: `custom_tags.example.json`; hot reload). CN-122 |
| Appearance-age / body cards | `backend/appearance_cards.yml` `cards:` / `body_groups:` (shared by both families; Danbooru tags only, one core tag per card, no weights; hot reload). CN-129 / CN-130 |
| Per-family generation strategy | `services/ai/gen_profile.py` `GEN_PROFILE` |

## 7. Debugging rules

1. **Confirm what runtime actually loaded before analysing.** Check `data/logs/backend.log` tags: `[wf-load]`, `[capability]`, `[lllite]` / `[img2img]` / `[lora]` / `[face-detailer]`, `[nsfw-guard]`, `[vision-cache]`. Verify any remembered path / line / setting against the current code.
2. **Look for absent evidence**: zero log hits or a missing row in the UI timing table = the path never ran. Don't tune dead code.
3. Whether a prompt used the family recipe: `generation_history.params.prompt_profile` (give the SQL to the user).
4. Vision extraction odd / vision prompt change ineffective: `backend/data/vision_cache.json` key = `mode|model|image hash`, **excludes the prompt** → clear cache + restart backend.
5. Vision model returns empty / very slow: log `RAW(len=…)` first; thinking-type VL models may ignore `think:false` and burn `num_predict`. Use non-thinking models for structured extraction.
6. Compare old code with `git show HEAD:<path>`. `generation_history.created_at` is UTC; files in `backend/uploads/` use CST (+8h).

## 8. Coding checkpoints (include in plans)

1. Anything newly *executed* must be *executed* by a test (an f-string double-brace bug once shipped as a 500).
2. Workflow params may be **node references** (one param node feeds KSampler and metadata) → write upstream via `wf_node_ops._set_node_input`.
3. List all callers before changing a shared function; watch the illustrious path.
4. Prompt engineering: `(text)` is weight syntax in `CLIPTextEncode` — never use parentheses as annotations; never list banned words in LLM templates (it induces them) — use positive wording with no literal (or substring) occurrence; use real Danbooru tags (plural `red eyes`), and cover singular/plural in cleanup regexes; when a cleaner fixes a bad format, check whether our own code produces it.

## 9. Testing rules

- Record the **pre-existing failure set** before a change; after the change the set must be identical.
- The illustrious path lock in `tests/test_anima_family.py` and `tests/golden/` snapshots: failure = contaminated baseline path → fix the change, **never edit assertions to pass**.
- Tests for registry-style config must **enumerate the real source** (files on disk), not hard-coded key lists; every new guard needs a **negative control** (restore the defect, confirm red).
- "Skip if file missing" tests can be silently disabled for months; investigate changes in the skipped count.
- Mock targets must follow the implementation (`requests.get` → `SESSION.get` once left tests idle).
- `conftest.py` isolates the local `.env`; tests must not depend on personal settings.

## 10. Environment pitfalls (proven)

- File-tool writes to the mounted folder may **truncate file tails**; write important files via shell and verify line count + tail. `py_compile` misses truncation → use `ast.parse` + compare function/class name sets.
- repo = LF, Windows tree = CRLF → preserve each file's original line endings.
- Sandbox cannot write SQLite or run git writes (leaves undeletable `.git/index.lock`) → give commands for the user to run locally.
- `.bat` files must be pure ASCII (CJK under `chcp 65001` shifts cmd's read offset); never pass `*` globs to Python CLIs from `.bat` (they get expanded).
- ComfyUI shares a pyenv 3.11.9 site-packages with sd-scripts (torch nightly cu132): **never `pip install -r requirements.txt`**, only `--no-deps` targeted upgrades. Check the installed version's `--help` before relying on a CLI flag.
- Never commit `vite.config.js.timestamp-*.mjs`.

## 11. Privacy & version control

- `amazingsora/Craftflow` is a **public repo** (only `main` on remote).
- Not in git: `.env`, `doc/` (purged from history, local only), `data/custom_tags.json`, logs/caches/outputs.
- Personal style tags / negatives live only in `.env` or `data/custom_tags.json` — **never in yml, tests or `.env.example`**.
- Services bind `127.0.0.1`; CORS from `config.CORS_ORIGINS`; output PNG metadata stripped by default (`PNG_STRIP_METADATA`).

## 12. Content guard

- Single rule source: `services/ai/prompt_engine/content_guard.py` (CN-118). `.env` `NSFW_GUARD_ENABLED` covers adult content only; **minor context is always enforced, no switch**.
- Minor appearance cards (child / teen) may only be added after the guard is restored (BACKLOG P-09).

## 13. Code quality

- Comments ≤ 3 lines; **no development history in code** (dates, SYNC/A3 codes, test narratives).
- Root causes → `CODE_NOTES.md`, code keeps one line `# [CN-xxx] <conclusion>`; overturned conclusions get a「訂正（date）」note, never deleted.
- Function docs > 3 lines → `FUNCTION_DOCS.md`, docstring keeps a one-line summary + `[FD-xxx]`.
- Dead code: delete if no future use; keep (and note in BACKLOG) if needed later or still under evaluation.

## 14. Doc rules

- **Daily dev log** `doc/YYYY-MM-DD_開發記錄.md`: that day's work/decisions/todos only; new day = new file starting with「承接 YYYY-MM-DD」; **never backfill old-dated files**.
- **`## 接續摘要`** right after the「承接」line (≤ 15 lines, five fixed rows: 狀態／決策／待辦 (→ BACKLOG area)／新發現／下一步); details go in later sections. Update it before ending each session.
- **New todos go to `doc/BACKLOG.md`** only; planning docs only get checkbox (🔲→✅) / status updates. Finished (incl. local verification) or rejected rows move to `doc/archive/BACKLOG_done.md`.
- Closed AGENT_SYNC topics are archived to `doc/agent_sync/`; leftovers move to BACKLOG.
- Month end: move files to `doc/archive/YYYY-MM/`, add `YYYY-MM_摘要.md` (decisions + root causes, ~30–50 lines), and repoint paths in BACKLOG / CODE_NOTES.
