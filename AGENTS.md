# Craftflow — Agent Instructions (Codex 等未指定 AI 讀這份)

本地優先的小說創作 + AI 生圖工具。FastAPI + React + ComfyUI + Ollama，全部跑在本機。
`CLAUDE.md`（Claude）／`GEMINI.md`（Gemini）是同一套規則的各自版本，內容衝突時以本檔＋`CLAUDE.md`為準。

## 多 AI 協作（最重要，先讀）

- 規劃階段一律走根目錄 **`AGENT_SYNC.md`**，順序 **Claude → Codex → Gemini → Claude 整合 → 使用者裁決 → Claude 執行**。
- **Codex 的角色是規劃者**：只寫 `AGENT_SYNC.md` 的 `§2.2 Codex 規劃` 區塊，**不得修改任何程式碼**，也不得改他人區塊。
- 要改動 → 寫成「`檔名:行號` → 怎麼改、為什麼」的敘述，附證據。
- 寫完在區塊尾補 `<!-- HANDOFF: Codex DONE @ YYYY-MM-DD HH:MM -->`。
- 完整規則見 `AGENT_SYNC.md` §0。

## 先讀哪裡（省 token）

| 需求 | 檔 |
|---|---|
| 該改哪個檔 / 生圖流程 | `doc/MODULE_MAP.md` |
| 待辦（唯一真相） | `doc/BACKLOG.md` |
| 顯存/共存/解析度 | `doc/VRAM分析報告.md` |
| 文件導航 | `doc/INDEX.md` |
| 今天做到哪 | `python tools/session_status.py` |

**不要** `ls doc/` 逐檔猜、**不要** Read 整份開發記錄（用 `grep -n` 定位段落再讀）。

## 架構鐵則

- **Local-First**：AI 只用 Ollama + ComfyUI，無雲端 API（除非明確指示）。
- **Human-in-the-Loop**：絕不覆蓋原始創作內容；AI 產出只進分析報告／獨立欄位。
- **最小程式架構組成通用廣泛工具** —— 所有改動以此為準繩。
- **Docker → Host**：容器內用 `host.docker.internal`；本機直跑用 `localhost`。

## Stack

| 層 | 技術 |
|---|---|
| Backend | FastAPI · SQLAlchemy 2.0 · Pydantic v2 · SQLite · Python 3.11 |
| Frontend | React 18 · Vite 5 · Vanilla CSS-in-JS |
| LLM | 文字/視覺模型由設定 UI 切換（清單來自 Ollama `/api/tags`，存 `data/runtime_state.json`）。fallback 見 `core/config.py` |
| Image | ComfyUI `:8188`（SDXL · CN Union ProMax · IPA · Anima LLLite） |
| Ollama | `:11434` |
| LoRA 訓練 | kohya_ss（subprocess） |

## 零程式碼的設定點（優先用這些，別改碼）

| 要做的事 | 改哪裡 |
|---|---|
| 新 checkpoint 歸哪個 family | `backend/checkpoint_styles.yml`（`checkpoints:` 與 `families:` **兩區都要加**） |
| 某 workflow 專屬 prompt 覆寫 | `backend/prompt_profiles.yml`（名單制，未登錄＝零介入） |
| 生成旋鈕（VRAM 門檻、畫風權重、upsample 開關…） | 專案根 `.env`，定義見 `core/config.py` |
| 家族生成策略（CN 上限、denoise 映射、能力開關） | `services/ai/gen_profile.py` 的 `GEN_PROFILE` |

## Coding Rules

1. **Surgical updates** —— 只改必要處，無關的不重構，保留既有架構與風格。
2. **Progressive feedback** —— 慢速 AI 任務需後端狀態 + 前端進度 UI。
3. **Resilient errors** —— Ollama/ComfyUI 失敗不可讓 app crash。
4. **改前先讀，動手前先說明 why**（根因不是症狀）。方向可能錯就直接反對，附證據。
5. **Permission First** —— 沒有明確指令不動任何程式碼。
6. 避免幻覺類別/函式；顧及效能與安全。

流程：Research → Propose → Explain risk → Apply

## 編程檢查點（規劃時就要納入考量）

1. 新增「會被執行的東西」時，**測試必須真的執行它**。
2. 改生成流程前確認**參數是不是節點參照** —— 作者型 workflow 用單一參數節點分送 KSampler 與 metadata。用 `wf_node_ops._set_node_input` 寫上游，別寫字面值到消費端。
3. 加 fallback／替代路徑時**確認前端不會把它擋死**（能力旗標要一路貫通到 UI，否則後端變死代碼）。
4. 改共用函式時列出所有呼叫端，特別注意已定版的 `Standard_V37`。
5. `backend/tests/test_anima_family.py` 有 **V37 零回歸鎖**。斷言失敗＝改動污染定版路徑 —— **回頭修，不可改斷言充當通過**。

## 沙箱陷阱（實證，違反必踩）

| 陷阱 | 對策 |
|---|---|
| 檔案工具寫掛載資料夾**檔尾截斷**，且 bash 後續讀取可能持續讀到殘檔 >15 分鐘 | 重要檔用 shell 寫入，寫完立刻驗檔尾 |
| `py_compile` **抓不到截斷** | 改用 `ast.parse` + 比對預期函式/類別名稱 |
| repo=LF、Windows 工作目錄=CRLF → git status 全檔假 modified | 寫檔沿用原檔換行符 |
| 沙箱**不可直寫 SQLite** | DB 變更給指令由使用者本機執行 |
| `git stash` / `git add` / `git commit` 在掛載層會留下刪不掉的 `.git/index.lock` | **沙箱不跑 git 寫入** |
| 前端改完沒 `npm run build` → 舊 bundle 造成誤判 | 前端改動後必提醒使用者 build |

## Doc Rules

- **每日開發記錄** `doc/YYYY-MM-DD_開發記錄.md`：當天工作/決策/待辦只寫當天檔；跨日開新檔，開頭「承接 YYYY-MM-DD」。**禁止在舊日期檔補寫新內容。**
- **新待辦一律寫 `doc/BACKLOG.md`**，不要再開新規劃檔堆疊。
- **規劃文件**：只更新 checkbox（🔲→✅）與狀態欄。
- 多 AI 規劃過程寫 `AGENT_SYNC.md`，結案後歸檔到 `doc/agent_sync/`。
