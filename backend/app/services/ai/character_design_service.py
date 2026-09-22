# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
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
    PERSONAL_NEGATIVE_ENABLED, PERSONAL_NEGATIVE, PERSONAL_STYLE_WEIGHT,
    IPA_FLAT_DRAFT_SCALE,
)
from app.core import state
from app.core.database import get_db
from app.models.art_style import ArtStyle
from app.models.character import Character
from app.models.generation_history import GenerationHistory  # A3 P0-3：reuse_prompt 查詢用
from app.services import comfyui_client
from app.services.ai.prompt_engine import compile as compile_prompt
from app.services.ai.prompt_engine import prompt_cache_hit
from app.services.ai.vram_manager import guardian
from app.services.ai.generation_recorder import record_generation
from app.services.ai.workflow_builder import (
    _extra_tags,
    _inject_loras,
    lora_trigger_words,
    _load_workflow,
    _log_wf_snapshot,
    _replace_negative_seeds,
    _resolve_prompt_overrides,
    _prompt_profile_source,
    _resolve_style,
    _run_comfyui,
    _is_custom_workflow,
    _workflow_style_extra,
)
from app.services.ai.image_ops import (
    _BODY_FILL_RATIO,
    _BODY_TOP_OFFSET,
    _FULLBODY_NEG_TAGS,
    _FULLBODY_POS_TAGS,
    _border_color,
    _dedup_tags,
    _fullbody_canvas,
    _strip_sheet_tags,
    _is_flat_color_draft,
    _normalize_i2i_ref,
    _fit_to_canvas,
    _letterbox_to_aspect,
    _pixel_coverage_check,
    _pixel_fullness_check,
    _detect_body_break,
    _shrink_for_full_body,
)
from app.services.ai.capability import extract_checkpoint_from_wf, resolve_capability
from app.services.ai.gen_profile import resolve_profile_for_workflow
from app.services.ai.wf_node_ops import (
    _CN_APPLY_TYPES,
    _bypass_controlnet_nodes,
    _get_node_input,
    _bypass_ipa_nodes,
    _inject_controlnet_image,
    _inject_img2img,
    _inject_lllite,
    _inject_ipa_cn_nodes,
    _inject_ipa_image,
    _inject_prompts,
    _set_node_input,
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


def _effective_ksampler_steps(wf: dict, steps: Optional[int]) -> Optional[int]:
    """R3（2026-07-12）：steps 為 None（家族 profile 選擇不覆寫 KSampler）時，回讀 wf
    內 KSampler 節點的實際 steps（workflow JSON 內建值），供 generation_history 記錄
    真實生效值，避免可重現性記錄失真。steps 有值時原樣回傳，不受影響（零回歸）。"""
    if steps is not None:
        return steps
    # [CN-034] steps 在作者型 workflow 是節點參照，須往上游解析，否則 DB 記成 list、可重現性失真
    ks_id = next(
        (nid for nid, n in wf.items()
         if isinstance(n, dict) and n.get("class_type") == "KSampler"),
        None,
    )
    if ks_id is None:
        return None
    return _get_node_input(wf, ks_id, "steps")


def _effective_ksampler_cfg(wf: dict) -> Optional[float]:
    """A3 P0-4：cfg 一律由 workflow JSON 節點決定（gen_profile.py 明文「cfg/sampler/
    scheduler 寫在 workflow JSON、後端不覆寫」），故無 steps 那種「入參覆寫優先」語義，
    直接回讀實際生效值。用法與 `_effective_ksampler_steps` 相同的節點參照解析規則
    （見 D1：node 24 分送 KSampler 與 metadata 的作者型 workflow，須經 `_get_node_input`
    解參照，不可直讀字面值）。"""
    ks_id = next(
        (nid for nid, n in wf.items()
         if isinstance(n, dict) and n.get("class_type") == "KSampler"),
        None,
    )
    if ks_id is None:
        return None
    return _get_node_input(wf, ks_id, "cfg")


# coverage→CN 上限/end_percent 已移至 gen_profile.GEN_PROFILE（R3 2026-06-20，per-family 單一真相）。


def _coverage_badge(coverage: str, user_w: float, eff_w: float, cn_on: bool,
                    original: str | None = None, pre_ref: bool = False) -> str:
    """S10（2026-07-13）：debug 用 coverage/CN 標註。半身圖故障連三輪歸因靠猜，
    把「coverage 判定 + CN 使用者值→實際夾制值」可視化，一眼看出是否誤判/夾制生效。
    例：`coverage: bust (CN 0.85→0.50)`、`coverage: full (CN 0.85)`、`coverage: full (CN off)`。

    T0-1（2026-07-14）：`coverage` 是「最終」值（pre_ref 外擴或 fullness 升級後可能已成 full），
    附掛 `original`（改寫前原判）＋ `pre_ref`（是否走過外擴）以區分：
    `full (CN 0.85) [原判 bust, pre_ref 外擴]`（已外擴）vs `full (CN 0.85)`（原判即 full、未動）。"""
    if not cn_on:
        base = f"coverage: {coverage} (CN off)"
    elif abs(user_w - eff_w) > 1e-3:
        base = f"coverage: {coverage} (CN {user_w:.2f}→{eff_w:.2f})"
    else:
        base = f"coverage: {coverage} (CN {eff_w:.2f})"
    notes: list[str] = []
    if original is not None and original != coverage:
        notes.append(f"原判 {original}")
    if pre_ref:
        notes.append("pre_ref 外擴")
    if notes:
        base += " [" + ", ".join(notes) + "]"
    return base



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
) -> tuple[bytes, bytes, int]:
    """
    Place sketch in upper portion of a full-body canvas and generate inpaint mask.
    Returns (canvas_png, mask_png, expand_px) — mask white=inpaint lower body, black=preserve
    sketch；expand_px=下半實際擴圖像素高(coverage=full→fill=1.0 時為 0，供呼叫端 0px 防呆)。
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

    expand_px = max(0, target_h - sketch_bottom)
    logger.info("[expand-canvas] coverage=%s fill=%.2f canvas=%dx%d sketch=%dx%d@top%d bottom=%d (下半 inpaint 區=%d px)",
                coverage, fill, target_w, target_h, new_w, new_h, top, sketch_bottom, expand_px)
    canvas_out = io.BytesIO()
    canvas.save(canvas_out, format="PNG")
    mask_out = io.BytesIO()
    mask.save(mask_out, format="PNG")
    return canvas_out.getvalue(), mask_out.getvalue(), expand_px


# _inject_inpaint_nodes / _inject_img2img_node 已移除（死代碼，無呼叫端；2026-06-20 R1）。


_CANVAS_EXPAND_WF = "canvas_expand_flux.json"
_CANVAS_EXPAND_SDXL_WF = "canvas_expand_sdxl.json"   # 方案3：SDXL inpaint 外擴（重用主生成 checkpoint，免載 Flux）
# 下半擴圖區低於此像素門檻 → 視為無下半身可補（多半是 coverage 誤判/防呆預設 full），
# 啟動 Flux 只會空轉到 timeout，故直接沿用輸入圖，避免 silent 觸發 17GB Flux 拖垮速度。
_MIN_EXPAND_PX = 16
# 方案3（pre-ref 外擴）為 v36 變體半身→全身正式路線（06-19 定版），預設啟用。
# 設 CRAFTFLOW_PRE_REF_EXPAND=0 可關閉、退回方案1（CN 夾上限單段 SDXL，較快但貼合較鬆）。
_PRE_REF_ENABLED = os.getenv("CRAFTFLOW_PRE_REF_EXPAND", "1").strip() == "1"
# T1A（2026-07-14）：像素反向升級防呆（LLM 誤判 partial/bust 但草圖實為完整全身 → 升級 full、
# 跳過外擴，避免幽靈下半身）。設 CRAFTFLOW_FULLNESS_CHECK=0 可關閉、退回純 LLM 判定。
_FULLNESS_CHECK_ENABLED = os.getenv("CRAFTFLOW_FULLNESS_CHECK", "1").strip() == "1"
# T3A（2026-07-15）：外擴輸出斷裂防線（幽靈下半身最後攔截）。外擴成功後掃描輸出，偵測到
# 主體內純背景空帶 → 丟棄外擴、回退方案1（縮圖+夾CN）。設 CRAFTFLOW_EXPAND_BREAK_GUARD=0 可關。
_EXPAND_BREAK_GUARD_ENABLED = os.getenv("CRAFTFLOW_EXPAND_BREAK_GUARD", "1").strip() == "1"
# T0-3（2026-07-14）：CRAFTFLOW_EXPAND_DEBUG=1 時把外擴 canvas/mask/輸出三圖落地 data/debug/，
# 檔名含 coverage 與 seed，供全身外擴誤判的失敗案例直接檢視 mask 幾何。
_EXPAND_DEBUG_DIR = CUSTOM_WORKFLOWS_DIR.parent / "debug"


def _expand_debug_enabled() -> bool:
    return os.getenv("CRAFTFLOW_EXPAND_DEBUG", "0").strip() == "1"


def _dump_expand_debug(coverage: str, seed: int, tag: str, data: bytes) -> None:
    """落地一張外擴中間圖（input canvas / mask / output）。任何失敗僅告警、不影響生成。"""
    try:
        _EXPAND_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        fn = _EXPAND_DEBUG_DIR / f"expand_{coverage}_{seed}_{tag}.png"
        fn.write_bytes(data)
        logger.info("[expand-debug] dump %s (%d bytes)", fn.name, len(data))
    except Exception as e:
        logger.warning("[expand-debug] dump 失敗: %s", e)


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
    canvas_bytes, mask_bytes, expand_px = _create_inpaint_canvas_and_mask(
        sketch_bytes, width, height, coverage
    )
    # 0px 防呆：無下半身可補 → 跳過 Flux，直接回輸入圖（修正 coverage 誤判預設 full 時的空轉 timeout）
    if expand_px < _MIN_EXPAND_PX:
        logger.info("[canvas-expand] 下半擴圖區 %dpx < %dpx → 跳過 Flux，沿用輸入圖", expand_px, _MIN_EXPAND_PX)
        return sketch_bytes
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
    # 外擴輸出僅作 CN 結構參考（preprocessor 重描到 resolution=1024、主 pass 再全解析度重繪），
    # 故外擴解析度對 final 品質近乎無影響 → 用 75% 省時省 VRAM（64 對齊、最小 512）。
    _exp_scale = 0.75
    _exp_w = max(512, round(width  * _exp_scale / 64) * 64)
    _exp_h = max(512, round(height * _exp_scale / 64) * 64)
    canvas_bytes, mask_bytes, _ = _create_inpaint_canvas_and_mask(
        sketch_bytes, _exp_w, _exp_h, coverage
    )
    if _expand_debug_enabled():
        _dump_expand_debug(coverage, seed, "input", canvas_bytes)
        _dump_expand_debug(coverage, seed, "mask", mask_bytes)
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
        out = await _run_comfyui(wf)
        if _expand_debug_enabled():
            _dump_expand_debug(coverage, seed, "output", out)
        return out
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


# [CN-035] 全身 suffix 拿掉 design/reference sheet：那是 2026-07-26 出雙人的根因，補 solo 擋不住
def _build_fullbody_suffix(bg_tag: str) -> str:
    """組出全身人設圖的固定 suffix（單張全身插畫、單人、簡潔背景）。"""
    return (
        # [CN-097] SYNC-005 軌 S（2026-09-21）：拔掉 "character illustration" 與
        # "full body portrait" 兩個泛詞。① 對以 danbooru 標籤為語料的動漫模型，泛用
        # 描述是無效稀釋（Gemini §2.3-9）；② `full body portrait` 裡的 "portrait"
        # 與 CN-070「移除 close-up/portrait：壓低臉部佔比」是同一個顧慮 —— CN-070
        # 當時只改了負向（image_ops.py:27），正向這裡一直殘留著。
        # ⚠️ "solo, single character" 不得一併拔除：那是 CN-035 擋出雙人的防線。
        # 回滾＝改回 `", character illustration, full body portrait, full body, front view"`。
        ", full body, front view"
        f", {_FULLBODY_POS_TAGS}"
        ", solo, single character"
        # [CN-036] 拔正向 "no background detail/no scenery"：正向 no-xxx 是反效果，負向已含同義項
        ", simple background, flat background" + bg_tag
    )


def _wf_checkpoint(wf: dict) -> str:
    """實際生效的 checkpoint：**工作流內嵌值優先**，讀不到才退回全域設定。

    SYNC-001（2026-09-15，Codex §2.2 B 案）：custom workflow 的模型內嵌於 JSON
    （`_load_workflow` 只對 system workflow 套全域覆寫），所以內嵌值才是實跑值。
    本檔原本兩處直接把 `state.get_checkpoint()` 餵給 `resolve_capability()`，
    當全域 checkpoint 與工作流內嵌模型不同家族時（例：全域 fabricatedXL＋跑 Anima
    工作流，或反向），family 會判錯 → 注入錯家族的 IPA/CN 模型，或漏掉
    Anima 的 LLLite/img2img fallback（`cn_fallback` 整段跳過）。

    這正是 `capability.py:50-55` 已寫明的同一個坑（AC-2' 把 checkpoint 解析集中化），
    `api/settings.py:149` 與 `api/art_generate.py:87` 早已改用內嵌優先，角色生成端漏改。
    與 `gen_profile.resolve_profile_for_workflow()` 的解析來源一致後，同一張圖的
    family 判定不再有兩個出處。

    註：此處收 wf dict（記憶體中實際要送出的那份，已套用 system workflow 的全域覆寫），
    而非工作流檔名——與 params["checkpoint"] 的記錄來源同源，確保「判定值＝記錄值＝實跑值」。
    """
    return extract_checkpoint_from_wf(wf) or state.get_checkpoint()


# [CN-037] 畫風 tag／權重優先序：art_style DB > yml style_extra > .env > 無；未登錄 workflow 零回歸
def _resolve_style_extra(art_style: Optional[ArtStyle], workflow: str) -> tuple[str, float]:
    profile_extra, profile_weight = _workflow_style_extra(workflow)
    style_extra = _extra_tags(art_style)
    if not style_extra and profile_extra:
        style_extra = profile_extra
    if not style_extra and PERSONAL_STYLE_ENABLED and PERSONAL_STYLE_EXTRA_TAGS:
        style_extra = PERSONAL_STYLE_EXTRA_TAGS
    weight = profile_weight if profile_weight is not None else PERSONAL_STYLE_WEIGHT
    return style_extra, weight


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
    use_vision: bool,             # 是否把視覺模型抽取的特徵拼進 prompt（CN coverage 偵測不受此影響）
    use_ipa: bool,
    ipa_weight: float,
    use_controlnet: bool,
    cn_weight: float,
    canvas_expand_mode: str,      # "pre"=角色版(SDXL前/概念圖/提早return) | "post"=變體版(SDXL後/輸出圖/try)
    use_pixel_override: bool,     # 角色版 True：coverage=full 時像素二次確認
    log_label: str,
    record_endpoint: str,
    seed: int = -1,                # A3 P0-1：-1=維持現行隨機（零回歸），>=0 沿用指定 seed（可重現實驗台）
    reuse_prompt: bool = False,    # A3 P0-3：True=沿用上次 generation_history 的 prompt，略過重新編譯
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

    active_wf = state.get_workflow()
    _profile, _gen_family = resolve_profile_for_workflow(active_wf)
    logger.info("[%s] gen profile: family=%s steps=%s full_cn_weight=%s",
                log_label, _gen_family, _profile.steps, _profile.full_cn_weight)

    # [CN-038] 角色中文名不進 prompt（SD 無此 token 概念），避免名字洩漏成 tag
    parts: list[str] = []

    all_flat = True  # no images → treat as flat, use core_traits for anchors
    _ipa_ref_bytes: bytes | None = None
    _cn_ref_bytes: bytes | None = None
    _i2i_ref_bytes: bytes | None = None   # D'-2：CN 替代（img2img）參考圖
    # [CN-039] 外擴輸入一律用 _orig_ref_bytes：_ipa_ref_bytes 的語義是 IPA 參考圖，不是「有無概念圖」
    _orig_ref_bytes: bytes | None = None
    _cn_coverage: str = "full"
    _coverage_original: str = "full"   # T0-1：pre_ref/fullness 改寫前的原始判定（badge 觀測用）
    _coverage_end_pct: float | None = None
    _cn_weight_user = cn_weight        # 方案3：保留使用者原始 CN 強度（夾制前）
    _pre_ref = False                   # 方案3：是否要在 SDXL 前 Flux 外擴概念圖成全身 ref
    _pre_ref_done = False              # 方案3：pre-ref 外擴成功（成功則跳過 post 外擴、還原 CN）
    _expand_engine: str | None = None  # T0-2：實際外擴引擎檔名（回傳 timings.models 供 UI 顯示，取代 hardcode）

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
            _orig_ref_bytes = valid_images[0]  # A3 P2-2：不受 IPA/CN 閘控，供方案3 外擴判斷「有無概念圖」
            # [CN-040] G0 能力閘控：非 SDXL 家族不取 IPA/CN 參考圖，避免跨架構注入
            if use_ipa and _profile.ipa_enabled:
                _ipa_ref_bytes = valid_images[0]
            if use_controlnet and _profile.cn_enabled:
                _cn_ref_bytes = valid_images[0]
            # [CN-041] 改判 cn_fallback_chain 非空（不寫死 img2img）；走哪條由下游執行期偵測決定
            elif use_controlnet and _profile.cn_fallback_chain:
                _i2i_ref_bytes = valid_images[0]

            # [CN-042] coverage 偵測不可綁 cn_enabled：有 fallback 鏈的家族同樣要 coverage 決定縮圖/外擴
            need_coverage = use_controlnet and not is_expression and (
                _profile.cn_enabled or bool(_profile.cn_fallback_chain)
            )
            if use_vision or need_coverage:
                t0 = time.perf_counter()
                coverage, visual = await _vision_extract_cached(valid_images, need_coverage)
                timings["vision_extract"] = round(time.perf_counter() - t0, 1)
            else:
                coverage, visual = "full", ""
            if need_coverage:
                _exp_w, _exp_h = _fullbody_canvas(inp.height)
                _cn_coverage = coverage
                # 角色版：LLM 偵測 full 時用像素分析二次確認（變體版略過）
                if use_pixel_override and _cn_coverage == "full":
                    pixel_override = _pixel_coverage_check(valid_images[0])
                    if pixel_override:
                        logger.info("[%s] pixel-check override: %s → %s", log_label, _cn_coverage, pixel_override)
                        _cn_coverage = pixel_override
                # T0-1：記錄 pre_ref/fullness 改寫前的原始判定，供 badge 區分「已外擴／升級」vs「未動」
                _coverage_original = _cn_coverage
                # T1A（2026-07-14）：反向升級。LLM 判 partial/bust 但草圖幾何實為完整站立全身
                # → 升級 full、跳過外擴（否則在完整身體下方再 inpaint 一套腿＝幽靈下半身／比例拉長）。
                if (_FULLNESS_CHECK_ENABLED
                        and _cn_coverage in ("partial", "bust")
                        and _pixel_fullness_check(valid_images[0])):
                    logger.info("[%s] fullness-check 反向升級：%s → full（草圖幾何為完整站立全身，跳過外擴）",
                                log_label, _cn_coverage)
                    _cn_coverage = "full"
                # [CN-043] 所有 coverage 一律保留 CN 不 bypass；partial/bust 走縮圖＋方案3 外擴
                _pre_ref = (
                    _PRE_REF_ENABLED
                    and canvas_expand_mode in ("pre", "post")
                    and _cn_coverage in ("partial", "bust")
                    and _orig_ref_bytes is not None
                    and (CUSTOM_WORKFLOWS_DIR / _CANVAS_EXPAND_SDXL_WF).exists()
                )
                # [CN-044] 縮圖結果依家族寫回正確通道：cn_enabled→_cn_ref_bytes，只有 fallback 的→_i2i_ref_bytes
                _shrunk_ref = _shrink_for_full_body(valid_images[0], _exp_w, _exp_h, _cn_coverage)
                if _profile.cn_enabled:
                    _cn_ref_bytes = _shrunk_ref
                else:
                    _i2i_ref_bytes = _shrunk_ref
                _cn_w_ceiling = (
                    _profile.full_cn_weight if _cn_coverage == "full"
                    else _profile.coverage_cn_weight.get(_cn_coverage)
                )
                if _cn_w_ceiling is not None and cn_weight > _cn_w_ceiling:
                    logger.info(
                        "[%s] coverage=%s：CN 強度 %.2f 超過補腿安全上限，夾到 %.2f",
                        log_label, _cn_coverage, cn_weight, _cn_w_ceiling,
                    )
                    cn_weight = _cn_w_ceiling
                _coverage_end_pct = _profile.coverage_cn_end_pct.get(_cn_coverage)
                logger.info(
                    "[%s] coverage=%s pre_ref=%s → CN (weight=%.2f, fill=%.2f)",
                    log_label, _cn_coverage, _pre_ref, cn_weight,
                    _BODY_FILL_RATIO.get(_cn_coverage, 1.0),
                )
            if use_vision and visual and not visual.startswith("["):
                has_outfit = bool(use_outfit and inp.outfit)
                has_hair_in_traits = bool(inp.core_traits and
                    any(kw in inp.core_traits for kw in ("髮", "頭髮", "hair")))
                # [CN-045] vision 描述剝除服裝/髮型/膚色洩漏詞，避免蓋掉角色設定
                visual_for_llm = _filter_visual_for_llm(
                    visual,
                    strip_clothing=has_outfit,
                    strip_hairstyle=has_hair_in_traits,
                    strip_skin=True,
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
    art_style = db.get(ArtStyle, art_style_id) if art_style_id else None
    style = _resolve_style(art_style, active_wf)
    # P1：art_style > workflow 級 prompt_profiles.yml > checkpoint family。
    _overrides = _resolve_prompt_overrides(art_style, active_wf)

    # [CN-046] reuse_prompt 整段跳過重編譯（非只跳 LLM）：否則已組裝字串會被二次組裝、前後綴重貼
    _reused_positive: Optional[str] = None
    _reused_negative: Optional[str] = None
    if reuse_prompt:
        _hist = (
            db.query(GenerationHistory)
            .filter(
                GenerationHistory.character_id == character.id,
                GenerationHistory.variant_slot == slot,
                GenerationHistory.endpoint == record_endpoint,
            )
            .order_by(GenerationHistory.id.desc())
            .first()
        )
        if _hist and _hist.positive:
            _reused_positive, _reused_negative = _hist.positive, _hist.negative or ""
            logger.info("[%s] reuse_prompt=True，沿用 history #%s 的 prompt（略過重新編譯）",
                        log_label, _hist.id)
        else:
            logger.info("[%s] reuse_prompt=True 但無可用歷史紀錄，落回正常編譯", log_label)

    if _reused_positive is not None:
        final_positive = _reused_positive
        final_negative = _reused_negative
        _profile_source = "reused-history"
        _ai_prompt_compiled = ""
        if is_expression:
            width, height, steps = 512, 640, 20
        else:
            width, height = _fullbody_canvas(inp.height)
            steps = _profile.steps
    else:
        t0 = time.perf_counter()
        # P4：debug prompt 來源標註（profile: <wf> / family fallback），僅供前端 DEBUG 顯示。
        _profile_source = _prompt_profile_source(art_style, active_wf)
        # [CN-047] 只有真要呼叫 Ollama 才 request_focus：搶一次 focus＝ComfyUI 卸掉約 11GB 再重載
        _compile_kwargs = dict(
            style=style, model=state.get_text_model(),
            anchor_text=_color_anchor, **_overrides,
        )
        if not prompt_cache_hit(raw_desc, **_compile_kwargs):
            await guardian.request_focus("ollama")
        try:
            positive, negative = compile_prompt(raw_desc, **_compile_kwargs)
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=f"Ollama 文字模型失敗，請確認 {state.get_text_model()} 已安裝：{e}")
        timings["compile_prompt"] = round(time.perf_counter() - t0, 1)

        # ── Compile ai_prompt separately (placed first → higher SD attention weight) ──
        extra_prefix = ""
        _ai_prompt_compiled = ""
        if use_ai_prompt and inp.ai_prompt and inp.ai_prompt.strip():
            t0 = time.perf_counter()
            # quality_prefix/suffix 只在主描述套一次，避免同一段 quality tag 被灌兩次
            # （P1：workflow profile 的 quality_suffix 與既有 quality_prefix 同一防重複邏輯）。
            _ai_overrides = {**_overrides, "quality_prefix_override": "", "quality_suffix_override": ""}
            _ai_compile_kwargs = dict(
                style=style, model=state.get_text_model(), **_ai_overrides,
            )
            # 同上：命中快取就不必為了它把 ComfyUI 的模型卸掉。
            if not prompt_cache_hit(inp.ai_prompt.strip(), **_ai_compile_kwargs):
                await guardian.request_focus("ollama")
            try:
                extra_compiled, _ = compile_prompt(
                    inp.ai_prompt.strip(), **_ai_compile_kwargs,
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
            suffix = _build_fullbody_suffix(bg_tag)
            width, height = _fullbody_canvas(inp.height)
            steps = _profile.steps

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

        # P5-5：畫風 tag／權重優先序（art_style DB > workflow profile > .env > 無）見
        # _resolve_style_extra()；未登錄 profile 時逐字等同改動前行為。
        style_extra, _style_weight = _resolve_style_extra(art_style, active_wf)
        # [CN-048] style weight!=1.0 時畫風 tags 加權並前置到 identity，讓畫風由 prompt 承擔、CN 可降權
        style_front = ""
        style_extra_str = ""
        if style_extra:
            if _style_weight != 1.0:
                _weighted = ", ".join(
                    f"({t.strip()}:{_style_weight})"
                    for t in style_extra.split(",") if t.strip()
                )
                style_front = f"{_weighted}, " if _weighted else ""
            else:
                style_extra_str = f", {style_extra}"

        final_positive = gender_prefix + body_prefix + style_front + extra_prefix + positive + suffix + gender_pos_extra + style_extra_str
        final_positive = _dedup_tags(final_positive)  # 去框架/眼睛等重複,收稀釋
        # E-2（2026-07-26）：剝除 LLM 自行吐出的多視圖/設定稿 tag（只作用於正向）。
        final_positive = _strip_sheet_tags(final_positive)

        extra_neg = ("detailed background, complex background, scenery, landscape, buildings, environment"
                     # 2026-06-21：抑制無端能量/火焰/光暈假影（不放 plain "glowing" 以免壓掉異色瞳/眼神光）
                     ", energy aura, glowing aura, flames, fire, burning, embers, magic effect, spell effect"
                     ", particle effects, glowing hands, energy effect, smoke"
                     )
        if not is_expression:
            extra_neg = f"{extra_neg}, {_FULLBODY_NEG_TAGS}"
            # E-1（2026-07-26）：多視圖抑制自 partial/bust 放寬到全 coverage —— 與正向端
            # 改走單張全身插畫同批；只改正向不改負向，工作流內建 wildcard 仍可能帶回多視圖。
            extra_neg += ", multiple views, reference sheet, design sheet, multiple poses, chibi inset, inset image, sketch overlay"
        base_neg = negative
        # [CN-049] negative 優先序 art_style > workflow profile > PERSONAL_NEGATIVE > family 預設
        if PERSONAL_NEGATIVE_ENABLED and PERSONAL_NEGATIVE and not _overrides.get("negative_override"):
            base_neg = PERSONAL_NEGATIVE
            # R4：negative_extra 為「補充」語義，須跨越 PERSONAL_NEGATIVE 取代仍生效。
            # 非此分支時 base_neg 已是 compile() 的輸出（negative_extra 已在 compile 內附加），不重覆加。
            _neg_extra = _overrides.get("negative_extra_override")
            if _neg_extra:
                base_neg = f"{base_neg}, {_neg_extra}"
        final_negative = f"{base_neg}, {extra_neg}{gender_neg_extra}" if base_neg else f"{extra_neg}{gender_neg_extra}"
        final_negative = _dedup_tags(final_negative)

    # A3 P0-1：seed<0（含預設 -1）＝維持現行隨機行為；>=0 則沿用呼叫端指定值，
    # 供「同 seed 連按兩次應輸出一致」的可重現實驗台驗收使用。
    seed = random.randint(0, 2**31 - 1) if seed < 0 else seed
    _canvas_expand_available = (CUSTOM_WORKFLOWS_DIR / _CANVAS_EXPAND_WF).exists()
    _canvas_expand_sdxl_available = (CUSTOM_WORKFLOWS_DIR / _CANVAS_EXPAND_SDXL_WF).exists()

    # [CN-050] 方案3：partial/bust 先用 SDXL inpaint 外擴成全身當 CN 參考；IPA 仍用原圖保身分
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
            # A3 P2-2：外擴輸入改用 _orig_ref_bytes（不受 IPA 閘控，Anima 一樣有概念圖）。
            _expanded = await _run_canvas_expand_sdxl(
                _orig_ref_bytes, _cn_coverage, final_positive, final_negative,
                width, height, seed, _main_ckpt,
            )
            timings["canvas_expand"] = round(time.perf_counter() - t0_pre, 1)
            # T3A：外擴輸出斷裂防線。偵測到幽靈下半身（主體內純背景空帶）→ 丟棄外擴、
            # 保留方案1 基線（先前已設好的 _shrink_for_full_body ref + 夾制 CN），coverage 不還原 full。
            if _EXPAND_BREAK_GUARD_ENABLED and _detect_body_break(_expanded):
                logger.warning(
                    "[%s] 方案3 外擴輸出偵測到主體斷裂（幽靈下半身）→ 丟棄外擴、回退方案1（縮圖+夾CN）",
                    log_label,
                )
                _expand_engine = _CANVAS_EXPAND_SDXL_WF  # 引擎仍記錄（已跑但丟棄）
            else:
                # [CN-051] 外擴輸出依家族寫回通道；cn_weight 已還原為使用者原值，下游按 full 計算
                if _profile.cn_enabled:
                    _cn_ref_bytes = _expanded
                else:
                    _i2i_ref_bytes = _expanded
                cn_weight = _cn_weight_user
                _cn_coverage = "full"
                _pre_ref_done = True
                _expand_engine = _CANVAS_EXPAND_SDXL_WF
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
            and _orig_ref_bytes is not None  # A3 P2-2：同上，改用不受 IPA 閘控的原始概念圖
            and _canvas_expand_available):
        t0 = time.perf_counter()
        logger.info("[%s] canvas-expand via Flux 2 (coverage=%s)", log_label, _cn_coverage)
        image_bytes = await _run_canvas_expand_flux(
            _orig_ref_bytes, _cn_coverage, final_positive, width, height, seed
        )
        timings["canvas_expand"] = round(time.perf_counter() - t0, 1)
        timings["total"] = round(time.perf_counter() - t_total, 1)
        timings["models"] = {"vision": state.get_vision_model(), "text": state.get_text_model(), "workflow": _CANVAS_EXPAND_WF, "canvas_expand": _CANVAS_EXPAND_WF}
        return Response(
            content=image_bytes,
            media_type="image/png",
            headers={
                "X-Seed": str(seed), "X-Style": style.value,
                "X-Flat-Draft": "1" if all_flat else "0",
                "X-IPA-Used": "0", "X-CN-Used": "0", "X-CN-Mode": "canvas_expand",
                "X-Raw-Desc": base64.b64encode(raw_desc.encode()).decode(),
                "X-Prompt": base64.b64encode(final_positive.encode()).decode(),
                "X-Prompt-Profile": base64.b64encode(_profile_source.encode()).decode(),
                "X-Coverage": base64.b64encode(
                    _coverage_badge(_cn_coverage, _cn_weight_user, cn_weight, cn_on=False,
                                    original=_coverage_original, pre_ref=_pre_ref_done).encode()
                ).decode(),
                "X-Timings": base64.b64encode(json.dumps(timings).encode()).decode(),
                "X-AI-Prompt-Compiled": "",
            },
        )

    # ── Generate（SDXL）────────────────────────────────────────────────────
    ipa_used = False

    global_lora = state.get_lora()
    lora_list = []
    # 全域 LoRA 僅 Checkpoint 模式生效；自訂 workflow 模式「LoRA 由 workflow 決定」→ 不注入。
    # （角色 / 畫風 LoRA 屬個別實體設定，仍注入。）
    if global_lora.get("name") and not _is_custom_workflow(active_wf):
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

    # [CN-052] pre-ref 成功時記憶體內把 Canny 換成 AnimeLineArt：Canny 會把彩圖陰影提成 noise 邊緣
    if _pre_ref_done:
        for _n in wf.values():
            if isinstance(_n, dict) and _n.get("class_type") == "CannyEdgePreprocessor":
                _n["class_type"] = "AnimeLineArtPreprocessor"
                _inp = _n.get("inputs", {})
                _inp.pop("low_threshold", None)
                _inp.pop("high_threshold", None)
                if "resolution" not in _inp:
                    _inp["resolution"] = 1024
                logger.info("[%s] 方案3：CannyEdgePreprocessor → AnimeLineArtPreprocessor（pre-ref 外擴圖相容）", log_label)

    # 統一注入管線：啟用且有圖 → 缺節點則建、有則沿用；停用或無圖 → 既有節點 bypass。
    need_ipa_inject = _ipa_ref_bytes is not None and not _wf_has_ipa(wf)
    need_cn_inject = _cn_ref_bytes is not None and not _wf_has_controlnet(wf)
    if need_ipa_inject or need_cn_inject:
        # SYNC-001：checkpoint 以工作流內嵌值為準（見 _wf_checkpoint docstring）。
        _inject_models = resolve_capability(wf, _wf_checkpoint(wf))["models"]
        # CN preprocessor：依 profile（illustrious=canny，復刻 V35 附件三品質）；
        # pre-ref 外擴為彩色圖 → Canny 會抓雜訊 → 強制 AnimeLineArt。
        if _pre_ref_done or _profile.cn_preprocessor != "canny":
            _cn_pp = {"type": "AnimeLineArtPreprocessor", "resolution": _profile.cn_resolution}
        else:
            _cn_pp = {"type": "CannyEdgePreprocessor", "low_threshold": _profile.cn_canny_low,
                      "high_threshold": _profile.cn_canny_high, "resolution": _profile.cn_resolution}
        _inject_ipa_cn_nodes(
            wf, inject_ipa=need_ipa_inject, inject_cn=need_cn_inject,
            models=_inject_models, cn_preprocessor=_cn_pp,
        )
        logger.info("[%s] 動態注入節點 ipa=%s cn=%s preproc=%s（工作流 '%s' 原缺節點）",
                    log_label, need_ipa_inject, need_cn_inject, _cn_pp["type"], active_wf)

    if _ipa_ref_bytes is not None:
        _t = time.perf_counter()
        # [CN-053] IPA 參考圖先 letterbox 成 1:1：CLIPImageProcessor 會置中裁切，直長條圖頭腳全被裁掉
        _ipa_bytes = _letterbox_to_aspect(_ipa_ref_bytes, 1, 1, label="ipa-letterbox")
        uploaded_ref = comfyui_client.upload_image_bytes(_ipa_bytes, "char_concept_ref.png")
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
    # [CN-054] 補 LoRA 觸發詞並放在 identity 之前；刻意不經 _dedup_tags（觸發詞含零寬空格）
    _lora_triggers = lora_trigger_words(lora_list)
    if _lora_triggers:
        final_positive = ", ".join(_lora_triggers) + ", " + final_positive
        logger.info("[%s] LoRA 觸發詞已補入正向：%s", log_label,
                    " | ".join(w.encode("unicode_escape").decode() for w in _lora_triggers))
    _inject_prompts(wf, final_positive, final_negative)
    # flat_draft（線稿/平塗概念圖）當 IPA 參考易把成像拉平 → 自動降 IPA 權重（下限 0.1）。
    _ipa_weight_eff = ipa_weight
    if ipa_used and all_flat and IPA_FLAT_DRAFT_SCALE < 1.0:
        _ipa_weight_eff = max(0.1, round(ipa_weight * IPA_FLAT_DRAFT_SCALE, 2))
        logger.info("[%s] flat_draft 概念圖 → IPA 權重 %.2f→%.2f（IPA_FLAT_DRAFT_SCALE=%.2f，避免平塗拉平）",
                    log_label, ipa_weight, _ipa_weight_eff, IPA_FLAT_DRAFT_SCALE)
    for _nid, node in list(wf.items()):
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        inputs = node.get("inputs", {})
        if ct == "EmptyLatentImage":
            # [CN-055] width/height 走 _set_node_input：部分作者型工作流是 easy int 節點參照，直寫只改到 latent
            _set_node_input(wf, _nid, "width", width)
            _set_node_input(wf, _nid, "height", height)
        elif ct == "KSampler":
            _set_node_input(wf, _nid, "seed", seed)
            # R3：steps=None（illustrious 家族現況）→ 不覆寫，沿用 workflow JSON 內建值
            # （如 V37 官方 28 步）；有值的家族維持既有覆寫行為，零回歸。
            if steps is not None:
                _set_node_input(wf, _nid, "steps", steps)
        elif ct == "IPAdapterAdvanced" and ipa_used:
            inputs["weight"] = round(_ipa_weight_eff, 2)
        elif ct in _CN_APPLY_TYPES and _cn_ref_bytes is not None:
            # [CN-056] 內建 CN 保留 workflow JSON 校準值，動態注入才吃滑桿；end_percent 兩者都設
            if need_cn_inject:
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

    # [CN-057] CN 替代路徑 img2img 低 denoise；SDXL 家族 _i2i_ref_bytes 恆 None，零回歸
    i2i_used = False
    i2i_denoise: float | None = None
    lllite_used = False
    lllite_weight_used: str | None = None
    # N1（SYNC-005）：先初始化，避免 LLLite 分支沒走到時，下方 params 組裝踩 NameError。
    # （條件運算式本來就不會求值 else 側，但依賴那個行為是脆弱前提——顯式初始化比較誠實。）
    _lllite_strength: float | None = None
    if _i2i_ref_bytes is not None:
        # [CN-058] 先色彩正規化再對齊畫布，順序不可對調（先色後形，避免縮放插值糊掉二值線稿）
        _i2i_bytes = _normalize_i2i_ref(_i2i_ref_bytes, prompt=final_positive)
        # [CN-059] img2img 與 lllite 兩條路都要先 letterbox：lllite 內部 F.interpolate 不保比例
        _i2i_bytes = _fit_to_canvas(_i2i_bytes, width, height)
        _t = time.perf_counter()

        # [CN-060] lllite（MODEL 層）與 img2img（latent 層）互斥，只走候選鏈中的一條
        _cn_mech = None
        _lllite_weight = None
        _lllite_node_class = None
        try:
            # [CN-061] 用工作流內嵌 checkpoint 解析 family，否則 cn_supported 誤判 True → 候選鏈永遠解析不到
            _cap_cn = resolve_capability(wf, _wf_checkpoint(wf))
            _cn_mech = _cap_cn.get("cn_fallback")
            _lllite_weight = _cap_cn.get("lllite_weight")
            _lllite_node_class = _cap_cn.get("lllite_node_class")
        except Exception as e:
            logger.warning("[%s] CN 替代機制解析失敗（%s）→ 退 img2img", log_label, e)

        if _cn_mech == "lllite" and _lllite_weight:
            _up = comfyui_client.upload_image_bytes(_i2i_bytes, "char_lllite_ref.png")
            timings["upload"] = round(timings.get("upload", 0.0) + (time.perf_counter() - _t), 1)
            # [CN-062] LLLite strength 與 CN weight 同向，不做 denoise 那種反向映射
            _end_pct = _profile.coverage_cn_end_pct.get(_cn_coverage, 1.0)
            # [CN-063] 滑桿值 × family scale 才是 LLLite strength：兩者尺度不同（LoRA-like 乘數 vs 0~1 權重）
            _lllite_strength = round(_cn_weight_user * _profile.lllite_strength_scale, 3)
            lllite_used = _inject_lllite(
                wf, _up, _lllite_weight, _lllite_strength, end_percent=_end_pct,
                node_class=_lllite_node_class,
            )
            if lllite_used:
                lllite_weight_used = _lllite_weight
                logger.info("[%s] CN 替代：LLLite 啟用（family=%s，滑桿=%.2f × scale=%.2f "
                            "→ strength=%.3f，end_pct=%.2f，weights=%s）— 真條件注入，latent 未被污染",
                            log_label, _gen_family, _cn_weight_user,
                            _profile.lllite_strength_scale, _lllite_strength,
                            _end_pct, _lllite_weight)
            else:
                logger.warning("[%s] CN 替代：LLLite 注入失敗 → 退 img2img", log_label)

        if not lllite_used:
            _i2i_uploaded = comfyui_client.upload_image_bytes(_i2i_bytes, "char_i2i_ref.png")
            timings["upload"] = round(timings.get("upload", 0.0) + (time.perf_counter() - _t), 1)
            i2i_denoise = _profile.img2img_denoise(_cn_weight_user)
            i2i_used = _inject_img2img(wf, _i2i_uploaded, i2i_denoise)
            if i2i_used:
                logger.info("[%s] CN 替代：img2img 啟用（family=%s，cn_weight=%.2f → denoise=%.2f）",
                            log_label, _gen_family, _cn_weight_user, i2i_denoise)
            else:
                i2i_denoise = None
                logger.warning("[%s] CN 替代：img2img 注入失敗（缺 KSampler 或 VAE）→ 退回純 txt2img",
                               log_label)

    _replace_negative_seeds(wf, seed)
    _log_wf_snapshot(wf, label=log_label)
    t0 = time.perf_counter()
    await guardian.request_focus("comfyui")
    image_bytes = await _run_comfyui(wf)
    timings["comfyui"] = round(time.perf_counter() - t0, 1)

    # [CN-064] canvas expand 僅限 coverage=full 且 CN 實際啟用；否則誤觸發 Flux（17GB）異常慢
    cn_mode_out = cn_mode
    if (canvas_expand_mode == "post"
            and not is_expression
            and _cn_coverage == "full"
            and not _pre_ref_done
            and _canvas_expand_available
            and cn_used):
        t0_expand = time.perf_counter()
        logger.info("[%s] canvas-expand via Flux 2 on SDXL output (coverage=%s)", log_label, _cn_coverage)
        try:
            image_bytes = await _run_canvas_expand_flux(
                image_bytes, _cn_coverage, final_positive, width, height, seed
            )
            timings["canvas_expand"] = round(time.perf_counter() - t0_expand, 1)
            _expand_engine = _CANVAS_EXPAND_WF
            cn_mode_out = "canvas_expand"
        except Exception as e:
            logger.warning("[%s] canvas-expand 失敗，使用 SDXL 輸出: %s", log_label, e)

    # S2-1/S2-2（2026-08-17）：結構控制機制要能從耗時表 / generation_history 一眼看出
    # 走了哪條路 —— 08-17 記錄附件 3 的耗時表看不出走 img2img 還是 LLLite，本輪補上。
    if lllite_used:
        _mechanism = "lllite"
    elif i2i_used:
        _mechanism = "img2img"
    elif cn_used:
        _mechanism = "controlnet"
    else:
        _mechanism = "none"

    timings["total"] = round(time.perf_counter() - t_total, 1)
    timings["mechanism"] = _mechanism
    timings["models"] = {
        "vision": state.get_vision_model(),
        "text": state.get_text_model(),
        "workflow": active_wf,
        "canvas_expand": _expand_engine,
    }

    _effective_steps = _effective_ksampler_steps(wf, steps)
    _effective_cfg = _effective_ksampler_cfg(wf)  # A3 P0-4：workflow 實際生效 cfg

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
            "width": width, "height": height, "steps": _effective_steps,
            "cfg": _effective_cfg,  # A3 P0-4：對應 D1（workflow 檔位/採樣參數 A/B 需要能單筆還原）
            "expression": expression, "art_style_id": art_style_id,
            "ipa_used": ipa_used, "ipa_weight": round(ipa_weight, 2),
            "cn_used": cn_used, "cn_weight": round(cn_weight, 2),
            "cn_mode": cn_mode_out, "coverage": _cn_coverage,
            "loras": lora_list, "use_ai_prompt": use_ai_prompt,
            "use_outfit": use_outfit, "timings": timings,
            # [CN-065] 底模必須入 DB：08-17 把「LLLite+換底模」誤記成純 LLLite 功勞，肇因就是沒記錄
            "checkpoint": extract_checkpoint_from_wf(wf),
            # [CN-066] prompt 配方來源要入 DB，否則檔名改版造成的靜默降級事後無法查
            "prompt_profile": _profile_source,
            "mechanism": _mechanism,
            "lllite_name": lllite_weight_used,
            # [CN-067] LLLite strength 改記「實際送出值」（滑桿×scale）；⚠️ #648 之前是滑桿值，比較前先看 id
            "lllite_strength": _lllite_strength if lllite_used else None,
            "img2img_denoise": round(i2i_denoise, 2) if i2i_used and i2i_denoise is not None else None,
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
            "X-Prompt-Profile": base64.b64encode(_profile_source.encode()).decode(),
            # [CN-068] cn_on badge 看三個訊號（cn_used / lllite / img2img），任一為真就顯示 coverage
            "X-Coverage": base64.b64encode(
                _coverage_badge(_cn_coverage, _cn_weight_user, cn_weight,
                                cn_on=(cn_used or lllite_used or i2i_used),
                                original=_coverage_original, pre_ref=_pre_ref_done).encode()
            ).decode(),
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
    use_vision: bool = True,
    use_ipa: bool = True,
    ipa_weight: float = 0.6,
    use_controlnet: bool = True,
    cn_weight: float = 0.65,   # 2026-06-24：草圖開 CN 0.85 整圖品質略差,預設降 0.65 測試
    seed: int = -1,            # A3 P0-1：-1=隨機（零回歸），>=0 沿用
    reuse_prompt: bool = False,  # A3 P0-3：沿用上次 prompt，不重新編譯
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
        use_ai_prompt=use_ai_prompt, use_outfit=use_outfit, use_vision=use_vision,
        use_ipa=use_ipa, ipa_weight=ipa_weight,
        use_controlnet=use_controlnet, cn_weight=cn_weight,
        canvas_expand_mode="pre", use_pixel_override=True,
        log_label="char-gen", record_endpoint="character_design",
        seed=seed, reuse_prompt=reuse_prompt,
    )


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
    cn_weight: float = 0.65,   # 2026-06-24：與 generate_character_design 同步降 0.65 測試
    seed: int = -1,            # A3 P0-1：-1=隨機（零回歸），>=0 沿用
    reuse_prompt: bool = False,  # A3 P0-3：沿用上次 prompt，不重新編譯
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
        use_ai_prompt=use_ai_prompt, use_outfit=use_outfit, use_vision=use_vision,
        use_ipa=use_ipa, ipa_weight=ipa_weight,
        use_controlnet=use_controlnet, cn_weight=cn_weight,
        canvas_expand_mode="post", use_pixel_override=False,
        log_label="variant-gen", record_endpoint="variant_design",
        seed=seed, reuse_prompt=reuse_prompt,
    )
