"""A12 功能盤點修正的回歸測試（2026-09-27）：P-01～P-07、R-01 的後端部分。"""
import io
from types import SimpleNamespace

import pytest
from PIL import Image

from app.services.ai import workflow_builder as wb


def _png(w=640, h=480):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (255, 255, 255)).save(buf, "PNG")
    return buf.getvalue()


def _anima_wf():
    """AnimaStandardV9 的骨架：UNETLoader + CLIPLoader + LoraManager + 參數節點分送。"""
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "miaomiaoHarem_anima12.safetensors"}},
        "18": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_06b_base.safetensors"}},
        "23": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "5": {"class_type": "Lora Loader (LoraManager)", "inputs": {"model": ["1", 0], "clip": ["18", 0]}},
        "24": {"class_type": "Input Parameters (Image Saver)", "inputs": {"seed": 1, "steps": 20, "denoise": 1.0}},
        "45": {"class_type": "easy int", "inputs": {"value": 1024}},
        "48": {"class_type": "easy int", "inputs": {"value": 1536}},
        "55": {"class_type": "EmptyLatentImage", "inputs": {"width": ["45", 0], "height": ["48", 0], "batch_size": 1}},
        "53": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["5", 1]}},
        "54": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["5", 1]}},
        "6": {"class_type": "KSampler", "inputs": {
            "seed": ["24", 0], "steps": ["24", 1], "denoise": ["24", 5], "model": ["5", 0],
            "positive": ["53", 0], "negative": ["54", 0], "latent_image": ["55", 0]}},
        "35": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["23", 0]}},
    }


# ── P-04：Anima（UNet）工作流的 LoRA 注入 ─────────────────────────────────────

def test_inject_loras_on_unet_workflow_uses_unet_and_clip_loader():
    wf = _anima_wf()
    wb._inject_loras(wf, [{"model": "a.safetensors", "weight": 0.8}, {"model": "b.safetensors", "weight": 1.1}])
    assert wf["_lora_0"]["class_type"] == "LoraLoader"
    assert wf["_lora_0"]["inputs"]["model"] == ["1", 0]
    assert wf["_lora_0"]["inputs"]["clip"] == ["18", 0]
    assert wf["_lora_1"]["inputs"]["model"] == ["_lora_0", 0]
    assert wf["_lora_1"]["inputs"]["clip"] == ["_lora_0", 1]
    # 原本吃 UNet／CLIP 的下游（LoraManager）改接最後一顆 LoRA
    assert wf["5"]["inputs"]["model"] == ["_lora_1", 0]
    assert wf["5"]["inputs"]["clip"] == ["_lora_1", 1]
    # 沒直接吃 UNet 的節點不被動到
    assert wf["6"]["inputs"]["model"] == ["5", 0]


def test_inject_loras_unet_without_clip_loader_is_model_only():
    wf = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "anima_baseV10.safetensors"}},
        "6": {"class_type": "KSampler", "inputs": {"model": ["1", 0]}},
    }
    wb._inject_loras(wf, [{"model": "a.safetensors", "weight": 0.7}])
    assert wf["_lora_0"]["class_type"] == "LoraLoaderModelOnly"
    assert "clip" not in wf["_lora_0"]["inputs"]
    assert wf["6"]["inputs"]["model"] == ["_lora_0", 0]


# ── P-06：tag 清理 ─────────────────────────────────────────────────────────────

def test_sanitize_tags_drops_negation_alternatives_sentences_and_dupes():
    from app.services.ai.art_service import sanitize_tags
    raw = ("1girl, full body, , white background, thigh-high socks or leg warmers, "
           "slightly exaggerated anime proportions, no shading, no color, "
           "no complex background elements, full body, White Background, no humans, (masterpiece:1.2)")
    assert sanitize_tags(raw) == "1girl, full body, white background, no humans, (masterpiece:1.2)"


def test_sanitize_tags_negative_mode_only_dedupes():
    from app.services.ai.art_service import sanitize_tags
    assert sanitize_tags("lowres, no humans, , lowres, bad hands", drop_negations=False) == "lowres, no humans, bad hands"


def test_compose_suffix_has_no_negation_in_positive():
    from app.api import art_generate as ag
    assert not any(t.strip().startswith("no ") for t in ag._COMPOSE_LINEART_TAGS.split(","))
    assert "shading" in ag._COMPOSE_LINEART_NEG


