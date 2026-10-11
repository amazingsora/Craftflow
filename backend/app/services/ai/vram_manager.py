"""VRAM Guardian — Dynamic GPU memory management for RTX 5000/4000 series [FD-092]"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Literal

from starlette.concurrency import run_in_threadpool

from app.core.config import (
    OLLAMA_BASE,
    COMFYUI_BASE,
    VRAM_COEXIST_ENABLED,
    COMFYUI_REQUIRED_VRAM_GB,
    COMFYUI_RESIDENT_MIN_FREE_GB,
    OLLAMA_REQUIRED_VRAM_GB,
    VRAM_FREE_WAIT_SEC,
    VRAM_FREE_POLL_SEC,
    VRAM_STRICT_FREE,
    VRAM_FREE_MIN_DROP_GB,
    VRAM_STUCK_RATIO,
)
from app.services import comfyui_client
from app.services.http_local import SESSION

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
        """取得 GPU focus，必要時卸載另一方的模型；以 asyncio.Lock 序列化切換流程。
        exclusive=True：即將載入超大模型，跳過共存判定、一律卸載另一方。"""
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
                    # 等 ComfyUI 真的讓出顯存，才載入 Ollama 模型
                    if not await self._unload_comfyui() and VRAM_STRICT_FREE:
                        logger.error(
                            "VRAM: ComfyUI 未讓出顯存且 VRAM_STRICT_FREE=true "
                            "→ 不轉移 focus 到 ollama（避免把 ComfyUI 權重擠進共享記憶體）"
                        )
                        return False

                self._current_owner = tool
                return True
            except Exception as e:
                logger.error(f"VRAM: Failed to switch focus to {tool}: {e}")
                return False

    def _comfyui_vram(self) -> tuple[int, int, int]:
        """Return (gpu_free, torch_reserved, gpu_total) in bytes, from ComfyUI /system_stats."""
        stats = SESSION.get(f"{COMFYUI_BASE}/system_stats", timeout=5).json()
        dev = (stats.get("devices") or [{}])[0]
        return (int(dev.get("vram_free", 0)),
                int(dev.get("torch_vram_total", 0)),
                int(dev.get("vram_total", 0)))

    def _can_coexist(self, tool: ServiceType) -> bool:
        """依即時 VRAM 判斷 tool 能否與另一方共存 [FD-093]"""
        try:
            if tool == "comfyui":
                return self._comfyui_can_coexist()
            # tool == "ollama"
            r = SESSION.get(f"{OLLAMA_BASE}/api/ps", timeout=5).json()
            # 模型仍駐留 Ollama VRAM → 可直接服務
            if any(m.get("size_vram", 0) > 0 for m in r.get("models", [])):
                return True
            gpu_free, _, _ = self._comfyui_vram()
            return gpu_free >= OLLAMA_REQUIRED_VRAM_GB * _GIB
        except Exception as e:
            logger.debug(f"VRAM: coexist check failed ({e}) — falling back to unload")
            return False

    def _comfyui_can_coexist(self) -> bool:
        """ComfyUI 端共存判定，依序 [FD-094]"""
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
            r = SESSION.get(f"{OLLAMA_BASE}/api/ps", timeout=5)
            if r.status_code != 200:
                return
            models = r.json().get("models", [])
            for model in models:
                name = model.get("name", "")
                if name:
                    # keep_alive: 0 tells Ollama to evict this model from VRAM immediately
                    SESSION.post(
                        f"{OLLAMA_BASE}/api/generate",
                        json={"model": name, "prompt": "", "keep_alive": 0},
                        timeout=10,
                    )
                    logger.info(f"VRAM: Unloaded Ollama model '{name}'")
        except Exception as e:
            logger.warning(f"VRAM: Ollama unload failed: {e}")

    async def _unload_comfyui(self) -> bool:
        """Request ComfyUI to free its VRAM cache (sync HTTP call off the event loop)."""
        return await run_in_threadpool(self._unload_comfyui_sync)

    def _unload_comfyui_sync(self) -> bool:
        """請 ComfyUI 釋放 VRAM（unload_models＋free_memory），輪詢到 reserved 真的下降才返回。
        /free 是非同步排程，送出後立即回讀量到的是舊值，故需等待。
        回傳 False＝逾時仍未下降（見 VRAM_STRICT_FREE）。"""
        try:
            before = self._comfyui_vram()
        except Exception:
            before = None
        logger.info(
            "VRAM: Requesting ComfyUI to free cache...%s",
            "" if before is None else f" (before: free={before[0] / _GIB:.1f}G reserved={before[1] / _GIB:.1f}G)",
        )
        try:
            SESSION.post(
                f"{comfyui_client.COMFYUI_BASE}/free",
                json={"unload_models": True, "free_memory": True},
                timeout=10,
            )
        except Exception as e:
            logger.warning(f"VRAM: ComfyUI unload failed: {e}")
            return False

        if before is None:
            # 量不到基準就無從驗證，維持舊行為（樂觀放行），不要因為診斷不到而擋住功能
            return True

        started = time.monotonic()
        deadline = started + VRAM_FREE_WAIT_SEC
        after = before
        while True:
            time.sleep(VRAM_FREE_POLL_SEC)
            try:
                after = self._comfyui_vram()
            except Exception:
                break
            # 要求最低歸還量，小幅下降視為量測雜訊
            if (before[1] - after[1]) >= VRAM_FREE_MIN_DROP_GB * _GIB:
                logger.info(
                    "VRAM: ComfyUI freed → free=%.1fG reserved=%.1fG（%.1fG 已歸還，等待 %.2fs）",
                    after[0] / _GIB, after[1] / _GIB,
                    (before[1] - after[1]) / _GIB, time.monotonic() - started,
                )
                return True
            if time.monotonic() >= deadline:
                break

        logger.error(
            "VRAM: /free 等待 %.1fs 後 reserved 仍未下降（%.1fG → %.1fG，free=%.1fG）—— "
            "ComfyUI 沒有讓出顯存。此時載入 Ollama 會把 ComfyUI 的權重頁擠進共享系統"
            "記憶體，下一輪生圖會慢上數十倍（2026-09-20 實測 2.64 it/s → 12.69 s/it）。%s",
            time.monotonic() - started, before[1] / _GIB, after[1] / _GIB, after[0] / _GIB,
            "VRAM_STRICT_FREE=true → 拒絕轉移 focus。" if VRAM_STRICT_FREE
            else "VRAM_STRICT_FREE=false → 仍放行（維持現行行為）。",
        )
        self._warn_if_stuck(after)
        return False

    @staticmethod
    def _warn_if_stuck(stats: tuple[int, int, int]) -> None:
        """reserved 逼近卡容量＝權重已換出到共享記憶體，不會自行恢復，只能重啟 ComfyUI。"""
        gpu_free, reserved, total = stats
        if not total or reserved < VRAM_STUCK_RATIO * total:
            return
        logger.error(
            "VRAM: ComfyUI 已佔用 %.1fG / %.1fG（%.0f%%），free=%.1fG —— 顯卡實質塞滿，"
            "極可能已在使用共享系統記憶體。此狀態不會自行恢復（換出的頁不會搬回 VRAM），"
            "接下來每一張都會慢數倍。**請重啟 ComfyUI**（重啟後 reserved 應歸零；"
            "若重啟後仍很快回到 15G 以上，代表啟動旗標還是 --highvram，沒吃到 --normalvram）。",
            reserved / _GIB, total / _GIB, 100.0 * reserved / total, gpu_free / _GIB,
        )

# Global singleton
guardian = VRAMGuardian()
