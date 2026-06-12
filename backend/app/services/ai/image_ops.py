"""純影像處理工具（PIL / bytes 層級，無 app 狀態依賴）。

自 api/art_generate.py 下沉（2026-06-11 A1 階段 1）：
letterbox 補邊、尺寸偵測、全身畫布選取、平色草稿偵測、
CN 參考圖縮放（為 SD 補腿留空）、像素級 coverage 後備檢查。
"""
from __future__ import annotations

import io
import logging
import statistics
import struct

from PIL import Image

logger = logging.getLogger(__name__)

_FLAT_COLOR_STD_THRESHOLD = 25.0  # max per-channel std to be considered a flat-color draft

# ── 全身人設取景常數（痛點3）─────────────────────────────────────────────────
# 強化整體取景與手部/四肢補全，避免只生成中段（下巴到大腿）。集中為具名常數，
# 避免 magic string 散落於主角色與變體兩處生成流程。
_FULLBODY_POS_TAGS = (
    "full body shot, head to toe, full body visible, standing, detailed hands, five fingers"
)
# 全身專屬負向：抑制裁切/特寫構圖，並補全手指相關防護（部分底模預設未含）。
_FULLBODY_NEG_TAGS = (
    "cropped, out of frame, cut off, close-up, portrait, "
    "missing fingers, extra digits, bad hands, fused fingers"
)
# 全身畫布比例：依角色身形自動選取（「自動匹配大小」）。皆為 64 倍數、約 1MP，
# 貼近 SDXL 訓練分佈。高瘦 → 更長縱向畫布（多給頭/腳空間，減少裁切）；矮/幼態 → 較方。
# 2026-06-07：整體往上拉一個 SDXL 直幅 bucket，加大縱向空間。部分 checkpoint
# （如 AnythingXL_xl）偏 portrait 構圖，較矮畫布會裁掉小腿/腳；加高後全身較完整。
_FULLBODY_CANVAS_TALL = (704, 1408)    # 身高 ≥170：高挑/長腿（比例 1:2）
_FULLBODY_CANVAS_STD = (768, 1344)     # 標準成人比例（預設，SDXL 直幅 bucket）
_FULLBODY_CANVAS_SHORT = (832, 1216)   # 身高 <150 或幼態：矮/Q版
# 身高分界（cm）
_FULLBODY_TALL_CM = 170
_FULLBODY_SHORT_CM = 150
_FULLBODY_WIDTH, _FULLBODY_HEIGHT = _FULLBODY_CANVAS_STD

_BODY_FILL_RATIO = {"full": 1.0, "partial": 0.58, "bust": 0.42}
_BODY_TOP_OFFSET = {"full": 0.0, "partial": 0.02, "bust": 0.02}


