# Craftflow — 技術架構文件

**專案**：Craftflow 個人創作輔助平台
**版本**：v2.0（截至 2026-05-21）

---

## 1. 系統概覽

Craftflow 是一套**本地優先**的個人創作輔助平台，結合小說管理與插畫生成。
AI 運算完全在本機執行，不依賴雲端服務。

```
瀏覽器 (localhost:3000)
    ↕  HTTP / SSE
React Frontend (Vite dev server)
    ↕  HTTP proxy → /api/*
FastAPI Backend (localhost:8000)
    ├── Ollama (localhost:11434)   ← 文字生成 / 視覺分析
    ├── ComfyUI (localhost:8188)   ← 圖片生成 / 線稿處理
    └── kohya_ss (subprocess)     ← LoRA 訓練
```

---

## 2. 技術棧

| 層 | 技術 | 說明 |
|---|---|---|
| **後端** | FastAPI 0.136+ | REST API + SSE 即時推送 |
| | SQLAlchemy 2.0 | ORM（Mapped 型別安全寫法） |
| | Pydantic v2 | Schema 驗證 |
| | SQLite | 本地資料庫（`backend/craftflow.db`） |
| | Python 3.11（venv） | 後端執行環境 |
| **前端** | React 18 | UI 框架 |
| | Vite 5 | 打包工具 / dev server（port 3000） |
| | Vanilla CSS-in-JS | 無 CSS 框架，style object 直寫 |
| **LLM** | `dolphin-llama3` | 文字生成、翻譯、分析 |
| | `qwen2.5vl:7b`（預設）| 視覺分析（全域可切換） |
| **圖像** | ComfyUI | txt2img、img2img、ControlNet、IP-Adapter |
| **訓練** | kohya_ss (`sd-scripts`) | LoRA 訓練（`train_network.py`） |
| | PyTorch 2.13+cu132 | GPU 加速（RTX 5070 Ti · 16 GB VRAM） |

---

## 3. 架構原則

1. **Local-First** — Ollama / ComfyUI 皆用 `localhost`（本機執行）
2. **Human-in-the-Loop** — AI 不覆寫原始創作內容，產出進分析報告
3. **Resilient** — Ollama / ComfyUI 失敗不 crash 後端，回傳明確錯誤
4. **Progressive feedback** — 長時間 AI 任務以 SSE 即時推送進度
5. **VRAM 協調** — `VRAMGuardian` 確保 Ollama 與 ComfyUI 不同時佔用 VRAM

---

## 4. 目錄結構

```
Craftflow/
├── start.bat                        ← 一鍵啟動（雙擊）
├── run_backend.ps1                  ← PowerShell 後端啟動腳本
├── .env                             ← 本機設定（不進 git）
├── .env.example                     ← 設定範本
│
├── backend/
│   ├── main.py                      ← FastAPI app 進入點，router 註冊
│   ├── requirements.txt
│   ├── checkpoint_styles.yml        ← Checkpoint 名稱 → PromptStyle 對應表
│   ├── .venv/                       ← Python 虛擬環境
│   └── app/
│       ├── core/
│       │   ├── config.py            ← 環境變數讀取（load_dotenv）
│       │   ├── database.py          ← SQLAlchemy engine + init_db() + _migrate()
│       │   └── state.py             ← 執行期全域狀態（checkpoint / workflow / lora / vision model）
│       ├── models/                  ← SQLAlchemy ORM 模型（9 張資料表）
│       ├── schemas/                 ← Pydantic request / response schema
│       ├── api/                     ← FastAPI routers
│       └── services/
│           ├── ai/
│           │   ├── ollama_client.py        ← Ollama HTTP 封裝（text / vision / multi-image）
│           │   ├── art_service.py          ← 草圖分析、完稿批評、配色建議、草圖問答
│           │   ├── character_service.py    ← 角色摘要、特性提取、視覺描述、Q&A
│           │   ├── consistency_service.py  ← 一致性掃描（表面 + 語義）
│           │   ├── rewrite_service.py      ← AI 改寫建議
│           │   ├── rhythm_service.py       ← 段落節奏分析（純規則）
│           │   ├── vram_manager.py         ← VRAMGuardian（Ollama ↔ ComfyUI 切換）
│           │   └── prompt_engine/
│           │       ├── styles.py           ← PromptStyle enum + STYLE_CONFIG
│           │       ├── lexicon.py          ← 詞庫（顏色表、regex、tag 集合）
│           │       └── compiler.py         ← compile() 主流程
│           ├── lora_trainer/
│           │   ├── runner.py               ← TrainingRunner 抽象基類
│           │   ├── local_runner.py         ← LocalSubprocessRunner
│           │   ├── remote_runner.py        ← RemoteAgentRunner（Docker 備用）
│           │   └── config_writer.py        ← 生成 kohya_ss TOML config
│           └── comfyui_client.py           ← ComfyUI WebSocket 封裝
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx                  ← Tab 路由 + 全域設定狀態 + 歷史記錄 panel
│   │   └── components/
│   │       ├── ProcessTab.jsx       ← 草稿 → 線稿
│   │       ├── GenerateTab.jsx      ← 文字 / 參考圖 → 生圖
│   │       ├── ComposeTab.jsx       ← 草圖問答 + 構圖參考圖
│   │       ├── CharacterTab.jsx     ← 角色管理（最大元件）
│   │       ├── ArtStyleTab.jsx      ← 畫風管理
│   │       ├── TrainingTab.jsx      ← LoRA 訓練
│   │       └── SettingsTab.jsx      ← 全域設定 Modal（⚙ 齒輪按鈕開啟）
│   └── vite.config.js               ← proxy /api → localhost:8000
│
├── data/
│   ├── custom_workflows/            ← 使用者自訂 ComfyUI workflow JSON
│   └── training_images/             ← LoRA 訓練圖片
│
└── tools/Craftflow/diffusion/workflows/   ← 系統內建 workflow JSON（6 個）
    ├── text_to_image.json
    ├── image_to_image.json
    ├── sketch_to_lineart.json
    ├── sketch_to_reference.json
    ├── ipadapter_txt2img.json
    └── style_enhance.json
```

