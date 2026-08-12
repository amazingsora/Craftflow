"""Anima family 落地 + 能力閘控回歸測試（AC-4，2026-07-25）。

涵蓋 2026-07-25 一批改動：
  AC-1   PromptStyle.ANIMA / STYLE_CONFIG.anima（07-23 §4.3 定案配方）
  AC-2   workflow_builder._detect_style 的 UNETLoader fallback
  AC-2'  capability 三處共用 checkpoint 解析（UI 與生成端 family 一致）
  D'-2   cn_fallback="img2img" 與 _inject_img2img 注入鏈
  B-3'   _set_node_input 上游參數覆寫（採樣/解析度雙真相）

⚠️ 本檔同時是 **Standard_V37 定版零回歸鎖**：V37 相關斷言若失敗，代表 Anima 適配
   污染了已定版的 V37 路徑，必須回頭修，不可改斷言就當過關。

執行：cd backend && pytest tests/test_anima_family.py -v
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.services.ai import capability as cap
from app.services.ai import gen_profile as gp
from app.services.ai import wf_node_ops as ops
from app.services.ai.prompt_engine.styles import PromptStyle, STYLE_CONFIG

_WF_DIR = Path(__file__).resolve().parents[2] / "data" / "custom_workflows"


def _load(name: str) -> dict:
    p = _WF_DIR / name
    if not p.exists():
        pytest.skip(f"workflow {name} 不在 {_WF_DIR}")
    return json.loads(p.read_text(encoding="utf-8"))


# ── AC-1：PromptStyle.ANIMA / STYLE_CONFIG ────────────────────────────────────

def test_anima_enum_exists_and_roundtrips():
    """AC-1 與 AC-2 必須同批：enum 缺席時 PromptStyle('anima') 會 ValueError。"""
    assert PromptStyle("anima") is PromptStyle.ANIMA
    assert PromptStyle.ANIMA in STYLE_CONFIG


def test_anima_style_config_golden():
    """配方 golden — 來源：doc/2026-07-23 開發清單 §4.3。改配方請連同本測試一起改。"""
    c = STYLE_CONFIG[PromptStyle.ANIMA]
    assert c.quality_prefix == (
        "masterpiece, best quality, absurdres, ultra detailed, high contrast"
    )
    # 決策①：family 不做 safety 分級
    for tag in ("safe", "sensitive", "explicit"):
        assert tag not in c.quality_prefix
    # 決策②：光影組不寫死在 family
    for tag in ("bokeh", "depth of field", "backlighting", "light particles"):
        assert tag not in c.quality_prefix
    # Anima 專屬負向對比項（07-22 實測：缺這段必偏白）
    for tag in ("overexposed", "washed out", "faded", "low contrast",
                "blown out highlights", "pale"):
        assert tag in c.negative


@pytest.mark.parametrize("style", list(STYLE_CONFIG))
def test_llm_template_formats_with_only_prompt_field(style):
    """所有家族的 llm_template 必須只含 {prompt} 一個佔位符，且 .format 得起來。

    2026-07-25 實戰 bug：_ANIMA_TEMPLATE 是 f-string，裡面寫 "{{color}} theme" 想表達
    「任何顏色主題 tag」，f-string 求值後變成 {color}，compiler 的
    `config.llm_template.format(prompt=text)` 便當成佔位符 → KeyError: 'color'（500）。
    原測試只驗 STYLE_CONFIG 欄位內容、沒真的跑一次 format，所以沒攔下來。
    """
    import re
    fields = set(re.findall(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})",
                            STYLE_CONFIG[style].llm_template))
    assert fields == {"prompt"}, f"{style.value} 模板含非預期佔位符：{sorted(fields - {'prompt'})}"
    out = STYLE_CONFIG[style].llm_template.format(prompt="測試輸入")
    assert "測試輸入" in out


def test_anima_template_pale_rule_present():
    """NO-PALE 規則本身要留著（修 KeyError 時別把規則一起刪了）。"""
    tpl = STYLE_CONFIG[PromptStyle.ANIMA].llm_template
    for kw in ("pale skin", "pastel colors", "limited palette", "theme"):
        assert kw in tpl


def test_anima_pale_tags_not_banned():
    """決策③：蒼白 tag 僅記錄於 watchlist，不進 banned_tags。"""
    from app.services.ai.prompt_engine import styles as st
    c = STYLE_CONFIG[PromptStyle.ANIMA]
    assert "pale skin" in st._PALE_TAGS_ANIMA_WATCHLIST
    for tag in st._PALE_TAGS_ANIMA_WATCHLIST:
        assert tag not in c.banned_tags


# ── AC-2'：checkpoint 解析（三處共用同一來源）──────────────────────────────────

def test_extract_checkpoint_prefers_checkpoint_loader():
    wf = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "a.safetensors"}},
          "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "b.safetensors"}}}
    assert cap.extract_checkpoint_from_wf(wf) == "a.safetensors"


@pytest.mark.parametrize("ct", ["UNETLoader", "UnetLoaderGGUF", "UNETLoaderGGUF"])
def test_extract_checkpoint_unet_fallback(ct):
    """AC-2 的核心：無 CheckpointLoaderSimple 時要讀得到 unet_name（含 GGUF 變體）。"""
    wf = {"1": {"class_type": ct, "inputs": {"unet_name": "anima_baseV10.safetensors"}}}
    assert cap.extract_checkpoint_from_wf(wf) == "anima_baseV10.safetensors"
    assert cap.resolve_family(cap.extract_checkpoint_from_wf(wf)) == "anima"


def test_extract_checkpoint_empty_inputs():
    assert cap.extract_checkpoint_from_wf({}) == ""
    assert cap.extract_checkpoint_from_wf({"1": None, "2": "x"}) == ""


def test_nova_anime_xl_registered():
    """漏登錄 bug（2026-07-25）：novaAnimeXL 是 Illustrious 衍生，原本 fallback 成 sdxl。
    注意也要確認它不會誤命中 anima（"anime" != "anima"）。"""
    assert cap.resolve_family("novaAnimeXL_ilV190.safetensors") == "illustrious"


def test_anima_workflow_capability_all_false():
    """使用者回報「CN 沒有效果」的根因鎖：UI 端能力必須與生成端閘控一致。"""
    wf = _load("AnimaStandardV7.json")
    c = cap.resolve_capability(wf, cap.extract_checkpoint_from_wf(wf))
    assert c["family"] == "anima"
    assert c["ipa_supported"] is False
    assert c["cn_supported"] is False
    assert c["cn_fallback"] == "img2img"   # 有替代 → 前端仍要顯示控制項
    assert c["models"] is None


# ── Standard_V37 定版零回歸鎖 ────────────────────────────────────────────────

def test_v37_capability_unchanged():
    wf = _load("Standard_V37.json")
    c = cap.resolve_capability(wf, cap.extract_checkpoint_from_wf(wf))
    assert c["family"] == "illustrious"
    assert c["ipa_supported"] is True
    assert c["cn_supported"] is True
    assert c["cn_fallback"] is None
    assert c["models"] is not None


def test_v37_illustrious_style_config_unchanged():
    """V37 的 prompt 由 prompt_profiles.yml 決定，但 family 仍是 fallback 底線。"""
    c = STYLE_CONFIG[PromptStyle.ILLUSTRIOUS]
    assert c.quality_prefix == "masterpiece, best quality, amazing quality, absurdres"
    assert c.negative.startswith("worst quality, low quality, lowres, bad anatomy")


def test_v37_profile_registered_and_anima_not():
    """AC-3：AnimaStandardV7 刻意不登錄 workflow profile（避免與 family 兩份真相）。"""
    from app.services.ai.workflow_builder import _load_prompt_profiles
    profiles = _load_prompt_profiles()
    assert "Standard_V37.json" in profiles
    assert "AnimaStandardV7.json" not in profiles


def test_illustrious_profile_has_no_cn_fallback():
    """SDXL 系家族不得被 D'-2 影響：cn_fallback 必須是 None，否則會走錯路徑。"""
    for fam in ("sdxl", "pony", "noobai", "illustrious"):
        p = gp.get_profile(fam)
        assert p.cn_fallback is None, fam
        assert p.cn_enabled is True, fam
        assert p.ipa_enabled is True, fam


