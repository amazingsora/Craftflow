# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
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


# [CN-087] checkpoint 解析單一真相：Anima 的模型名在 UNETLoader.unet_name，三處共用避免 family 分歧
_UNET_LOADER_TYPES = ("UNETLoader", "UnetLoaderGGUF", "UNETLoaderGGUF")

# [CN-088] UNet-only 家族清單；family 由檔名子字串判定會誤命中（animagineXL 含 anima），刻意不含 flux
_UNET_ONLY_FAMILIES = frozenset({"anima"})


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
          "family_conflict": str | None,  # SYNC-003："loader_mismatch" = 名稱與載入節點矛盾
        }

    判定邏輯（混合）：
      1. wf 已有節點 → 支援（無論家族）
      2. INJECT_MODELS[family] 有對應模型 → 可動態注入 → 支援
      否則 → 不支援
    """
    family = resolve_family(checkpoint_name)

    # [CN-089] 名稱判定與載入節點矛盾 → 什麼都不注入，也不改判 sdxl（護欄不猜）
    if _is_loader_family_conflict(wf, family):
        _warn_loader_family_conflict(checkpoint_name, family)
        return {
            "ipa_supported": _wf_has_ipa(wf),
            "cn_supported":  _wf_has_controlnet(wf),
            "cn_fallback":   None,
            "lllite_weight": None,
            "lllite_node_class": None,
            "family":        family,
            "models":        None,
            "family_conflict": "loader_mismatch",
        }

    models = INJECT_MODELS.get(family)  # None if family not in table (e.g. flux)

    ipa_supported = _wf_has_ipa(wf) or (models is not None and "ipa_adapter" in models)
    cn_supported = _wf_has_controlnet(wf) or (models is not None and "cn_model" in models)

    # [CN-090] 不支援 CN 但有替代路徑時一併回報，否則前端送 use_controlnet=0，後端 fallback 永遠進不去
    cn_fallback = None
    lllite_weight = None
    lllite_node_class = None
    if not cn_supported:
        try:
            from app.services.ai.gen_profile import get_profile
            chain = get_profile(family).cn_fallback_chain
            # [CN-091] 沿候選鏈找第一個執行期真的可用的機制；lllite 需問 ComfyUI，其餘視為恆可用
            for mech in chain:
                if mech != "lllite":
                    cn_fallback = mech
                    break
                lllite_weight = _resolve_lllite_weight()
                if lllite_weight:
                    cn_fallback = "lllite"
                    # [CN-092] node_class 與 weight 來自同一次 detect_lllite()，讓注入端拿到探測到的實名
                    lllite_node_class = _resolve_lllite_node_class()
                    break
        except Exception as e:
            logger.debug("[capability] cn_fallback 解析略過：%s", e)

    return {
        "ipa_supported": ipa_supported,
        "cn_supported":  cn_supported,
        "cn_fallback":   cn_fallback,
        "lllite_weight": lllite_weight,      # None = 不走 lllite；有值 = 要餵給節點的檔名
        "lllite_node_class": lllite_node_class,  # 探測到的實際 class 名，None = 未探測/不可用
        "family":        family,
        "models":        models,
        "family_conflict": None,             # SYNC-003 A2：None = 名稱與載入節點一致
    }


# SYNC-003 A2（2026-09-16）：已告警過的 (checkpoint, family)。每張圖會解析 capability
# 多次（API 閘門＋service 內兩處），不去重會洗版；沿用 `_LLLITE_UNAVAILABLE_WARNED` 慣例。
_LOADER_CONFLICT_WARNED: set[tuple[str, str]] = set()


def _is_loader_family_conflict(wf: dict, family: str) -> bool:
    """family 必須用 UNet 載入器，但工作流只有 CheckpointLoaderSimple → True。純函式。

    wf 為空或非 dict（呼叫端讀不到工作流時會傳 {}）→ False：沒有結構資訊就不下判斷，
    維持既有依名稱的行為。
    """
    if family not in _UNET_ONLY_FAMILIES or not isinstance(wf, dict):
        return False
    types = {n.get("class_type") for n in wf.values() if isinstance(n, dict)}
    return "CheckpointLoaderSimple" in types and not types.intersection(_UNET_LOADER_TYPES)


def _warn_loader_family_conflict(checkpoint_name: str, family: str) -> None:
    """同一 (checkpoint, family) 只發一次 WARNING，其餘降為 DEBUG。"""
    key = (str(checkpoint_name), str(family))
    msg = ("[capability] checkpoint '%s' 依檔名被判為 family '%s'，但工作流以 "
           "CheckpointLoaderSimple 載入（無 UNet 載入器）→ 本次不注入 IPA/CN/LLLite/img2img。"
           "若它是 SDXL 系模型：名稱對照誤判，請在 checkpoint_styles.yml 的 checkpoints 與 "
           "families 兩區補登錄（須排在較短的關鍵字之前）；若它真是 UNet 模型：檔案放錯了"
           "目錄（應在 models/diffusion_models/，改用 UNETLoader 工作流）")
    if key not in _LOADER_CONFLICT_WARNED:
        _LOADER_CONFLICT_WARNED.add(key)
        logger.warning(msg, checkpoint_name, family)
    else:
        logger.debug(msg, checkpoint_name, family)


# [CN-093] node_class 側寫快取：不讓 _resolve_lllite_weight 回 tuple，以免動到既有回傳型別
_lllite_node_class_cache: str | None = None


# [CN-094] warn-once：同一 reason 只吵一次（實測會洗版 28 次），reason 變了才再吵
_LLLITE_UNAVAILABLE_WARNED: set[str] = set()


def _warn_lllite_unavailable(reason: str, detail: str) -> None:
    """同一 reason 只發一次 WARNING，其餘降為 DEBUG。"""
    key = str(reason)
    if key not in _LLLITE_UNAVAILABLE_WARNED:
        _LLLITE_UNAVAILABLE_WARNED.add(key)
        logger.warning("[capability] %s → 本次生成改走退路（非 LLLite）。"
                       "同一原因只告警一次；`params.mechanism` 會記錄實際機制", detail)
    else:
        logger.debug("[capability] %s → 退候選鏈下一項", detail)


def _resolve_lllite_weight() -> str | None:
    """問 ComfyUI 有沒有可用的 Anima LLLite 權重，回檔名或 None。

    偵測結果在 comfyui_client 內快取（成功永久、失敗退避），故不會每次生成都打 API。
    任何失敗都回 None → 自動退到鏈的下一個機制（Resilient errors）。
    """
    global _lllite_node_class_cache
    try:
        from app.services import comfyui_client
        info = comfyui_client.detect_lllite()
        _lllite_node_class_cache = info.get("node_class")
        if not info.get("available"):
            _warn_lllite_unavailable(
                info.get("reason"),
                f"LLLite 不可用（{info.get('reason')}）")
            return None
        weight = comfyui_client.pick_lllite_weight(info.get("weights") or [])
        if weight is None:
            _warn_lllite_unavailable(
                "no-weight",
                f"LLLite 節點已裝，但 controlnet 目錄找不到 lllite 權重檔"
                f"（目前檔案：{info.get('weights')}）")
        return weight
    except Exception as e:
        logger.debug("[capability] LLLite 偵測略過：%s", e)


def _resolve_lllite_node_class() -> str | None:
    """回傳最近一次 _resolve_lllite_weight() 探測到的實際 class 名。

    不獨立打 API —— 呼叫端必須先呼叫過 _resolve_lllite_weight()（resolve_capability
    的呼叫順序已保證這點）。這是刻意的側寫快取而非參數，見上方註解。
    """
    return _lllite_node_class_cache
