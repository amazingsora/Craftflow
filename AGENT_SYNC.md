# AGENT_SYNC — 多 AI 協作交流板

> Craftflow 的**規劃階段**共用工作區。三個 AI 在此各寫各的規劃，由 Claude 整合、使用者裁決、Claude 執行。
> 架構鐵則以 `CLAUDE.md` / `GEMINI.md` / `AGENTS.md` 為準，本檔只定義**協作流程**，不重複架構內容。

---

## 0. 規則（任何 AI 進來先讀這段）

### 0.1 角色與邊界

| 角色 | 身分 | 可寫區塊 | 可否改 code |
|---|---|---|---|
| **Claude** | 規劃者 + **唯一執行者** | `§2.1 Claude 規劃`、`§2.4 整合分析`、`§2.6 執行紀錄` | ✅ 但**限**使用者在 `§2.5` 核可後 |
| **Codex** | 規劃者 | `§2.2 Codex 規劃` | ❌ 規劃階段禁止動 code |
| **Gemini** | 規劃者 | `§2.3 Gemini 規劃` | ❌ 規劃階段禁止動 code |
| **使用者** | 決策者 | `§1 議題卡`、`§2.5 裁決` | — |

**硬規則**

1. **只寫自己的區塊。** 不得修改、刪除、重寫他人區塊。要反駁別人 → 寫在自己區塊的「對他案的意見」小節。
2. **規劃階段零 code 變更。** 只准讀檔、grep、寫本檔。要改動請寫成「檔名:行號 → 怎麼改」的敘述。
3. **附證據。** 任何主張要能指到 `檔名:行號` 或指令輸出，不接受「應該是…」。
4. **未經 `§2.5` 使用者裁決，不得進入執行。** 違反視同流程失敗。
5. **寫完在自己區塊結尾補交接標記**（見 0.3），下一棒才知道可以動了。
6. 遵守既有 Doc Rules：新待辦最終仍歸 `doc/BACKLOG.md`，本檔只承載「決策過程」。

### 0.2 流程

```mermaid
flowchart LR
    U[使用者提議題<br/>填 §1 議題卡] --> C1[Claude 規劃<br/>§2.1]
    C1 --> X[Codex 規劃<br/>§2.2]
    X --> G[Gemini 規劃<br/>§2.3]
    G --> C2[Claude 整合分析<br/>§2.4 比較表+建議]
    C2 --> U2{使用者裁決<br/>§2.5}
    U2 -->|核可| E[Claude 執行<br/>§2.6 紀錄]
    U2 -->|退回| C1
    E --> A[歸檔 §3<br/>待辦寫回 doc/BACKLOG.md]
```

### 0.3 交接標記

每個 AI 寫完自己的規劃，**最後一行**補上：

```
<!-- HANDOFF: <AI 名> DONE @ YYYY-MM-DD HH:MM -->
```

沒有這行 = 上一棒還沒寫完，**不要開始寫**。

### 0.4 議題狀態

| 記號 | 意義 |
|---|---|
| 🔲 | 待規劃（議題卡已開，Claude 尚未動筆） |
| 🟡 | 規劃中（三方輪流填寫） |
| 🟢 | 待裁決（`§2.4` 已完成，等使用者） |
| 🔵 | 執行中 |
| ✅ | 已結案（待歸檔） |
| ⬛ | 已否決／擱置 |

---

## 1. 目前議題

> ✍️ 本卡由 Claude 依使用者 2026-09-23 對話裁決代擬（「家族當預設就好」「不要有固定配方，移除」「不等 Gemini 原文，先寫 §2.1」）。Codex／Gemini 以本卡為準。
> ID 說明：`SYNC-006` 已被 2026-09-20 的 N14（`/free` 量測時機）非正式使用（見 `doc/BACKLOG.md` D 節、`CODE_NOTES.md`），為避免撞號本案取 `SYNC-007`。

| 欄位 | 內容 |
|---|---|
| **ID** | `SYNC-007` |
| **標題** | prompt 配方改以「底模家族」為鍵：移除 workflow 檔名層、V37 定版配方退役、illustrious 換 R1 配方；**追加軌 P：個人自訂標籤分家族 `.env`** |
| **提出者 / 日期** | amazingsora / 2026-09-23 |
| **前案** | `SYNC-005` 提前歸檔至 `doc/agent_sync/2026-09-23_SYNC-005_畫風太平塗-Anima條件控制.md`；遺留本機項目轉 `doc/BACKLOG.md` §A9。本案沿用其證據，不接手其遺留項 |
| **目標** | ① 新增／改名 workflow（如 `Standard_V41`）**不必改 yml**，底模已知即生效<br>② 從結構上消滅「檔名脫鉤 → 靜默降級」（07-25、08-22、09-15、09-19 已發生四次）<br>③ illustrious 家族換成 09-23 ComfyUI 驗證過的 R1 配方<br>④ V37 定版配方退役；「V37 零回歸鎖」改為「illustrious 家族路徑鎖」 |
| **軌** | **M｜yml 結構遷移**（零行為變更，先做）<br>**R｜illustrious 配方換 R1**（單一變因，M 驗收後才做）<br>**T｜測試改寫＋反向護欄**<br>**D｜文件同步**<br>**P｜個人自訂標籤分家族 `.env`**（09-23 追加；R 驗收後才做，單一變因；規劃見 §2.1-P） |
| **範圍限制** | ① 不動 `custom_workflows` 節點與 widget<br>② `anima` 家族配方**逐字搬移**，本案不調<br>③ 不改 `checkpoint_styles.yml` 兩區重複問題（轉 BACKLOG）<br>④ 不改 `gen_profile.GEN_PROFILE`<br>⑤ 不保留 workflow 例外層（使用者裁決）；個案實驗改走 art_style（DB）<br>⑥（軌 P）個人標籤**只放 `.env`**（09-23 起不進 git），不進 yml／不進 DB |
| **驗收標準** | **M**：磁碟上每支 workflow 解析出的 `quality_prefix / negative / negative_extra / style_extra / style_extra_weight` 與遷移前**逐字相同**（比對腳本）<br>**R**：露碧娜 × `Standard_V38` × seed 17021106 × IPA 0.2 × CN 0.75 → 正向尾端為 R1 畫風段、全文無 `flat color`；目視接近 R1 參考圖<br>**T**：`cd backend && pytest tests/` 全綠；新護欄對「複製一支 V41」零登錄通過、對「未知 checkpoint」紅燈<br>**共同**：新增 workflow 不需碰 yml<br>**P**：未設個人鍵 → prompt 與改動前逐字相同；設鍵 → 只作用於該家族，illustrious 出圖接近 ComfyUI K2 |
| **狀態** | 🔵 執行中（軌 M／R／P 程式面完成並驗證；待使用者本機 pytest、R／P 實機驗收、commit） |

> 09-23 15:40 追加軌 P（使用者：「Anima 額外客製標籤用 `blue archive, @kozaki yuusuke`，以 `.env` 處理且不參與 git，由使用者自行添加」「SDXL 測試後沒問題走 B」）。併入本案而非另開 SYNC-008：本案 M 尚未 commit、R 未做，另開會第五度提前歸檔；且 P 與 R 改的是同一條 `style_extra` 組裝鏈。

> 開新議題：把本區塊換成新議題卡，舊議題整段移到 `doc/agent_sync/`（見 §3）。

---

## 2. 規劃區

### 2.1 Claude 規劃

#### 〇、結論（先講）

**`prompt_profiles.yml` 以 workflow 檔名為鍵，但它實際上從來只有「每個底模家族一份配方」。**
18 個登錄鍵只有 3 份相異配方（E1），沒有任何一支 workflow 需要與同家族不同的配方；
而檔名鍵每換一次版號就要補登錄，漏了就靜默降級（E4）。改成以**底模家族**為鍵後：

```
改前：workflow 檔名 ──(名單查表，漏登錄＝靜默降級)──► 配方
改後：workflow ─► 內嵌 checkpoint ─► checkpoint_styles.yml ─► PromptStyle ─► families[style] ─► 配方
                                              （既有機制，_detect_style 已在用）
```

