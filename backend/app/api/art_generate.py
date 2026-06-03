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
    found_in_custom = False
    for base in (CUSTOM_WORKFLOWS_DIR, _SYSTEM_WORKFLOW_DIR):
        path = base / name
        if path.exists():
            found_in_custom = (base == CUSTOM_WORKFLOWS_DIR)
            break
    else:
        raise FileNotFoundError(f"Workflow '{name}' not found in custom or system directories")
    logger.info("[wf-load] name=%s  path=%s  custom=%s", name, path, found_in_custom)
    with open(path, encoding="utf-8") as f:
        wf = json.load(f)
    print(f"[CRAFTFLOW-DEBUG-FILE] loaded {path} → {len(wf)} top-level keys, is_ui={'nodes' in wf}", flush=True)
    wf.pop("_comment", None)

    # Detect ComfyUI UI-format workflows (exported via "Save", not "Save (API format)")
    # UI format has top-level keys like "nodes" (list), "links", "last_node_id" — these are
    # not valid node dicts and will cause TypeErrors in ComfyUI's on_prompt handlers.
    if isinstance(wf.get("nodes"), list):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Workflow '{name}' 是 ComfyUI UI 格式（含 'nodes' 陣列），無法直接使用。"
                " 請在 ComfyUI 重新匯出：Settings → Enable Dev mode options → Save (API format)。"
            ),
        )

    # Custom workflows keep their own embedded checkpoint; only system workflows
    # respect the global checkpoint selection so the UI "checkpoint" picker takes effect.
    global_ckpt = state.get_checkpoint()
    if not found_in_custom:
        if global_ckpt:
            for node in wf.values():
                if isinstance(node, dict) and node.get("class_type") == "CheckpointLoaderSimple":
                    node["inputs"]["ckpt_name"] = global_ckpt
            logger.info("[wf-load] system workflow → checkpoint overridden to: %s", global_ckpt)
        else:
            logger.info("[wf-load] system workflow → no global checkpoint set, using embedded value")
    else:
        embedded_ckpt = next(
            (n["inputs"].get("ckpt_name", "<none>")
             for n in wf.values()
             if isinstance(n, dict) and n.get("class_type") == "CheckpointLoaderSimple"),
            "<no CheckpointLoaderSimple node>",
        )
        logger.info(
            "[wf-load] custom workflow → checkpoint NOT overridden  "
            "embedded=%s  global_state=%s",
            embedded_ckpt, global_ckpt,
        )
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


def _replace_negative_seeds(wf: dict, seed: int) -> None:
    """Replace seed=-1 in any node that carries a seed widget (KSampler, rgthree Seed, etc.).

    Only replaces when the current value is -1 (the ComfyUI "random each run" sentinel)
    and the value is a plain int (not a link reference list).
    """
    for node in wf.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        if isinstance(inputs.get("seed"), int) and inputs["seed"] < 0:
            inputs["seed"] = seed
        if isinstance(inputs.get("noise_seed"), int) and inputs["noise_seed"] < 0:
            inputs["noise_seed"] = seed


def _log_wf_snapshot(wf: dict, label: str = "") -> None:
    """Log the checkpoint / KSampler settings actually present in the workflow before submission."""
    prefix = f"[wf-snapshot{' ' + label if label else ''}]"
    for nid, node in wf.items():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        inp = node.get("inputs", {})
        if ct == "CheckpointLoaderSimple":
            logger.info("%s node=%s  CheckpointLoaderSimple  ckpt_name=%s", prefix, nid, inp.get("ckpt_name"))
        elif ct == "UNETLoader":
            logger.info("%s node=%s  UNETLoader  unet_name=%s", prefix, nid, inp.get("unet_name"))
        elif ct == "KSampler":
            logger.info(
                "%s node=%s  KSampler  seed=%s  steps=%s  cfg=%s  sampler=%s  scheduler=%s  denoise=%s",
                prefix, nid,
                inp.get("seed"), inp.get("steps"), inp.get("cfg"),
                inp.get("sampler_name"), inp.get("scheduler"), inp.get("denoise"),
            )
        elif ct == "IPAdapterAdvanced":
            logger.info("%s node=%s  IPAdapterAdvanced  weight=%s", prefix, nid, inp.get("weight"))
        elif ct == "LoraLoader":
            logger.info("%s node=%s  LoraLoader  lora=%s  str_model=%s", prefix, nid, inp.get("lora_name"), inp.get("strength_model"))


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

    _replace_negative_seeds(wf, seed)
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


_IPA_NODE_TYPES = {"IPAdapterAdvanced", "IPAdapter"}


