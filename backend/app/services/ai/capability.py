"""
Checkpoint family detection + IPA/CN injection model lookup + capability resolution.

B2 (2026-06-17)：集中能力判斷邏輯，單一真相來源。
  - INJECT_MODELS : family → 注入模型檔名對照表
  - resolve_family: checkpoint 檔名 → family string
  - resolve_capability: workflow dict + checkpoint → {ipa_supported, cn_supported, family, models}

設計原則：
  - 未知家族 fallback = 'sdxl'（現況全 SDXL，零行為變更）
  - 'flux' 不在 INJECT_MODELS → IPA/CN 不支援注入
  - workflow 已有節點 → 該功能仍算支援（節點偵測優先）
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from app.services.ai.wf_node_ops import _wf_has_ipa, _wf_has_controlnet

logger = logging.getLogger(__name__)

# ── YAML 路徑（同 workflow_builder 規則）────────────────────────────────────
_STYLES_YML = Path("/app/backend/checkpoint_styles.yml")
if not _STYLES_YML.exists():
    _STYLES_YML = Path(__file__).resolve().parents[3] / "checkpoint_styles.yml"

# ── SDXL 系注入模型（sdxl / pony / illustrious / noobai 共用）───────────────
_SDXL_MODELS: dict[str, str] = {
    "ipa_clipvision": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
    "ipa_adapter":    "ip-adapter-plus_sdxl_vit-h.safetensors",
    "cn_model":       "diffusion_pytorch_model_promax.safetensors",
    "cn_union_type":  "canny/lineart/anime_lineart/mlsd",
}

# family → 注入模型；未列家族（如 flux）= 不支援注入。
INJECT_MODELS: dict[str, dict[str, str]] = {
    "sdxl":        _SDXL_MODELS,
    "pony":        _SDXL_MODELS,        # Pony = SDXL 架構
    "illustrious": _SDXL_MODELS,        # Illustrious = SDXL 架構
    "noobai":      _SDXL_MODELS,        # NoobAI = SDXL 架構
    # "sd15": {...}  # 有需求時補
    # "flux"         # 不列 = 不支援注入 → 前端隱藏 IPA/CN
}


# ── Checkpoint 解析（單一真相，2026-07-25 AC-2'）─────────────────────────────
# Anima 等 diffusion-model 工作流無 CheckpointLoaderSimple，模型名在 UNETLoader.unet_name。
# 過去 gen_profile 已補此 fallback，但 workflow_builder._detect_style 與本模組的 caller
# （api/settings.py、api/art_generate.py）未補 → 同一工作流被解析成兩種 family：
# 生成端 anima（正確閘控），UI 端 sdxl（謊報 cn_supported=True）。集中於此避免再分歧。
_UNET_LOADER_TYPES = ("UNETLoader", "UnetLoaderGGUF", "UNETLoaderGGUF")


def extract_checkpoint_from_wf(wf: dict) -> str:
    """從 workflow dict 取出模型檔名。純函式，無 I/O。

    優先序：CheckpointLoaderSimple.ckpt_name → UNETLoader 系 .unet_name → ""。
    回 "" 表示此工作流未內嵌模型名，呼叫端應退回全域 checkpoint。
    """
    if not isinstance(wf, dict):
        return ""
    ckpt = next(
        (n["inputs"].get("ckpt_name", "") for n in wf.values()
         if isinstance(n, dict) and n.get("class_type") == "CheckpointLoaderSimple"
         and isinstance(n.get("inputs"), dict)),
        "",
    ) or ""
    if ckpt:
        return ckpt
    return next(
        (n["inputs"].get("unet_name", "") for n in wf.values()
         if isinstance(n, dict) and n.get("class_type") in _UNET_LOADER_TYPES
         and isinstance(n.get("inputs"), dict)),
        "",
    ) or ""


def resolve_checkpoint_for_workflow(workflow_name: str) -> str:
    """工作流名 → 實際生效的模型檔名（內嵌優先，讀不到才退回全域 checkpoint）。

    custom workflow 的模型內嵌於 JSON（不被全域覆寫），是實際生成所用，故以內嵌值為準。
    任何錯誤 → 退回全域 checkpoint，不讓呼叫端 crash。
    """
    wf: dict = {}
    try:
        from app.services.ai.workflow_builder import _load_workflow
        wf = _load_workflow(workflow_name)
    except Exception as e:
        logger.warning("[capability] 讀工作流 '%s' 失敗（%s），改用全域 checkpoint", workflow_name, e)
    ckpt = extract_checkpoint_from_wf(wf)
    if ckpt:
        return ckpt
    try:
        from app.core import state
        return state.get_checkpoint() or ""
    except Exception:
        return ""


def _load_families() -> dict[str, str]:
    """Load checkpoint-pattern → family from checkpoint_styles.yml `families` section."""
    try:
        with open(_STYLES_YML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("families", {})
    except Exception as e:
        logger.warning("[capability] Could not load checkpoint_styles.yml families: %s", e)
        return {}


def resolve_family(checkpoint_name: str) -> str:
    """
    Map checkpoint filename → family string.

    Pattern matching：case-insensitive substring，同 _detect_style 邏輯。
    Fallback = 'sdxl'（現況全 SDXL，維持零行為變更）。
    """
    if not checkpoint_name:
        return "sdxl"
    families = _load_families()
    ckpt_base = Path(checkpoint_name).stem.lower()
    for pattern, family in families.items():
        if str(pattern).lower() in ckpt_base:
            logger.debug("[capability] '%s' matched pattern '%s' → family '%s'",
                         checkpoint_name, pattern, family)
            return str(family)
    logger.debug("[capability] '%s' → fallback family 'sdxl'", checkpoint_name)
    return "sdxl"


def resolve_capability(wf: dict, checkpoint_name: str) -> dict:
    """
    Compute capability for a given workflow dict + checkpoint.

    Returns:
        {
          "ipa_supported": bool,
          "cn_supported":  bool,
          "family":        str,
          "models":        dict | None,   # 注入模型檔名；None = 不支援注入
        }

    判定邏輯（混合）：
      1. wf 已有節點 → 支援（無論家族）
      2. INJECT_MODELS[family] 有對應模型 → 可動態注入 → 支援
      否則 → 不支援
    """
    family = resolve_family(checkpoint_name)
    models = INJECT_MODELS.get(family)  # None if family not in table (e.g. flux)

    ipa_supported = _wf_has_ipa(wf) or (models is not None and "ipa_adapter" in models)
    cn_supported = _wf_has_controlnet(wf) or (models is not None and "cn_model" in models)

    # D'-2（2026-07-25）：家族不支援 CN 但有替代路徑時一併回報，前端才能保留控制項
    # （Anima → "img2img"）。若不回報，前端會因 cn_supported=False 送出 use_controlnet=0，
    # 後端的 cn_fallback 分支就永遠進不去。lazy import 避免與 gen_profile 循環相依。
    cn_fallback = None
    if not cn_supported:
        try:
            from app.services.ai.gen_profile import get_profile
            cn_fallback = get_profile(family).cn_fallback
        except Exception as e:
            logger.debug("[capability] cn_fallback 解析略過：%s", e)

    return {
        "ipa_supported": ipa_supported,
        "cn_supported":  cn_supported,
        "cn_fallback":   cn_fallback,
        "family":        family,
        "models":        models,
    }
