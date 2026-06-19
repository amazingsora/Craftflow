"""角色人設圖 / 變體人設圖生成主流程。

自 api/art_generate.py 下沉(2026-06-13 A1 Step 3,逐字搬移零邏輯變更)。
兩主流程相似度 ~65% 但 IPA/CN 權重規則有分歧——本步只搬不去重(P7 另開)。
_get_variants/_slot_index 於 2026-06-13(項2)抽至 services/ai/variant_helpers，本模組與 api/characters 共同 import。
"""
from __future__ import annotations

import base64
import colorsys
import io
import json
import logging
import os
import random
import time
from typing import Optional
from dataclasses import dataclass

from PIL import Image, ImageDraw

from fastapi import Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

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
from app.services.ai.prompt_engine import compile as compile_prompt
from app.services.ai.vram_manager import guardian
from app.services.ai.generation_recorder import record_generation
from app.services.ai.workflow_builder import (
    _compile_overrides,
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
    _FULLBODY_NEG_TAGS,
    _FULLBODY_POS_TAGS,
    _border_color,
    _fullbody_canvas,
    _is_flat_color_draft,
    _letterbox_to_aspect,
    _pixel_coverage_check,
    _shrink_for_full_body,
)
from app.services.ai.capability import resolve_capability
from app.services.ai.wf_node_ops import (
    _CN_APPLY_TYPES,
    _bypass_controlnet_nodes,
    _bypass_ipa_nodes,
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
from app.services.ai.variant_helpers import _get_variants, _slot_index

_PORTRAIT_DIR = UPLOAD_DIR / "portraits"

logger = logging.getLogger(__name__)

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


# CN weight 上限（None = 不設限，沿用使用者滑桿值）
# partial/bust：概念圖為半身，下半身需由 SDXL 在留白區腦補。CN 過強會把「下半留空」
# 也當成硬約束 → 腿生不出來（實測 0.50 可完整補腿、≥0.70 失敗）。故對需腦補下半的
# coverage 設上限，cn_weight = min(滑桿值, 上限)，保證任何滑桿值都能補出全身。
# bust 露出較少、需腦補更多 → 上限比 partial 再低。
_COVERAGE_CN_WEIGHT: dict[str, float | None] = {
    "full":    None,
    "partial": 0.6,
    "bust":    0.5,
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
_CANVAS_EXPAND_SDXL_WF = "canvas_expand_sdxl.json"   # 方案3：SDXL inpaint 外擴（重用主生成 checkpoint，免載 Flux）
# 方案3（pre-ref 外擴）預設關閉 → 走穩定的方案1（CN 夾 0.5 單段 SDXL）。
# 設環境變數 CRAFTFLOW_PRE_REF_EXPAND=1 才啟用（實驗性，高貼合但較慢、偶有破圖風險）。
_PRE_REF_ENABLED = os.getenv("CRAFTFLOW_PRE_REF_EXPAND", "1").strip() == "1"


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


async def _run_canvas_expand_sdxl(
    sketch_bytes: bytes,
    coverage: str,
    positive: str,
    negative: str,
    width: int,
    height: int,
    seed: int,
    ckpt_name: str | None,
) -> bytes:
    """方案3：用 SDXL inpaint 外擴（取代 Flux,免載大模型）。

    概念圖置於畫布上半、下半留白為 mask → VAEEncodeForInpaint + denoise=1 補下半身。
    checkpoint 設為主生成同一顆 → 不換模型。用主 seed（非固定）→ 重生可換姿勢、不鎖死。
    外擴 prompt 強制 solo/full body/simple background 並抑制 reference-sheet，避免破圖/inset。
    """
    # 外擴專用 prompt：聚焦單人全身、簡單背景；抑制 reference sheet/多視圖/inset（破圖主因）
    expand_pos = (
        "solo, full body, standing, straight legs, normal body proportions, "
        "anatomically correct, simple background, " + positive
    )
    expand_neg = (
        negative
        + ", reference sheet, character sheet, multiple views, multiple poses, "
          "inset, split image, border, frame, cropped, disconnected body, "
          "long legs, elongated body, wide stance, spread legs, disproportionate"
    )
    canvas_bytes, mask_bytes = _create_inpaint_canvas_and_mask(
        sketch_bytes, width, height, coverage
    )
    canvas_fn = comfyui_client.upload_image_bytes(canvas_bytes, "canvas_expand_sdxl_input.png")
    mask_fn = comfyui_client.upload_image_bytes(mask_bytes, "canvas_expand_sdxl_mask.png")

    wf = _load_workflow(_CANVAS_EXPAND_SDXL_WF)
    for nid, node in wf.items():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        inputs = node.get("inputs", {})
        if ct == "CheckpointLoaderSimple" and ckpt_name:
            inputs["ckpt_name"] = ckpt_name
        elif ct == "LoadImage" and inputs.get("image") == "":
            inputs["image"] = canvas_fn
        elif ct == "LoadImageMask" and inputs.get("image") == "":
            inputs["image"] = mask_fn
        elif ct == "CLIPTextEncode":
            inputs["text"] = expand_neg if "Negative" in node.get("_meta", {}).get("title", "") else expand_pos
        elif ct == "KSampler":
            inputs["seed"] = seed

    _log_wf_snapshot(wf, label="canvas-expand-sdxl")
    await guardian.request_focus("comfyui")
    try:
        return await _run_comfyui(wf)
    except Exception as e:
        logger.error("[canvas-expand-sdxl] ComfyUI 執行失敗: %s: %s", type(e).__name__, e)
        raise


@dataclass
class _DesignInputs:
    """正規化的設計輸入：角色版取自 character 模型欄位，變體版取自 variant slot dict。"""
    name: str
    concept_imgs: list
    outfit: Optional[str]
    core_traits: Optional[str]
    color: Optional[str]
    gender: Optional[str]
    age: Optional[int]
    ai_prompt: Optional[str]
    height: Optional[int]


async def _generate_design_core(
    *,
    character: Character,
    inp: _DesignInputs,
    db: Session,
    slot: Optional[int],
    expression: Optional[str],
    art_style_id: Optional[int],
    use_ai_prompt: bool,
    use_outfit: bool,
    use_ipa: bool,
    ipa_weight: float,
    use_controlnet: bool,
    cn_weight: float,
    canvas_expand_mode: str,      # "pre"=角色版(SDXL前/概念圖/提早return) | "post"=變體版(SDXL後/輸出圖/try)
    use_pixel_override: bool,     # 角色版 True：coverage=full 時像素二次確認
    use_solo_tag: bool,           # 變體版 True：partial/bust 加 solo 標籤
    log_label: str,
    record_endpoint: str,
):
    """角色人設圖 / 變體人設圖共用核心（2026-06-13 項3 去重；分歧以策略參數保留，零行為變更）。"""
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
    parts = [f"角色名稱：{inp.name}"]

    all_flat = True  # no images → treat as flat, use core_traits for anchors
    _ipa_ref_bytes: bytes | None = None
    _cn_ref_bytes: bytes | None = None
    _cn_coverage: str = "full"
    _coverage_end_pct: float | None = None
    _cn_weight_user = cn_weight        # 方案3：保留使用者原始 CN 強度（夾制前）
    _pre_ref = False                   # 方案3：是否要在 SDXL 前 Flux 外擴概念圖成全身 ref
    _pre_ref_done = False              # 方案3：pre-ref 外擴成功（成功則跳過 post 外擴、還原 CN）

    if inp.concept_imgs:
        valid_images: list[bytes] = []
        for img_filename in inp.concept_imgs[:3]:
            img_path = _PORTRAIT_DIR / img_filename
            if img_path.exists():
                try:
                    valid_images.append(img_path.read_bytes())
                except Exception:
                    pass
        if valid_images:
            all_flat = all(_is_flat_color_draft(img) for img in valid_images)
            logger.info("[prompt-log] %s concept images flat_draft=%s (%d imgs)", log_label, all_flat, len(valid_images))
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
                _exp_w, _exp_h = _fullbody_canvas(inp.height)
                _cn_coverage = coverage
                # 角色版：LLM 偵測 full 時用像素分析二次確認（變體版略過）
                if use_pixel_override and _cn_coverage == "full":
                    pixel_override = _pixel_coverage_check(valid_images[0])
                    if pixel_override:
                        logger.info("[%s] pixel-check override: %s → %s", log_label, _cn_coverage, pixel_override)
                        _cn_coverage = pixel_override
                # CN≥0.7 限制條件：所有 coverage 一律保留 CN，不再 bypass。
                # partial/bust 透過 _shrink_for_full_body 縮到畫布上半，下半留空補腿；
                # CN 以 AnimeLineArt（非 Canny）引導上半身，單 pass 無接縫。
                # 方案3：變體 partial/bust 且有 Flux 擴圖 → 稍後在 SDXL 前外擴成全身 ref
                _pre_ref = (
                    _PRE_REF_ENABLED
                    and canvas_expand_mode == "post"
                    and _cn_coverage in ("partial", "bust")
                    and _ipa_ref_bytes is not None
                    and (CUSTOM_WORKFLOWS_DIR / _CANVAS_EXPAND_SDXL_WF).exists()
                )
                # 安全基線（方案1）：先縮圖 + 夾 CN 上限；pre-ref 成功時後段會覆寫為全身 ref 並還原 CN。
                _cn_ref_bytes = _shrink_for_full_body(valid_images[0], _exp_w, _exp_h, _cn_coverage)
                _cn_w_ceiling = _COVERAGE_CN_WEIGHT.get(_cn_coverage)
                if _cn_w_ceiling is not None and cn_weight > _cn_w_ceiling:
                    logger.info(
                        "[%s] coverage=%s：CN 強度 %.2f 超過補腿安全上限，夾到 %.2f",
                        log_label, _cn_coverage, cn_weight, _cn_w_ceiling,
                    )
                    cn_weight = _cn_w_ceiling
                _coverage_end_pct = _COVERAGE_CN_END_PERCENT.get(_cn_coverage)
                logger.info(
                    "[%s] coverage=%s pre_ref=%s → CN (weight=%.2f, fill=%.2f)",
                    log_label, _cn_coverage, _pre_ref, cn_weight,
                    _BODY_FILL_RATIO.get(_cn_coverage, 1.0),
                )
            if visual and not visual.startswith("["):
                has_outfit = bool(use_outfit and inp.outfit)
                has_hair_in_traits = bool(inp.core_traits and
                    any(kw in inp.core_traits for kw in ("髮", "頭髮", "hair")))
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

    if use_outfit and inp.outfit:
        parts.append(f"服裝設定：{inp.outfit}")

    if inp.core_traits:
        parts.append(f"外貌與個性（優先採用）：{inp.core_traits}")

    bg_color_name = _hex_to_sd_color(inp.color) if inp.color else None

    if is_expression:
        parts.append("動漫插畫風格，角色臉部特寫半身圖")
    else:
        parts.append("人設圖，全身正面，動漫插畫風格，清晰展示角色外觀")

    raw_desc = "，".join(parts)
    logger.info("[prompt-log] %s raw_desc (中文，AI翻譯前): %s", log_label, raw_desc)

    _color_anchor = inp.core_traits or ""

    # ── Compile description ────────────────────────────────────────────────
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
    if use_ai_prompt and inp.ai_prompt and inp.ai_prompt.strip():
        t0 = time.perf_counter()
        await guardian.request_focus("ollama")
        try:
            _ai_overrides = {**_overrides, "quality_prefix_override": ""}
            extra_compiled, _ = compile_prompt(
                inp.ai_prompt.strip(), style=style, model=state.get_text_model(), **_ai_overrides,
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
            f", {expr_tags}, bust shot, upper body, close-up portrait, face focus"
            ", simple background, flat background" + bg_tag
        )
        width, height, steps = 512, 640, 20
    else:
        # partial/bust：用單張全身插畫模式，避免 design sheet 觸發多視圖構圖
        _design_tags = (
            "character illustration, full body portrait"
            if _cn_coverage in ("partial", "bust")
            else "character design sheet, character reference sheet"
        )
        # 變體版：partial/bust 加 solo 避免 IPA 把設計稿多視角構圖帶進來
        _solo_tag = ", solo, single character" if (use_solo_tag and _cn_coverage in ("partial", "bust")) else ""
        suffix = (
            f", {_design_tags}, full body, front view"
            f", {_FULLBODY_POS_TAGS}"
            f"{_solo_tag}"
            ", simple background, flat background, no background detail, no scenery" + bg_tag
        )
        width, height = _fullbody_canvas(inp.height)
        steps = 20

    # Gender/age tag anchors subject count — must be at absolute front
    gender_tag = _age_gender_tag(inp.gender, inp.age)
    gender_prefix = gender_tag + ", " if gender_tag else ""

    _age_tags = _age_body_tags(inp.age)
    _ht_tags = _height_body_tags(inp.height)
    _body_parts = [t for t in [_age_tags, _ht_tags] if t]
    body_prefix = ", ".join(_body_parts) + ", " if _body_parts else ""

    is_male = gender_tag.startswith(("1boy", "1man"))
    is_female = gender_tag.startswith(("1girl", "1woman"))
    gender_pos_extra = ", clothed, shirt, pants, male clothes" if is_male else ""
    gender_neg_extra = (
        ", bare chest, shirtless, topless, naked upper body, no shirt"
        ", skirt, dress, miniskirt, female clothes, feminine clothing, thighhighs, sailor uniform"
        if is_male else
        ", male face, masculine features" if is_female else ""
    )

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
    _canvas_expand_sdxl_available = (CUSTOM_WORKFLOWS_DIR / _CANVAS_EXPAND_SDXL_WF).exists()

    # ── 方案3：變體 partial/bust → SDXL 前先用 SDXL inpaint 外擴概念圖成全身，當 CN 結構參考 ──
    # 成功後 coverage 視為 full：CN 還原使用者完整強度、不縮圖；全身結構已具備 → 補得出腿且貼合度高。
    # IPA 仍用原始概念圖（保身分）；CN 用外擴全身圖（保結構）。外擴用主生成同一顆 checkpoint，
    # 不換模型、不載 Flux。失敗則沿用方案1 基線（縮圖+夾 CN）。
    if _pre_ref and _canvas_expand_sdxl_available:
        t0_pre = time.perf_counter()
        # 取主生成 workflow 的 checkpoint，讓外擴用同一顆 → 避免模型 swap
        _main_ckpt = None
        try:
            _mwf = _load_workflow(state.get_workflow())
            _main_ckpt = next(
                (n["inputs"].get("ckpt_name") for n in _mwf.values()
                 if isinstance(n, dict) and n.get("class_type") == "CheckpointLoaderSimple"),
                None,
            )
        except Exception:
            pass
        logger.info("[%s] 方案3 pre-ref 外擴（SDXL inpaint, ckpt=%s, coverage=%s → full, CN 還原 %.2f）",
                    log_label, _main_ckpt, _cn_coverage, _cn_weight_user)
        try:
            _cn_ref_bytes = await _run_canvas_expand_sdxl(
                _ipa_ref_bytes, _cn_coverage, final_positive, final_negative,
                width, height, seed, _main_ckpt,
            )
            cn_weight = _cn_weight_user
            _cn_coverage = "full"
            _pre_ref_done = True
            timings["canvas_expand"] = round(time.perf_counter() - t0_pre, 1)
        except HTTPException as he:
            if he.status_code == 504:
                # 外擴逾時：ComfyUI 多半仍在背景處理該 job，回退再送主 SDXL 會 double submit → 串行。
                logger.error("[%s] 方案3 pre-ref 外擴逾時(504)，中止以避免 double submit", log_label)
                raise
            logger.warning("[%s] 方案3 pre-ref 外擴失敗(HTTP %s)，回退方案1: %s", log_label, he.status_code, he.detail)
        except Exception as e:
            logger.warning("[%s] 方案3 pre-ref 外擴失敗，回退方案1（縮圖+夾 CN）: %s", log_label, e)

    # ── Canvas Expand 前置（角色版：partial/bust → SDXL 前對概念圖 Flux 擴圖並提早 return）──
    if (canvas_expand_mode == "pre"
            and not is_expression
            and _cn_coverage in ("partial", "bust")
            and _ipa_ref_bytes is not None
            and _canvas_expand_available):
        t0 = time.perf_counter()
        logger.info("[%s] canvas-expand via Flux 2 (coverage=%s)", log_label, _cn_coverage)
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

    # ── Generate（SDXL）────────────────────────────────────────────────────
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

    logger.info("[%s] char_id=%s slot=%s use_ipa=%s use_cn=%s ipa_ref=%s cn_ref=%s active_workflow=%s",
                log_label, character.id, slot, use_ipa, use_controlnet,
                "yes" if _ipa_ref_bytes else "no", "yes" if _cn_ref_bytes else "no", active_wf)
    # HTTPException (e.g. UI-format workflow 422) intentionally not caught here — surfaces to user
    wf = _load_workflow(active_wf)

    # 統一注入管線：啟用且有圖 → 缺節點則建、有則沿用；停用或無圖 → 既有節點 bypass。
    need_ipa_inject = _ipa_ref_bytes is not None and not _wf_has_ipa(wf)
    need_cn_inject = _cn_ref_bytes is not None and not _wf_has_controlnet(wf)
    if need_ipa_inject or need_cn_inject:
        _inject_models = resolve_capability(wf, state.get_checkpoint())["models"]
        _inject_ipa_cn_nodes(
            wf, inject_ipa=need_ipa_inject, inject_cn=need_cn_inject, models=_inject_models
        )
        logger.info("[%s] 動態注入節點 ipa=%s cn=%s（工作流 '%s' 原缺節點）",
                    log_label, need_ipa_inject, need_cn_inject, active_wf)

    if _ipa_ref_bytes is not None:
        _t = time.perf_counter()
        uploaded_ref = comfyui_client.upload_image_bytes(_ipa_ref_bytes, "char_concept_ref.png")
        timings["upload"] = round(time.perf_counter() - _t, 1)
        ipa_used = True
        logger.info("[%s] IP-Adapter 啟用（active workflow '%s'）", log_label, active_wf)
    elif _wf_has_ipa(wf):
        _bypass_ipa_nodes(wf)
        logger.info("[%s] IPA 停用/無參考圖 → 既有節點 bypass", log_label)

    # ControlNet：無參考圖時剝離既有 CN 節點（須在 _inject_prompts 之前）
    if _cn_ref_bytes is None and _wf_has_controlnet(wf):
        _bypass_controlnet_nodes(wf)
        logger.info("[%s] ControlNet 停用/無參考圖 → 既有節點 bypass", log_label)
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
        logger.info("[%s] ControlNet (%s) injected, weight=%.2f", log_label, cn_mode, cn_weight)

    _replace_negative_seeds(wf, seed)
    _log_wf_snapshot(wf, label=log_label)
    t0 = time.perf_counter()
    await guardian.request_focus("comfyui")
    image_bytes = await _run_comfyui(wf)
    timings["comfyui"] = round(time.perf_counter() - t0, 1)

    # ── Canvas Expand 後置（變體版：full → SDXL 後對輸出 Flux 擴圖，try/except 回退）──
    # 只有 coverage=full 時 SDXL 有 CN 引導、輸出穩定為單人全身圖，才安全做 canvas expand
    cn_mode_out = cn_mode
    if (canvas_expand_mode == "post"
            and not is_expression
            and _cn_coverage == "full"
            and not _pre_ref_done
            and _canvas_expand_available):
        t0_expand = time.perf_counter()
        logger.info("[%s] canvas-expand via Flux 2 on SDXL output (coverage=%s)", log_label, _cn_coverage)
        try:
            image_bytes = await _run_canvas_expand_flux(
                image_bytes, _cn_coverage, final_positive, width, height, seed
            )
            timings["canvas_expand"] = round(time.perf_counter() - t0_expand, 1)
            cn_mode_out = "canvas_expand"
        except Exception as e:
            logger.warning("[%s] canvas-expand 失敗，使用 SDXL 輸出: %s", log_label, e)

    timings["total"] = round(time.perf_counter() - t_total, 1)
    timings["models"] = {
        "vision": state.get_vision_model(),
        "text": state.get_text_model(),
        "workflow": active_wf,
    }

    hist_id = record_generation(
        db,
        endpoint=record_endpoint,
        character_id=character.id,
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


# ── Character / Variant Design Sheet（薄轉接 → _generate_design_core，2026-06-13 項3 去重）──

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

    concept_imgs = list(character.concept_images or [])
    if not concept_imgs and character.portrait_path:
        concept_imgs = [character.portrait_path]
    inp = _DesignInputs(
        name=character.name,
        concept_imgs=concept_imgs,
        outfit=getattr(character, "outfit", None),
        core_traits=character.core_traits,
        color=character.color,
        gender=character.gender,
        age=character.age,
        ai_prompt=character.ai_prompt,
        height=getattr(character, "height", None),
    )
    return await _generate_design_core(
        character=character, inp=inp, db=db, slot=None,
        expression=expression, art_style_id=art_style_id,
        use_ai_prompt=use_ai_prompt, use_outfit=use_outfit,
        use_ipa=use_ipa, ipa_weight=ipa_weight,
        use_controlnet=use_controlnet, cn_weight=cn_weight,
        canvas_expand_mode="pre", use_pixel_override=True, use_solo_tag=False,
        log_label="char-gen", record_endpoint="character_design",
    )


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
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    idx = _slot_index(slot)
    v = _get_variants(character)[idx]
    inp = _DesignInputs(
        name=character.name,
        concept_imgs=list(v.get("concept_images") or []),
        outfit=v.get("outfit"),
        core_traits=v.get("core_traits"),
        color=v.get("color"),
        gender=v.get("gender"),
        age=v.get("age"),
        ai_prompt=v.get("ai_prompt"),
        height=v.get("height"),
    )
    return await _generate_design_core(
        character=character, inp=inp, db=db, slot=slot,
        expression=expression, art_style_id=art_style_id,
        use_ai_prompt=use_ai_prompt, use_outfit=use_outfit,
        use_ipa=use_ipa, ipa_weight=ipa_weight,
        use_controlnet=use_controlnet, cn_weight=cn_weight,
        canvas_expand_mode="post", use_pixel_override=False, use_solo_tag=True,
        log_label="variant-gen", record_endpoint="variant_design",
    )
