"""wf_node_ops 單元測試（A3，2026-06-13）。

純 workflow dict 操作，不需要 ComfyUI。
執行：cd backend && pytest tests/test_wf_node_ops.py
"""
import copy

from app.services.ai.wf_node_ops import (
    _bypass_controlnet_nodes,
    _bypass_ipa_nodes,
    _find_main_ksampler_id,
    _inject_controlnet_image,
    _inject_ipa_cn_nodes,
    _inject_ipa_image,
    _inject_prompts,
    _wf_has_controlnet,
    _wf_has_ipa,
)


def _base_txt2img() -> dict:
    """最小可用 txt2img workflow（API 格式）。"""
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "test.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["1", 1]},
              "_meta": {"title": "Positive Prompt"}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["1", 1]},
              "_meta": {"title": "Negative Prompt"}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
            "latent_image": ["4", 0], "seed": -1, "steps": 20, "denoise": 1.0,
        }},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0]}},
    }


# ── 偵測 ──────────────────────────────────────────────────────────────────────

def test_has_ipa_and_cn_on_bare_workflow():
    wf = _base_txt2img()
    assert _wf_has_ipa(wf) is False
    assert _wf_has_controlnet(wf) is False


def test_find_main_ksampler_single():
    assert _find_main_ksampler_id(_base_txt2img()) == "5"


def test_find_main_ksampler_hires_fix_picks_denoise_1():
    wf = _base_txt2img()
    wf["8"] = {"class_type": "KSampler", "inputs": {"model": ["1", 0], "denoise": 0.45}}
    assert _find_main_ksampler_id(wf) == "5"  # denoise 1.0 為主路徑


# ── 動態注入 IPA/CN 鏈 ────────────────────────────────────────────────────────

def test_inject_ipa_cn_nodes_full():
    wf = _base_txt2img()
    _inject_ipa_cn_nodes(wf, inject_ipa=True, inject_cn=True)

    assert _wf_has_ipa(wf) and _wf_has_controlnet(wf)
    ks = wf["5"]["inputs"]
    # KSampler.model 改接 IPA、positive/negative 改接 CN apply
    ipa_id = ks["model"][0]
    assert wf[ipa_id]["class_type"] == "IPAdapterAdvanced"
    assert wf[ipa_id]["inputs"]["model"] == ["1", 0]  # IPA 上游 = 原 model 來源
    cn_id = ks["positive"][0]
    assert wf[cn_id]["class_type"] == "ControlNetApplyAdvanced"
    assert ks["negative"] == [cn_id, 1]
    # CN apply 上游 conditioning = 原 CLIPTextEncode
    assert wf[cn_id]["inputs"]["positive"] == ["2", 0]
    assert wf[cn_id]["inputs"]["negative"] == ["3", 0]


def test_inject_then_bypass_roundtrip():
    """注入後 bypass，KSampler 接線應還原、注入節點應清除。"""
    wf = _base_txt2img()
    original = copy.deepcopy(wf)
    _inject_ipa_cn_nodes(wf, inject_ipa=True, inject_cn=True)
    _bypass_controlnet_nodes(wf)
    _bypass_ipa_nodes(wf)

    assert wf["5"]["inputs"]["model"] == original["5"]["inputs"]["model"]
    assert wf["5"]["inputs"]["positive"] == original["5"]["inputs"]["positive"]
    assert wf["5"]["inputs"]["negative"] == original["5"]["inputs"]["negative"]
    assert _wf_has_ipa(wf) is False
    assert _wf_has_controlnet(wf) is False
    # 共用節點（checkpoint/CLIP/KSampler 等）不可被誤刪
    for nid in original:
        assert nid in wf


# ── 參考圖注入 ────────────────────────────────────────────────────────────────

