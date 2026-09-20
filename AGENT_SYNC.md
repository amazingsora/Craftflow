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

> ✍️ 本卡由 Claude 依使用者 2026-09-19 的三項裁決代擬。Codex／Gemini 以本卡為準。

| 欄位 | 內容 |
|---|---|
| **ID** | `SYNC-005` |
| **標題** | 畫風「太平塗」與 Anima 條件控制失效：拆掉全域平塗算子、把 LLLite 修到真正可用 |
| **提出者 / 日期** | amazingsora / 2026-09-19（口頭回饋：「anima 的 CN 效果不如 SDXL 且畫風沒有達到我的要求」「fabricatedXL_v70 也是畫風差一點，太平塗」） |
| **前案** | `SYNC-004` 已提前歸檔至 `doc/agent_sync/2026-09-19_SYNC-004_出圖品質對標官方範例.md`。本案**不接手**其未完成項（C2/C3/C5、本機 pytest、git add），只沿用其證據（T0 PASS、T0-E1～E3） |
| **目標** | ① 找出「太平塗」的單一元凶並拆掉，而不是繼續整組調權重<br>② 把 Anima 的 LLLite 從「只給六成」修到真正可用，並量化底模錯配的代價<br>③ 補上臉部修復的有效強度<br>④ 修掉一份會誤導下一輪決策的錯誤文件 |
| **軌** | **S｜畫風算子 A/B**（零程式，改 yml）<br>**N｜Anima 條件控制**（小面積程式＋零程式對照）<br>**F｜臉部修復強度**（零程式，改 workflow widget）<br>**X｜文件修正**（零程式） |
| **範圍限制** | ① 使用者裁決**維持 D1 純 prompt，LoRA 本輪不啟用** → 軌 S 不得引入任何 LoRA<br>② 使用者裁決 **Anima 不封存，要修到可用** → 軌 N 不得以「建議放棄」結案<br>③ 不換顯卡、不升 ComfyUI 版本<br>④ 不動 `custom_workflows` 節點拓樸（沿用 SYNC-004 §1 的使用者明示）；軌 F 只改既有節點的 widget 值<br>⑤ 不做兩段式放大／hires-fix |
| **驗收標準** | **S**：五組單變因對照跑完，能指名「太平塗」的元凶是哪一個 tag；勝出組的皮膚有明暗階層（非單一平色塊）且布料仍為硬邊 cel<br>**N**：`lllite_strength` 與 UI 滑桿解耦，掃描區間涵蓋 1.0 以上；`base10` 同代對照有圖有數據，能回答「底模錯配吃掉多少貼合度」<br>**F**：臉部五官可辨識度目視提升，且未出現換臉／崩臉<br>**共同**：`cd backend && pytest tests/` 全綠；`Standard_V38` 預設路徑零行為變更（所有新旋鈕預設值＝現況） |
| **狀態** | 🔵 執行中（Gemini §2.3 已回；Codex §2.2 未參與。§2.4 整合、§2.5 核可、§2.6 落地完成：軌 E／V／L／I／N／X 全數沙箱驗證通過，測試 +10。**待使用者本機**：重啟後端、`pytest tests/`、依 §2.6「四、」五步測試、`git add`。軌 S 五組畫風 A/B 待本機判讀） |

> 開新議題：把本區塊換成新議題卡，舊議題整段移到 `doc/agent_sync/`（見 §3）。

---

## 2. 規劃區

### 2.1 Claude 規劃

#### 〇、結論（先講）

**三個回饋是同一件事：我們在用「全域平塗算子」假造畫風。**

`flat color` 是**全域**算子——它不分布料與皮膚，一律壓成無階層的純色塊。
而目標畫風（蔚藍檔案立繪）的實際構成是：

```
布料 → 硬邊 cel 階梯陰影     ← cel shading 給的就是這個（對）
皮膚 → 柔邊漸層 + 反光高光    ← flat color 把這個消滅了（錯）
線條 → 粗黑收邊              ← thick outlines（與平塗無關，不該動）
```

**所以「太平塗」的頭號嫌疑犯是 `flat color`，不是 `cel shading`，更不是權重太高。**
這個假設在 2026-09-15 的記憶裡就寫過（「BA 立繪實際是布料硬邊 cel ＋ 皮膚柔邊漸層與反光，
`flat color` 是全域算子，翻譯時只取硬邊沒保住皮膚有階」），對應的 A/B 從那天排到現在**一次都沒跑**。
本案軌 S 的全部工作就是把這個 A/B 跑完。

**Anima 的 CN 弱，三條成因裡有兩條可修、一條是外部事實：**

| # | 成因 | 性質 | 本案能不能處理 |
|---|---|---|---|
| 1 | strength 被當成 0~1 尺度餵進去，實際只給 **0.6 倍** | **實錘缺陷** | ✅ N1，小面積程式 |
| 2 | LLLite 權重訓練在 Anima-**Base v1.0**，現行底模是 `anima_turboV11`，隔兩代 | 外部事實 | ⚠️ N2 只能**量化**代價，不能消除 |
| 3 | 無 IPAdapter、`ToDetailerPipe` 是死節點 | 能力缺口 | ⬛ 不在本案（BACKLOG N1） |

**成因 1 是本案最高槓桿的一項**：使用者習慣 SDXL ControlNet 的 0.75 ≈ 高貼合，
但同一個 0.75 餵給 LLLite 只是 **0.75 倍乘數、低於官方 default 1.0**。
「Anima CN 不如 SDXL」這個觀感，至少有一部分是這個尺度錯配直接造成的。

---

#### 一、證據（E1～E8，全部附檔名:行號或指令輸出）

**E1｜現況畫風配方（軌 S 的基準）**

`backend/prompt_profiles.yml`，anchor `&illustrious_fabricatedxl`：

```yaml
style_extra: "flat color, cel shading, thick outlines"
style_extra_weight: 1.2
```

實際出圖驗證（`generation_history` #643，`Advanced_V38.json`）：

```
1girl, child, petite, (flat color:1.2), (cel shading:1.2), (thick outlines:1.2),
masterpiece, best quality, absurdres, red eyes, green eyes, smile, ...
```

→ SYNC-004 的 C4 已落地（五項→三項），**但使用者的「太平塗」是在 C4 之後回報的** ⇒ 砍 tag 數不是解方。

**E2｜畫風 tag 的加權與位置機制（改動時的硬約束）**

`character_design_service.py:815-826`：

```python
if _style_weight != 1.0:
    _weighted = ", ".join(f"({t.strip()}:{_style_weight})" for t in style_extra.split(",") if t.strip())
    style_front = f"{_weighted}, " if _weighted else ""
else:
    style_extra_str = f", {style_extra}"
```

→ **`style_extra_weight` 設成 1.0 會同時改變權重與位置兩個變因**（前置 → 末端 append）。
SYNC-004 的 N8 已記錄過這個坑。**軌 S 的所有對照組權重一律用 1.2 或 1.1，絕不用 1.0。**

**E3｜`flat color` 與 `cel shading` 語義不同（軌 S 的主假設依據）**

danbooru 語彙：`flat color` = 無漸層的純色填充；`cel shading` = 賽璐璐式**硬邊階梯陰影**（前提是**有**陰影）。
兩者不是同義詞，是**互斥傾向**——`flat color` 要求沒有陰影，`cel shading` 要求有硬邊陰影。
現行配方把兩者同時加權 1.2 前置 ⇒ **prompt 自己打自己**（與 P5-9 記錄的
「`(flat cel shaded coloring:2.0)` ＋ `ultra detailed, high contrast` 互打」同型）。