優先序：`art_style（DB）` ＞ `families[style]`（yml）＞ `STYLE_CONFIG`（程式內建，pony／noobai／sdxl 等未調校家族）＞ `.env`（僅 style_extra）

改動集中在一個咽喉點 `workflow_builder._profile_for()`（E5），**不改任何函式簽章與呼叫端**。
執行拆兩步：**M（結構遷移、零行為變更）→ 驗收 → R（換 R1 配方）**，確保「結構」與「配方」兩個變因分開驗。

---

#### 一、證據

**E1｜18 個登錄鍵＝3 份配方（零例外）**（讀 `backend/prompt_profiles.yml` 依配方分組）

| 配方 | 登錄鍵 | 在磁碟 |
|---|---|---|
| illustrious（`&illustrious_fabricatedxl`，`prompt_profiles.yml:48`） | Standard_V37 / Standard_V38 / Advanced_V38 / Standard_V38_NOVE | V37 ✗ |
| V35 黃金對照（`prompt_profiles.yml:121`） | Standard_V35 | ✗ |
| anima（`&anima_aesthetic_turbo`，`prompt_profiles.yml:151`） | V8 / V8turbo / V8_Aesthetic / V8_trubo11 / Advanced×2 / `_0919`×4 / V8_base10 / V9×2 | V8、V8turbo、V8_base10 ✗ |

磁碟上 13 支 workflow 全部是某個 anchor 的原樣複製（`<<: *anchor`，無任何欄位覆寫）。

**E2｜V37 零回歸鎖早已失效**
- `data/custom_workflows/Standard_V37.json` 不存在（只在 `history/`）。
- `tests/test_anima_family.py:31-35` 的 `_load()` 遇檔案不存在即 `pytest.skip` → `:233`、`:697`、`:866`、`:1009` 四組 V37 鎖**一直被跳過**。
- 仍在跑的只有 `:242`（驗 `STYLE_CONFIG[ILLUSTRIOUS]`，家族層）與 `:250`（驗「V37 有登錄」，本案刪除）。
- 同型教訓：`feedback_test_locks_wrong_target`（鎖不存在的對象＝沒鎖）。

**E3｜家族解析已存在，且鍵空間與下層一致**
- `workflow_builder.py:447 _detect_style()`：workflow → `capability.extract_checkpoint_from_wf` → `checkpoint_styles.yml` 的 `checkpoints:` 區 → `PromptStyle`。
- `prompt_engine/styles.py:344 STYLE_CONFIG: dict[PromptStyle, StyleConfig]` —— yml 家族層直接疊在它上面，**同一組鍵**（`illustrious`／`anima`／`sdxl`…）。

**E4｜檔名鍵的靜默降級史**：07-25 novaAnimeXL 漏登錄、08-22 V8turbo 漏登錄、09-15 V37→V38 改名六支全 miss（SYNC-001）、09-19 `Standard_V38_NOVE` 未登錄（SYNC-005 E10）。SYNC-001 的對策（anchor＋warn-once＋磁碟反向護欄）是**止血**，每次新增仍要人記得登錄。

**E5｜單一咽喉點**：所有讀取都經 `workflow_builder.py:112 _profile_for()`：
`_workflow_profile_overrides()`（:133）、`_workflow_style_extra()`（:159）、`_prompt_profile_source()`（:190）；
`_resolve_prompt_overrides()`（:175）再包前者。外部呼叫端只有 `character_design_service.py:50-55, 470, 664, 700`（grep `app/` 全域確認）。

**E6｜R1 配方實證（2026-09-23）**
- ComfyUI `output/CharDesign_V38_IPA/final_00001_.png`：fabricatedXL_v70、seed 17021106、28 步、CFG 6、euler_a、CN Union Canny 100/200 0.75/0→0.85、IPA plus ViT-H 0.2 linear（參考 `char_concept_ref.png`），使用者評「還不錯」。
- 同條件換回 Craftflow #815 原 prompt（`final_00002_`）明顯較平 → 差異只在 prompt。
- R1 與 2026-06-09 最佳圖（`output/2026-06-09-004800_fabricatedXL_v70_17021106.png`，由 dHash 比對 729 張尋回、嵌入 workflow 完整）同方向：**畫風段放最後、不加權、不含 `flat color`**。

**E7｜`style_extra_weight: 1.0` 正是 R1 的組裝方式**
`character_design_service.py` final_positive 組裝處：`_style_weight != 1.0` → 加權並**前置**；`== 1.0` → `style_extra_str` **接在最尾端**。
`prompt_profiles.yml:110` 註解稱 1.0 是應避免的退化行為（[CN-048] 的 chunk 稀釋顧慮）—— **E6 實測推翻**，須在 CODE_NOTES 對 CN-048 加訂正。

---

#### 二、設計決策

| # | 決策 | 理由 |
|---|---|---|
| D1 | 鍵＝`PromptStyle` 值（`_detect_style(workflow).value`，來源 `checkpoint_styles.yml` 的 `checkpoints:` 區） | 與下層 `STYLE_CONFIG` 同鍵空間（E3）。**不用** `capability.resolve_family`（`families:` 區）：兩區有差異，例 `AnythingXL → anythingxl`（checkpoints）vs `sdxl`（families），混用會讓 prompt 層與 STYLE_CONFIG 對不上 |
| D2 | yml 頂層鍵 `profiles:` → `families:`；舊 `profiles:` **不再讀取**，存在時 WARNING 一次「舊格式已停用」 | 使用者裁決不保留 workflow 層；不做雙軌相容以免兩份真相 |
| D3 | 函式名與簽章全部不改（`_profile_for(workflow)` 仍收檔名，內部轉 style） | Surgical；呼叫端零改動（E5） |
| D4 | miss 告警改以 style 為單位 warn-once；訊息改為「家族 X 未在 prompt_profiles.yml 設定 → 使用 STYLE_CONFIG 內建」 | pony／sdxl 等未調校家族落回內建是**預期行為**，不該每支 workflow 各吵一次 |
| D5 | debug 來源標註：`family: illustrious`／`family fallback (STYLE_CONFIG: sdxl)`，保留 `+art_style#id` | DEBUG prompt 一眼看出吃到哪層 |
| D6 | 將來 Anima **Base** 版（score 規則與 aesthetic 相反）不預留結構，需要時走 art_style | YAGNI；目前磁碟上無 base workflow（E1） |

---

#### 三、改動清單（檔名:行號 → 怎麼改）

**軌 M（零行為變更）**

| 檔 | 位置 | 改法 |
|---|---|---|
| `backend/prompt_profiles.yml` | 全檔（395 行） | 改寫為 `families:` 兩條：`illustrious` ＝ 現行 `Standard_V38.json` 解析值**逐字**；`anima` ＝ 現行 `AnimaStandardV9_aesthetic.json` 解析值逐字（含 `style_extra: ""`、`style_extra_weight: 2.0`）。長篇沿革註解移到 CODE_NOTES 新條目，yml 只留一行 `# [CN-xxx]` |
| `backend/app/services/ai/workflow_builder.py` | `:76-91 _load_prompt_profiles()` | 改讀 `data.get("families")`；偵測到 `profiles` 鍵 → warn-once（D2）；docstring 更新 |
| 同上 | `:96 _PROFILE_MISS_WARNED` | 改記 style 值 |
| 同上 | `:99-123 _profile_for()` | `style = _detect_style(workflow).value` → `_load_prompt_profiles().get(style)`；miss 訊息依 D4 |
| 同上 | `:184-198 _prompt_profile_source()` | 依 D5 |
| `character_design_service.py` | `_resolve_style_extra()`（:469）與 style weight 分支 | **不改邏輯**，只更新註解中「workflow profile」字樣為「family profile」 |

**軌 R（M 驗收後）**：`families.illustrious` 換成 R1：

