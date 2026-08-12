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
import logging
import random
import time
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core import state
from app.core.database import get_db
from app.models.art_style import ArtStyle
from app.services import comfyui_client
from app.services.ai import art_service
from app.services.ai.prompt_engine import compile as compile_prompt
from app.services.ai.prompt_engine.styles import STYLE_CONFIG
from app.services.ai.vram_manager import guardian
from app.services.ai.generation_recorder import record_generation
from app.services.ai import generation_jobs
from app.services.ai import character_design_service
from app.services.ai import image_edit_service
from app.services.ai.capability import resolve_capability, resolve_checkpoint_for_workflow
from app.schemas.art_generate import (
    CompilePromptRequest,
    GenerateRequest,
    GenerateAsyncRequest,
)
from app.services.ai.workflow_builder import (
    _build_txt2img,
    _style_prompts,
    _compile_overrides,
    _detect_style,
    _extra_tags,
    _inject_loras,
    _load_workflow,
    _replace_negative_seeds,
    _resolve_style,
    _run_comfyui,
)
from app.services.ai.image_ops import (
    _clamp_dim,
    _image_dimensions,
    _letterbox_to_aspect,
)
from app.services.ai.wf_node_ops import (
    _CN_APPLY_TYPES,
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


logger = logging.getLogger(__name__)

router = APIRouter(tags=["art-generate"])


def _current_capability(wf_name: str | None = None) -> dict:
    """B5 守門用：取得目前 checkpoint + workflow 的能力。

    wf_name 預設使用 state.get_workflow()；caller 可傳入實際要用的 workflow 名稱。
    若 workflow 無法載入（檔案不存在）則以空 dict 計算，僅依家族查表。
    """
    # 2026-07-25 AC-2'：checkpoint 改由工作流內嵌值解析（CheckpointLoaderSimple →
    # UNETLoader.unet_name → 全域），與 gen_profile 走同一函式，避免 UI 與生成端
    # 對同一工作流解析出不同 family。
    name = wf_name or state.get_workflow()
    ckpt = resolve_checkpoint_for_workflow(name)
    try:
        wf = _load_workflow(name)
    except Exception:
        wf = {}
    return resolve_capability(wf, ckpt)


# ── endpoints ─────────────────────────────────────────────────────────────────

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
    # B5 能力守門：前端隱藏選項時不應送旗標，但後端雙重確認，避免家族不支援時意外注入
    _cap = _current_capability()
    if not _cap["ipa_supported"]:
        use_sketch_as_ref = False
        character_ref = None
    if not _cap["cn_supported"]:
        use_cn = False

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
            _inject_ipa_cn_nodes(wf, inject_ipa=False, inject_cn=True, models=_cap["models"])
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
            _inject_ipa_cn_nodes(wf, inject_ipa=False, inject_cn=True, models=_cap["models"])
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


# ── Character Design Sheet Generation(主流程已下沉 character_design_service,A1 Step 3)──

@router.post("/characters/{character_id}/generate-design", summary="角色人設圖生成(ComfyUI)")
async def generate_character_design(
    character_id: int,
    expression: Optional[str] = None,
    art_style_id: Optional[int] = None,
    use_ai_prompt: bool = True,
    use_outfit: bool = True,
    use_vision: bool = True,
    use_ipa: bool = True,
    ipa_weight: float = 0.6,
    use_controlnet: bool = True,
    cn_weight: float = 0.85,
    db: Session = Depends(get_db),
):
    """主流程見 services/ai/character_design_service.py。"""
    # B5 能力守門
    _cap = _current_capability()
    if not _cap["ipa_supported"]:
        use_ipa = False
    # 2026-08-05 D'-2 補洞：家族不支援 CN 但有替代路徑（Anima → img2img）時不可打成 False，
    # 否則 service 的 cn_fallback 分支永遠進不去（前端 cnUsable 已同此判斷，後端漏改）。
    if not _cap["cn_supported"] and not _cap.get("cn_fallback"):
        use_controlnet = False
    return await character_design_service.generate_character_design(
        character_id=character_id, expression=expression, art_style_id=art_style_id,
        use_ai_prompt=use_ai_prompt, use_outfit=use_outfit, use_vision=use_vision,
        use_ipa=use_ipa, ipa_weight=ipa_weight,
        use_controlnet=use_controlnet, cn_weight=cn_weight, db=db,
    )


@router.post("/characters/{character_id}/variants/{slot}/generate-design", summary="角色變體人設圖生成(ComfyUI)")
async def generate_variant_design(
    character_id: int,
    slot: int,
    expression: Optional[str] = None,
    art_style_id: Optional[int] = None,
    use_ai_prompt: bool = True,
    use_outfit: bool = True,
    use_vision: bool = True,
    use_ipa: bool = True,
    ipa_weight: float = 0.6,
    use_controlnet: bool = True,
    cn_weight: float = 0.85,
    db: Session = Depends(get_db),
):
    """主流程見 services/ai/character_design_service.py。"""
    # B5 能力守門
    _cap = _current_capability()
    if not _cap["ipa_supported"]:
        use_ipa = False
    # 2026-08-05 D'-2 補洞：家族不支援 CN 但有替代路徑（Anima → img2img）時不可打成 False，
    # 否則 service 的 cn_fallback 分支永遠進不去（前端 cnUsable 已同此判斷，後端漏改）。
    if not _cap["cn_supported"] and not _cap.get("cn_fallback"):
        use_controlnet = False
    return await character_design_service.generate_variant_design(
        character_id=character_id, slot=slot, expression=expression, art_style_id=art_style_id,
        use_ai_prompt=use_ai_prompt, use_outfit=use_outfit, use_vision=use_vision,
        use_ipa=use_ipa, ipa_weight=ipa_weight,
        use_controlnet=use_controlnet, cn_weight=cn_weight, db=db,
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
