# Craftflow

> 以創作者為中心的**本地優先**私人創作輔助平台 — 結合小說文字創作與 AI 插畫生成。
> AI 運算完全在本機執行（Ollama + ComfyUI），不依賴雲端；AI 產出皆為建議，**從不覆寫原始創作**。

---

## 核心原則

- **本地優先（Local-First）** — 文字與圖像 AI 一律跑本機 Ollama / ComfyUI，無雲端 API（除非明確指示）。
- **人類為決策主體（Human-in-the-Loop）** — AI 永遠只產出建議與分析報告，絕不覆寫原稿。
- **創作歷程可回溯** — 角色、插畫、章節版本皆可追蹤。

---

## 功能總覽

前端為單頁式（React），分頁對應主要工作流：

| 分頁 | 功能 |
|------|------|
| **草稿 → 線稿**（ProcessTab） | 上傳草稿，經 ComfyUI ControlNet 轉乾淨線稿 |
| **文字 → 生圖**（GenerateTab） | 文字提示詞 → SDXL 生圖（txt2img / IP-Adapter / ControlNet） |
| **草圖問答**（ComposeTab） | 上傳草圖，視覺模型分析、構圖與配色建議 |
| **角色管理**（CharacterTab） | 角色設定、概念圖 → 全身人設圖生成（IPA + ControlNet） |
| **畫風**（ArtStyleTab） | 畫風預設管理，套用至生圖 |

另含**畫風 LoRA 訓練**（TrainingTab，透過 kohya_ss）與章節**節奏 / 一致性分析**、**改寫建議**（移植自 `tools/Craftflow` legacy CLI）。

---

## 技術棧

| 層 | 技術 |
|---|---|
| 後端 | FastAPI · SQLAlchemy 2.0 · Pydantic v2 · SQLite · Python 3.11 |
| 前端 | React 18 · Vite 5 · Vanilla CSS-in-JS（無框架） |
| 文字 LLM | `dolphin-llama3`（生成 / 翻譯 / 分析） |
| 視覺 LLM | `qwen2.5vl:7b`（圖像分析，可全域切換） |
| 圖像生成 | ComfyUI（SDXL · ControlNet Union ProMax · IP-Adapter · Flux2） |
| LoRA 訓練 | kohya_ss（subprocess） |

---

## 系統架構

```
瀏覽器 (localhost:3000)
    ↕  HTTP
React Frontend (Vite dev server)
    ↕  HTTP  → /api/v1/*
FastAPI Backend (localhost:8000)
    ├── Ollama   (host.docker.internal:11434)  ← 文字生成 / 視覺分析
    ├── ComfyUI  (host.docker.internal:8188)   ← 圖片生成 / 線稿 / ControlNet / IPA
    └── kohya_ss (subprocess)                   ← LoRA 訓練
```

> **Docker → 主機**：容器內連主機服務一律用 `host.docker.internal`（非 `localhost`）。直接跑 Python 時改用 `localhost`。

---

## 專案結構

```
Craftflow/
├── backend/
│   ├── main.py                  # FastAPI 入口（掛載 16 個 router）
│   └── app/
│       ├── api/                 # REST 端點（projects, characters, art_generate, training …）
│       ├── models/              # SQLAlchemy ORM 模型
│       ├── schemas/             # Pydantic v2 schema
│       ├── services/ai/         # AI 邏輯：ollama_client, comfyui_client,
│       │   │                    #   art_service, character_service, consistency_service
│       │   ├── prompt_engine/   #   提示詞編譯（compiler / lexicon / styles）
│       │   └── lora_trainer/    #   LoRA 訓練 runner（local / remote）
│       └── core/                # config · database · state
├── frontend/
│   └── src/
│       ├── App.jsx              # 分頁殼層 + 服務狀態燈 + 歷史紀錄
│       ├── components/          # 各分頁（*Tab.jsx）
│       └── api/                 # client / endpoints / useAsync
├── tools/Craftflow/            # legacy CLI（分析 / 繪圖邏輯，逐步遷移至 services/ai/）
├── data/                       # custom_workflows · training_images
├── doc/                        # 開發記錄 · 規劃 · 技術架構 · 安裝手冊
├── docker-compose.yml          # 後端容器
├── start.bat                   # Windows 一鍵啟動（前後端）
└── .env.example                # 環境設定範本
```