```yaml
illustrious:
  quality_prefix: "masterpiece, best quality, amazing quality, absurdres"
  style_extra: "anime game illustration, clean lineart, soft shading, crisp edges, bright highlights, detailed eyes, high detail"
  style_extra_weight: 1.0
  negative: >-
    bad quality, worst quality, worst detail, lowres, jpeg artifacts, blurry,
    sketch, rough lineart, monochrome, greyscale,
    bad anatomy, bad hands, bad proportions, extra fingers, missing fingers, fused fingers, extra limbs, deformed,
    photorealistic, 3d, heavy rendering, oily skin, shiny skin,
    artist name, signature, watermark, text, username, patreon, twitter username,
    detailed background, scenery, floor, cast shadow,
    nsfw, nude
```
（`multiple views`、`cropped`、背景雜物、`male face` 由 `character_design_service` 的 `extra_neg` 自動附加，不重複列。`nsfw, nude` 為 R1 之外新增的人設圖全年齡防護，見 §2.1 八 Q6。）

**軌 T（測試）**

| 檔 | 現況 | 改法 |
|---|---|---|
| `tests/test_workflow_builder.py:96-232`（P1／P4／P5-5 機制測試） | monkeypatch 檔名鍵 `"Standard_V37.json"` | 改為家族鍵，並 monkeypatch `_detect_style` 回傳指定 style；斷言不變 |
| 同 `:355-437`（實檔配方鎖） | 點名歷史檔名 | 改鎖 `families.illustrious`／`families.anima` 實值（R 後為 R1 值） |
| 同 `:447-468 test_all_custom_workflows_are_registered` | 要求每支檔名登錄 | **改寫為** `test_all_custom_workflows_resolve_to_configured_family`：列舉磁碟，逐支要求 ① 抽得到 checkpoint ② 命中 `checkpoint_styles.yml` 某 pattern（非 SDXL 預設退路）③ 解析出的 style 在 `families:` 內 |
| 同 `:471 test_profile_for_warns_once_on_miss` | 檔名單位 | 改 style 單位 |
| 新增 | — | `test_new_workflow_needs_no_registration`：tmp 目錄複製 V38 為 `Standard_V41_test.json`，斷言 profile 與 V38 相同、source 為 `family: illustrious` |
| `tests/test_anima_family.py:233,697,866,1009` | 載入 V37（一直 skip） | 改載 `Standard_V38.json`（同 fabricatedXL），測試名 `v37` → `illustrious_path`；斷言內容不變 |
| 同 `:250 test_v37_profile_registered_and_anima_not` | 驗 V37 登錄 | 刪除（由新護欄取代） |
| 同 `:789-840`（G-1／G-2 V37 品質段） | 鎖 V37 配方文字 | 刪除 |
| 同 其餘 anima profile 斷言（共 24 處引用） | 點名 V8／V9 檔名 | 改鎖 `families.anima` |
| `tests/test_character_design_pure.py`（23 處）、`test_gen_profile.py`（5）、`test_generation_info_link.py`（1） | 待逐條確認是否依賴檔名鍵 | 執行時逐條檢視；**非** profile 機制的斷言不動 |
| `tests/golden/snapshots.json` | prompt 快照 | M 後應零差異（本身即驗收）；R 後只允許 illustrious 案例變動，**anima 案例必須零差異** |

**軌 D（文件）**：`CLAUDE.md`（零程式設定點表 `prompt_profiles.yml` 一列、編程檢查點 4／5 的 V37 鎖描述）、`AGENTS.md`、`GEMINI.md`（慣例需一致）、`doc/MODULE_MAP.md`、`doc/reference/CODE_NOTES.md`（新條目：家族鍵設計；對 SYNC-001 相關條目與 CN-048 加「訂正（2026-09-23）」，不刪舊條目）、`doc/BACKLOG.md`（`checkpoint_styles.yml` 兩區重複）。

---

#### 四、驗收步驟

1. **M 比對腳本**（沙箱可跑，免 fastapi）：遷移前先把磁碟 13 支 workflow 的 5 欄位解析結果存成 JSON；遷移後重跑，逐字 diff 必須為空。
2. `cd backend && pytest tests/`（本機；沙箱缺套件）。
3. **R 實機**：露碧娜 × `Standard_V38` × seed 17021106 × IPA 0.2 × CN 0.75 → 查該筆 `generation_history.positive`：尾端為 R1 畫風段、無 `flat color`、`params.prompt_profile` = `family: illustrious`。
4. **零登錄驗證**：複製 `Standard_V38.json` 為 `Standard_V41_test.json`，不改 yml，UI 切過去生成 → source 同上；驗完刪檔。

---

#### 五、風險與回滾

| 風險 | 影響 | 對策 |
|---|---|---|
| 改家族配方＝同家族所有 workflow 一起變 | 單一 workflow A/B 失去隔離 | 個案實驗走 art_style（DB 最高優先，已支援 quality_prefix／negative／extra_tags） |
| 靜默降級點移到「checkpoint 未登錄 `checkpoint_styles.yml`」（`_detect_style` 退 SDXL 不吵） | 新底模吃到 sdxl 內建配方 | 軌 T 新護欄第 ② 項；另於 `_detect_style` 退路加 warn-once（小改，列入 M） |
| art_style.base_style 與 checkpoint 家族不一致 | compile 用 art_style 的 STYLE_CONFIG、yml 用 checkpoint 家族 | 見八 Q1，請 Codex／Gemini 表態 |
| 測試改動量大（約 140 處引用，多為 monkeypatch 鍵名） | diff 大、審查成本高 | M、R 各自一個 commit；M 的測試改動只換鍵不換斷言 |
| R1 只在一個角色、一個 seed 驗過 | 家族預設可能過擬合 | R 驗收加跑第二個角色（`聖真希` id 3）＋隨機 seed 2 張，目視無崩壞才定案 |
| `_detect_style` 每次都讀 workflow JSON | 每張圖多 3 次讀檔 | 檔小、成本可忽略；若 `_load_workflow` 無快取也不在本案處理 |

**回滾**：M、R 分兩個 commit。R 有問題 → 只還原 `families.illustrious` 區塊（yml 免重啟生效）；M 有問題 → revert M commit（`prompt_profiles.yml` 在 git 內）。

---

#### 六、否決的方案

| 方案 | 否決理由 |
|---|---|
| 以「SDXL 大類」為鍵 | SDXL 下 illustrious／pony／noobai 提示詞方言不相容（pony 需 `score_9…`）；Anima 不是 SDXL |
| 保留 workflow 例外層 | 使用者裁決；且 E1 顯示現況零例外 |
| 檔名正規化／模糊比對（V38→V3x） | SYNC-001 已否決：把明確鍵換成會誤命中的猜測規則 |
| 以 `gen_profile` family（`capability.resolve_family`）為鍵 | 與 `STYLE_CONFIG` 鍵空間不一致（D1） |
| 把配方寫回 `styles.STYLE_CONFIG`（Python） | 調配方要改碼＋重啟；yml 免重啟是 P5 調參期的關鍵便利 |
| 本案一併合併 `checkpoint_styles.yml` 兩區 | 會同時動 prompt 與 GEN_PROFILE 兩條解析，範圍過大；轉 BACKLOG |

---

#### 七、不在本案（順手記）

- `families.anima` 負向含 `child, toddler, chibi`，而角色年齡欄位 ≤12 時 `_age_body_tags()` 會在正向加 `child` → 正負向互打。屬年齡策略（BACKLOG F4），本案配方逐字搬移不處理。
- `checkpoint_styles.yml` 的 `checkpoints:` 與 `families:` 兩區內容幾乎重複、需雙寫 → 轉 BACKLOG。

---

#### 八、請 Codex／Gemini 特別檢查的問題