# ── P-07：空 tag ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("masterpiece, best quality, absurdres, , 1girl", "masterpiece, best quality, absurdres, 1girl"),
    ("a,b ,, c, ", "a, b, c"),
    ("(a, b:1.2), c", "(a, b:1.2), c"),
    ("", ""),
])
def test_tidy_tags_removes_empty_entries(raw, expected):
    from app.services.ai.prompt_engine.compiler import _tidy_tags
    assert _tidy_tags(raw) == expected


# ── P-01／P-02：小說改寫 ───────────────────────────────────────────────────────

def test_rewrite_error_string_goes_to_error_field_not_suggestion():
    from app.api import ai_text
    ok = SimpleNamespace(paragraph_index=1, original="x", suggestion="改寫後", reason="r")
    bad = SimpleNamespace(paragraph_index=2, original="y", reason="r",
                          suggestion="[Ollama error at http://127.0.0.1:11434: 404 Client Error]")
    empty = SimpleNamespace(paragraph_index=3, original="z", suggestion="", reason="r")
    assert ai_text._suggestion_dict(ok)["error"] is None
    d = ai_text._suggestion_dict(bad)
    assert d["suggestion"] == "" and "404" in d["error"]
    assert ai_text._suggestion_dict(empty)["error"]


def test_text_endpoints_default_to_runtime_text_model(monkeypatch):
    from app.api import ai_text
    monkeypatch.setattr(ai_text.state, "get_text_model", lambda: "picked:9b")
    assert ai_text._model(None) == "picked:9b"
    assert ai_text._model("explicit") == "explicit"
    assert ai_text.RewriteRequest().model is None


# ── P-03／#15：參考圖引導走目前 workflow，無 CN 時退 LLLite → img2img ─────────

@pytest.fixture
def _ag(monkeypatch):
    from app.api import art_generate as ag
    monkeypatch.setattr(ag.comfyui_client, "upload_image_bytes", lambda b, name: f"up_{name}")
    return ag


def _anima_profile():
    from app.services.ai.gen_profile import get_profile
    return get_profile("anima")


def test_cn_guide_uses_lllite_when_family_has_no_cn(_ag):
    wf = _anima_wf()
    cap = {"cn_supported": False, "cn_fallback": "lllite", "lllite_weight": "lllite.safetensors",
           "lllite_node_class": None}
    mech, params = _ag._apply_cn_guide(wf, cap, _anima_profile(), _png(), 1024, 1536, 0.85, "t")
    assert mech == "lllite"
    assert params["lllite_strength"] == round(0.85 * _anima_profile().lllite_strength_scale, 3)
    ks_model = wf["6"]["inputs"]["model"]
    assert wf[ks_model[0]]["class_type"].startswith("AnimaLLLiteApply")


def test_cn_guide_falls_back_to_img2img(_ag):
    wf = _anima_wf()
    cap = {"cn_supported": False, "cn_fallback": "img2img"}
    mech, params = _ag._apply_cn_guide(wf, cap, _anima_profile(), _png(), 1024, 1536, 0.85, "t")
    assert mech == "img2img"
    enc = wf["6"]["inputs"]["latent_image"]
    assert wf[enc[0]]["class_type"] == "VAEEncode"
    # denoise 是節點參照 → 寫回來源 node 24
    assert wf["24"]["inputs"]["denoise"] == params["denoise"]


def test_set_main_sampler_writes_through_param_nodes(_ag):
    wf = _anima_wf()
    _ag._set_main_sampler(wf, seed=42, steps=28, width=1024, height=768)
    assert wf["6"]["inputs"]["seed"] == ["24", 0] and wf["24"]["inputs"]["seed"] == 42
    assert wf["24"]["inputs"]["steps"] == 28
    assert wf["45"]["inputs"]["value"] == 1024 and wf["48"]["inputs"]["value"] == 768


def test_img_guide_accepts_size_and_cn_weight():
    import inspect
    from app.api import art_generate as ag
    params = inspect.signature(ag.img_guide).parameters
    assert {"width", "height", "cn_weight"} <= set(params)


# ── R-09：外觀年齡卡片 ─────────────────────────────────────────────────────────

def test_appearance_cards_yml_loads_and_has_no_minor_cards():
    from app.services.ai.appearance_cards import list_cards
    keys = [c["key"] for c in list_cards()]
    assert keys == ["young_adult", "mature", "elder"]
    # 未成年卡片要等內容護欄（P-09）還原後才加入
    assert not {"child", "teen"} & set(keys)


