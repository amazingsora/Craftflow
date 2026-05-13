# Craftflow — 產品規劃文件

**版本：v0.2**
**建立日期：2026-05-08**
**最後更新：2026-05-08**

---

## 版本歷史

| 版號 | 日期 | 說明 |
|------|------|------|
| v0.1 | 2026-05-08 | 初版：確立產品方向、架構決策、開發分期 |
| v0.2 | 2026-05-08 | 調整分期：Phase 2 改為 Web UI，Phase 3 為 Flutter App |

---

## 1. 產品願景

**Craftflow** 是一套以創作者為中心的私人創作輔助平台，支援小說文字創作與插畫繪圖兩大方向。

### 核心原則

- **人類創作者永遠是決策主體** — AI 產出皆為建議，從不覆寫原文
- **創作歷程可回溯** — 所有版本皆可追蹤
- **本地優先** — AI 運算優先使用本機（Ollama + ComfyUI），未來擴展至雲端
- **最終產出是一本小說** — 文字章節 + 插畫，由創作者手動匯入並整合

### 使用者

目前定位：個人創作者（單人使用）
未來擴展：多使用者帳號系統（Phase 2+）

---

## 2. 功能範疇

### 2.1 小說管理

| 功能 | 說明 |
|------|------|
| 專案管理 | 建立多個小說專案，各自獨立 |
| 章節控制 | 建立、排序、重命名、刪除章節 |
| 文字編輯 | 小說排版格式，支援中文創作 |
| 章節分析 | 節奏分析、一致性檢查（現有邏輯移植） |
| 改寫建議 | AI 產出建議段落，不動原稿 |
| 插畫掛載 | 章節內指定插畫位置 |

### 2.2 人物設定系統

| 功能 | 說明 |
|------|------|
| 角色檔案 | 結構化角色設定（名稱、特徵、行為規則、語氣風格） |
| 從劇情提取 | AI 從章節文本分析並建議角色特徵 |
| 從插畫提取 | 匯入角色圖後，AI 描述視覺外觀特徵 |
| AI 設計協助 | 對話式問答，協助創作者補全角色設定 |
| 一致性守衛 | 寫作時檢查是否違反角色設定 |

### 2.3 繪圖輔助工具

| 功能 | 說明 |
|------|------|
| 草稿分析 | 草稿 → 文字改進意見（Ollama vision） |
| 配色建議 | 線稿 → 配色方案建議 |
| 完成圖評析 | 完成插畫 → 光影/色彩/細節意見 |
| 構圖問答 | 畫面構圖、人物動作、鏡頭角度建議 |
| 風格強化 | 草稿 + 自己作品 → 同風格商業品質參考圖（ComfyUI + IP-Adapter）|
| 線稿化 | 草稿 → 清稿線稿（ComfyUI ControlNet） |

### 2.4 小說匯出

| 功能 | 說明 |
|------|------|
| 目錄生成 | 自動根據章節結構產生目錄 |
| 小說排版 | 中文小說標準排版 |
| 插圖整合 | 依章節內標記位置插入插畫 |
| 匯出格式 | Markdown（v1）→ EPUB / PDF（v2） |

---

## 3. 系統架構

### 3.1 總覽

```
┌──────────────────────────────────────┐
│           Clients                    │
│  Mobile App (Flutter)                │
│  Web App（未來 Phase 3+）            │
└────────────────┬─────────────────────┘
                 │ REST API / WebSocket
┌────────────────▼─────────────────────┐
│         Backend API                  │
│  FastAPI (Python)                    │
│  ├── 小說 / 章節管理                 │
│  ├── 人物設定管理                    │
│  ├── 插畫管理                        │
│  ├── AI 分析服務                     │
│  └── 小說匯出服務                    │
└──────┬─────────────┬─────────────────┘
       │             │
┌──────▼──────┐ ┌────▼────────────────┐
│  Database   │ │  AI Services        │
│  SQLite     │ │  Ollama (local)     │
│  (Phase 1)  │ │  ComfyUI (local)    │
│  → Postgres │ │  → Cloud API        │
│  (Phase 2+) │ │    (Phase 2+)       │
└─────────────┘ └────────────────────┘
```

### 3.2 目錄結構（目標）

```
Craftflow/
├── backend/               ← Phase 1 新建
│   ├── app/
│   │   ├── api/           ← FastAPI 路由
│   │   ├── models/        ← SQLAlchemy ORM 模型
│   │   ├── services/      ← 業務邏輯
│   │   │   ├── ai/        ← AI 服務（移植現有邏輯）
│   │   │   ├── novel/     ← 章節管理
│   │   │   └── export/    ← 匯出引擎
│   │   └── core/          ← 設定、DB 連線
│   └── main.py
├── mobile/                ← Phase 3 新建
│   └── (Flutter project)
├── tools/Craftflow/       ← 現有原型（維持可用）
└── doc/
    └── product_plan.md    ← 本文件
```

### 3.3 技術選型

