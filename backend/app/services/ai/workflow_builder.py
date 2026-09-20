# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
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

from app.core.config import CUSTOM_WORKFLOWS_DIR, COMFYUI_LORAS_DIR, COMFYUI_JOB_TIMEOUT_SEC
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

# prompt_profiles.yml — workflow 級 prompt override（P1，2026-07-12）。同一路徑慣例。
_PROMPT_PROFILES_YML = Path("/app/backend/prompt_profiles.yml")
if not _PROMPT_PROFILES_YML.exists():
    _PROMPT_PROFILES_YML = Path(__file__).resolve().parents[3] / "prompt_profiles.yml"

logger.info("system workflow dir: %s", _SYSTEM_WORKFLOW_DIR)
logger.info("checkpoint styles: %s", _STYLES_YML)
logger.info("prompt profiles: %s", _PROMPT_PROFILES_YML)


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


def _load_prompt_profiles() -> dict:
    """Load workflow → prompt profile mapping from prompt_profiles.yml.

    未建檔／解析失敗 → {}（這層機制完全不介入，等同改動前行為，零回歸）。
    不快取（同 _load_checkpoint_styles 慣例）：檔案小、每次讀取成本可忽略，
    换来調參期間（P5 回歸測試）改 yml 免重啟即生效。
    """
    try:
        with open(_PROMPT_PROFILES_YML, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("profiles", {}) or {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("Could not load prompt_profiles.yml: %s", e)
        return {}


# SYNC-001（2026-09-15）：已就 profile miss 告警過的 workflow 檔名。
# 每張圖都會查好幾次 profile，不去重會把 log 洗掉；用集合讓「同一檔名只吵一次」。
_PROFILE_MISS_WARNED: set[str] = set()


def _profile_for(workflow: str) -> dict:
    """查 workflow 的 prompt profile；**miss 時記一次 WARNING**（SYNC-001）。

    為什麼要這個函式：本機制以 workflow **檔名**為唯一鍵，改名即整組脫鉤，而原本
    miss 是靜默的（`_prompt_profile_source()` 只在命中時回來源）。2026-09-15 盤點發現
    六個現役 workflow 全部 miss、08-12～08-26 三輪 P5 調校成果 100% 未生效，且這是
    同型缺陷第三次（07-25 novaAnimeXL 漏登錄、08-22 V8turbo 漏登錄）。

    **刻意不做檔名正規化／模糊比對**：那會把「一個明確的鍵」換成「一組會誤命中的
    猜測規則」，出事時更難查。這裡只負責讓脫鉤變成看得見的事件。

    回傳 {} 代表未登錄 → 呼叫端落回 checkpoint family / .env（行為與本函式導入前一致）。
    """
    profile = _load_prompt_profiles().get(workflow)
    if profile:
        return profile
    if workflow not in _PROFILE_MISS_WARNED:
        _PROFILE_MISS_WARNED.add(workflow)
        logger.warning(
            "[prompt-profile] workflow '%s' 未登錄於 %s → 落回 checkpoint family + .env。"
            "若這不是預期行為，請在該檔 profiles: 下補登錄（可用 YAML anchor 沿用既有配方）",
            workflow, _PROMPT_PROFILES_YML,
        )
    return {}


def _workflow_profile_overrides(workflow: str) -> dict:
    """P1：查 workflow 檔名在 prompt_profiles.yml 是否有登錄的 quality_prefix /
    quality_suffix / negative / negative_extra；只有實際登錄（非空）的欄位才放進回傳 dict，
    未登錄欄位不佔位，讓 compile() 的預設 fallback（checkpoint family）維持有效。

    negative（取代語義）與 negative_extra（補充語義，R4）互不排斥，可同時登錄：
    前者決定 negative 主體、後者附加於其後。
    """
    profile = _profile_for(workflow)
    if not profile:
        return {}
    out: dict = {}
    if profile.get("quality_prefix"):
        out["quality_prefix_override"] = profile["quality_prefix"]
    if profile.get("quality_suffix"):
        out["quality_suffix_override"] = profile["quality_suffix"]
    if profile.get("negative"):
        out["negative_override"] = profile["negative"]
    if profile.get("negative_extra"):
        out["negative_extra_override"] = profile["negative_extra"]
    return out


def _workflow_style_extra(workflow: str) -> tuple[str, Optional[float]]:
    """P5-5：查 workflow 檔名在 prompt_profiles.yml 是否登錄 style_extra / style_extra_weight。
    與 _workflow_profile_overrides 平行，共用同一個 _profile_for()（含 miss 告警）。

    這兩個欄位**不進** _resolve_prompt_overrides() 的回傳 dict —— 那個 dict 是
    compile_prompt() 的 kwargs，而 style_extra 是 compile 之後在 service 層組裝的
    （character_design_service.py 的 _resolve_style_extra()／final_positive 組裝處）。

    未登錄 workflow 或欄位留白 → ("", None)，呼叫端落回 .env
    PERSONAL_STYLE_EXTRA_TAGS / PERSONAL_STYLE_WEIGHT（零回歸）。
    """
    profile = _profile_for(workflow)
    if not profile:
        return "", None
    extra = (profile.get("style_extra") or "").strip()
    weight = profile.get("style_extra_weight")
    return extra, (float(weight) if weight is not None else None)


def _resolve_prompt_overrides(art_style: Optional[ArtStyle], workflow: str) -> dict:
    """P1：整合 compile_prompt() 的三個 override 欄位，優先序：
    art_style 個別欄位 > workflow 級 prompt_profiles.yml > checkpoint family
    （後者由 compile() 內部 fallback 到 STYLE_CONFIG，這裡不重複填）。

    只用「非空」值覆寫下層，避免 art_style 留白的欄位把 workflow profile 的定案值蓋掉
    （_compile_overrides 對已存在的 art_style 一律回傳含 None 值的 key，不可直接 dict merge）。
    """
    out = dict(_workflow_profile_overrides(workflow))
    if art_style:
        if art_style.quality_prefix:
            out["quality_prefix_override"] = art_style.quality_prefix
        if art_style.negative:
            out["negative_override"] = art_style.negative
    return out


def _prompt_profile_source(art_style: Optional[ArtStyle], workflow: str) -> str:
    """P4：回傳 debug prompt 用的來源標註字串，反映 _resolve_prompt_overrides 的實際優先序。
      - workflow 在 prompt_profiles.yml 有登錄 → "profile: <workflow>"
      - 否則 → "family fallback"（compile() 內部 fallback 到 checkpoint family STYLE_CONFIG）
      - art_style 另有覆寫 quality_prefix/negative 時，附加 " +art_style#<id>" 標註疊加層。
    純標註用途，不影響任何生成邏輯。"""
    if _profile_for(workflow):
        src = f"profile: {workflow}"
    else:
        src = "family fallback"
    if art_style and (art_style.quality_prefix or art_style.negative):
        src += f" +art_style#{art_style.id}"
    return src


def _extra_tags(art_style: Optional[ArtStyle]) -> str:
    return (art_style.extra_tags or "").strip() if art_style else ""


_LORA_DIR_WARNED = False


def _lora_dir_ok() -> bool:
    """LoRA 目錄存在與否，warn-once。

    SYNC-005 L3（2026-09-20）：`COMFYUI_LORAS_DIR` 預設是 `C:\\ComfyUI\\models\\loras`，
    使用者機器上實際在 `F:\\wk\\ComfyUI_portable\\...`，而 .env 那行本來被註解掉。
    兩個吃這個常數的功能都是**讀不到就安靜回 None／[]**：
      · `_lora_arch()`  → 架構健檢從頭到尾空轉（LoRA 架構不符也不會警告）
      · `lora_trigger_words()` → 觸發詞永遠空的，LoRA 只剩殘留效果
    兩者都不該讓生成失敗，但**也不該一聲不吭** —— 沿用 SYNC-001／SYNC-002 的
    warn-once 慣例（`_PROFILE_MISS_WARNED` / `_LLLITE_UNAVAILABLE_WARNED`），
    同一個問題只吵一次，其餘走 DEBUG。
    """
    global _LORA_DIR_WARNED
    if COMFYUI_LORAS_DIR.exists():
        return True
    if not _LORA_DIR_WARNED:
        _LORA_DIR_WARNED = True
        logger.warning(
            "[lora] LoRA 目錄不存在：%s → 架構健檢與觸發詞注入都會靜默失效。"
            "請在專案根 .env 設定 COMFYUI_LORAS_DIR 指向實際的 ComfyUI loras 目錄。",
            COMFYUI_LORAS_DIR,
        )
    return False


_LORA_ARCH_CACHE: dict = {}

def _lora_arch(lora_name: str):
    """從 safetensors __metadata__ 的 ss_base_model_version 推 LoRA 訓練底模架構。
    回 'sdxl'/'sd15'/None(未知→不警告)。best-effort，任何失敗→None。"""
    if lora_name in _LORA_ARCH_CACHE:
        return _LORA_ARCH_CACHE[lora_name]
    arch = None
    if not _lora_dir_ok():
        _LORA_ARCH_CACHE[lora_name] = None
        return None
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


_LORA_TRIGGER_CACHE: dict = {}


def lora_trigger_words(loras: list) -> list[str]:
    """讀同名 `.civitai.info` 的 `trainedWords`，回傳去重後的觸發詞清單。

    SYNC-005 軌 L（2026-09-19）。**為什麼需要這個**：`_inject_loras()` 只插節點，
    不碰 prompt。而畫風 LoRA 的效果強度高度依賴觸發詞 —— 實例
    `Blue_archive_style.safetensors` 的 `ss_tag_frequency` 只有**單一 tag**
    `blue archive style`+U+200B，出現 270 次（＝每一張訓練圖都是這一句 caption）。
    不帶觸發詞時 LoRA 仍會改權重、但效果剩殘留強度 ——
    **付了全部 VRAM 與時間代價，只拿到一小部分畫風**（AGENT_SYNC §2.1 E11b）。

    ⚠️ `trainedWords` 可能含**零寬空格 U+200B 等不可見字元**（上例就是），
    那是訓練 caption 的一部分，必須**原樣保留**，不可 strip 掉或正規化 ——
    使用者手打也打不出來，這正是自動注入的價值。此處只去頭尾的一般空白
    （`str.strip()` 不會移除 U+200B）。

    best-effort：檔案不存在／JSON 壞掉／欄位缺 → 回空 list，絕不讓生成失敗。
    """
    out: list[str] = []
    if not _lora_dir_ok():
        return out
    for lora in (loras or []):
        if not isinstance(lora, dict):
            continue
        name = (lora.get("model") or "").strip()
        if not name:
            continue
        if name in _LORA_TRIGGER_CACHE:
            words = _LORA_TRIGGER_CACHE[name]
        else:
            words = []
            try:
                info = COMFYUI_LORAS_DIR / (Path(name).stem + ".civitai.info")
                if info.exists():
                    data = json.loads(info.read_text(encoding="utf-8"))
                    for w in (data.get("trainedWords") or []):
                        w = str(w).strip()
                        if w:
                            words.append(w)
            except Exception as e:
                logger.debug("[lora] 讀 trainedWords 失敗 %s: %s", name, e)
                words = []
            _LORA_TRIGGER_CACHE[name] = words
        for w in words:
            if w not in out:
                out.append(w)
    return out


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

    # [CN-106] LoRA rewire 改走 edge-based：type-based 會漏掉中間節點，注入的 LoRA 變成懸空未用
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

    # [CN-107] 偵測 UI-format（非 API format）工作流：其 nodes 是 list，會讓 ComfyUI on_prompt 拋 TypeError
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
    Read the model name from a workflow, then look it up in checkpoint_styles.yml.
    Falls back to SDXL if not found.

    2026-07-25 (AC-2)：模型名改由 capability.extract_checkpoint_from_wf 取得——原本只讀
    CheckpointLoaderSimple，Anima 這類 UNETLoader 工作流一律落到 SDXL fallback，
    prompt 被套錯家族配方。共用函式同時涵蓋 UNETLoader / GGUF 變體。
    """
    mapping = _load_checkpoint_styles()
    try:
        wf = _load_workflow(workflow_name)
    except Exception:
        return PromptStyle.SDXL

    from app.services.ai.capability import extract_checkpoint_from_wf
    ckpt = extract_checkpoint_from_wf(wf)
    if ckpt:
        ckpt_base = Path(ckpt).stem.lower()
        for pattern, style_str in mapping.items():
            if str(pattern).lower() in ckpt_base:
                logger.debug("checkpoint '%s' matched pattern '%s' → style '%s'", ckpt, pattern, style_str)
                try:
                    return PromptStyle(style_str)
                except ValueError:
                    # yml 寫了 enum 沒有的字串 → 不讓生成 crash，繼續找下一個 pattern
                    logger.warning("checkpoint_styles.yml style '%s' 不是合法 PromptStyle，略過", style_str)
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
        filenames = comfyui_client.wait_for_result(prompt_id, COMFYUI_JOB_TIMEOUT_SEC)
    except TimeoutError as e:
        # [CN-108] 本路徑原本完全沒有 log，逾時只能靠 ComfyUI 端還原現場 —— 補上記錄
        logger.error("[comfyui] 主生成逾時：prompt_id=%s timeout=%ss —— ComfyUI 很可能仍在跑並會把圖存進 output/，"
                     "請查 ComfyUI 端 log 的 'Prompt executed in'。放寬上限：.env 的 COMFYUI_JOB_TIMEOUT_SEC",
                     prompt_id, COMFYUI_JOB_TIMEOUT_SEC)
        raise HTTPException(status_code=504, detail=str(e))
    if not filenames:
        raise HTTPException(status_code=500, detail="ComfyUI 未回傳輸出圖片，請確認 workflow 設定。")
    return comfyui_client.download_image(filenames[0])


async def _run_comfyui(workflow: dict) -> bytes:
    return await run_in_threadpool(_run, workflow)

# ── txt2img 組裝 / inpaint·upscale 風格解析（A1 Step 4 自 api 下沉）─────────────────────────────

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