def _wf_has_ipa(wf: dict) -> bool:
    """Return True if the workflow contains any IP-Adapter node."""
    return any(
        isinstance(n, dict) and n.get("class_type") in _IPA_NODE_TYPES
        for n in wf.values()
    )


def _find_ipa_loadimage_id(wf: dict) -> str | None:
    """
    BFS backward from IPAdapterAdvanced.image input until a LoadImage node is found.
    Handles arbitrary chains: LoadImage → CLIPVisionEncode → IPAdapterAdvanced, etc.
    Returns the node_id string or None.
    """
    # Find IPA node and get its image input reference
    ipa_img_ref: str | None = None
    for node in wf.values():
        if isinstance(node, dict) and node.get("class_type") in _IPA_NODE_TYPES:
            ref = node.get("inputs", {}).get("image")
            if isinstance(ref, list) and ref:
                ipa_img_ref = str(ref[0])
            break

    if ipa_img_ref is None:
        return None

    visited: set[str] = set()
    queue = [ipa_img_ref]
    while queue:
        nid = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)
        node = wf.get(nid)
        if not isinstance(node, dict):
            continue
        if node.get("class_type") == "LoadImage":
            return nid
        for val in node.get("inputs", {}).values():
            if isinstance(val, list) and val:
                upstream = str(val[0])
                if upstream not in visited:
                    queue.append(upstream)
    return None


def _inject_ipa_image(wf: dict, uploaded_name: str) -> bool:
    """
    Inject reference image only into the LoadImage node that feeds IPAdapterAdvanced.
    Returns True on success, False if the chain wasn't found (workflow will still run,
    just without the reference injection).
    """
    node_id = _find_ipa_loadimage_id(wf)
    if node_id and node_id in wf:
        wf[node_id]["inputs"]["image"] = uploaded_name
        logger.debug("[ipa-inject] reference → LoadImage node %s", node_id)
        return True
    logger.warning("[ipa-inject] LoadImage not found in IPA chain — skipping reference injection")
    return False


def _bypass_ipa_nodes(wf: dict) -> None:
    """
    Remove IPA nodes from an API-format workflow when no reference image is provided.
    Rewires: upstream_model → IPAdapterAdvanced → KSampler
         to: upstream_model → KSampler
    """
    ipa_id: str | None = None
    ipa_upstream_model = None
    for nid, node in wf.items():
        if isinstance(node, dict) and node.get("class_type") in _IPA_NODE_TYPES:
            ipa_id = nid
            ipa_upstream_model = node.get("inputs", {}).get("model")
            break

    if ipa_id is None or not isinstance(ipa_upstream_model, list):
        return

    ipa_node = wf[ipa_id]
    to_remove: set[str] = {ipa_id}
    for key in ("ipadapter", "image", "clip_vision"):
        ref = ipa_node.get("inputs", {}).get(key)
        if isinstance(ref, list) and ref:
            src_id = str(ref[0])
            if src_id in wf:
                to_remove.add(src_id)

    for nid, node in wf.items():
        if not isinstance(node, dict) or nid in to_remove:
            continue
        for key, val in node.get("inputs", {}).items():
            if isinstance(val, list) and len(val) >= 2 and str(val[0]) == ipa_id and val[1] == 0:
                node["inputs"][key] = ipa_upstream_model
                logger.info("[ipa-bypass] rewired %s.%s → %s", nid, key, ipa_upstream_model)

    for nid in to_remove:
        ct = (wf[nid].get("class_type", "?") if nid in wf else "?")
        wf.pop(nid, None)
        logger.debug("[ipa-bypass] removed node %s (%s)", nid, ct)


# ── ControlNet helpers ────────────────────────────────────────────────────────

_CN_APPLY_TYPES = {"ControlNetApplyAdvanced", "ControlNetApply"}
_CN_PREPROCESSOR_TYPES = {
    "AIO_Preprocessor", "LineArtPreprocessor", "AnimeLineArtPreprocessor",
    "DepthAnythingPreprocessor", "MiDaS-DepthMapPreprocessor",
    "DWPreprocessor", "OpenposePreprocessor", "CannyEdgePreprocessor",
    "HEDPreprocessor", "ScribblePreprocessor",
}


def _wf_has_controlnet(wf: dict) -> bool:
    """Return True if the workflow contains ControlNet apply nodes."""
    return any(
        isinstance(n, dict) and n.get("class_type") in _CN_APPLY_TYPES
        for n in wf.values()
    )


