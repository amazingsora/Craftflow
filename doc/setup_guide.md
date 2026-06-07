# Craftflow 安裝與建置手冊

**適用版本：** Phase 1  
**最後更新：** 2026-06-07

---

## 目錄

1. [前置需求](#前置需求)
2. [步驟 0 — 依硬體選擇模型](#步驟-0--依硬體選擇模型)
3. [情境 A — Windows 主力機（有 GPU）](#情境-a--windows-主力機有-gpu)
4. [情境 B — 無 GPU 輕量機](#情境-b--無-gpu-輕量機)
5. [ComfyUI 必要節點與模型](#comfyui-必要節點與模型)
6. [LoRA 訓練設定（可選）](#lora-訓練設定可選)
7. [Personal Style Preset（可選）](#personal-style-preset可選)
8. [常見問題](#常見問題)

---

## 前置需求

### 必裝工具

| 工具 | 版本 | 說明 |
|---|---|---|
| Git | 任意 | 拉取程式碼 |
| Docker Desktop | 4.x+ | 執行 Backend + Frontend |
| Ollama | 最新 | 本地 LLM 服務 |
| Node.js | **20 LTS** | 本地前端開發（非 Docker 時需要） |

### 安裝指令（Windows / PowerShell）

```powershell
winget install --id Git.Git -e
winget install --id Docker.DockerDesktop -e
winget install --id Ollama.Ollama -e
winget install --id OpenJS.NodeJS.LTS -e --version 20.19.1
```

> 安裝完成後**重新開啟 PowerShell**，讓 PATH 生效。

```powershell
git --version        # git version 2.x.x
docker --version     # Docker version 2x.x.x
ollama --version     # ollama version 0.x.x
node --version       # v20.x.x
npm --version        # 10.x.x
```

---

## 步驟 0 — 依硬體選擇模型

> **目標：** AI 功能在 **1–3 分鐘內**完成。決定因素：有 GPU 看 **VRAM**，無 GPU 看 **RAM**。

### 有 GPU（NVIDIA RTX 系列）

| GPU 型號 | VRAM | TEXT_MODEL | VISION_MODEL | 文字 | 視覺 | ComfyUI | ≤3min |
|---|---|---|---|---|---|---|---|
| RTX 5090 | 32GB | `qwen2.5:14b` | `qwen2.5vl:7b` | ~12s | ~20s | ~35s | ✅ |
| RTX 4090 / 3090 | 24GB | `qwen2.5:14b` | `qwen2.5vl:7b` | ~17s | ~27s | ~50s | ✅ |
| RTX 5070 Ti / 4080 | 16GB | `dolphin-llama3` | `qwen2.5vl:7b` | ~25s | ~40s | ~75s | ✅ ← **當前配置** |
| RTX 5070 / 3080 Ti | 12GB | `dolphin-llama3` | `llava:7b` | ~33s | ~53s | ~100s | ✅ |
| RTX 4070 / 3060 12GB | 12GB | `dolphin-llama3` | `llava:7b` | ~38s | ~62s | ~110s | ✅ |
| RTX 4060 Ti / 3070 | 8GB | `llama3.2:3b` | `llava:7b` | ~50s | ~80s | ~2.5min | ✅ |
| RTX 4060 / 3060 8GB | 8GB | `llama3.2:3b` | `moondream` | ~60s | ~100s | ~3min | ⚠️ 邊緣 |

> ⚠️ **8GB VRAM**：ComfyUI 生圖可能壓線，解析度建議不超過 512×512。

### 無 GPU（CPU 模式）

> ❌ CPU 模式無法達到 1–3 分鐘目標；ComfyUI 圖像生成亦不可用。

| RAM | TEXT_MODEL | VISION_MODEL | 文字 | 視覺 |
|---|---|---|---|---|
| 64GB | `llama3.2:8b` | `llava:7b` | ~5min | ~10min |
| 32GB | `llama3.2:8b` | `llava:7b` | ~6min | ~13min |
| 16GB | `llama3.2:3b` | `moondream` | ~10min | ~20min+ |

---

## 情境 A — Windows 主力機（有 GPU）

### 1. 啟動 Ollama

```powershell
$env:OLLAMA_HOST = "0.0.0.0"
ollama serve
```

依步驟 0 拉取模型（首次依網速需時）：

```powershell
ollama pull <TEXT_MODEL>      # 例如 dolphin-llama3
ollama pull <VISION_MODEL>    # 例如 qwen2.5vl:7b
```

### 2. 啟動 ComfyUI

進入 ComfyUI 資料夾執行（portable 版）：

```powershell
.\run_nvidia_gpu.bat -- --listen 0.0.0.0
```

> `--listen 0.0.0.0` 是必要的，否則 Docker 容器無法連入。

安裝必要的 ComfyUI Custom Nodes → 見 [ComfyUI 必要節點與模型](#comfyui-必要節點與模型)。

### 3. 複製專案與設定環境

```powershell
git clone <repo-url> Craftflow
cd Craftflow
copy .env.example .env
```

開啟 `.env`，依步驟 0 的結果填入模型：

```env
TEXT_MODEL=dolphin-llama3
VISION_MODEL=qwen2.5vl:7b
```

其他 `.env` 設定見後續章節說明。

### 4. 啟動 Docker 服務

```powershell
docker compose up --build
```

首次 build 需數分鐘（安裝 Python 套件）。

### 5. 確認服務

| 服務 | 網址 |
|---|---|
| Backend API | http://localhost:8000/api/v1/status |
| Frontend | http://localhost:3000 |
| Ollama | http://localhost:11434 |
| ComfyUI | http://localhost:8188 |

---

## 情境 B — 無 GPU 輕量機

### 1. 啟動 Ollama（CPU 模式）

```powershell
$env:OLLAMA_HOST = "0.0.0.0"
ollama serve
ollama pull <TEXT_MODEL>
ollama pull <VISION_MODEL>
```

### 2. 複製專案與設定環境

```powershell
git clone <repo-url> Craftflow
cd Craftflow
copy .env.example .env
```

編輯 `.env`：

```env
TEXT_MODEL=llama3.2:3b
VISION_MODEL=llava:7b
```

> ComfyUI 不在此裝置，`COMFYUI_BASE` 保持預設；系統偵測不到時顯示提示但不崩潰。

### 3. 啟動 Docker 服務

```powershell
docker compose up --build
```

### 4. 可用功能一覽

| 功能 | 有 GPU | 無 GPU |
|---|---|---|
| 小說管理 / 章節 CRUD | ✅ | ✅ |
| AI 文字改寫建議 | ✅ | ✅（較慢）|
| 草稿視覺分析 | ✅ | ✅（較慢）|
| 角色人設圖生成 | ✅ | ❌ |
| LoRA 訓練 | ✅ | ❌ |

---

## ComfyUI 必要節點與模型

> **全部圖像生成功能都依賴以下節點和模型。**  
> 建議透過 [ComfyUI Manager](https://github.com/ltdrdata/ComfyUI-Manager) 安裝 custom nodes。

### Custom Nodes

| 節點 | 用途 | 安裝方式 |
|---|---|---|
| `comfyui_controlnet_aux` | ControlNet 預處理器（**AnimeLineArtPreprocessor** 等） | ComfyUI Manager 搜尋 "controlnet aux" |
| `comfyui_ipadapter_plus` | IP-Adapter（角色外觀參考） | ComfyUI Manager 搜尋 "ipadapter plus" |
| `ComfyUI-Manager` | 節點管理器（安裝其他節點的前提） | [GitHub](https://github.com/ltdrdata/ComfyUI-Manager) |
| `comfyui-custom-scripts` | WD14 Tagger（tag 分析功能） | ComfyUI Manager 搜尋 "custom scripts" |
| `rgthree-comfy` | rgthree Seed 等輔助節點 | ComfyUI Manager 搜尋 "rgthree" |
| `comfyui-kjnodes` | KJNodes（workflow 輔助） | ComfyUI Manager 搜尋 "kjnodes" |
| `ComfyUI-GGUF` | GGUF 格式模型支援（Flux2 所需） | ComfyUI Manager 搜尋 "gguf" |
| `comfyui-easy-use` | Easy Use 輔助節點 | ComfyUI Manager 搜尋 "easy use" |
| `comfyui-impact-pack` | Impact Pack 工具節點 | ComfyUI Manager 搜尋 "impact" |

### 模型檔案

#### SDXL Checkpoints（至少選一個）

| 檔案名稱 | 說明 | 放置位置 |
|---|---|---|
| `fabricatedXL_v70.safetensors` | 主力動漫 SDXL checkpoint | `models/checkpoints/` |
| `animagineXL40_v4Opt.safetensors` | 備用 SDXL | `models/checkpoints/` |
| `novaAnimeXL_ilV190.safetensors` | 備用 SDXL（Illustrious 系） | `models/checkpoints/` |

#### ControlNet（Union ProMax，必裝）

| 檔案名稱 | 說明 | 放置位置 |
|---|---|---|
| `diffusion_pytorch_model_promax.safetensors` | Union ControlNet ProMax（支援 Lineart、Canny、Depth 等多模式） | `models/controlnet/` |

#### IP-Adapter（必裝）

| 檔案名稱 | 說明 | 放置位置 |
|---|---|---|
| `ip-adapter-plus_sdxl_vit-h.safetensors` | SDXL IP-Adapter Plus | `models/ipadapter/` |
| `CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors` | IP-Adapter 搭配用 CLIP Vision | `models/clip_vision/` |

#### Flux2（Canvas Expand 功能用，可選）

> Canvas Expand 功能（半身概念圖補全下半身）需要 Flux2 模型。  
> 若不需要此功能可略過。

| 檔案名稱 | 說明 | 放置位置 |
|---|---|---|
| `flux2-dev-q5_k_m.gguf` | Flux2 Dev（GGUF 量化） | `models/diffusion_models/` |
| `mistral_3_small_flux2_fp8.safetensors` | Flux2 CLIP text encoder（Mistral） | `models/text_encoders/` |
| `t5xxl_fp8_e4m3fn.safetensors` | Flux2 T5 text encoder | `models/text_encoders/` |
| `clip_l.safetensors` | Flux2 CLIP-L | `models/text_encoders/` |

### Custom Workflows

將 `data/custom_workflows/` 內的 JSON 複製到 ComfyUI workflow 目錄或透過系統使用（後端自動讀取）。

| Workflow 檔案 | 用途 |
|---|---|
| `Standard_V35.json` | 角色人設圖主力 workflow（SDXL + IPA + Union CN AnimeLineArt） |
| `canvas_expand_flux.json` | 半身概念圖補全下半身（Flux2 Inpaint） |

---

## LoRA 訓練設定（可選）

> 需另外安裝 [kohya_ss](https://github.com/bmaltais/kohya_ss)。

### 安裝 kohya_ss

參考官方文件，預設安裝至 `C:\kohya_ss`。

### `.env` 設定

```env
TRAINING_RUNNER_MODE=local          # local（本機 subprocess）| remote（Docker 模式）
KOHYA_PATH=C:\kohya_ss              # kohya_ss 安裝路徑
TRAINING_IMAGES_DIR=F:\wk\Craftflow\data\training_images
COMFYUI_LORAS_DIR=F:\wk\ComfyUI_portable\ComfyUI\models\loras
```

> 訓練完成後 LoRA 會自動複製到 `COMFYUI_LORAS_DIR`，ComfyUI 立即可用。

---

## Personal Style Preset（可選）

> 固定畫風使用者（如 Blue Archive 風格）可啟用此功能，角色生圖時自動附加畫風標籤。

在 `.env` 加入：

```env
PERSONAL_STYLE_ENABLED=true
PERSONAL_STYLE_EXTRA_TAGS=Blue Archive style, anime game illustration, clean lineart, soft shading, large expressive eyes, delicate face, pale skin, light blush, pastel tone

PERSONAL_NEGATIVE_ENABLED=true
PERSONAL_NEGATIVE=lowres, bad quality, worst quality, sketch, photorealistic, 3d, realistic, blurry face, deformed hands, extra fingers, bad anatomy, watermark
```

> `PERSONAL_STYLE_ENABLED=false`（預設）時完全不影響生圖行為。

---

## 後端套件（自動安裝）

Docker `build` 時會自動安裝 `backend/requirements.txt` 所有套件：

```
fastapi, uvicorn, sqlalchemy, pydantic, python-multipart
aiofiles, requests, pyyaml, pillow, toml, python-dotenv
```

若需本機直接跑（非 Docker）：

```powershell
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## 常見問題

**Q: `/api/v1/status` 顯示 Ollama unavailable？**  
確認 Ollama 用 `OLLAMA_HOST=0.0.0.0` 啟動，且 docker-compose.yml 有 `extra_hosts: host.docker.internal:host-gateway`。

**Q: ComfyUI 連不上？**  
確認啟動指令含 `--listen 0.0.0.0`，否則預設只監聽 127.0.0.1，Docker 容器無法連入。

**Q: 角色人設圖出現機甲/外骨骼效果？**  
`Standard_V35.json` 的 ControlNet preprocessor 必須是 `AnimeLineArtPreprocessor`（非 `CannyEdgePreprocessor`）。已於 2026-06-07 修正，重新 pull 最新版本即可。

**Q: Canvas Expand 跑出 `ModuleNotFoundError: No module named 'transformers.models.pixtral'`？**  
需要修正 ComfyUI 的 `comfy/text_encoders/flux.py`，加入第三層 fallback。參考 `doc/2026-06-07_開發記錄.md` 第一節。

**Q: 換裝置或更換模型？**  
只需修改 `.env` 的 `TEXT_MODEL` / `VISION_MODEL`，重啟 Docker 即生效。

**Q: 本機直接跑（非 Docker）時 .env 不生效？**  
`config.py` 會自動在啟動時 `load_dotenv()`，確認 `.env` 在專案根目錄即可。
