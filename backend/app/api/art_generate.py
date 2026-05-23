"""
ComfyUI image generation endpoints:
  POST /api/v1/art/compile-prompt  — 中文 → model-aware prompt (自動偵測 checkpoint style)
  POST /api/v1/art/lineart         — upload sketch → lineart PNG (ControlNet)
  POST /api/v1/art/generate        — text prompt → image PNG (SDXL txt2img)
  POST /api/v1/art/compose         — sketch + question → advice text + reference image (JSON)
  POST /api/v1/art/img-guide       — reference image + prompt → image (i2i / controlnet modes)
"""
from __future__ import annotations

import base64
import colorsys
import io
import json
import logging
import random
import statistics
import struct
import time
from pathlib import Path
from typing import Annotated, Optional

from PIL import Image

import yaml
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import UPLOAD_DIR, CUSTOM_WORKFLOWS_DIR
from app.core import state
from app.core.database import get_db
from app.models.art_style import ArtStyle
from app.models.character import Character
from app.services import comfyui_client
from app.services.ai import art_service, ollama_client as _oc
from app.services.ai.prompt_engine import compile as compile_prompt, PromptStyle
from app.services.ai.prompt_engine.styles import STYLE_CONFIG
from app.services.ai.vram_manager import guardian

_PORTRAIT_DIR = UPLOAD_DIR / "portraits"

logger = logging.getLogger(__name__)

router = APIRouter(tags=["art-generate"])

_SYSTEM_WORKFLOW_DIR = Path("/app/tools/Craftflow/diffusion/workflows")
if not _SYSTEM_WORKFLOW_DIR.exists():
    _SYSTEM_WORKFLOW_DIR = Path(__file__).resolve().parents[3] / "tools" / "Craftflow" / "diffusion" / "workflows"

# checkpoint_styles.yml — Docker path / local fallback
_STYLES_YML = Path("/app/backend/checkpoint_styles.yml")
if not _STYLES_YML.exists():
    _STYLES_YML = Path(__file__).resolve().parents[2] / "checkpoint_styles.yml"

logger.info("system workflow dir: %s", _SYSTEM_WORKFLOW_DIR)
logger.info("checkpoint styles: %s", _STYLES_YML)


# ── Art Style helpers ─────────────────────────────────────────────────────────

def _resolve_style(art_style: Optional[ArtStyle], workflow: str = "text_to_image.json") -> PromptStyle:
    """Return effective PromptStyle: art_style.base_style > checkpoint detection."""
    if art_style and art_style.base_style:
        try:
            return PromptStyle(art_style.base_style)
        except ValueError:
            pass
    return _detect_style(workflow)


def _compile_overrides(art_style: Optional[ArtStyle]) -> dict:
    """Return kwargs to pass into compile_prompt() for art_style overrides."""
    if not art_style:
        return {}
    return {
        "quality_prefix_override": art_style.quality_prefix or None,
        "negative_override": art_style.negative or None,
    }


def _extra_tags(art_style: Optional[ArtStyle]) -> str:
    return (art_style.extra_tags or "").strip() if art_style else ""