⚠️ 這是 Claude 的**語義推論，不是實測**。軌 S 的五組對照就是為了證實或推翻它。

**E4｜LLLite strength 被當成 0~1 尺度（實錘缺陷）**

`character_design_service.py:1131-1133`：

```python
lllite_used = _inject_lllite(
    wf, _up, _lllite_weight, _cn_weight_user, end_percent=_end_pct,
    node_class=_lllite_node_class,
)
```

`_cn_weight_user` = UI 的 CN 滑桿原始值（`:548`，範圍 0.1~1.5，實際常用 0.6~0.75）。
而 `wf_node_ops.py:356` 自己的註解寫著節點規格：

```
#   required: model(MODEL) / lllite_name(檔名) / image(IMAGE) / strength(FLOAT, -10~10,
```

`ComfyUI-Anima-LLLite/nodes.py:130` default **1.0**、range −10~10；`:192` 直接傳 `multiplier=strength`。

→ **這是 LoRA-like 乘數，不是 ControlNet 的 0~1 權重。** 現行程式碼的註解（`:1127-1128`）
寫「strength 與 SDXL CN weight 同向 → 直接用滑桿值」——**方向沒錯，尺度錯了**。
`generation_history` #640/#641 記錄的 `lllite_strength = 0.6` ⇒ 實際只給了官方預設的六成。

**E5｜官方沒有 turbo／aesthetic 專屬 LLLite 權重（外部事實，不可改）**

`huggingface.co/kohya-ss/Anima-LLLite` README 實查（2026-09-19）：
released 權重只有 `anima-lllite-inpainting-v2.safetensors` 與
`anima-lllite-any-test-like-v2.safetensors`，**兩支皆訓練於 Anima-Base v1.0**；
其餘為 Preview3 legacy。本機 `ComfyUI/models/controlnet/` 實際只有後者一支。

→ 「換一支對得上 turbo 的權重」這條路**不存在**。軌 N 只能在「修尺度」與「換底模對齊」兩者裡選。

**E6｜`AnimaStandardV8_base10.json` 已預先登錄，檔案未放（N2 的零成本入口）**

`prompt_profiles.yml` 末段（SYNC-003 B1）已登錄該檔名並 `<<: *anima_aesthetic_turbo`，
註明「先登錄、檔案後放：名單制，檔案不存在時本行零作用」。

→ N2 的對照組**不需要改任何設定**，使用者複製一份 workflow 改 `unet_name` 即可，且 prompt 配方天然同源（單變因）。

**E7｜主線 FaceDetailer 確實在輸出鏈上，但 denoise 偏保守**

節點鏈實查（`data/custom_workflows/`）：

```
Standard_V38 :  27 FaceDetailerPipe → 75 ImpactSwitch(input1=input2=['27',0]) → 54 Image Saver
Advanced_V38 :  33 FaceDetailerPipe → 164 ImpactSwitch(input1=['33',0])        → 124 Image Saver
```

→ **SYNC-004 的 N11 可結案：主線臉部修復是有在跑的。**
但兩支的 `FaceDetailerPipe` 都是 `steps 14 / denoise 0.26 / feather 16`；
`guide_size` Standard 寫死 512、Advanced 接 node 68。

全身取景下臉框約 70~100px（T0-E1：#633–638 臉部佔畫面高度約 6%），
放大到 512 後 denoise 0.26 只夠「微調」不足以「重畫五官」⇒ 臉糊的直接原因。

**E8｜`ComfyUI_portable/CLAUDE.md` 的 LoRA 記載有錯（會誤導下一輪決策）**

實查 safetensors `__metadata__` 與同名 `.civitai.info`：

| LoRA | 文件記載 | 實際 | 差異 |
|---|---|---|---|
| `ag31_style_ba_v1-000016` | 「**SD1.5 (LoKr)**，不可用於 SDXL/Anima」 | `ss_base_model_version=sdxl_base_v1-0`、`ss_sd_model_name=animagine-xl-3.1.safetensors`、`ss_network_module=lycoris.kohya`；civitai `baseModel: SDXL 1.0` | ❌ **架構記錯**。它是 SDXL LyCORIS，不是 SD1.5 |
| `Blue_archive_style` | 「SDXL / 畫風」 | civitai `baseModel: **Illustrious**`，`trainedWords: ['Blue archive style​']` | ⚠️ 不精確（Illustrious 是 SDXL 衍生，但與 `fabricatedXL_v70` 同族這點沒記到）；**觸發詞結尾帶 U+200B 零寬空格**，未記載 |

→ 本輪 D1 裁決不啟用 LoRA，**但這份錯誤記載必須先修**：下一輪若重新評估 LoRA，
這兩條會直接導致選錯或觸發失敗。軌 X 只改文件，零風險。

---

#### 二、根因（一句話）

**畫風端**：用全域算子（`flat color`）去描述一個分區現象（布料平、皮膚有階），
壓平布料的同時把皮膚一起壓平——調權重或砍 tag 數都動不了這個，只能拆掉那個算子本身。

**條件控制端**：把一個 LoRA-like 乘數（default 1.0、range −10~10）接在一個 0~1 語義的 UI 滑桿上，
於是使用者每次都在給不到官方預設值的強度，然後得出「LLLite 不如 ControlNet」的結論。

---

#### 三、方案

##### 軌 S｜畫風算子 A/B（零程式，改 `prompt_profiles.yml` 的 anchor）

> 全部固定 seed、純 txt2img（取消「概念圖參考」與「ControlNet」）、`Advanced_V38.json`、同一角色。
> `_load_prompt_profiles()` 不快取（`workflow_builder.py:79-81`）⇒ **改 yml 免重啟後端**。

| 組 | `style_extra` | weight | 驗證什麼 |
|---|---|---|---|
| **S0** | `flat color, cel shading, thick outlines` | 1.2 | 現況基準（＝#643，可沿用不重跑） |
| **S1** ⭐ | `cel shading, thick outlines` | 1.2 | **主假設**：拔掉 `flat color` → 皮膚回復明暗階層，布料仍硬邊 |
| **S2** | `flat color, thick outlines` | 1.2 | 反向對照：如果 S2 也改善，元凶就不是 `flat color` 而是「兩者相衝」 |
| **S3** | `flat color, cel shading, thick outlines` | **1.1** | 分離「tag 組成」與「權重」兩個變因 |
| **S4** | `thick outlines` | 1.2 | 極端組：平塗算子全拔（T0-E2 已證底模原生就會平塗） |

**判讀順序**：先看皮膚（有沒有明暗階層）、再看布料（是不是硬邊 cel）、最後才看整體討不討喜。
**回滾**：改回 S0 字串即可，yml 註解會寫明。

##### 軌 N｜Anima 條件控制修到可用