---

## 5. 資料庫模型

資料庫：`backend/craftflow.db`（SQLite）
建立方式：後端啟動時 `Base.metadata.create_all()` 自動建表；欄位新增透過 `_migrate()` 中的 `_add_columns()`。

### 資料表一覽

| 資料表 | 主要欄位 | 說明 |
|---|---|---|
| `projects` | id, title, author, synopsis, art_style_id, status | 小說專案 |
| `chapters` | id, project_id, order_index, title, content | 章節（支援 reorder） |
| `characters` | id, project_id, name, core_traits, gender, age, color, concept_images(JSON), ai_generated_images(JSON), variants(JSON), art_style_id | 角色（含最多 2 變體） |
| `factions` | id, project_id, name, thumbnail_path | 勢力 |
| `illustrations` | id, project_id, file_path, linked_chapter_id, linked_character_id, ai_description | 插畫 |
| `analysis_reports` | id, chapter_id, report_type, content(JSON) | 分析報告 |
| `art_styles` | id, name, base_style, quality_prefix, negative, extra_tags, loras(JSON) | 畫風預設 |
| `training_images` | id, filename, filepath, caption, width, height | LoRA 訓練圖片 |
| `training_jobs` | id, name, status, base_checkpoint, trigger_word, lora_rank, learning_rate, epochs, current_step, total_steps, last_loss | LoRA 訓練任務 |

### 關聯圖

```
Project ──< Chapter ──< AnalysisReport
        ──< Character >──< Faction  (many-to-many: character_factions)
        ──< Illustration
        ──> ArtStyle (FK, optional)

Character ──> ArtStyle (FK, optional)
TrainingJob ──> ArtStyle (FK, optional, 訓練完成後自動掛載)
```

---

## 6. 執行期全域狀態（state.py）

所有狀態為記憶體級別，**重啟後回到 .env 設定值**，前端以 localStorage 持久化。

| 狀態 | 說明 | Getter / Setter |
|---|---|---|
| `_active_checkpoint` | 目前使用的 SD checkpoint | `get/set_checkpoint()` |
| `_active_workflow` | 目前使用的 ComfyUI workflow | `get/set_workflow()` |
| `_active_lora` | 全域 LoRA `{name, strength}` | `get/set_lora()` |
| `_active_vision_model` | 全域 Ollama 視覺模型 | `get/set_vision_model()` |

**視覺模型優先級**：`state._active_vision_model` → `.env VISION_MODEL` → 預設 `qwen2.5vl:7b`

---

## 7. API 端點

所有端點前綴：`/api/v1`

### 7.1 專案 / 章節 / 勢力

