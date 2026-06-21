"""Workflow 載入 / 風格偵測 / LoRA 注入 / ComfyUI 執行。

自 api/art_generate.py 下沉（2026-06-11 A1 階段 1）。
唯一非逐字搬移處：_SYSTEM_WORKFLOW_DIR / _STYLES_YML 的本機 fallback 路徑
parents 索引依本檔深度調整（services/ai/ 比 api/ 深一層）；Docker 路徑不變。
"""
from __future__ import annotations

import json
import struct
import logging
from pathlib import Path
from typing import Optional

import yaml
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

import random

from sqlalchemy.orm import Session

from app.core.config import CUSTOM_WORKFLOWS_DIR, COMFYUI_LORAS_DIR
from app.core import state
from app.models.art_style import ArtStyle
from app.services import comfyui_client
from app.services.ai.prompt_engine import PromptStyle
from app.services.ai.prompt_engine.styles import STYLE_CONFIG
from app.schemas.art_generate import GenerateRequest
from app.services.ai.wf_node_ops import _inject_prompts

logger = logging.getLogger(__name__)

_SYSTEM_WORKFLOW_DIR = Path("/app/tools/Craftflow/diffusion/workflows")
if not _SYSTEM_WORKFLOW_DIR.exists():
    _SYSTEM_WORKFLOW_DIR = Path(__file__).resolve().parents[4] / "tools" / "Craftflow" / "diffusion" / "workflows"

# checkpoint_styles.yml — Docker path / local fallback
_STYLES_YML = Path("/app/backend/checkpoint_styles.yml")
if not _STYLES_YML.exists():
    _STYLES_YML = Path(__file__).resolve().parents[3] / "checkpoint_styles.yml"

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


_LORA_ARCH_CACHE: dict = {}

def _lora_arch(lora_name: str):
    """從 safetensors __metadata__ 的 ss_base_model_version 推 LoRA 訓練底模架構。
    回 'sdxl'/'sd15'/None(未知→不警告)。best-effort，任何失敗→None。"""
    if lora_name in _LORA_ARCH_CACHE:
        return _LORA_ARCH_CACHE[lora_name]
    arch = None
    try:
        path = COMFYUI_LORAS_DIR / lora_name
        if path.exists():
            with open(path, "rb") as f:
                n = struct.unpack("<Q", f.read(8))[0]
                hdr = json.loads(f.read(n))
            base = str(hdr.get("__metadata__", {}).get("ss_base_model_version", "")).lower()
            if "xl" in base:
                arch = "sdxl"
            elif base.startswith("sd_v1") or "v1-5" in base or "sd1" in base:
                arch = "sd15"
    except Exception:
        arch = None
    _LORA_ARCH_CACHE[lora_name] = arch
    return arch


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

    # 架構健檢（警告為主，不阻擋）：LoRA 訓練底模與 checkpoint family 不符 → 多半靜默失效。
    try:
        from app.services.ai.capability import resolve_family
        _ckpt_name = wf[ckpt_id].get("inputs", {}).get("ckpt_name", "")
        _ckpt_arch = "sd15" if resolve_family(_ckpt_name) == "sd15" else "sdxl"
        for _l in valid:
            _la = _lora_arch(_l["model"].strip())
            if _la and _la != _ckpt_arch:
                logger.warning("[lora] 架構不符：LoRA '%s'(%s) vs checkpoint '%s'(%s) → 多半靜默失效，請確認",
                               _l["model"], _la, _ckpt_name, _ckpt_arch)
    except Exception as _e:
        logger.debug("[lora] arch check skipped: %s", _e)

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

    # Rewire every consumer of the checkpoint's model (slot 0) / clip (slot 1) outputs to
    # the LoRA chain, so the LoRA applies even when the model/clip path first runs through
    # other nodes (e.g. a workflow's built-in "Lora Loader (LoraManager)"). Edge-based, not
    # type-based: the old type-list missed those intermediaries → injected LoRA dangled unused.
    # VAE output (slot 2) is left on the checkpoint. The injected LoRA nodes are skipped to
    # avoid rewiring the chain's own root reference into a cycle.
    lora_ids = {f"_lora_{i}" for i in range(len(valid))}
    for nid, node in wf.items():
        if nid in lora_ids or not isinstance(node, dict):
            continue
        for key, val in node.get("inputs", {}).items():
            if isinstance(val, list) and len(val) >= 2 and str(val[0]) == str(ckpt_id):
                if val[1] == 0:
                    node["inputs"][key] = [prev_id, 0]
                elif val[1] == 1:
                    node["inputs"][key] = [prev_id, 1]


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


def _is_custom_workflow(name: str) -> bool:
    """True = 工作流位於使用者 CUSTOM_WORKFLOWS_DIR（即前端「自訂 Workflow 模式」）。

    此模式下 Checkpoint/全域 LoRA「由 workflow 本身決定」，後端不注入全域 LoRA；
    Checkpoint 模式（系統 text_to_image.json）才注入全域 LoRA。
    角色 / 畫風 LoRA 屬個別實體設定，不受此模式影響。
    """
    return (CUSTOM_WORKFLOWS_DIR / name).exists()


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


async def _run_comfyui(workflow: dict) -> bytes:
    return await run_in_threadpool(_run, workflow)

# ── txt2img 組裝 / inpaint·upscale 風格解析（A1 Step 4 自 api 下沉）─────────────

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
    # 全域 LoRA 僅 Checkpoint 模式（系統工作流）生效；自訂 workflow 模式由 workflow 決定。
    if global_lora.get("name") and not _is_custom_workflow(state.get_workflow()):
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