| ID | 內容 | 性質 |
|---|---|---|
| **N1** | `character_design_service.py:1132` 的 strength 與 UI 滑桿解耦：新增 `.env` 的 `LLLITE_STRENGTH_SCALE`（`core/config.py` 的 `_env_float` 慣例），實際 strength ＝ `_cn_weight_user × SCALE`。**預設 1.0 ⇒ 零行為變更**；`generation_history.params.lllite_strength` 改記**實際送出值**而非滑桿值 | 程式，小面積 |
| **N2** | 掃 `LLLITE_STRENGTH_SCALE` = 1.0 / 1.7 / 2.2（對應 CN 0.6 時 strength ≈ 0.6 / 1.0 / 1.3），同草圖同 seed 各出一張 | 零程式（改 .env） |
| **N3** | 使用者複製 `AnimaStandardV8_trubo11.json` → `AnimaStandardV8_base10.json`，只改 `unet_name` 為 `anima_baseV10.safetensors`（yml 已登錄，見 E6），與 turbo 組同 seed 對照 | 零程式 |
| **N4** | `end_percent` 現為 `coverage_cn_end_pct[full]=0.85`，掃 0.85 vs 1.0 | 零程式（`gen_profile.py` 的 `GEN_PROFILE`） |

> ⚠️ **N1 的 `lllite_strength` 記錄口徑要一起改**，否則掃描結果全部記成滑桿值，
> 事後無法從 `generation_history` 反查（同 SYNC-004 Q5-1「steps 記錄失真」的同型問題）。
>
> ⚠️ **N2 與 N3 不可合併**：前者測「給夠強度會不會好」，後者測「底模同代會不會好」。
> 合併就回到 08-17 S3「LLLite ＋ 換底模雙變因」的歸因陷阱。

##### 軌 F｜臉部修復強度（零程式，只改既有節點 widget 值）

| ID | 內容 |
|---|---|
| **F1** | `Standard_V38.json` node 27 / `Advanced_V38.json` node 33 的 `denoise`：0.26 → **0.40** A/B |
| **F2** | 若 F1 出現換臉／崩臉，退 0.33；若仍糊，`Standard_V38` node 27 的 `guide_size` 512 → 768 |

> 依使用者「不動節點拓樸」的限制，F 軌**只改 widget 值不改連線**。
> 沿用 SYNC-004 §2.5 的做法：**產生 `_F1` 對照檔，原檔不動**，並同步登錄 `prompt_profiles.yml`（否則靜默脫鉤，SYNC-001 原始災情）。

##### 軌 X｜文件修正（零程式，零風險）

| ID | 內容 |
|---|---|
| **X1** | 修 `ComfyUI_portable/CLAUDE.md` 的 LoRA 表：`ag31_style_ba_v1-000016` 改記為 **SDXL LyCORIS（animagine-xl-3.1）**；`Blue_archive_style` 補記 **baseModel=Illustrious、與 `fabricatedXL_v70` 同族**、觸發詞 `Blue archive style` **結尾含 U+200B** |
| **X2** | 同檔補一行：本表的架構欄位應以 safetensors `__metadata__.ss_base_model_version` ＋ 同名 `.civitai.info` 的 `baseModel` 為準，不憑檔名推測 |

---

#### 四、執行順序

```
S1/S2/S3/S4（四張圖，一次跑完）─→ 判讀選出勝出組 ─→ 寫回 anchor
        │
        └─→ 同時可做：X1/X2（純文件）
                        │
F1（臉部 denoise）───────┘
        │
        ▼
N1（程式，解耦 strength）─→ N2（掃 SCALE）─→ N3（base10 同代對照）─→ N4（end_percent）
```

**S 軌排最前**，因為它是使用者最在意的一項，且零程式、可即時回滾、一輪就有答案。
**N 軌排最後**，因為 N1 是本案唯一的程式改動，要等 S 軌的基準穩定後再引入新變因。

##### 本案不做的（明確劃界）

- 不啟用任何 LoRA（D1 裁決）
- 不動 SYNC-004 遺留的 C2／C3／C5
- 不補 Anima 的 `FaceDetailerPipe`（BACKLOG N1）
- 不動 `Standard_V38` / `Advanced_V38` 的採樣參數（SYNC-004 E4 已確認與官方一致）

---

#### 五、風險與回滾

| # | 風險 | 徵兆 | 回滾 |
|---|---|---|---|
| R1 | S1 拔掉 `flat color` 後畫面變厚塗／失去平塗感 | 布料出現柔邊漸層 | 改回 S0 字串（yml，免重啟） |
| R2 | S4（算子全拔）後畫風完全跟著底模走，與目標差更遠 | 出現環境光／厚塗 | 同上；S4 本來就是探邊界的極端組 |
| R3 | **N1 改了 `lllite_strength` 的記錄口徑，舊資料的語義與新資料不同** | `generation_history` 跨 #644 前後不可直接比較 | 不可回滾，**必須在開發記錄寫明分界 id** |
| R4 | N2 把 strength 拉到 1.3 後構圖被草圖鎖死、失去底模補細節的空間 | 出圖僵硬、線條照描 | 降回 SCALE 1.0；並改用 N4 的 `end_percent` 釋放末段 |
| R5 | F1 denoise 0.40 造成換臉（五官與草圖不一致） | 臉與 CN 參考明顯不同人 | 退 0.33，或回 0.26 原檔（`_F1` 是獨立檔，原檔未動） |
| R6 | `_F1` 新檔名未登錄 `prompt_profiles.yml` → 靜默脫鉤 | prompt 配方落回 family + .env | **落地時同步登錄**，`test_all_custom_workflows_are_registered` 會擋 |

---

#### 六、否決的方案

| 方案 | 否決理由 |
|---|---|
| 啟用 `Blue_archive_style` LoRA | 使用者 2026-09-19 裁決「先跑算子 A/B，LoRA 之後再說」。證據已備妥於 E8，下輪要用可直接取用 |
| 封存 Anima 對照線 | 使用者 2026-09-19 裁決「沒有封存的選項，只有弄到好」 |
| 換底模到 `novaAnimeXL_ilV190` | 會同時改變畫風基準，S 軌的對照組立刻失效。等 S 軌有結論再議 |
| 只調 `style_extra_weight` 不動 tag 組成 | E1 已證 C4 砍過 tag 數、使用者仍回報太平塗；且 E3 指出問題在**算子選擇**不在強度。S3 保留此組作對照，但不作為主線 |
| 下載新的 LLLite 權重對齊 turbo | E5：官方只有兩支 v2 權重，皆訓練於 Base v1.0，不存在 turbo 專屬權重 |

---

#### 七、請 Codex／Gemini 特別檢查的問題

1. **E3 的語義推論站不站得住？** `flat color` 與 `cel shading` 在 danbooru / Illustrious 訓練分佈裡是否真的互斥？有沒有反例（大量同時帶兩者且皮膚仍有階層的圖）？
2. **軌 S 的五組設計有沒有漏掉必要的對照？** 特別是：要不要補一組「`flat color` 降到 0.9、`cel shading` 維持 1.2」的分項權重組？現行機制支不支援單 tag 各自權重（`character_design_service.py:815-826` 看起來是整組同一個 weight）？
3. **N1 的 `LLLITE_STRENGTH_SCALE` 是不是最小改動？** 有沒有更乾淨的做法（例如在 `gen_profile.py` 的 `GEN_PROFILE` 加一個 family 級的 `lllite_strength_scale`，而不是全域 .env）？
4. **N1 改 `lllite_strength` 記錄口徑會不會打到既有測試？** 列出所有斷言該欄位的測試。
5. **軌 F 的 `_F1` 對照檔要不要也做 Anima 四支？** 還是主線兩支就夠（Anima 本來就沒有 FaceDetailer）？
6. **`ImpactSwitch` 的 `select: 1` 在 `Advanced_V38` 只有 `input1`** —— 這是不是代表該 switch 實際上是無作用的直通？有沒有可能某些情況下 select 被改寫成 2 而導致 detailer 被繞過？
7. **有沒有比「改 denoise」更省事的臉部改善手段**，在不動拓樸的前提下？（例如 `guide_size` / `feather` / detailer 的 `wildcard` 欄位現為 `[CONCAT] {face|face,detailed face}`）
8. **X1 之外，`ComfyUI_portable/CLAUDE.md` 還有沒有其他與實際檔案不符的記載？** 請用 safetensors metadata 反向驗證整張表（這是 SYNC-001「測試鎖錯對象 → 改成列舉真實來源反向驗證」的同型做法）。