| 方法 | 路徑 | 說明 |
|---|---|---|
| CRUD | `/projects`, `/{id}` | 專案管理（含封面圖） |
| CRUD | `/projects/{id}/chapters`, `/chapters/{id}` | 章節管理 |
| PATCH | `/chapters/{id}/reorder` | 章節排序 |
| CRUD | `/projects/{id}/factions`, `/factions/{id}` | 勢力管理 |
| POST/DELETE | `/factions/{id}/members/{char_id}` | 角色加入 / 移出勢力 |

### 7.2 角色管理

| 方法 | 路徑 | 說明 |
|---|---|---|
| CRUD | `/projects/{id}/characters`, `/characters/{id}` | 角色基本 CRUD |
| POST | `/characters/{id}/portrait` | 上傳頭像 |
| POST/GET/DELETE | `/characters/{id}/concept-images/{index}` | 概念圖管理（最多 3 張） |
| POST/GET/DELETE | `/characters/{id}/ai-images/{index}` | AI 生成圖管理（最多 8 張） |
| GET/PUT | `/characters/{id}/variants/{slot}` | 變體資料（slot 1-2） |
| POST/DELETE | `/characters/{id}/variants/{slot}/concept-images/{index}` | 變體概念圖 |
| POST/DELETE | `/characters/{id}/variants/{slot}/ai-images/{index}` | 變體 AI 圖 |

### 7.3 AI 文字服務

| 方法 | 路徑 | 說明 |
|---|---|---|
| POST | `/chapters/{id}/analyze` | 章節節奏 + 一致性分析（modes: gentle / pro） |
| POST | `/chapters/{id}/rewrite` | AI 改寫建議 |
| POST | `/characters/{id}/summarize` | 角色摘要生成（AI） |
| POST | `/characters/{id}/extract` | 從章節文字提取角色描述 |
| POST | `/characters/{id}/ask` | 角色設計 Q&A |

### 7.4 AI 視覺分析

| 方法 | 路徑 | 說明 |
|---|---|---|
| POST | `/illustrations/{id}/analyze` | 插畫批評（sketch / finished / line_color） |
| POST | `/illustrations/{id}/describe` | 自動生成插畫描述 |
| POST | `/illustrations/{id}/ask` | 構圖問答 |
| POST | `/art/ask` | 自由格式藝術問答（可選上傳圖片） |
| POST | `/characters/{id}/describe-portrait` | 角色頭像視覺描述 → 角色設定 |

### 7.5 圖片生成（ComfyUI）

| 方法 | 路徑 | 說明 |
|---|---|---|
| POST | `/art/compile-prompt` | 中文 → SD 提示詞編譯（自動偵測 checkpoint style） |
| POST | `/art/lineart` | 草稿 → 線稿（ControlNet） |
| POST | `/art/generate` | 文字 → 圖片（txt2img，支援自訂 workflow） |
| POST | `/art/compose` | 草圖 + 問題 → 構圖意見 + 參考圖（Ollama vision + ComfyUI） |
| POST | `/art/img-guide` | 參考圖 → 圖片（`mode=i2i` 或 `mode=controlnet`，含 denoise 控制） |
| POST | `/art/ipadapter` | 外觀參考圖 → 圖片（IP-Adapter，`weight` 0.1-1.5） |
| POST | `/characters/{id}/generate-design` | 角色人設圖（全身圖或表情半身圖） |
| POST | `/characters/{id}/variants/{slot}/generate-design` | 角色變體人設圖 |

### 7.6 插畫管理

| 方法 | 路徑 | 說明 |
|---|---|---|
| CRUD | `/projects/{id}/illustrations`, `/illustrations/{id}` | 插畫 CRUD |
| GET | `/illustrations/{id}/file` | 取得插畫檔案 |

### 7.7 畫風管理

| 方法 | 路徑 | 說明 |
|---|---|---|
| CRUD | `/art-styles`, `/{id}` | 畫風模型 CRUD |

### 7.8 LoRA 訓練

| 方法 | 路徑 | 說明 |
|---|---|---|
| POST | `/training/images/upload` | 上傳訓練圖片（自動偵測尺寸） |
| GET/DELETE | `/training/images`, `/{id}` | 圖片列表 / 刪除 |
| PUT | `/training/images/{id}/caption` | 更新 caption |
| GET | `/training/images/{id}/file` | 取得圖片檔案 |
| POST | `/training/jobs` | 建立訓練任務 |
| GET | `/training/jobs`, `/{id}` | 任務列表 / 詳情 |
| POST | `/training/jobs/{id}/start` | 啟動訓練（async 202） |
| POST | `/training/jobs/{id}/stop` | 停止訓練 |
| GET | `/training/jobs/{id}/progress` | SSE 即時進度串流 |
| POST | `/training/jobs/{id}/caption-all` | Ollama Vision 批次生成 caption |
| GET | `/training/status` | kohya_ss 環境狀態檢查 |

