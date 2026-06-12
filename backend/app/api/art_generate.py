"""
ComfyUI image generation endpoints:
  POST /api/v1/art/compile-prompt  — 中文 → model-aware prompt (自動偵測 checkpoint style)
  POST /api/v1/art/lineart         — upload sketch → lineart PNG (ControlNet)
  POST /api/v1/art/generate        — text prompt → image PNG (SDXL txt2img)
  POST /api/v1/art/compose         — sketch + question → advice text + reference image (JSON)
  POST /api/v1/art/img-guide       — reference image + prompt → image (i2i / controlnet modes)
"""
from __future__ import annotations

import asyncio
import base64
import colorsys
import io
import json
import logging
import random
import time
from typing import Annotated, Optional

from PIL import Image, ImageDraw

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import (
    UPLOAD_DIR, CUSTOM_WORKFLOWS_DIR,
    PERSONAL_STYLE_ENABLED, PERSONAL_STYLE_EXTRA_TAGS,
    PERSONAL_NEGATIVE_ENABLED, PERSONAL_NEGATIVE,
)
from app.core import state
from app.core.database import get_db
from app.models.art_style import ArtStyle
from app.models.character import Character
from app.services import comfyui_client
from app.services.ai import art_service, ollama_client as _oc
from app.services.ai.prompt_engine import compile as compile_prompt, PromptStyle
from app.services.ai.prompt_engine.styles import STYLE_CONFIG
from app.services.ai.vram_manager import guardian
from app.services.ai.generation_recorder import record_generation
from app.services.ai import generation_jobs
from app.services.ai import image_edit_service
from app.services.ai.workflow_builder import (
    _compile_overrides,
    _detect_style,
    _extra_tags,
    _inject_loras,
    _load_workflow,
    _log_wf_snapshot,
    _replace_negative_seeds,
    _resolve_style,
    _run_comfyui,
)
from app.services.ai.image_ops import (
    _BODY_FILL_RATIO,
    _BODY_TOP_OFFSET,
    _FULLBODY_HEIGHT,
    _FULLBODY_NEG_TAGS,
    _FULLBODY_POS_TAGS,
    _FULLBODY_WIDTH,
    _border_color,
    _clamp_dim,
    _fullbody_canvas,
    _image_dimensions,
    _is_flat_color_draft,
    _letterbox_to_aspect,
    _pixel_coverage_check,
    _shrink_for_full_body,
)
from app.services.ai.wf_node_ops import (
    _CN_APPLY_TYPES,
    _CN_END_PERCENT,
    _bypass_controlnet_nodes,
    _bypass_ipa_nodes,
    _inject_controlnet_compose,
    _inject_controlnet_image,
    _inject_ipa_cn_nodes,
    _inject_ipa_image,
    _inject_prompts,
    _wf_has_controlnet,
    _wf_has_ipa,
)
from app.services.ai.vision_extract import (
    _age_body_tags,
    _age_gender_tag,
    _filter_visual_for_llm,
    _height_body_tags,
    _vision_extract_cached,
)

_PORTRAIT_DIR = UPLOAD_DIR / "portraits"

logger = logging.getLogger(__name__)

router = APIRouter(tags=["art-generate"])

# ── endpoints ─────────────────────────────────────────────────────────────────

class CompilePromptRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    art_style_id: Optional[int] = None


@router.post("/art/compile-prompt", summary="AI 編譯提示詞 (中文 → 模型對應格式)")
async def compile_prompt_endpoint(req: CompilePromptRequest, db: Session = Depends(get_db)):
    """
    Detect current checkpoint style from text_to_image.json,
    then compile Chinese description into the correct prompt format.

    Returns:
      positive  — compiled positive prompt (ready for ComfyUI)
      negative  — model-appropriate negative prompt
      style     — detected style (sdxl / pony / flux / ...)
    """
    art_style = db.get(ArtStyle, req.art_style_id) if req.art_style_id else None
    style = _resolve_style(art_style)
    await guardian.request_focus("ollama")
    try:
        positive, negative = compile_prompt(req.prompt, style=style, model=req.model or state.get_text_model(), **_compile_overrides(art_style))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"Ollama 文字模型失敗：{e}")
    extra = _extra_tags(art_style)
    if extra:
        positive = f"{positive}, {extra}"
    return {
        "positive": positive,
        "negative": negative,
        "style": style.value,
        "art_style_id": req.art_style_id,
    }


# Keep old endpoint as alias for backward compatibility
@router.post("/art/optimize-prompt", summary="[deprecated] 請改用 /art/compile-prompt")
async def optimize_prompt_compat(req: CompilePromptRequest):
    return await compile_prompt_endpoint(req)


@router.post("/art/lineart", summary="草稿→線稿 (ComfyUI ControlNet)")
async def lineart(file: Annotated[UploadFile, File(description="草稿圖片 (JPEG/PNG)")]):
    image_bytes = await file.read()
    wf = _load_workflow("sketch_to_lineart.json")

    uploaded_name = comfyui_client.upload_image_bytes(
        image_bytes, file.filename or "sketch.png"
    )
    for node in wf.values():
        if isinstance(node, dict) and node.get("class_type") == "LoadImage":
            node["inputs"]["image"] = uploaded_name

    await guardian.request_focus("comfyui")
    return Response(content=await _run_comfyui(wf), media_type="image/png")


class GenerateRequest(BaseModel):
    prompt: str
    negative_prompt: str = ""   # 若為空，由偵測到的 style 或 art_style 自動填入
    width: int = 1024
    height: int = 1024
    steps: int = 20
    seed: int = -1
    art_style_id: Optional[int] = None


def _build_txt2img(req: "GenerateRequest", db: Session, batch_size: int = 1):
    """txt2img workflow 組裝（sync /art/generate 與 async job 共用）。

    回傳 (wf, seed, style, prompt, negative, lora_list)。
    """
    art_style = db.get(ArtStyle, req.art_style_id) if req.art_style_id else None
    style = _resolve_style(art_style)
    default_neg = (art_style.negative or STYLE_CONFIG[style].negative) if art_style else STYLE_CONFIG[style].negative
    negative = req.negative_prompt or default_neg
    seed = req.seed if req.seed >= 0 else random.randint(0, 2**31 - 1)
    prompt = req.prompt
    extra = _extra_tags(art_style)
    if extra:
        prompt = f"{prompt}, {extra}"

    wf = _load_workflow(state.get_workflow())
    # global LoRA（settings 頁設定）優先注入，art_style LoRA 疊加在後
    global_lora = state.get_lora()
    lora_list = []
    if global_lora.get("name"):
        lora_list.append({"model": global_lora["name"], "weight": global_lora["strength"]})
    if art_style and art_style.loras:
        lora_list.extend(art_style.loras)
    _inject_loras(wf, lora_list)
    _inject_prompts(wf, prompt, negative)
    for node in wf.values():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        inputs = node.get("inputs", {})
        if ct == "EmptyLatentImage":
            inputs["width"] = req.width
            inputs["height"] = req.height
            if batch_size > 1:
                inputs["batch_size"] = batch_size
        elif ct == "KSampler":
            inputs["seed"] = seed
            inputs["steps"] = req.steps

    _replace_negative_seeds(wf, seed)
    return wf, seed, style, prompt, negative, lora_list


@router.post("/art/generate", summary="文字→圖片 (SDXL txt2img)")
async def generate(req: GenerateRequest, db: Session = Depends(get_db)):
    """
    Generate an illustration from a text prompt via ComfyUI.
    If negative_prompt is empty, uses the model-appropriate preset (or art_style override).
    """
    wf, seed, style, prompt, negative, lora_list = _build_txt2img(req, db)
    await guardian.request_focus("comfyui")
    image_bytes = await _run_comfyui(wf)
    hist_id = record_generation(
        db,
        endpoint="generate",
        seed=seed,
        workflow=state.get_workflow(),
        style=style.value,
        positive=prompt,
        negative=negative,
        params={
            "width": req.width, "height": req.height, "steps": req.steps,
            "loras": lora_list, "art_style_id": req.art_style_id,
        },
    )
    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={
            "X-Seed": str(seed),
            "X-Style": style.value,
            "X-Steps": str(req.steps),
            "X-Workflow": state.get_workflow(),
            "X-History-Id": str(hist_id) if hist_id else "",
        },
    )


class GenerateAsyncRequest(GenerateRequest):
    batch_size: int = 1  # 1~8，>1 時同 seed 批次出多張（挑圖用）


@router.post("/art/generate-async", summary="文字→圖片（非同步 job + 批次）")
async def generate_async(req: GenerateAsyncRequest, db: Session = Depends(get_db)):
    """
    立即回傳 job_id，背景執行生成（避免 two-pass / 高解析度 / 批次撞 HTTP 逾時）。
    輪詢 GET /art/jobs/{job_id}，完成後 GET /art/jobs/{job_id}/result?index=N 取圖。
    """
    batch_size = max(1, min(8, req.batch_size))
    wf, seed, style, prompt, negative, lora_list = _build_txt2img(req, db, batch_size=batch_size)
    job = generation_jobs.create_job(meta={
        "seed": seed,
        "style": style.value,
        "workflow": state.get_workflow(),
        "batch_size": batch_size,
    })
    record_kwargs = dict(
        endpoint="generate",
        seed=seed,
        workflow=state.get_workflow(),
        style=style.value,
        positive=prompt,
        negative=negative,
        params={
            "width": req.width, "height": req.height, "steps": req.steps,
            "loras": lora_list, "art_style_id": req.art_style_id,
            "batch_size": batch_size, "async": True,
        },
    )
    asyncio.create_task(generation_jobs.run_txt2img_job(job, wf, record_kwargs))
    return {"job_id": job.id, "status": job.status, "seed": seed, "batch_size": batch_size}


