# Craftflow — Agent Instructions（Codex 等未指定 AI 讀這份）

本地優先的小說創作＋AI 生圖私人工具（FastAPI + React + Ollama + ComfyUI，全在本機）。AI 只給建議，決策權在創作者。

> `CLAUDE.md`（Claude）／`GEMINI.md`（Gemini）是同一套規則的各自版本，內容衝突時以本檔＋`CLAUDE.md` 為準。
> 本檔只放**長期有效**的規則與地雷。「今天做到哪」→ `python tools/session_status.py`、最新 `doc/YYYY-MM-DD_開發記錄.md`、`doc/BACKLOG.md`。

## 0. 開工順序（省 token）

1. `python tools/session_status.py`：一次拿 git／前端 build 狀態、BACKLOG 各區未完成數、最新記錄的「接續摘要」。
2. 需要細節才讀單段：`--section <標題字>`（最新記錄）、`--section <字> --file doc/BACKLOG.md`、`--area <區塊標題字>`（列某區未完成項）。**不讀整份記錄、不 `ls doc/` 逐檔猜、不翻 `doc/archive/`**（歷史先看月摘要）。
3. 要改碼：`doc/MODULE_MAP.md` 定位檔案 → `doc/reference/CODE_NOTES.md` 查該段 `[CN-xxx]` 根因 → 再讀原始碼。

| 需求 | 檔 |
|---|---|
| 該改哪個檔／生圖主流程 | `doc/MODULE_MAP.md` |
| 待辦（唯一真相） | `doc/BACKLOG.md` |
| 某段程式碼為什麼這樣寫 | `doc/reference/CODE_NOTES.md`（`# [CN-xxx]`） |
| 函式完整行為說明 | `doc/reference/FUNCTION_DOCS.md`（`[FD-xxx]`） |
| 顯存／共存／解析度 | `doc/VRAM分析報告.md` |
| 文件導航／歷史決策 | `doc/INDEX.md`、`doc/archive/YYYY-MM_摘要.md` |
| ComfyUI 端實驗工作流 | `F:\wk\ComfyUI_portable\*_工作流說明.md` |

## 1. 協作模式（最重要，先讀）

- 規劃一律走根目錄 **`AGENT_SYNC.md`**，順序 **Claude → Codex → Gemini → Claude 整合 → 使用者裁決 → Claude 執行**。完整規則見該檔 §0。
- **Codex 的角色是規劃者**：只寫 `AGENT_SYNC.md` 的 `§2.2 Codex 規劃` 區塊，**不得修改任何程式碼、設定檔或文件**，也不得改他人區塊。
- 要改動 → 寫成「`檔名:行號` → 怎麼改、為什麼」，附證據（程式碼行、log 行）。反駁他案寫在自己區塊的「對他案的意見」。
- 寫完在區塊尾補 `<!-- HANDOFF: Codex DONE @ YYYY-MM-DD HH:MM -->`；沒有上一棒的 HANDOFF 行代表上一棒未完成。
- 下文的「改動規則」（§8～§14）是讓規劃內容可執行、可驗收的依據：規劃要寫出受影響的呼叫端、要跑的測試與負向對照。

## 2. 使用者硬性要求

| 規則 | 做法 |
|---|---|
| **不自行調查 DB** | 不開 `backend/craftflow.db`（含唯讀、含 SQL）。需要資料 → 給 SQL／查詢方向，由使用者本機執行後回報 |
| 結論先行、該反對就反對 | 附證據（`檔名:行號`、log 行），不過度稱讚 |
| 被一次實測推翻就停 | 立刻回頭驗證前提，不在錯的前提上疊推論 |
| 需求不清就問 | 不猜規格；不幻覺類別／函式 |

## 3. 架構鐵則

- **最小程式架構組成通用廣泛工具**：所有改動以此為準繩。收斂共用路徑，不為單一 workflow／模型開例外分支（prompt 配方以**底模家族**為鍵，不以 workflow 檔名）。
- **Local-First**：AI 只用 Ollama + ComfyUI，無雲端 API（除非明確指示）。
- **Human-in-the-Loop**：絕不覆蓋原始創作內容；AI 產出只進分析報告／獨立欄位。
- **Surgical updates**：只改必要處，無關的不重構，保留既有架構與風格。
- **Progressive feedback**：慢速 AI 任務需後端狀態＋前端進度 UI。
- **Resilient errors**：Ollama／ComfyUI 失敗不可讓 app crash，錯誤字串不可當成結果顯示（CN-123）。
- **Permission First**：沒有明確指令不動任何程式碼。
- 流程：Research → 根因 → Propose → Explain risk →（使用者核可後由 Claude）Apply。