### 7.9 設定 / 狀態

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/status/` | 系統整體健康檢查 |
| GET | `/status/ollama` | Ollama 狀態 + 已安裝模型清單 |
| GET | `/status/comfyui` | ComfyUI 狀態 |
| GET/POST | `/settings/checkpoint` | 取得 / 切換 checkpoint |
| GET | `/settings/checkpoints` | 可用 checkpoint 列表（ComfyUI） |
| GET/POST | `/settings/workflow` | 取得 / 切換 workflow |
| GET | `/settings/workflows` | 可用 workflow 列表（custom dir） |
| GET/POST | `/settings/vision-model` | 取得 / 切換全域視覺模型 |
| GET | `/settings/vision-models` | Ollama 已安裝模型清單 |
| GET/POST | `/settings/lora` | 取得 / 設定全域 LoRA |
| GET | `/settings/loras` | 可用 LoRA 列表（ComfyUI） |

---

## 8. 前端元件

| 元件 | Tab | 功能摘要 |
|---|---|---|
| `ProcessTab` | 草稿 → 線稿 | 上傳草圖，ComfyUI ControlNet 轉線稿 |
| `GenerateTab` | 文字 → 生圖 | 中文描述編譯 + txt2img；支援 img-guide（i2i / ControlNet）及 IP-Adapter 三種生成模式 |
| `ComposeTab` | 草圖問答 | 上傳草圖 + 提問，Ollama vision 分析後給出構圖意見並生成參考圖；支援 IP-Adapter 外觀參考 |
| `CharacterTab` | 角色管理 | 角色 CRUD、概念圖 / AI 圖管理、人設圖生成、最多 2 個服裝變體、勢力關聯 |
| `ArtStyleTab` | 畫風 | 畫風預設 CRUD、LoRA 組合設定、畫風測試生成 |
| `TrainingTab` | LoRA 訓練 | 圖片上傳、caption 管理、訓練任務建立、SSE 即時進度、Log 展開 |
| `SettingsTab` | — | 全域設定 Modal（⚙ 齒輪按鈕開啟）：視覺模型切換、生成模式、Checkpoint、LoRA、Workflow |

**Tab 切換機制**：`display: none` 切換（保留各 Tab React state，不 unmount）

**歷史記錄 Panel**（常駐底部）：
- 最多 100 筆，超過自動移除最舊
- Canvas 縮圖（max 300px, JPEG）持久化至 localStorage
- 支援：隱藏/顯示 toggle、單筆刪除、點圖 Lightbox 放大、下載

---

## 9. 提示詞引擎（Prompt Engine）

位置：`backend/app/services/ai/prompt_engine/`

### 流程

```
中文輸入
    ↓
[1] LLM 翻譯（Ollama dolphin-llama3）— 依 style 選模板（styles.py）
    ↓
[2] 萃取 Output（_extract_output）
    ↓
[3] Sanitizer — 移除 banned_tags（自動含 quality_prefix tags）
    ↓
[4] Anchor 提取（_extract_color_anchors）
    ← 從中文原文 regex 萃取「髮色、眼色、髮長」
    ← anchor_text 優先（core_traits），避免 vision 污染
    ↓
[5] 衝突清除（_remove_conflicting_tags）
    ← 移除 LLM 輸出中與 anchor 衝突的髮色/眼色/髮長標籤
    ↓
[6] 排序 + 加權（_reorder_tags）
    ← Subject > (anchor:1.1) > Clothing > Others > Meta
    ↓
[7] 拼接 quality_prefix（可被 ArtStyle 覆寫）
    ↓
(positive_prompt, negative_prompt)
```

### 支援的 Style

| Style | quality_prefix | 用途 |
|---|---|---|
| `sdxl` | masterpiece, best quality, high quality | 通用 SDXL |
| `pony` | score_9, score_8_up, score_7_up | Pony Diffusion |
| `flux` | （無）| Flux（自然語言格式） |
| `noobai` | masterpiece, best quality, newest, absurdres | NoobAI |
| `illustrious` | masterpiece, best quality, newest, highres | Illustrious XL |
| `anythingxl` | newest, masterpiece, best quality | Anything XL |

### ArtStyle 覆寫優先級

```
手動傳入 art_style_id
  > character.art_style_id（角色預設）
  > project.art_style_id（專案預設）
  > _detect_style()（讀 checkpoint 名稱自動判斷）
