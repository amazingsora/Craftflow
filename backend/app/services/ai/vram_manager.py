"""
VRAM Guardian — Dynamic GPU memory management for RTX 5000/4000 series.
Coordinates memory usage between Ollama (LLM) and ComfyUI (Diffusion).
"""
from __future__ import annotations

import asyncio
import logging
import requests
from typing import Literal

from starlette.concurrency import run_in_threadpool

from app.core.config import (
    OLLAMA_BASE,
    COMFYUI_BASE,
    VRAM_COEXIST_ENABLED,
    COMFYUI_REQUIRED_VRAM_GB,
    COMFYUI_RESIDENT_MIN_FREE_GB,
    OLLAMA_REQUIRED_VRAM_GB,
)
from app.services import comfyui_client

logger = logging.getLogger(__name__)

ServiceType = Literal["ollama", "comfyui"]

_GIB = 1024 ** 3
# ComfyUI torch 已保留記憶體超過此值 → 視為 checkpoint 仍駐留（載入成本已付）
_COMFYUI_RESIDENT_BYTES = 4 * _GIB

class VRAMGuardian:
    _instance: VRAMGuardian | None = None
    _current_owner: ServiceType | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VRAMGuardian, cls).__new__(cls)
            cls._instance._lock = asyncio.Lock()
        return cls._instance

    @property
    def current_owner(self) -> ServiceType | None:
        return self._current_owner

    async def request_focus(self, tool: ServiceType, exclusive: bool = False) -> bool:
        """
        Request GPU focus for a specific tool.
        Unloads the other tool's models if necessary to free up VRAM.

        2026-07-07 P3：singleton 無鎖時，兩個 async job 同時呼叫會各自讀到
        舊的 _current_owner 並行卸載/轉移 focus，導致另一種 VRAM 爆法。
        用 asyncio.Lock 序列化整個 focus 切換流程（含 VRAM 查詢與卸載）。

        exclusive=True：下一個 job 會載入遠大於現駐留量的模型（如 Flux 2 17GB），
        絕不可與另一方共存。跳過 coexist 短路，一律卸載另一方獨佔顯卡。
        """
        async with self._lock:
            if self._current_owner == tool and not exclusive:
                return True

            # 條件式卸載：VRAM 足夠共存就直接轉移 focus，不卸載另一方
            # exclusive 時強制略過此短路，走下方卸載流程
            if not exclusive and VRAM_COEXIST_ENABLED and await run_in_threadpool(self._can_coexist, tool):
                logger.info(
                    f"VRAM: enough memory — keeping {self._current_owner} loaded, focus → {tool}"
                )
                self._current_owner = tool
                return True

            logger.info(f"VRAM: Switching focus from {self._current_owner} to {tool}")

            try:
                if tool == "comfyui":
                    await self._unload_ollama()
                elif tool == "ollama":
                    await self._unload_comfyui()

                self._current_owner = tool
                return True
            except Exception as e:
                logger.error(f"VRAM: Failed to switch focus to {tool}: {e}")
                return False

    def _comfyui_vram(self) -> tuple[int, int, int]:
        """Return (gpu_free, torch_reserved, gpu_total) in bytes, from ComfyUI /system_stats."""
        stats = requests.get(f"{COMFYUI_BASE}/system_stats", timeout=5).json()
        dev = (stats.get("devices") or [{}])[0]
        return (int(dev.get("vram_free", 0)),
                int(dev.get("torch_vram_total", 0)),
                int(dev.get("vram_total", 0)))

    def _can_coexist(self, tool: ServiceType) -> bool:
        """
        Check live VRAM stats to decide whether `tool` can run without
        evicting the other service.  Conservative: any query failure → False
        (falls back to the legacy unload behaviour).
        """
        try:
            if tool == "comfyui":
                return self._comfyui_can_coexist()
            # tool == "ollama"
            r = requests.get(f"{OLLAMA_BASE}/api/ps", timeout=5).json()
            # 模型仍駐留 Ollama VRAM → 可直接服務
            if any(m.get("size_vram", 0) > 0 for m in r.get("models", [])):
                return True
            gpu_free, _, _ = self._comfyui_vram()
            return gpu_free >= OLLAMA_REQUIRED_VRAM_GB * _GIB
        except Exception as e:
            logger.debug(f"VRAM: coexist check failed ({e}) — falling back to unload")
            return False

    def _comfyui_can_coexist(self) -> bool:
        """ComfyUI 端的共存判定。

        2026-07-27 修正（實測 log 佐證）：舊版寫成

            if torch_reserved >= _COMFYUI_RESIDENT_BYTES: return True
            return gpu_free >= COMFYUI_REQUIRED_VRAM_GB * _GIB

        短路在 gpu_free 檢查「之前」，方向與風險相反 —— **reserved 越高越判定安全**，
        但 reserved 高 + free 低正是最危險的狀態。實測出現 free=0.1G / reserved=16.2G
        仍回報「記憶體足夠」，且第二行的 gpu_free 檢查形同虛設（reserved 幾乎恆 ≥4G）。

        新規則，順序即優先序：
          1. torch_reserved > gpu_total → 已溢出到系統 RAM（Windows WDDM 共享記憶體），
             必然變慢數倍，直接拒絕共存。
          2. gpu_free 足夠跑一次完整載入 → 共存。
          3. checkpoint 已駐留 → 需求降為「增量」（CN/preprocessor/latent/activations），
             但仍要求 gpu_free ≥ COMFYUI_RESIDENT_MIN_FREE_GB。**不再無視 free。**
          4. 其餘 → 不共存，卸載另一方。
        """
        gpu_free, torch_reserved, gpu_total = self._comfyui_vram()
        overcommit = bool(gpu_total) and torch_reserved > gpu_total
        logger.info(
            "VRAM[comfyui] free=%.1fG reserved=%.1fG total=%.1fG "
            "(resident_th=%.0fG req=%.0fG resident_min_free=%.0fG)%s",
            gpu_free / _GIB, torch_reserved / _GIB, gpu_total / _GIB,
            _COMFYUI_RESIDENT_BYTES / _GIB, COMFYUI_REQUIRED_VRAM_GB,
            COMFYUI_RESIDENT_MIN_FREE_GB, "  ⚠️OVERCOMMIT" if overcommit else "",
        )

        if overcommit:
            logger.warning(
                "VRAM: torch 保留 %.1fG 已超過顯卡 %.1fG → 正在使用系統 RAM 溢出，"
                "生成會慢上數倍（實測 40s 的工作變成 >300s timeout）。強制卸載另一方。",
                torch_reserved / _GIB, gpu_total / _GIB,
            )
            return False

        if gpu_free >= COMFYUI_REQUIRED_VRAM_GB * _GIB:
            return True

        if (torch_reserved >= _COMFYUI_RESIDENT_BYTES
                and gpu_free >= COMFYUI_RESIDENT_MIN_FREE_GB * _GIB):
            return True

        logger.info("VRAM: free 不足以共存（free=%.1fG）→ 卸載另一方", gpu_free / _GIB)
        return False

    async def _unload_ollama(self):
        """Unload all models from Ollama to free VRAM (sync HTTP calls off the event loop)."""
        await run_in_threadpool(self._unload_ollama_sync)

    def _unload_ollama_sync(self):
        logger.info("VRAM: Unloading all Ollama models...")
        try:
            r = requests.get(f"{OLLAMA_BASE}/api/ps", timeout=5)
            if r.status_code != 200:
                return
            models = r.json().get("models", [])
            for model in models:
                name = model.get("name", "")
                if name:
                    # keep_alive: 0 tells Ollama to evict this model from VRAM immediately
                    requests.post(
                        f"{OLLAMA_BASE}/api/generate",
                        json={"model": name, "prompt": "", "keep_alive": 0},
                        timeout=10,
                    )
                    logger.info(f"VRAM: Unloaded Ollama model '{name}'")
        except Exception as e:
            logger.warning(f"VRAM: Ollama unload failed: {e}")

    async def _unload_comfyui(self):
        """Request ComfyUI to free its VRAM cache (sync HTTP call off the event loop)."""
        await run_in_threadpool(self._unload_comfyui_sync)

    def _unload_comfyui_sync(self):
        """請 ComfyUI 釋放 VRAM，並回讀驗證是否真的還回來了。

        2026-07-27 修正：舊版只送 ``unload_models``。ComfyUI 的 unload_models 只卸掉
        模型物件，**torch caching allocator 的保留區不會歸還作業系統** → torch_vram_total
        幾乎恆 ≥4G，剛好讓舊的 coexist 短路永遠命中，整條共存檢查等同沒作用。
        必須同時送 ``free_memory``（觸發 soft_empty_cache）才會真的降 reserved。
        """
        try:
            before = self._comfyui_vram()
        except Exception:
            before = None
        logger.info(
            "VRAM: Requesting ComfyUI to free cache...%s",
            "" if before is None else f" (before: free={before[0] / _GIB:.1f}G reserved={before[1] / _GIB:.1f}G)",
        )
        try:
            requests.post(
                f"{comfyui_client.COMFYUI_BASE}/free",
                json={"unload_models": True, "free_memory": True},
                timeout=10,
            )
        except Exception as e:
            logger.warning(f"VRAM: ComfyUI unload failed: {e}")
            return
        # 回讀驗證：不重試（重試也救不了 ComfyUI 端不放），但要讓 log 看得出有沒有生效
        try:
            after = self._comfyui_vram()
            logger.info("VRAM: ComfyUI freed → free=%.1fG reserved=%.1fG",
                        after[0] / _GIB, after[1] / _GIB)
            if before and after[1] >= before[1]:
                logger.warning(
                    "VRAM: /free 後 reserved 未下降（%.1fG → %.1fG）—— ComfyUI 可能正在執行中，"
                    "或該版本不支援 free_memory。",
                    before[1] / _GIB, after[1] / _GIB,
                )
        except Exception:
            pass

# Global singleton
guardian = VRAMGuardian()
