"""
Training API — LoRA 訓練圖片管理 + Job CRUD + SSE 進度

端點：
  POST   /training/images/upload          上傳訓練圖片
  GET    /training/images                 列出所有訓練圖片
  PUT    /training/images/{id}/caption    更新 caption
  DELETE /training/images/{id}            刪除圖片

  POST   /training/jobs                   建立訓練 Job
  GET    /training/jobs                   列出所有 Jobs
  GET    /training/jobs/{id}              取得 Job 詳情
  POST   /training/jobs/{id}/start        啟動訓練
  POST   /training/jobs/{id}/stop         停止訓練
  GET    /training/jobs/{id}/progress     SSE 進度串流
  POST   /training/jobs/{id}/caption-all  用 Ollama Vision 批次生成 caption
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import TRAINING_IMAGES_DIR, COMFYUI_LORAS_DIR
from app.core.database import get_db
from app.models.training_image import TrainingImage
from app.models.training_job import TrainingJob
from app.models.art_style import ArtStyle
from app.schemas.training import (
    TrainingImageResponse,
    TrainingImageUpdate,
    TrainingJobCreate,
    TrainingJobResponse,
)
from app.services.ai import ollama_client
from app.services.ai.lora_trainer.config_writer import write_config
from app.services.ai.lora_trainer.runner import get_runner

router = APIRouter(prefix="/training", tags=["training"])
logger = logging.getLogger(__name__)

TRAINING_IMAGES_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/status")
def training_status():
    """回傳 kohya_ss 安裝狀態及訓練環境檢查結果。"""
    from app.core.config import KOHYA_PATH, KOHYA_PYTHON, TRAINING_RUNNER_MODE, COMFYUI_LORAS_DIR
    import shutil
    kohya_script = KOHYA_PATH / "train_network.py"
    python_resolved = shutil.which(str(KOHYA_PYTHON)) or str(KOHYA_PYTHON)
    return {
        "runner_mode": TRAINING_RUNNER_MODE,
        "kohya_path": str(KOHYA_PATH),
        "kohya_found": kohya_script.exists(),
        "kohya_python": python_resolved,
        "comfyui_loras_dir": str(COMFYUI_LORAS_DIR),
        "comfyui_loras_dir_exists": COMFYUI_LORAS_DIR.exists(),
        "training_images_dir": str(TRAINING_IMAGES_DIR),
        "ready": kohya_script.exists(),
    }

# SSE 廣播佇列：job_id → list of queues（每個 SSE 連線一個）
_sse_queues: dict[int, list[asyncio.Queue]] = {}


# ── Images ────────────────────────────────────────────────────────────────────

@router.post("/images/upload", response_model=TrainingImageResponse)
async def upload_training_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Only image files are accepted")

    suffix = Path(file.filename or "img").suffix or ".png"
    dest = TRAINING_IMAGES_DIR / f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}{suffix}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    width, height = None, None
    try:
        with Image.open(dest) as img:
            width, height = img.size
    except Exception:
        pass

    record = TrainingImage(
        filename=file.filename or dest.name,
        filepath=str(dest),
        caption="",
        width=width,
        height=height,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/images", response_model=list[TrainingImageResponse])
def list_training_images(db: Session = Depends(get_db)):
    return db.query(TrainingImage).order_by(TrainingImage.created_at.desc()).all()


@router.put("/images/{image_id}/caption", response_model=TrainingImageResponse)
def update_caption(
    image_id: int,
    body: TrainingImageUpdate,
    db: Session = Depends(get_db),
):
    img = db.get(TrainingImage, image_id)
    if not img:
        raise HTTPException(404, "Image not found")
    img.caption = body.caption
    img.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(img)
    return img


@router.get("/images/{image_id}/file")
def get_image_file(image_id: int, db: Session = Depends(get_db)):
    img = db.get(TrainingImage, image_id)
    if not img or not Path(img.filepath).exists():
        raise HTTPException(404, "Image file not found")
    return FileResponse(img.filepath)


@router.delete("/images/{image_id}", status_code=204)
def delete_training_image(image_id: int, db: Session = Depends(get_db)):
    img = db.get(TrainingImage, image_id)
    if not img:
        raise HTTPException(404, "Image not found")
    try:
        Path(img.filepath).unlink(missing_ok=True)
    except Exception:
        pass
    db.delete(img)
    db.commit()


# ── Caption auto-generation ────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/caption-all")
async def caption_all_images(job_id: int, db: Session = Depends(get_db)):
    """Use Ollama vision to generate captions for all images that have an empty caption."""
    job = db.get(TrainingJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    images = db.query(TrainingImage).filter(TrainingImage.caption == "").all()
    updated = 0
    for img in images:
        try:
            caption = ollama_client.analyze_image(
                image_path=img.filepath,
                prompt=(
                    f"Describe this character illustration for Stable Diffusion training. "
                    f"Start with the trigger word '{job.trigger_word}'. "
                    "List comma-separated Danbooru tags describing: hair color/length, eye color, "
                    "clothing, expression, and pose. Do NOT describe background."
                ),
            )
            img.caption = caption.strip()
            img.updated_at = datetime.utcnow()
            updated += 1
        except Exception as e:
            logger.warning("Caption failed for image %d: %s", img.id, e)

    db.commit()
    return {"updated": updated}


# ── Jobs ──────────────────────────────────────────────────────────────────────

@router.post("/jobs", response_model=TrainingJobResponse, status_code=201)
def create_job(body: TrainingJobCreate, db: Session = Depends(get_db)):
    if body.art_style_id and not db.get(ArtStyle, body.art_style_id):
        raise HTTPException(404, "ArtStyle not found")
    job = TrainingJob(**body.model_dump())
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get("/jobs", response_model=list[TrainingJobResponse])
def list_jobs(db: Session = Depends(get_db)):
    return db.query(TrainingJob).order_by(TrainingJob.created_at.desc()).all()


@router.get("/jobs/{job_id}", response_model=TrainingJobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(TrainingJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/jobs/{job_id}/stop", status_code=204)
async def stop_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(TrainingJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status != "running":
        raise HTTPException(400, f"Job is not running (status: {job.status})")
    await get_runner().stop(job_id)
    job.status = "stopped"
    job.finished_at = datetime.utcnow()
    job.updated_at = datetime.utcnow()
    db.commit()


@router.post("/jobs/{job_id}/start", status_code=202)
async def start_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(TrainingJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status == "running":
        raise HTTPException(400, "Job is already running")

    images = db.query(TrainingImage).all()
    if not images:
        raise HTTPException(400, "No training images uploaded")

    # Write caption .txt files alongside images
    dataset_dir = TRAINING_IMAGES_DIR
    for img in images:
        txt_path = Path(img.filepath).with_suffix(".txt")
        txt_path.write_text(img.caption or job.trigger_word, encoding="utf-8")

    output_dir = TRAINING_IMAGES_DIR.parent / "lora_output" / f"job_{job_id}"
    config_path = write_config(
        dataset_dir=dataset_dir,
        output_dir=output_dir,
        output_name=job.trigger_word,
        base_checkpoint=job.base_checkpoint,
        trigger_word=job.trigger_word,
        lora_rank=job.lora_rank,
        learning_rate=job.learning_rate,
        epochs=job.epochs,
        resolution=job.resolution,
    )

    job.status = "running"
    job.started_at = datetime.utcnow()
    job.updated_at = datetime.utcnow()
    db.commit()

    asyncio.create_task(_run_training(job_id, config_path, output_dir))
    return {"detail": "Training started", "job_id": job_id}


@router.get("/jobs/{job_id}/progress")
async def job_progress_sse(job_id: int):
    """SSE stream — yields progress events until training finishes."""
    queue: asyncio.Queue = asyncio.Queue()
    _sse_queues.setdefault(job_id, []).append(queue)

    async def event_stream():
        try:
            while True:
                data = await asyncio.wait_for(queue.get(), timeout=30)
                if data is None:
                    break
                yield f"data: {json.dumps(data)}\n\n"
        except asyncio.TimeoutError:
            yield "data: {\"heartbeat\": true}\n\n"
        finally:
            queues = _sse_queues.get(job_id, [])
            if queue in queues:
                queues.remove(queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Background training task ──────────────────────────────────────────────────

async def _run_training(job_id: int, config_path: Path, output_dir: Path):
    from app.core.database import engine
    from sqlalchemy.orm import Session as _Session

    runner = get_runner()
    LOG_TAIL_MAX = 20
    log_lines: list[str] = []

    try:
        async for progress in runner.start(job_id, config_path, output_dir):
            if progress.message == "__DONE__":
                break

            log_lines.append(progress.message)
            if len(log_lines) > LOG_TAIL_MAX:
                log_lines.pop(0)

            event = {
                "step": progress.step,
                "total_steps": progress.total_steps,
                "loss": progress.loss,
                "message": progress.message,
            }
            for q in list(_sse_queues.get(job_id, [])):
                await q.put(event)

            # Persist progress snapshot every 10 steps
            if progress.step and progress.step % 10 == 0:
                with _Session(engine) as db:
                    job = db.get(TrainingJob, job_id)
                    if job:
                        job.current_step = progress.step
                        job.total_steps = progress.total_steps
                        job.last_loss = progress.loss
                        job.log_tail = "\n".join(log_lines)
                        job.updated_at = datetime.utcnow()
                        db.commit()

        # Training finished — copy LoRA to ComfyUI
        with _Session(engine) as db:
            job = db.get(TrainingJob, job_id)
            if job:
                lora_files = list(output_dir.glob("*.safetensors"))
                if lora_files:
                    lora_src = max(lora_files, key=lambda p: p.stat().st_mtime)
                    lora_dest = COMFYUI_LORAS_DIR / lora_src.name
                    try:
                        COMFYUI_LORAS_DIR.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(lora_src, lora_dest)
                        job.output_lora_name = lora_src.name
                        logger.info("LoRA copied to %s", lora_dest)
                    except Exception as e:
                        logger.error("Failed to copy LoRA: %s", e)

                    # Auto-attach to art_style if bound
                    if job.art_style_id and job.output_lora_name:
                        art_style = db.get(ArtStyle, job.art_style_id)
                        if art_style:
                            import json as _json
                            loras = _json.loads(art_style.loras or "[]")
                            if not any(l.get("model") == job.output_lora_name for l in loras):
                                loras.append({"model": job.output_lora_name, "weight": 0.8})
                                art_style.loras = _json.dumps(loras)

                job.status = "done"
                job.finished_at = datetime.utcnow()
                job.current_step = job.total_steps
                job.log_tail = "\n".join(log_lines)
                job.updated_at = datetime.utcnow()
                db.commit()

        _broadcast_done(job_id)

    except Exception as e:
        logger.error("Training job %d failed: %s", job_id, e)
        with _Session(engine) as db:
            job = db.get(TrainingJob, job_id)
            if job:
                job.status = "failed"
                job.finished_at = datetime.utcnow()
                job.log_tail = str(e)
                job.updated_at = datetime.utcnow()
                db.commit()
        _broadcast_done(job_id)


def _broadcast_done(job_id: int):
    for q in list(_sse_queues.get(job_id, [])):
        q.put_nowait(None)
    _sse_queues.pop(job_id, None)