# ── 動態節點注入（工作流缺 IPA / CN 節點時補上）────────────────────────────────
# 模型檔名沿用既有 Standard_V35.json（已確認存在於 ComfyUI），避免硬編不存在的檔。
_IPA_CLIPVISION_MODEL = "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"
_IPA_ADAPTER_MODEL = "ip-adapter-plus_sdxl_vit-h.safetensors"
_CN_MODEL = "diffusion_pytorch_model_promax.safetensors"
_CN_UNION_TYPE = "canny/lineart/anime_lineart/mlsd"  # 照抄 Standard_V35（運作中的值）
# 佔位圖檔名；實際參考圖會由 _inject_ipa_image / _inject_controlnet_image 覆寫
_IPA_PLACEHOLDER_IMAGE = "char_concept_ref.png"
_CN_PLACEHOLDER_IMAGE = "char_cn_ref.png"
# Canny 預處理參數（與 Standard_V35 一致）
_CANNY_LOW, _CANNY_HIGH, _CANNY_RES = 100, 200, 1024
# ControlNet 套用範圍（end=0.85：CN 權重需 ≥0.85 才夠貼合，見開發記錄 CN 權重偏好）
_CN_START_PERCENT, _CN_END_PERCENT = 0.0, 0.85
# 注入節點的預設強度；實際值由端點依前端傳入的 ipa_weight / cn_weight 覆寫
_IPA_DEFAULT_WEIGHT, _CN_DEFAULT_STRENGTH = 0.6, 0.85


def _find_main_ksampler_id(wf: dict) -> str | None:
    """回傳主取樣 KSampler 的 node id。

    單一 KSampler → 直接回傳。
    多 KSampler（如 hires-fix）→ 取 denoise==1.0 的主路徑，避免命中二次取樣；
    皆無法判定時回傳第一個。
    """
    ks_ids = [
        k for k, n in wf.items()
        if isinstance(n, dict) and n.get("class_type") == "KSampler"
    ]
    if not ks_ids:
        return None
    if len(ks_ids) == 1:
        return ks_ids[0]
    for k in ks_ids:
        denoise = wf[k].get("inputs", {}).get("denoise")
        if isinstance(denoise, (int, float)) and abs(denoise - 1.0) < 1e-6:
            return k
    return ks_ids[0]


def _inject_ipa_cn_nodes(wf: dict, *, inject_ipa: bool, inject_cn: bool) -> None:
    """當工作流缺少 IPA / ControlNet 節點時，依 Standard_V35 模板動態建立並接線。

    - IPA：在「現有 model 來源 → KSampler.model」之間插入 IPAdapterAdvanced 鏈。
    - CN ：在「現有 positive/negative → KSampler」之間插入 ControlNetApplyAdvanced 鏈。

    僅在對應功能啟用且工作流本身沒有該節點時呼叫（由端點判斷）；既有節點不重複注入。
    節點 id 從現有最大數字 +1 起遞增，確保不衝突。圖片由後續 _inject_*_image 注入。
    """
    ks_id = _find_main_ksampler_id(wf)
    if ks_id is None:
        logger.warning("[wf-inject] 找不到 KSampler，略過節點注入")
        return
    ks_inputs = wf[ks_id].setdefault("inputs", {})

    next_id = max((int(k) for k in wf if k.isdigit()), default=0) + 1

    def _new_id() -> str:
        nonlocal next_id
        nid = str(next_id)
        next_id += 1
        return nid

    if inject_ipa:
        model_src = ks_inputs.get("model")  # 現有 model 來源（通常 CheckpointLoaderSimple）
        clipvision_id, ipamodel_id, loadimg_id, ipa_id = (
            _new_id(), _new_id(), _new_id(), _new_id(),
        )
        wf[clipvision_id] = {
            "class_type": "CLIPVisionLoader",
            "inputs": {"clip_name": _IPA_CLIPVISION_MODEL},
        }
        wf[ipamodel_id] = {
            "class_type": "IPAdapterModelLoader",
            "inputs": {"ipadapter_file": _IPA_ADAPTER_MODEL},
        }
        wf[loadimg_id] = {
            "class_type": "LoadImage",
            "inputs": {"image": _IPA_PLACEHOLDER_IMAGE, "upload": "image"},
        }
        wf[ipa_id] = {
            "class_type": "IPAdapterAdvanced",
            "inputs": {
                "model": model_src,
                "ipadapter": [ipamodel_id, 0],
                "image": [loadimg_id, 0],
                "clip_vision": [clipvision_id, 0],
                "weight": _IPA_DEFAULT_WEIGHT,
                "weight_type": "linear",
                "combine_embeds": "concat",
                "start_at": 0,
                "end_at": 1,
                "embeds_scaling": "V only",
            },
        }
        ks_inputs["model"] = [ipa_id, 0]
        logger.info("[wf-inject] IPA 鏈已注入：KSampler(%s).model ← IPAdapterAdvanced(%s)", ks_id, ipa_id)

    if inject_cn:
        pos_src = ks_inputs.get("positive")
        neg_src = ks_inputs.get("negative")
        cnloader_id, settype_id, canny_id, loadimg_id, cnapply_id = (
            _new_id(), _new_id(), _new_id(), _new_id(), _new_id(),
        )
        wf[cnloader_id] = {
            "class_type": "ControlNetLoader",
            "inputs": {"control_net_name": _CN_MODEL},
        }
        wf[settype_id] = {
            "class_type": "SetUnionControlNetType",
            "inputs": {"control_net": [cnloader_id, 0], "type": _CN_UNION_TYPE},
        }
        wf[loadimg_id] = {
            "class_type": "LoadImage",
            "inputs": {"image": _CN_PLACEHOLDER_IMAGE, "upload": "image"},
        }
        wf[canny_id] = {
            "class_type": "CannyEdgePreprocessor",
            "inputs": {
                "image": [loadimg_id, 0],
                "low_threshold": _CANNY_LOW,
                "high_threshold": _CANNY_HIGH,
                "resolution": _CANNY_RES,
            },
        }
        wf[cnapply_id] = {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": pos_src,
                "negative": neg_src,
                "control_net": [settype_id, 0],
                "image": [canny_id, 0],
                "strength": _CN_DEFAULT_STRENGTH,
                "start_percent": _CN_START_PERCENT,
                "end_percent": _CN_END_PERCENT,
            },
        }
        ks_inputs["positive"] = [cnapply_id, 0]
        ks_inputs["negative"] = [cnapply_id, 1]
        logger.info(
            "[wf-inject] CN 鏈已注入：KSampler(%s).positive/negative ← ControlNetApplyAdvanced(%s)",
            ks_id, cnapply_id,
        )


