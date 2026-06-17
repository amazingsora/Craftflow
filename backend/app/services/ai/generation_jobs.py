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
    progress: dict = field(default_factory=lambda: {"pct": 0, "value": 0, "max": 0, "node": None, "status": "queued"})


_JOBS: dict[str, GenJob] = {}

_progress_queues: dict[str, list] = {}


def subscribe_progress(job_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _progress_queues.setdefault(job_id, []).append(q)
    return q


def unsubscribe_progress(job_id: str, q) -> None:
    qs = _progress_queues.get(job_id, [])
    if q in qs:
        qs.remove(q)


def _push_progress(job_id: str, event) -> None:
    for q in list(_progress_queues.get(job_id, [])):
        try:
            q.put_nowait(event)
        except Exception:
            pass


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
    job.progress["status"] = "running"
    prog_task = None
    try:
        if not await asyncio.to_thread(comfyui_client.is_available):
            raise RuntimeError("ComfyUI 未啟動，請先執行 ComfyUI (host.docker.internal:8188)。")
        await guardian.request_focus("comfyui")
        import uuid as _uuid
        from app.services.ai import comfyui_progress
        client_id = _uuid.uuid4().hex
        prompt_id = await asyncio.to_thread(comfyui_client.submit_workflow, wf, client_id)

        def _on_event(ev):
            # 只推 progress / node；ws 的 done/error 不推（完成以 job finally 終結事件為準，避免混淆）
            et = ev.get("type")
            if et == "progress":
                job.progress.update(value=ev["value"], max=ev["max"], pct=ev["pct"], status="running")
                _push_progress(job.id, {**job.progress, "event": "progress"})
            elif et == "node":
                job.progress["node"] = ev["node"]
                _push_progress(job.id, {**job.progress, "event": "node"})

        # ws 進度為 best-effort 疊加；完成/輸出仍以 wait_for_result 為準
        prog_task = asyncio.create_task(
            comfyui_progress.stream_progress(client_id, prompt_id, _on_event, timeout=_COMFYUI_JOB_TIMEOUT)
        )
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
        job.progress.update(pct=100, status="done")
        logger.info("[gen-job] %s done — %d image(s)", job.id, len(job.images))
    except Exception as e:
        job.status = "error"
        job.progress["status"] = "error"
        job.error = str(e)
        logger.error("[gen-job] %s failed: %s", job.id, e)
    finally:
        if prog_task is not None:
            prog_task.cancel()
        job.finished_at = time.time()
        _push_progress(job.id, {**job.progress, "event": job.status})
        _push_progress(job.id, None)  # 哨兵：通知 SSE 結束
