"""
VRAM Guardian — Dynamic GPU memory management for RTX 5000/4000 series.
Coordinates memory usage between Ollama (LLM) and ComfyUI (Diffusion).
"""
from __future__ import annotations

import logging
import requests
from typing import Literal

from app.core.config import OLLAMA_BASE
from app.services import comfyui_client

logger = logging.getLogger(__name__)

ServiceType = Literal["ollama", "comfyui"]

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