---

## 快速開始

> 完整步驟（含硬體對照、ComfyUI 節點 / 模型清單、Docker 與無 GPU 情境）見 **[`doc/setup_guide.md`](doc/setup_guide.md)**。以下為精簡版。

### 前置需求

1. **Ollama** 已安裝並下載對應模型（依顯卡，見 `.env.example` 對照表）：
   ```bash
   ollama pull dolphin-llama3
   ollama pull qwen2.5vl:7b
   ```
2. **ComfyUI** 已啟動於 `:8188`，並安裝必要節點與模型（ControlNet Union ProMax、IP-Adapter；詳見安裝手冊）。

### 1. 設定環境變數

```bash
cp .env.example .env
# 依本機環境調整 OLLAMA_BASE / COMFYUI_BASE / 模型名稱
```

### 2. 啟動後端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
（或在專案根目錄執行 `.\run_backend.ps1`）

### 3. 啟動前端

```bash
cd frontend
npm install
npm run dev
```

### 4. 開啟

- 前端：<http://localhost:3000>
- 後端 API 文件：<http://localhost:8000/docs>

> Windows 可直接執行 **`start.bat`** 一鍵啟動前後端並開啟瀏覽器。

---

## 環境設定（`.env` 重點）

| 變數 | 說明 | 預設 |
|------|------|------|
| `OLLAMA_BASE` | Ollama 位址（Docker 用 `host.docker.internal`，本機用 `localhost`） | `http://host.docker.internal:11434` |
| `COMFYUI_BASE` | ComfyUI 位址 | `http://host.docker.internal:8188` |
| `TEXT_MODEL` | 文字模型 | `dolphin-llama3` |
| `VISION_MODEL` | 視覺模型 | `qwen2.5vl:7b` |
| `COMFYUI_CHECKPOINT` | 覆寫所有工作流的 ckpt | （空＝用工作流內建） |
| `TRAINING_RUNNER_MODE` | LoRA 訓練模式 `local` / `remote` | `local` |
| `KOHYA_PATH` | kohya_ss 安裝目錄 | `C:\kohya_ss` |
| `PERSONAL_STYLE_ENABLED` | 啟用個人畫風預設標籤（如 Blue Archive 風） | `false` |

---

## API 概覽

所有端點前綴 `/api/v1`，互動式文件於 `/docs`。主要 router：

`projects` · `volumes` · `chapters` · `characters` · `factions` · `illustrations` · `art_styles` ·
`art_generate`（人設 / 變體生成）· `ai_art` · `ai_text` · `analysis`（節奏 / 一致性）·
`training`（LoRA）· `export`（Markdown / 角色集匯出）· `generation_history`（生成參數記錄）·
`settings` · `status`（Ollama / ComfyUI 健康檢查）

---

## 開發慣例

- **外科式修改**：只改必要處，不重構無關程式碼，保留既有架構與風格。
- **改前先讀，動手前先說明 why**：工作流為 研究 → 提案 → 說明風險 → 套用。
- **韌性錯誤**：Ollama / ComfyUI 失敗不可讓 app crash；慢速 AI 任務需後端狀態 + 前端進度。
- **每日開發記錄**：當天工作只寫 `doc/YYYY-MM-DD_開發記錄.md`，跨日開新檔不改舊檔。

詳見 [`CLAUDE.md`](CLAUDE.md)。

---

## 文件索引

| 文件 | 內容 |
|------|------|
| [`doc/product_plan.md`](doc/product_plan.md) | 產品願景、功能範疇、開發分期 |
| [`doc/Craftflow_技術架構.md`](doc/Craftflow_技術架構.md) | 完整技術架構、資料模型、AI 流程 |
| [`doc/setup_guide.md`](doc/setup_guide.md) | 安裝建置手冊（含 ComfyUI 節點 / 模型清單） |
| [`doc/comfyui_setup.md`](doc/comfyui_setup.md) | ComfyUI 設定細節 |
| [`doc/YYYY-MM-DD_開發記錄.md`](doc/) | 每日開發記錄與決策 |

---

## 狀態

開發中（v0.1.0，Phase 1：本機單人使用）。