def _inject_loras(wf: dict, loras: list) -> None:
    """Insert a LoraLoader chain into the workflow (mutates wf in place).

    Finds CheckpointLoaderSimple as the chain root, then rewires KSampler.model
    and all CLIPTextEncode.clip to point to the last LoRA node output.
    Empty model names are silently skipped.
    """
    valid = [l for l in (loras or []) if isinstance(l, dict) and l.get("model", "").strip()]
    if not valid:
        return

    ckpt_id = next(
        (nid for nid, n in wf.items()
         if isinstance(n, dict) and n.get("class_type") == "CheckpointLoaderSimple"),
        None,
    )
    if ckpt_id is None:
        logger.warning("[lora] CheckpointLoaderSimple not found — skipping LoRA injection")
        return

    prev_id = ckpt_id
    for i, lora in enumerate(valid):
        node_id = f"_lora_{i}"
        weight = float(lora.get("weight", 0.8))
        wf[node_id] = {
            "class_type": "LoraLoader",
            "inputs": {
                "model": [prev_id, 0],
                "clip": [prev_id, 1],
                "lora_name": lora["model"].strip(),
                "strength_model": weight,
                "strength_clip": weight,
            },
        }
        logger.debug("[lora] injected %s (weight=%.2f)", lora["model"], weight)
        prev_id = node_id

    # Rewire KSampler.model and CLIPTextEncode.clip to the last LoRA node
    for node in wf.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        ct = node.get("class_type")
        if ct == "KSampler":
            if isinstance(inputs.get("model"), list) and inputs["model"][0] == ckpt_id:
                inputs["model"] = [prev_id, 0]
        elif ct == "IPAdapterAdvanced":
            if isinstance(inputs.get("model"), list) and inputs["model"][0] == ckpt_id:
                inputs["model"] = [prev_id, 0]
        elif ct == "CLIPTextEncode":
            if isinstance(inputs.get("clip"), list) and inputs["clip"][0] == ckpt_id:
                inputs["clip"] = [prev_id, 1]


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_workflow(name: str) -> dict:
    # 先找使用者自訂目錄，找不到再找系統目錄
    for base in (CUSTOM_WORKFLOWS_DIR, _SYSTEM_WORKFLOW_DIR):
        path = base / name
        if path.exists():
            break
    else:
        raise FileNotFoundError(f"Workflow '{name}' not found in custom or system directories")
    with open(path, encoding="utf-8") as f:
        wf = json.load(f)
    wf.pop("_comment", None)
    ckpt = state.get_checkpoint()
    if ckpt:
        for node in wf.values():
            if isinstance(node, dict) and node.get("class_type") == "CheckpointLoaderSimple":
                node["inputs"]["ckpt_name"] = ckpt
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
    return Response(content=_run(wf), media_type="image/png")


class GenerateRequest(BaseModel):
    prompt: str
    negative_prompt: str = ""   # 若為空，由偵測到的 style 或 art_style 自動填入
    width: int = 1024
    height: int = 1024
    steps: int = 20
    seed: int = -1
    art_style_id: Optional[int] = None


@router.post("/art/generate", summary="文字→圖片 (SDXL txt2img)")
async def generate(req: GenerateRequest, db: Session = Depends(get_db)):
    """
    Generate an illustration from a text prompt via ComfyUI.
    If negative_prompt is empty, uses the model-appropriate preset (or art_style override).
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
            "X-Workflow": state.get_workflow(),
        },
    )


def _inject_prompts(wf: dict, positive: str, negative: str) -> None:
    """Inject positive/negative prompts into CLIPTextEncode nodes.

    Priority:
      1. __POSITIVE__ / __NEGATIVE__ placeholder text (system workflows)
      2. _meta.title containing "positive" / "negative" (user workflows with titles)
      3. First two CLIPTextEncode nodes by node-id order (fallback)
    """
    clips = {
        nid: node for nid, node in wf.items()
        if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode"
    }
    if not clips:
        return

    # Pass 1: placeholder text
    pos_injected = neg_injected = False
    for node in clips.values():
        text = node["inputs"].get("text", "")
        if text == "__POSITIVE__":
            node["inputs"]["text"] = positive
            pos_injected = True
        elif text == "__NEGATIVE__":
            node["inputs"]["text"] = negative
            neg_injected = True
    if pos_injected or neg_injected:
        return

    # Pass 2: _meta.title keywords
    for node in clips.values():
        title = (node.get("_meta") or {}).get("title", "").lower()
        if not pos_injected and "positive" in title:
            node["inputs"]["text"] = positive
            pos_injected = True
        elif not neg_injected and "negative" in title:
            node["inputs"]["text"] = negative
            neg_injected = True
    if pos_injected or neg_injected:
        return

    # Pass 3: first two nodes by sorted id
    sorted_ids = sorted(clips.keys(), key=lambda x: int(x) if x.isdigit() else 0)
    if sorted_ids:
        clips[sorted_ids[0]]["inputs"]["text"] = positive
    if len(sorted_ids) > 1:
        clips[sorted_ids[1]]["inputs"]["text"] = negative


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


_FLAT_COLOR_STD_THRESHOLD = 25.0  # max per-channel std to be considered a flat-color draft


def _is_flat_color_draft(image_bytes: bytes) -> bool:
    """
    Returns True when the image is a single-color fill with no meaningful content.
    Uses per-channel std-deviation on a 32×32 thumbnail; a purely flat canvas has
    std ≈ 0, a fully colored character illustration typically exceeds 40.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((32, 32))
        pixels = list(img.getdata())
        channel_stds = [statistics.stdev(p[c] for p in pixels) for c in range(3)]
        return max(channel_stds) < _FLAT_COLOR_STD_THRESHOLD
    except Exception:
        return False