def _inject_controlnet_image(wf: dict, uploaded_name: str) -> int:
    """
    Inject reference image into all LoadImage nodes that feed ControlNet preprocessors.
    Returns the number of LoadImage nodes updated.
    """
    # Build set of node IDs that are ControlNet preprocessors
    preprocessor_ids: set[str] = set()
    for nid, node in wf.items():
        if isinstance(node, dict) and node.get("class_type") in _CN_PREPROCESSOR_TYPES:
            preprocessor_ids.add(nid)

    # Also treat LoadImage nodes feeding directly into ControlNetApply as targets
    cn_apply_image_sources: set[str] = set()
    for nid, node in wf.items():
        if isinstance(node, dict) and node.get("class_type") in _CN_APPLY_TYPES:
            ref = node.get("inputs", {}).get("image")
            if isinstance(ref, list) and ref:
                cn_apply_image_sources.add(str(ref[0]))

    # Collect LoadImage nodes that feed preprocessors or ControlNet directly
    updated = 0
    for nid, node in wf.items():
        if not isinstance(node, dict) or node.get("class_type") != "LoadImage":
            continue
        # Check if this LoadImage's output is consumed by a preprocessor or CN apply
        is_cn_source = False
        if nid in cn_apply_image_sources:
            is_cn_source = True
        if not is_cn_source:
            for pid in preprocessor_ids:
                pnode = wf.get(pid, {})
                for val in pnode.get("inputs", {}).values():
                    if isinstance(val, list) and val and str(val[0]) == nid:
                        is_cn_source = True
                        break
        if is_cn_source:
            node["inputs"]["image"] = uploaded_name
            logger.info("[cn-inject] reference → LoadImage node %s", nid)
            updated += 1

    if updated == 0:
        logger.warning("[cn-inject] no ControlNet LoadImage found — skipping")
    return updated