def _border_color(im) -> tuple[int, int, int]:
    """取概念圖四角與上下緣中點的平均色，作為 letterbox 補邊色（與背景一致 → Canny 無接縫）。"""
    w, h = im.size
    px = im.load()
    pts = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1], px[w // 2, 0], px[w // 2, h - 1]]
    n = len(pts)
    return (sum(p[0] for p in pts) // n, sum(p[1] for p in pts) // n, sum(p[2] for p in pts) // n)


def _letterbox_to_aspect(image_bytes: bytes, target_w: int, target_h: int) -> bytes:
    """
    把概念圖補邊（letterbox）成與生成畫布相同比例，避免 ComfyUI 對 ControlNet hint 圖
    做置中裁切而切掉頭/腳（窄長草圖塞進較寬畫布 → 上下被裁 → 只剩中段）。
    補邊用取樣背景色，置中貼上，整張全身（含草圖姿勢）等比保留。
    """
    im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = im.size
    target_ar = target_w / target_h
    src_ar = w / h
    if abs(src_ar - target_ar) < 1e-3:
        return image_bytes  # 比例已相符，免處理
    if src_ar < target_ar:        # 太窄 → 左右補邊
        new_w, new_h = round(h * target_ar), h
    else:                         # 太寬 → 上下補邊
        new_w, new_h = w, round(w / target_ar)
    canvas = Image.new("RGB", (new_w, new_h), _border_color(im))
    canvas.paste(im, ((new_w - w) // 2, (new_h - h) // 2))
    out = io.BytesIO()
    canvas.save(out, "PNG")
    logger.info("[cn-letterbox] %sx%s → %sx%s (target_ar=%.3f)", w, h, new_w, new_h, target_ar)
    return out.getvalue()


def _image_dimensions(image_bytes: bytes) -> tuple[int, int]:
    """Read width/height from PNG or JPEG bytes without external libs. Falls back to 1024x1024."""
    try:
        if image_bytes[:4] == b'\x89PNG':
            w = struct.unpack('>I', image_bytes[16:20])[0]
            h = struct.unpack('>I', image_bytes[20:24])[0]
            return _clamp_dim(w), _clamp_dim(h)
        if image_bytes[:2] == b'\xff\xd8':
            i = 2
            while i + 4 < len(image_bytes):
                if image_bytes[i] != 0xff:
                    break
                marker = image_bytes[i + 1]
                if marker in (0xc0, 0xc1, 0xc2):
                    h = struct.unpack('>H', image_bytes[i + 5:i + 7])[0]
                    w = struct.unpack('>H', image_bytes[i + 7:i + 9])[0]
                    return _clamp_dim(w), _clamp_dim(h)
                length = struct.unpack('>H', image_bytes[i + 2:i + 4])[0]
                i += 2 + length
    except Exception:
        pass
    return 1024, 1024


def _clamp_dim(v: int) -> int:
    """Round to nearest multiple of 64, clamped to [512, 2048] for SDXL."""
    v = max(512, min(2048, v))
    return (v // 64) * 64


def _fullbody_canvas(height) -> tuple[int, int]:
    """依角色身高自動選全身畫布比例；身高未知或無法解析則用標準比例。"""
    try:
        h = float(height) if height not in (None, "") else None
    except (TypeError, ValueError):
        h = None
    if h is None:
        return _FULLBODY_CANVAS_STD
    if h >= _FULLBODY_TALL_CM:
        return _FULLBODY_CANVAS_TALL
    if h < _FULLBODY_SHORT_CM:
        return _FULLBODY_CANVAS_SHORT
    return _FULLBODY_CANVAS_STD


def _is_flat_color_draft(image_bytes: bytes) -> bool:
    """
    Returns True when the image is a single-color fill with no meaningful content.
    Uses per-channel std-deviation on a 32×32 thumbnail; a purely flat canvas has
    std ≈ 0, a fully colored character illustration typically exceeds 40.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((32, 32))
        pixels = list(img.getdata())
        channel_stds = [statistics.stdev(p[c] for p in pixels) for c in range(3)]
        return max(channel_stds) < _FLAT_COLOR_STD_THRESHOLD
    except Exception:
        return False


def _shrink_for_full_body(image_bytes: bytes, target_w: int, target_h: int, coverage: str) -> bytes:
    """
    Scale down the CN reference image so the character occupies only part of the canvas,
    leaving room at the bottom for SD to generate the missing lower body.
    coverage: "full" → no change (returns original for normal letterbox path)
              "partial" → ~72 % canvas height, 4 % top offset
              "bust"    → ~55 % canvas height, 5 % top offset
    """
    fill = _BODY_FILL_RATIO.get(coverage, 0.72)
    if fill >= 1.0:
        return image_bytes
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        max_h = int(target_h * fill)
        max_w = target_w
        scale = min(max_w / w, max_h / h)
        new_w, new_h = int(w * scale), int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

        bg = _border_color(img)
        canvas = Image.new("RGB", (target_w, target_h), bg)
        top = int(target_h * _BODY_TOP_OFFSET.get(coverage, 0.04))
        left = (target_w - new_w) // 2
        canvas.paste(img, (left, top))

        out = io.BytesIO()
        canvas.save(out, format="PNG")
        return out.getvalue()
    except Exception as e:
        logger.error("[shrink-full-body] error: %s", e)
        return image_bytes


def _pixel_coverage_check(image_bytes: bytes) -> str | None:
    """
    Pixel-based fallback: if the bottom 30% of the image is mostly a flat
    background colour (std-dev < threshold), the sketch is partial/bust regardless
    of what the LLM said.  Returns "partial", "bust", or None (no override).
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        bottom_band = img.crop((0, int(h * 0.70), w, h))
        pixels = list(bottom_band.getdata())
        n = len(pixels)
        if n == 0:
            return None
        r_mean = sum(p[0] for p in pixels) / n
        g_mean = sum(p[1] for p in pixels) / n
        b_mean = sum(p[2] for p in pixels) / n
        variance = sum(
            (p[0] - r_mean) ** 2 + (p[1] - g_mean) ** 2 + (p[2] - b_mean) ** 2
            for p in pixels
        ) / n
        std_dev = variance ** 0.5
        # Flat background (std_dev < 18): sketch character doesn't reach the bottom
        if std_dev < 18:
            mid_band = img.crop((0, int(h * 0.40), w, int(h * 0.70)))
            mid_pixels = list(mid_band.getdata())
            m = len(mid_pixels)
            mid_r = sum(p[0] for p in mid_pixels) / m
            mid_g = sum(p[1] for p in mid_pixels) / m
            mid_b = sum(p[2] for p in mid_pixels) / m
            mid_var = sum(
                (p[0] - mid_r) ** 2 + (p[1] - mid_g) ** 2 + (p[2] - mid_b) ** 2
                for p in mid_pixels
            ) / m
            mid_std = mid_var ** 0.5
            # Middle also flat → bust; middle has content → partial
            return "bust" if mid_std < 18 else "partial"
    except Exception:
        pass
    return None
