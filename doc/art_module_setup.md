# Craftflow Art Module — 安裝指南

本指南涵蓋繪圖分析模組的完整安裝流程。  
硬體假設：**NVIDIA RTX 5070 Ti**（主力 AI 運算）+ Windows 11。

---

## 模式總覽

| 模式 | 說明 | 需要 |
|------|------|------|
| `enhance` ★ | 草稿 + 自己的作品 → 同風格商業品質參考圖 | ComfyUI + IP-Adapter |
| `style_explore` | 草稿 + 任意風格參考圖 → 探索不同畫風 | ComfyUI + IP-Adapter |
| `sketch_critique` | 草稿 → 文字改進意見 | Ollama |
| `line_color` | 線稿 → 配色建議 | Ollama |
| `finished_critique` | 完成圖 → 詳細改進意見 | Ollama |
| `sketch_to_line` | 草稿 → 清稿線稿 | ComfyUI |

---

## 目錄

1. [Python 依賴套件](#1-python-依賴套件)
2. [Ollama（視覺分析）](#2-ollama視覺分析)
3. [ComfyUI（圖像生成）](#3-comfyui圖像生成)
4. [設定工作流模板](#4-設定工作流模板)
5. [驗證安裝](#5-驗證安裝)
6. [常見問題](#6-常見問題)

---

## 1. Python 依賴套件

目前專案沒有 `requirements.txt`，手動安裝以下套件：

```bash
pip install requests
```

> `requests` 是唯一新增的外部依賴（用於呼叫 Ollama 和 ComfyUI API）。

---

## 2. Ollama（視覺分析）

視覺分析的三個模式（`sketch_critique`、`line_color`、`finished_critique`）都需要 Ollama。

### 2-1. 安裝 Ollama

前往 [https://ollama.com/download](https://ollama.com/download) 下載 Windows 版安裝檔，執行安裝。

安裝完成後確認：

```bash
ollama --version
```

### 2-2. 下載視覺模型（二選一）

| 模型 | 大小 | 效果 | 推薦情境 |
|------|------|------|----------|
| `llava` | ~4 GB | 普通 | 快速測試 |
| `qwen2-vl` | ~8 GB | 較好，中文理解強 | **推薦** |

```bash
# 擇一下載
ollama pull llava
ollama pull qwen2-vl
```

### 2-3. 啟動 Ollama 服務

安裝後 Ollama 通常會自動在背景執行。若未啟動：

```bash
ollama serve
```

確認服務正常：

```bash
# 應回傳模型清單
curl http://localhost:11434/api/tags
```

---

## 3. ComfyUI（圖像生成）

`enhance`、`style_explore`、`sketch_to_line` 模式都需要此步驟。若只用文字分析功能可跳過。

### 3-1. 安裝 ComfyUI（便攜版）

前往 `github.com/comfyanonymous/ComfyUI` 的 **Releases** 頁面，  
下載 `ComfyUI_windows_portable_nvidia.7z`，解壓縮到任意位置（例如 `F:\wk\ComfyUI_portable`）。

> **不要用 git clone 安裝**。目前最新開發版的依賴套件（`comfy-kitchen`）尚未發布到 PyPI，  
> 直接跑 `pip install -r requirements.txt` 會失敗。便攜版內建完整環境，不需要手動安裝任何東西。

### 3-2. 安裝 ComfyUI Manager（選用但推薦）

ComfyUI Manager 可以透過介面安裝缺少的節點。

```powershell
cd F:\wk\ComfyUI_portable\ComfyUI\custom_nodes
git clone https://github.com/ltdrdata/ComfyUI-Manager.git
```

### 3-3. 安裝自定義節點

```powershell
cd F:\wk\ComfyUI_portable\ComfyUI\custom_nodes

# ControlNet 預處理節點（Scribble / LineArt 等）
git clone https://github.com/Fannovel16/comfyui_controlnet_aux.git

# IP-Adapter 節點（enhance / style_explore 模式必要）
git clone https://github.com/cubiq/ComfyUI_IPAdapter_plus.git
```

> 便攜版不需要在節點資料夾內跑 `pip install`，ComfyUI 啟動時會自動處理。

### 3-4. 下載模型檔案

#### 動漫風 SDXL 模型（擇一）→ `ComfyUI/models/checkpoints/`

| 模型 | 大小 | 特色 |
|------|------|------|
| **AnythingXL**（推薦） | ~6.5 GB | 經典動漫風，線條乾淨、眼睛有神 |
| BluePencilXL | ~6.5 GB | 偏手繪感，更接近漫畫原稿風格 |

前往 Civitai（civitai.com）搜尋模型名稱，選擇 SDXL 版本的 `.safetensors` 下載。

#### ControlNet 模型（擇一）→ `ComfyUI/models/controlnet/`

| 模型 | 適合情境 | 大小 |
|------|----------|------|
| **controlnet-scribble-sdxl-1.0**（推薦入門） | 草稿粗糙、線條不乾淨 | ~2.5 GB |
| controlnet-union-sdxl-1.0 | 草稿輪廓清楚，想保留更多細節 | ~2.5 GB |

前往 HuggingFace 搜尋 `xinsir/controlnet-scribble-sdxl-1.0` 或 `xinsir/controlnet-union-sdxl-1.0`，只需下載 `.safetensors` 檔案。

#### IP-Adapter 模型（enhance / style_explore 模式必要）→ `ComfyUI/models/ipadapter/`

| 檔案 | 大小 | 說明 |
|------|------|------|
| `ip-adapter-plus_sdxl_vit-h.safetensors` | ~1 GB | IP-Adapter SDXL 版本 |

前往 HuggingFace 搜尋 `h94/IP-Adapter`，進入 `sdxl_models/` 資料夾下載。  
`ipadapter` 資料夾不存在時需手動建立。

#### CLIP Vision 模型 → `ComfyUI/models/clip_vision/`

| 檔案 | 大小 | 說明 |
|------|------|------|
| `open_clip_model.safetensors` | ~3.9 GB | IP-Adapter 的視覺編碼器（OpenCLIP ViT-H-14） |

在 `h94/IP-Adapter` 的 `models/image_encoder/` 資料夾下載 `open_clip_model.safetensors`。  
（同目錄還有 `model.safetensors`，那是 OpenAI CLIP，**不要下載錯**）

> 只需下載指定的單一檔案，不需要整個資料夾。

### 3-5. 啟動 ComfyUI

直接執行便攜版的啟動腳本：

```
F:\wk\ComfyUI_portable\run_nvidia_gpu.bat
```

瀏覽器開啟 `http://localhost:8188` 確認介面正常。

---

## 4. 設定工作流模板

開啟 `tools/Craftflow/diffusion/workflows/sketch_to_lineart.json`，  
將模型名稱改為你實際下載的檔案名稱：

```json
"1": {
    "class_type": "CheckpointLoaderSimple",
    "inputs": {
        "ckpt_name": "這裡填你下載的 SDXL 模型檔名.safetensors"
    }
},
...
"4": {
    "class_type": "ControlNetLoader",
    "inputs": {
        "control_net_name": "這裡填你下載的 ControlNet 模型檔名.safetensors"
    }
}
```

目前設定（已對應實際下載的檔名）：

```json
"ckpt_name": "AnythingXL_xl.safetensors"
"control_net_name": "controlnet-scribble-sdxl-1.0.safetensors"
"ipadapter_file": "ip-adapter-plus_sdxl_vit-h.safetensors"
"clip_name": "open_clip_model.safetensors"
```

> 若之後換了模型，檔名請以資料夾裡看到的名稱為準，大小寫需完全一致。

---

## 5. 驗證安裝

在 `tools/Craftflow/` 目錄下執行：

### 確認 Ollama 模型可用

```bash
ollama list
# 應看到 llava 或 qwen2-vl
```

### 測試視覺分析（準備任意一張圖片）

```bash
python art_main.py 你的圖片.png --mode sketch_critique --model llava
# 成功：在 analysis/ 目錄產生 *_sketch_critique.md
```

### 測試風格強化（主要功能，確認 ComfyUI 已啟動）

```bash
# 準備：草稿圖 + 至少一張自己的完成作品
python art_main.py 你的草稿.png --mode enhance --style-ref 你的作品1.png 你的作品2.png
# 成功：在 analysis/ 目錄產生 *_enhance.png 和 *_enhance_result.md
```

### 測試風格探索（次要功能）

```bash
python art_main.py 你的草稿.png --mode style_explore --style-ref 目標風格參考圖.png
# 成功：在 analysis/ 目錄產生 *_style_explore.png 和 *_style_explore_result.md
```

### 測試線稿化（工具功能）

```bash
python art_main.py 你的草稿.png --mode sketch_to_line
# 成功：在 analysis/ 目錄產生 *_lineart.png 和 *_lineart_result.md
```

---

## 6. 常見問題

### `[Vision analysis unavailable: Ollama is not running]`

Ollama 未啟動或未安裝。執行 `ollama serve` 後重試。

### `ComfyUI is not running`

ComfyUI 未啟動。在 ComfyUI 目錄執行 `python main.py --listen` 後重試。

### ComfyUI 報錯 `model not found`

`sketch_to_lineart.json` 裡的模型檔名與實際下載的檔名不符。  
確認 `ComfyUI/models/checkpoints/` 和 `ComfyUI/models/controlnet/` 裡的實際檔名並更新 JSON。

### 視覺分析結果是英文

預設模型（llava）中文回應品質參差不齊。改用 qwen2-vl：

```bash
ollama pull qwen2-vl
python art_main.py 圖片.png --mode sketch_critique --model qwen2-vl
```

### RTX 5070 Ti CUDA 版本問題

若 PyTorch 無法偵測到 GPU：

```bash
python -c "import torch; print(torch.cuda.is_available())"
# 應輸出 True
```

若為 False，重新安裝對應 CUDA 版本的 PyTorch：

```bash
pip uninstall torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

---

## 快速參考：所有指令

```bash
# ★ 主要：草稿 → 同風格商業品質參考圖（提供自己的完成作品作為風格參考）
python art_main.py draft.png --mode enhance --style-ref my_art1.png my_art2.png

# 次要：草稿 → 探索不同畫風
python art_main.py draft.png --mode style_explore --style-ref ghibli_ref.png

# 草稿 → 文字改進意見
python art_main.py draft.png --mode sketch_critique

# 線稿 → 配色建議
python art_main.py lineart.png --mode line_color

# 完成圖 → 詳細改進意見（光影、色彩、細節）
python art_main.py final.png --mode finished_critique

# 草稿 → 清稿線稿
python art_main.py draft.png --mode sketch_to_line

# 使用更好的視覺模型（文字分析模式）
python art_main.py 圖片.png --mode sketch_critique --model qwen2-vl

# 指定輸出目錄
python art_main.py 圖片.png --mode enhance --style-ref ref.png --output-dir ./my_output
```