```

---

## 10. ComfyUI Workflow 管理

### 系統內建 Workflow

| 檔案 | 用途 |
|---|---|
| `text_to_image.json` | 標準 txt2img（SDXL），含 LoRA 注入支援 |
| `image_to_image.json` | img2img，VAEEncode + KSampler denoise |
| `sketch_to_lineart.json` | ControlNet 線稿抽取（lineart preprocessor） |
| `sketch_to_reference.json` | ControlNet 構圖參考（scribble） |
| `ipadapter_txt2img.json` | IP-Adapter 外觀參考生成 |
| `style_enhance.json` | 風格強化（備用） |

### Prompt 注入優先級

```
1. __POSITIVE__ / __NEGATIVE__ 佔位符（系統 workflow）
2. _meta.title 含 "positive" / "negative" 關鍵字（使用者自訂 workflow）
3. 依 node ID 排序，第 1 / 第 2 個 CLIPTextEncode（兜底）
```

### LoRA 動態注入（`_inject_loras()`）

```
CheckpointLoaderSimple → LoraLoader_0 → LoraLoader_1 → ...
                              ↓
                    KSampler.model  重聯至最後一個 LoRA
                    CLIPTextEncode.clip 重聯至最後一個 LoRA
```

注入優先級：全域 LoRA（Settings 設定）→ ArtStyle LoRA

---

## 11. LoRA 訓練 Pipeline

```
Frontend TrainingTab
    → POST /training/jobs/{id}/start
        ↓
Backend (training.py)
    1. 寫 caption .txt（與圖片同名）
    2. config_writer.write_config() → train_config.toml
    3. asyncio.create_task(_run_training)
        ↓
TrainingRunner（get_runner() factory）
    ├── LocalSubprocessRunner（TRAINING_RUNNER_MODE=local）
    │   subprocess → python kohya_ss/sd-scripts/train_network.py
    │   解析 stdout（步數 / loss / ETA）
    │   每 10 step 寫入 DB
    │   SSE 廣播 → 前端進度條
    │
    └── RemoteAgentRunner（TRAINING_RUNNER_MODE=remote，Docker 備用）
        HTTP POST host.docker.internal:7788/train

訓練完成
    → 複製 .safetensors → COMFYUI_LORAS_DIR
    → 若綁定 ArtStyle → 自動加入 loras JSON
    → job.status = "done"
```

### 漸進訓練策略

| 張數 | 目的 |
|---|---|
| 5 張 | 驗證 pipeline 能跑通 |
| 10 張 | 確認風格特徵捕捉 |
| 20 張 | 主要品質評估點 |
| 30 張 | 穩定輸出目標 |

---

## 12. VRAM 協調機制（VRAMGuardian）

Ollama 與 ComfyUI 共用 GPU（RTX 5070 Ti · 16 GB），不能同時載入。

```
guardian.request_focus("ollama")
    → 若 ComfyUI 為 owner：POST /free_memory 卸載 ComfyUI
    → 等待 Ollama 可用
    → 標記 owner = "ollama"

guardian.request_focus("comfyui")
    → 若 Ollama 為 owner：POST /api/generate keep_alive=0 卸載 Ollama
    → 標記 owner = "comfyui"
