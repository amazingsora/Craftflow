"""
character_design_service 純函式單測（P2 2026-07-02、R3 2026-07-12）。
執行：cd backend && pytest tests/test_character_design_pure.py
"""
import pytest

from app.models.art_style import ArtStyle
from app.services.ai import character_design_service as cds
from app.services.ai.character_design_service import (
    _hex_to_sd_color,
    _effective_ksampler_steps,
    _coverage_badge,
    _resolve_style_extra,
)


@pytest.mark.parametrize("hex_color, expected", [
    ("#000000", "black"),
    ("#FFFFFF", "white"),
    ("#808080", "gray"),
    ("#FF0000", "light red"),      # 全飽和全亮度 → val>0.75 補 light 前綴
    ("#FFA500", "light orange"),   # hue ~39° 落在 orange 區間
    ("#00FF00", "light green"),
    ("#0000FF", "light blue"),
    # #800080 (CSS "purple") 的 hue=300° 不落在程式的 <290 purple 區間，
    # 落入 else 分支被歸類為 pink；val=0.502 不觸發 dark/light 前綴。
    # 這是目前演算法的已知邊界（HSV 分段與人類色名直覺不完全對齊），非本次範圍要修。
    ("#800080", "pink"),
    ("#FFC0CB", "light red"),      # CSS pink 的 hue 落在 red 分界（<15/>=345）內
])
def test_hex_to_sd_color_known_hues(hex_color, expected):
    assert _hex_to_sd_color(hex_color) == expected


def test_hex_to_sd_color_invalid_input_falls_back():
    assert _hex_to_sd_color("not-a-color") == "colored"


def test_hex_to_sd_color_accepts_without_hash_prefix():
    assert _hex_to_sd_color("FF0000") == "light red"


# ── _effective_ksampler_steps（R3，2026-07-12）───────────────────────────────────

def _wf_with_ksampler(steps):
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "x.safetensors"}},
        "3": {"class_type": "KSampler", "inputs": {"steps": steps}},
    }


def test_effective_steps_returns_given_value_when_not_none():
    """steps 有值（多數家族現況）→ 原樣回傳，不讀 wf，行為與改動前一致。"""
    assert _effective_ksampler_steps(_wf_with_ksampler(28), 26) == 26


def test_effective_steps_reads_back_workflow_json_when_none():
    """steps=None（illustrious 家族現況）→ 未被覆寫，回讀 wf 內建的 KSampler.steps。"""
    assert _effective_ksampler_steps(_wf_with_ksampler(28), None) == 28