---

#### 八、規劃後追加的新發現（2026-09-19 下午，E9～E13）

> §2.1 的「一～七」已於稍早 HANDOFF。本節是**之後**由使用者實機回饋觸發的追加證據，
> 刻意另起一節而不改寫上文，避免事後看不出哪些是原始判斷、哪些是修正。
> **E9 與 E10 會直接改變軌 S 的操作方式，Codex／Gemini 請一併納入。**

**E9｜`PERSONAL_STYLE_ENABLED=false` 對現役六支 workflow 完全無效（實錘）**

`character_design_service.py:474-482`：

```python
def _resolve_style_extra(art_style, workflow) -> tuple[str, float]:
    profile_extra, profile_weight = _workflow_style_extra(workflow)
    style_extra = _extra_tags(art_style)
    if not style_extra and profile_extra:
        style_extra = profile_extra                                    # ← yml 先中
    if not style_extra and PERSONAL_STYLE_ENABLED and PERSONAL_STYLE_EXTRA_TAGS:
        style_extra = PERSONAL_STYLE_EXTRA_TAGS                        # ← 永遠走不到
```

`Standard_V38` / `Advanced_V38` / 四支 Anima 在 `prompt_profiles.yml` 都有 `style_extra`
⇒ `profile_extra` 必有值 ⇒ **第 479 行的 `not style_extra` 恆為 False**。

`config.py:70` 的註解自己就寫過這件事（「只節制 .env 這一層，**不節制** yml 的 style_extra」），
但那是寫給讀程式的人看的，操作面沒有任何提示。

實證：使用者於 `.env` 設 `PERSONAL_STYLE_ENABLED=false` 之後產生的
`generation_history` **#644（12:41）與 #646（12:46）**，正向仍完整帶著：

```
(flat color:1.2), (cel shading:1.2), (thick outlines:1.2)
```

⇒ **軌 S 的「拔算子」只能改 `prompt_profiles.yml`，改 `.env` 是無效操作。**
操作單 `doc/target/SYNC-005_軌S_畫風算子AB_操作單_20260919.md` 已據此更正。

**E10｜`Standard_V38_NOVE.json` 未登錄 → SYNC-001 災情原地復發（實錘）**

磁碟 11 支 workflow、`prompt_profiles.yml` 登錄 15 個鍵，比對後**唯一未登錄**的是
`Standard_V38_NOVE.json`（底模 `novaAnimeXL_ilV190.safetensors`）。

實證 —— `generation_history` #647（12:50）的正向：

```
1girl, child, petite, (flat color:1.2), (cel shading:1.2), (anime coloring:1.2),
masterpiece, best quality, amazing quality, absurdres, ...
```

逐項比對來源：

| tag | 來自 | 應該來自 |
|---|---|---|
| `anime coloring` | `.env` 的 `PERSONAL_STYLE_EXTRA_TAGS`（`flat color, cel shading, anime coloring`） | yml 的 `style_extra`（`flat color, cel shading, thick outlines`） |
| `amazing quality` | `styles.py` 的 illustrious **family 預設** | yml 的 `quality_prefix`（`masterpiece, best quality, absurdres`） |
| weight `1.2` | `.env` 的 `PERSONAL_STYLE_WEIGHT=1.2` | yml 的 `style_extra_weight` |

⇒ 這支落回 family + .env，**prompt 配方與其他五支不同**。
拿它跟 `Standard_V38` 比較 ＝「底模」與「prompt 配方」雙變因，比出來的結論不可用。
`test_all_custom_workflows_are_registered` 會擋下來，但本機測試至今沒跑（BACKLOG §A6 S4-V1 阻擋項）。

**修法（零程式、一行）**：yml 加

```yaml
  Standard_V38_NOVE.json:
    <<: *illustrious_fabricatedxl
```

**E11｜~~「用 LoRA 就逾時」沒有證據~~ → 已推翻，LoRA 有注入，使用者的因果觀察是對的（實錘）**

> ⚠️ **本條原文已作廢。** 原判斷依據是 `generation_history` #644～#647 的 `params.loras=[]`，
> 但那四筆全部早於使用者設定 LoRA 的時間點 —— `characters.updated_at = 2026-09-19 12:50:59 UTC`
> （＝20:50:59 CST），而 #647 是 12:50:38 UTC。**只差 21 秒**。
> 教訓與 `project_craftflow_generation_history_forensics` 同型：**DB 存 UTC、log 存 CST，
> 差 8 小時**；拿 DB 空值當「功能沒跑」的證據前，先確認該功能當時是否已經啟用。

**訂正後的事實**（`data/logs/backend.log`，CST）：

```
20:51:20,883 [wf-snapshot char-gen] node=_lora_0  LoraLoader  lora=Blue_archive_style.safetensors  str_model=0.8
21:54:00,869 （同上）
23:29:29,087 （同上）
23:41:52,845 （同上）
```

⇒ **LoRA 傳遞鏈完全正常**：`character.lora_name`（`models/character.py:53`）
→ `character_design_service.py:966-971` 組進 `lora_list`
→ `workflow_builder._inject_loras()` 插入 `_lora_0` 節點。四次都注入成功，四次都逾時。

⚠️ 使用者在 UI 選的是**角色「專屬 LoRA」**欄位（`characters.lora_name`），不是 `art_style.loras`。
DB 實值是 `Blue_archive_style.safetensors` @0.8（Illustrious 同族，與 `novaAnimeXL_ilV190` 相容）。

**E11b｜LoRA 觸發詞完全沒有注入機制（新實錘，高影響）**

`grep -n "trigger\|trained_word\|trainedWords\|activation"` 於
`workflow_builder.py` 與 `character_design_service.py` —— **零命中**。

`Blue_archive_style` 的 `ss_tag_frequency` 只有**單一 tag**：`blue archive style` ＋ U+200B，出現 **270 次**
（＝全部訓練圖都用這一句 caption）。訓練 caption 單一的畫風 LoRA，不帶觸發詞時效果會顯著衰減。

⇒ **目前是最糟的組合：付出了 LoRA 的全部 VRAM 與時間代價，卻只拿到殘留強度的畫風效果。**
修法有二，擇一：(a) `_inject_loras()` 讀同名 `.civitai.info` 的 `trainedWords` 自動補進正向；
(b) UI 的 LoRA 選單旁顯示觸發詞，由使用者自行貼進「外貌／個性特徵」。
⚠️ 觸發詞尾端的 **U+200B 零寬空格必須原樣保留**，手打會打不出來。

**E11c｜主生成路徑的逾時沒有任何後端 log（新實錘）**