@router.post("/art/compose", summary="草圖問答 → 構圖意見 + 參考圖")
async def compose(
    file: Annotated[UploadFile, File(description="草稿圖片")],
    question: str = Form(..., description="針對草圖的構圖問題"),
    model: str = Form(""),
    character_ref: Optional[UploadFile] = File(None, description="角色外觀參考圖（隱藏備用）"),
    ipa_weight: float = Form(0.6, ge=0.1, le=1.5, description="IP-Adapter 強度"),
    use_sketch_as_ref: bool = Form(False, description="以草圖本身作為 IP-Adapter 參考"),
):
    image_bytes = await file.read()
    width, height = _image_dimensions(image_bytes)
    effective_model = model.strip() or state.get_vision_model()

    await guardian.request_focus("ollama")
    try:
        advice, sdxl_prompt = art_service.compose_ask(question, image_bytes, model=effective_model)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    seed = random.randint(0, 2**31 - 1)
    style = _detect_style("text_to_image.json")
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

    if use_sketch_as_ref or character_ref is not None:
        # IP-Adapter 模式：以草圖（或外部參考圖）作為外觀基準
        if character_ref is not None:
            ref_bytes = await character_ref.read()
            ref_filename = character_ref.filename or "char_ref.png"
        else:
            ref_bytes = image_bytes  # 草圖本身作為參考
            ref_filename = "sketch_ref.png"
        uploaded_ref = comfyui_client.upload_image_bytes(ref_bytes, ref_filename)
        final_prompt = sdxl_prompt.rstrip(", ") + ", full body, complete character, all limbs visible"
        wf = _load_workflow("ipadapter_txt2img.json")
        _inject_prompts(wf, final_prompt, negative)
        for node in wf.values():
            if not isinstance(node, dict):
                continue
            ct = node.get("class_type")
            inputs = node.get("inputs", {})
            if ct == "LoadImage":
                inputs["image"] = uploaded_ref
            elif ct == "IPAdapterAdvanced":
                inputs["weight"] = round(ipa_weight, 2)
            elif ct == "EmptyLatentImage":
                inputs["width"] = gen_w
                inputs["height"] = gen_h
            elif ct == "KSampler":
                inputs["seed"] = seed
    else:
        # 原本的 txt2img 模式（線稿風）
        final_prompt = sdxl_prompt.rstrip(", ") + ", full body, complete character, all limbs visible, white background, monochrome, lineart, clean lines, no shading, no color"
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


def _age_gender_tag(gender: str | None, age: int | None) -> str:
    """
    Return the primary SD subject tag(s) based on gender + age.
    Placed at the very front of the positive prompt to anchor subject count.
    Returns empty string when gender is unset.
    """
    if gender == "female":
        base = "1girl" if (age is None or age < 25) else "1woman"
        suffix = ", mature female" if age is not None and age >= 40 else ""
        return base + suffix
    if gender == "male":
        base = "1boy" if (age is None or age < 25) else "1man"
        suffix = ", mature male" if age is not None and age >= 40 else ""
        return base + suffix
    if gender == "neutral":
        return "androgynous"
    return ""


def _age_body_tags(age: int | None) -> str:
    """Convert character age to SD body proportion tags."""
    if age is None:
        return ""
    if age <= 6:
        return "toddler, very young, chubby cheeks, round face"
    if age <= 11:
        return "young, childlike features, round face, flat chest, small hands"
    if age <= 14:
        return "young, youthful, flat chest"
    if age <= 17:
        return "teenage, youthful"
    return ""


def _height_body_tags(height: int | None) -> str:
    """Convert character height (cm) to SD stature tags."""
    if height is None:
        return ""
    if height < 130:
        return "very short stature, tiny, small figure"
    if height < 150:
        return "short stature, petite"
    if height < 160:
        return "petite"
    if height < 170:
        return ""
    if height < 180:
        return "tall, long legs"
    return "very tall, long legs"