| 層級 | 技術 | 理由 |
|------|------|------|
| Backend API | FastAPI (Python) | 現有 AI 程式碼全是 Python，直接整合 |
| 資料庫 (Phase 1) | SQLite | 零設定，本機開發，單人使用足夠 |
| 資料庫 (Phase 2+) | PostgreSQL | 多用戶、雲端部署 |
| ORM | SQLAlchemy 2.x | 與 FastAPI 標準搭配 |
| 行動應用 | Flutter | 單一程式碼出 iOS + Android |
| 本機 LLM | Ollama | 現有，qwen2-vl 中文視覺效果好 |
| 本機圖像生成 | ComfyUI | 現有，已驗證流程 |
| 雲端 AI (未來) | Claude API / OpenAI | Phase 2+ 擴展，provider 模式切換 |

---

## 4. 資料模型

```
Project（小說專案）
├── id, title, author, cover_image_id, created_at, updated_at

Chapter（章節）
├── id, project_id, order_index
├── title, content (text)
├── created_at, updated_at
└── → AnalysisReport（分析報告）

Character（人物設定）
├── id, project_id
├── name, aliases (JSON array)
├── core_traits, behavior_rules, voice_style
├── forbidden_actions, notes
├── created_at, updated_at
└── → Illustration（肖像圖）

Illustration（插畫）
├── id, project_id
├── file_path, thumbnail_path
├── linked_chapter_id (nullable)
├── linked_character_id (nullable)
├── caption, ai_description
└── created_at

AnalysisReport（分析報告）
├── id, chapter_id
├── report_type (rhythm | consistency | rewrite)
├── content (JSON or text)
└── created_at
```

---

## 5. 開發分期

### Phase 1 — 後端基礎 + 資料層
**目標：** 把現有 CLI 工具轉換為有 API 的後端服務，建立正式資料模型

**範疇：**
- [ ] FastAPI 專案初始化
- [ ] SQLite + SQLAlchemy 資料庫設置
- [ ] Project / Chapter CRUD API
- [ ] Character CRUD API
- [ ] Illustration 上傳與管理 API
- [ ] 現有 AI 分析邏輯（rhythm、consistency、art）移植為 service
- [ ] 小說匯出 API（Markdown + 目錄）

**完成標準：** 可用 API client（Postman / curl）完整操作所有功能

---

### Phase 2 — Web UI
**目標：** 建立可日常使用的桌面 Web 介面，作為手機 App 前的完整使用者體驗驗證

**技術選型：** React + Vite（輕量、與 FastAPI 分離部署）

**範疇：**
- [ ] React 專案初始化
- [ ] 專案列表與建立頁
- [ ] 章節管理與文字編輯器（小說排版）
- [ ] 人物設定管理介面
- [ ] 插畫上傳與管理
- [ ] AI 分析結果呈現（節奏圖、一致性報告）
- [ ] 繪圖輔助問答介面
- [ ] 小說預覽

**完成標準：** 可在瀏覽器完成完整創作流程（建立專案→寫章節→管理角色→AI分析→看報告）

---

### Phase 3 — Flutter 行動應用
**目標：** 將 Web UI 驗證過的功能移植至手機，補充手機專屬互動

**範疇：**
- [ ] Flutter 專案初始化（iOS + Android）
- [ ] 核心功能移植（章節、角色、插畫、AI問答）
- [ ] 手機專屬功能（相機直接匯入插畫、推播通知）

**完成標準：** 可在手機上完成完整創作流程

---

### Phase 4 — 雲端 AI + 多用戶（未來）
**目標：** 支援雲端部署，讓其他創作者也能使用

**範疇：**
- [ ] PostgreSQL 遷移
- [ ] 用戶帳號系統
- [ ] Claude API / OpenAI 作為 AI provider 選項
- [ ] 雲端圖片儲存（S3-compatible）
- [ ] EPUB / PDF 匯出

---

## 6. AI 功能對應表

| 功能 | AI 來源 | Phase |
|------|---------|-------|
| 節奏分析 | 規則為主（無 LLM） | 1 |
| 一致性 surface scan | 規則為主（無 LLM） | 1 |
| 一致性 semantic scan | Ollama | 1 |
| 改寫建議 | Ollama | 1 |
| 草稿分析 / 完成圖評析 | Ollama vision | 1 |
| 配色建議 | Ollama vision | 1 |
| 構圖問答 | Ollama vision | 1 |
| 從劇情提取角色特徵 | Ollama | 1 |
| 從插畫提取視覺特徵 | Ollama vision | 1 |
| 角色設計問答 | Ollama | 1 |
| 風格強化 / 線稿化 | ComfyUI | 1 |
| 雲端 AI fallback | Claude / OpenAI | 3 |

---

## 7. 硬體假設（Phase 1-2）

- OS：Windows 11
- GPU：NVIDIA RTX 5070 Ti（本機 AI 運算）
- Ollama：本機服務，`http://localhost:11434`
- ComfyUI：本機便攜版，`http://localhost:8188`

---

## 8. 待決議

| 議題 | 狀態 | 備註 |
|------|------|------|
| EPUB / PDF 匯出優先度 | 未決 | Phase 1 先做 Markdown，夠用再加 |
| 離線 vs 連線模式 | 未決 | Phase 1 全本機，不涉及 |
| 是否需要 Web 版 | 未決 | Phase 3 再評估 |
