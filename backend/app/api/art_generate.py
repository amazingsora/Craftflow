"""
ComfyUI image generation endpoints:
  POST /api/v1/art/compile-prompt  — 中文 → model-aware prompt (自動偵測 checkpoint style)
  POST /api/v1/art/lineart         — upload sketch → lineart PNG (ControlNet)
  POST /api/v1/art/generate        — text prompt → image PNG (SDXL txt2img)
  POST /api/v1/art/compose         — sketch + question → advice text + reference image (JSON)
"""
from __future__ import annotations

import base64
import json
import random
import time
from pathlib import Path
from typing import Annotated

import yaml
from fastapi import APIRouter, Form, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel

from app.services import comfyui_client
from app.services.ai import art_service
from app.services.ai.ollama_client import DEFAULT_VISION_MODEL, DEFAULT_TEXT_MODEL
from app.services.ai.prompt_engine import compile as compile_prompt, PromptStyle
from app.services.ai.prompt_engine.styles import STYLE_CONFIG

router = APIRouter(tags=["art-generate"])

_WORKFLOW_DIR = Path("/app/tools/Craftflow/diffusion/workflows")
if not _WORKFLOW_DIR.exists():
    _WORKFLOW_DIR = Path(__file__).resolve().parents[3] / "tools" / "Craftflow" / "diffusion" / "workflows"

# checkpoint_styles.yml — Docker path / local fallback
_STYLES_YML = Path("/app/backend/checkpoint_styles.yml")
if not _STYLES_YML.exists():
    _STYLES_YML = Path(__file__).resolve().parents[3] / "checkpoint_styles.yml"

print(f"DEBUG: workflow dir: {_WORKFLOW_DIR}", flush=True)
print(f"DEBUG: checkpoint styles: {_STYLES_YML}", flush=True)


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_workflow(name: str) -> dict:
    path = _WORKFLOW_DIR / name
    with open(path, encoding="utf-8") as f:
        wf = json.load(f)
    wf.pop("_comment", None)
    return wf


def _load_checkpoint_styles() -> dict:
    """Load checkpoint → style mapping from YAML. Returns {} on error."""
    try:
        with open(_STYLES_YML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("checkpoints", {})
    except Exception as e:
        print(f"WARN: Could not load checkpoint_styles.yml: {e}", flush=True)
        return {}


def _detect_style(workflow_name: str = "text_to_image.json") -> PromptStyle:
    """
    Read ckpt_name from a workflow's CheckpointLoaderSimple node,
    then look it up in checkpoint_styles.yml.
    Falls back to SDXL if not found.
    """
    mapping = _load_checkpoint_styles()
    try:
        wf = _load_workflow(workflow_name)
    except Exception:
        return PromptStyle.SDXL

    for node in wf.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") == "CheckpointLoaderSimple":
            ckpt = node.get("inputs", {}).get("ckpt_name", "")
            ckpt_base = Path(ckpt).stem.lower()
            for pattern, style_str in mapping.items():
                if pattern.lower() in ckpt_base:
                    print(f"DEBUG: checkpoint '{ckpt}' matched pattern '{pattern}' → style '{style_str}'", flush=True)
                    try:
                        return PromptStyle(style_str)
                    except ValueError:
                        pass
    print(f"DEBUG: checkpoint style not found in mapping, falling back to SDXL", flush=True)
    return PromptStyle.SDXL


def _run(workflow: dict) -> bytes:
    if not comfyui_client.is_available():
        raise HTTPException(
            status_code=503,
            detail="ComfyUI 未啟動，請先執行 ComfyUI (host.docker.internal:8188)。",
        )
    try:
        prompt_id = comfyui_client.submit_workflow(workflow)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"ComfyUI workflow 驗證失敗：{e}")
    try:
        filenames = comfyui_client.wait_for_result(prompt_id)
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    if not filenames:
        raise HTTPException(status_code=500, detail="ComfyUI 未回傳輸出圖片，請確認 workflow 設定。")
    return comfyui_client.download_image(filenames[0])


# ── endpoints ─────────────────────────────────────────────────────────────────

class CompilePromptRequest(BaseModel):
    prompt: str
    model: str = DEFAULT_TEXT_MODEL