def _bypass_controlnet_nodes(wf: dict) -> None:
    """
    Remove ControlNet nodes from an API-format workflow when CN is disabled or
    has no reference image. Stripping the CN chain means fewer nodes execute
    (no preprocessor / controlnet model load) → faster generation.

    ControlNetApplyAdvanced has *dual* conditioning outputs:
        positive (slot 0) and negative (slot 1).
    These are rewired back to the apply node's own upstream positive/negative
    conditioning, then the CN-only node chain (apply, loader, union-type,
    preprocessor, CN LoadImage) is stripped.

    Asymmetric with _bypass_ipa_nodes (which rewires a single model output);
    here two conditioning lines must be restored independently.
    """
    apply_id: str | None = None
    for nid, node in wf.items():
        if isinstance(node, dict) and node.get("class_type") in _CN_APPLY_TYPES:
            apply_id = nid
            break
    if apply_id is None:
        return

    apply_node = wf[apply_id]
    up_pos = apply_node.get("inputs", {}).get("positive")
    up_neg = apply_node.get("inputs", {}).get("negative")
    # Only proceed if both conditioning inputs are graph edges we can restore.
    if not (isinstance(up_pos, list) and up_pos) or not (isinstance(up_neg, list) and up_neg):
        logger.warning("[cn-bypass] apply node %s missing conditioning edges — skip bypass", apply_id)
        return

    # 1) Rewire consumers of the apply node's two outputs back to upstream conditioning.
    for nid, node in wf.items():
        if not isinstance(node, dict) or nid == apply_id:
            continue
        for key, val in node.get("inputs", {}).items():
            if isinstance(val, list) and len(val) >= 2 and str(val[0]) == apply_id:
                if val[1] == 0:
                    node["inputs"][key] = up_pos
                    logger.info("[cn-bypass] rewired %s.%s → positive %s", nid, key, up_pos)
                elif val[1] == 1:
                    node["inputs"][key] = up_neg
                    logger.info("[cn-bypass] rewired %s.%s → negative %s", nid, key, up_neg)

    # 2) Collect CN-only nodes by walking upstream via control_net & image edges
    #    (NOT positive/negative — those are shared conditioning that must survive).
    to_remove: set[str] = {apply_id}
    queue: list[str] = []
    for key in ("control_net", "image"):
        ref = apply_node.get("inputs", {}).get(key)
        if isinstance(ref, list) and ref:
            queue.append(str(ref[0]))
    while queue:
        nid = queue.pop()
        if nid in to_remove or nid not in wf:
            continue
        to_remove.add(nid)
        for val in wf[nid].get("inputs", {}).values():
            if isinstance(val, list) and val:
                queue.append(str(val[0]))

    # 3) Safety: never delete a node still referenced by a surviving node
    #    (guards against removing a shared upstream node).
    for nid in sorted(to_remove, key=lambda x: int(x) if x.isdigit() else 0):
        referenced_outside = any(
            isinstance(node, dict)
            and oid not in to_remove
            and any(
                isinstance(v, list) and v and str(v[0]) == nid
                for v in node.get("inputs", {}).values()
            )
            for oid, node in wf.items()
        )
        if referenced_outside:
            logger.debug("[cn-bypass] keep node %s (still referenced outside CN chain)", nid)
            continue
        ct = wf[nid].get("class_type", "?")
        wf.pop(nid, None)
        logger.debug("[cn-bypass] removed node %s (%s)", nid, ct)


