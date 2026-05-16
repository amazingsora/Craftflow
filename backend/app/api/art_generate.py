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
import logging
import random
import struct
from pathlib import Path
from typing import Annotated, Optional

import yaml
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import UPLOAD_DIR
from app.core.database import get_db
from app.models.character import Character
from app.services import comfyui_client
from app.services.ai import art_service, ollama_client as _oc
from app.services.ai.ollama_client import DEFAULT_VISION_MODEL, DEFAULT_TEXT_MODEL
from app.services.ai.prompt_engine import compile as compile_prompt, PromptStyle
from app.services.ai.prompt_engine.styles import STYLE_CONFIG
from app.services.ai.vram_manager import guardian

_PORTRAIT_DIR = UPLOAD_DIR / "portraits"

logger = logging.getLogger(__name__)

router = APIRouter(tags=["art-generate"])

_WORKFLOW_DIR = Path("/app/tools/Craftflow/diffusion/workflows")
if not _WORKFLOW_DIR.exists():
    _WORKFLOW_DIR = Path(__file__).resolve().parents[3] / "tools" / "Craftflow" / "diffusion" / "workflows"

# checkpoint_styles.yml — Docker path / local fallback
_STYLES_YML = Path("/app/backend/checkpoint_styles.yml")
if not _STYLES_YML.exists():
    _STYLES_YML = Path(__file__).resolve().parents[3] / "checkpoint_styles.yml"

