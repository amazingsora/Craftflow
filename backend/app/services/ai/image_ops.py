"""純影像處理工具（PIL / bytes 層級，無 app 狀態依賴）。

自 api/art_generate.py 下沉（2026-06-11 A1 階段 1）：
letterbox 補邊、尺寸偵測、全身畫布選取、平色草稿偵測、
CN 參考圖縮放（為 SD 補腿留空）、像素級 coverage 後備檢查。
"""
from __future__ import annotations

import io
import os
import logging
import statistics
import struct

from PIL import Image

logger = logging.getLogger(__name__)

_FLAT_COLOR_STD_THRESHOLD = 25.0  # max per-channel std to be considered a flat-color draft

# ── 全身人設取景常數（痛點3）─────────────────────────────────────────────────
# 強化整體取景與手部/四肢補全，避免只生成中段（下巴到大腿）。集中為具名常數，
# 避免 magic string 散落於主角色與變體兩處生成流程。
# 2026-06-23：去語義稀釋。呼叫端 suffix 已含 "full body, front view"，此處不再重複
# full body shot / head to toe / full body visible（同義詞攤平注意力）；只保留取景補強
# 的 standing。
# S1（2026-07-12）：拔 "detailed hands, five fingers"——Illustrious 正向手部 tag 無效
# （手部品質應由負向擋，見下方 _FULLBODY_NEG_TAGS 的 missing fingers/extra digits/
# bad hands/fused fingers + FaceDetailer），純稀釋且實測歸因為零效益 tag。
_FULLBODY_POS_TAGS = (
    "standing"
)
# 全身專屬負向：抑制裁切/特寫構圖，並補全手指相關防護（部分底模預設未含）。
_FULLBODY_NEG_TAGS = (
    "cropped, out of frame, cut off, close-up, portrait, "
    "missing fingers, extra digits, bad hands, fused fingers"
)

# 框架類同義詞 → 去重比對用的代表（只用於比對，不改寫保留標籤的原形）。
_FRAMING_SYNONYMS = {
    "full body shot": "full body",
    "full body visible": "full body",
    "full body portrait": "full body",
    "head to toe": "full body",
    "whole body": "full body",
}


def _dedup_tags(prompt: str) -> str:
    """去除組裝後 prompt 的重複標籤（保留首次出現的原形）。

    額外把 full body 系框架同義詞收斂為單一概念，避免 LLM（翻譯「全身正面」）
    與 suffix（確定性補 full body）各補一份。權重語法 (tag:1.1) 去括號去權重後比對。
    """
    seen: set[str] = set()
    out: list[str] = []
    for raw in prompt.split(","):
        tag = raw.strip()
        if not tag:
            continue
        norm = tag.lower().strip("() ")
        if ":" in norm:
            norm = norm.rsplit(":", 1)[0].strip()
        norm = _FRAMING_SYNONYMS.get(norm, norm)
        if norm in seen:
            continue
        seen.add(norm)
        out.append(tag)
    return ", ".join(out)
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

# 半身→全身外擴的畫布幾何：概念圖佔畫布高度比例。可由 env 覆寫做 A/B(預設＝定版值，行為不變)。
def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default
_BODY_FILL_RATIO = {"full": 1.0,
                    "partial": _env_float("BODY_FILL_PARTIAL", 0.58),
                    "bust": _env_float("BODY_FILL_BUST", 0.42)}
_BODY_TOP_OFFSET = {"full": 0.0,
                    "partial": _env_float("BODY_TOP_OFFSET_PARTIAL", 0.02),
                    "bust": _env_float("BODY_TOP_OFFSET_BUST", 0.02)}


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

