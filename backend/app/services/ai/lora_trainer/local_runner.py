"""
LocalSubprocessRunner — calls kohya_ss train_network.py via subprocess.
Used when the backend runs directly on the Windows host.
"""
from __future__ import annotations

import asyncio
import logging
import re
import sys
from pathlib import Path
from typing import AsyncIterator

from app.core.config import KOHYA_PATH, KOHYA_PYTHON
from app.services.ai.lora_trainer.runner import TrainingProgress, TrainingRunner

logger = logging.getLogger(__name__)

# Active processes keyed by job_id
_active: dict[int, asyncio.subprocess.Process] = {}

# Regex to parse kohya_ss progress lines like:
#   steps:  50%|█████     | 100/200 [01:23<01:23, 2.00it/s, avr_loss=0.1234]
_PROGRESS_RE = re.compile(
    r"steps:\s+\d+%.*?(\d+)/(\d+).*?avr_loss=([\d.]+)",
    re.IGNORECASE,
)


class LocalSubprocessRunner(TrainingRunner):

    async def start(
        self,
        job_id: int,
        config_path: Path,
        output_dir: Path,
    ) -> AsyncIterator[TrainingProgress]:
        train_script = KOHYA_PATH / "train_network.py"
        python_exe   = KOHYA_PYTHON

        if not train_script.exists():
            raise FileNotFoundError(
                f"kohya_ss not found at {KOHYA_PATH}. "
                "Please install it and set KOHYA_PATH in .env"
            )

        cmd = [
            str(python_exe),
            str(train_script),
            f"--config_file={config_path}",
        ]

        logger.info("Starting training job %d: %s", job_id, " ".join(cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(KOHYA_PATH),
        )
        _active[job_id] = proc

        try:
            async for line in _read_lines(proc):
                progress = _parse_line(line)
                if progress is not None:
                    yield progress
                else:
                    yield TrainingProgress(step=0, total_steps=0, loss=None, message=line.rstrip())

            await proc.wait()
            if proc.returncode != 0:
                raise RuntimeError(f"kohya_ss exited with code {proc.returncode}")

            yield TrainingProgress(step=0, total_steps=0, loss=None, message="__DONE__")
        finally:
            _active.pop(job_id, None)

    async def stop(self, job_id: int) -> None:
        proc = _active.get(job_id)
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
            except asyncio.TimeoutError:
                proc.kill()
            _active.pop(job_id, None)
            logger.info("Training job %d stopped", job_id)


async def _read_lines(proc: asyncio.subprocess.Process) -> AsyncIterator[str]:
    assert proc.stdout
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        yield line.decode(sys.stdout.encoding or "utf-8", errors="replace")


def _parse_line(line: str) -> TrainingProgress | None:
    m = _PROGRESS_RE.search(line)
    if not m:
        return None
    step, total, loss = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return TrainingProgress(step=step, total_steps=total, loss=loss, message=line.rstrip())
