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

    return {
        "ipa_supported": ipa_supported,
        "cn_supported":  cn_supported,
        "family":        family,
        "models":        models,
    }