@router.get("/art/jobs/{job_id}", summary="生圖 job 狀態")
def get_generation_job(job_id: str):
    job = generation_jobs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found（可能已逾時淘汰）")
    return {
        "job_id": job.id,
        "status": job.status,
        "error": job.error,
        "image_count": len(job.images),
        "elapsed": round(time.time() - job.created_at, 1),
        **job.meta,
    }


@router.get("/art/jobs/{job_id}/result", summary="取生圖 job 結果（PNG）")
def get_generation_job_result(job_id: str, index: int = 0):
    job = generation_jobs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found（可能已逾時淘汰）")
    if job.status == "error":
        raise HTTPException(status_code=500, detail=job.error or "生成失敗")
    if job.status != "done":
        raise HTTPException(status_code=409, detail=f"Job 尚未完成（{job.status}）")
    if not (0 <= index < len(job.images)):
        raise HTTPException(status_code=404, detail=f"index 超出範圍（共 {len(job.images)} 張）")
    hist_id = job.meta.get("history_id")
    return Response(
        content=job.images[index],
        media_type="image/png",
        headers={
            "X-Seed": str(job.meta.get("seed", "")),
            "X-Batch-Index": str(index),
            "X-Batch-Size": str(job.meta.get("batch_size", 1)),
            "X-History-Id": str(hist_id) if hist_id else "",
        },
    )


def _style_prompts(db: Session, art_style_id: Optional[int], prompt: str, negative: str):
    """inpaint/upscale 共用：解析 art_style，補 extra tags 與預設負向。"""
    art_style = db.get(ArtStyle, art_style_id) if art_style_id else None
    style = _resolve_style(art_style)
    default_neg = (art_style.negative or STYLE_CONFIG[style].negative) if art_style else STYLE_CONFIG[style].negative
    negative = negative.strip() or default_neg
    prompt = prompt.strip()
    extra = _extra_tags(art_style)
    if prompt and extra:
        prompt = f"{prompt}, {extra}"
    return style, prompt, negative


