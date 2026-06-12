# Craftflow — Claude Instructions

## Architecture Mandates
- **Local-First:** AI on Ollama + ComfyUI；無雲端 API（除非明確指示）。
- **Human-in-the-Loop:** 絕不覆蓋原始創作內容；AI 產出只進分析報告／獨立欄位。
- **Docker → Host:** 容器內連主機服務用 `host.docker.internal`；本機直跑 Python 用 `localhost`。

## Stack
| Layer | Tech |
|---|---|
| Backend | FastAPI · SQLAlchemy 2.0 · Pydantic v2 · SQLite · Python 3.11 |
| Frontend | React 18 · Vite 5 · Vanilla CSS-in-JS |
| LLM | `dolphin-llama3`（文字/翻譯）· `qwen2.5vl:7b`（視覺，可全域切換） |
| Image | ComfyUI @ `host.docker.internal:8188`（SDXL · CN Union ProMax · IPA） |
| Ollama | `host.docker.internal:11434` |
| LoRA 訓練 | kohya_ss（subprocess） |

## Architecture Map
```
backend/main.py   16 routers，前綴 /api/v1
backend/app/
  api/       路由層：projects volumes chapters characters factions illustrations
             art_styles art_generate(3075行→A1拆解中) ai_art ai_text analysis
             training export generation_history settings status
  services/  export_service comfyui_client
    ai/      art_service character_service consistency_service image_edit_service
             generation_jobs(非同步生圖job) generation_recorder(seed/參數落DB)
             vram_manager(條件式卸載) ollama_client prompt_engine/ lora_trainer/
  models/ schemas/  ORM+Pydantic（chapter_revision=章節快照；generation_history=生成可重現）
  core/      config(.env/PERSONAL_STYLE) database backup(定時VACUUM INTO)
             state(執行期全域設定，重啟重置)
frontend/src/
  App.jsx        側欄佈局殼層(196px) + 服務狀態燈 + 底部歷史 + settings modal
  components/    ProcessTab GenerateTab ComposeTab NovelTab CharacterTab(2431行→A2待拆)
                 ArtStyleTab SettingsTab TrainingTab
  index.css      雙主題 token：:root=淺色預設、[data-theme="dark"]；localStorage craftflow_theme
data/custom_workflows/  ComfyUI workflow（須 API 格式；Standard_V35 / _EyeFix=眼睛強化A/B）
tools/Craftflow/        legacy CLI（遷移目標 → services/ai/）
doc/                    每日開發記錄 · 規劃文件
```

## 機制速查
- 畫風 = art_styles DB（LoRA+tags）；`.env` PERSONAL_STYLE_* 寫死個人畫風 tags（角色畫風 extra_tags 為空才套用）
- checkpoint/workflow/LoRA/模型 全域切換存 core/state（執行期，重啟回 .env）
- 生圖：同步 `/art/generate` + 非同步 `/art/generate-async`（job+polling）；參數記錄 generation_history

## Coding Rules
1. **Surgical updates** — 只改必要處，無關的不重構。
2. **Progressive feedback** — 慢速 AI 任務需後端狀態 + 前端進度 UI。
3. **Resilient errors** — Ollama/ComfyUI 失敗不可讓 app crash。
4. 改前先讀；動手前先說明 *why*。

## Workflow
Research → Propose → Explain risk → Apply

## 沙箱/環境注意（實戰教訓）
- repo=LF、Windows 工作目錄=CRLF：沙箱 git status 會全檔假 modified；commit 前對要提交的檔先 `sed 's/\r$//'` 正規化，否則整檔換行符入版
- 檔案工具寫掛載資料夾可能**檔尾截斷**：重要檔用 shell 寫入，寫完驗檔尾（已實證 06-10/06-12）
- 沙箱不可直寫 SQLite（掛載層不支援鎖定）；DB 變更提供指令由使用者本機執行
- `vite.config.js.timestamp-*.mjs` 為 Vite 暫存檔，已 gitignore，勿入版

## Doc Rules
- **每日開發記錄** `doc/YYYY-MM-DD_開發記錄.md`：當天所有工作/討論/決策/待辦只寫當天檔；跨日開新檔，開頭「承接 YYYY-MM-DD」，不改舊檔；會話開始先讀最新一筆確認狀態。
- **規劃文件** `doc/YYYY-MM-DD_*規劃.md`：只更新進度 checkbox（🔲→✅）與狀態欄；當 spec/checklist 用，保持精簡。
- **禁止**：在舊日期檔補寫新內容；把技術細節分散到多個檔案。
