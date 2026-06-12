"""ComfyUI workflow（API-format dict）節點操作工具。

自 api/art_generate.py 下沉（2026-06-11 A1 階段 1）：
IPA / ControlNet 節點偵測、參考圖注入、動態建鏈、bypass 拆鏈、
prompt 注入（含 conditioning 邊回溯）。純 dict 操作，無 app 狀態依賴。

備註：_inject_txt2img 搬移時即無呼叫端（死碼），保留待確認。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

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

    # Safety: never delete a node still referenced by a surviving node outside the IPA chain.
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
            logger.debug("[ipa-bypass] keep node %s (still referenced outside IPA chain)", nid)
            continue
        ct = wf[nid].get("class_type", "?") if nid in wf else "?"
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
# AnimeLineArt 預處理解析度（與 Standard_V35 一致；取代原 Canny，避免機甲效果）
_CANNY_RES = 1024
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
        cnloader_id, settype_id, prep_id, loadimg_id, cnapply_id = (
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
        wf[prep_id] = {
            "class_type": "AnimeLineArtPreprocessor",
            "inputs": {
                "image": [loadimg_id, 0],
                "resolution": _CANNY_RES,
            },
        }
        wf[cnapply_id] = {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": pos_src,
                "negative": neg_src,
                "control_net": [settype_id, 0],
                "image": [prep_id, 0],
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


def _resolve_conditioning(
    wf: dict, node_id: str, out_slot: int, clips: dict, _seen: frozenset = frozenset()
) -> str | None:
    """Recursively follow a conditioning edge back to a CLIPTextEncode node.

    Handles intermediate conditioning nodes by mapping their output slot to the
    corresponding input edge:
    - ControlNetApplyAdvanced: slot 0 → positive input, slot 1 → negative input
    - Generic passthrough nodes: follow conditioning/positive/negative inputs in order

    Returns the CLIPTextEncode node_id, or None if unreachable.
    """
    if node_id in _seen:
        return None
    _seen = _seen | {node_id}
    if node_id in clips:
        return node_id
    node = wf.get(node_id)
    if not isinstance(node, dict):
        return None
    ct = node.get("class_type", "")
    inp = node.get("inputs", {})
    if ct in _CN_APPLY_TYPES:
        # ControlNetApplyAdvanced: slot 0 = conditioned positive, slot 1 = conditioned negative
        follow_key = "positive" if out_slot == 0 else "negative"
        ref = inp.get(follow_key)
        if isinstance(ref, list) and ref:
            return _resolve_conditioning(wf, str(ref[0]), int(ref[1]) if len(ref) > 1 else 0, clips, _seen)
    else:
        for key in ("positive", "negative", "conditioning"):
            ref = inp.get(key)
            if isinstance(ref, list) and ref:
                result = _resolve_conditioning(wf, str(ref[0]), int(ref[1]) if len(ref) > 1 else 0, clips, _seen)
                if result:
                    return result
    return None


def _inject_prompts(wf: dict, positive: str, negative: str) -> None:
    """Inject positive/negative prompts into CLIPTextEncode nodes.

    Strategy (in order, stops as soon as both are resolved):
      1. Trace KSampler.positive / KSampler.negative graph edges back to CLIPTextEncode nodes,
         recursively passing through intermediate conditioning nodes (e.g. ControlNetApplyAdvanced).
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

    # Pass 1: follow KSampler edges with recursive conditioning passthrough
    for node in wf.values():
        if not isinstance(node, dict) or node.get("class_type") != "KSampler":
            continue
        inp = node.get("inputs", {})
        for slot, text in (("positive", positive), ("negative", negative)):
            ref = inp.get(slot)
            if isinstance(ref, list) and ref:
                clip_id = _resolve_conditioning(
                    wf, str(ref[0]), int(ref[1]) if len(ref) > 1 else 0, clips
                )
                if clip_id:
                    clips[clip_id]["inputs"]["text"] = text
                    if slot == "positive":
                        pos_injected = True
                    else:
                        neg_injected = True
                    logger.debug("[inject-prompts] KSampler.%s → (resolved) node %s", slot, clip_id)

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
