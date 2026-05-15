# RTX 5070 Ti 深度優化指南 (極致效能篇)

本指南針對 RTX 5070 Ti (16GB VRAM) 提供三項核心優化方案，旨在實現「瞬發生圖」與「流暢 AI 對話」。

---

## 1. ComfyUI 導入 TensorRT 加速 (生圖速度提升 200%)

TensorRT 是 NVIDIA 開發的推理優化引擎，能針對特定顯卡編譯模型。

### 操作步驟：
1.  **安裝插件**：在 ComfyUI 中安裝 `ComfyUI_TensorRT` 自定義節點。
2.  **模型轉換 (Engine Build)**：
    - 在 ComfyUI 介面選擇 `TensorRT Engine Object Creator`。
    - 輸入你的 SDXL 模型路徑，設定 `min_batch: 1`, `max_batch: 1`。
    - **關鍵參數**：設定最佳解析度為 `1024x1024`。
3.  **執行編譯**：點擊 Generate。這會消耗大量 CPU/GPU 資源約 5-10 分鐘，生成 `.engine` 檔案。
4.  **切換 Workflow**：使用 TensorRT 專屬的 Unet Loader 加載該 `.engine` 檔案。

### 效能預期：
- **標準 SDXL**：約 6-8 秒。
- **TensorRT 優化後**：約 **1.5 - 3 秒**。

---

## 2. Ollama 混合量化策略 (K-Quants)

對於 16GB 顯存，我們的目標是讓模型完全駐留在 GPU 中，避免切換到 RAM 導致的卡頓。

### 優化建議：
- **模型選擇**：`qwen2.5-vl:7b` (視覺) 或 `llama3.1:8b` (文字)。
- **量化等級等級建議**：
  - **Q6_K (中強)**：推薦首選。權重損失極小，但體積比 F16 小很多。
  - **Q8_0 (最強)**：如果你只運行 Ollama（關閉 ComfyUI），5070 Ti 足以應付 Q8。
- **自定義 Modelfile**：
  ```dockerfile
  FROM qwen2.5-vl:7b-instruct-q6_K
  PARAMETER num_gpu 99
  PARAMETER num_thread 8
  PARAMETER num_ctx 8192
  ```
- **執行指令**：`ollama create my-optimized-qwen -f Modelfile`。

---

## 3. VRAM Guardian (後端顯存動態管理)

這是解決「Ollama 與 ComfyUI 互搶顯存」的進階方案。

### 邏輯設計 (Backend 實作概念)：
在 `backend/app/services/ai/art_service.py` 中，我們需要實作一個簡單的狀態機：

```python
# 概念代碼：VRAM 管理器
class VRAMGuardian:
    def __init__(self):
        self.current_owner = None # 'ollama' or 'comfyui'

    async def request_focus(self, tool_name: str):
        if self.current_owner == tool_name:
            return
        
        if tool_name == 'comfyui':
            # 讓 Ollama 釋放顯存 (透過 API 卸載模型)
            await ollama_client.unload_all_models()
        elif tool_name == 'ollama':
            # 讓 ComfyUI 釋放顯存 (觸發 GC 或重啟)
            await comfyui_client.free_vram()
            
        self.current_owner = tool_name
```

### 操作指南：
1.  **Ollama 卸載模型**：呼叫 `/api/generate` 並將 `keep_alive` 設為 `0`。
2.  **ComfyUI 釋放**：呼叫 `/free` 接口或在 Workflow 最後加入 `Garbage Collector` 節點。

---

## 4. 終極目標：AI 即時聯動 (The "Flow" State)

當這三者結合時，你的 5070 Ti 將能支持以下場景：
- **即時草稿分析**：在畫板勾勒幾筆，0.5 秒內 Ollama 給出改進建議。
- **背景自動補完**：你在寫小說時，後端利用 TensorRT 在 2 秒內偷偷生成下一段劇情的參考圖，完全不干擾你的寫作節奏。

---

## 5. 常見問題與警告
- **過熱風險**：TensorRT 編譯時 GPU 會滿載，請確保 5070 Ti 風扇曲線調整正確。
- **顯存溢出 (OOM)**：若同時跑 Q8 LLM + SDXL，16GB 可能會爆。**VRAM Guardian 是必做的核心功能**。
