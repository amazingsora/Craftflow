"""image_ops 純函式單元測試（A3，2026-06-13）。

不需要 DB / Ollama / ComfyUI，純 PIL 與 bytes 運算。
執行：cd backend && pytest tests/test_image_ops.py
"""
import io

import pytest
from PIL import Image

from app.services.ai.image_ops import (
    _border_color,
    _clamp_dim,
    _fullbody_canvas,
    _image_dimensions,
    _is_flat_color_draft,
    _letterbox_to_aspect,
    _pixel_coverage_check,
    _shrink_for_full_body,
    _FULLBODY_CANVAS_TALL,
    _FULLBODY_CANVAS_STD,
    _FULLBODY_CANVAS_SHORT,
)


def _png_bytes(w: int, h: int, color=(200, 120, 80)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


# ── _clamp_dim ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    (100, 512),     # 低於下限 → 512
    (4096, 2048),   # 高於上限 → 2048
    (1000, 960),    # 取 64 倍數（向下）
    (1024, 1024),   # 已是 64 倍數
])
def test_clamp_dim(raw, expected):
    assert _clamp_dim(raw) == expected


# ── _image_dimensions ─────────────────────────────────────────────────────────

def test_image_dimensions_png():
    assert _image_dimensions(_png_bytes(768, 1344)) == (768, 1344)


def test_image_dimensions_jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (640, 832), (10, 20, 30)).save(buf, "JPEG")
    assert _image_dimensions(buf.getvalue()) == (640, 832)


def test_image_dimensions_garbage_falls_back():
    assert _image_dimensions(b"not an image") == (1024, 1024)


# ── _fullbody_canvas ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("height, expected", [
    (175, _FULLBODY_CANVAS_TALL),
    (170, _FULLBODY_CANVAS_TALL),    # 邊界：≥170
    (160, _FULLBODY_CANVAS_STD),
    (149, _FULLBODY_CANVAS_SHORT),   # 邊界：<150
    (None, _FULLBODY_CANVAS_STD),
    ("abc", _FULLBODY_CANVAS_STD),   # 無法解析 → 標準
    ("", _FULLBODY_CANVAS_STD),
])
def test_fullbody_canvas(height, expected):
    assert _fullbody_canvas(height) == expected


# ── _letterbox_to_aspect ──────────────────────────────────────────────────────

def test_letterbox_same_ratio_returns_original():
    raw = _png_bytes(512, 1024)
    assert _letterbox_to_aspect(raw, 768, 1536) is raw  # 比例相同免處理


def test_letterbox_narrow_image_pads_width():
    out = _letterbox_to_aspect(_png_bytes(300, 900), 768, 1344)
    w, h = Image.open(io.BytesIO(out)).size
    assert h == 900                       # 高度不變
    assert abs(w / h - 768 / 1344) < 0.01  # 比例對齊目標


def test_letterbox_keeps_border_color():
    raw = _png_bytes(300, 900, color=(250, 240, 230))
    out = Image.open(io.BytesIO(_letterbox_to_aspect(raw, 768, 1344)))
    # 補邊取樣自背景色 → 邊緣應接近原背景
    r, g, b = out.getpixel((1, out.size[1] // 2))
    assert abs(r - 250) <= 2 and abs(g - 240) <= 2 and abs(b - 230) <= 2


# ── _border_color ─────────────────────────────────────────────────────────────

def test_border_color_flat_image():
    im = Image.new("RGB", (64, 64), (100, 150, 200))
    assert _border_color(im) == (100, 150, 200)


# ── _is_flat_color_draft ──────────────────────────────────────────────────────

def test_flat_color_draft_true():
    assert _is_flat_color_draft(_png_bytes(256, 256)) is True


def test_flat_color_draft_false_for_noisy_image():
    im = Image.new("RGB", (64, 64))
    px = im.load()
    for y in range(64):
        for x in range(64):
            px[x, y] = ((x * 37) % 256, (y * 91) % 256, (x * y) % 256)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    assert _is_flat_color_draft(buf.getvalue()) is False


def test_flat_color_draft_garbage_returns_false():
    assert _is_flat_color_draft(b"garbage") is False


# ── _pixel_coverage_check ─────────────────────────────────────────────────────

def _sketch(content_until: float) -> bytes:
    """產生上半部有雜訊、content_until 以下為平色背景的測試圖。"""
    im = Image.new("RGB", (128, 256), (245, 245, 245))
    px = im.load()
    for y in range(int(256 * content_until)):
        for x in range(128):
            px[x, y] = ((x * 53) % 256, (y * 31) % 256, 60)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def test_pixel_coverage_full_content_no_override():
    assert _pixel_coverage_check(_sketch(1.0)) is None


def test_pixel_coverage_partial():
    # 中段有內容、底部 30% 平色 → partial
    assert _pixel_coverage_check(_sketch(0.65)) == "partial"


def test_pixel_coverage_bust():
    # 中段與底部皆平色 → bust
    assert _pixel_coverage_check(_sketch(0.35)) == "bust"


# ── _shrink_for_full_body ─────────────────────────────────────────────────────

def test_shrink_full_coverage_passthrough():
    raw = _png_bytes(300, 900)
    assert _shrink_for_full_body(raw, 768, 1344, "full") is raw


@pytest.mark.parametrize("coverage, max_ratio", [
    ("partial", 0.58),
    ("bust", 0.42),
])
def test_shrink_partial_and_bust(coverage, max_ratio):
    out = _shrink_for_full_body(_png_bytes(300, 900), 768, 1344, coverage)
    im = Image.open(io.BytesIO(out))
    assert im.size == (768, 1344)  # 輸出為完整畫布
