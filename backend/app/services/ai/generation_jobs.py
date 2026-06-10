"""
生圖非同步 Job（P4 + P5 批次）。

In-memory job store（單人本地工具，結果為短生命週期 bytes，不落 DB）。
與 LoRA training 的「建 job → 查狀態 → 取結果」模式一致。
完成的 job 保留 _TTL_SECONDS 供取圖，逾時或超量自動淘汰。
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_JOBS = 30
_TTL_SECONDS = 30 * 60
_COMFYUI_JOB_TIMEOUT = 600  # 批次/高解析度比單張久，放寬到 10 分鐘


@dataclass
class GenJob:
    id: str
    status: str = "queued"          # queued | running | done | error
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    images: list[bytes] = field(default_factory=list)
    error: Optional[str] = None
    meta: dict = field(default_factory=dict)  # seed / style / workflow / batch_size / history_id


_JOBS: dict[str, GenJob] = {}


def create_job(meta: dict) -> GenJob:
    _prune()
    job = GenJob(id=uuid.uuid4().hex, meta=meta)
    _JOBS[job.id] = job
    return job


def get_job(job_id: str) -> Optional[GenJob]:
    return _JOBS.get(job_id)


def _prune() -> None:
    now = time.time()
    expired = [
        jid for jid, j in _JOBS.items()
        if j.status in ("done", "error") and j.finished_at and now - j.finished_at > _TTL_SECONDS
    ]
    for jid in expired:
        del _JOBS[jid]
    # 超量時淘汰最舊的已完成 job
    while len(_JOBS) >= _MAX_JOBS:
        finished = sorted(
            (j for j in _JOBS.values() if j.status in ("done", "error")),
            key=lambda j: j.created_at,
        )
        if not finished:
            break
        del _JOBS[finished[0].id]


async def run_txt2img_job(job: GenJob, wf: dict, record_kwargs: dict) -> None:
    """背景執行 ComfyUI 生成；錯誤一律收進 job.error，不外拋。"""
    from app.services import comfyui_client
    from app.services.ai.vram_manager import guardian

    job.status = "running"
    try:
        if not await asyncio.to_thread(comfyui_client.is_available):
            raise RuntimeError("ComfyUI 未啟動，請先執行 ComfyUI (host.docker.internal:8188)。")
        await guardian.request_focus("comfyui")
        prompt_id = await asyncio.to_thread(comfyui_client.submit_workflow, wf)
        filenames = await asyncio.to_thread(
            comfyui_client.wait_for_result, prompt_id, _COMFYUI_JOB_TIMEOUT
        )
        if not filenames:
            raise RuntimeError("ComfyUI 未回傳輸出圖片，請確認 workflow 設定。")
        job.images = [
            await asyncio.to_thread(comfyui_client.download_image, f) for f in filenames
        ]

        # 記錄 generation_history（背景 task 用獨立 session）
        try:
            from sqlalchemy.orm import Session
            from app.core.database import engine
            from app.services.ai.generation_recorder import record_generation
            with Session(engine) as s:
                job.meta["history_id"] = record_generation(s, **record_kwargs)
        except Exception as e:
            logger.warning("[gen-job] history 記錄失敗（不影響結果）：%s", e)

        job.status = "done"
        logger.info("[gen-job] %s done — %d image(s)", job.id, len(job.images))
    except Exception as e:
        job.status = "error"
        job.error = str(e)
        logger.error("[gen-job] %s failed: %s", job.id, e)
    finally:
        job.finished_at = time.time()