def test_inject_ipa_image():
    wf = _base_txt2img()
    _inject_ipa_cn_nodes(wf, inject_ipa=True, inject_cn=False)
    assert _inject_ipa_image(wf, "ref_abc.png") is True
    ipa_id = wf["5"]["inputs"]["model"][0]
    loadimg_ref = wf[ipa_id]["inputs"]["image"]
    assert wf[loadimg_ref[0]]["inputs"]["image"] == "ref_abc.png"


def test_inject_ipa_image_without_chain_returns_false():
    assert _inject_ipa_image(_base_txt2img(), "x.png") is False


def test_inject_controlnet_image():
    wf = _base_txt2img()
    _inject_ipa_cn_nodes(wf, inject_ipa=False, inject_cn=True)
    assert _inject_controlnet_image(wf, "cn_ref.png") == 1
    # 確認注入的是餵 CN 前處理器的 LoadImage，而非其他 LoadImage
    updated = [n for n in wf.values()
               if n.get("class_type") == "LoadImage" and n["inputs"].get("image") == "cn_ref.png"]
    assert len(updated) == 1


def test_inject_controlnet_image_no_cn_returns_zero():
    assert _inject_controlnet_image(_base_txt2img(), "x.png") == 0


# ── prompt 注入 ───────────────────────────────────────────────────────────────

def test_inject_prompts_via_ksampler_edges():
    wf = _base_txt2img()
    _inject_prompts(wf, "POS_TEXT", "NEG_TEXT")
    assert wf["2"]["inputs"]["text"] == "POS_TEXT"
    assert wf["3"]["inputs"]["text"] == "NEG_TEXT"


def test_inject_prompts_through_cn_apply():
    """conditioning 經過 ControlNetApplyAdvanced 仍應回溯到正確的 CLIPTextEncode。"""
    wf = _base_txt2img()
    _inject_ipa_cn_nodes(wf, inject_ipa=False, inject_cn=True)
    _inject_prompts(wf, "POS_TEXT", "NEG_TEXT")
    assert wf["2"]["inputs"]["text"] == "POS_TEXT"
    assert wf["3"]["inputs"]["text"] == "NEG_TEXT"


def test_inject_prompts_title_fallback():
    """KSampler 邊缺失時退回 _meta.title 匹配。"""
    wf = _base_txt2img()
    del wf["5"]["inputs"]["positive"]
    del wf["5"]["inputs"]["negative"]
    _inject_prompts(wf, "POS_TEXT", "NEG_TEXT")
    assert wf["2"]["inputs"]["text"] == "POS_TEXT"
    assert wf["3"]["inputs"]["text"] == "NEG_TEXT"


# ── _inject_ipa_cn_nodes：CN preprocessor 可選（canny / anime_lineart）──────────

def _min_wf_for_inject():
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "x.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "p", "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "n", "clip": ["1", 1]}},
        "4": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "denoise": 1.0,
        }},
    }


def _preproc_types(wf):
    return [n.get("class_type") for n in wf.values()
            if isinstance(n, dict) and "Preprocessor" in n.get("class_type", "")]


def test_inject_cn_default_is_anime_lineart():
    from app.services.ai import wf_node_ops as ops
    wf = _min_wf_for_inject()
    ops._inject_ipa_cn_nodes(wf, inject_ipa=False, inject_cn=True)
    assert "AnimeLineArtPreprocessor" in _preproc_types(wf)


def test_inject_cn_canny_when_requested():
    from app.services.ai import wf_node_ops as ops
    wf = _min_wf_for_inject()
    ops._inject_ipa_cn_nodes(
        wf, inject_ipa=False, inject_cn=True,
        cn_preprocessor={"type": "CannyEdgePreprocessor", "low_threshold": 100,
                         "high_threshold": 200, "resolution": 1024},
    )
    canny = [n for n in wf.values()
             if isinstance(n, dict) and n.get("class_type") == "CannyEdgePreprocessor"]
    assert len(canny) == 1
    assert canny[0]["inputs"]["low_threshold"] == 100
    assert canny[0]["inputs"]["high_threshold"] == 200