@router.post("/art/compile-prompt", summary="AI 編譯提示詞 (中文 → 模型對應格式)")
def compile_prompt_endpoint(req: CompilePromptRequest):
    """
    Detect current checkpoint style from text_to_image.json,
    then compile Chinese description into the correct prompt format.

    Returns:
      positive  — compiled positive prompt (ready for ComfyUI)
      negative  — model-appropriate negative prompt
      style     — detected style (sdxl / pony / flux / ...)
    """
    style = _detect_style("text_to_image.json")
    print(f"DEBUG: Compiling for style={style}, model={req.model}, input={req.prompt!r}", flush=True)

    start = time.time()
    positive, negative = compile_prompt(req.prompt, style=style, model=req.model)
    print(f"DEBUG: compile took {time.time() - start:.2f}s → positive={positive!r}", flush=True)

    return {
        "positive": positive,
        "negative": negative,
        "style": style.value,
    }


# Keep old endpoint as alias for backward compatibility
@router.post("/art/optimize-prompt", summary="[deprecated] 請改用 /art/compile-prompt")
def optimize_prompt_compat(req: CompilePromptRequest):
    return compile_prompt_endpoint(req)


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

    return Response(content=_run(wf), media_type="image/png")


class GenerateRequest(BaseModel):
    prompt: str
    negative_prompt: str = ""   # 若為空，由偵測到的 style 自動填入
    width: int = 1024
    height: int = 1024
    steps: int = 20
    seed: int = -1


@router.post("/art/generate", summary="文字→圖片 (SDXL txt2img)")
def generate(req: GenerateRequest):
    """
    Generate an illustration from a text prompt via ComfyUI.
    If negative_prompt is empty, uses the model-appropriate preset.
    """
    style = _detect_style("text_to_image.json")
    negative = req.negative_prompt or STYLE_CONFIG[style]["negative"]
    seed = req.seed if req.seed >= 0 else random.randint(0, 2**31 - 1)

    wf = _load_workflow("text_to_image.json")
    for node in wf.values():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        inputs = node.get("inputs", {})
        if ct == "CLIPTextEncode":
            if inputs.get("text") == "__POSITIVE__":
                inputs["text"] = req.prompt
            elif inputs.get("text") == "__NEGATIVE__":
                inputs["text"] = negative
        elif ct == "EmptyLatentImage":
            inputs["width"] = req.width
            inputs["height"] = req.height
        elif ct == "KSampler":
            inputs["seed"] = seed
            inputs["steps"] = req.steps

    return Response(
        content=_run(wf),
        media_type="image/png",
        headers={
            "X-Seed": str(seed),
            "X-Style": style.value,
            "X-Steps": str(req.steps),
        },
    )


def _inject_txt2img(wf: dict, prompt: str, negative: str, seed: int, steps: int = 20) -> None:
    for node in wf.values():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        inputs = node.get("inputs", {})
        if ct == "CLIPTextEncode":
            if inputs.get("text") == "__POSITIVE__":
                inputs["text"] = prompt
            elif inputs.get("text") == "__NEGATIVE__":
                inputs["text"] = negative
        elif ct == "KSampler":
            inputs["seed"] = seed
            inputs["steps"] = steps


@router.post("/art/compose", summary="草圖問答 → 構圖意見 + 參考圖")
async def compose(
    file: Annotated[UploadFile, File(description="草稿圖片")],
    question: str = Form(..., description="針對草圖的構圖問題"),
    model: str = Form(DEFAULT_VISION_MODEL),
):
    start_total = time.time()
    image_bytes = await file.read()

    try:
        start_ollama = time.time()
        advice, sdxl_prompt = art_service.compose_ask(question, image_bytes, model=model)
        print(f"DEBUG: Ollama analysis took {time.time() - start_ollama:.2f}s", flush=True)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    start_comfy = time.time()
    seed = random.randint(0, 2**31 - 1)
    style = _detect_style("text_to_image.json")
    negative = STYLE_CONFIG[style]["negative"]
    wf = _load_workflow("text_to_image.json")
    _inject_txt2img(wf, sdxl_prompt, negative, seed)
    image_data = _run(wf)
    print(f"DEBUG: ComfyUI generation took {time.time() - start_comfy:.2f}s", flush=True)

    encoded_image = base64.b64encode(image_data).decode()
    print(f"DEBUG: Total compose took {time.time() - start_total:.2f}s", flush=True)

    return {
        "advice": advice,
        "suggested_prompt": sdxl_prompt,
        "image": encoded_image,
        "seed": seed,
        "style": style.value,
    }
