# Craftflow — Claude Instructions

本地優先的小說創作 + AI 生圖工具。FastAPI + React + ComfyUI + Ollama，全部跑在本機。

> **多 AI 協作**：規劃階段先寫根目錄 `AGENT_SYNC.md` 的 `§2.1 Claude 規劃`／`§2.4 整合分析`（順序 Claude → Codex → Gemini → Claude 整合），**經使用者在 `§2.5` 核可後才動碼**。規則見該檔 §0。

## 先讀哪裡（省 token）

| 需求 | 檔 |
|---|---|
| 該改哪個檔 / 生圖流程 | `doc/MODULE_MAP.md` |
| 待辦（唯一真相） | `doc/BACKLOG.md` |
| 顯存/共存/解析度 | `doc/VRAM分析報告.md` |
| 某段程式碼為什麼這樣寫 | `doc/reference/CODE_NOTES.md`（程式碼中 `# [CN-xxx]` 的完整根因） |
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
| 某底模家族的 prompt 配方 | `backend/prompt_profiles.yml` 的 `families:`（**以底模家族為鍵，新增／改名 workflow 免登錄**；只有新 checkpoint 需登錄 `checkpoint_styles.yml`）。個案實驗走 art_style（DB），不加 workflow 例外 |
| 生成旋鈕（VRAM 門檻、畫風權重、upsample 開關…） | 專案根 `.env`，定義見 `core/config.py` |
| 個人畫風標籤／個人負向（例：畫師、作品名） | 專案根 `.env` 的 `PERSONAL_STYLE_EXTRA_<家族>`／`PERSONAL_NEGATIVE_EXTRA_<家族>`（家族＝PromptStyle 大寫，如 `ANIMA`、`ILLUSTRIOUS`；疊加語義；`.env` 不進 git）。見 CN-115 |
| 家族生成策略（CN 上限、denoise 映射、能力開關） | `services/ai/gen_profile.py` 的 `GEN_PROFILE` |

## Coding Rules

1. **Surgical updates** —— 只改必要處，無關的不重構，保留既有架構與風格。
2. **Progressive feedback** —— 慢速 AI 任務需後端狀態 + 前端進度 UI。
3. **Resilient errors** —— Ollama/ComfyUI 失敗不可讓 app crash。
4. **改前先讀，動手前先說明 why**（根因不是症狀）。方向可能錯就直接反對，附證據。
5. 避免幻覺類別/函式；顧及效能與安全。

流程：Research → Propose → Explain risk → Apply

## 編程檢查點

1. 新增「會被執行的東西」時，**測試必須真的執行它**（曾因只驗欄位、沒跑 `.format()`，f-string 雙層大括號上線即 500）。
2. 改生成流程前確認**參數是不是節點參照** —— 作者型 workflow 用單一參數節點分送 KSampler 與 metadata。用 `wf_node_ops._set_node_input` 寫上游，別寫字面值到消費端。
3. 加 fallback／替代路徑時**確認前端不會把它擋死**（能力旗標要一路貫通到 UI，否則後端變死代碼）。
4. 改共用函式時列出所有呼叫端，特別注意 illustrious 家族路徑（現役 `Standard_V38`）。
5. `backend/tests/test_anima_family.py` 有 **illustrious 家族路徑鎖**（SYNC-007 前為 V37 零回歸鎖；V37 已退役、改指 V38）。斷言失敗＝改動污染 SDXL/illustrious 路徑 —— **回頭修，不可改斷言充當通過**。

## 沙箱陷阱（實證，違反必踩）

| 陷阱 | 對策 |
|---|---|
| 檔案工具寫掛載資料夾**檔尾截斷**，且 bash 後續讀取可能持續讀到殘檔 >15 分鐘 | 重要檔用 shell 寫入，寫完立刻驗檔尾 |
| `py_compile` **抓不到截斷**（斷點落在註解/docstring 尾時仍語法合法） | 改用 `ast.parse` + 比對預期函式/類別名稱：`{n.name for n in ast.walk(t) if hasattr(n,'name')}` |
| repo=LF、Windows 工作目錄=CRLF → git status 全檔假 modified | 寫檔沿用原檔換行符（`nl='\r\n' if '\r\n' in s else '\n'`） |
| 沙箱**不可直寫 SQLite**（掛載層不支援鎖定） | DB 變更給指令由使用者本機執行 |
| `git stash` / `git add` / `git commit` 在掛載層會留下刪不掉的 `.git/index.lock` | **沙箱不跑 git 寫入**。比對舊版用 `git show HEAD:path` 取到 /tmp |
| 前端改完沒 `npm run build` → 舊 bundle 造成誤判 | 前端改動後必提醒使用者 build |
| 沙箱缺套件（pytest/fastapi/sqlalchemy…） | 測試失敗先確認是否為缺套件而非改動所致 |

## Doc Rules

- **每日開發記錄** `doc/YYYY-MM-DD_開發記錄.md`：當天工作/決策/待辦只寫當天檔；跨日開新檔，開頭「承接 YYYY-MM-DD」。**禁止在舊日期檔補寫新內容。**
- **新待辦一律寫 `doc/BACKLOG.md`**，不要再開新規劃檔堆疊。
- **根因／踩坑結論寫 `doc/reference/CODE_NOTES.md`**，程式碼只留一行 `# [CN-xxx] <結論>`。推翻舊結論時**不刪舊條目**，在該條末尾加「訂正（日期）」。
- **函式／模組完整說明寫 `doc/reference/FUNCTION_DOCS.md`**，docstring 只留一行摘要＋`[FD-xxx]`；改行為時同步更新該條。註解不超過 3 行、不寫開發歷程（日期、代號、實測過程）。
- **規劃文件**：只更新 checkbox（🔲→✅）與狀態欄。
- 新發現的 bug 或推翻先前結論的證據 → 寫進當天記錄的「新發現」章節，附檔名行號。
- 月底把該月檔案移進 `doc/archive/YYYY-MM/` 並補 `YYYY-MM_摘要.md`。