`backend.log` 在 `20:51:22` 之後**直接跳到 `21:53:36`（後端重啟）**，中間 62 分鐘零輸出：
沒有 `TimeoutError`、沒有 `_poll_history` 的「暫時逾時」WARNING、沒有任何 ERROR。

對照組：`canvas-expand` 路徑同樣的逾時**有**完整記錄 ——
`[canvas-expand] ComfyUI 執行失敗: HTTPException: 504: ComfyUI job ... timed out after 300s`。

⇒ 主生成路徑的例外被上層吞掉，只回錯誤給前端，**事後完全無法查**。
這正是本次要靠 ComfyUI 端的 log 才能還原現場的原因。修法：主路徑比照 `canvas-expand` 補 error log。

**E12｜逾時的實際機制：臉部 detailer 在 1536² 上重跑了一張完整大圖（實錘）**

ComfyUI log 逐行：

```
Detailer: segment upscale for ((184.79, 185.48)) | crop region (554, 556) x 2.7706 -> (1534, 1540)
100%|...| 14/14 [06:42<00:00, 28.73s/it]
```

算式（`Advanced_V38.json` 實查）：

| 環節 | 值 | 來源 |
|---|---|---|
| 臉 bbox | **185 px** | log（印證 T0-E1「臉部佔畫面約 6%」） |
| `bbox_crop_factor` | ×3 → 554 | node 33 ← node 72 |
| `guide_size` | **512**，`guide_size_for=true` | node 33 ← node 68 `PrimitiveFloat 512` |
| 放大倍率 | 512 ÷ 185 = **2.77** | — |
| detailer 實際工作解析度 | 554 × 2.77 = **1534 × 1540** | log |
| `max_size` | 2048 → **沒擋住** | node 33 ← node 65 `PrimitiveFloat 2048` |

⇒ **臉越小，detailer 的工作解析度越大。** 14 步跑在 1536² 上，等於再生一張完整 SDXL 圖。

同時 VRAM 爆掉（log 實錘）：

```
[WARNING] [Impact Pack] The model is not moved to the 'cuda:0' due to insufficient memory. [2]
[INFO] Using RAM pressure cache.
[INFO] Unloaded partially: 2514.51 MB freed, 589.23 MB remains loaded, ...
```

同時常駐的模型：SDXL 4897 + ControlNet 2396 + CLIPVision 1208 + SDXLClip 1560 + SAM + VAE 159
≈ **10.2 GB**，加上 1024×1536 的 activations 與 1536² 的 detailer latent，16 GB 不夠。
啟動旗標是 `--highvram`（`run_amazingSP_v3.bat`），模型不主動卸載 ⇒ 只能 partial unload + RAM cache
⇒ 每個 step 都在 PCIe 搬權重。

**決定性證據**：第三次執行的同一個 detailer 是

```
14/14 [00:13<00:00, 1.04it/s]      ← 對比第一次 [06:42, 28.73s/it]，快 30 倍
```

參數一字沒改，差別只在「這次模型還在 VRAM 裡」。
⇒ **慢的原因是記憶體壓力，不是計算量。**

主 KSampler 同樣異常：`30.27 / 25.04 / 19.59 s/it`，而 #643（同 workflow、同畫布、無 detailer 觸發）
整趟只花 **66.1 秒**。⇒ 慢了 10～13 倍。

後端 timeout：`comfyui_client.py:82` `wait_for_result(timeout=300)`。
⇒ 實際耗時 9～21 分鐘 ≫ 300 秒 ⇒ **Craftflow 必然逾時，ComfyUI 卻會跑完並存檔**，
與使用者描述的現象完全吻合。

⚠️ **連帶疑問（待驗證，不列為結論）**：#643 只花 66 秒，裝不下「28 步主圖 ＋ 14 步 1536² detailer」。
懷疑 detailer **不是每次都觸發**（`bbox_threshold 0.4`，185px 的臉在 1024×1536 上是偵測邊緣情況）。
若屬實，代表目前的臉部品質是**時好時壞而非穩定**，這比單純慢更該修。

**E13｜IPAdapter 只看到草圖的腰部（實錘）**

ComfyUI log：

```
INFO: the IPAdapter reference image is not a square, CLIPImageProcessor will resize and crop it at the center.
```

概念圖是直長條（需求書 §一 草圖 476×1098）。CLIP 的前處理會 **center crop 成正方形**
⇒ 頭與腿全被裁掉，IPA 實際只拿到腰部那一段。

⇒ 「概念圖參考」在全身直長草圖上幾乎沒有傳遞角色外觀，這解釋了 IPA 0.1 為何感覺不到作用。
**專案內已有現成解法**：`_letterbox_to_aspect`（CN 側為了同一類問題寫的，
見 `project_craftflow_cn_weight` 的「只生成中段」根因），餵 IPA 前補邊成 1:1 即可。

---

##### 這些發現對原方案的影響

| 原項目 | 影響 |
|---|---|
| 軌 S 全部 | **操作方式更正**：拔算子改 yml，不是改 .env（E9）。原本的五組設計不變 |
| 軌 F（臉部 denoise 0.26→0.40） | **降級／可能取消**。E12 顯示問題不是 denoise 太保守，而是 detailer 工作解析度失控＋VRAM 爆。先修 E12 再談 denoise |
| 新增 **軌 V｜耗時與 VRAM** | V1 `guide_size` 512→320（讓工作解析度落在 ~960 而非 1536）；V2 `max_size` 2048→1280 當硬上限；V3 後端 `wait_for_result` timeout 300s 是否要調、前端要不要顯示真實進度；V4 驗證 detailer 是否每次都觸發 |
| 新增 **軌 I｜IPA 參考圖** | I1 餵 IPA 前 letterbox 補方（沿用 `_letterbox_to_aspect`） |
| 新增 **軌 E｜登錄護欄** | E1' `Standard_V38_NOVE.json` 補登錄 yml（E10）；E2' 本機跑 `pytest tests/`（BACKLOG S4-V1，已是第三次被同一個護欄擋下卻沒跑） |

> **順序建議改為**：E10 補登錄（一行）→ 軌 V（不修完，後面每一輪 A/B 都要等 20 分鐘）→ 軌 S → 軌 I → 軌 N。
> 原本把軌 S 排第一，是在不知道「每張圖要 9～21 分鐘」的前提下訂的。

<!-- HANDOFF: Claude DONE @ 2026-09-19（含 E9~E13 追加） -->

---

### 2.2 Codex 規劃

（待填）

---

### 2.3 Gemini 規劃

針對 Claude 提出的八個問題，提出以下實證與規劃修正：

#### 1. 語義推論完全正確，`flat color` 是元凶
danbooru 語彙中 `flat color` 意指「缺乏明暗漸層與陰影的純色區塊」，而 `cel shading` 要求「有硬邊階梯陰影」。兩者同時使用會導致 tag 互打。當我們追求「皮膚有漸層、布料有平塗感」時，全域加上 `flat color` 必然會把皮膚的漸層一起壓平。S1 拔除 `flat color` 是正確的假設。

#### 2. 現行機制「不支援」單一 tag 各自權重
`character_design_service.py:815-826` 的程式碼顯示：
```python
_weighted = ", ".join(f"({t.strip()}:{_style_weight})" for t in style_extra.split(",") if t.strip())
```
這會把 `style_extra_weight` 無差別地套用到每一個逗號分隔的 tag 上。因此「`flat color:0.9, cel shading:1.2`」這類精細操作目前無法透過 `prompt_profiles.yml` 達成。維持 Claude 的 S1~S4 對照組即可。

