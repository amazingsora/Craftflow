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
| LLM | 文字/翻譯 + 視覺模型皆由設定 UI 切換（清單來自 Ollama `/api/tags`，存 core/state→runtime_state.json）。下方為 **fallback 預設**（UI 未選且 `.env` 未覆蓋時才用）：文字 `dolphin-llama3`、視覺 `qwen2.5vl:7b` |
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
             state(執行期全域設定，A4後持久化 data/runtime_state.json，重啟保留)
frontend/src/
  App.jsx        側欄佈局殼層(196px) + 服務狀態燈 + 底部歷史 + settings modal
  components/    ProcessTab GenerateTab ComposeTab NovelTab ArtStyleTab SettingsTab TrainingTab
                 CharacterTab(A2已拆:113行shell)→ characterTabStyles/Parts/Shared/Views + CharacterDetailView(1380行)
  index.css      雙主題 token：:root=淺色預設、[data-theme="dark"]；localStorage craftflow_theme
data/custom_workflows/  ComfyUI workflow（須 API 格式；Standard_V35 / _EyeFix=眼睛強化A/B）
tools/Craftflow/        legacy CLI（遷移目標 → services/ai/）
doc/                    每日開發記錄 · 規劃文件
```

## 機制速查
- 畫風 = art_styles DB（LoRA+tags）；`.env` PERSONAL_STYLE_* 寫死個人畫風 tags（角色畫風 extra_tags 為空才套用）
- checkpoint/workflow/LoRA/模型 全域切換存 core/state（A4後持久化 data/runtime_state.json，重啟保留；檔案缺失才回 .env 預設）
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
- 檔案工具寫掛載資料夾可能**檔尾截斷**：重要檔用 shell 寫入，寫完驗檔尾（已實證 06-10/06-12/07-12）。07-12 新增觀察：截斷不只發生在寫入當下，bash 端對同一檔案的後續讀取（cat/grep/python open）也可能長時間（>15 分鐘）持續讀到截斷/局部損壞版本，即便 Windows host 端（Read tool）內容已完整正確；`__pycache__` 清除、`sleep` 等待、`--import-mode=importlib` 皆無效。唯一穩定解法：用 bash 寫入正確內容覆蓋該檔（`python3 -c "open(f,'wb').write(...)"`，需手動保留原始 CRLF），寫完立即 `py_compile` 驗證。改動 `.py` 檔後、要在沙箱跑 pytest 前，先對受影響檔案跑一次 `python3 -m py_compile` 健檢，比事後除錯省時很多。⚠️ 07-12 新增觀察：`py_compile` 不保證抓到截斷——若截斷點恰好落在註解/docstring 結尾，殘缺檔仍可能語法合法、`py_compile` 誤判成功。更可靠的健檢是額外跑 `ast.parse` 後檢查預期的函式/類別名稱是否都還在（`{n.name for n in ast.walk(tree) if hasattr(n,'name')}`），才抓到 `lexicon.py` 這種漏網案例。
- 沙箱不可直寫 SQLite（掛載層不支援鎖定）；DB 變更提供指令由使用者本機執行
- `vite.config.js.timestamp-*.mjs` 為 Vite 暫存檔，已 gitignore，勿入版

## Doc Rules
- **每日開發記錄** `doc/YYYY-MM-DD_開發記錄.md`：當天所有工作/討論/決策/待辦只寫當天檔；跨日開新檔，開頭「承接 YYYY-MM-DD」，不改舊檔；會話開始先讀最新一筆確認狀態。
- **規劃文件** `doc/YYYY-MM-DD_*規劃.md`：只更新進度 checkbox（🔲→✅）與狀態欄；當 spec/checklist 用，保持精簡。
- **禁止**：在舊日期檔補寫新內容；把技術細節分散到多個檔案。