def test_effective_steps_none_and_no_ksampler_node_returns_none():
    assert _effective_ksampler_steps({"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}, None) is None


# ── _coverage_badge（S10，2026-07-13）────────────────────────────────────────────

def test_coverage_badge_clamped_shows_arrow():
    assert _coverage_badge("bust", 0.85, 0.50, cn_on=True) == "coverage: bust (CN 0.85→0.50)"


def test_coverage_badge_unclamped_single_value():
    assert _coverage_badge("full", 0.85, 0.85, cn_on=True) == "coverage: full (CN 0.85)"


def test_coverage_badge_cn_off():
    assert _coverage_badge("full", 0.85, 0.85, cn_on=False) == "coverage: full (CN off)"


# ── _resolve_style_extra（P5-5，優先序 DB > profile > .env > 無，見畫風強化規劃 §3.3）───

@pytest.fixture
def _no_env_style(monkeypatch):
    """基準：.env 畫風全關，確認每層測試互不干擾。"""
    monkeypatch.setattr(cds, "PERSONAL_STYLE_ENABLED", False)
    monkeypatch.setattr(cds, "PERSONAL_STYLE_EXTRA_TAGS", "")
    monkeypatch.setattr(cds, "PERSONAL_STYLE_WEIGHT", 1.0)


def test_resolve_style_extra_none_registered_returns_empty(_no_env_style, monkeypatch):
    """四層皆空 → 零介入（tag="", weight=1.0，逐字等同改動前 PERSONAL_STYLE 全關的行為）。"""
    monkeypatch.setattr(cds, "_workflow_style_extra", lambda w: ("", None))
    tag, weight = _resolve_style_extra(None, "text_to_image.json")
    assert tag == ""
    assert weight == 1.0


def test_resolve_style_extra_env_fallback_when_enabled(_no_env_style, monkeypatch):
    """無 DB、無 profile → 落回 .env（ENABLED=true 時才生效）。"""
    monkeypatch.setattr(cds, "_workflow_style_extra", lambda w: ("", None))
    monkeypatch.setattr(cds, "PERSONAL_STYLE_ENABLED", True)
    monkeypatch.setattr(cds, "PERSONAL_STYLE_EXTRA_TAGS", "blue archive")
    monkeypatch.setattr(cds, "PERSONAL_STYLE_WEIGHT", 1.2)
    tag, weight = _resolve_style_extra(None, "text_to_image.json")
    assert tag == "blue archive"
    assert weight == 1.2


def test_resolve_style_extra_env_disabled_stays_empty(_no_env_style, monkeypatch):
    """ENABLED=false 是總開關 —— 即使 .env 字串有值也不生效。"""
    monkeypatch.setattr(cds, "_workflow_style_extra", lambda w: ("", None))
    monkeypatch.setattr(cds, "PERSONAL_STYLE_EXTRA_TAGS", "blue archive")
    tag, weight = _resolve_style_extra(None, "text_to_image.json")
    assert tag == ""


def test_resolve_style_extra_profile_beats_env(_no_env_style, monkeypatch):
    """profile 登錄時贏過 .env（即便 .env 也開著且有值）。"""
    monkeypatch.setattr(cds, "_workflow_style_extra", lambda w: ("flat color, thick outlines", 1.2))
    monkeypatch.setattr(cds, "PERSONAL_STYLE_ENABLED", True)
    monkeypatch.setattr(cds, "PERSONAL_STYLE_EXTRA_TAGS", "blue archive")
    monkeypatch.setattr(cds, "PERSONAL_STYLE_WEIGHT", 9.9)
    tag, weight = _resolve_style_extra(None, "Standard_V37.json")
    assert tag == "flat color, thick outlines"
    assert weight == 1.2  # profile weight 也贏過 .env


def test_resolve_style_extra_profile_weight_absent_falls_back_to_env(_no_env_style, monkeypatch):
    """profile 只登錄 style_extra、未登錄 weight → weight 落回 .env（tag 與 weight 各自獨立判斷）。"""
    monkeypatch.setattr(cds, "_workflow_style_extra", lambda w: ("flat color", None))
    monkeypatch.setattr(cds, "PERSONAL_STYLE_WEIGHT", 2.0)
    tag, weight = _resolve_style_extra(None, "AnimaStandardV8.json")
    assert tag == "flat color"
    assert weight == 2.0


def test_resolve_style_extra_db_beats_everything(_no_env_style, monkeypatch):
    """art_style.extra_tags（DB，單一角色專屬）優先序最高，蓋過 profile 與 .env。"""
    monkeypatch.setattr(cds, "_workflow_style_extra", lambda w: ("flat color", 1.2))
    monkeypatch.setattr(cds, "PERSONAL_STYLE_ENABLED", True)
    monkeypatch.setattr(cds, "PERSONAL_STYLE_EXTRA_TAGS", "blue archive")
    st = ArtStyle(name="s", extra_tags=" vibrant colors, cel shading ")
    tag, weight = _resolve_style_extra(st, "Standard_V37.json")
    assert tag == "vibrant colors, cel shading"
    # DB 只決定 tag，不決定 weight —— weight 仍照 profile > .env 判斷（此處 profile 有登錄）。
    assert weight == 1.2


def test_resolve_style_extra_unregistered_workflow_zero_regression(_no_env_style, monkeypatch):
    """未登錄 workflow → _workflow_style_extra 真實回傳 ("", None)（不 mock），確認端到端零回歸。"""
    monkeypatch.setattr(cds, "PERSONAL_STYLE_ENABLED", True)
    monkeypatch.setattr(cds, "PERSONAL_STYLE_EXTRA_TAGS", "blue archive")
    monkeypatch.setattr(cds, "PERSONAL_STYLE_WEIGHT", 1.2)
    tag, weight = _resolve_style_extra(None, "text_to_image.json")
    assert tag == "blue archive"
    assert weight == 1.2


# ── style_front 組裝格式鎖（P5-11，golden 精神：鎖住加權/前置的字串格式）──────────

def test_style_extra_weighted_assembly_format_matches_frontend_logic():
    """複製 _generate_design_core 內的組裝邏輯（weight!=1.0 → 逐 tag 加權並前置），
    鎖住輸出格式：避免日後改動悄悄改變 (tag:w) 語法或分隔符。"""
    style_extra, weight = "flat color, thick outlines, vibrant colors", 1.2
    weighted = ", ".join(f"({t.strip()}:{weight})" for t in style_extra.split(",") if t.strip())
    style_front = f"{weighted}, " if weighted else ""
    assert style_front == "(flat color:1.2), (thick outlines:1.2), (vibrant colors:1.2), "


def test_style_extra_weight_one_appends_unweighted_suffix_instead():
    """weight==1.0 → 不加權，維持改動前的末端 append 語義（style_extra_str，非 style_front）。"""
    style_extra, weight = "flat color", 1.0
    style_front = ""
    style_extra_str = ""
    if style_extra:
        if weight != 1.0:
            weighted = ", ".join(f"({t.strip()}:{weight})" for t in style_extra.split(",") if t.strip())
            style_front = f"{weighted}, " if weighted else ""
        else:
            style_extra_str = f", {style_extra}"
    assert style_front == ""
    assert style_extra_str == ", flat color"


# ── SYNC-001（2026-09-15）：_wf_checkpoint 內嵌優先 ────────────────────────────
# Codex §2.2 B 案。原本兩處直接把全域 checkpoint 餵給 resolve_capability()，
# 全域與工作流內嵌不同家族時 family 判錯 → 注入錯家族的 IPA/CN 模型，或整段跳過
# Anima 的 LLLite/img2img fallback。這組測試鎖「內嵌優先、讀不到才退全域」。

def test_wf_checkpoint_prefers_embedded_over_global(monkeypatch):
    """SDXL 系工作流（CheckpointLoaderSimple）→ 取內嵌 ckpt_name，忽略全域。"""
    monkeypatch.setattr(cds.state, "get_checkpoint", lambda: "miaomiaoHarem_anima12.safetensors")
    wf = {"30": {"class_type": "CheckpointLoaderSimple",
                 "inputs": {"ckpt_name": "fabricatedXL_v70.safetensors"}}}
    assert cds._wf_checkpoint(wf) == "fabricatedXL_v70.safetensors"


def test_wf_checkpoint_reads_unet_loader_for_anima(monkeypatch):
    """Anima 系工作流無 CheckpointLoaderSimple，模型名在 UNETLoader.unet_name。
    反向情境：全域是 Illustrious，工作流是 Anima —— 判錯會把 SDXL IPA/CN 注進 Anima UNet。"""
    monkeypatch.setattr(cds.state, "get_checkpoint", lambda: "fabricatedXL_v70.safetensors")
    wf = {"1": {"class_type": "UNETLoader",
                "inputs": {"unet_name": "anima_turboV11.safetensors"}}}
    assert cds._wf_checkpoint(wf) == "anima_turboV11.safetensors"


def test_wf_checkpoint_falls_back_to_global_when_not_embedded(monkeypatch):
    """system workflow 未內嵌模型名 → 退回全域（零回歸：等同改動前行為）。"""
    monkeypatch.setattr(cds.state, "get_checkpoint", lambda: "global.safetensors")
    assert cds._wf_checkpoint({"3": {"class_type": "KSampler", "inputs": {}}}) == "global.safetensors"