1. **Q1**：art_style 設了 `base_style`（例：art_style 指定 pony，但 workflow 底模是 fabricatedXL）時，yml 家族層應跟 **checkpoint 家族**（本案 D1）還是 **art_style.base_style**？後者需把 `style` 傳進 `_profile_for`，會改簽章。
2. **Q2**：除 `character_design_service` 外，是否還有路徑（`/art/generate`、`compose`、LoRA 訓練預覽等）間接依賴檔名鍵 profile？我 grep `app/` 只找到 E5 所列呼叫端，請獨立複核。
3. **Q3**：`_detect_style()` 在 `_load_workflow` 失敗時直接回 SDXL（`workflow_builder.py:456-459`）。家族層啟用後，這條退路是否需要與 `_profile_for` 的 miss 告警合併成一條訊息？
4. **Q4**：M／R 拆兩步是否必要，或可一次到位（以 golden 快照差異同時驗兩者）？
5. **Q5**：`test_character_design_pure.py` 的 23 處引用中，是否有斷言實際依賴「檔名鍵」語義（而非只是拿 V37 當範例字串）？
6. **Q6**：R1 之外新增的 `nsfw, nude` 負向，對 fabricatedXL 全年齡人設圖是否有可觀察的副作用（例如壓低 `bare shoulders` 類正常服裝描述）？
7. **Q7**：R1 僅一角色一 seed 實證，作為家族預設是否足夠？若不足，最小補證集合為何？

<!-- HANDOFF: Claude DONE @ 2026-09-23 14:15 -->

### 2.1-P Claude 規劃（追加：軌 P 個人自訂標籤分家族 `.env`）

#### 〇、結論（先講）

使用者的個人畫風標籤要放 `.env`（不進 git），而且**各家族寫法不同**（`@` 是 Anima 專用畫師前綴）。
現行 `PERSONAL_STYLE_EXTRA_TAGS` 是「全域單值＋yml `style_extra` 為空才生效」的 fallback（E-P1），illustrious 永遠吃不到；Anima 吃得到只是因為 `families.anima.style_extra` 恰好是空字串。
→ 新增**分家族、疊加語義**的 `.env` 鍵，家族名沿用本案 `PromptStyle` 值，新家族零改碼。

```
.env（使用者自填，不進 git）
PERSONAL_STYLE_EXTRA_ANIMA=blue archive, @kozaki yuusuke
PERSONAL_STYLE_EXTRA_ILLUSTRIOUS=blue archive, kozaki yuusuke
PERSONAL_NEGATIVE_EXTRA_ANIMA=(halo:1.5)
PERSONAL_NEGATIVE_EXTRA_ILLUSTRIOUS=halo

正向：style_extra = [art_style.extra_tags ｜ families[f].style_extra ｜ 舊全域 fallback]（既有，不動）
                    ＋ PERSONAL_STYLE_EXTRA_<F>（新，疊加）
      → 沿用既有 weight／位置規則（character_design_service.py:778-787，不新增旋鈕）
負向：final_negative ＋ PERSONAL_NEGATIVE_EXTRA_<F>（新，疊加，任何分支都生效）
F = _detect_style(workflow).value.upper()（與 families[] 同一個家族判定來源）
```

#### 一、證據

- **E-P1**｜`backend/app/services/ai/character_design_service.py:469-477` `_resolve_style_extra`：`.env` 只在 art_style 與 yml 皆空且 `PERSONAL_STYLE_ENABLED` 時才取代；是**單值、取代語義**。
- **E-P2**｜`backend/app/core/config.py:84-90`：`PERSONAL_*` 皆為 import 時求值的模組常數；`config.py:20` `load_dotenv(BASE_DIR.parent / ".env")` ⇒ pytest 也會載入使用者真實 `.env`。`backend/tests/` 無 `conftest.py`。
- **E-P3**｜09-23 ComfyUI SDXL A/B（`人設圖CN_IPA_V38_K0~K3_workflow.json`，R1 底、seed 17021106）使用者判讀：**K1 認得畫師**；K2（尾端）與 K3（前段）差異在誤差內 ⇒ illustrious 走既有「weight 1.0 → 尾端 append」即可，**不需新增位置機制**。
- **E-P4**｜Anima 的 ComfyUI 驗證（A 系列 `Anima_miao_FaceCN_BA_A*`）是**不加權、置於 `1girl, solo` 之後**；Craftflow `prompt_profiles.yml` `families.anima.style_extra_weight: 2.0`（註解自稱佔位）⇒ 個人標籤會被包成 `(tag:2.0)` 前置（`character_design_service.py:778-785`），**此組合未驗證**。
- **E-P5**｜`character_design_service.py:806`：`PERSONAL_NEGATIVE` 是取代語義，且 yml 有 `negative` 時直接跳過 ⇒ 今天無法用 `.env` 補 `halo`。
- **E-P6**｜`_resolve_style_extra` 只有角色設計用；`backend/app/api/art_generate.py:114、:653` 只吃 `_extra_tags(art_style)`，不經本鏈。
- **E-P7**｜09-23 使用者已 `git rm --cached .env`，`.gitignore:2` 生效。

#### 二、設計決策

| # | 決策 | 理由 |
|---|---|---|
| P-D1 | 鍵名 `PERSONAL_STYLE_EXTRA_<家族>`／`PERSONAL_NEGATIVE_EXTRA_<家族>`；**呼叫時** `os.getenv` 讀取，不做模組常數 | 家族是動態值；可用 `monkeypatch.setenv` 測試 |
| P-D2 | **疊加**：接在已解析的 style_extra 之後，不論其來源（art_style／yml／舊 fallback） | 個人偏好跨畫風；取代語義會與 yml 配方互斥（E-P1 的老問題） |
| P-D3 | 權重與位置**跟家族既有規則**，不加新旋鈕 | illustrious（R 後 weight 1.0）＝尾端＝K2 已驗；anima 2.0 前置交給驗收決定（見 Q-P2） |
| P-D4 | 無開關：鍵不存在或空字串＝關；不受 `PERSONAL_STYLE_ENABLED` 節制 | 少一個會忘記打開的開關；舊開關只管舊 fallback |
| P-D5 | 舊鍵 `PERSONAL_STYLE_EXTRA_TAGS`／`PERSONAL_NEGATIVE` 保留原語義 | 零回歸；新舊重複的 tag 由 `_dedup_tags` 收斂 |
| P-D6 | `_prompt_profile_source` 命中時附加 ` +personal(.env)` | DEBUG prompt 能一眼看出個人層有沒有生效（「先看 runtime 再分析」教訓） |

#### 三、改動清單（檔名:行號 → 怎麼改）

| # | 位置 | 改法 |
|---|---|---|
| P-1 | `backend/app/core/config.py:84-90` 之後 | 新增 `personal_family_extra(kind: str, family: str) -> str`：`os.getenv(f"PERSONAL_{kind}_EXTRA_{family.upper()}", "").strip()`；`kind` 以常數 `PERSONAL_KIND_STYLE="STYLE"`／`PERSONAL_KIND_NEGATIVE="NEGATIVE"` 表示，避免魔術字串 |
| P-2 | `character_design_service.py:469-477` `_resolve_style_extra` | 既有解析後：`fam = _detect_style(workflow).value`；`personal = personal_family_extra(STYLE, fam)`；非空則 `style_extra = f"{style_extra}, {personal}" if style_extra else personal`。**簽章不變**；`_detect_style` 加進 `:43` 的 `workflow_builder` import |
| P-3 | `character_design_service.py:813`（`final_negative` 組好）與 `:814`（`_dedup_tags`）之間 | 非空則 `final_negative += f", {personal_neg}"` |
| P-4 | `workflow_builder.py:200` `_prompt_profile_source` | 該家族任一 personal 鍵非空 → 附加 ` +personal(.env)` |
| P-5 | `backend/tests/conftest.py`（新檔） | autouse fixture：`monkeypatch.delenv` 所有 `PERSONAL_STYLE_EXTRA_*`／`PERSONAL_NEGATIVE_EXTRA_*`，隔離使用者真實 `.env`（E-P2） |
| P-5 | `backend/tests/test_character_design_pure.py` | 新增：①無鍵＝逐字零回歸 ②anima 鍵疊加且吃家族 weight 2.0 包裝 ③illustrious 鍵 weight 1.0 接尾端 ④**跨家族不外洩**（設 ANIMA、偵測為 illustrious → 無）⑤art_style 有 extra_tags 時仍疊加 ⑥家族有 negative 時 personal negative 仍附加 ⑦來源標註含 `+personal(.env)` |
| P-6 | `.env.example:24-34`、`CLAUDE.md` 零程式設定點表、`doc/reference/CODE_NOTES.md`（CN-115）、`doc/BACKLOG.md` | 範例（全註解）與優先序圖；BACKLOG 記 art_generate 範圍（Q-P3）與「art_style.base_style 與 yml 家族判定可能不一致」對 P 的影響 |

