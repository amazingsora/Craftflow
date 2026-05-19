"""
TrainingRunner — Abstract base for LoRA training execution.

Two implementations:
  LocalSubprocessRunner  — subprocess calls kohya_ss directly (backend on Windows host)
  RemoteAgentRunner      — HTTP calls to a host_agent.py (backend in Docker)

Switch via TRAINING_RUNNER_MODE env var: "local" | "remote"
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator


@dataclass
class TrainingProgress:
    step: int
    total_steps: int
    loss: float | None
    message: str


class TrainingRunner(ABC):
    """Abstract training runner. Yields TrainingProgress events."""

    @abstractmethod
    async def start(
        self,
        job_id: int,
        config_path: Path,
        output_dir: Path,
    ) -> AsyncIterator[TrainingProgress]:
        """Start training; yield progress until done or error. Raises on fatal error."""
        ...

    @abstractmethod
    async def stop(self, job_id: int) -> None:
        """Terminate a running training job."""
        ...


def get_runner() -> TrainingRunner:
    """Factory — returns the runner configured by TRAINING_RUNNER_MODE."""
    from app.core.config import TRAINING_RUNNER_MODE

    if TRAINING_RUNNER_MODE == "remote":
        from app.services.ai.lora_trainer.remote_runner import RemoteAgentRunner
        return RemoteAgentRunner()

    from app.services.ai.lora_trainer.local_runner import LocalSubprocessRunner
    return LocalSubprocessRunner()
