"""GPU 分級（CN-133）與 Hires 第二段注入（CN-134）。
執行：cd backend && pytest tests/test_gpu_tier_hires.py
"""
import copy

import pytest

from app.core import config
from app.services import comfyui_client
from app.services.ai import capability as cap
from app.services.ai import gen_profile as gp
from app.services.ai import workflow_builder as wb
from app.services.ai.wf_node_ops import (
    _find_main_ksampler_id,
    _inject_face_detailer,
    _inject_hires,
    hires_params,
    hires_target_size,
)


# ── 判級 ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [("4g", "4g"), ("8G", "8g"), (" 16g ", "16g")])
def test_explicit_tier_wins(raw, expected):
    tier, source = config.resolve_gpu_tier(raw, detect=lambda: 4.0)
    assert (tier, source) == (expected, ".env")


def test_invalid_tier_falls_back_to_16g():
    tier, source = config.resolve_gpu_tier("12g", detect=lambda: 4.0)
    assert tier == "16g" and "無效值" in source


@pytest.mark.parametrize("total_gb,expected", [
    (3.9, "4g"), (5.9, "4g"), (7.99, "8g"), (12.0, "8g"), (15.92, "16g"), (24.0, "16g"),
])
def test_auto_tier_by_vram(total_gb, expected):
    assert config.resolve_gpu_tier("auto", detect=lambda: total_gb)[0] == expected


def test_auto_without_nvidia_keeps_current_behaviour():
    tier, source = config.resolve_gpu_tier(None, detect=lambda: None)
    assert tier == "16g" and "偵測不到" in source


def test_tier_env_defaults_only_known_tiers_and_16g_is_noop():
    assert set(config.GPU_TIER_ENV_DEFAULTS) == set(config.GPU_TIERS)
    assert config.GPU_TIER_ENV_DEFAULTS["16g"] == {}


# ── profile 覆寫 ─────────────────────────────────────────────────────────
def test_16g_profile_unchanged():
    base = gp.GEN_PROFILE["illustrious"]
    assert gp.apply_tier(base, "16g") is base


def test_4g_disables_heavy_features_and_falls_back_to_img2img():
    p = gp.apply_tier(gp.GEN_PROFILE["illustrious"], "4g")
    assert (p.ipa_enabled, p.cn_enabled, p.face_detailer_denoise, p.hires_scale) == (False, False, None, None)
    assert p.cn_fallback_chain == ("img2img",)


def test_4g_keeps_anima_fallback_chain():
    p = gp.apply_tier(gp.GEN_PROFILE["anima"], "4g")
    assert p.cn_fallback_chain == ("lllite", "img2img")


def test_8g_caps_hires_and_uses_latent():
    p = gp.apply_tier(gp.GEN_PROFILE["illustrious"], "8g")
    assert p.ipa_enabled is False and p.cn_enabled is True
    assert p.hires_use_model is False and p.hires_scale <= gp.TIER_8G_HIRES_MAX_SCALE


def test_get_profile_reads_tier_at_call_time(monkeypatch):
    assert gp.get_profile("illustrious").ipa_enabled is True
    monkeypatch.setattr(config, "GPU_TIER", "4g")
    assert gp.get_profile("illustrious").ipa_enabled is False


# ── 能力閘控一路貫通到 capability（前端據此隱藏控制項）───────────────────────
def test_capability_4g_hides_injected_ipa_cn(monkeypatch):
    monkeypatch.setattr(config, "GPU_TIER", "4g")
    c = cap.resolve_capability({}, "fabricatedXL_v70.safetensors")
    assert c["ipa_supported"] is False and c["cn_supported"] is False
    assert c["cn_fallback"] == "img2img"
    assert c["face_detailer_supported"] is False


def test_capability_4g_keeps_workflow_builtin_nodes(monkeypatch):
    monkeypatch.setattr(config, "GPU_TIER", "4g")
    monkeypatch.setattr(cap, "_wf_has_ipa", lambda wf: True)
    c = cap.resolve_capability({}, "fabricatedXL_v70.safetensors")
    assert c["ipa_supported"] is True


