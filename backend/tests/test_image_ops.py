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
    _pixel_fullness_check,
    _detect_body_break,
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


# ── _pixel_fullness_check（T1A 反向升級，2026-07-14 全身外擴誤判修復）──────────────

def _draw_bytes(w, h, box, color=(30, 30, 30), bg=(255, 255, 255)):
    """在 bg 底上畫一個實心矩形當 ink，回傳 PNG bytes。"""
    from PIL import ImageDraw
    im = Image.new("RGB", (w, h), bg)
    ImageDraw.Draw(im).rectangle(box, fill=color)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def test_fullness_caseA_fullbody_feet_near_bottom_upgrades():
    # 案例A：全身草圖，腳貼近底邊仍留 >3% 邊、直立高瘦 → 升級（跳過外擴）
    img = _draw_bytes(446, 1023, [150, 40, 296, 985])
    assert _pixel_fullness_check(img) is True


def test_fullness_caseB_faint_fullbody_upgrades():
    # 案例B：淡鉛筆全身（淺灰 ink 仍偏離白底 >28）→ 升級
    img = _draw_bytes(500, 1000, [180, 30, 320, 940], color=(170, 170, 170))
    assert _pixel_fullness_check(img) is True


def test_fullness_0713_cropped_bust_touches_bottom_not_upgraded():
    # 07-13 緊裁半身填到底：ink 觸底(margin≈0) → 條件1不成立 → 不升級（不回歸）
    img = _draw_bytes(512, 768, [80, 20, 430, 767])
    assert _pixel_fullness_check(img) is False


def test_fullness_real_bust_low_aspect_not_upgraded():
    # 真胸像：上半、方形 AR<2 → 不升級（維持 bust→外擴）
    img = _draw_bytes(512, 512, [100, 20, 420, 300])
    assert _pixel_fullness_check(img) is False


def test_fullness_blank_image_not_upgraded():
    # 全白無 ink → None bbox → 不升級
    img = _png_bytes(512, 512, color=(255, 255, 255))
    assert _pixel_fullness_check(img) is False


# ── _detect_body_break（T3A 外擴斷裂防線，2026-07-15）──────────────────────────

def test_break_ghost_lower_body_detected():
    # 幽靈下半身：上半身塊 + 純背景空帶 + 下方漂浮腿 → 斷裂
    from PIL import ImageDraw
    im = Image.new("RGB", (500, 1000), (240, 90, 90))
    d = ImageDraw.Draw(im)
    d.rectangle([160, 40, 340, 380], fill=(30, 30, 30))     # 上半身
    d.rectangle([170, 640, 330, 950], fill=(30, 30, 30))    # 下方漂浮腿（中間 260px 空帶 = 26% 圖高）
    buf = io.BytesIO(); im.save(buf, "PNG")
    assert _detect_body_break(buf.getvalue()) is True


def test_break_continuous_body_not_flagged():
    # 連續全身（無空帶）→ 不判斷裂
    img = _draw_bytes(500, 1000, [160, 40, 340, 960])
    assert _detect_body_break(img) is False


def test_break_thin_waist_not_flagged():
    # 連續全身但中段細窄（腰/腳踝）：細窄列 frac 介於雙門檻間、不計為空帶 → 不誤攔
    from PIL import ImageDraw
    im = Image.new("RGB", (500, 1000), (240, 90, 90))
    d = ImageDraw.Draw(im)
    d.rectangle([120, 40, 380, 450], fill=(30, 30, 30))     # 上半身（寬）
    d.rectangle([235, 450, 265, 620], fill=(30, 30, 30))    # 細腰（~6% 寬，>GAP_ROW）
    d.rectangle([150, 620, 350, 960], fill=(30, 30, 30))    # 下半身（寬）
    buf = io.BytesIO(); im.save(buf, "PNG")
    assert _detect_body_break(buf.getvalue()) is False


def test_break_blank_output_not_flagged():
    img = _png_bytes(500, 1000, color=(240, 90, 90))
    assert _detect_body_break(img) is False


# ── IPA 參考圖補方（SYNC-005 軌 I，2026-09-19）────────────────────────────────

def test_letterbox_to_square_for_ipa():
    """IPA 走 CLIPImageProcessor，非正方形會被**置中裁切** → 直長草圖只剩腰部。

    ComfyUI 端實錘訊息：
      "the IPAdapter reference image is not a square, CLIPImageProcessor will
       resize and crop it at the center."
    補方後頭與腿都保住。用實際草圖比例 476x1098 驗。
    """
    out = _letterbox_to_aspect(_png_bytes(476, 1098), 1, 1, label="ipa-letterbox")
    w, h = Image.open(io.BytesIO(out)).size
    assert w == h == 1098          # 以長邊為準補寬，內容不被縮小


def test_letterbox_square_input_is_passthrough():
    """已是 1:1 → 原樣回傳（is 比較），不付多餘的編解碼成本。"""
    raw = _png_bytes(1024, 1024)
    assert _letterbox_to_aspect(raw, 1, 1, label="ipa-letterbox") is raw


def test_letterbox_label_defaults_keep_cn_callers_unchanged():
    """label 是新增的具名參數且有預設值 → CN 既有呼叫端零行為變更。"""
    out_default = _letterbox_to_aspect(_png_bytes(300, 900), 768, 1344)
    out_labeled = _letterbox_to_aspect(_png_bytes(300, 900), 768, 1344, label="cn-letterbox")
    assert Image.open(io.BytesIO(out_default)).size == Image.open(io.BytesIO(out_labeled)).size