#### 3. N1 應改寫至 `GenProfile`，拒絕全域 `.env`
既然 LLLite 是 Anima 家族專屬的機制，把 `LLLITE_STRENGTH_SCALE` 放進全域 `.env` 會造成架構污染。
**修正方案**：在 `gen_profile.py` 的 `GenProfile` 類別新增 `lllite_strength_scale: float = 1.0`，並在 `GEN_PROFILE["anima"]` 內覆寫。在 `character_design_service.py` 讀取 `gen_profile` 時提取該乘數。這才是最小且最乾淨的改動。

#### 4. N1 記錄口徑變更「不會」打到既有測試
透過 `grep -r "lllite_strength" backend/tests/` 實查，**無任何測試斷言此欄位**。將 `generation_history.params.lllite_strength` 記錄為「實際送出值」是安全的。

#### 5. 軌 F 不需也無法做 Anima 側
依據本案前提與既有架構（BACKLOG N1：不補 Anima 的 FaceDetailerPipe），Anima 的工作流內根本沒有 `FaceDetailer` 節點。因此 F 軌只針對 SDXL 的 `Standard_V38` 與 `Advanced_V38` 進行。

#### 6. node 164 `ImpactSwitch` 不是死節點
經查 `Advanced_V38.json`，node 164 設定為 `"select": 1` 且接了 `"input1": ["33", 0]`。這代表它是一個穩定的直通節點（pass-through），確實將 `FaceDetailer` (node 33) 的輸出往後送。臉糊純粹是參數問題（denoise 太低），不是因為節點被繞過。

#### 7. 臉部改善的其他零程式手段
若 F1/F2 調整 `denoise` 與 `guide_size` 效果受限，我們還可透過修改 `FaceDetailer` 節點內的 `wildcard` 或 `prompt` 欄位（例如強制加上 `highly detailed face, sharp focus`），或降低 `feather` 值（目前為 16，可能導致邊緣過度羽化而顯糊）。這些皆可在不動拓樸的前提下於 JSON 內完成。

#### 8. safetensors metadata 驗證無其他隱患
使用 Python 實查 `models/loras/*.safetensors` 的 `__metadata__`，Claude 在 E8 抓出的 `ag31_style_ba_v1-000016` (實際上是 `sdxl_base_v1-0` LyCORIS) 與 `Blue_archive_style` (結尾帶零寬空格) 是清單中唯二的嚴重錯誤。其餘模型如 `Hoshimachi Suisei` 與 `Kozeki_Ui` 皆正確標示為 `sdxl_base_v1-0`。執行 X1/X2 的文件修正即可。

<!-- HANDOFF: Gemini DONE @ 2026-09-19 20:56 -->

---

### 2.4 Claude 整合分析

> Codex（§2.2）未參與本案 —— 使用者於 2026-09-20 指示直接依 Gemini 案落地。
> 下表只比 Claude §2.1（含 E9～E13）與 Gemini §2.3。

#### 一、比較表

| 議題 | Claude §2.1 | Gemini §2.3 | 採用 | 理由 |
|---|---|---|---|---|
| Q1 `flat color` 是不是元凶 | 是（語義推論，標明未實測） | 同意 | **Claude 案**，仍列為假設 | 兩方都是推論。Gemini 找不到反例但也沒找到正例 → 不升級為結論，交 S 軌實測 |
| Q2 單 tag 各自權重 | 問可不可行 | **不支援**，附 `:815-826` 程式碼 | **Gemini** | 實查程式碼，`style_extra_weight` 無差別套用到每個 tag。S1~S4 維持原設計 |
| Q3 LLLite scale 放哪 | 全域 `.env` | **改 `gen_profile.GenProfile`**，family 級 | **Gemini** | LLLite 是 anima 家族專屬機制，放全域 `.env` 是架構污染。這條比 Claude 原案乾淨 |
| Q4 記錄口徑會不會打到測試 | 未知，請查 | **實查無任何測試斷言** | **Gemini** | 已複核：`grep lllite_strength backend/tests/` 零命中 |
| Q5 軌 F 要不要做 Anima | 問 | **不做**（Anima 根本沒有 FaceDetailer 節點） | **Gemini** | 與 BACKLOG N1 一致 |
| Q6 `ImpactSwitch` 會不會繞過 detailer | 懷疑 | **不會**，`select:1` + `input1` = 穩定直通 | **Gemini** | 與 Claude E12（detailer 確實有跑、且跑在 1536²）互相印證，不衝突 |
| Q7 臉部還有什麼零程式手段 | 問 | denoise／wildcard／feather | **部分採用** | ⚠️ 見下方「三」：Gemini 這題答在 E12 之前，前提已變 |
| Q8 文件還有沒有其他錯 | 問 | 逐支重查，**只有 Claude E8 抓到的兩處** | **Gemini** | 直接執行 X1/X2 |

#### 二、唯一的實質分歧：臉糊的根因

| | 主張 | 依據 |
|---|---|---|
| Gemini Q6/Q7 | 「臉糊**純粹**是參數問題（denoise 太低）」 | 節點沒被繞過 |
| Claude E12 | 臉糊的**成本**來自工作解析度失控，denoise 是次要 | detailer 實際跑在 **1534×1540**（log 實證），14 步耗 6:42；VRAM 爆到 `RAM pressure cache` |

**裁定：兩者不互斥，但順序要倒過來。** Gemini 的 Q6 答案（switch 是直通）正是 E12 成立的前提 ——
detailer 有跑，而且跑得**太貴**。在單張要 9～21 分鐘的情況下調 denoise，每個檔位都要等 20 分鐘，
根本做不完 A/B。**先把成本壓下來，denoise 再談**（已降級為 BACKLOG S5-F1）。

#### 三、Claude 自己方案的修正（誠實記錄）

| # | 原案 | 改成 | 為什麼 |
|---|---|---|---|
| **M1** | 軌 V1：`guide_size` 512 → 320 | **`bbox_crop_factor` 3.0 → 2.0，`guide_size` 不動** | 推導錯了。工作解析度 ＝ `bbox_crop_factor × guide_size`（log 實證 3.0×512＝1534，與 bbox 大小無關）。**`guide_size` 就是臉的工作像素＝品質本身**，砍它等於砍畫質；該砍的是 `crop_factor`（臉周圍的 padding）。改後 Advanced 1536²→1024²（像素 0.44×），**臉仍在 512px 渲染、品質不降** |
| **M2** | 軌 N1：全域 `.env` 的 `LLLITE_STRENGTH_SCALE` | family 級 `GenProfile.lllite_strength_scale` | 採 Gemini Q3 |
| **M3** | 軌 F 排在軌 S 之後 | **降級轉 BACKLOG** | 見上「二」 |
| **M4** | （原案沒有） | 新增 **V3 VRAM 門檻** 與 **V4 逾時 log** | E12／E11c 是規劃後才查到的 |
| **M5** | （原案沒有） | 新增 **軌 L｜LoRA 觸發詞** | E11b 是規劃後才查到的，且影響最大：付全額 VRAM 只拿殘留畫風 |

#### 四、最終執行清單

見 §2.6。零程式 6 項、小面積程式 5 項、測試 +10、文件 2 項。