#### 四、驗收步驟

1. `cd backend && pytest tests/` → 除 §2.6 已知 6 條外全綠。
2. **負向對照**：`.env` 不設任何新鍵 → 露碧娜 DEBUG prompt 與改動前**逐字相同**。
3. illustrious（R 完成後）：露碧娜 × `Standard_V38` × seed 17021106 → 正向尾端 `…, blue archive, kozaki yuusuke`、負向含 `halo`、來源標 `family: illustrious +personal(.env)`；目視接近 ComfyUI K2。
4. anima：露碧娜 × `AnimaStandardV9_miaomiaoHarem` → 正向含 `(blue archive:2.0), (@kozaki yuusuke:2.0)`；對照 ComfyUI A 系列。出現光環或角色漂移 → §2.5 裁決是否把 `families.anima.style_extra_weight` 改 1.0（會觸及本案範圍限制 ②）。

#### 五、風險與回滾

| 風險 | 對策 |
|---|---|
| 真實 `.env` 的個人鍵污染測試 | P-5 conftest 自動清除 |
| Anima 版權 tag 被 2.0 加權前置 → 光環／角色特徵被拉向 BA | 驗收 4；必要時裁決 weight |
| 使用者在 illustrious 鍵誤用 `@` 或未跳脫括號 | `.env.example` 寫明各家族寫法；是否加 warn-once 見 Q-P4 |
| `.env` 不進 git → 換機器後設定不隨行 | 使用者裁決即如此；`.env.example` 留範本 |

回滾：刪 `.env` 新鍵即回到改動前行為（不必改碼）；程式面單一 commit 可 revert。

#### 六、否決的方案

| 方案 | 否決理由 |
|---|---|
| 單一全域鍵＋非 Anima 自動剝 `@` | 隱性轉換；兩家族差異不只 `@`（權重量級、可用 tag 集合） |
| 個人標籤寫進 yml | 違反「不進 git」 |
| 把舊 `PERSONAL_STYLE_EXTRA_TAGS` 改成疊加語義 | 破壞零回歸，且仍是單值 |
| 走 art_style（DB） | 以畫風為單位而非使用者偏好；且會被 P-D2 疊加，不衝突 |

#### 七、請 Codex／Gemini 特別檢查的問題

1. **Q-P1**：P-D2「對 art_style.extra_tags 也疊加」合理嗎？還是 art_style 有值時應完全取代？
2. **Q-P2**：Anima 版權／畫師 tag 在 2.0 加權前置 vs 1.0 尾端，有無官方或社群證據可先判斷？
3. **Q-P3**：`art_generate.py`（一般插畫）要不要本案一併吃個人鍵，或轉 BACKLOG？
4. **Q-P4**：非 anima 家族的個人鍵含 `@` 時要不要 warn-once？
5. **Q-P5**：新增 `tests/conftest.py` autouse 會不會影響既有依賴真實 `.env` 值的測試？
6. **Q-P6**：執行順序 M commit → R 驗收 → P，同意嗎？

<!-- HANDOFF: Claude 軌P DONE @ 2026-09-23 15:45 -->


### 2.2 Codex 規劃

（待填）

### 2.3 Gemini 規劃

針對 Claude 提出的問題（§2.1 八），我已透過 codebase 檢索完成驗證，回覆如下：

**Q1：`art_style.base_style` 與 checkpoint 家族衝突時，聽誰的？**
**答：絕對必須聽 checkpoint（維持 D1 決策）。** prompt profile 定義了該底模所特有的品質詞與負向寫法（例如 pony 需要 `score_9`、Anima 負向不需要 `nsfw` 等）。如果 `art_style` 指定 pony 但實際執行用的是 fabricatedXL，餵給它 pony 的 prompt 會導致成圖崩壞或 tag 失效。prompt 必須與「實際執行它的模型」匹配，因此 `_detect_style(workflow).value` 是唯一正確的解法。

**Q2：是否有其他路徑間接依賴檔名鍵 profile？**
**答：沒有。** 全域 grep `_profile_for` 及其直接包裝函式（`_workflow_style_extra`, `_resolve_prompt_overrides`, `_prompt_profile_source`），確認外部呼叫端**僅有** `character_design_service.py` 內的那 4 處。Claude 的 E5 證據完整無誤。

**Q3：`_detect_style()` 的 SDXL 退路是否該加 warn-once？**
**答：必須加。** `_detect_style` 在解析 custom workflow 失敗時會靜默 fallback 到 SDXL。在導入家族層後，如果某支新 workflow 沒有正確內嵌 checkpoint，它會靜默落回 SDXL 配方。這與「已知 checkpoint 但漏登錄家族」是兩種不同層級的錯誤。建議在 `_detect_style` 退回 SDXL 時補上獨立的 warn-once（如：`Workflow X 無法解析 checkpoint，退回預設 sdxl 家族`），以便與 `_profile_for` 的 miss 告警區分。

**Q4：M／R 拆兩步是否必要？**
**答：極度必要。** 軌 M 是純粹的「結構重構」（零行為變更），可以利用現有 `snapshots.json` 進行 100% 的等價驗證；一旦 M 驗收通過，後續的任何快照差異或出圖變化，都能 100% 歸因於軌 R 的配方改動。如果混在一起做，將無法分辨測試失敗是因為「讀不到 JSON 檔案」還是「prompt 寫法改了」。

**Q5：`test_character_design_pure.py` 的測試依賴？**
**答：有隱患，必須改。** 我已檢查該檔，其中直接將字串 `"Standard_V37.json"` 傳給 `_resolve_style_extra` 等函式。在現行架構下，這只是單純的 dict key lookup；但改版後，`_profile_for` 會去磁碟上讀取 `"Standard_V37.json"` 以抽取 checkpoint。由於該檔已不存在（見 E2），這會導致測試靜默 fallback 到 SDXL 配方，從而讓測試驗證到錯誤的邏輯！**所有測試中的 `"Standard_V37.json"` 字串必須替換為實際存在磁碟上的 `"Standard_V38.json"`，或將 `_detect_style` mock 掉。**

**Q6：新增 `nsfw, nude` 對 fabricatedXL 的副作用？**
**答：風險極低。** 動漫模型（基於 illustrious）對 `bare shoulders`、`cleavage`、`bikini` 等明確服裝概念的訓練非常深。標準的 `nsfw, nude` 負向通常只會壓制生殖器或直接裸露，不會蓋掉明確的正向服裝 tag。如果後續發現正常服裝被和諧，可在 `character_design_service.py` 中針對特定 `outfit` 自動將 `nsfw` 移出負向（目前無需過早優化）。

**Q7：R1 僅一角色一 seed 實證是否足夠？**
**答：不足。** 單一角色容易產生過擬合（例如該 seed 剛好沒有觸發 flat color）。最小補證集合為：
1. **Lupina**（標準女性，原測試 seed）
2. **聖真希（Maki，id 3）**（不同色彩配置與特徵，隨機 seed）
3. 另選一個**男性角色**或**不同畫風（如 Q 版/機甲）**的角色。
只要這三組 A/B test 都確認沒有崩壞、且畫風優於舊版，即可定案為家族預設。

**總結與補充建議：**
我完全同意 Claude 的 M → R 分段執行計畫，以及軌 T 的測試改動。唯一要補充的是，在執行 M 時，請務必處理好 Q3（`_detect_style` 加警告）與 Q5（清理所有測試對 `V37` 的依賴），避免測試假陽性。

<!-- HANDOFF: Gemini DONE @ 2026-09-23 14:11 -->

### 2.4 Claude 整合分析

> 參與：Claude §2.1、Gemini §2.3。Codex §2.2 本輪未參與（同 SYNC-005 前例），不等待。
> Gemini 的每項主張我都回到程式碼複核，結果標在「複核」欄。