## 4. 執行環境

| 項目 | 值 |
|---|---|
| 硬體 | Windows 11 · RTX 5070 Ti 16GB |
| Backend | FastAPI · SQLAlchemy 2.0 · Pydantic v2 · SQLite · Python 3.11；`start.bat` → uvicorn `127.0.0.1:8000`（`--reload-dir app`），venv 在 `backend/.venv` |
| Frontend | React 18 · Vite 5 · CSS-in-JS；dev `:3000`。**改前端後提醒使用者 `cd frontend && npm run build`**，舊 bundle 會造成誤判 |
| Ollama | `:11434`；文字／視覺模型由設定 UI 切換，存 `data/runtime_state.json`；fallback 見 `core/config.py` |
| ComfyUI | `F:\wk\ComfyUI_portable`，`:8188`，啟動 `run_amazingSP_v3.bat`（無 FP8；v2 的 FP8 旗標會降畫質） |
| Log | `data/logs/backend.log`（**不是** `backend/logs/`） |
| Workflow | **`data/custom_workflows/`** 才是 runtime 讀的（必須 API 格式；退役檔在 `history/`）。`ComfyUI/user/default/workflows/craftflow/` 是同名**影子檔**，改了無效 |
| 測試 | `cd backend && pytest` |
| Docker | 容器內用 `host.docker.internal`；本機直跑用 `localhost`／`127.0.0.1` |

## 5. 兩大底模家族（多數 bug 出在這條分界）

| | illustrious（SDXL 系） | anima |
|---|---|---|
| 載入節點 | `CheckpointLoaderSimple` | `UNETLoader` ＋ `CLIPLoader`（Qwen 編碼器） |
| 模型位置 | `models/checkpoints/` | `models/diffusion_models/` |
| 現役 workflow | `Standard_V38`／`Advanced_V38`（V39 新增中） | `AnimaStandardV9_*`（`miaomiaoHarem` 為主力） |
| 結構控制 | CN Union ProMax ＋ IPA | 無 CN／IPA → LLLite → img2img 替代鏈（CN-125） |
| FaceDetailer | workflow 內建 | 後端注入（CN-120） |

- `/settings/checkpoints` 只列 `CheckpointLoaderSimple` 的選項 → Anima UNet 永遠不在清單，Anima 一律走「自訂 Workflow」模式。
- 任何「找到 `CheckpointLoaderSimple` 才動作」的程式在 Anima 下會**靜默跳過**（LoRA 注入曾如此，CN-124）。新增節點手術時兩種載入器都要處理。
- LoRA 架構須與底模相符（SDXL／Illustrious LoRA 掛 Anima 無效）。
- `checkpoint_styles.yml` 是**子字串、依序命中**：`animagineXL` 必須排在 catch-all `anima` 之前；新 checkpoint 的 `checkpoints:` 與 `families:` 兩區都要加。
- Anima tag 順序：作品／畫師在 `1girl` 之後、一般 tag 之前；Aesthetic 版正負向皆禁 `score_*`。
- **改 workflow JSON 裡的 prompt 文字對產線無效**（`wf_node_ops._inject_prompts` 會覆寫）→ 產線 prompt 改 `prompt_engine/styles.py` 模板或 `prompt_profiles.yml`。
- 能力閘控是**前端＋API 雙層**（`CharacterDetailView.jsx` 的 `cnUsable`／`ipaSupported` ＋ `api/art_generate.py` 守門）。加 fallback 兩層都要改，否則後端分支是死碼。

## 6. 零程式碼設定點（優先用這些，別改碼）

| 要做的事 | 改哪裡 |
|---|---|
| 新 checkpoint 歸哪個 family | `backend/checkpoint_styles.yml`（見 §5 順序規則） |
| 某底模家族的 prompt 配方 | `backend/prompt_profiles.yml` 的 `families:`（新增／改名 workflow 免登錄）。個案實驗走 art_style（DB），不加 workflow 例外 |
| 生成旋鈕（VRAM 門檻、逾時、開關…） | 專案根 `.env`，定義與預設值只看 `core/config.py` |
| 個人負向（例：halo） | `.env` 的 `PERSONAL_NEGATIVE_EXTRA_<家族>`（家族＝PromptStyle 大寫；疊加語義）。CN-115 |
| 客製化標籤（作品／繪師下拉） | `data/custom_tags.json`（格式見 `custom_tags.example.json`；免重啟）。CN-122 |
| 角色外觀年齡／身材卡片 | `backend/appearance_cards.yml` 的 `cards:`／`body_groups:`（兩家族共用；只用 Danbooru tag、一卡一核心 tag、不加權；免重啟）。CN-129／CN-130 |
| 家族生成策略（CN 上限、denoise 映射、能力開關） | `services/ai/gen_profile.py` 的 `GEN_PROFILE` |