@router.post("/art/inpaint", summary="局部重繪（白色遮罩區 = 重繪區）")
async def inpaint(
    file: Annotated[UploadFile, File(description="原圖 (JPEG/PNG)")],
    mask: Annotated[UploadFile, File(description="遮罩圖（白=重繪區、黑=保留）")],
    prompt: str = Form("", description="重繪區內容描述（SD tags，可空）"),
    negative_prompt: str = Form(""),
    denoise: float = Form(0.75, ge=0.1, le=1.0, description="重繪強度：0.5 微調 / 0.75 標準 / 1.0 全換"),
    steps: int = Form(20, ge=1, le=60),
    seed: int = Form(-1),
    grow_mask: int = Form(6, ge=0, le=64, description="遮罩外擴像素，緩和接縫"),
    art_style_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    """完稿微調用：改手、改臉、改局部細節，不必整張重 roll。"""
    style, pos, neg = _style_prompts(db, art_style_id, prompt, negative_prompt)
    actual_seed = seed if seed >= 0 else random.randint(0, 2**31 - 1)

    wf = _load_workflow(state.get_workflow())
    canvas_name = comfyui_client.upload_image_bytes(await file.read(), "inpaint_canvas.png")
    mask_name = comfyui_client.upload_image_bytes(await mask.read(), "inpaint_mask.png")
    try:
        image_edit_service.to_inpaint_workflow(wf, canvas_name, mask_name, denoise, grow_mask)
    except image_edit_service.WorkflowShapeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _inject_prompts(wf, pos, neg)
    for node in wf.values():
        if isinstance(node, dict) and node.get("class_type") == "KSampler":
            node["inputs"]["seed"] = actual_seed
            node["inputs"]["steps"] = steps
    _replace_negative_seeds(wf, actual_seed)

    await guardian.request_focus("comfyui")
    image_bytes = await _run_comfyui(wf)
    hist_id = record_generation(
        db, endpoint="inpaint", seed=actual_seed, workflow=state.get_workflow(),
        style=style.value, positive=pos, negative=neg,
        params={"denoise": denoise, "steps": steps, "grow_mask": grow_mask,
                "art_style_id": art_style_id},
    )
    return Response(
        content=image_bytes, media_type="image/png",
        headers={"X-Seed": str(actual_seed), "X-Denoise": str(denoise),
                 "X-History-Id": str(hist_id) if hist_id else ""},
    )


@router.post("/art/upscale", summary="高解析度修復（hires-fix 放大）")
async def upscale(
    file: Annotated[UploadFile, File(description="原圖 (JPEG/PNG)")],
    scale: float = Form(1.5, ge=1.1, le=2.0, description="放大倍率（1.5 建議；2.0 需較多 VRAM）"),
    denoise: float = Form(0.4, ge=0.1, le=0.7, description="重採樣強度：0.3 保守 / 0.4 標準 / 0.55 重建細節"),
    prompt: str = Form("", description="內容描述（可空，給重採樣參考）"),
    negative_prompt: str = Form(""),
    steps: int = Form(20, ge=1, le=60),
    seed: int = Form(-1),
    art_style_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    """完稿輸出用：潛空間放大 + 低 denoise 重採樣補細節（只用核心節點，免裝 upscale 模型）。"""
    style, pos, neg = _style_prompts(db, art_style_id, prompt, negative_prompt)
    actual_seed = seed if seed >= 0 else random.randint(0, 2**31 - 1)

    wf = _load_workflow(state.get_workflow())
    image_name = comfyui_client.upload_image_bytes(await file.read(), "upscale_src.png")
    try:
        image_edit_service.to_upscale_workflow(wf, image_name, scale, denoise)
    except image_edit_service.WorkflowShapeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _inject_prompts(wf, pos, neg)
    for node in wf.values():
        if isinstance(node, dict) and node.get("class_type") == "KSampler":
            node["inputs"]["seed"] = actual_seed
            node["inputs"]["steps"] = steps
    _replace_negative_seeds(wf, actual_seed)

    await guardian.request_focus("comfyui")
    image_bytes = await _run_comfyui(wf)
    hist_id = record_generation(
        db, endpoint="upscale", seed=actual_seed, workflow=state.get_workflow(),
        style=style.value, positive=pos, negative=neg,
        params={"scale": scale, "denoise": denoise, "steps": steps,
                "art_style_id": art_style_id},
    )
    return Response(
        content=image_bytes, media_type="image/png",
        headers={"X-Seed": str(actual_seed), "X-Scale": str(scale),
                 "X-History-Id": str(hist_id) if hist_id else ""},
    )


@router.post("/art/compose", summary="草圖問答 → 構圖意見 + 參考圖")
async def compose(
    file: Annotated[UploadFile, File(description="草稿圖片")],
    question: Optional[str] = Form(None, description="針對草圖的構圖問題（空白則 AI 自動分析）"),
    model: str = Form(""),
    character_ref: Optional[UploadFile] = File(None, description="角色外觀參考圖（隱藏備用）"),
    ipa_weight: float = Form(0.6, ge=0.1, le=1.5, description="IP-Adapter 強度"),
    use_sketch_as_ref: bool = Form(False, description="以草圖本身作為 IP-Adapter 參考"),
    use_cn: bool = Form(False, description="以草圖作為 ControlNet hint"),
    cn_weight: float = Form(0.85, ge=0.1, le=1.5, description="ControlNet 強度"),
):
    image_bytes = await file.read()
    width, height = _image_dimensions(image_bytes)
    effective_model = model.strip() or state.get_vision_model()

    await guardian.request_focus("ollama")
    try:
        advice, sdxl_prompt = art_service.compose_ask(question or None, image_bytes, model=effective_model)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    seed = random.randint(0, 2**31 - 1)
    active_wf = state.get_workflow()
    style = _detect_style(active_wf)
    negative = STYLE_CONFIG[style].negative

    # Cap generation to 1024px max (preserve aspect ratio from original sketch)
    _MAX_COMPOSE_DIM = 1024
    ratio = width / height
    if width >= height:
        gen_w = _MAX_COMPOSE_DIM
        gen_h = _clamp_dim(int(_MAX_COMPOSE_DIM / ratio))
    else:
        gen_h = _MAX_COMPOSE_DIM
        gen_w = _clamp_dim(int(_MAX_COMPOSE_DIM * ratio))
    gen_w = max(512, gen_w)
    gen_h = max(512, gen_h)

    await guardian.request_focus("comfyui")

    # CN：草圖 letterbox 後上傳作為 ControlNet hint
    uploaded_cn: str | None = None
    if use_cn:
        sketch_lb = _letterbox_to_aspect(image_bytes, gen_w, gen_h)
        uploaded_cn = comfyui_client.upload_image_bytes(sketch_lb, "compose_cn_ref.png")

    if use_sketch_as_ref or character_ref is not None:
        # IP-Adapter 模式：以草圖（或外部參考圖）作為外觀基準
        if character_ref is not None:
            ref_bytes = await character_ref.read()
            ref_filename = character_ref.filename or "char_ref.png"
        else:
            ref_bytes = image_bytes
            ref_filename = "sketch_ref.png"
        uploaded_ref = comfyui_client.upload_image_bytes(ref_bytes, ref_filename)
        final_prompt = sdxl_prompt.rstrip(", ") + ", full body, complete character, all limbs visible"
        wf = _load_workflow("ipadapter_txt2img.json")

        # CN 注入 / bypass
        if use_cn and not _wf_has_controlnet(wf):
            _inject_ipa_cn_nodes(wf, inject_ipa=False, inject_cn=True)
        elif not use_cn and _wf_has_controlnet(wf):
            _bypass_controlnet_nodes(wf)

        _inject_prompts(wf, final_prompt, negative)
        for node in wf.values():
            if not isinstance(node, dict):
                continue
            ct = node.get("class_type")
            inputs = node.get("inputs", {})
            if ct == "IPAdapterAdvanced":
                inputs["weight"] = round(ipa_weight, 2)
            elif ct == "EmptyLatentImage":
                inputs["width"] = gen_w
                inputs["height"] = gen_h
            elif ct == "KSampler":
                inputs["seed"] = seed

        # IPA 圖片：BFS 只注入 IPA 鏈的 LoadImage（不覆蓋 CN 的 LoadImage）
        _inject_ipa_image(wf, uploaded_ref)
    else:
        # txt2img / CN-only 模式
        final_prompt = sdxl_prompt.rstrip(", ") + ", full body, complete character, all limbs visible, white background, monochrome, lineart, clean lines, no shading, no color"
        wf = _load_workflow(active_wf)

        # IPA bypass（若 workflow 有殘留 IPA 節點）
        if _wf_has_ipa(wf):
            _bypass_ipa_nodes(wf)

        # CN 注入 / bypass
        if use_cn and not _wf_has_controlnet(wf):
            _inject_ipa_cn_nodes(wf, inject_ipa=False, inject_cn=True)
        elif not use_cn and _wf_has_controlnet(wf):
            _bypass_controlnet_nodes(wf)

        _inject_prompts(wf, final_prompt, negative)
        for node in wf.values():
            if not isinstance(node, dict):
                continue
            ct = node.get("class_type")
            inputs = node.get("inputs", {})
            if ct == "EmptyLatentImage":
                inputs["width"] = gen_w
                inputs["height"] = gen_h
            elif ct == "KSampler":
                inputs["seed"] = seed

    # CN 圖片注入 + 強度設定
    if use_cn and uploaded_cn and _wf_has_controlnet(wf):
        _inject_controlnet_image(wf, uploaded_cn)
        for node in wf.values():
            if isinstance(node, dict) and node.get("class_type") in _CN_APPLY_TYPES:
                node.get("inputs", {})["strength"] = round(cn_weight, 2)

    _replace_negative_seeds(wf, seed)
    image_data = await _run_comfyui(wf)
    encoded_image = base64.b64encode(image_data).decode()

    return {
        "advice": advice,
        "suggested_prompt": final_prompt,
        "image": encoded_image,
        "seed": seed,
        "style": style.value,
    }


# ── Character Design Sheet Generation ────────────────────────────────────────

def _hex_to_sd_color(hex_color: str) -> str:
    """Convert #RRGGBB to an approximate SD color name (e.g. 'dark green')."""
    try:
        h = hex_color.lstrip('#')
        r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
        hue, sat, val = colorsys.rgb_to_hsv(r, g, b)
        hue_deg = hue * 360
        if val < 0.15:
            return "black"
        if val > 0.85 and sat < 0.12:
            return "white"
        if sat < 0.12:
            return "gray"
        if   hue_deg < 15 or hue_deg >= 345: base = "red"
        elif hue_deg < 40:  base = "orange"
        elif hue_deg < 70:  base = "yellow"
        elif hue_deg < 150: base = "green"
        elif hue_deg < 185: base = "cyan"
        elif hue_deg < 260: base = "blue"
        elif hue_deg < 290: base = "purple"
        else:               base = "pink"
        prefix = "dark " if val < 0.45 else "light " if val > 0.75 else ""
        return prefix + base
    except Exception:
        return "colored"


# CN weight override (None = 維持使用者設定)
_COVERAGE_CN_WEIGHT: dict[str, float | None] = {
    "full":    None,
    "partial": None,
    "bust":    None,
}
# CN end_percent override
_COVERAGE_CN_END_PERCENT: dict[str, float | None] = {
    "full":    None,
    "partial": None,
    "bust":    None,
}



# expression id → (English SD tags for positive, Chinese label)
_EXPRESSION_MAP: dict[str, tuple[str, str]] = {
    "smile":   ("smiling, happy expression, gentle smile", "喜"),
    "angry":   ("angry expression, frowning, fierce glare", "怒"),
    "sad":     ("sad expression, teary eyes, sorrowful", "哀"),
    "joy":     ("laughing, joyful expression, excited, wide grin", "樂"),
    "neutral": ("neutral expression, calm, composed, expressionless", "平靜"),
}


def _create_inpaint_canvas_and_mask(
    sketch_bytes: bytes,
    target_w: int,
    target_h: int,
    coverage: str,
) -> tuple[bytes, bytes]:
    """
    Place sketch in upper portion of a full-body canvas and generate inpaint mask.
    Returns (canvas_png, mask_png) — mask white=inpaint lower body, black=preserve sketch.
    """
    fill = _BODY_FILL_RATIO.get(coverage, 0.72)
    top_offset_ratio = _BODY_TOP_OFFSET.get(coverage, 0.02)

    img = Image.open(io.BytesIO(sketch_bytes)).convert("RGB")
    w, h = img.size
    max_h = int(target_h * fill)
    scale = min(target_w / w, max_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    bg = _border_color(img)
    canvas = Image.new("RGB", (target_w, target_h), bg)
    top = int(target_h * top_offset_ratio)
    left = (target_w - new_w) // 2
    canvas.paste(img, (left, top))

    # Mask: 0=preserve (upper sketch), 255=inpaint (lower body)
    sketch_bottom = top + new_h
    blend_px = max(20, new_h // 8)
    blend_start = max(0, sketch_bottom - blend_px)

    mask = Image.new("L", (target_w, target_h), 0)
    draw = ImageDraw.Draw(mask)
    if sketch_bottom < target_h:
        draw.rectangle([0, sketch_bottom, target_w - 1, target_h - 1], fill=255)
    for dy in range(blend_px):
        y = blend_start + dy
        if y >= target_h:
            break
        draw.rectangle([0, y, target_w - 1, y], fill=int(dy / blend_px * 255))

    canvas_out = io.BytesIO()
    canvas.save(canvas_out, format="PNG")
    mask_out = io.BytesIO()
    mask.save(mask_out, format="PNG")
    return canvas_out.getvalue(), mask_out.getvalue()


def _inject_inpaint_nodes(wf: dict, canvas_filename: str, mask_filename: str) -> None:
    """
    Replace EmptyLatentImage with VAEEncodeForInpaint (canvas image + mask).
    Sets KSampler denoise=1.0 so only the masked lower-body region is regenerated.
    """
    empty_latent_id: str | None = None
    for nid, node in wf.items():
        if isinstance(node, dict) and node.get("class_type") == "EmptyLatentImage":
            empty_latent_id = nid
            break
    if empty_latent_id is None:
        logger.warning("[inpaint-inject] EmptyLatentImage not found — inpaint skipped")
        return

    vae_ref: list | None = None
    for nid, node in wf.items():
        if isinstance(node, dict) and node.get("class_type") == "CheckpointLoaderSimple":
            vae_ref = [nid, 2]
            break
    if vae_ref is None:
        logger.warning("[inpaint-inject] CheckpointLoaderSimple not found — inpaint skipped")
        return

    max_id = max((int(k) for k in wf if k.isdigit()), default=500)
    canvas_load_id = str(max_id + 1)
    mask_load_id = str(max_id + 2)
    vae_encode_id = str(max_id + 3)

    wf[canvas_load_id] = {
        "class_type": "LoadImage",
        "inputs": {"image": canvas_filename, "upload": "image"},
    }
    wf[mask_load_id] = {
        "class_type": "LoadImageMask",
        "inputs": {"image": mask_filename, "channel": "red", "upload": "image"},
    }
    wf[vae_encode_id] = {
        "class_type": "VAEEncodeForInpaint",
        "inputs": {
            "pixels": [canvas_load_id, 0],
            "vae": vae_ref,
            "mask": [mask_load_id, 0],
            "grow_mask_by": 6,
        },
    }

    for nid, node in wf.items():
        if not isinstance(node, dict) or nid == empty_latent_id:
            continue
        for key, val in node.get("inputs", {}).items():
            if isinstance(val, list) and val and str(val[0]) == empty_latent_id:
                node["inputs"][key] = [vae_encode_id, 0]

    wf.pop(empty_latent_id, None)

    for node in wf.values():
        if isinstance(node, dict) and node.get("class_type") == "KSampler":
            node.get("inputs", {})["denoise"] = 1.0

    logger.info("[inpaint-inject] VAEEncodeForInpaint injected (canvas=%s)", canvas_filename)


def _inject_img2img_node(wf: dict, canvas_filename: str, denoise: float = 0.70) -> None:
    """
    Replace EmptyLatentImage with VAEEncode (img2img).
    The full canvas (sketch in upper portion) is encoded as the starting latent;
    KSampler denoise=0.70 re-renders the whole image in a unified style while
    preserving the sketch structure — no hard seam between original and generated.
    """
    empty_latent_id: str | None = None
    for nid, node in wf.items():
        if isinstance(node, dict) and node.get("class_type") == "EmptyLatentImage":
            empty_latent_id = nid
            break
    if empty_latent_id is None:
        logger.warning("[img2img-inject] EmptyLatentImage not found — img2img skipped")
        return

    vae_ref: list | None = None
    for nid, node in wf.items():
        if isinstance(node, dict) and node.get("class_type") == "CheckpointLoaderSimple":
            vae_ref = [nid, 2]
            break
    if vae_ref is None:
        logger.warning("[img2img-inject] CheckpointLoaderSimple not found — img2img skipped")
        return

    max_id = max((int(k) for k in wf if k.isdigit()), default=500)
    load_id = str(max_id + 1)
    encode_id = str(max_id + 2)

    wf[load_id] = {
        "class_type": "LoadImage",
        "inputs": {"image": canvas_filename, "upload": "image"},
    }
    wf[encode_id] = {
        "class_type": "VAEEncode",
        "inputs": {"pixels": [load_id, 0], "vae": vae_ref},
    }

    for nid, node in wf.items():
        if not isinstance(node, dict) or nid == empty_latent_id:
            continue
        for key, val in node.get("inputs", {}).items():
            if isinstance(val, list) and val and str(val[0]) == empty_latent_id:
                node["inputs"][key] = [encode_id, 0]

    wf.pop(empty_latent_id, None)

    for node in wf.values():
        if isinstance(node, dict) and node.get("class_type") == "KSampler":
            node.get("inputs", {})["denoise"] = denoise

    logger.info("[img2img-inject] VAEEncode injected (canvas=%s, denoise=%.2f)", canvas_filename, denoise)


_CANVAS_EXPAND_WF = "canvas_expand_flux.json"


async def _run_canvas_expand_flux(
    sketch_bytes: bytes,
    coverage: str,
    positive: str,
    width: int,
    height: int,
    seed: int,
) -> bytes:
    """
    Canvas expand using Flux 2 Dev inpainting:
    - Sketch placed in the upper portion of the canvas
    - Lower body area (mask=white) inpainted by Flux 2
    - Returns full-body image bytes
    """
    canvas_bytes, mask_bytes = _create_inpaint_canvas_and_mask(
        sketch_bytes, width, height, coverage
    )
    canvas_fn = comfyui_client.upload_image_bytes(canvas_bytes, "canvas_expand_input.png")
    mask_fn = comfyui_client.upload_image_bytes(mask_bytes, "canvas_expand_mask.png")

    wf = _load_workflow(_CANVAS_EXPAND_WF)

    for nid, node in wf.items():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        inputs = node.get("inputs", {})
        if ct == "LoadImage" and inputs.get("image") == "":
            inputs["image"] = canvas_fn
        elif ct == "LoadImageMask" and inputs.get("image") == "":
            inputs["image"] = mask_fn
        elif ct == "CLIPTextEncode":
            inputs["text"] = positive
        elif ct == "RandomNoise":
            inputs["noise_seed"] = seed

    _log_wf_snapshot(wf, label="canvas-expand")
    await guardian.request_focus("comfyui")
    try:
        return await _run_comfyui(wf)
    except Exception as e:
        logger.error("[canvas-expand] ComfyUI 執行失敗: %s: %s", type(e).__name__, e)
        raise


@router.post("/characters/{character_id}/generate-design", summary="角色人設圖生成（ComfyUI）")
async def generate_character_design(
    character_id: int,
    expression: Optional[str] = None,  # None=full body; key from _EXPRESSION_MAP = bust shot
    art_style_id: Optional[int] = None,
    use_ai_prompt: bool = True,
    use_outfit: bool = True,
    use_ipa: bool = True,
    ipa_weight: float = 0.6,
    use_controlnet: bool = True,
    cn_weight: float = 0.85,
    db: Session = Depends(get_db),
):
    """
    expression=None  → full-body character design sheet (768×1024)
    expression=<key> → bust/face close-up with that expression (512×640)
    Returns PNG bytes.
    """
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    if expression and expression not in _EXPRESSION_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown expression. Valid: {list(_EXPRESSION_MAP)}")

    # Priority: explicit param > character.art_style_id > project.art_style_id > _detect_style()
    if art_style_id is None and character.art_style_id:
        art_style_id = character.art_style_id
    if art_style_id is None:
        from app.models.project import Project as _Project
        proj = db.get(_Project, character.project_id)
        if proj and proj.art_style_id:
            art_style_id = proj.art_style_id

    is_expression = expression is not None
    expr_tags, _ = _EXPRESSION_MAP[expression] if is_expression else ("", "")

    timings: dict[str, float] = {}
    t_total = time.perf_counter()

    # ── Build Chinese description ──────────────────────────────────────────
    # Age/gender are encoded via gender_prefix (1boy/1girl/1man/1woman) — do NOT
    # pass age text to the LLM to avoid spurious "15 years old" text tags.
    parts = [f"角色名稱：{character.name}"]

    # Visual traits from first concept image — added BEFORE core_traits so that
    # the author's explicit description (core_traits) takes precedence when the
    # LLM resolves conflicts (recency bias: later tokens win).
    concept_imgs = list(character.concept_images or [])
    if not concept_imgs and character.portrait_path:
        concept_imgs = [character.portrait_path]

    _ipa_ref_bytes: bytes | None = None
    _cn_ref_bytes: bytes | None = None
    _cn_coverage: str = "full"
    _coverage_end_pct: float | None = None

    if concept_imgs:
        # Load all available concept images (up to 3) for multi-image analysis
        valid_images: list[bytes] = []
        for img_filename in concept_imgs[:3]:
            img_path = _PORTRAIT_DIR / img_filename
            if img_path.exists():
                try:
                    valid_images.append(img_path.read_bytes())
                except Exception:
                    pass

        # Detect flat-color drafts before vision analysis
        all_flat = all(_is_flat_color_draft(img) for img in valid_images)
        logger.info("[prompt-log] concept images flat_draft=%s (%d imgs)", all_flat, len(valid_images))

        # IP-Adapter: use first available image when enabled (flat drafts included)
        if use_ipa and valid_images:
            _ipa_ref_bytes = valid_images[0]

        # ControlNet base ref (may be overridden by _shrink_for_full_body below)
        if use_controlnet and valid_images:
            _cn_ref_bytes = valid_images[0]

        # Full-body CN mode: merge coverage detection + visual extraction into one Ollama call
        # to avoid paying the vision-model cold-start cost twice.
        # Result cached by image hash — repeat generations skip the vision call.
        if valid_images:
            t0 = time.perf_counter()
            need_coverage = use_controlnet and not is_expression
            coverage, visual = await _vision_extract_cached(valid_images, need_coverage)
            timings["vision_extract"] = round(time.perf_counter() - t0, 1)
            if need_coverage:
                _exp_w, _exp_h = _fullbody_canvas(getattr(character, 'height', None))
                _cn_coverage = coverage
                # Pixel fallback：LLM 偵測不穩定時，用像素分析二次確認
                if _cn_coverage == "full":
                    pixel_override = _pixel_coverage_check(valid_images[0])
                    if pixel_override:
                        logger.info("[char-gen] pixel-check override: %s → %s", _cn_coverage, pixel_override)
                        _cn_coverage = pixel_override
                # CN≥0.7 限制條件：所有 coverage 一律保留 CN，不再 bypass。
                # partial/bust 透過 _shrink_for_full_body 把草圖縮到畫布上半（依
                # _BODY_FILL_RATIO），下半留空交給 SD 補腿；CN 以 AnimeLineArt（非 Canny）
                # 用使用者權重引導上半身結構，單 pass 無接縫。
                _cn_ref_bytes = _shrink_for_full_body(valid_images[0], _exp_w, _exp_h, _cn_coverage)
                _override_cn_w = _COVERAGE_CN_WEIGHT.get(_cn_coverage)
                if _override_cn_w is not None:
                    cn_weight = _override_cn_w
                _coverage_end_pct = _COVERAGE_CN_END_PERCENT.get(_cn_coverage)
                logger.info(
                    "[char-gen] coverage=%s → CN (weight=%.2f, fill=%.2f)",
                    _cn_coverage, cn_weight, _BODY_FILL_RATIO.get(_cn_coverage, 1.0),
                )
            logger.debug("visual extract (%d imgs): %s", len(valid_images), visual)
            if visual and not visual.startswith("["):
                has_outfit = bool(use_outfit and getattr(character, 'outfit', None))
                has_hair_in_traits = bool(character.core_traits and
                    any(kw in character.core_traits for kw in ("髮", "頭髮", "hair")))
                visual_for_llm = _filter_visual_for_llm(
                    visual,
                    strip_clothing=has_outfit,
                    strip_hairstyle=has_hair_in_traits,
                )
                if visual_for_llm:
                    if len(valid_images) > 1:
                        label = "視覺參考特徵（多圖共同，服裝髮型以設定欄位為準）" if (has_outfit or has_hair_in_traits) else "視覺參考特徵（多圖共同特徵）"
                    else:
                        label = "視覺外觀提示（膚色體型風格參考）" if (has_outfit or has_hair_in_traits) else "視覺參考特徵（僅供風格參考）"
                    parts.append(f"{label}：{visual_for_llm}")
    else:
        all_flat = True  # no images → treat as flat, use core_traits for anchors

    if use_outfit and getattr(character, 'outfit', None):
        parts.append(f"服裝設定：{character.outfit}")

    if character.core_traits:
        parts.append(f"外貌與個性（優先採用）：{character.core_traits}")

    # Background colour is injected directly into the SD suffix (bg_tag) — NOT
    # passed through Ollama compilation, to avoid duplicate background tokens and
    # mixed-language noise in the compiled prompt.
    bg_color_name = _hex_to_sd_color(character.color) if character.color else None

    if is_expression:
        parts.append("動漫插畫風格，角色臉部特寫半身圖")
    else:
        parts.append("人設圖，全身正面，動漫插畫風格，清晰展示角色外觀")

    raw_desc = "，".join(parts)
    logger.info("[prompt-log] raw_desc (中文，AI翻譯前): %s", raw_desc)

    # Color anchor source:
    #   flat draft (single fill) → core_traits wins (vision colors are canvas fill, not character)
    #   properly colored         → raw_desc (vision colors trusted as actual character appearance)
    _color_anchor = character.core_traits or ""

    # ── Compile character description ──────────────────────────────────────
    t0 = time.perf_counter()
    art_style = db.get(ArtStyle, art_style_id) if art_style_id else None
    style = _resolve_style(art_style)
    _overrides = _compile_overrides(art_style)
    await guardian.request_focus("ollama")
    try:
        positive, negative = compile_prompt(
            raw_desc, style=style, model=state.get_text_model(),
            anchor_text=_color_anchor, **_overrides,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"Ollama 文字模型失敗，請確認 {state.get_text_model()} 已安裝：{e}")
    timings["compile_prompt"] = round(time.perf_counter() - t0, 1)

    # ── Compile ai_prompt separately (placed first → higher SD attention weight) ──
    extra_prefix = ""
    _ai_prompt_compiled = ""
    if use_ai_prompt and character.ai_prompt and character.ai_prompt.strip():
        t0 = time.perf_counter()
        await guardian.request_focus("ollama")
        try:
            # quality_prefix_override="" prevents duplicate quality tags in final prompt
            _ai_overrides = {**_overrides, "quality_prefix_override": ""}
            extra_compiled, _ = compile_prompt(
                character.ai_prompt.strip(), style=style, model=state.get_text_model(), **_ai_overrides,
            )
            _ai_prompt_compiled = extra_compiled
        except RuntimeError:
            extra_compiled = ""
            _ai_prompt_compiled = "[compilation_failed]"
        timings["compile_ai_prompt"] = round(time.perf_counter() - t0, 1)
        if extra_compiled:
            extra_prefix = extra_compiled + ", "

    # ── Build final prompt based on mode ──────────────────────────────────
    bg_tag = f", {bg_color_name} background" if bg_color_name else ", gradient background"

    if is_expression:
        suffix = (
            f", {expr_tags}"
            ", bust shot, upper body, close-up portrait, face focus"
            ", simple background, flat background" + bg_tag
        )
        width, height, steps = 512, 640, 20
    else:
        # partial/bust: "character design sheet" causes multi-view compositions (small sketch in
        # corner + 3/4 body main view). Use single full-body illustration mode instead.
        _design_tags = (
            "character illustration, full body portrait"
            if _cn_coverage in ("partial", "bust")
            else "character design sheet, character reference sheet"
        )
        suffix = (
            f", {_design_tags}"
            ", full body, front view"
            f", {_FULLBODY_POS_TAGS}"
            ", simple background, flat background, no background detail, no scenery" + bg_tag
        )
        # 畫布比例依角色身高自動匹配（高瘦更長、矮/幼態較方），減少頭/腳裁切
        width, height = _fullbody_canvas(getattr(character, 'height', None))
        steps = 20

    # Gender/age tag anchors subject count — must be at absolute front
    gender_tag = _age_gender_tag(character.gender, character.age)
    gender_prefix = gender_tag + ", " if gender_tag else ""

    # Age + height body proportion tags (placed right after gender anchor)
    _age_tags = _age_body_tags(character.age)
    _ht_tags = _height_body_tags(getattr(character, 'height', None))
    _body_parts = [t for t in [_age_tags, _ht_tags] if t]
    body_prefix = ", ".join(_body_parts) + ", " if _body_parts else ""

    # Gender-specific prompt reinforcement
    is_male = gender_tag.startswith(("1boy", "1man"))
    is_female = gender_tag.startswith(("1girl", "1woman"))
    # "clothed, shirt" anchors clothing when core_traits lacks an explicit outfit.
    # If core_traits already specifies clothing (e.g. jacket, robe), those tags carry
    # higher weight and override these soft defaults.
    gender_pos_extra = ", clothed, shirt, pants, male clothes" if is_male else ""
    gender_neg_extra = (
        ", bare chest, shirtless, topless, naked upper body, no shirt"
        ", skirt, dress, miniskirt, female clothes, feminine clothing, thighhighs, sailor uniform"
        if is_male else
        ", male face, masculine features" if is_female else ""
    )

    # art_style extra_tags → 若未設定且 PERSONAL_STYLE_ENABLED，使用個人風格標籤
    style_extra = _extra_tags(art_style)
    if not style_extra and PERSONAL_STYLE_ENABLED and PERSONAL_STYLE_EXTRA_TAGS:
        style_extra = PERSONAL_STYLE_EXTRA_TAGS
    style_extra_str = f", {style_extra}" if style_extra else ""

    # ai_prompt compiled tags lead the prompt for maximum enforcement
    final_positive = gender_prefix + body_prefix + extra_prefix + positive + suffix + gender_pos_extra + style_extra_str

    extra_neg = "detailed background, complex background, scenery, landscape, buildings, environment"
    # 全身模式補上裁切/缺手指防護；表情特寫模式維持原樣（特寫本就允許 close-up/portrait）
    if not is_expression:
        extra_neg = f"{extra_neg}, {_FULLBODY_NEG_TAGS}"
        # partial/bust 參考圖：禁止多視圖設計稿構圖（避免生成含草稿縮圖的設計稿格式）
        if _cn_coverage in ("partial", "bust"):
            extra_neg += ", multiple views, reference sheet, design sheet, multiple poses, chibi inset, inset image, sketch overlay"
    # 負向：art_style 有設定 → 優先；否則若 PERSONAL_NEGATIVE_ENABLED → 使用個人負向
    base_neg = negative
    if PERSONAL_NEGATIVE_ENABLED and PERSONAL_NEGATIVE and not (art_style and art_style.negative):
        base_neg = PERSONAL_NEGATIVE
    final_negative = f"{base_neg}, {extra_neg}{gender_neg_extra}" if base_neg else f"{extra_neg}{gender_neg_extra}"

    # ── Canvas Expand（Flux 2 inpainting：partial/bust → 補足下半身）──────────────
    seed = random.randint(0, 2**31 - 1)
    _canvas_expand_available = (CUSTOM_WORKFLOWS_DIR / _CANVAS_EXPAND_WF).exists()
    if (not is_expression
            and _cn_coverage in ("partial", "bust")
            and _ipa_ref_bytes is not None
            and _canvas_expand_available):
        t0 = time.perf_counter()
        logger.info("[char-gen] canvas-expand via Flux 2 (coverage=%s)", _cn_coverage)
        image_bytes = await _run_canvas_expand_flux(
            _ipa_ref_bytes, _cn_coverage, final_positive, width, height, seed
        )
        timings["canvas_expand"] = round(time.perf_counter() - t0, 1)
        timings["total"] = round(time.perf_counter() - t_total, 1)
        timings["models"] = {"vision": state.get_vision_model(), "text": state.get_text_model(), "workflow": _CANVAS_EXPAND_WF}
        return Response(
            content=image_bytes,
            media_type="image/png",
            headers={
                "X-Seed": str(seed), "X-Style": style.value,
                "X-Flat-Draft": "1" if all_flat else "0",
                "X-IPA-Used": "0", "X-CN-Used": "0", "X-CN-Mode": "canvas_expand",
                "X-Raw-Desc": base64.b64encode(raw_desc.encode()).decode(),
                "X-Prompt": base64.b64encode(final_positive.encode()).decode(),
                "X-Timings": base64.b64encode(json.dumps(timings).encode()).decode(),
                "X-AI-Prompt-Compiled": "",
            },
        )

    # ── Generate（SDXL 原始路徑）────────────────────────────────────────────
    ipa_used = False
    active_wf = state.get_workflow()

    global_lora = state.get_lora()
    lora_list = []
    if global_lora.get("name"):
        lora_list.append({"model": global_lora["name"], "weight": global_lora["strength"]})
    # 角色專屬 LoRA（直通欄位）：每角色一致性的主線，優先於畫風 LoRA 套用
    if character.lora_name:
        lora_list.append({
            "model": character.lora_name,
            "weight": character.lora_weight if character.lora_weight is not None else 0.8,
        })
    if art_style and art_style.loras:
        lora_list.extend(art_style.loras)

    logger.info("[char-gen] char_id=%s  use_ipa=%s  use_cn=%s  ipa_ref=%s  cn_ref=%s  active_workflow=%s",
                character_id, use_ipa, use_controlnet,
                "yes" if _ipa_ref_bytes else "no", "yes" if _cn_ref_bytes else "no", active_wf)
    # HTTPException (e.g. UI-format workflow 422) intentionally not caught here — surfaces to user
    wf = _load_workflow(active_wf)

    # 統一注入管線：功能啟用且有參考圖 → 工作流缺節點則動態建立、已有則沿用既有；
    #               功能停用或無參考圖 → 既有節點 bypass（少跑節點 → 生圖更快）。
    # 此設計同時解決 checkpoint 模式（text_to_image.json 無 IPA/CN 節點）下不套用的問題。
    need_ipa_inject = _ipa_ref_bytes is not None and not _wf_has_ipa(wf)
    need_cn_inject = _cn_ref_bytes is not None and not _wf_has_controlnet(wf)
    if need_ipa_inject or need_cn_inject:
        _inject_ipa_cn_nodes(wf, inject_ipa=need_ipa_inject, inject_cn=need_cn_inject)
        logger.info("[char-gen] 動態注入節點 ipa=%s cn=%s（工作流 '%s' 原缺節點）",
                    need_ipa_inject, need_cn_inject, active_wf)

    # IPA：有參考圖則啟用（含剛注入的節點）；否則既有 IPA 節點 bypass
    if _ipa_ref_bytes is not None:
        _t = time.perf_counter()
        uploaded_ref = comfyui_client.upload_image_bytes(_ipa_ref_bytes, "char_concept_ref.png")
        timings["upload"] = round(time.perf_counter() - _t, 1)
        ipa_used = True
        logger.info("[char-gen] IP-Adapter 啟用（active workflow '%s'）", active_wf)
    elif _wf_has_ipa(wf):
        _bypass_ipa_nodes(wf)
        logger.info("[char-gen] IPA 停用/無參考圖 → 既有節點 bypass")

    # ControlNet：無參考圖時剝離既有 CN 節點。
    # 須在 _inject_prompts 之前，使 KSampler 條件線直連 CLIPTextEncode。
    if _cn_ref_bytes is None and _wf_has_controlnet(wf):
        _bypass_controlnet_nodes(wf)
        logger.info("[char-gen] ControlNet 停用/無參考圖 → 既有節點 bypass")
    _inject_loras(wf, lora_list)
    _inject_prompts(wf, final_positive, final_negative)
    for node in wf.values():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        inputs = node.get("inputs", {})
        if ct == "EmptyLatentImage":
            inputs["width"] = width
            inputs["height"] = height
        elif ct == "KSampler":
            inputs["seed"] = seed
            inputs["steps"] = steps
        elif ct == "IPAdapterAdvanced" and ipa_used:
            inputs["weight"] = round(ipa_weight, 2)
        elif ct in _CN_APPLY_TYPES and _cn_ref_bytes is not None:
            inputs["strength"] = round(cn_weight, 2)
            if _coverage_end_pct is not None:
                inputs["end_percent"] = _coverage_end_pct
    # IPA 圖片注入：BFS 回溯找正確的 LoadImage，避免打到 ControlNet 等其他節點
    if ipa_used:
        _inject_ipa_image(wf, uploaded_ref)

    # ControlNet 圖片注入（Canny 跟隨概念圖 → 保留草圖姿勢）
    cn_used = False
    cn_mode = "none"
    if _cn_ref_bytes is not None and _wf_has_controlnet(wf):
        cn_bytes = _cn_ref_bytes
        if not is_expression:
            # 全身模式：先把概念圖補邊成畫布比例，避免置中裁切切掉頭/腳 → 全身完整
            cn_bytes = _letterbox_to_aspect(_cn_ref_bytes, width, height)
            cn_mode = "canny_fit"
        else:
            cn_mode = "canny"
        _t = time.perf_counter()
        uploaded_cn_ref = comfyui_client.upload_image_bytes(cn_bytes, "char_cn_ref.png")
        timings["upload"] = round(timings.get("upload", 0.0) + (time.perf_counter() - _t), 1)
        _inject_controlnet_image(wf, uploaded_cn_ref)
        cn_used = True
        logger.info("[char-gen] ControlNet (%s) injected, weight=%.2f", cn_mode, cn_weight)

    _replace_negative_seeds(wf, seed)
    _log_wf_snapshot(wf, label="char-gen")
    t0 = time.perf_counter()
    await guardian.request_focus("comfyui")
    image_bytes = await _run_comfyui(wf)
    timings["comfyui"] = round(time.perf_counter() - t0, 1)
    timings["total"] = round(time.perf_counter() - t_total, 1)
    timings["models"] = {
        "vision": state.get_vision_model(),
        "text": state.get_text_model(),
        "workflow": active_wf,
    }

    hist_id = record_generation(
        db,
        endpoint="character_design",
        character_id=character_id,
        seed=seed,
        workflow=active_wf,
        style=style.value,
        positive=final_positive,
        negative=final_negative,
        params={
            "width": width, "height": height, "steps": steps,
            "expression": expression, "art_style_id": art_style_id,
            "ipa_used": ipa_used, "ipa_weight": round(ipa_weight, 2),
            "cn_used": cn_used, "cn_weight": round(cn_weight, 2),
            "cn_mode": cn_mode, "coverage": _cn_coverage,
            "loras": lora_list, "use_ai_prompt": use_ai_prompt,
            "use_outfit": use_outfit, "timings": timings,
        },
    )
    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={
            "X-History-Id": str(hist_id) if hist_id else "",
            "X-Seed": str(seed),
            "X-Style": style.value,
            "X-Flat-Draft": "1" if all_flat else "0",
            "X-IPA-Used": "1" if ipa_used else "0",
            "X-CN-Used": "1" if cn_used else "0",
            "X-CN-Mode": cn_mode,
            "X-Raw-Desc": base64.b64encode(raw_desc.encode()).decode(),
            "X-Prompt": base64.b64encode(final_positive.encode()).decode(),
            "X-Timings": base64.b64encode(json.dumps(timings).encode()).decode(),
            "X-AI-Prompt-Compiled": base64.b64encode(_ai_prompt_compiled.encode()).decode() if _ai_prompt_compiled else "",
        },
    )


# ── Variant Design Sheet Generation ──────────────────────────────────────────

@router.post("/characters/{character_id}/variants/{slot}/generate-design", summary="角色變體人設圖生成（ComfyUI）")
async def generate_variant_design(
    character_id: int,
    slot: int,
    expression: Optional[str] = None,
    art_style_id: Optional[int] = None,
    use_ai_prompt: bool = True,
    use_outfit: bool = True,
    use_ipa: bool = True,
    ipa_weight: float = 0.6,
    use_controlnet: bool = True,
    cn_weight: float = 0.85,
    db: Session = Depends(get_db),
):
    """Generate a design sheet using the variant's data instead of the main character fields."""
    from app.api.characters import _get_variants, _slot_index

    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    idx = _slot_index(slot)
    variants = _get_variants(character)
    v = variants[idx]

    if expression and expression not in _EXPRESSION_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown expression. Valid: {list(_EXPRESSION_MAP)}")

    # Priority: explicit param > character.art_style_id > project.art_style_id > _detect_style()
    if art_style_id is None and character.art_style_id:
        art_style_id = character.art_style_id
    if art_style_id is None:
        from app.models.project import Project as _Project
        proj = db.get(_Project, character.project_id)
        if proj and proj.art_style_id:
            art_style_id = proj.art_style_id

    is_expression = expression is not None
    expr_tags, _ = _EXPRESSION_MAP[expression] if is_expression else ("", "")

    timings: dict[str, float] = {}
    t_total = time.perf_counter()

    # ── Build description from variant data ────────────────────────────────
    parts = [f"角色名稱：{character.name}"]

    concept_imgs = list(v.get("concept_images") or [])
    all_flat = True  # default: no images → use core_traits anchors
    _ipa_ref_bytes: bytes | None = None       # concept image for IP-Adapter
    _cn_ref_bytes: bytes | None = None        # concept image for ControlNet
    _coverage_end_pct: float | None = None   # CN end_percent override (partial/bust early-exit)
    _cn_coverage: str = "full"               # detected body coverage of concept image
    if concept_imgs:
        valid_images: list[bytes] = []
        for img_filename in concept_imgs[:3]:
            img_path = _PORTRAIT_DIR / img_filename
            if img_path.exists():
                try:
                    valid_images.append(img_path.read_bytes())
                except Exception:
                    pass
        if valid_images:
            all_flat = all(_is_flat_color_draft(img) for img in valid_images)
            logger.info("[prompt-log] variant concept images flat_draft=%s (%d imgs)", all_flat, len(valid_images))
            if use_ipa:
                _ipa_ref_bytes = valid_images[0]
            if use_controlnet:
                _cn_ref_bytes = valid_images[0]

            # Merge coverage detection + visual extraction into one Ollama call
            # (cached by image hash — repeat generations skip the vision call)
            t0 = time.perf_counter()
            need_coverage = use_controlnet and not is_expression
            coverage, visual = await _vision_extract_cached(valid_images, need_coverage)
            timings["vision_extract"] = round(time.perf_counter() - t0, 1)
            if need_coverage:
                _exp_w, _exp_h = _fullbody_canvas(v.get("height"))
                _cn_coverage = coverage
                # CN≥0.7 限制條件：所有 coverage 一律保留 CN，不再 bypass。
                # partial/bust 透過 _shrink_for_full_body 縮到畫布上半，下半留空補腿；
                # CN 以 AnimeLineArt（非 Canny）引導上半身，單 pass 無接縫。
                _cn_ref_bytes = _shrink_for_full_body(valid_images[0], _exp_w, _exp_h, coverage)
                _override_cn_w = _COVERAGE_CN_WEIGHT.get(coverage)
                if _override_cn_w is not None:
                    cn_weight = _override_cn_w
                _coverage_end_pct = _COVERAGE_CN_END_PERCENT.get(coverage)
                logger.info(
                    "[variant-gen] coverage=%s → CN (weight=%.2f, fill=%.2f)",
                    coverage, cn_weight, _BODY_FILL_RATIO.get(coverage, 1.0),
                )
            if visual and not visual.startswith("["):
                v_outfit_check = v.get("outfit")
                has_outfit = bool(use_outfit and v_outfit_check)
                v_core = v.get("core_traits") or ""
                has_hair_in_traits = bool(v_core and
                    any(kw in v_core for kw in ("髮", "頭髮", "hair")))
                visual_for_llm = _filter_visual_for_llm(
                    visual,
                    strip_clothing=has_outfit,
                    strip_hairstyle=has_hair_in_traits,
                )
                if visual_for_llm:
                    if len(valid_images) > 1:
                        label = "視覺參考特徵（多圖共同，服裝髮型以設定欄位為準）" if (has_outfit or has_hair_in_traits) else "視覺參考特徵（多圖共同特徵）"
                    else:
                        label = "視覺外觀提示（膚色體型風格參考）" if (has_outfit or has_hair_in_traits) else "視覺參考特徵（僅供風格參考）"
                    parts.append(f"{label}：{visual_for_llm}")

    v_outfit = v.get("outfit")
    if use_outfit and v_outfit:
        parts.append(f"服裝設定：{v_outfit}")

    core_traits = v.get("core_traits")
    if core_traits:
        parts.append(f"外貌與個性（優先採用）：{core_traits}")

    v_color = v.get("color")
    bg_color_name = _hex_to_sd_color(v_color) if v_color else None

    if is_expression:
        parts.append("動漫插畫風格，角色臉部特寫半身圖")
    else:
        parts.append("人設圖，全身正面，動漫插畫風格，清晰展示角色外觀")

    raw_desc = "，".join(parts)
    logger.info("[prompt-log] variant raw_desc (中文，AI翻譯前): %s", raw_desc)

    _color_anchor = core_traits or ""

    # ── Compile ───────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    art_style = db.get(ArtStyle, art_style_id) if art_style_id else None
    style = _resolve_style(art_style)
    _overrides = _compile_overrides(art_style)
    await guardian.request_focus("ollama")

    v_gender = v.get("gender")
    v_age = v.get("age")
    v_ai_prompt = v.get("ai_prompt")

    try:
        positive, negative = compile_prompt(
            raw_desc, style=style, model=state.get_text_model(),
            anchor_text=_color_anchor, **_overrides,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"Ollama 文字模型失敗，請確認 {state.get_text_model()} 已安裝：{e}")
    timings["compile_prompt"] = round(time.perf_counter() - t0, 1)

    extra_prefix = ""
    _ai_prompt_compiled = ""
    if use_ai_prompt and v_ai_prompt and v_ai_prompt.strip():
        t0 = time.perf_counter()
        await guardian.request_focus("ollama")
        try:
            _ai_overrides = {**_overrides, "quality_prefix_override": ""}
            extra_compiled, _ = compile_prompt(v_ai_prompt.strip(), style=style, model=state.get_text_model(), **_ai_overrides)
            _ai_prompt_compiled = extra_compiled
        except RuntimeError:
            extra_compiled = ""
            _ai_prompt_compiled = "[compilation_failed]"
        timings["compile_ai_prompt"] = round(time.perf_counter() - t0, 1)
        if extra_compiled:
            extra_prefix = extra_compiled + ", "

    bg_tag = f", {bg_color_name} background" if bg_color_name else ", gradient background"

    if is_expression:
        suffix = (
            f", {expr_tags}, bust shot, upper body, close-up portrait, face focus"
            ", simple background, flat background" + bg_tag
        )
        width, height, steps = 512, 640, 20
    else:
        _design_tags = (
            "character illustration, full body portrait"
            if _cn_coverage in ("partial", "bust")
            else "character design sheet, character reference sheet"
        )
        # partial/bust 參考圖時加 solo 避免 IPA 把設計稿的多視角構圖帶進來
        _solo_tag = ", solo, single character" if _cn_coverage in ("partial", "bust") else ""
        suffix = (
            f", {_design_tags}, full body, front view"
            f", {_FULLBODY_POS_TAGS}"
            f"{_solo_tag}"
            ", simple background, flat background, no background detail, no scenery" + bg_tag
        )
        width, height = _fullbody_canvas(v.get("height"))
        steps = 20

    gender_tag = _age_gender_tag(v_gender, v_age)
    gender_prefix = gender_tag + ", " if gender_tag else ""
    is_male = gender_tag.startswith(("1boy", "1man"))
    is_female = gender_tag.startswith(("1girl", "1woman"))
    gender_pos_extra = ", clothed, shirt, pants, male clothes" if is_male else ""
    gender_neg_extra = (
        ", bare chest, shirtless, topless, naked upper body, no shirt"
        ", skirt, dress, miniskirt, female clothes, feminine clothing, thighhighs, sailor uniform"
        if is_male else
        ", male face, masculine features" if is_female else ""
    )

    # Age + height body proportion tags
    _age_tags = _age_body_tags(v_age)
    _ht_tags = _height_body_tags(v.get("height"))
    _body_parts = [t for t in [_age_tags, _ht_tags] if t]
    body_prefix = ", ".join(_body_parts) + ", " if _body_parts else ""

    style_extra = _extra_tags(art_style)
    if not style_extra and PERSONAL_STYLE_ENABLED and PERSONAL_STYLE_EXTRA_TAGS:
        style_extra = PERSONAL_STYLE_EXTRA_TAGS
    style_extra_str = f", {style_extra}" if style_extra else ""

    final_positive = gender_prefix + body_prefix + extra_prefix + positive + suffix + gender_pos_extra + style_extra_str
    extra_neg = "detailed background, complex background, scenery, landscape, buildings, environment"
    if not is_expression:
        extra_neg = f"{extra_neg}, {_FULLBODY_NEG_TAGS}"
        if _cn_coverage in ("partial", "bust"):
            extra_neg += ", multiple views, reference sheet, design sheet, multiple poses, chibi inset, inset image, sketch overlay"
    base_neg = negative
    if PERSONAL_NEGATIVE_ENABLED and PERSONAL_NEGATIVE and not (art_style and art_style.negative):
        base_neg = PERSONAL_NEGATIVE
    final_negative = f"{base_neg}, {extra_neg}{gender_neg_extra}" if base_neg else f"{extra_neg}{gender_neg_extra}"

    seed = random.randint(0, 2**31 - 1)
    _canvas_expand_available = (CUSTOM_WORKFLOWS_DIR / _CANVAS_EXPAND_WF).exists()

    # ── Generate（SDXL 先生成完整風格圖）────────────────────────────────────────────
    ipa_used = False
    active_wf = state.get_workflow()

    global_lora = state.get_lora()
    lora_list = []
    if global_lora.get("name"):
        lora_list.append({"model": global_lora["name"], "weight": global_lora["strength"]})
    # 角色專屬 LoRA（直通欄位）：變體沿用主角色的 LoRA 以維持一致性
    if character.lora_name:
        lora_list.append({
            "model": character.lora_name,
            "weight": character.lora_weight if character.lora_weight is not None else 0.8,
        })
    if art_style and art_style.loras:
        lora_list.extend(art_style.loras)

    logger.info("[variant-gen] char_id=%s  slot=%s  use_ipa=%s  ipa_ref_bytes=%s  active_workflow=%s",
                character_id, slot, use_ipa, "yes" if _ipa_ref_bytes else "no", active_wf)
    # HTTPException intentionally not caught here — surfaces to user
    wf = _load_workflow(active_wf)

    # 統一注入管線（同 generate-design）：啟用且有圖 → 缺節點則建、有則沿用；
    # 停用或無圖 → 既有節點 bypass。同時解決 checkpoint 模式不套用問題。
    need_ipa_inject = _ipa_ref_bytes is not None and not _wf_has_ipa(wf)
    need_cn_inject = _cn_ref_bytes is not None and not _wf_has_controlnet(wf)
    if need_ipa_inject or need_cn_inject:
        _inject_ipa_cn_nodes(wf, inject_ipa=need_ipa_inject, inject_cn=need_cn_inject)
        logger.info("[variant-gen] 動態注入節點 ipa=%s cn=%s（工作流 '%s' 原缺節點）",
                    need_ipa_inject, need_cn_inject, active_wf)

    if _ipa_ref_bytes is not None:
        _t = time.perf_counter()
        uploaded_ref = comfyui_client.upload_image_bytes(_ipa_ref_bytes, "char_concept_ref.png")
        timings["upload"] = round(time.perf_counter() - _t, 1)
        ipa_used = True
        logger.info("[variant-gen] IP-Adapter 啟用（active workflow '%s'）", active_wf)
    elif _wf_has_ipa(wf):
        _bypass_ipa_nodes(wf)
        logger.info("[variant-gen] IPA 停用/無參考圖 → 既有節點 bypass")

    # ControlNet：無參考圖時剝離既有 CN 節點（須在 _inject_prompts 之前）
    if _cn_ref_bytes is None and _wf_has_controlnet(wf):
        _bypass_controlnet_nodes(wf)
        logger.info("[variant-gen] ControlNet 停用/無參考圖 → 既有節點 bypass")
    _inject_loras(wf, lora_list)
    _inject_prompts(wf, final_positive, final_negative)
    for node in wf.values():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        inputs = node.get("inputs", {})
        if ct == "EmptyLatentImage":
            inputs["width"] = width
            inputs["height"] = height
        elif ct == "KSampler":
            inputs["seed"] = seed
            inputs["steps"] = steps
        elif ct == "IPAdapterAdvanced" and ipa_used:
            inputs["weight"] = round(ipa_weight, 2)
        elif ct in _CN_APPLY_TYPES and _cn_ref_bytes is not None:
            inputs["strength"] = round(cn_weight, 2)
            if _coverage_end_pct is not None:
                inputs["end_percent"] = _coverage_end_pct
    if ipa_used:
        _inject_ipa_image(wf, uploaded_ref)

    cn_used = False
    cn_mode = "none"
    if _cn_ref_bytes is not None and _wf_has_controlnet(wf):
        cn_bytes = _cn_ref_bytes
        if not is_expression:
            cn_bytes = _letterbox_to_aspect(_cn_ref_bytes, width, height)
            cn_mode = "canny_fit"
        else:
            cn_mode = "canny"
        _t = time.perf_counter()
        uploaded_cn_ref = comfyui_client.upload_image_bytes(cn_bytes, "char_cn_ref.png")
        timings["upload"] = round(timings.get("upload", 0.0) + (time.perf_counter() - _t), 1)
        _inject_controlnet_image(wf, uploaded_cn_ref)
        cn_used = True
        logger.info("[variant-gen] ControlNet (%s) injected, weight=%.2f", cn_mode, cn_weight)

    _replace_negative_seeds(wf, seed)
    _log_wf_snapshot(wf, label="variant-gen")
    t0 = time.perf_counter()
    await guardian.request_focus("comfyui")
    image_bytes = await _run_comfyui(wf)
    timings["comfyui"] = round(time.perf_counter() - t0, 1)

    # ── Canvas Expand（Flux 2 inpainting：SDXL 輸出 → 補足下半身）──────────────
    # 只有 coverage=full 時 SDXL 有 CN 引導、輸出穩定為單人全身圖，才安全做 canvas expand
    # partial/bust 時 CN bypass → SDXL 可能生成設計稿多視角，canvas expand 會拼接錯誤
    cn_mode_out = cn_mode
    if (not is_expression
            and _cn_coverage == "full"
            and _canvas_expand_available):
        t0_expand = time.perf_counter()
        logger.info("[variant-gen] canvas-expand via Flux 2 on SDXL output (coverage=%s)", _cn_coverage)
        try:
            image_bytes = await _run_canvas_expand_flux(
                image_bytes, _cn_coverage, final_positive, width, height, seed
            )
            timings["canvas_expand"] = round(time.perf_counter() - t0_expand, 1)
            cn_mode_out = "canvas_expand"
        except Exception as e:
            logger.warning("[variant-gen] canvas-expand 失敗，使用 SDXL 輸出: %s", e)

    timings["total"] = round(time.perf_counter() - t_total, 1)
    timings["models"] = {
        "vision": state.get_vision_model(),
        "text": state.get_text_model(),
        "workflow": active_wf,
    }

    hist_id = record_generation(
        db,
        endpoint="variant_design",
        character_id=character_id,
        variant_slot=slot,
        seed=seed,
        workflow=active_wf,
        style=style.value,
        positive=final_positive,
        negative=final_negative,
        params={
            "width": width, "height": height, "steps": steps,
            "expression": expression, "art_style_id": art_style_id,
            "ipa_used": ipa_used, "ipa_weight": round(ipa_weight, 2),
            "cn_used": cn_used, "cn_weight": round(cn_weight, 2),
            "cn_mode": cn_mode_out, "coverage": _cn_coverage,
            "loras": lora_list, "use_ai_prompt": use_ai_prompt,
            "use_outfit": use_outfit, "timings": timings,
        },
    )
    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={
            "X-History-Id": str(hist_id) if hist_id else "",
            "X-Seed": str(seed),
            "X-Style": style.value,
            "X-Flat-Draft": "1" if all_flat else "0",
            "X-IPA-Used": "1" if ipa_used else "0",
            "X-CN-Used": "1" if cn_used else "0",
            "X-CN-Mode": cn_mode_out,
            "X-Raw-Desc": base64.b64encode(raw_desc.encode()).decode(),
            "X-Prompt": base64.b64encode(final_positive.encode()).decode(),
            "X-Timings": base64.b64encode(json.dumps(timings).encode()).decode(),
            "X-AI-Prompt-Compiled": base64.b64encode(_ai_prompt_compiled.encode()).decode() if _ai_prompt_compiled else "",
        },
    )


# ── Image-Guided Generation ───────────────────────────────────────────────────

# ── WD14 Tag Extraction ───────────────────────────────────────────────────────

@router.post("/art/wd14-tags", summary="WD14 圖像反推 Danbooru 標籤")
async def wd14_tags(
    file: Annotated[UploadFile, File(description="參考圖片 (JPEG/PNG)")],
    threshold: float = Form(0.35, ge=0.1, le=0.9, description="標籤信心門檻（預設 0.35）"),
):
    """
    透過 ComfyUI WD14Tagger 節點，從圖片反推 Danbooru 標籤。
    需要 ComfyUI 已安裝 WD14Tagger（pythongosssss/ComfyUI-Custom-Scripts 或相容節點）。
    """
    node_type = comfyui_client.detect_wd14_node()
    if not node_type:
        raise HTTPException(
            status_code=501,
            detail=(
                "ComfyUI 中找不到 WD14Tagger 節點。"
                " 請安裝：https://github.com/pythongosssss/ComfyUI-Custom-Scripts"
            ),
        )

    if not comfyui_client.is_available():
        raise HTTPException(status_code=503, detail="ComfyUI 未啟動")

    image_bytes = await file.read()
    uploaded_name = comfyui_client.upload_image_bytes(image_bytes, file.filename or "wd14_input.png")

    wf = {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": uploaded_name},
        },
        "2": {
            "class_type": node_type,
            "inputs": {
                "image": ["1", 0],
                "model": "wd-v1-4-moat-tagger-v2",
                "threshold": threshold,
                "character_threshold": threshold,
            },
        },
    }

    try:
        prompt_id = comfyui_client.submit_workflow(wf)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"WD14 workflow 提交失敗：{e}")

    try:
        texts = await run_in_threadpool(comfyui_client.wait_for_text_result, prompt_id, 90)
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))

    if not texts:
        raise HTTPException(status_code=500, detail="WD14 未回傳標籤，請確認節點設定")

    raw = texts[0]
    # Danbooru 用底線，轉空格以符合 ComfyUI prompt 慣例
    tags_list = [t.strip().replace("_", " ") for t in raw.split(",") if t.strip()]

    return {
        "tags": tags_list,
        "prompt": ", ".join(tags_list),
        "node_used": node_type,
        "threshold": threshold,
    }