# ── Hires 注入 ──────────────────────────────────────────────────────────
def _sdxl_wf():
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "fabricatedXL_v70.safetensors"}},
        "2": {"class_type": "Input Parameters (Image Saver)", "inputs": {"steps": 28, "cfg": 6, "denoise": 1}},
        "3": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1536, "batch_size": 1}},
        "4": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["3", 0],
            "seed": 7, "steps": ["2", 1], "cfg": ["2", 2], "sampler_name": "euler_ancestral",
            "scheduler": "normal", "denoise": ["2", 5]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": "a"}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": "b"}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["4", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "x"}},
        "9": {"class_type": "FaceDetailerPipe", "inputs": {"image": ["7", 0]}},
    }


def _anima_wf():
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "miaomiaoHarem_anima12.safetensors"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_06b_base.safetensors"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1536, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["6", 0], "negative": ["6", 0], "latent_image": ["4", 0],
            "seed": 7, "steps": 30, "cfg": 4, "sampler_name": "er_sde", "scheduler": "simple", "denoise": 1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": "a"}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["3", 0]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "x"}},
    }


def _by_type(wf, ct):
    return [k for k, n in wf.items() if n.get("class_type") == ct]


def _assert_graph_closed(wf):
    """所有節點參照都指向存在的節點（ComfyUI 收件前的最低要求）"""
    for nid, n in wf.items():
        for key, v in n.get("inputs", {}).items():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                assert v[0] in wf, f"{nid}.{key} → 不存在的節點 {v[0]}"


def test_hires_target_size_multiple_of_16():
    assert hires_target_size(1024, 1536, 1.31) == (1344, 2016)
    assert hires_target_size(1024, 1536, 1.5) == (1536, 2304)
    w, h = hires_target_size(832, 1216, 1.3)
    assert w % 16 == 0 and h % 16 == 0


def test_inject_hires_model_mode_rewires_all_consumers():
    wf = _sdxl_wf()
    assert _inject_hires(wf, width=1024, height=1536, scale=1.5, denoise=0.4, steps=20,
                         sampler="dpmpp_2m", scheduler="karras", upscale_model="4x-AnimeSharp.safetensors")
    _assert_graph_closed(wf)
    new_decode = [k for k in _by_type(wf, "VAEDecode") if k != "7"][0]
    assert wf["8"]["inputs"]["images"] == [new_decode, 0]
    assert wf["9"]["inputs"]["image"] == [new_decode, 0]
    up = _by_type(wf, "ImageUpscaleWithModel")[0]
    assert wf[up]["inputs"]["image"] == ["7", 0]
    scale = _by_type(wf, "ImageScale")[0]
    assert (wf[scale]["inputs"]["width"], wf[scale]["inputs"]["height"]) == (1536, 2304)
    ks2 = [k for k in _by_type(wf, "KSampler") if k != "4"][0]
    inp = wf[ks2]["inputs"]
    assert inp["denoise"] == 0.4 and inp["steps"] == 20 and inp["sampler_name"] == "dpmpp_2m"
    assert inp["cfg"] == ["2", 2] and inp["seed"] == 7 and inp["model"] == ["1", 0]
    assert wf[inp["latent_image"][0]]["class_type"] == "VAEEncode"
    assert _find_main_ksampler_id(wf) == "4"
    # 字串 id 排序後 hires 節點（兩位數 id）會排在 "4" 前面；主取樣判定不可被順序影響
    assert _find_main_ksampler_id(dict(sorted(wf.items()))) == "4"
    assert hires_params(wf)["upscale_model"] == "4x-AnimeSharp.safetensors"


def test_inject_hires_latent_mode_on_anima_unet_loader():
    wf = _anima_wf()
    assert _inject_hires(wf, width=1024, height=1536, scale=1.31, denoise=0.35, steps=20,
                         sampler="euler", scheduler="simple", upscale_model=None)
    _assert_graph_closed(wf)
    lat = _by_type(wf, "LatentUpscale")[0]
    assert wf[lat]["inputs"]["samples"] == ["5", 0]
    assert (wf[lat]["inputs"]["width"], wf[lat]["inputs"]["height"]) == (1344, 2016)
    assert not _by_type(wf, "UpscaleModelLoader")
    assert hires_params(wf)["upscale_model"] is None