## 7. 除錯鐵律

1. **先確認 runtime 實際載入什麼，再分析。** 看 `data/logs/backend.log`：`[wf-load]`（實際 workflow 路徑）、`[capability]`、`[lllite]`／`[img2img]`／`[lora]`／`[face-detailer]`（是否真的注入）、`[nsfw-guard]`、`[vision-cache]`。記憶／文件中的路徑、行號、設定，使用前先對現況驗證。
2. **找缺席的證據**：log grep 零命中、UI 耗時表少一列 → 那條路徑根本沒跑。改參數前先確認路徑真的有執行，不要調死碼。
3. prompt 有沒有吃到家族配方：看 `generation_history.params.prompt_profile`（SQL 交給使用者查）；是 fallback 就先別評畫質。
4. 視覺抽取怪、或改了 vision prompt 沒效果：`backend/data/vision_cache.json` 的 key＝`模式|模型|圖hash`，**不含 prompt** → 清快取＋重啟後端。
5. 視覺模型回空／極慢：先印 `RAW(len=…)` 區分「真空回／thinking 燒光 `num_predict`／不照格式」。thinking 類 VL 的 `think:false` 可能無效，結構化抽取用非 thinking 模型。
6. 比對舊版程式碼：`git show HEAD:<path> > /tmp/…`。考古「以前那張比較好」：`generation_history.created_at` 是 UTC、`backend/uploads/` 檔案 mtime 是 CST（+8h）。

## 8. 編程檢查點

1. 新增「會被執行的東西」時，**測試必須真的執行它**（曾因只驗欄位、沒跑 `.format()`，f-string 雙大括號上線即 500）。
2. workflow 參數可能是**節點參照**（作者型 workflow 用單一參數節點分送 KSampler 與 metadata）→ 用 `wf_node_ops._set_node_input` 寫上游，別把字面值寫到消費端。
3. 改共用函式先列出所有呼叫端，特別注意 illustrious 路徑。
4. 能力旗標要一路貫通到 UI（§5 雙層閘控）。
5. Prompt 工程：
   - `(text)` 在 `CLIPTextEncode` 是權重語法，tag 內不可用括號做註記。
   - LLM 模板**不要列舉禁用詞**（會誘發該 token）→ 改正向措辭、字面連子字串都不出現（`palette` 含 `pale`）；測試斷言「字面不存在」。
   - 只用 Danbooru 實際 tag（複數 `red eyes`）；清理 regex 要涵蓋單複數。
   - 看到「清理器在處理某壞格式」→ 先查產生端是不是我們自己。
   - 替換含 `\n` 的大段文字用 `str.replace`，不要 `re.sub`（repl 的 `\n` 會被解譯）。

## 9. 測試規則

- 改動前先跑一次，記下**既有失敗集合**；改動後比對集合相同。新增的失敗＝自己造成。
- `tests/test_anima_family.py` 的 illustrious 路徑鎖、`tests/golden/` 快照：斷言失敗＝污染定版路徑 → **回頭修，不可改斷言充當通過**。
- 名單制設定（yml 登錄才生效）的測試要**反向列舉真實來源**（磁碟目錄），不寫死鍵名清單。
- 新增護欄必跑**負向對照**：還原成缺陷版確認會紅燈。
- 「檔案不存在就 skip」的測試可能長期靜默失效（V37 鎖曾整組被 skip）；skipped 數量變動要追原因。
- mock／patch 目標要跟著實作走（`requests.get` 改 `SESSION.get` 後舊測試曾空轉）。
- `conftest.py` 已隔離本機 `.env`，測試不可依賴個人設定。
- 失敗先排除「沙箱缺套件／FastAPI 版本差」再判斷是否為改動所致。

## 10. 環境陷阱（實證，規劃時納入）