def _visual_extract_prompt(n: int) -> str:
    """Return a vision prompt tuned for single or multi-image analysis."""
    ignore_bg = (
        "【重要警告】這是一張草稿或帶有單色背景的參考圖。請完全忽略背景顏色（例如：如果背景是純粉色，請勿將其判定為衣服或髮色）。"
        "背景不屬於角色特徵。請只觀察「角色線條內」的特徵。"
    )
    if n == 1:
        return (
            f"{ignore_bg}\n"
            "請仔細觀察這張角色參考圖，描述以下視覺特徵：\n"
            "① 髮色與髮型（顏色、長度、形狀，請根據角色本身的髮色判斷）"
            "② 眼睛顏色"
            "③ 膚色"
            "④ 體型輪廓（高挑/嬌小、胖瘦）"
            "⑤ 服裝主要顏色與風格（僅描述角色穿著的部分，無視背景）"
            "⑥ 明顯特殊特徵（獸耳、印記、武器等）\n"
            "格式：逗號分隔的中文短語，不加標號，不寫句子，控制在70字以內。"
        )
    return (
        f"{ignore_bg}\n"
        f"你收到了 {n} 張同一角色的不同參考圖。"
        "請綜合比較所有圖片，找出在多張圖中一致出現的視覺特徵：\n"
        "① 髮色與髮型"
        "② 眼睛顏色"
        "③ 膚色"
        "④ 體型輪廓"
        "⑤ 服裝主要顏色與風格"
        "⑥ 各圖均出現的特殊特徵\n"
        "以共同特徵為主，忽略只在單張圖出現的細節。"
        "格式：逗號分隔的中文短語，不加標號，不寫句子，控制在90字以內。"
    )

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
    art_style_id: Optional[int] = None,
    use_ai_prompt: bool = True,
    use_outfit: bool = True,
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

    _ipa_ref_bytes: bytes | None = None  # first non-flat concept image for IP-Adapter

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

        # Pick first non-flat image as IP-Adapter visual anchor
        if not all_flat:
            for _img in valid_images:
                if not _is_flat_color_draft(_img):
                    _ipa_ref_bytes = _img
                    break

        if valid_images:
            t0 = time.perf_counter()
            await guardian.request_focus("ollama")
            prompt_txt = _visual_extract_prompt(len(valid_images))
            visual = _oc.analyze_multi_images_bytes(
                valid_images, prompt_txt, model=state.get_vision_model(),
                options={"num_predict": 160, "temperature": 0.1},
            )
            timings["vision_extract"] = round(time.perf_counter() - t0, 1)
            logger.debug("visual extract (%d imgs): %s", len(valid_images), visual)
            if visual and not visual.startswith("["):
                label = "視覺參考特徵（多圖共同特徵）" if len(valid_images) > 1 else "視覺參考特徵（僅供風格參考）"
                parts.append(f"{label}：{visual}")
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
        suffix = (
            ", character design sheet, character reference sheet"
            ", full body, front view"
            ", simple background, flat background, no background detail, no scenery" + bg_tag
        )
        width, height, steps = 768, 1024, 25

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

    # art_style extra_tags appended after character tags
    style_extra = _extra_tags(art_style)
    style_extra_str = f", {style_extra}" if style_extra else ""

    # ai_prompt compiled tags lead the prompt for maximum enforcement
    final_positive = gender_prefix + body_prefix + extra_prefix + positive + suffix + gender_pos_extra + style_extra_str

    extra_neg = "detailed background, complex background, scenery, landscape, buildings, environment"
    final_negative = f"{negative}, {extra_neg}{gender_neg_extra}" if negative else f"{extra_neg}{gender_neg_extra}"

    # ── Generate ──────────────────────────────────────────────────────────
    seed = random.randint(0, 2**31 - 1)
    ipa_used = False
    if _ipa_ref_bytes is not None:
        uploaded_ref = comfyui_client.upload_image_bytes(_ipa_ref_bytes, "char_concept_ref.png")
        wf = _load_workflow("ipadapter_txt2img.json")
        ipa_used = True
    else:
        wf = _load_workflow("text_to_image.json")
    _inject_loras(wf, art_style.loras if art_style else [])
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
        elif ct == "LoadImage" and ipa_used:
            inputs["image"] = uploaded_ref

    t0 = time.perf_counter()
    await guardian.request_focus("comfyui")
    image_bytes = _run(wf)
    timings["comfyui"] = round(time.perf_counter() - t0, 1)
    timings["total"] = round(time.perf_counter() - t_total, 1)

    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={
            "X-Seed": str(seed),
            "X-Style": style.value,
            "X-Flat-Draft": "1" if all_flat else "0",
            "X-IPA-Used": "1" if ipa_used else "0",
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
    _ipa_ref_bytes: bytes | None = None  # first non-flat concept image for IP-Adapter
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
            if not all_flat:
                for _img in valid_images:
                    if not _is_flat_color_draft(_img):
                        _ipa_ref_bytes = _img
                        break
            t0 = time.perf_counter()
            await guardian.request_focus("ollama")
            prompt_txt = _visual_extract_prompt(len(valid_images))
            visual = _oc.analyze_multi_images_bytes(
                valid_images, prompt_txt, model=state.get_vision_model(),
                options={"num_predict": 160, "temperature": 0.1},
            )
            timings["vision_extract"] = round(time.perf_counter() - t0, 1)
            if visual and not visual.startswith("["):
                label = "視覺參考特徵（多圖共同特徵）" if len(valid_images) > 1 else "視覺參考特徵（僅供風格參考）"
                parts.append(f"{label}：{visual}")

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
        suffix = (
            ", character design sheet, character reference sheet, full body, front view"
            ", simple background, flat background, no background detail, no scenery" + bg_tag
        )
        width, height, steps = 768, 1024, 25

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
    style_extra_str = f", {style_extra}" if style_extra else ""

    final_positive = gender_prefix + body_prefix + extra_prefix + positive + suffix + gender_pos_extra + style_extra_str
    extra_neg = "detailed background, complex background, scenery, landscape, buildings, environment"
    final_negative = f"{negative}, {extra_neg}{gender_neg_extra}" if negative else f"{extra_neg}{gender_neg_extra}"

    # ── Generate ──────────────────────────────────────────────────────────
    seed = random.randint(0, 2**31 - 1)
    ipa_used = False
    if _ipa_ref_bytes is not None:
        uploaded_ref = comfyui_client.upload_image_bytes(_ipa_ref_bytes, "char_concept_ref.png")
        wf = _load_workflow("ipadapter_txt2img.json")
        ipa_used = True
    else:
        wf = _load_workflow("text_to_image.json")
    _inject_loras(wf, art_style.loras if art_style else [])
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
        elif ct == "LoadImage" and ipa_used:
            inputs["image"] = uploaded_ref

    t0 = time.perf_counter()
    await guardian.request_focus("comfyui")
    image_bytes = _run(wf)
    timings["comfyui"] = round(time.perf_counter() - t0, 1)
    timings["total"] = round(time.perf_counter() - t_total, 1)

    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={
            "X-Seed": str(seed),
            "X-Style": style.value,
            "X-Flat-Draft": "1" if all_flat else "0",
            "X-IPA-Used": "1" if ipa_used else "0",
            "X-Raw-Desc": base64.b64encode(raw_desc.encode()).decode(),
            "X-Prompt": base64.b64encode(final_positive.encode()).decode(),
            "X-Timings": base64.b64encode(json.dumps(timings).encode()).decode(),
            "X-AI-Prompt-Compiled": base64.b64encode(_ai_prompt_compiled.encode()).decode() if _ai_prompt_compiled else "",
        },
    )


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

    await guardian.request_focus("comfyui")
    image_out = _run(wf)

    return Response(
        content=image_out,
        media_type="image/png",
        headers={
            "X-Seed": str(actual_seed),
            "X-Mode": mode,
            "X-Style": style.value,
            "X-Denoise": str(denoise),
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

    await guardian.request_focus("comfyui")
    image_out = _run(wf)

    return Response(
        content=image_out,
        media_type="image/png",
        headers={
            "X-Seed": str(actual_seed),
            "X-Style": style.value,
            "X-IPAdapter-Weight": str(weight),
        },
    )