# ── Image-Guided Generation ───────────────────────────────────────────────────

_IMG_GUIDE_MODES = ("i2i", "controlnet")


@router.post("/art/img-guide", summary="參考圖引導生成 (i2i / controlnet)")
async def img_guide(
    file: Annotated[UploadFile, File(description="參考圖片 (JPEG/PNG)")],
    prompt: str = Form(..., description="正向提示詞（英文，已編譯）"),
    negative_prompt: str = Form("", description="負向提示詞"),
    mode: str = Form("i2i", description="生成模式：i2i | controlnet"),
    denoise: float = Form(0.35, ge=0.05, le=0.95, description="去噪強度（i2i 模式）"),
    steps: int = Form(20, ge=5, le=60),
    seed: int = Form(-1),
    art_style_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    """
    i2i       — 以參考圖為底圖，denoise 0.05~0.95 控制保留程度（低=保留原圖，高=大幅改變）
    controlnet — 以參考圖約束構圖/姿勢，prompt 決定風格（使用 scribble ControlNet）
    """
    if mode not in _IMG_GUIDE_MODES:
        raise HTTPException(status_code=400, detail=f"mode 必須為 {_IMG_GUIDE_MODES}")

    image_bytes = await file.read()
    actual_seed = seed if seed >= 0 else random.randint(0, 2**31 - 1)

    art_style = db.get(ArtStyle, art_style_id) if art_style_id else None
    style = _resolve_style(art_style)
    default_neg = (art_style.negative if art_style and art_style.negative else STYLE_CONFIG[style].negative)
    neg = negative_prompt.strip() or default_neg

    extra = _extra_tags(art_style)
    pos = f"{prompt}, {extra}" if extra else prompt

    uploaded_name = comfyui_client.upload_image_bytes(image_bytes, file.filename or "ref.png")

    if mode == "i2i":
        wf = _load_workflow("image_to_image.json")
        _inject_loras(wf, art_style.loras if art_style else [])
        for node in wf.values():
            if not isinstance(node, dict):
                continue
            ct = node.get("class_type")
            inputs = node.get("inputs", {})
            if ct == "LoadImage":
                inputs["image"] = uploaded_name
            elif ct == "CLIPTextEncode":
                if inputs.get("text") == "__POSITIVE__":
                    inputs["text"] = pos
                elif inputs.get("text") == "__NEGATIVE__":
                    inputs["text"] = neg
            elif ct == "KSampler":
                inputs["seed"] = actual_seed
                inputs["steps"] = steps
                inputs["denoise"] = round(denoise, 2)

    else:  # controlnet
        wf = _load_workflow("sketch_to_reference.json")
        _inject_loras(wf, art_style.loras if art_style else [])
        img_w, img_h = _image_dimensions(image_bytes)
        _inject_controlnet_compose(wf, uploaded_name, pos, neg, actual_seed, img_w, img_h, steps)

    _replace_negative_seeds(wf, actual_seed)
    await guardian.request_focus("comfyui")
    image_out = await _run_comfyui(wf)

    hist_id = record_generation(
        db, endpoint="img_guide", seed=actual_seed, workflow=state.get_workflow(),
        style=style.value, positive=pos, negative=neg,
        params={"mode": mode, "denoise": denoise, "steps": steps, "art_style_id": art_style_id},
    )
    return Response(
        content=image_out,
        media_type="image/png",
        headers={
            "X-Seed": str(actual_seed),
            "X-Mode": mode,
            "X-Style": style.value,
            "X-Denoise": str(denoise),
            "X-History-Id": str(hist_id) if hist_id else "",
        },
    )


@router.post("/art/ipadapter", summary="IP-Adapter 外觀參考生成")
async def ipadapter(
    file: Annotated[UploadFile, File(description="角色外觀參考圖 (JPEG/PNG)")],
    prompt: str = Form(..., description="正向提示詞（英文，已編譯）"),
    negative_prompt: str = Form("", description="負向提示詞"),
    weight: float = Form(0.6, ge=0.1, le=1.5, description="IP-Adapter 強度"),
    width: int = Form(1024),
    height: int = Form(1024),
    steps: int = Form(20, ge=5, le=60),
    seed: int = Form(-1),
    art_style_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    """
    以參考圖萃取外觀特徵（角色臉部、髮型、服裝風格），
    結合文字 prompt 生成風格一致的插畫。
    weight: 0.1=微影響, 0.6=平衡, 1.0+=強參考
    """
    image_bytes = await file.read()
    actual_seed = seed if seed >= 0 else random.randint(0, 2**31 - 1)

    art_style = db.get(ArtStyle, art_style_id) if art_style_id else None
    style = _resolve_style(art_style, "ipadapter_txt2img.json")
    default_neg = (art_style.negative if art_style and art_style.negative else STYLE_CONFIG[style].negative)
    neg = negative_prompt.strip() or default_neg

    extra = _extra_tags(art_style)
    pos = f"{prompt}, {extra}" if extra else prompt

    uploaded_name = comfyui_client.upload_image_bytes(image_bytes, file.filename or "ref.png")

    wf = _load_workflow("ipadapter_txt2img.json")
    _inject_prompts(wf, pos, neg)

    for node in wf.values():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        inputs = node.get("inputs", {})
        if ct == "LoadImage":
            inputs["image"] = uploaded_name
        elif ct == "IPAdapterAdvanced":
            inputs["weight"] = round(weight, 2)
        elif ct == "EmptyLatentImage":
            inputs["width"] = width
            inputs["height"] = height
        elif ct == "KSampler":
            inputs["seed"] = actual_seed
            inputs["steps"] = steps

    _replace_negative_seeds(wf, actual_seed)
    await guardian.request_focus("comfyui")
    image_out = await _run_comfyui(wf)

    hist_id = record_generation(
        db, endpoint="ipadapter", seed=actual_seed, workflow="ipadapter_txt2img.json",
        style=style.value, positive=pos, negative=neg,
        params={"weight": weight, "steps": steps, "width": width, "height": height,
                "art_style_id": art_style_id},
    )
    return Response(
        content=image_out,
        media_type="image/png",
        headers={
            "X-Seed": str(actual_seed),
            "X-Style": style.value,
            "X-IPAdapter-Weight": str(weight),
            "X-History-Id": str(hist_id) if hist_id else "",
        },
    )