<!-- HANDOFF: Claude DONE @ 2026-09-20 -->

---

### 2.5 使用者裁決

- [x] **核可，一次做完**（使用者 2026-09-20 於對話中：「gemini已經提出交流 請根據對話跟md進行開發 一次做完並告訴我預期成效」，由 Claude 代為記錄）
- [ ] 核可，但修改如下：
- [ ] 退回重新規劃，理由：

**附帶裁決（Claude 依對話推定，若與原意不符請劃掉重填）**

| 項 | 決定 | 依據 |
|---|---|---|
| 畫風路線 | **維持 D1 純 prompt**，先跑算子 A/B，LoRA 之後再說 | 2026-09-19 對話裁決 |
| Anima 對照線 | **不封存，要修到可用** | 同上（使用者原話「沒有封存的選項 只有弄到好」） |
| 軌 V 的 workflow 改動 | **就地改 widget，不另產對照檔** | 與 SYNC-004 軌 A 不同：那是要比較的品質 A/B，這是效能修復。原值已完整寫進 §2.6 可一行還原 |
| 軌 S（五組畫風 A/B） | **本輪不代跑**，交操作單 | 需 GPU 判讀，Claude 無法代替使用者判斷「皮膚有沒有階層」 |

**簽核日期**：2026-09-20

---

### 2.6 執行紀錄（Claude 填）

> §2.5 於 2026-09-20 核可（「一次做完」）後執行。全程沙箱，**未跑 git 寫入**。

#### 一、變更紀錄

| # | 軌 | 動作 | 檔案 | 原值 → 新值 | 結果 |
|---|---|---|---|---|---|
| **E1'** | E | `Standard_V38_NOVE.json` 補登錄（`<<: *illustrious_fabricatedxl`） | `backend/prompt_profiles.yml` | 未登錄 → 登錄 | ✅ |
| **V1** | V | `bbox_crop_factor` 下修（**不動 `guide_size`**） | `Standard_V38.json` node 31 / `Advanced_V38.json` node 72 | 2.5 → **2.0** / 3.0 → **2.0** | ✅ |
| **V2** | V | `max_size` 硬上限 | `Standard_V38.json` node 19 / `Advanced_V38.json` node 65 | 1536 → **1280** / 2048 → **1280** | ✅ |
| **V3a** | V | `COMFYUI_REQUIRED_VRAM_GB` | `backend/app/core/config.py` | 8 → **11** | ✅ |
| **V3b** | V | `COMFYUI_RESIDENT_MIN_FREE_GB` | 同上 | 6 → **10** | ✅ |
| **V3c** | V | 新增 `COMFYUI_JOB_TIMEOUT_SEC`（原寫死 300） | 同上 ＋ `workflow_builder._run()` | — → **1200** | ✅ |
| **V4** | V | 主生成路徑逾時補 `logger.error`（原本**一行 log 都沒有**） | `workflow_builder._run()` | — | ✅ |
| **L1** | L | 新增 `lora_trigger_words()`：讀同名 `.civitai.info` 的 `trainedWords` | `workflow_builder.py` | — | ✅ |
| **L2** | L | 觸發詞前置進正向（`_inject_loras` 之後、`_inject_prompts` 之前） | `character_design_service.py` | — | ✅ |
| **I1** | I | IPA 參考圖 `_letterbox_to_aspect(..., 1, 1)` 補方 | `character_design_service.py` | — | ✅ |
| **I2** | I | `_letterbox_to_aspect` 加具名參數 `label`（預設 `"cn-letterbox"`＝原字串） | `image_ops.py` | — | ✅ |
| **N1a** | N | `GenProfile.lllite_strength_scale`（family 級，非全域 `.env`；採 Gemini Q3） | `gen_profile.py` | — → **1.0**（零回歸） | ✅ |
| **N1b** | N | LLLite strength ＝ 滑桿 × scale；log 印出三個數 | `character_design_service.py` | 直接餵滑桿 → 乘 scale | ✅ |
| **N1c** | N | `params.lllite_strength` 改記**實際送出值** | 同上 | 滑桿值 → 實際值 | ✅ |
| **X1** | X | `ComfyUI_portable\CLAUDE.md` LoRA 表訂正（架構／觸發詞／同族關係） | 該檔 | — | ✅ |
| **X2** | X | 同檔補「架構欄位以 metadata＋civitai.info 為準」的維護規則與查法 | 同上 | — | ✅ |
| **T** | 測試 | 新增 10 項、改 5 處為符號化 | `tests/test_lora_arch.py`／`test_gen_profile.py`／`test_image_ops.py`／`test_vram_coexist.py` | — | ✅ |
| **S** | S | 畫風算子 A/B（S0～S4） | — | — | 🔲 **本輪不代跑**（需 GPU 判讀） |

#### 二、執行中發現並修正的兩件事（規劃階段沒看到的）

**N12（高）§2.1 軌 V1 的「`guide_size` 512→320」是錯的，已不採用。**

Impact Pack 的 `enhance_detail` 是
`工作解析度 = crop_region × (guide_size / bbox)`，而 `crop_region = bbox × crop_factor`，
兩個 bbox 相消 ⇒ **工作解析度 ＝ `bbox_crop_factor × guide_size`，與臉多大無關**。
log 實證：`554 × 2.7706 = 1534`，且 `554/185 = 3.0 = crop_factor`。

於是 **`guide_size` 就是臉被渲染時的像素數 ＝ 畫質本身**，砍它等於砍畫質。
真正該砍的是 `bbox_crop_factor`（臉周圍的 padding，3.0 偏大）。改後：

| | crop_factor × guide_size | 工作解析度 | 相對像素 | 臉的渲染像素 |
|---|---|---|---|---|
| `Advanced_V38` 改前 | 3.0 × 512 | 1536² | 1.00 | 512 |
| `Advanced_V38` 改後 | **2.0 × 512** | **1024²** | **0.44** | **512（不變）** |
| `Standard_V38` 改前 | 2.5 × 512 | 1280² | 1.00 | 512 |
| `Standard_V38` 改後 | **2.0 × 512** | **1024²** | **0.64** | **512（不變）** |

**成本砍一半以上，臉的畫質不動。** 這是本輪最划算的一項。

**N13（中）`tests/test_vram_coexist.py` 的決策表寫死了舊門檻算出來的常數。**

`free_g=9.0`（照舊門檻 8 手算）與 `free_g=6.5`（照舊 resident 門檻 6 手算）兩筆，
門檻一改就會紅。**但那不是「改動污染定版路徑」，是測試鎖錯對象**——
它鎖的是「門檻等於某個值」，而門檻本來就該隨實測調整。

已改為從 `config` 推導（`_ABOVE_REQ` / `_ABOVE_RESIDENT` / `_BELOW_RESIDENT`），
測的是**決策邏輯照不照門檻走**。同 SYNC-001「測試鎖錯對象 → 改成列舉真實來源反向驗證」的教訓。

⚠️ 上面那組「2026-07-26 實測 log 逐筆固化」**刻意不符號化** —— 它們是歷史誤判樣本，
鎖的是「這些具體情境永遠不可放行」，門檻調高只會讓它們更該被拒。

#### 三、驗證

**沙箱可做的（已做）**

