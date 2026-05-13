# Craftflow — ComfyUI 配置文件

**適用版本：** Phase 1  
**最後更新：** 2026-05-14  
**硬體基準：** RTX 5070 Ti（16GB VRAM）

---

## 功能對應表

| 功能 | Workflow 檔案 | 需要的模型 |
|---|---|---|
| 草稿 → 線稿化 | `sketch_to_lineart.json` | Checkpoint + ControlNet |
| 草稿 → 風格強化 / 探索 | `style_enhance.json` | Checkpoint + ControlNet + IP-Adapter + CLIP Vision |
| 文字 → 生圖 | `text_to_image.json` | Checkpoint |

Workflow 檔案位置：`tools/Craftflow/diffusion/workflows/`

---

## 一、安裝 ComfyUI（便攜版）

前往 [ComfyUI Releases](https://github.com/comfyanonymous/ComfyUI/releases)，  
下載 `ComfyUI_windows_portable_nvidia.7z`，解壓縮到任意位置，例如：

```
F:\wk\ComfyUI_portable\
```

> ⚠️ **不要用 `git clone` 安裝**。開發版依賴尚未發布到 PyPI，`pip install -r requirements.txt` 會失敗。便攜版內建完整環境。

---

## 二、安裝自定義節點

進入 `ComfyUI_portable\ComfyUI\custom_nodes\`，執行：

```powershell
# 管理器（可透過 UI 安裝缺少的節點，強烈建議）
git clone https://github.com/ltdrdata/ComfyUI-Manager.git

# ControlNet 預處理（線稿化 / 風格強化必要）
git clone https://github.com/Fannovel16/comfyui_controlnet_aux.git

# IP-Adapter（風格強化必要）
git clone https://github.com/cubiq/ComfyUI_IPAdapter_plus.git
```

> 便攜版不需在節點目錄手動跑 `pip install`，ComfyUI 啟動時自動處理。

---

## 三、下載模型檔案

### 目錄結構

```
ComfyUI_portable/ComfyUI/models/
├── checkpoints/    ← SDXL 主模型
├── controlnet/     ← ControlNet 模型
├── ipadapter/      ← IP-Adapter 模型（需手動建立此資料夾）
└── clip_vision/    ← CLIP Vision 模型
```

### 模型清單

| 用途 | 檔名 | 大小 | 下載來源 | 放入資料夾 |
|---|---|---|---|---|
| SDXL 主模型 | `AnythingXL_xl.safetensors` | ~6.5 GB | [Civitai](https://civitai.com) 搜尋 AnythingXL | `checkpoints/` |
| ControlNet | `controlnet-scribble-sdxl-1.0.safetensors` | ~2.5 GB | [HuggingFace](https://huggingface.co/xinsir/controlnet-scribble-sdxl-1.0) | `controlnet/` |
| IP-Adapter | `ip-adapter-plus_sdxl_vit-h.safetensors` | ~1 GB | [HuggingFace](https://huggingface.co/h94/IP-Adapter) → `sdxl_models/` | `ipadapter/` |
| CLIP Vision | `open_clip_model.safetensors` | ~3.9 GB | [HuggingFace](https://huggingface.co/h94/IP-Adapter) → `models/image_encoder/` | `clip_vision/` |

> ⚠️ CLIP Vision 同目錄有兩個檔案：`model.safetensors`（OpenAI CLIP）與 `open_clip_model.safetensors`（OpenCLIP ViT-H-14）。**請只下載 `open_clip_model.safetensors`**，檔名不同功能不同。

**替代 SDXL 模型（依風格偏好擇一）：**

| 模型 | 特色 |
|---|---|
| AnythingXL（預設）| 動漫風，線條乾淨，眼睛有神 |
| BluePencilXL | 偏手繪感，接近漫畫原稿風格 |

---

## 四、確認 Workflow 設定

三個 JSON 的模型檔名已對應預設下載檔名，**若下載的檔名不同才需要修改**。

| JSON 內的 key | 預設值 | 對應模型 |
|---|---|---|
| `ckpt_name` | `AnythingXL_xl.safetensors` | SDXL 主模型 |
| `control_net_name` | `controlnet-scribble-sdxl-1.0.safetensors` | ControlNet |
| `ipadapter_file` | `ip-adapter-plus_sdxl_vit-h.safetensors` | IP-Adapter |
| `clip_name` | `open_clip_model.safetensors` | CLIP Vision |

> 大小寫需與資料夾內的實際檔名完全一致。

---

## 五、依顯卡調整 Workflow 參數

> **預設值為 RTX 5070 Ti（16GB）配置。** 其他顯卡依下表修改對應 JSON 欄位。

### 需要修改的欄位

三個 workflow 的解析度與步數位置：

| JSON 檔案 | 解析度節點 | 步數節點 |
|---|---|---|
| `text_to_image.json` | `"4"` → `width` / `height` | `"5"` → `steps` |
| `sketch_to_lineart.json` | `"9"` → `width` / `height` | `"8"` → `steps` |
| `style_enhance.json` | `"13"` → `width` / `height` | `"12"` → `steps` |

### 各顯卡建議配置

| GPU | VRAM | 解析度 | steps | style_enhance | 預期時間 |
|---|---|---|---|---|---|
| RTX 5090 | 32GB | 1024×1024 | 25 | ✅ | ~35–50s |
| RTX 4090 / 3090 | 24GB | 1024×1024 | 25 | ✅ | ~45–60s |
| RTX 5070 Ti / 4080 | 16GB | 1024×1024 | 20 | ✅ | ~70–100s **← 預設** |
| RTX 5070 / 3080 Ti | 12GB | 1024×1024 | 20 | ⚠️ 768×768 建議 | ~100–130s |
| RTX 4070 / 3060 12GB | 12GB | 768×768 | 20 | ⚠️ 768×768 | ~110–140s |
| RTX 4060 Ti / 3070 | 8GB | 768×768 | 20 | ⚠️ 512×512 | ~150–180s |
| RTX 4060 / 3060 8GB | 8GB | 512×512 | 15 | ⚠️ 512×512 | ~170–200s |

> **⚠️ style_enhance 特別說明：** 此 workflow 同時載入 ControlNet + IP-Adapter，VRAM 佔用最高。12GB 以下顯卡在 1024×1024 可能 OOM，建議降至 768×768 或 512×512。

### 修改範例（以 RTX 4070 12GB 為例）

編輯 `sketch_to_lineart.json`：
```json
"9": {
    "class_type": "EmptyLatentImage",
    "inputs": {
        "width": 768,
        "height": 768,
        "batch_size": 1
    }
},
"8": {
    "class_type": "KSampler",
    "inputs": {
        ...
        "steps": 20,
        ...
    }
}
```

同樣修改 `style_enhance.json` 節點 `"13"` 和 `"12"`，以及 `text_to_image.json` 節點 `"4"` 和 `"5"`。

---

## 七、啟動 ComfyUI

```powershell
# ⚠️ 必須加 --listen 0.0.0.0，否則 Docker 容器無法連入
.\run_nvidia_gpu.bat -- --listen 0.0.0.0
```

開啟瀏覽器確認：`http://localhost:8188`

---

## 八、預期生成時間（RTX 5070 Ti 基準）

| 功能 | Workflow | 預期時間 |
|---|---|---|
| 文字生圖（1024×1024，20 steps）| `text_to_image.json` | ~60–75s |
| 草稿線稿化（1024×1024，20 steps）| `sketch_to_lineart.json` | ~70–85s |
| 風格強化（1024×1024，25 steps）| `style_enhance.json` | ~80–100s |

> 其他顯卡預期時間請參考 `setup_guide.md` 步驟 0 的對照表。

---

## 九、常見問題

**Q: ComfyUI 啟動後，Backend 仍顯示 ComfyUI unavailable？**  
確認啟動指令包含 `--listen 0.0.0.0`。ComfyUI 預設只監聽 `127.0.0.1`，Docker 容器無法連入。

**Q: 執行 Workflow 時報 `model not found`？**  
JSON 裡的 `ckpt_name` / `control_net_name` 與資料夾內的實際檔名不符。確認大小寫並修正。

**Q: `style_enhance.json` 執行時報 IP-Adapter 節點缺失？**  
`ComfyUI_IPAdapter_plus` 未安裝或未載入。重啟 ComfyUI，若仍缺少，透過 ComfyUI Manager 安裝。

**Q: 換了 SDXL 模型想更新預設值？**  
修改對應 JSON 檔的 `ckpt_name` 欄位，填入實際檔名即可。