| 陷阱 | 對策 |
|---|---|
| 檔案工具寫掛載資料夾會**檔尾截斷**，後續讀取可能持續讀到殘檔 | 重要檔用 shell／python 寫入；寫完立刻驗行數與檔尾 |
| `py_compile` 抓不到截斷（斷點在註解／docstring 尾仍合法） | `ast.parse` ＋ 比對預期函式／類別名集合 |
| repo=LF、Windows 工作樹=CRLF | 寫檔沿用原檔換行符（`nl='\r\n' if '\r\n' in s else '\n'`） |
| 沙箱不可寫 SQLite（掛載層無鎖）；DB 欄位靠啟動時自動補欄 | DB 變更給指令由使用者本機執行 |
| `git add`／`commit`／`stash` 在掛載層留下刪不掉的 `.git/index.lock` | **沙箱不跑 git 寫入**；commit 指令交給使用者。已誤觸就給 PowerShell 清 lock 指令 |
| `.bat` 含中文 → `chcp 65001` 下 cmd 讀取位移錯亂，從行中間執行 | `.bat` 一律純 ASCII，說明另放 `.md` |
| `.bat` 傳給 Python CLI 的 `*` 會被展開（`--reload-exclude` 事件） | 用「指定要看哪裡」（`--reload-dir`），不用 glob 排除 |
| ComfyUI 與 sd-scripts 共用 pyenv 3.11.9 site-packages（torch nightly cu132） | **禁止 `pip install -r requirements.txt`**，只 `--no-deps` 點名升級；pip 指令請使用者本機跑 |
| 憑對稱性推測 CLI 旗標存在（`--normalvram` 事件） | 改旗標前先查該版本 `--help` |

## 11. 隱私與版控

- GitHub `amazingsora/Craftflow` 是**公開 repo**，遠端只留 `main`。隱私處理與歷史改寫都以此為前提。
- 不進 git：`.env`、`doc/`（已從全歷史清除，只存本機）、`data/custom_tags.json`、log／cache／產出圖、`Claude outputs/`。
- 個人畫風標籤／個人負向只放 `.env` 或 `data/custom_tags.json`，**不進 yml、測試、`.env.example`**。
- 服務只綁 `127.0.0.1`；CORS 讀 `config.CORS_ORIGINS`；輸出 PNG 預設剝除 metadata（`PNG_STRIP_METADATA`）。
- commit／push／歷史改寫一律使用者本機執行（`tools/privacy_cleanup.ps1`）。

## 12. 內容護欄

- 規則唯一來源 `services/ai/prompt_engine/content_guard.py`（CN-118）。`.env` `NSFW_GUARD_ENABLED` 只管成人內容；**未成年情境永遠強制、無開關**。
- 未成年外觀卡片（兒童／少年少女）須等護欄還原後才加入 `appearance_cards.yml`；護欄現況看 BACKLOG P-09。
- 動 `wf_node_ops._inject_prompts`、`compiler._sanitize_to_list`、`character_design_service` 的 prompt 組裝時，確認護欄呼叫沒被帶掉。

## 13. 程式碼品質

- 註解 ≤3 行，**不在程式碼寫開發歷程**（日期、SYNC／A3 等代號、實測過程、回滾說明）。
- 根因／踩坑 → `CODE_NOTES.md`，程式碼只留一行 `# [CN-xxx] <結論>`；編號接續最大號；推翻舊結論**不刪舊條目**，在末尾加「訂正（日期）」。
- 超過 3 行的函式說明 → `FUNCTION_DOCS.md`，docstring 只留一行摘要＋`[FD-xxx]`；改行為時同步更新該條。
- 死碼：未來擴充用不到就刪；未來需要或仍待評估的保留，並在 BACKLOG 註記。
- 整合重複碼時行為逐字保留，以「測試失敗集合不變」驗證。
- 避免 magic number，旋鈕進 `core/config.py` 或 yml。

## 14. Doc Rules

- **每日開發記錄** `doc/YYYY-MM-DD_開發記錄.md`：當天工作／決策／待辦只寫當天檔；跨日開新檔，開頭「承接 YYYY-MM-DD」。**禁止在舊日期檔補寫新內容。**
- **接續摘要**：每份記錄在「承接」行之後放 `## 接續摘要`（≤15 行，固定五列：狀態／決策／待辦（→ BACKLOG 區號）／新發現（一行一條）／下一步），細節寫在後面章節。**每次收工前更新這段**；下次開場只讀它。
- 使用者裁決寫成「決策（MM-DD）：…」；新發現或推翻先前結論的證據寫進當天「新發現」章節，附 `檔名:行號`。
- **新待辦一律寫 `doc/BACKLOG.md`**，不開新規劃檔堆疊；規劃文件只更新 checkbox（🔲→✅）與狀態欄。項目完成（含本機驗收）或否決後，整列移到 `doc/archive/BACKLOG_done.md`，BACKLOG 只留未完成項。
- AGENT_SYNC 議題結案後歸檔到 `doc/agent_sync/`，遺留轉 BACKLOG。
- 改動大檔順手更新 `MODULE_MAP.md` 行數；`INDEX.md`「當前活躍」過期要更新。
- 月底把該月檔案移進 `doc/archive/YYYY-MM/` 並補 `YYYY-MM_摘要.md`（定案決策＋根因記錄兩節，約 30～50 行）；BACKLOG／CODE_NOTES 內指向舊檔的路徑同步改成 archive 路徑。