| 項 | 方法 | 結果 |
|---|---|---|
| 五支 `.py` 未截斷 | `ast.parse` ＋ 比對預期函式／類別名（`py_compile` 抓不到截斷，CLAUDE.md 沙箱陷阱） | ✅ 全數命中 |
| 兩支 `.yml` / 兩支 `.json` | `yaml.safe_load` / `json.load` | ✅ |
| 登錄反向護欄 | 列舉磁碟 11 支 × 比對 yml 16 鍵 | ✅ **未登錄＝0**（改動前有 1 支） |
| NOVE 配方同源 | `profiles['Standard_V38_NOVE.json'] == profiles['Advanced_V38.json']` | ✅ 逐字相同 |
| workflow 參數反查 | 從 `FaceDetailerPipe` 反查 `bbox_crop_factor`／`max_size` 的來源節點 | ✅ 2.0 / 1280（兩支） |
| 無字面值污染 | 掃全檔確認沒有 `KSampler` 把 `steps` 寫成字面值（CLAUDE.md 編程檢查點 2） | ✅ `strays=[]` |
| `lora_trigger_words` **實際執行** | 真的建檔、真的讀檔，5 組情境 | ✅ 零寬空格保留／一般空白 strip／跨 LoRA 去重／7 種壞輸入回 `[]`／壞 JSON 不炸 |
| `lllite_strength_scale` | import `gen_profile` 讀實值 | ✅ 全 family ＝ 1.0（零回歸）；0.6×{1.0,1.7,2.2}＝{0.600,1.020,1.320} |
| IPA 補方 | import `image_ops` 真的跑圖 | ✅ 476×1098→1098²、303×691→691²、1024²原樣回傳；CN 既有呼叫 303×691→461×691 不變 |
| VRAM 決策表 | 純函式模擬 13 種情境（含 5 筆歷史誤判樣本 ＋ **09-19 逾時當下的兩筆實況**） | ✅ 全數符合期望；兩筆實況由「放行」轉為「拒絕」 |

**沙箱做不到，需使用者本機執行**

1. **`cd backend && pytest tests/`** —— 沙箱無 `pytest`（CLAUDE.md 已載明）。本輪**沒跑過測試**。
   重點看 `test_vram_coexist.py`（N13 改動）、`test_lora_arch.py`（+5）、
   `test_gen_profile.py`（+2）、`test_image_ops.py`（+3）、
   以及 `test_all_custom_workflows_are_registered`（E1'）。
   ⚠️ 這是**第三輪**被同一個護欄擋下卻沒跑，見 BACKLOG §A6 S4-V1。
2. **必須重啟後端** —— `config.py` 是模組常數，`gen_profile` / `image_ops` / `workflow_builder`
   / `character_design_service` 都是 Python 模組。（`prompt_profiles.yml` 不用，不快取。）
3. **workflow JSON 改動不需重啟**（每次生成重讀）。
4. 前端未動，不需 `npm run build`。
5. **沙箱不跑 git 寫入** —— 改動目前未進 git。

#### 四、交給使用者的測試順序

> 每一項固定 seed、沿用 prompt。**先重啟後端。**

| 順 | 測什麼 | 怎麼測 | 預期 | 失敗徵兆與回滾 |
|---|---|---|---|---|
| 1 | **V1＋V2＋V3**（成本） | `Advanced_V38` 出 1 張，**不掛 LoRA、不勾概念圖參考**，與 #643（66.1s）比 | 仍在 1 分鐘量級；log 出現 `Detailer: ... -> (1024, ...)` 而非 1534 | 若臉部出現接縫／邊緣突兀 ＝ crop_factor 2.0 太緊 → node 72／31 改回 3.0／2.5 |
| 2 | **L1＋L2**（LoRA 觸發詞） | 掛 `Blue_archive_style` @0.8 再出 1 張。看 log 有沒有 `LoRA 觸發詞已補入正向：Blue archive style​` | BA 畫風明顯強於 2026-09-19 那幾張（那幾張沒有觸發詞） | 畫風過頭／角色被拉走 → LoRA 權重降到 0.5~0.6 |
| 3 | **V3 的代價** | 同上觀察 log 的 `VRAM:` 行 | 應看到「卸載另一方」而非「enough memory — keeping ollama loaded」；Ollama 重載約 10~30s | 若覺得卸太兇 → `.env` 設 `COMFYUI_RESIDENT_MIN_FREE_GB=8` |
| 4 | **I1**（IPA 補方） | 勾回「概念圖參考」出 1 張 | log 出現 `[ipa-letterbox] 476x1098 → 1098x1098`；ComfyUI 端**不再印** `not a square ... crop it at the center` | — |
| 5 | **軌 S**（畫風五組） | 照 `doc/target/SYNC-005_軌S_畫風算子AB_操作單_20260919.md` | 見該操作單 | — |

> **順序理由**：1 先確認成本壓下來（不然後面每輪要等 20 分鐘）；2 才是畫風；
> 4 排在 2 之後是因為 IPA 會多吃 1208MB CLIPVision，先讓 2 在最寬鬆的條件下跑。

#### 五、落地後首輪實測（#648～#651）與 L3 修正

後端已於 00:25:58 重啟，改動**有**生效 —— `[ipa-letterbox] 303x691 → 691x691` 實證軌 I 成功。
但軌 L 全程空轉：

**L3（高）`COMFYUI_LORAS_DIR` 指向不存在的目錄。**
`config.py:43` 預設 `C:\ComfyUI\models\loras`，`.env` 那行被註解掉，實際在 `F:\wk\ComfyUI_portable\...`。
兩個吃這個常數的功能都**安靜降級**：`lora_trigger_words()` 回 `[]`（軌 L 等於沒做）、
`_lora_arch()` 回 `None`（架構健檢從 2026-06-21 起一直在空轉，既有缺陷今天才暴露）。

| # | 修正 | 檔案 |
|---|---|---|
| L3a | 補 `COMFYUI_LORAS_DIR=F:\wk\ComfyUI_portable\ComfyUI\models\loras` | 專案根 `.env` |
| L3b | `_lora_dir_ok()`：目錄不存在 warn-once，兩個函式都先問一次（沿用 `_PROFILE_MISS_WARNED` 慣例） | `workflow_builder.py` |
| L3c | 測試 +2（安全降級且只吵一次／目錄存在不吵） | `tests/test_lora_arch.py` |

> **Claude 的疏失**：沙箱測 `lora_trigger_words` 時手動傳了正確路徑，沒驗證該常數在使用者機器上指到哪。
> 同型教訓：「分析前先用 runtime log 確認實際載入的檔／設定」—— 該驗的不只是邏輯，還有它吃的設定值。

**三張回饋圖都不是軌 S 的對照組**，且 LoRA 只有殘留效果
⇒ 目前沒有任何一張圖能判斷 D1（純 prompt）的上限。順序因此修正：

```
0. 重啟後端（.env 改了）
1. Advanced_V38 ＋ LoRA 0.8 → 確認 log 出現「LoRA 觸發詞已補入正向」
       └─ 一張圖回答「BA LoRA 行不行」＝ D1 該不該重開
2. 有效 → 重開 D1；無效 → 才跑軌 S 五組
3. Anima：掃 lllite_strength_scale 1.7 / 2.2
```

⚠️ 改用 `Advanced_V38.json`；`Standard_V38.json` 的背景洗白（N10）未解，會多一個變因。

<!-- HANDOFF: Claude DONE @ 2026-09-20 -->

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