# ── D'-2：img2img 替代 ────────────────────────────────────────────────────────

def test_anima_profile_fallback_and_denoise_mapping():
    p = gp.get_profile("anima")
    assert p.cn_enabled is False and p.ipa_enabled is False
    assert p.cn_fallback == "img2img"
    # cn_weight 越高＝越貼合參考圖；denoise 語義相反，必須單調遞減
    assert p.img2img_denoise(1.0) < p.img2img_denoise(0.5)
    # 夾在設定範圍內
    assert p.img2img_denoise_min <= p.img2img_denoise(1.0) <= p.img2img_denoise_max
    assert p.img2img_denoise_min <= p.img2img_denoise(0.0) <= p.img2img_denoise_max


@pytest.mark.parametrize("endpoint_name", ["generate_character_design", "generate_variant_design"])
def test_api_gate_keeps_use_controlnet_when_cn_fallback_exists(monkeypatch, endpoint_name):
    """2026-08-05 根因鎖：API 層 B5 能力守門不得把有替代路徑的家族打成 use_controlnet=False。

    背景：07-25 D'-2 只修了前端（cnUsable = cnSupported or cn_fallback），後端
    `if not _cap["cn_supported"]: use_controlnet = False` 漏改 → service 的
    cn_fallback 分支永遠進不去，img2img 替代方案自加入起就是死代碼（log 零命中）。
    這個測試鎖住兩層判斷一致，避免再次只修一邊。
    """
    import asyncio
    from app.api import art_generate as ag

    captured = {}

    async def _fake_gen(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(ag, "_current_capability",
                        lambda *a, **k: {"ipa_supported": False, "cn_supported": False,
                                         "cn_fallback": "img2img", "family": "anima"})
    monkeypatch.setattr(ag.character_design_service, endpoint_name, _fake_gen)

    endpoint = getattr(ag, endpoint_name)
    call = {"character_id": 1, "use_ipa": True, "use_controlnet": True, "db": None}
    if endpoint_name == "generate_variant_design":
        call["slot"] = 1
    asyncio.run(endpoint(**call))

    assert captured["use_controlnet"] is True, "有 cn_fallback 時 use_controlnet 被誤關 → img2img 死代碼"
    assert captured["use_ipa"] is False, "ipa_supported=False 仍須關閉（無替代路徑）"


def test_api_gate_still_disables_cn_without_fallback(monkeypatch):
    """反向鎖：家族既不支援 CN 也沒有替代路徑時，守門仍必須關閉（如 flux）。"""
    import asyncio
    from app.api import art_generate as ag

    captured = {}

    async def _fake_gen(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(ag, "_current_capability",
                        lambda *a, **k: {"ipa_supported": False, "cn_supported": False,
                                         "cn_fallback": None, "family": "flux"})
    monkeypatch.setattr(ag.character_design_service, "generate_character_design", _fake_gen)
    asyncio.run(ag.generate_character_design(character_id=1, use_ipa=True,
                                             use_controlnet=True, db=None))
    assert captured["use_controlnet"] is False


# ── 2026-08-05：img2img 參考圖色彩正規化 ──────────────────────────────────────

def _pink_sketch_bytes(w=64, h=128):
    """仿真實草圖：粉紅底 + 深粉線條（去色後背景為中灰，非白）。"""
    import io as _io
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), (240, 190, 195))
    d = ImageDraw.Draw(im)
    d.line([(w // 2, 4), (w // 2, h - 4)], fill=(120, 60, 70), width=2)
    buf = _io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _channels_of(image_bytes):
    import io as _io
    from PIL import Image
    im = Image.open(_io.BytesIO(image_bytes)).convert("RGB")
    px = list(im.getdata())
    return px


def test_i2i_ref_none_is_byte_identical():
    """回滾模式必須完全不動圖，否則「關掉」就不是真的關掉。"""
    from app.services.ai.image_ops import _normalize_i2i_ref
    raw = _pink_sketch_bytes()
    assert _normalize_i2i_ref(raw, "none") is raw


def test_i2i_ref_grayscale_removes_hue():
    """核心需求：去掉草圖色相，避免粉底染整張輸出；但保留明暗層次。"""
    from app.services.ai.image_ops import _normalize_i2i_ref
    raw = _pink_sketch_bytes()
    assert any(r != g or g != b for r, g, b in _channels_of(raw)), "測試素材本身應有色相"
    px = _channels_of(_normalize_i2i_ref(raw, "grayscale"))
    assert all(r == g == b for r, g, b in px), "grayscale 後仍殘留色相"
    assert len({p[0] for p in px}) > 1, "層次被壓平（應保留明暗，不是純色塊）"


def test_i2i_ref_lineart_needs_autocontrast_not_all_black():
    """回歸鎖：草圖去色後背景是中灰，直接套固定門檻會整張變黑（2026-08-05 實作時踩到）。

    正確行為是先 autocontrast 把背景拉到接近白，再二值化 → 必須同時存在黑與白。
    """
    from app.services.ai.image_ops import _normalize_i2i_ref
    px = _channels_of(_normalize_i2i_ref(_pink_sketch_bytes(), "lineart"))
    vals = {p[0] for p in px}
    assert vals <= {0, 255}, f"lineart 應為純二值，實際={sorted(vals)[:8]}"
    assert 0 in vals and 255 in vals, "整張同色＝門檻失效（全黑或全白）"
    dark_ratio = sum(1 for p in px if p[0] == 0) / len(px)
    assert 0.0 < dark_ratio < 0.5, f"線條占比異常={dark_ratio:.1%}"


@pytest.mark.parametrize("bad", ["bogus", "GRAYSCALE ", ""])
def test_i2i_ref_mode_is_validated(bad, monkeypatch):
    """未知/髒 mode 不得靜默走到別的分支：大小寫與空白正規化，無法辨識則退預設。"""
    from app.services.ai.image_ops import _normalize_i2i_ref
    raw = _pink_sketch_bytes()
    px = _channels_of(_normalize_i2i_ref(raw, bad) if bad else _normalize_i2i_ref(raw))
    assert all(r == g == b for r, g, b in px), "應退回預設 grayscale"


def test_i2i_ref_bad_bytes_falls_back_to_input():
    """Resilient errors：參考圖壞掉不可讓生成 crash，回傳原 bytes 繼續跑。"""
    from app.services.ai.image_ops import _normalize_i2i_ref
    junk = b"not-an-image"
    assert _normalize_i2i_ref(junk, "grayscale") == junk


def test_i2i_ref_env_override(monkeypatch):
    """IMG2IMG_REF_MODE 供本機 A/B；打錯字要退預設而不是靜默改行為。"""
    from app.services.ai import image_ops as io_mod
    monkeypatch.setenv("IMG2IMG_REF_MODE", "lineart")
    assert io_mod._resolve_i2i_ref_mode() == "lineart"
    monkeypatch.setenv("IMG2IMG_REF_MODE", "linart")   # typo
    assert io_mod._resolve_i2i_ref_mode() == io_mod._I2I_REF_MODE_DEFAULT


def test_inject_img2img_rewires_latent_and_denoise():
    wf = _load("AnimaStandardV7.json")
    ks = ops._find_main_ksampler_id(wf)
    before_latent = copy.deepcopy(wf[ks]["inputs"]["latent_image"])

    assert ops._inject_img2img(wf, "ref.png", 0.55) is True

    new_latent = wf[ks]["inputs"]["latent_image"]
    assert new_latent != before_latent
    enc = wf[new_latent[0]]
    assert enc["class_type"] == "VAEEncode"
    img = wf[enc["inputs"]["pixels"][0]]
    assert img["class_type"] == "LoadImage" and img["inputs"]["image"] == "ref.png"
    # VAE 必須接到工作流既有的 VAE 來源，不可憑空造一個 loader
    assert enc["inputs"]["vae"] == ops._find_vae_ref(_load("AnimaStandardV7.json"))


def test_inject_img2img_denoise_written_to_shared_param_node():
    """雙真相鎖：AnimaStandardV7 的 denoise 由 node 24 分送 KSampler 與 metadata。
    denoise 必須寫到 node 24，否則 PNG metadata 會記錯值。"""
    wf = _load("AnimaStandardV7.json")
    ks = ops._find_main_ksampler_id(wf)
    ref = wf[ks]["inputs"]["denoise"]
    assert isinstance(ref, list), "前提變了：denoise 不再是節點參照，請重新確認本測試"
    src_id = str(ref[0])

    ops._inject_img2img(wf, "ref.png", 0.55)

    assert wf[src_id]["inputs"]["denoise"] == 0.55
    # KSampler 仍透過參照取值 → 兩個消費端同源
    assert wf[ks]["inputs"]["denoise"] == ref


def test_inject_img2img_missing_ksampler_returns_false():
    assert ops._inject_img2img({}, "ref.png", 0.5) is False


def test_inject_img2img_missing_vae_returns_false():
    wf = {"1": {"class_type": "KSampler", "inputs": {"latent_image": ["2", 0], "denoise": 1.0}}}
    assert ops._inject_img2img(wf, "ref.png", 0.5) is False


# ── B-3'：_set_node_input 上游參數覆寫 ────────────────────────────────────────

def test_set_node_input_literal_in_place():
    wf = {"1": {"class_type": "EmptyLatentImage", "inputs": {"width": 512}}}
    assert ops._set_node_input(wf, "1", "width", 1024) is True
    assert wf["1"]["inputs"]["width"] == 1024


def test_set_node_input_follows_primitive_source():
    """easy int 這類參數節點 → 寫到來源的 value，讓 metadata 等消費端同步。"""
    wf = {
        "1": {"class_type": "easy int", "inputs": {"value": 832}},
        "2": {"class_type": "EmptyLatentImage", "inputs": {"width": ["1", 0]}},
        "3": {"class_type": "Image Saver", "inputs": {"width": ["1", 0]}},
    }
    assert ops._set_node_input(wf, "2", "width", 1024) is True
    assert wf["1"]["inputs"]["value"] == 1024
    assert wf["2"]["inputs"]["width"] == ["1", 0]   # 仍為參照 → 兩端同源
    assert wf["3"]["inputs"]["width"] == ["1", 0]


def test_set_node_input_follows_same_named_source_key():
    """作者型參數節點（Input Parameters (Image Saver)）用同名 key。"""
    wf = {
        "24": {"class_type": "Input Parameters (Image Saver)",
               "inputs": {"steps": 30, "cfg": 4, "denoise": 1}},
        "6": {"class_type": "KSampler", "inputs": {"steps": ["24", 1]}},
    }
    assert ops._set_node_input(wf, "6", "steps", 45) is True
    assert wf["24"]["inputs"]["steps"] == 45


def test_set_node_input_unresolvable_source_falls_back_and_reports_false():
    """來源不可解析時退為字面值，但要回 False 讓呼叫端知道 metadata 可能不同步。"""
    wf = {"6": {"class_type": "KSampler", "inputs": {"steps": ["99", 1]}}}
    assert ops._set_node_input(wf, "6", "steps", 45) is False
    assert wf["6"]["inputs"]["steps"] == 45


def test_set_node_input_missing_node():
    assert ops._set_node_input({}, "nope", "steps", 1) is False


def test_v37_resolution_override_reaches_metadata():
    """V37 的 width/height 同樣是 easy int 參照，且同時餵 EmptyLatentImage 與 Image Saver。
    改動後兩者同源 —— 出圖尺寸不變，metadata 由『恆記工作流內建值』修正為實際值。"""
    wf = _load("Standard_V37.json")
    el = next(k for k, v in wf.items()
              if isinstance(v, dict) and v.get("class_type") == "EmptyLatentImage")
    w_ref = wf[el]["inputs"]["width"]
    if not isinstance(w_ref, list):
        pytest.skip("V37 width 非節點參照，本情境不適用")

    ops._set_node_input(wf, el, "width", 768)

    assert wf[str(w_ref[0])]["inputs"]["value"] == 768
    savers = [v for v in wf.values()
              if isinstance(v, dict) and v.get("class_type", "").startswith("Image Saver")]
    for s in savers:
        if isinstance(s["inputs"].get("width"), list):
            assert str(s["inputs"]["width"][0]) == str(w_ref[0])


# ── E-1 / E-2：單張全身插畫模式（2026-07-26）──────────────────────────────────

def test_fullbody_suffix_is_single_illustration():
    """E-1：suffix 不得再出現 design/reference sheet，且必含 solo。

    直接執行組裝函式而非只驗常數 —— 這段字串會原封不動送進 SD。
    """
    from app.services.ai.character_design_service import _build_fullbody_suffix
    suffix = _build_fullbody_suffix(", light red background")
    low = suffix.lower()
    for banned in ("design sheet", "reference sheet", "multiple views"):
        assert banned not in low, banned
    assert "character illustration" in low
    assert "full body portrait" in low
    assert "solo" in low
    assert "front view" in low
    assert low.endswith(", light red background")


def test_fullbody_suffix_survives_sheet_strip():
    """E-1 × E-2 交互：suffix 本身不得被 _strip_sheet_tags 誤刪任何 tag。"""
    from app.services.ai.character_design_service import _build_fullbody_suffix
    from app.services.ai.image_ops import _strip_sheet_tags
    suffix = _build_fullbody_suffix(", white background")
    before = [t.strip() for t in suffix.split(",") if t.strip()]
    after = [t.strip() for t in _strip_sheet_tags(suffix).split(",") if t.strip()]
    assert before == after


def test_strip_sheet_tags_drops_llm_sheet_synonyms():
    """E-2：LLM 常吐的三種同義寫法都要被剝除，其餘 tag 原形保留。"""
    from app.services.ai.image_ops import _strip_sheet_tags
    out = _strip_sheet_tags(
        "1girl, solo, character design reference sheet, character sheet, "
        "(multiple views:1.1), multiple poses, turnaround sheet, full body, white hair"
    )
    assert out == "1girl, solo, full body, white hair"


def test_strip_sheet_tags_noop_on_clean_prompt():
    from app.services.ai.image_ops import _strip_sheet_tags
    p = "1girl, solo, full body, front view, standing, simple background"
    assert _strip_sheet_tags(p) == p


# ── G-1 / G-2：V37 profile 品質段（2026-07-26）────────────────────────────────

def test_v37_profile_quality_prefix_and_suffix_golden():
    """G-5 golden：profile 層（非 family 層）的品質段定版鎖。"""
    from app.services.ai.workflow_builder import _load_prompt_profiles
    p = _load_prompt_profiles()["Standard_V37.json"]
    assert p["quality_prefix"] == (
        "masterpiece, best quality, (newest:0.6), "
        "(highres, absurdres, very aesthetic:0.8)"
    )
    assert p["quality_suffix"] == (
        "(A highly aesthetic illustration, clean composition, "
        "high-quality digital art, sharp focus on facial expressions:0.6)"
    )
    # 與 negative 的 detailed background/scenery 對衝項必須不在 suffix 內
    assert "detailed background" not in p["quality_suffix"]
    assert "detailed background" in p["negative"]


def test_v37_profile_overrides_reach_compiler_kwargs():
    """profile → compile_prompt kwargs 的欄位對映（只驗登錄欄位有轉成 *_override）。"""
    from app.services.ai.workflow_builder import _workflow_profile_overrides
    ov = _workflow_profile_overrides("Standard_V37.json")
    assert ov["quality_prefix_override"].startswith("masterpiece, best quality, (newest:0.6)")
    assert ov["quality_suffix_override"].startswith("(A highly aesthetic illustration")


def test_weight_group_expansion_covers_new_prefix():
    """G-1 前置驗證：權重群組語法要能展開進 banned_tags，否則 LLM 重複吐 highres/
    absurdres/very aesthetic 時去重失效、正向被灌爆。"""
    from app.services.ai.prompt_engine.styles import _WEIGHT_GROUP_RE
    from app.services.ai.workflow_builder import _workflow_profile_overrides
    ov = _workflow_profile_overrides("Standard_V37.json")
    joined = ", ".join(filter(None, [ov.get("quality_prefix_override"),
                                     ov.get("quality_suffix_override")]))
    expanded = _WEIGHT_GROUP_RE.sub(r"\1", joined)
    tags = {t.strip().lower() for t in expanded.split(",") if t.strip()}
    for t in ("newest", "highres", "absurdres", "very aesthetic", "masterpiece", "best quality"):
        assert t in tags, t


# ── H-3：Image Saver metadata prompt 與實跑同源（2026-07-26）──────────────────

@pytest.mark.parametrize("wf_name", ["Standard_V37.json", "AnimaStandardV7.json"])
def test_saver_metadata_prompt_matches_injected(wf_name):
    """注入後 saver 的 positive/negative 必須是實際送出值，不再是內建 wildcard 鏈參照。"""
    wf = _load(wf_name)
    savers = [v for v in wf.values()
              if isinstance(v, dict) and str(v.get("class_type", "")).startswith("Image Saver")
              and "positive" in v.get("inputs", {})]
    if not savers:
        pytest.skip(f"{wf_name} 無帶 prompt 欄位的 Image Saver 節點")
    assert any(isinstance(s["inputs"]["positive"], list) for s in savers), \
        "前提失效：改動前 positive 應為節點參照"

    ops._inject_prompts(wf, "POS_ACTUAL", "NEG_ACTUAL")

    for s in savers:
        assert s["inputs"]["positive"] == "POS_ACTUAL"
        assert s["inputs"]["negative"] == "NEG_ACTUAL"


def test_saver_metadata_sync_is_noop_without_saver():
    assert ops._sync_saver_prompt_metadata({}, "p", "n") == 0


def test_inject_prompts_still_writes_clip_text_encode():
    """H-3 零回歸：saver 同步不得取代原本的 CLIPTextEncode 注入。"""
    wf = _load("Standard_V37.json")
    ops._inject_prompts(wf, "POS_ACTUAL", "NEG_ACTUAL")
    texts = {n["inputs"].get("text") for n in wf.values()
             if isinstance(n, dict) and n.get("class_type") == "CLIPTextEncode"}
    assert "POS_ACTUAL" in texts and "NEG_ACTUAL" in texts