# ── 反向升級檢查（2026-07-14 全身外擴誤判修復 T1A）─────────────────────────────
# 事故：LLM 把「完整站立全身草圖」誤判 partial/bust → 觸發外擴 → 在已完整的身體
# 下方再 inpaint 一套腿（幽靈下半身／比例被拉長）。coverage 誤判偏差中，
# full→partial（少補腿）代價 << partial→full（憑空多生下半身），故只加「反向升級」單向
# 防呆：LLM 判 partial/bust 時，用像素幾何反查草圖是否其實已是完整站立全身，是則升級
# full、跳過外擴。雙條件「同時」成立才升級，任一不成立即維持 LLM 判定 → 對真半身零回歸。
_FULLNESS_BOTTOM_MARGIN = _env_float("FULLNESS_BOTTOM_MARGIN", 0.015)  # ink bbox 底距畫布底 ≥ 此比例 → 角色收尾於畫面內。2026-07-15：實測真半身margin=0%、真全身≥2%，0.03太嚴會擋掉2%的全身(附件1/6)→降0.015；仍是調參(真全身腳觸底邊者仍漏)，根治見 T1B DWPose
_FULLNESS_MIN_AR = _env_float("FULLNESS_MIN_AR", 2.0)                 # ink bbox 高/寬 ≥ 此值 → 站立全身 prior（胸像 AR≈1.0–1.3）
_FULLNESS_INK_DELTA = _env_float("FULLNESS_INK_DELTA", 28.0)          # 偏離背景色歐氏距離 ≥ 此值 → 視為 ink（非固定灰階閾值，淡鉛筆稿才抓得到）
_FULLNESS_MAX_EDGE = 256                                              # bbox 計算前降採樣最長邊（比例不受影響、提速）