logger.info("workflow dir: %s", _WORKFLOW_DIR)
logger.info("checkpoint styles: %s", _STYLES_YML)


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
        logger.warning("Could not load checkpoint_styles.yml: %s", e)
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
                    logger.debug("checkpoint '%s' matched pattern '%s' → style '%s'", ckpt, pattern, style_str)
                    try:
                        return PromptStyle(style_str)
                    except ValueError:
                        pass
    logger.debug("checkpoint style not found in mapping, falling back to SDXL")
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
async def compile_prompt_endpoint(req: CompilePromptRequest):
    """
    Detect current checkpoint style from text_to_image.json,
    then compile Chinese description into the correct prompt format.

    Returns:
      positive  — compiled positive prompt (ready for ComfyUI)
      negative  — model-appropriate negative prompt
      style     — detected style (sdxl / pony / flux / ...)
    """
    style = _detect_style("text_to_image.json")
    await guardian.request_focus("ollama")
    positive, negative = compile_prompt(req.prompt, style=style, model=req.model)
    return {
        "positive": positive,
        "negative": negative,
        "style": style.value,
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
    return Response(content=_run(wf), media_type="image/png")


class GenerateRequest(BaseModel):
    prompt: str
    negative_prompt: str = ""   # 若為空，由偵測到的 style 自動填入
    width: int = 1024
    height: int = 1024
    steps: int = 20
    seed: int = -1


@router.post("/art/generate", summary="文字→圖片 (SDXL txt2img)")
async def generate(req: GenerateRequest):
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

    await guardian.request_focus("comfyui")
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


def _inject_controlnet_compose(
    wf: dict, uploaded_name: str, prompt: str, negative: str, seed: int,
    width: int, height: int, steps: int = 20
) -> None:
    """Inject runtime values into sketch_to_reference.json workflow."""
    for node in wf.values():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        inputs = node.get("inputs", {})
        if ct == "LoadImage":
            inputs["image"] = uploaded_name
        elif ct == "CLIPTextEncode":
            if inputs.get("text") == "__POSITIVE__":
                inputs["text"] = prompt
            elif inputs.get("text") == "__NEGATIVE__":
                inputs["text"] = negative
        elif ct == "EmptyLatentImage":
            inputs["width"] = width
            inputs["height"] = height
        elif ct == "KSampler":
            inputs["seed"] = seed
            inputs["steps"] = steps


def _image_dimensions(image_bytes: bytes) -> tuple[int, int]:
    """Read width/height from PNG or JPEG bytes without external libs. Falls back to 1024x1024."""
    try:
        if image_bytes[:4] == b'\x89PNG':
            w = struct.unpack('>I', image_bytes[16:20])[0]
            h = struct.unpack('>I', image_bytes[20:24])[0]
            return _clamp_dim(w), _clamp_dim(h)
        if image_bytes[:2] == b'\xff\xd8':
            i = 2
            while i + 4 < len(image_bytes):
                if image_bytes[i] != 0xff:
                    break
                marker = image_bytes[i + 1]
                if marker in (0xc0, 0xc1, 0xc2):
                    h = struct.unpack('>H', image_bytes[i + 5:i + 7])[0]
                    w = struct.unpack('>H', image_bytes[i + 7:i + 9])[0]
                    return _clamp_dim(w), _clamp_dim(h)
                length = struct.unpack('>H', image_bytes[i + 2:i + 4])[0]
                i += 2 + length
    except Exception:
        pass
    return 1024, 1024


def _clamp_dim(v: int) -> int:
    """Round to nearest multiple of 64, clamped to [512, 2048] for SDXL."""
    v = max(512, min(2048, v))
    return (v // 64) * 64


@router.post("/art/compose", summary="草圖問答 → 構圖意見 + 參考圖")
async def compose(
    file: Annotated[UploadFile, File(description="草稿圖片")],
    question: str = Form(..., description="針對草圖的構圖問題"),
    model: str = Form(DEFAULT_VISION_MODEL),
):
    image_bytes = await file.read()
    width, height = _image_dimensions(image_bytes)

    await guardian.request_focus("ollama")
    try:
        advice, sdxl_prompt = art_service.compose_ask(question, image_bytes, model=model)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    seed = random.randint(0, 2**31 - 1)
    style = _detect_style("text_to_image.json")
    negative = STYLE_CONFIG[style]["negative"]

    # Sketch-style suffix: complete the figure, force monochrome lineart for consistent draft look
    _COMPOSE_SUFFIX = ", full body, complete character, all limbs visible, white background, monochrome, lineart, clean lines, no shading, no color"
    final_prompt = sdxl_prompt.rstrip(", ") + _COMPOSE_SUFFIX

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

    wf = _load_workflow("text_to_image.json")
    for node in wf.values():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        inputs = node.get("inputs", {})
        if ct == "CLIPTextEncode":
            if inputs.get("text") == "__POSITIVE__":
                inputs["text"] = final_prompt
            elif inputs.get("text") == "__NEGATIVE__":
                inputs["text"] = negative
        elif ct == "EmptyLatentImage":
            inputs["width"] = gen_w
            inputs["height"] = gen_h
        elif ct == "KSampler":
            inputs["seed"] = seed
    await guardian.request_focus("comfyui")
    image_data = _run(wf)

    encoded_image = base64.b64encode(image_data).decode()

    return {
        "advice": advice,
        "suggested_prompt": final_prompt,
        "image": encoded_image,
        "seed": seed,
        "style": style.value,
    }


# ── Character Design Sheet Generation ────────────────────────────────────────

_VISUAL_EXTRACT_PROMPT = """\
請用40字以內描述這張參考圖中角色的視覺外型。
只列出：髮色、髮型、眼睛顏色、主要服裝顏色與風格。
格式：逗號分隔的短語，使用中文，不要句子。"""

# expression id → (English SD tags for positive, Chinese label)
_EXPRESSION_MAP: dict[str, tuple[str, str]] = {
    "smile":   ("smiling, happy expression, gentle smile", "喜"),
    "angry":   ("angry expression, frowning, fierce glare", "怒"),
    "sad":     ("sad expression, teary eyes, sorrowful", "哀"),
    "joy":     ("laughing, joyful expression, excited, wide grin", "樂"),
    "neutral": ("neutral expression, calm, composed, expressionless", "平靜"),
}


@router.post("/characters/{character_id}/generate-design", summary="角色人設圖生成（ComfyUI）")
async def generate_character_design(
    character_id: int,
    expression: Optional[str] = None,  # None=full body; key from _EXPRESSION_MAP = bust shot
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

    is_expression = expression is not None
    expr_tags, _ = _EXPRESSION_MAP[expression] if is_expression else ("", "")

    # ── Build Chinese description ──────────────────────────────────────────
    parts = [f"角色名稱：{character.name}"]
    if character.age:
        parts.append(f"年齡：{character.age}歲")
    if character.core_traits:
        parts.append(f"外貌與個性：{character.core_traits}")

    # Visual traits from first concept image (30-60% influence)
    concept_imgs = list(character.concept_images or [])
    if not concept_imgs and character.portrait_path:
        concept_imgs = [character.portrait_path]

    if concept_imgs:
        img_path = _PORTRAIT_DIR / concept_imgs[0]
        if img_path.exists():
            await guardian.request_focus("ollama")
            visual = _oc.analyze_image(str(img_path), _VISUAL_EXTRACT_PROMPT, model=DEFAULT_VISION_MODEL)
            if visual and not visual.startswith("["):
                parts.append(f"視覺參考特徵：{visual}")

    # Background
    if character.color:
        parts.append(f"背景為{character.color}色調的純色特效背景，無場景細節")
    else:
        parts.append("簡單純色背景，無場景細節")

    if is_expression:
        parts.append("動漫插畫風格，角色臉部特寫半身圖")
    else:
        parts.append("人設圖，全身正面，動漫插畫風格，清晰展示角色外觀")

    raw_desc = "，".join(parts)

    # ── Compile character description ──────────────────────────────────────
    style = _detect_style("text_to_image.json")
    await guardian.request_focus("ollama")
    positive, negative = compile_prompt(raw_desc, style=style, model=DEFAULT_TEXT_MODEL)

    # ── Compile ai_prompt separately (placed first → higher SD attention weight) ──
    extra_prefix = ""
    if character.ai_prompt and character.ai_prompt.strip():
        await guardian.request_focus("ollama")
        extra_compiled, _ = compile_prompt(
            character.ai_prompt.strip(), style=style, model=DEFAULT_TEXT_MODEL
        )
        if extra_compiled:
            extra_prefix = extra_compiled + ", "

    # ── Build final prompt based on mode ──────────────────────────────────
    bg_tag = f", {character.color} background, color gradient background" if character.color else ", gradient background"

    if is_expression:
        suffix = (
            f", {expr_tags}"
            ", bust shot, upper body, close-up portrait, face focus"
            ", simple background, flat background" + bg_tag
        )
        width, height, steps = 512, 640, 20
    else:
        suffix = (
            ", character design sheet, character reference sheet"
            ", full body, front view"
            ", simple background, flat background, no background detail, no scenery" + bg_tag
        )
        width, height, steps = 768, 1024, 25

    # ai_prompt compiled tags lead the prompt for maximum enforcement
    final_positive = extra_prefix + positive + suffix

    extra_neg = "detailed background, complex background, scenery, landscape, buildings, environment"
    final_negative = f"{negative}, {extra_neg}" if negative else extra_neg

    # ── Generate ──────────────────────────────────────────────────────────
    seed = random.randint(0, 2**31 - 1)
    wf = _load_workflow("text_to_image.json")
    for node in wf.values():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        inputs = node.get("inputs", {})
        if ct == "CLIPTextEncode":
            if inputs.get("text") == "__POSITIVE__":
                inputs["text"] = final_positive
            elif inputs.get("text") == "__NEGATIVE__":
                inputs["text"] = final_negative
        elif ct == "EmptyLatentImage":
            inputs["width"] = width
            inputs["height"] = height
        elif ct == "KSampler":
            inputs["seed"] = seed
            inputs["steps"] = steps

    await guardian.request_focus("comfyui")
    return Response(
        content=_run(wf),
        media_type="image/png",
        headers={
            "X-Seed": str(seed),
            "X-Style": style.value,
            "X-Prompt": base64.b64encode(final_positive.encode()).decode()  # Encode to avoid header char issues
        },
    )
