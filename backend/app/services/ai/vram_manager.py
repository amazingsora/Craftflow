"""
VRAM Guardian — Dynamic GPU memory management for RTX 5000/4000 series.
Coordinates memory usage between Ollama (LLM) and ComfyUI (Diffusion).
"""
from __future__ import annotations

import logging
import requests
from typing import Literal

from app.core.config import (
    OLLAMA_BASE,
    COMFYUI_BASE,
    VRAM_COEXIST_ENABLED,
    COMFYUI_REQUIRED_VRAM_GB,
    OLLAMA_REQUIRED_VRAM_GB,
)
from app.services import comfyui_client

logger = logging.getLogger(__name__)

ServiceType = Literal["ollama", "comfyui"]

_GIB = 1024 ** 3
# ComfyUI torch 已保留記憶體超過此值 → 視為 checkpoint 仍駐留，無需騰出空間
_COMFYUI_RESIDENT_BYTES = 4 * _GIB

class VRAMGuardian:
    _instance: VRAMGuardian | None = None
    _current_owner: ServiceType | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VRAMGuardian, cls).__new__(cls)
        return cls._instance

    @property
    def current_owner(self) -> ServiceType | None:
        return self._current_owner

    async def request_focus(self, tool: ServiceType) -> bool:
        """
        Request GPU focus for a specific tool. 
        Unloads the other tool's models if necessary to free up VRAM.
        """
        if self._current_owner == tool:
            return True

        # 條件式卸載：VRAM 足夠共存就直接轉移 focus，不卸載另一方
        if VRAM_COEXIST_ENABLED and self._can_coexist(tool):
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

    def _comfyui_vram(self) -> tuple[int, int]:
        """Return (gpu_free_bytes, torch_reserved_bytes) from ComfyUI /system_stats."""
        stats = requests.get(f"{COMFYUI_BASE}/system_stats", timeout=5).json()
        dev = (stats.get("devices") or [{}])[0]
        return int(dev.get("vram_free", 0)), int(dev.get("torch_vram_total", 0))

    def _can_coexist(self, tool: ServiceType) -> bool:
        """
        Check live VRAM stats to decide whether `tool` can run without
        evicting the other service.  Conservative: any query failure → False
        (falls back to the legacy unload behaviour).
        """
        try:
            if tool == "comfyui":
                gpu_free, torch_reserved = self._comfyui_vram()
                # checkpoint 仍駐留 ComfyUI → 不需額外空間
                if torch_reserved >= _COMFYUI_RESIDENT_BYTES:
                    return True
                return gpu_free >= COMFYUI_REQUIRED_VRAM_GB * _GIB
            # tool == "ollama"
            r = requests.get(f"{OLLAMA_BASE}/api/ps", timeout=5).json()
            # 模型仍駐留 Ollama VRAM → 可直接服務
            if any(m.get("size_vram", 0) > 0 for m in r.get("models", [])):
                return True
            gpu_free, _ = self._comfyui_vram()
            return gpu_free >= OLLAMA_REQUIRED_VRAM_GB * _GIB
        except Exception as e:
            logger.debug(f"VRAM: coexist check failed ({e}) — falling back to unload")
            return False

    async def _unload_ollama(self):
        """Unload all models from Ollama to free VRAM."""
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
        """Request ComfyUI to free its VRAM cache."""
        logger.info("VRAM: Requesting ComfyUI to free cache...")
        try:
            # ComfyUI /free endpoint can trigger garbage collection and model unloading
            requests.post(f"{comfyui_client.COMFYUI_BASE}/free", json={"unload_models": True}, timeout=5)
        except Exception as e:
            logger.warning(f"VRAM: ComfyUI unload failed: {e}")

# Global singleton
guardian = VRAMGuardian()