def _ink_bbox(image_bytes: bytes) -> tuple[tuple[int, int, int, int], int, int] | None:
    """以背景色為基準二值化，回傳 ink 像素 bounding box (l,t,r,b) 與降採樣後畫布 (w,h)。

    閾值取「偏離 _border_color 的歐氏距離」（非固定灰階閾值），淡鉛筆稿也抓得到。
    無任何 ink 像素 → None。最長邊降採樣至 _FULLNESS_MAX_EDGE 提速（bbox 比例不變）。
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w0, h0 = img.size
        longest = max(w0, h0)
        if longest > _FULLNESS_MAX_EDGE:
            scale = _FULLNESS_MAX_EDGE / longest
            img = img.resize((max(1, int(w0 * scale)), max(1, int(h0 * scale))), Image.BILINEAR)
        w, h = img.size
        br, bg, bb = _border_color(img)
        px = img.load()
        delta_sq = _FULLNESS_INK_DELTA ** 2
        min_x, min_y, max_x, max_y = w, h, -1, -1
        for y in range(h):
            for x in range(w):
                r, g, b = px[x, y]
                if (r - br) ** 2 + (g - bg) ** 2 + (b - bb) ** 2 >= delta_sq:
                    if x < min_x:
                        min_x = x
                    if x > max_x:
                        max_x = x
                    if y < min_y:
                        min_y = y
                    if y > max_y:
                        max_y = y
        if max_x < 0:
            return None
        return (min_x, min_y, max_x, max_y), w, h
    except Exception:
        return None


def _pixel_fullness_check(image_bytes: bytes) -> bool:
    """反向升級：LLM 判 partial/bust 但草圖幾何其實是完整站立全身 → True（升級 full、跳過外擴）。

    雙條件「同時」成立才升級（避免把真半身誤升級成 full 造成回歸）：
      1. 底部留白：ink bbox 最低點距底邊 ≥ FULLNESS_BOTTOM_MARGIN 圖高（角色完整收尾於畫面內）
      2. 直立比例：ink bbox 高/寬 ≥ FULLNESS_MIN_AR（站立全身 prior；胸像 AR≈1.0–1.3）
    07-13「緊裁半身填到底」ink 觸底 → 條件1不成立 → 不升級 → 不回歸。
    """
    res = _ink_bbox(image_bytes)
    if res is None:
        return False
    (l, t, r, b), w, h = res
    bbox_w = max(1, r - l + 1)
    bbox_h = b - t + 1
    bottom_margin = (h - 1 - b) / h              # ink bbox 底距畫布底的比例
    aspect = bbox_h / bbox_w
    upgrade = bottom_margin >= _FULLNESS_BOTTOM_MARGIN and aspect >= _FULLNESS_MIN_AR
    logger.info(
        "[fullness-check] bbox=%s canvas=%dx%d bottom_margin=%.3f(>=%.3f) ar=%.2f(>=%.2f) -> upgrade=%s",
        (l, t, r, b), w, h, bottom_margin, _FULLNESS_BOTTOM_MARGIN, aspect, _FULLNESS_MIN_AR, upgrade,
    )
    return upgrade

# ── 外擴輸出斷裂偵測（2026-07-15 全身外擴誤判修復 Stage 3 T3A）──────────────────────
# 最後防線：即使判定層誤放行、外擴仍生出「上半身完整 + 一段背景空帶 + 下方漂浮第二套腿」
# 的幽靈下半身（附件三實例），這裡在外擴輸出上做行掃描攔截：主體垂直範圍內若存在一整段
# 「整排幾乎純背景色」的空帶（≥ EXPAND_BREAK_MIN_FRAC 圖高），判定主體斷裂 → 呼叫端丟棄
# 外擴、回退方案1（縮圖＋夾 CN）。用雙門檻避開腳踝/脖子等細窄處誤判為斷裂。
_EXPAND_BREAK_MIN_FRAC = _env_float("EXPAND_BREAK_MIN_FRAC", 0.08)  # 主體內連續空帶 ≥ 此比例圖高 → 判斷裂
_EXPAND_BREAK_CONTENT_ROW = _env_float("EXPAND_BREAK_CONTENT_ROW", 0.02)  # 該列 ink 佔寬 ≥ 此比例 → 視為「有主體」列
_EXPAND_BREAK_GAP_ROW = _env_float("EXPAND_BREAK_GAP_ROW", 0.005)         # 該列 ink 佔寬 ≤ 此比例 → 視為「純背景」列（腳踝等細處落在兩者間、不計為空帶）


def _detect_body_break(image_bytes: bytes) -> bool:
    """外擴輸出主體斷裂偵測：主體垂直範圍內有整段純背景空帶 → True（幽靈下半身，應丟棄）。

    行掃描每列 ink 佔寬比例：content 列（≥ CONTENT_ROW）標出主體上下界；主體界內連續
    gap 列（≤ GAP_ROW）最長段 ≥ MIN_FRAC 圖高 → 斷裂。雙門檻使腳踝/脖子等細窄列（落在
    兩門檻之間）不被誤計為空帶，避免誤攔正常全身。
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w0, h0 = img.size
        longest = max(w0, h0)
        if longest > _FULLNESS_MAX_EDGE:
            scale = _FULLNESS_MAX_EDGE / longest
            img = img.resize((max(1, int(w0 * scale)), max(1, int(h0 * scale))), Image.BILINEAR)
        w, h = img.size
        br, bg, bb = _border_color(img)
        px = img.load()
        delta_sq = _FULLNESS_INK_DELTA ** 2
        frac = []
        for y in range(h):
            cnt = 0
            for x in range(w):
                r, g, b = px[x, y]
                if (r - br) ** 2 + (g - bg) ** 2 + (b - bb) ** 2 >= delta_sq:
                    cnt += 1
            frac.append(cnt / w)
        content_rows = [y for y in range(h) if frac[y] >= _EXPAND_BREAK_CONTENT_ROW]
        if len(content_rows) < 2:
            return False
        top, bottom = content_rows[0], content_rows[-1]
        # 主體界內最長連續 gap 段
        longest_gap = cur = 0
        for y in range(top, bottom + 1):
            if frac[y] <= _EXPAND_BREAK_GAP_ROW:
                cur += 1
                longest_gap = max(longest_gap, cur)
            else:
                cur = 0
        broken = longest_gap >= _EXPAND_BREAK_MIN_FRAC * h
        logger.info(
            "[expand-break] canvas=%dx%d body=[%d,%d] longest_gap=%d(>=%d) -> broken=%s",
            w, h, top, bottom, longest_gap, int(_EXPAND_BREAK_MIN_FRAC * h), broken,
        )
        return broken
    except Exception as e:
        logger.warning("[expand-break] 偵測失敗，視為未斷裂: %s", e)
        return False