#### 一、比較表（§2.1 八 的 Q1～Q7）

| # | 議題 | Claude §2.1 | Gemini §2.3 | 複核 | 結論 |
|---|---|---|---|---|---|
| Q1 | art_style.base_style 與 checkpoint 家族衝突 | 暫採 checkpoint（D1），請表態 | **聽 checkpoint** | DB 現況：`art_styles` 只有 #1「蔚藍檔案」`base_style=illustrious`，且**沒有任何角色／專案套用**（`characters.art_style_id`、`projects.art_style_id` 全 NULL） | ✅ 採 D1。另記：`compile` 層的 `_resolve_style()` 仍跟 art_style.base_style 走，衝突情境下兩層不一致——這是**現況即存在**的問題，本案不改變也不惡化，轉 BACKLOG |
| Q2 | 其他路徑依賴檔名鍵？ | grep 只見 `character_design_service` | 同意，僅 4 處 | 一致 | ✅ 無分歧 |
| Q3 | `_detect_style` 退 SDXL 加 warn-once | 列入 M（風險表） | **必須加**，且要與 `_profile_for` miss 分開兩種訊息 | `_detect_style` 有兩個退路：讀檔失敗（`workflow_builder.py:456-459`）與 pattern 全不中（函式尾） | ✅ 採 Gemini 細化：兩個退路各自 warn-once，訊息不同 |
| Q4 | M／R 拆兩步 | 拆 | **極度必要**，並稱可用 `snapshots.json` 做 100% 等價驗證 | ❌ **Gemini 的驗證手段不成立**：`tests/golden/cases.py:128-140` 把 profile negative **逐字抄成字串常數**直接餵 `compile()`，golden **不經過** `_profile_for`，驗不到 M 的結構遷移 | ✅ 拆兩步；M 的等價驗收**只能靠 §2.1 四-1 的比對腳本**，golden 只負責「compile 行為沒變」 |
| Q5 | 測試對 V37 的依賴 | 待逐條確認 | **有隱患**：改版後 `_profile_for("Standard_V37.json")` 會去讀磁碟，檔不存在 → 靜默退 SDXL → 測試驗錯東西 | ✅ 屬實：`test_character_design_pure.py:123,143` 傳 `Standard_V37.json`、`:132` 傳 `AnimaStandardV8.json`，兩檔都不在磁碟 | ✅ 採 Gemini：機制測試一律 **mock `_detect_style`**（不依賴磁碟）；需要真檔的鎖一律改 `Standard_V38.json` |
| Q6 | `nsfw, nude` 副作用 | 請評估 | 風險極低；不建議預先做「依服裝移除 nsfw」 | 無反證 | ✅ 保留，列入 R 驗收目視項 |
| Q7 | R1 補證集合 | 加一角色＋隨機 seed | **三組**，第三組取男性或不同畫風 | 角色表：`源輝` id 2 **male**、15 歲；Gemini 文中「Lupina」即 `露碧娜` | ✅ 採三組：露碧娜（seed 17021106）／聖真希（隨機）／源輝（男性，隨機） |

#### 二、整合中新發現（兩方都漏看）

**N1｜軌 M 不是嚴格的「零行為變更」：Checkpoint 模式會吃到家族配方**

- 角色生圖的 active workflow 若是系統內建（Checkpoint 模式，`tools/Craftflow/diffusion/workflows/text_to_image.json`），
  `_load_workflow()`（`workflow_builder.py:402-407`）會把全域 checkpoint 注入 → `_detect_style` 解析出的是**全域 checkpoint 的家族**。
- 改前：系統 workflow 檔名從未登錄 → 永遠 miss → `STYLE_CONFIG` 內建。
  改後：全域 checkpoint 若是 fabricatedXL／novaAnimeXL／Illustrious-XL（illustrious）→ **會吃到 `families.illustrious`**。
- 現況影響為零：`data/runtime_state.json` 的全域 checkpoint 是 `animagineXL40_v4Opt`（→ sdxl，yml 無此家族，行為不變），且 active workflow 是 custom。
- 判斷：這其實是**正確方向**（配方跟底模走，不該因模式不同而分岔），但必須明說，不能宣稱 M「零行為變更」。
- 對策：§2.1 驗收「M 比對腳本」範圍擴大為 ① 磁碟 13 支 custom workflow 逐字相同（嚴格零變更）② Checkpoint 模式 × 各已知 checkpoint 列出改前／改後差異表，差異**只允許**出現在 illustrious 家族。

#### 三、Claude 自己方案的修正（誠實記錄）

1. §2.1 目標寫「M＝零行為變更」不精確 → 改為「custom workflow 零行為變更；Checkpoint 模式 illustrious 家族改吃 yml 配方（N1）」。
2. §2.1 軌 T 對 `test_character_design_pure.py` 寫「待逐條確認」→ 已確認，採 Q5 處置。
3. §2.1 四-1 已經是正確的 M 驗收手段；golden 不能取代它（Q4 複核）。

#### 四、最終執行清單（待 §2.5 核可）

| 步 | 內容 | 驗收 |
|---|---|---|
| **M-0** | 產出「改前快照」：13 支 custom workflow ＋ Checkpoint 模式 × `checkpoint_styles.yml` 每個 pattern 的 5 欄位解析結果 → `doc/agent_sync/SYNC-007_M_before.json` | 檔案存在 |
| **M-1** | `prompt_profiles.yml` → `families:`（illustrious＝現行 V38 值、anima＝現行 V9_aesthetic 值，逐字） | — |
| **M-2** | `workflow_builder.py`：`_load_prompt_profiles`（讀 families、舊 `profiles:` warn-once）、`_profile_for`（style 鍵、miss warn-once）、`_prompt_profile_source`（D5）、`_detect_style` 兩個退路各自 warn-once（Q3） | — |
| **M-3** | 測試：機制測試 mock `_detect_style`（Q5）；V37 鎖改 V38；刪 `:250`、`:789-840`；新護欄 `test_all_custom_workflows_resolve_to_configured_family`；新增 `test_new_workflow_needs_no_registration` | 沙箱可跑部分全綠 |
| **M-4** | 重跑快照比對 | custom 13 支 diff＝空；Checkpoint 模式差異僅 illustrious（N1） |
| **M-5** | 文件：CLAUDE.md／AGENTS.md／GEMINI.md／MODULE_MAP／CODE_NOTES（新條目＋SYNC-001 相關條目與 CN-048 訂正）／BACKLOG（checkpoint_styles 兩區重複、art_style.base_style 兩層不一致） | — |
| **使用者本機** | `cd backend && pytest tests/`、`git add`／commit（**M 單獨一個 commit**） | 全綠 |
| **R-1** | `families.illustrious` 換 R1（§2.1 三 軌 R 區塊，含 `nsfw, nude`）＋ yml 註解訂正 `style_extra_weight: 1.0` 的說法 | yml 免重啟 |
| **R-2 使用者本機** | 三組實機：露碧娜 seed 17021106／聖真希 隨機／源輝 隨機，皆 `Standard_V38`、IPA 0.2、CN 0.75 | 正向尾端為 R1 畫風段、無 `flat color`、`params.prompt_profile=family: illustrious`；三張目視無崩壞且優於舊版 |
| **R-3** | 通過 → R 單獨 commit；不通過 → 只還原 `families.illustrious` 區塊 | — |

#### 五、請使用者在 §2.5 裁決

| # | 事項 | Claude 建議 |
|---|---|---|
| 1 | 依「四、」清單執行（M → 本機驗收 → R） | 核可 |
| 2 | 接受 N1：Checkpoint 模式下 illustrious 底模也吃 `families.illustrious` | 接受（配方跟底模走） |
| 3 | R 配方負向保留 `nsfw, nude` | 保留 |
| 4 | R 驗收三角色（含男性 `源輝`） | 採用 |
| 5 | 本案不等 Codex §2.2 | 同意 |

<!-- HANDOFF: Claude DONE @ 2026-09-23 14:25 -->

### 2.5 使用者裁決