def _border_color(im) -> tuple[int, int, int]:
    """取概念圖四角與上下緣中點的平均色，作為 letterbox 補邊色（與背景一致 → Canny 無接縫）。"""
    w, h = im.size
    px = im.load()
    pts = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1], px[w // 2, 0], px[w // 2, h - 1]]
    n = len(pts)
    return (sum(p[0] for p in pts) // n, sum(p[1] for p in pts) // n, sum(p[2] for p in pts) // n)


def _letterbox_to_aspect(image_bytes: bytes, target_w: int, target_h: int) -> bytes:
    """
    把概念圖補邊（letterbox）成與生成畫布相同比例，避免 ComfyUI 對 ControlNet hint 圖
    做置中裁切而切掉頭/腳（窄長草圖塞進較寬畫布 → 上下被裁 → 只剩中段）。
    補邊用取樣背景色，置中貼上，整張全身（含草圖姿勢）等比保留。
    """
    im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = im.size
    target_ar = target_w / target_h
    src_ar = w / h
    if abs(src_ar - target_ar) < 1e-3:
        return image_bytes  # 比例已相符，免處理
    if src_ar < target_ar:        # 太窄 → 左右補邊
        new_w, new_h = round(h * target_ar), h
    else:                         # 太寬 → 上下補邊
        new_w, new_h = w, round(w / target_ar)
    canvas = Image.new("RGB", (new_w, new_h), _border_color(im))
    canvas.paste(im, ((new_w - w) // 2, (new_h - h) // 2))
    out = io.BytesIO()
    canvas.save(out, "PNG")
    logger.info("[cn-letterbox] %sx%s → %sx%s (target_ar=%.3f)", w, h, new_w, new_h, target_ar)
    return out.getvalue()


def _inject_prompts(wf: dict, positive: str, negative: str) -> None:
    """Inject positive/negative prompts into CLIPTextEncode nodes.

    Strategy (in order, stops as soon as both are resolved):
      1. Trace KSampler.positive / KSampler.negative graph edges back to CLIPTextEncode nodes.
         This is reliable for any workflow structure regardless of node titles or content.
      2. _meta.title containing "positive" / "negative" (fallback for unusual topologies)
      3. First two CLIPTextEncode nodes by node-id order (last resort)

    The original text content of CLIPTextEncode nodes is never read — only overwritten.
    """
    clips = {
        nid: node for nid, node in wf.items()
        if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode"
    }
    if not clips:
        return

    pos_injected = neg_injected = False

    # Pass 1: follow KSampler edges — most reliable, works for any workflow
    for node in wf.values():
        if not isinstance(node, dict) or node.get("class_type") != "KSampler":
            continue
        inp = node.get("inputs", {})
        for slot, flag, text in (
            ("positive", "pos", positive),
            ("negative", "neg", negative),
        ):
            ref = inp.get(slot)
            if isinstance(ref, list) and ref:
                target_id = str(ref[0])
                if target_id in clips:
                    clips[target_id]["inputs"]["text"] = text
                    if slot == "positive":
                        pos_injected = True
                    else:
                        neg_injected = True
                    logger.debug("[inject-prompts] KSampler.%s → node %s", slot, target_id)

    if pos_injected and neg_injected:
        return

    # Pass 2: _meta.title keywords
    for nid, node in clips.items():
        title = (node.get("_meta") or {}).get("title", "").lower()
        if not pos_injected and "positive" in title:
            node["inputs"]["text"] = positive
            pos_injected = True
            logger.debug("[inject-prompts] title match positive → node %s", nid)
        elif not neg_injected and "negative" in title:
            node["inputs"]["text"] = negative
            neg_injected = True
            logger.debug("[inject-prompts] title match negative → node %s", nid)

    if pos_injected and neg_injected:
        return

    # Pass 3: first two nodes by sorted id
    sorted_ids = sorted(clips.keys(), key=lambda x: int(x) if x.isdigit() else 0)
    if not pos_injected and sorted_ids:
        clips[sorted_ids[0]]["inputs"]["text"] = positive
        logger.debug("[inject-prompts] fallback positive → node %s", sorted_ids[0])
    if not neg_injected and len(sorted_ids) > 1:
        clips[sorted_ids[1]]["inputs"]["text"] = negative
        logger.debug("[inject-prompts] fallback negative → node %s", sorted_ids[1])


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

# ── 全身人設取景常數（痛點3）─────────────────────────────────────────────────
# 強化整體取景與手部/四肢補全，避免只生成中段（下巴到大腿）。集中為具名常數，
# 避免 magic string 散落於主角色與變體兩處生成流程。
_FULLBODY_POS_TAGS = (
    "full body shot, head to toe, full body visible, standing, detailed hands, five fingers"
)
# 全身專屬負向：抑制裁切/特寫構圖，並補全手指相關防護（部分底模預設未含）。
_FULLBODY_NEG_TAGS = (
    "cropped, out of frame, cut off, close-up, portrait, "
    "missing fingers, extra digits, bad hands, fused fingers"
)
# 全身畫布比例：依角色身形自動選取（「自動匹配大小」）。皆為 64 倍數、約 1MP，
# 貼近 SDXL 訓練分佈。高瘦 → 更長縱向畫布（多給頭/腳空間，減少裁切）；矮/幼態 → 較方。
_FULLBODY_CANVAS_TALL = (768, 1344)    # 身高 ≥170：高挑/長腿
_FULLBODY_CANVAS_STD = (832, 1216)     # 標準成人比例（預設）
_FULLBODY_CANVAS_SHORT = (896, 1152)   # 身高 <150 或幼態：矮/Q版
# 身高分界（cm）
_FULLBODY_TALL_CM = 170
_FULLBODY_SHORT_CM = 150
_FULLBODY_WIDTH, _FULLBODY_HEIGHT = _FULLBODY_CANVAS_STD



def _fullbody_canvas(height) -> tuple[int, int]:
    """依角色身高自動選全身畫布比例；身高未知或無法解析則用標準比例。"""
    try:
        h = float(height) if height not in (None, "") else None
    except (TypeError, ValueError):
        h = None
    if h is None:
        return _FULLBODY_CANVAS_STD
    if h >= _FULLBODY_TALL_CM:
        return _FULLBODY_CANVAS_TALL
    if h < _FULLBODY_SHORT_CM:
        return _FULLBODY_CANVAS_SHORT
    return _FULLBODY_CANVAS_STD


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
        # txt2img 模式（線稿風）
        final_prompt = sdxl_prompt.rstrip(", ") + ", full body, complete character, all limbs visible, white background, monochrome, lineart, clean lines, no shading, no color"
        wf = _load_workflow(active_wf)
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

    _replace_negative_seeds(wf, seed)
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


def _detect_body_coverage(image_bytes: bytes) -> str:
    """
    Use the configured vision model to classify how much of the body is shown.
    Returns: "full" | "partial" | "bust"
    - full:    legs and feet visible
    - partial: torso visible but legs cut off (upper body / three-quarter)
    - bust:    face / shoulders only
    Falls back to "partial" on any error.
    """
    prompt = (
        "Look at this character illustration. How much of the body is shown?\n"
        "Reply with exactly one word:\n"
        "- 'full' if legs and feet are visible\n"
        "- 'partial' if the torso is shown but legs are cut off\n"
        "- 'bust' if only the face or shoulders are shown\n"
        "One word only."
    )
    try:
        result = _oc.analyze_image_bytes(image_bytes, prompt, model=state.get_vision_model())
        result = result.strip().lower().split()[0] if result.strip() else ""
        if result in ("full", "partial", "bust"):
            return result
        # fuzzy match
        if any(k in result for k in ("full", "whole", "entire", "feet", "leg")):
            return "full"
        if any(k in result for k in ("bust", "face", "head", "shoulder")):
            return "bust"
        return "partial"
    except Exception as e:
        logger.warning("[body-coverage] detection failed: %s — defaulting to partial", e)
        return "partial"


_BODY_FILL_RATIO = {"full": 1.0, "partial": 0.72, "bust": 0.55}
_BODY_TOP_OFFSET = {"full": 0.0, "partial": 0.04, "bust": 0.05}


def _shrink_for_full_body(image_bytes: bytes, target_w: int, target_h: int, coverage: str) -> bytes:
    """
    Scale down the CN reference image so the character occupies only part of the canvas,
    leaving room at the bottom for SD to generate the missing lower body.
    coverage: "full" → no change (returns original for normal letterbox path)
              "partial" → ~72 % canvas height, 4 % top offset
              "bust"    → ~55 % canvas height, 5 % top offset
    """
    fill = _BODY_FILL_RATIO.get(coverage, 0.72)
    if fill >= 1.0:
        return image_bytes
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        max_h = int(target_h * fill)
        max_w = target_w
        scale = min(max_w / w, max_h / h)
        new_w, new_h = int(w * scale), int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

        bg = _border_color(img)
        canvas = Image.new("RGB", (target_w, target_h), bg)
        top = int(target_h * _BODY_TOP_OFFSET.get(coverage, 0.04))
        left = (target_w - new_w) // 2
        canvas.paste(img, (left, top))

        out = io.BytesIO()
        canvas.save(out, format="PNG")
        return out.getvalue()
    except Exception as e:
        logger.error("[shrink-full-body] error: %s", e)
        return image_bytes


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
    if age <= 12:
        return "child, young girl, youthful, childlike features, round face, flat chest, small hands"
    if age <= 14:
        return "young girl, youthful, flat chest"
    if age <= 17:
        return "teenage girl, youthful"
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
    print(f"[CRAFTFLOW-DEBUG] generate_character_design called: char={character_id} use_ipa={use_ipa} use_controlnet={use_controlnet}", flush=True)
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

    _ipa_ref_bytes: bytes | None = None       # concept image for IP-Adapter
    _cn_ref_bytes: bytes | None = None        # concept image for ControlNet

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

        # ControlNet: same concept image drives pose/structure guidance
        if use_controlnet and valid_images:
            _cn_ref_bytes = valid_images[0]
            if not is_expression:
                # Full-body mode: detect how much body the reference shows and shrink
                # the CN hint so SD has canvas space to generate missing lower body.
                await guardian.request_focus("ollama")
                coverage = _detect_body_coverage(_cn_ref_bytes)
                _exp_w, _exp_h = _fullbody_canvas(getattr(character, 'height', None))
                _cn_ref_bytes = _shrink_for_full_body(_cn_ref_bytes, _exp_w, _exp_h, coverage)
                logger.info("[char-gen] body_coverage=%s → CN reference adjusted", coverage)

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
            f", {_FULLBODY_POS_TAGS}"
            ", simple background, flat background, no background detail, no scenery" + bg_tag
        )
        # 畫布比例依角色身高自動匹配（高瘦更長、矮/幼態較方），減少頭/腳裁切
        width, height = _fullbody_canvas(getattr(character, 'height', None))
        steps = 25

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
    # 負向：art_style 有設定 → 優先；否則若 PERSONAL_NEGATIVE_ENABLED → 使用個人負向
    base_neg = negative
    if PERSONAL_NEGATIVE_ENABLED and PERSONAL_NEGATIVE and not (art_style and art_style.negative):
        base_neg = PERSONAL_NEGATIVE
    final_negative = f"{base_neg}, {extra_neg}{gender_neg_extra}" if base_neg else f"{extra_neg}{gender_neg_extra}"

    # ── Generate ──────────────────────────────────────────────────────────
    seed = random.randint(0, 2**31 - 1)
    ipa_used = False
    active_wf = state.get_workflow()
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
        uploaded_ref = comfyui_client.upload_image_bytes(_ipa_ref_bytes, "char_concept_ref.png")
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
    _inject_loras(wf, art_style.loras if art_style else [])
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
        uploaded_cn_ref = comfyui_client.upload_image_bytes(cn_bytes, "char_cn_ref.png")
        _inject_controlnet_image(wf, uploaded_cn_ref)
        cn_used = True
        logger.info("[char-gen] ControlNet (%s) injected, weight=%.2f", cn_mode, cn_weight)

    _replace_negative_seeds(wf, seed)
    _log_wf_snapshot(wf, label="char-gen")
    # TEMP DEBUG
    print(f"[CRAFTFLOW-DEBUG2] ipa_used={ipa_used} cn_used={cn_used} cn_ref={'yes' if _cn_ref_bytes else 'no'}", flush=True)
    print(f"[CRAFTFLOW-DEBUG3] wf_nodes={[v.get('class_type') for v in wf.values() if isinstance(v,dict)]}", flush=True)
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
            # IP-Adapter: use first available image when enabled (flat drafts included)
            if use_ipa:
                _ipa_ref_bytes = valid_images[0]
            if use_controlnet:
                _cn_ref_bytes = valid_images[0]
                if not is_expression:
                    await guardian.request_focus("ollama")
                    coverage = _detect_body_coverage(_cn_ref_bytes)
                    _exp_w, _exp_h = _fullbody_canvas(v.get("height"))
                    _cn_ref_bytes = _shrink_for_full_body(_cn_ref_bytes, _exp_w, _exp_h, coverage)
                    logger.info("[variant-gen] body_coverage=%s → CN reference adjusted", coverage)
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
            f", {_FULLBODY_POS_TAGS}"
            ", simple background, flat background, no background detail, no scenery" + bg_tag
        )
        # 畫布比例依角色身高自動匹配（變體用變體身高）
        width, height = _fullbody_canvas(v.get("height"))
        steps = 25

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
    base_neg = negative
    if PERSONAL_NEGATIVE_ENABLED and PERSONAL_NEGATIVE and not (art_style and art_style.negative):
        base_neg = PERSONAL_NEGATIVE
    final_negative = f"{base_neg}, {extra_neg}{gender_neg_extra}" if base_neg else f"{extra_neg}{gender_neg_extra}"

    # ── Generate ──────────────────────────────────────────────────────────
    seed = random.randint(0, 2**31 - 1)
    ipa_used = False
    active_wf = state.get_workflow()
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
        uploaded_ref = comfyui_client.upload_image_bytes(_ipa_ref_bytes, "char_concept_ref.png")
        ipa_used = True
        logger.info("[variant-gen] IP-Adapter 啟用（active workflow '%s'）", active_wf)
    elif _wf_has_ipa(wf):
        _bypass_ipa_nodes(wf)
        logger.info("[variant-gen] IPA 停用/無參考圖 → 既有節點 bypass")

    # ControlNet：無參考圖時剝離既有 CN 節點（須在 _inject_prompts 之前）
    if _cn_ref_bytes is None and _wf_has_controlnet(wf):
        _bypass_controlnet_nodes(wf)
        logger.info("[variant-gen] ControlNet 停用/無參考圖 → 既有節點 bypass")
    _inject_loras(wf, art_style.loras if art_style else [])
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
        uploaded_cn_ref = comfyui_client.upload_image_bytes(cn_bytes, "char_cn_ref.png")
        _inject_controlnet_image(wf, uploaded_cn_ref)
        cn_used = True
        logger.info("[variant-gen] ControlNet (%s) injected, weight=%.2f", cn_mode, cn_weight)

    _replace_negative_seeds(wf, seed)
    _log_wf_snapshot(wf, label="variant-gen")
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
            "X-CN-Used": "1" if cn_used else "0",
            "X-CN-Mode": cn_mode,
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
        texts = comfyui_client.wait_for_text_result(prompt_id, timeout=90)
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

    _replace_negative_seeds(wf, actual_seed)
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
