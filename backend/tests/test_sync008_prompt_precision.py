"""SYNC-008（2026-09-24）提示詞精度：視覺細節不再被整句剝除、Anima 官方順序、確定性身體 tag 去衝突。

根因與 A/B 證據見 doc/2026-09-24_開發記錄.md 第七節、CODE_NOTES [CN-116]。
Ollama 全部 mock；每個新邏輯都「真的執行」（CLAUDE.md 檢查點 1）。
"""
import pytest

from app.services.ai import vision_extract as ve
from app.services.ai import workflow_builder as wb
from app.services.ai.image_ops import _drop_negative_overlap, _reorder_subject_first

# backend.log:29446（2026-09-23）露碧娜草圖的視覺原文
_REAL_VISUAL = "淺色雙馬尾，淡色眼眸，白皙肌膚，連帽外套與短褲裝束，腿部有幾何線條裝飾"


# ── 視覺過濾：顏色歸欄位、結構歸視覺 ─────────────────────────────────────────

def test_real_sample_keeps_structure_on_lineart():
    """改前：同一句只剩「淡色眼眸」。改後：線稿顏色全拿掉，雙馬尾／外套短褲／腿部裝飾保留。"""
    out = ve._filter_visual_for_llm(
        _REAL_VISUAL, strip_clothing=False, strip_hairstyle=False,
        strip_skin=True, decolor_all=True, decolor_clothing=True, decolor_hair=True,
    )
    assert out == "雙馬尾，連帽外套與短褲裝束，腿部有幾何線條裝飾"


def test_negative_control_old_flags_reproduce_the_loss():
    """負向對照：用改前的旗標組合，細節確實會全丟（證明上一條測的是真問題）。"""
    out = ve._filter_visual_for_llm(
        _REAL_VISUAL, strip_clothing=True, strip_hairstyle=True, strip_skin=True,
    )
    assert "雙馬尾" not in out and "外套" not in out


def test_decolor_clothing_only_touches_clothing():
    out = ve._filter_visual_for_llm(
        "深灰色外套，紅色的圍巾，金屬扣，灰黑色靴子，藍色眼睛",
        strip_clothing=False, strip_hairstyle=False, decolor_clothing=True,
    )
    assert out == "外套，圍巾，金屬扣，靴子，藍色眼睛"


def test_decolor_drops_phrase_left_with_bare_noun():
    assert ve._decolor_phrase("淡色眼眸") == ""
    assert ve._decolor_phrase("淺色雙馬尾") == "雙馬尾"
    assert ve._decolor_phrase("白皙肌膚") == "白皙肌膚"  # 非顏色詞不誤傷


def test_strip_expression_for_expression_mode():
    out = ve._filter_visual_for_llm(
        "雙馬尾，微笑，單手叉腰", strip_clothing=False, strip_hairstyle=False, strip_expression=True,
    )
    assert out == "雙馬尾，單手叉腰"


def test_skin_filter_no_longer_kills_garment_line_detail():
    out = ve._filter_visual_for_llm(
        "腿部有幾何線條裝飾，膚色未填色", strip_clothing=False, strip_hairstyle=False, strip_skin=True,
    )
    assert out == "腿部有幾何線條裝飾"


def test_combined_vision_prompt_asks_structure(monkeypatch):
    """真的跑 _detect_coverage_and_extract_visual，攔截送給視覺模型的 prompt。"""
    seen = {}

    def fake(images, prompt, **kw):
        seen["prompt"] = prompt
        return "COVERAGE: full\nFEATURES: 雙馬尾，外套，短褲，單手叉腰，微笑"

    monkeypatch.setattr(ve._oc, "analyze_multi_images_bytes", fake)
    monkeypatch.setattr(ve.state, "get_vision_model", lambda: "m")
    cov, vis = ve._detect_coverage_and_extract_visual([b"x"])
    assert cov == "full" and "單手叉腰" in vis
    p = seen["prompt"]
    assert "逐件" in p and "姿勢" in p and "表情" in p
    assert f"{ve._FEATURE_CHARS_SINGLE}字" in p


def test_vision_cache_version_bumped():
    """[CN-105] 動到 vision prompt 必 bump，否則舊結果（粗描述）被鎖死命中。"""
    assert ve._VISION_FLOW_VERSION != "v4-2026-07-14"


# ── compile 規則：不再示範整套服裝單一 tag ───────────────────────────────────

def test_templates_render_and_drop_whole_outfit_example():
    from app.services.ai.prompt_engine.styles import STYLE_CONFIG, _DANBOORU_COMMON_RULES
    assert "combat suit" not in _DANBOORU_COMMON_RULES
    assert "GARMENTS" in _DANBOORU_COMMON_RULES and "MERGE" in _DANBOORU_COMMON_RULES
    for style, cfg in STYLE_CONFIG.items():
        rendered = cfg.llm_template.format(prompt="測試輸入")
        assert "測試輸入" in rendered, style
        assert "{" not in rendered.replace("{prompt}", ""), f"{style} 模板殘留未展開大括號"
        assert "tactical vest" not in rendered and "combat suit" not in rendered, style


# ── Anima 組裝：官方順序、負向去衝突 ─────────────────────────────────────────

def test_reorder_subject_first_matches_comfyui_a4():
    assembled = (
        "1girl, child, petite, masterpiece, best quality, absurdres, safe, solo, brown hair, "
        "short twintails, grey jacket, full body, standing, single character, blue archive, @kozaki yuusuke"
    )
    out = _reorder_subject_first(
        assembled, "masterpiece, best quality, absurdres, safe", "blue archive, @kozaki yuusuke",
    )
    assert out == (
        "masterpiece, best quality, absurdres, safe, 1girl, solo, blue archive, @kozaki yuusuke, "
        "child, petite, brown hair, short twintails, grey jacket, full body, standing, single character"
    )


def test_reorder_is_permutation():
    s = "a, (b:1.2), 1girl, masterpiece, x"
    out = _reorder_subject_first(s, "masterpiece", "x")
    assert sorted(out.split(", ")) == sorted(s.split(", "))


def test_drop_negative_overlap_only_removes_asserted():
    neg = "worst quality, artist name, child, toddler, chibi, (halo:1.5)"
    assert _drop_negative_overlap(neg, "1girl, child, petite, ") == \
        "worst quality, artist name, toddler, chibi, (halo:1.5)"
    assert _drop_negative_overlap(neg, "") == neg


def test_real_yml_anima_subject_first_illustrious_untouched():
    fams = wb._load_prompt_profiles()
    assert fams["anima"].get("tag_order") == "subject_first"
    assert fams["anima"].get("style_extra_weight") == 1.0
    assert not fams["illustrious"].get("tag_order"), "illustrious（R1 定版）不得被重排"


def test_workflow_tag_order_resolves_by_family(monkeypatch):
    from app.services.ai.prompt_engine import PromptStyle
    monkeypatch.setattr(wb, "_detect_style", lambda _w: PromptStyle.ANIMA)
    assert wb._workflow_tag_order("AnimaStandardV9_miaomiaoHarem.json") == "subject_first"
    monkeypatch.setattr(wb, "_detect_style", lambda _w: PromptStyle.ILLUSTRIOUS)
    assert wb._workflow_tag_order("Standard_V38.json") == ""
