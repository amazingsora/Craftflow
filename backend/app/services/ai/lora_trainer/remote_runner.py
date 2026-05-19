"""
RemoteAgentRunner — delegates training to a small HTTP agent on the Windows host.
Used when the backend runs inside Docker (host.docker.internal).

The agent endpoint (host_agent.py, not yet implemented) must:
  POST /train  { config_path, output_dir, job_id }
  GET  /progress/{job_id}  → SSE stream of TrainingProgress JSON
  POST /stop/{job_id}
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import AsyncIterator

import requests

from app.services.ai.lora_trainer.runner import TrainingProgress, TrainingRunner

logger = logging.getLogger(__name__)

AGENT_BASE = "http://host.docker.internal:7788"


class RemoteAgentRunner(TrainingRunner):

    async def start(
        self,
        job_id: int,
        config_path: Path,
        output_dir: Path,
    ) -> AsyncIterator[TrainingProgress]:
        resp = requests.post(
            f"{AGENT_BASE}/train",
            json={
                "job_id": job_id,
                "config_path": str(config_path),
                "output_dir": str(output_dir),
            },
            timeout=10,
        )
        resp.raise_for_status()

        # SSE stream
        with requests.get(
            f"{AGENT_BASE}/progress/{job_id}",
            stream=True,
            timeout=None,
        ) as stream:
            for raw in stream.iter_lines():
                if not raw or not raw.startswith(b"data:"):
                    continue
                data = json.loads(raw[5:])
                yield TrainingProgress(**data)

    async def stop(self, job_id: int) -> None:
        try:
            requests.post(f"{AGENT_BASE}/stop/{job_id}", timeout=5)
        except Exception as e:
            logger.warning("Failed to stop remote job %d: %s", job_id, e)