@pytest.mark.parametrize("key, gender, pos", [
    ("mature", "female", "mature female"),
    ("mature", "male", "mature male"),
    ("elder", "female", "old woman"),
    ("elder", "male", "old man"),
    ("young_adult", "female", ""),
    ("mature", "neutral", ""),
    ("mature", None, ""),
])
def test_resolve_card_by_gender(key, gender, pos):
    from app.services.ai.appearance_cards import resolve_card
    card = resolve_card(key, gender)
    assert card.positive == pos
    assert "child" in card.negative


@pytest.mark.parametrize("key", [None, "", "none", "no_such_card"])
def test_resolve_card_none_or_unknown(key):
    from app.services.ai.appearance_cards import resolve_card
    assert resolve_card(key, "female") is None


def test_appearance_parts_female_mature():
    from app.services.ai import character_design_service as cds
    body, pos_extra, neg_extra = cds._appearance_parts("mature", "female", "1girl")
    assert body == "mature female, "
    assert pos_extra == ""
    assert "child, teenage" in neg_extra and "masculine features" in neg_extra


def test_appearance_parts_elder_male_uses_adult_pack():
    from app.services.ai import character_design_service as cds
    body, pos_extra, neg_extra = cds._appearance_parts("elder", "male", "1boy")
    assert body == "old man, "
    assert "bishounen" not in pos_extra and "male focus" in pos_extra
    assert "stubble" not in neg_extra  # 年輕化負向（_BOY_NEG_EXTRA）不套
    assert "child, teenage" in neg_extra


def test_appearance_parts_no_card_matches_gender_pack():
    from app.services.ai import character_design_service as cds
    assert cds._appearance_parts(None, "male", "1boy") == ("",) + cds._gender_extras("1boy")


def test_appearance_age_field_wired():
    from app.api.characters import VariantUpdate
    from app.schemas.character import CharacterUpdate, CharacterResponse
    from app.models.character import Character
    assert "appearance_age" in VariantUpdate.model_fields
    assert "appearance_age" in CharacterUpdate.model_fields and "appearance_age" in CharacterResponse.model_fields
    assert hasattr(Character, "appearance_age")


# ── 身材卡片（CN-130）──────────────────────────────────────────────────────────

def test_body_groups_chest_is_female_only_and_blocks_minors():
    from app.services.ai.appearance_cards import list_body_groups
    groups = {g["key"]: g for g in list_body_groups()}
    assert {"build", "chest"} <= set(groups)
    for card in groups["chest"]["cards"]:
        assert card["tags"]["female"] and card["tags"]["male"] is None and card["tags"]["neutral"] is None
    for card in groups["build"]["cards"]:
        assert all(card["tags"][g] for g in ("female", "male", "neutral"))


@pytest.mark.parametrize("keys, gender, age, pos", [
    ("slender,small_breasts", "female", None, "slender, small breasts"),
    ("slender,small_breasts", "male", None, "slender"),
    ("toned,large_breasts", "neutral", None, "toned"),
    ("toned,large_breasts", "female", "teenage", "toned"),
    ("plump", "female", "child", ""),
    ("slender,toned", "female", None, "slender"),
    ("no_such_card", "female", None, ""),
    (None, None, None, ""),
])
def test_resolve_body(keys, gender, age, pos):
    from app.services.ai.appearance_cards import resolve_body
    assert resolve_body(keys, gender, age).positive == pos


def test_body_parts_conflict_tags_strip_llm_positive():
    from app.services.ai import character_design_service as cds
    pos, neg, conflicts = cds._body_parts("small_breasts", "female", "young_adult")
    assert pos == "small breasts, " and "large breasts" in neg
    stripped = cds._drop_negative_overlap("1girl, small breasts, (large breasts:1.1), blue eyes", conflicts)
    assert stripped == "1girl, small breasts, blue eyes"


def test_body_cards_field_wired():
    from app.api.characters import VariantUpdate
    from app.schemas.character import CharacterUpdate, CharacterResponse
    from app.models.character import Character
    assert "body_cards" in VariantUpdate.model_fields
    assert "body_cards" in CharacterUpdate.model_fields and "body_cards" in CharacterResponse.model_fields
    assert hasattr(Character, "body_cards")