> 2026-09-23，使用者對話回覆「3. 所有有關 nsfw 到 SIT 驗測後再處理，其餘核可」，由 Claude 代錄。

| # | 事項 | 裁決 |
|---|---|---|
| 1 | 依 §2.4「四、」清單執行（M → 本機驗收 → R） | ✅ 核可 |
| 2 | 接受 N1：Checkpoint 模式下 illustrious 底模也吃 `families.illustrious` | ✅ 核可 |
| 3 | R 配方負向加 `nsfw, nude` | ⏸ **延後**：所有 nsfw 相關處理待 SIT 驗測後再議。R 配方**不含** `nsfw, nude`（＝ComfyUI R1 原樣） |
| 4 | R 驗收三角色（露碧娜 seed 17021106／聖真希／源輝） | ✅ 核可 |
| 5 | 本案不等 Codex §2.2 | ✅ 核可 |
| 6 | 軌 R＋軌 P（§2.1-P）一併執行，不等 Codex／Gemini（2026-09-23 使用者原話「軌 R＋P 核可，不等 Codex／Gemini」） | ✅ 核可。R 在前、P 在後，各自驗證；§2.1-P 七 的 Q-P1～Q-P6 由 Claude 依 §2.1-P 預設處理（疊加於 art_style／權重跟家族／art_generate 轉 BACKLOG／非 anima 含 `@` warn-once／conftest 只清新鍵／順序 R→P） |

### 2.6 執行紀錄（Claude 填）

#### 一、軌 M（結構遷移）—— 已完成，待使用者本機 commit

| 步 | 檔 | 變更 |
|---|---|---|
| M-0 | `doc/agent_sync/SYNC-007_M_before.json` | 改前快照：13 支 custom workflow ＋ Checkpoint 模式 × 24 個 checkpoint pattern 的 style／overrides／style_extra／source（**用真實程式碼解析**，非重寫邏輯） |
| M-1 | `backend/prompt_profiles.yml` | 395 行 → `families:` 兩條（illustrious＝舊 `Standard_V38.json` 解析值、anima＝舊 `AnimaStandardV9_aesthetic.json` 解析值，寫檔前以 `yaml.safe_load` 比對**逐字相等**才落檔）。舊檔含全部沿革註解存 `doc/agent_sync/SYNC-007_prompt_profiles_before.yml` |
| M-2 | `backend/app/services/ai/workflow_builder.py` | `_load_prompt_profiles` 改讀 `families`、舊 `profiles:` warn-once；新增 `_profile_for_style()`；`_profile_for()` 改經 `_detect_style()` 取家族；`_prompt_profile_source()` 改標 `family: <家族>`／`family fallback (STYLE_CONFIG: <家族>)`；`_detect_style()` 兩個 SDXL 退路各自 warn-once（`_warn_style_fallback`，Q3）。函式簽章與呼叫端零改動 |
| M-3 | `backend/tests/test_workflow_builder.py` | 機制測試 14 條加 `_as_family()` 固定家族（不依賴磁碟）＋鍵名改家族；實檔配方鎖改鎖 `families.*`；檔名登錄護欄 → `test_all_custom_workflows_resolve_to_known_family`（反向列舉磁碟）；新增 `test_new_workflow_needs_no_registration`、`test_load_prompt_profiles_ignores_legacy_profiles_key`、`test_profile_for_warns_once_per_family_on_miss`、`test_detect_style_fallback_warns_once_per_cause`；刪除 A/B 對照組與 anchor 一致性等已無對象的測試 |
| M-3 | `backend/tests/test_anima_family.py` | V37 鎖 4 條改載 `Standard_V38.json` 並更名 `illustrious_path_*`；刪 `test_v37_profile_registered_and_anima_not`、G-1／G-2 V37 配方鎖 2 條；V8 檔名鎖 3 條 → anima 家族鎖 2 條（官方 score_* 約束） |
| M-3 | `backend/tests/test_character_design_pure.py` | 範例檔名 V37→V38、V8→V9_aesthetic（這幾條 mock 了 `_workflow_style_extra`，不受家族解析影響）；不 mock 的零回歸測試改為固定 `_detect_style→sdxl`，避免隨本機全域 checkpoint 漂移 |
| M-5 | `CLAUDE.md`、`AGENTS.md`、`doc/MODULE_MAP.md` | 設定點表、編程檢查點 4／5：V37 鎖 → illustrious 家族路徑鎖（`GEMINI.md` 無相關敘述，未動） |
| M-5 | `doc/reference/CODE_NOTES.md` | 新增 CN-114；CN-048、CN-066 各加「訂正（2026-09-23）」，不刪舊條目 |
| M-5 | `doc/BACKLOG.md` §A9 | 補 3 列：art_style.base_style 兩層不一致（Q1）、AnimaStandardV7 同型靜默 skip、基線既有 6 條失敗 |

#### 二、驗證

**M-4 快照比對**（`SYNC-007_M_before.json` vs `SYNC-007_M_after.json`）：
- custom 13 支：style／overrides／style_extra **0 差異**（只有 source 標註字串改為 `family: …`，符合 D5）。
- Checkpoint 模式：差異**只出現在** illustrious（fabricatedXL／novaAnimeXL／IllustriousXL／illustrious-xl／illustriousXL）與 anima 三個 pattern ⇒ 與 §2.4 N1 預期一致。anima 在 Checkpoint 模式屬理論值（系統 workflow 是 CheckpointLoaderSimple，Anima 為 UNET，實際跑不起來）。

**pytest（使用者本機 VM 以 venv 補套件實跑，非 Windows 環境）**：

| | tests | failures | skipped |
|---|---|---|---|
| 改動前基線 | 449 | 14 | 15 |
| 改動後 | 428 | **6** | 9 |

- 新增失敗 **0**。剩 6 條全為基線既有、與本案無關（見 BACKLOG §A9）。
- 基線 14 條中有 8 條是 profile 實檔鎖**早已失效**（09-20／21 改 yml 未同步測試），隨本案改寫而消失。
- skipped 15→9：原本因 V37 不在磁碟而**靜默跳過**的 illustrious 路徑鎖，現在真的在跑（E2 修復實證）。

**負向對照**：複製 V38 並把 checkpoint 改成 `mysteryXL_v1.safetensors` 放進臨時目錄 → `test_all_custom_workflows_resolve_to_known_family` 紅燈，訊息指名該檔與 checkpoint；原 V38 副本通過。證明新護欄不是「鎖錯對象」。

#### 三、整合時的更正（誠實記錄）

- Gemini §2.3 Q5 稱 `test_character_design_pure.py` 會因讀磁碟而「靜默 fallback SDXL 驗錯」—— 實查該檔那幾條 **mock 的是 `_workflow_style_extra` 本身**，不會讀磁碟；真正會漂移的是**不 mock** 的那條零回歸測試（依本機全域 checkpoint），已修。結論（要處理）正確，指認的位置不精確。

#### 四、待使用者本機

1. 重啟後端（`workflow_builder.py` 有改；yml 本身免重啟）。
2. Windows 環境 `cd backend && pytest tests/`，預期與上表一致（6 條既有失敗）。
3. 角色頁隨便生一張（任一 V38／Anima workflow），DEBUG prompt 來源應顯示 `family: illustrious`／`family: anima`，prompt 內容與昨天相同。
4. **`git add` ＋ commit（軌 M 單獨一個 commit）**；`backend/data/vision_cache.json` 是執行期產物、非本案改動，自行決定是否納入。
5. 回報後進軌 R（`families.illustrious` 換 R1，**不含 nsfw/nude**，依 §2.5 #3）。

<!-- HANDOFF: Claude 軌 M DONE @ 2026-09-23 14:28 -->

#### 五、軌 R＋軌 P —— 已完成（§2.5 #6），待使用者本機驗收＋commit

改前快照：`doc/agent_sync/SYNC-007_RP_before/`（8 檔原樣複本，回滾用）。

