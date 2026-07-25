"""
character_design_service 純函式單測（P2 2026-07-02、R3 2026-07-12）。
執行：cd backend && pytest tests/test_character_design_pure.py
"""
import pytest

from app.services.ai.character_design_service import (
    _hex_to_sd_color,
    _effective_ksampler_steps,
    _coverage_badge,
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
