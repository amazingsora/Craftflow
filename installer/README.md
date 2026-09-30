# Craftflow 一鍵安裝程式（CraftflowSetup.exe）

## 使用者：怎麼裝

1. 下載 `CraftflowSetup.exe`（GitHub Releases），或已 `git clone` 的話放進專案根目錄。
2. 雙擊執行，照提示回答 Y/n。可以重複執行，已完成的步驟會自動略過。
3. 完成後雙擊 `start.bat`（或桌面「Craftflow」捷徑）。

| 參數 | 用途 |
|---|---|
| `--check-only` | 只做環境體檢，不安裝任何東西（出問題時先跑這個） |
| `--comfyui <路徑>` | 直接指定 ComfyUI（portable 根目錄或含 `main.py` 的目錄） |
| `--repo <路徑>` | 指定 Craftflow 專案路徑（預設從 exe 所在位置往上找） |
| `-y` / `--yes` | 全部採預設值（無人值守） |

結果報告：`data/logs/install_report.txt`（含 ComfyUI 缺件清單與完整 log）。

## 流程

```
[1] 作業系統  Windows 10/11 x64 ─ FAIL 即停
[2] 顯示卡    nvidia-smi → 無 NVIDIA / VRAM<8GB 級 / compute<7.5 ─ FAIL 即停
[3] 專案      往上找 backend/main.py；找不到 → git clone 或手動選
[4] 相依      Python 3.11、Node 18+、Ollama；缺 → winget 安裝（Ollama 缺只警告）
[5] ComfyUI   選資料夾 → 啟動中就用 /object_info 即時驗證，否則可代為啟動或靜態掃描
              逐支比對 data/custom_workflows/*.json 需要的節點包與模型（缺件只警告）
[6] .env      從 .env.example 建立；寫入 COMFYUI_DIR / COMFYUI_LAUNCHER / COMFYUI_LORAS_DIR
[7] 後端      backend/.venv（3.11）+ pip install -r requirements.txt
[8] 前端      npm ci + npm run build
[9] Ollama    確認服務；缺 .env 指定的 TEXT_MODEL / VISION_MODEL 就 ollama pull
[10] 冒煙     暫時起 uvicorn，GET / 成功即通過（順便建立 DB）
```

## GPU 規格門檻（`checks.py` 開頭常數）

| 條件 | 判定 | 依據 |
|---|---|---|
| 無 NVIDIA 卡／驅動 | FAIL | 生圖需要 CUDA |
| VRAM < 8 GB 級 | FAIL | `MIN_VRAM_GB` |
| compute < 7.5（GTX 10 系以前） | FAIL | `MIN_COMPUTE_CAP` |
| VRAM < 11 GB | WARN | 對齊 `COMFYUI_REQUIRED_VRAM_GB` 預設 |
| RTX 50 系＋驅動 < 570 | WARN | Blackwell 需 R570+ |
| VRAM < 18 GB | 提示 | ComfyUI(11)+Ollama(7) 無法同駐，後端會輪流佔用 |

## 開發者：打包與維護

```bat
installer\build_exe.bat      :: 自建 installer\.venv（不碰 ComfyUI 共用的 pyenv）→ 跑測試 → dist\CraftflowSetup.exe
```

- 發版：push tag `installer-v*` → GitHub Actions（`.github/workflows/build-installer.yml`）在 Windows runner 打包並附到 Release。
- **新增 workflow 用到新的 custom node** → `installer/tests/test_checks.py` 的反向護欄會失敗，到 `checks.NODE_PACKS` 登錄該節點所屬的包與 repo URL。
- 後端改了 IPA／CN／LLLite 模型常數 → 同步 `checks.OPTIONAL_FEATURES`（同樣有測試守著）。
- PyInstaller onefile 偶爾被 Windows Defender 誤報，屬已知現象；需要時可改 `--onedir` 或做程式碼簽章。