| 步 | 檔 | 變更 |
|---|---|---|
| R-1 | `backend/prompt_profiles.yml` | `families.illustrious` → R1：quality `masterpiece, best quality, amazing quality, absurdres`；style_extra 7 tag、weight **1.0**（不加權接尾端）；negative＝ComfyUI R1 原樣（**不含** nsfw/nude，§2.5 #3）。寫檔前 `yaml.safe_load` 比對：illustrious 逐字等於 R1、**anima 與改前逐字相同** |
| R-2 | `backend/tests/test_workflow_builder.py` | 實檔鎖 weight 1.2→1.0＋「不得回流 flat color」；`_BANNED_SUBSTRINGS` 移除 `lineart`/`line art`（理由見 CN-115）；`_MAX_STYLE_TAGS` 依位置分流（加權前置 5／尾端 8） |
| P-1 | `backend/app/core/config.py` | `PERSONAL_KIND_STYLE/NEGATIVE`、`PERSONAL_FAMILY_KEY_PREFIXES`、`personal_family_extra(kind, family)`（呼叫時才讀 env） |
| P-2 | `backend/app/services/ai/workflow_builder.py` | `_personal_extra(kind, workflow)`（家族經 `_detect_style`；非 anima 含 `@` → warn-once）；`_prompt_profile_source` 命中附加 ` +personal(.env)` |
| P-3 | `backend/app/services/ai/character_design_service.py` | `_resolve_style_extra` 末段疊加個人畫風；新增 `_with_personal_negative()`，於 `final_negative` 去重前疊加。簽章與呼叫端不變 |
| P-5 | `backend/tests/conftest.py`（新） | autouse 清除分家族鍵，隔離使用者真實 `.env` |
| P-5 | `test_workflow_builder.py` +5、`test_character_design_pure.py` +8 | 零回歸、疊加、anima 吃家族權重、跨家族不外洩（正負向各一）、疊加於 art_style／舊 fallback、來源標註、`@` warn-once |
| P-6 | `.env.example`、`CLAUDE.md`、`AGENTS.md`、`GEMINI.md`、`CODE_NOTES`（CN-115）、`BACKLOG` §A9 | 設定點與範例（範例用佔位字，不含個人標籤）；BACKLOG 補 art_generate 範圍、Anima 權重待判讀、`[wf-load]` +2 |
| — | 專案根 `.env`（不進 git） | 使用者要求代改：過渡期舊鍵關回（`ENABLED=false`、`EXTRA_TAGS` 清空）；新鍵 `PERSONAL_STYLE_EXTRA_ANIMA`／`_ILLUSTRIOUS`、`PERSONAL_NEGATIVE_EXTRA_ANIMA=(halo:1.5)`／`_ILLUSTRIOUS=halo` |

**驗證（使用者本機 VM venv，非 Windows）**

| 項目 | 結果 |
|---|---|
| 全量 pytest | **426 passed / 6 failed / 9 skipped**；6 條＝§2.6「二、」既有失敗清單逐條相同，新增失敗 0（測試數 +13） |
| golden `python -m tests.golden.run_diff` | 13 筆全數一致 |
| 負向對照 | 暫移 `conftest.py` → 10 條既有測試因讀到真實 `.env` 紅燈；放回全綠 ⇒ 隔離確實必要且有效 |
| 真實設定解析（真 `.env`＋真 yml＋磁碟 workflow） | `Standard_V38` → `family: illustrious +personal(.env)`，正向尾端 `…, high detail, blue archive, kozaki yuusuke`、負向 `…, halo`（＝ComfyUI K2）；`AnimaStandardV9_miaomiaoHarem` → `family: anima +personal(.env)`，前置 `(blue archive:2.0), (@kozaki yuusuke:2.0)`、負向 `…, (halo:1.5)` |

**待使用者本機**

1. 重啟後端（`.env`、`config.py` 有改）。
2. Windows `cd backend && pytest tests/`，預期 6 條既有失敗。
3. R 驗收：露碧娜 × `Standard_V38` × seed 17021106 → DEBUG 來源 `family: illustrious +personal(.env)`、正向無 `flat color`；目視接近 ComfyUI K2。加跑聖真希、源輝（§2.5 #4）。
4. P 驗收（Anima）：露碧娜 × `AnimaStandardV9_miaomiaoHarem` → 對照 ComfyUI A 系列；光環／角色漂移明顯 → 裁決 `families.anima.style_extra_weight` 是否改 1.0。
5. commit（`git add -p` 可拆 M／R／P；或單一 commit 註明三軌）。`backend/data/vision_cache.json` 為執行期產物。

<!-- HANDOFF: Claude 軌 R＋P DONE @ 2026-09-23 16:05 -->

---

## 3. 歸檔

議題結案（✅）後：

1. 把 `§1`＋`§2` 整段剪到 `doc/agent_sync/YYYY-MM-DD_SYNC-nnn_標題.md`。
2. 產出的待辦寫回 `doc/BACKLOG.md`（唯一真相）。
3. 當天決策摘要寫進 `doc/YYYY-MM-DD_開發記錄.md`。
4. 本檔 `§1`／`§2` 復原成空白範本，等下一個議題。

**歷史索引**

| 日期 | ID | 標題 | 結論 | 歸檔位置 |
|---|---|---|---|---|
| 2026-09-15 | `SYNC-001` | 角色管理出圖品質：prompt profile 因 workflow 改名整組脫鉤 | 程式面完成（YAML anchor 登錄六檔＋miss 告警＋capability checkpoint 內嵌優先＋磁碟反向護欄），342 測試通過；**實機驗收未跑**，提前歸檔 | `doc/agent_sync/2026-09-15_SYNC-001_prompt-profile檔名脫鉤.md` |
| 2026-09-16 | `SYNC-002` | 角色管理出圖品質第二刀：Anima 結構控制、FabricatedXL 皮膚平塗、Anima FaceDetailer | A1b（LLLite 退避快取）＋B4'／B5'（皮膚規則共用、眼色反向判定）落地，372 測試通過；實機驗收 A1b／B5' 通過，T1-A／T1-B／T2／T3 未完成；**因 SYNC-003 提前歸檔**，遺留項轉 `doc/BACKLOG.md` §A4 | `doc/agent_sync/2026-09-16_SYNC-002_Anima結構控制-皮膚平塗-FaceDetailer.md` |
| 2026-09-19 | `SYNC-003` | 模型家族誤判：`animagineXL` 被當成 Anima → LLLite 對 SDXL 空轉、IPA/CN 被錯誤閘掉 | A1（yml 兩區補登錄）＋A2（載入節點一致性護欄 `family_conflict`）＋A3（+6 測試，含磁碟反向驗證）＋B1~B4 文件落地，400 passed / 15 skipped；**本機驗收未跑**，因開新議題 SYNC-004 提前歸檔 | `doc/agent_sync/2026-09-19_SYNC-003_模型家族誤判-載入節點一致性護欄.md` |
| 2026-09-19 | `SYNC-004` | 出圖品質對標官方範例：釐清「設定 vs 顯卡」歸因，修採樣參數／畫布／臉部／prompt 四層落差 | **T0 PASS（環境與顯卡無罪）**；軌 A（四支 `_0919` 對照檔＋登錄）、B1/B2/B3、C1、C4 落地並沙箱驗證；A4／C6／C7 裁決不做轉 BACKLOG；**C2/C3/C5、本機 pytest、git add 未完成**。因使用者回報「太平塗／Anima CN 不如 SDXL」推翻 D1/D2 前提，開 SYNC-005 並提前歸檔 | `doc/agent_sync/2026-09-19_SYNC-004_出圖品質對標官方範例.md` |
| 2026-09-23 | `SYNC-005` | 畫風「太平塗」與 Anima 條件控制失效 | 軌 E／V／L／I／N／X 落地並沙箱驗證（測試 +10）；軌 S 五組 A/B 由 09-23 ComfyUI R1 實測取代（配方轉 SYNC-007 軌 R）；**本機 pytest、§2.6「四、」測試、git add 未完成**，因開 SYNC-007 提前歸檔，遺留轉 `doc/BACKLOG.md` §A9 | `doc/agent_sync/2026-09-23_SYNC-005_畫風太平塗-Anima條件控制.md` |