```

所有 AI 端點在呼叫服務前都先 `await guardian.request_focus(...)`.

---

## 13. 六大功能詳解

### 功能 1：草稿 → 線稿（ProcessTab）

| 技術 | 用途 |
|---|---|
| ComfyUI `sketch_to_lineart.json` | ControlNet lineart 工作流 |
| ControlNet + Lineart Preprocessor | 保留結構，萃取乾淨線條 |

**API**：`POST /art/lineart`

---

### 功能 2：文字 / 參考圖 → 生圖（GenerateTab）

三種生成模式：

| 模式 | 技術 | API |
|---|---|---|
| 文字生圖（txt2img） | dolphin-llama3 編譯提示詞 + ComfyUI txt2img | `/art/generate` |
| 參考圖引導（i2i）| ComfyUI image_to_image.json，denoise 0.05-0.95 | `/art/img-guide?mode=i2i` |
| ControlNet 構圖 | ComfyUI sketch_to_reference.json（scribble） | `/art/img-guide?mode=controlnet` |
| IP-Adapter 外觀 | ComfyUI ipadapter_txt2img.json，weight 0.1-1.5 | `/art/ipadapter` |

---

### 功能 3：草圖問答（ComposeTab）

| 技術 | 用途 |
|---|---|
| Ollama 視覺模型（全域切換）| 分析草圖，回答構圖問題，萃取 SDXL prompt |
| ComfyUI txt2img 或 IP-Adapter | 生成構圖參考圖 |

**API**：`POST /art/compose`（含 IP-Adapter 外觀參考模式）

**全域視覺模型切換**：⚙ 設定 → 視覺模型下拉，切換後 ComposeTab / CharacterTab 全部生效。

---

### 功能 4：角色管理（CharacterTab）

| 子功能 | 說明 |
|---|---|
| 角色 CRUD | 名稱、性別、年齡、外貌、個性、ai_prompt、代表色 |
| 概念圖上傳 | 最多 3 張，Vision 模型批次分析萃取視覺特徵 |
| AI 生成圖 | 最多 8 張，ComfyUI 人設圖或表情半身圖 |
| 服裝變體 | 最多 2 個 Slot，各有獨立概念圖 + AI 圖 |
| AI 摘要 | dolphin-llama3 自動生成角色摘要 |
| 勢力管理 | 多對多關聯，角色加入組織 |
| ArtStyle 優先鏈 | 手動指定 > 角色預設 > 專案預設 > checkpoint 自動偵測 |

**主要 API**：`/characters`, `/generate-design`, `/variants`, `/factions`

---

### 功能 5：畫風管理（ArtStyleTab）

每個畫風預設打包：

| 欄位 | 說明 |
|---|---|
| `base_style` | sdxl / pony / flux / noobai / illustrious / anythingxl |
| `quality_prefix` | 覆寫 STYLE_CONFIG 預設 |
| `negative` | 覆寫負向提示詞 |
| `extra_tags` | 每次生圖固定附加 |
| `loras` | `[{model, weight}]`，注入到 ComfyUI workflow |

**LoRA 注入**：全域 LoRA（Settings）+ ArtStyle LoRA 疊加注入，全域優先。

**API**：`/art-styles` CRUD + `/settings/loras`（autocomplete 資料來源）

---

### 功能 6：LoRA 訓練（TrainingTab）

| 技術 | 用途 |
|---|---|
| SQLite（training_images / training_jobs） | 圖片與任務持久化 |
| Ollama 視覺模型 | 批次生成圖片 caption |
| config_writer.py | 生成 kohya_ss TOML config |
| kohya_ss `train_network.py` | LoRA 訓練引擎（subprocess） |
| PyTorch 2.13+cu132 | GPU 訓練（RTX 5070 Ti） |
| SSE | 即時推送訓練進度 |

---

## 14. 環境設定（.env）

```env
# AI 服務
OLLAMA_BASE=http://localhost:11434
COMFYUI_BASE=http://localhost:8188
COMFYUI_CHECKPOINT=Illustrious-XL-v2.0.safetensors

# 模型（全域可在 Settings 即時切換，重啟後恢復此值）
TEXT_MODEL=dolphin-llama3
VISION_MODEL=qwen2.5vl:7b

# LoRA 訓練
TRAINING_RUNNER_MODE=local
KOHYA_PATH=C:\kohya_ss\sd-scripts
KOHYA_PYTHON=python
TRAINING_IMAGES_DIR=F:\wk\Craftflow\data\training_images
COMFYUI_LORAS_DIR=F:\wk\ComfyUI_portable\ComfyUI\models\loras
```

---

## 15. 啟動方式

### 快速啟動

雙擊專案根目錄 `start.bat`
→ 自動開後端視窗 + 前端視窗 + 瀏覽器（3 秒後）

### 手動啟動

```cmd
# 後端（backend/ 目錄）
.venv\Scripts\uvicorn.exe main:app --reload --host 0.0.0.0 --port 8000

# 前端（frontend/ 目錄）
npm run dev
```

---

## 16. 外部服務依賴

| 服務 | 位址 | 用途 | 必要性 |
|---|---|---|---|
| Ollama | localhost:11434 | 文字生成、視覺分析（多模型可切換） | 文字 / 視覺功能必要 |
| ComfyUI | localhost:8188 | 圖片生成、線稿、ControlNet、IP-Adapter | 生圖功能必要 |
| kohya_ss | subprocess | LoRA 訓練 | 訓練功能必要 |

三者皆不在線時後端仍可啟動；功能調用時若服務不在線，回傳 503，不 crash。