def test_inject_hires_is_idempotent():
    wf = _sdxl_wf()
    assert _inject_hires(wf, width=1024, height=1536, scale=1.5, denoise=0.4, steps=20)
    snapshot = copy.deepcopy(wf)
    assert _inject_hires(wf, width=1024, height=1536, scale=1.5, denoise=0.4, steps=20) is False
    assert wf == snapshot


def test_face_detailer_then_hires_feeds_hires_image_to_detailer():
    wf = _anima_wf()
    wf["10"] = {"class_type": "ToDetailerPipe", "inputs": {}}
    assert _inject_face_detailer(wf, 0.5, 18)
    fd = _by_type(wf, "FaceDetailerPipe")[0]
    assert _inject_hires(wf, width=1024, height=1536, scale=1.31, denoise=0.35, steps=20)
    new_decode = [k for k in _by_type(wf, "VAEDecode") if k != "7"][0]
    assert wf[fd]["inputs"]["image"] == [new_decode, 0]
    assert wf["8"]["inputs"]["images"] == [fd, 0]
    _assert_graph_closed(wf)


def test_inject_hires_without_vaedecode_is_noop():
    wf = _anima_wf()
    del wf["7"], wf["8"]
    assert _inject_hires(wf, width=1024, height=1536, scale=1.3, denoise=0.35, steps=20) is False


# ── _apply_hires：全域開關 × profile × 放大模型可用性 ──────────────────────────
def test_apply_hires_off_by_default():
    wf = _sdxl_wf()
    assert wb._apply_hires(wf, gp.get_profile("illustrious"), 1024, 1536) is False
    assert hires_params(wf) is None


def test_apply_hires_missing_upscaler_falls_back_to_latent(monkeypatch):
    monkeypatch.setattr(config, "HIRES_ENABLED", True)
    monkeypatch.setattr(comfyui_client, "list_upscale_models", lambda: [])
    wf = _sdxl_wf()
    assert wb._apply_hires(wf, gp.get_profile("illustrious"), 1024, 1536)
    assert _by_type(wf, "LatentUpscale") and not _by_type(wf, "UpscaleModelLoader")


def test_apply_hires_uses_upscaler_when_available(monkeypatch):
    monkeypatch.setattr(config, "HIRES_ENABLED", True)
    monkeypatch.setattr(config, "HIRES_UPSCALE_MODEL", "4x-AnimeSharp.safetensors")
    monkeypatch.setattr(comfyui_client, "list_upscale_models", lambda: ["4x-AnimeSharp.safetensors"])
    wf = _anima_wf()
    assert wb._apply_hires(wf, gp.get_profile("anima"), 1024, 1536)
    p = hires_params(wf)
    assert (p["width"], p["height"], p["denoise"]) == (1344, 2016, 0.35)


def test_apply_hires_respects_4g_tier(monkeypatch):
    monkeypatch.setattr(config, "HIRES_ENABLED", True)
    monkeypatch.setattr(config, "GPU_TIER", "4g")
    wf = _sdxl_wf()
    assert wb._apply_hires(wf, gp.get_profile("illustrious"), 1024, 1536) is False


def test_apply_hires_8g_never_queries_upscaler(monkeypatch):
    monkeypatch.setattr(config, "HIRES_ENABLED", True)
    monkeypatch.setattr(config, "GPU_TIER", "8g")
    monkeypatch.setattr(comfyui_client, "list_upscale_models", lambda: pytest.fail("8g 不應查放大模型"))
    wf = _sdxl_wf()
    assert wb._apply_hires(wf, gp.get_profile("illustrious"), 1024, 1536)
    assert hires_params(wf)["scale"] <= gp.TIER_8G_HIRES_MAX_SCALE


# ── /object_info 下拉選項格式 ────────────────────────────────────────────────
@pytest.mark.parametrize("spec,expected", [
    ([["a.pth", "b.safetensors"], {}], ["a.pth", "b.safetensors"]),
    (["COMBO", {"options": ["x.safetensors"]}], ["x.safetensors"]),
    (["COMBO"], []),
    (None, []),
])
def test_combo_options_both_formats(spec, expected):
    assert comfyui_client.combo_options(spec) == expected
