# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
"""純影像處理工具（PIL / bytes 層級，無 app 狀態依賴）。

自 api/art_generate.py 下沉（2026-06-11 A1 階段 1）：
letterbox 補邊、尺寸偵測、全身畫布選取、平色草稿偵測、
CN 參考圖縮放（為 SD 補腿留空）、像素級 coverage 後備檢查。
"""
from __future__ import annotations

import io
import os
import logging
import re
import statistics
import struct

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

_FLAT_COLOR_STD_THRESHOLD = 25.0  # max per-channel std to be considered a flat-color draft

# [CN-069] 全身取景常數只保留 standing：同義詞會攤平注意力，正向手部 tag 對 Illustrious 無效
_FULLBODY_POS_TAGS = (
    "standing"
)
# [CN-070] 移除 close-up/portrait：它們壓低臉部佔比，與「臉部像素不足」訴求相反。回滾＝加回第一行
_FULLBODY_NEG_TAGS = (
    "cropped, out of frame, cut off, "
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

# [CN-071] 多視圖／設定稿 tag「含即丟」，⚠️只作用於正向（負向刻意保留作抑制項）
_SHEET_TAG_RE = re.compile(
    r'(reference|design|character|model|turn[ -]?around)\s+sheet'
    r'|multiple\s+views?|multi[ -]?view|multiple\s+poses'
    r'|design\s+reference|reference\s+design',
    re.IGNORECASE,
)


def _strip_sheet_tags(prompt: str) -> str:
    """自**正向** prompt 移除多視圖／設定稿類 tag（見 _SHEET_TAG_RE）。

    逐 tag 比對（去括號去權重後），命中即整個 tag 丟棄；其餘原形保留。
    """
    out = [
        raw.strip() for raw in prompt.split(",")
        if raw.strip() and not _SHEET_TAG_RE.search(raw.strip().lower().strip("() "))
    ]
    return ", ".join(out)


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
def _clamp_dim(v: int) -> int:
    """Round to nearest multiple of 64, clamped to [512, 2048] for SDXL."""
    v = max(512, min(2048, v))
    return (v // 64) * 64


# [CN-072] _clamp_dim 必須定義在畫布常數之前：常數是模組載入時求值，放下面會 NameError
def _env_wh(key: str, w: int, h: int) -> tuple[int, int]:
    """讀 .env 的 `<key>=寬x高` 覆寫全身畫布尺寸；未設或格式錯 → 回預設值。

    B2（SYNC-004，2026-09-19）：B1 把三檔畫布整體上調，但其中只有 STD 有官方/作者
    背書，SHORT/TALL 是等比推的。需要能在本機即時退回舊值做 A/B 而不必改碼，
    比照本檔 `_env_float`（:BODY_FILL_* ）的既有慣例。
    值一律經 `_clamp_dim` 夾成 64 倍數且落在 [512, 2048]。
    例：`FULLBODY_CANVAS_STD=768x1344` 即退回 B1 之前的舊值。
    """
    raw = (os.getenv(key) or "").strip()
    if not raw:
        return w, h
    try:
        raw_w, raw_h = raw.lower().split("x", 1)
        return _clamp_dim(int(raw_w)), _clamp_dim(int(raw_h))
    except (TypeError, ValueError):
        logger.warning("[canvas] %s 格式錯誤（%r），應為「寬x高」如 768x1344 → 沿用預設 %sx%s",
                       key, raw, w, h)
        return w, h


# [CN-073] 三檔畫布短邊統一 1024；⚠️只有 STD 有作者範例背書，SHORT/TALL 是等比推的
_FULLBODY_CANVAS_TALL = _env_wh("FULLBODY_CANVAS_TALL", 1024, 1664)    # 身高 ≥170：高挑/長腿
_FULLBODY_CANVAS_STD = _env_wh("FULLBODY_CANVAS_STD", 1024, 1536)      # 標準（預設，與官方範例同尺寸）
_FULLBODY_CANVAS_SHORT = _env_wh("FULLBODY_CANVAS_SHORT", 1024, 1408)  # 身高 <150 或幼態：矮/Q版
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


def _letterbox_to_aspect(image_bytes: bytes, target_w: int, target_h: int,
                         label: str = "cn-letterbox") -> bytes:
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
    # label 預設 "cn-letterbox"（原字串）→ 既有 CN 呼叫端零行為變更；
    # SYNC-005 軌 I 的 IPA 呼叫端傳 "ipa-letterbox" 以便在 log 分辨兩條路徑。
    logger.info("[%s] %sx%s → %sx%s (target_ar=%.3f)", label, w, h, new_w, new_h, target_ar)
    return out.getvalue()


def _fit_to_canvas(image_bytes: bytes, target_w: int, target_h: int) -> bytes:
    """把圖精確縮放到 target_w x target_h（先補邊對齊比例，再等比縮放）。

    img2img 用（2026-07-25 D'-2）：VAEEncode 的 latent 尺寸由輸入圖決定，會**取代**
    EmptyLatentImage 的尺寸 → 參考圖若不是目標尺寸，出圖尺寸就跟著跑掉。
    先 _letterbox_to_aspect 保住構圖不被裁，再 resize 到精確畫布。
    """
    boxed = _letterbox_to_aspect(image_bytes, target_w, target_h)
    im = Image.open(io.BytesIO(boxed)).convert("RGB")
    if im.size == (target_w, target_h):
        return boxed
    im = im.resize((target_w, target_h), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "PNG")
    logger.info("[img2img-fit] → %sx%s", target_w, target_h)
    return out.getvalue()


# [CN-074] img2img 參考圖需色彩正規化：草圖粉色場直接進 VAEEncode 會讓出圖泛粉
_I2I_REF_MODES = ("none", "grayscale", "lineart")
_I2I_REF_MODE_DEFAULT = "grayscale"
# [CN-075] lineart 二值化前必須先 autocontrast，否則整張判成線條（全黑）
_I2I_LINEART_AUTOCONTRAST_CUTOFF = 1
_I2I_LINEART_THRESHOLD = 190


# [CN-076] lineart 白底要換成目標色；⚠️順序：二值化之後、縮放之前。auto 解析不到時退白底非草圖底色
_I2I_BG_MODE_DEFAULT = "auto"
_I2I_BG_WHITE = (255, 255, 255)

# 英文色名 → RGB。鍵集合涵蓋 lexicon.COLOR_MAP 的所有 value（中文→英文的產出端），
# 外加常見背景色寫法。lexicon 只做「中文→英文色名」，不帶 RGB，故此表獨立維護。
_I2I_BG_COLORS: dict[str, tuple[int, int, int]] = {
    "white": (255, 255, 255), "black": (0, 0, 0),
    "grey": (128, 128, 128), "gray": (128, 128, 128),
    "red": (200, 60, 60), "blue": (70, 110, 200), "green": (80, 170, 90),
    "yellow": (240, 220, 90), "orange": (240, 150, 60), "purple": (150, 90, 190),
    "pink": (240, 160, 190), "brown": (140, 100, 70), "beige": (235, 220, 190),
    "cream": (250, 240, 215), "ivory": (255, 250, 235), "navy": (35, 55, 110),
    "teal": (50, 140, 140), "cyan": (110, 210, 220), "magenta": (210, 70, 170),
    "silver": (200, 200, 205), "golden": (215, 175, 70), "blonde": (230, 205, 140),
    "amber": (230, 170, 60),
}
# 「<color> background」。允許一個修飾詞（light blue background），取最後一個色詞比對。
_I2I_BG_TAG_RE = re.compile(r"([a-z]+(?:\s+[a-z]+)?)\s+background\b", re.I)


def _parse_bg_color_from_prompt(prompt: str | None) -> tuple[int, int, int] | None:
    """從 prompt 抓 "<color> background" 的顏色。抓不到色名回 None。

    prompt 裡常見 simple/detailed/plain background 等非顏色寫法 → 逐一往下找，
    第一個查得到色名的才算命中（不因非顏色 tag 排在前面就放棄）。
    """
    if not prompt:
        return None
    for m in _I2I_BG_TAG_RE.finditer(prompt):
        words = m.group(1).lower().split()
        for w in reversed(words):          # 取最靠近 background 的色詞
            if w in _I2I_BG_COLORS:
                return _I2I_BG_COLORS[w]
    return None


def _parse_hex_color(v: str) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", v.strip())
    if not m:
        return None
    h = m.group(1)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _resolve_i2i_ref_bg(prompt: str | None, sketch_bg: tuple[int, int, int] | None
                        ) -> tuple[int, int, int] | None:
    """依 env `IMG2IMG_REF_BG` 決定線稿要貼的底色。回 None 代表不合成（維持純白底）。"""
    raw = os.getenv("IMG2IMG_REF_BG", _I2I_BG_MODE_DEFAULT).strip()
    v = raw.lower()
    if v == "none":
        return None
    if v not in ("auto", "sketch"):
        rgb = _parse_hex_color(raw)
        if rgb is None:
            logger.warning("[i2i-ref] IMG2IMG_REF_BG=%r 非 auto/sketch/none/#RRGGBB，"
                           "改用預設 %s", raw, _I2I_BG_MODE_DEFAULT)
            v = _I2I_BG_MODE_DEFAULT
        else:
            return rgb
    from_prompt = _parse_bg_color_from_prompt(prompt)
    if from_prompt is not None:
        return from_prompt
    if v == "sketch" and sketch_bg is not None:
        return sketch_bg
    return None


def _composite_lineart_on_bg(im, bg_rgb: tuple[int, int, int]):
    """把二值線稿（255=背景、0=線條）貼到指定底色畫布。線條保持純黑，背景換色。

    用 Image.composite 而非 paste：mask 為二值圖本身，255 處取底色、0 處取黑線，
    不產生任何中間灰階 → 維持「純二值」前提，縮放前不引入邊緣過渡。
    """
    bg_canvas = Image.new("RGB", im.size, bg_rgb)
    line_canvas = Image.new("RGB", im.size, (0, 0, 0))
    return Image.composite(bg_canvas, line_canvas, im)


def _resolve_i2i_ref_mode() -> str:
    """讀 env 決定正規化模式；未知值 → 預設值（不讓打錯字靜默改變行為）。"""
    mode = os.getenv("IMG2IMG_REF_MODE", _I2I_REF_MODE_DEFAULT).strip().lower()
    if mode not in _I2I_REF_MODES:
        logger.warning("[i2i-ref] IMG2IMG_REF_MODE=%r 不是 %s 之一，改用預設 %s",
                       mode, _I2I_REF_MODES, _I2I_REF_MODE_DEFAULT)
        return _I2I_REF_MODE_DEFAULT
    return mode


def _normalize_i2i_ref(image_bytes: bytes, mode: str | None = None,
                       prompt: str | None = None) -> bytes:
    """把 img2img 參考圖的色彩正規化，避免草圖底色污染整張輸出。

    只動色彩，不動幾何（尺寸對齊仍由 _fit_to_canvas 負責）。任何失敗都回傳原圖，
    讓生成繼續跑（Resilient errors）。

    `prompt`（P0，2026-08-12）：僅 lineart 模式使用，供解析 "<color> background"
    決定線稿底色。未傳入時等同解析不到 → 依 IMG2IMG_REF_BG 決定白底或草圖底色。
    """
    mode = (mode or _resolve_i2i_ref_mode()).strip().lower()
    if mode not in _I2I_REF_MODES:
        logger.warning("[i2i-ref] 未知 mode=%r → 改用預設 %s", mode, _I2I_REF_MODE_DEFAULT)
        mode = _I2I_REF_MODE_DEFAULT
    if mode == "none":
        return image_bytes
    try:
        src = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        im = src.convert("L")
        if mode == "lineart":
            im = ImageOps.autocontrast(im, cutoff=_I2I_LINEART_AUTOCONTRAST_CUTOFF)
            im = im.point(lambda v: 0 if v < _I2I_LINEART_THRESHOLD else 255, mode="L")
            # 背景合成必須落在此處：二值化之後、_fit_to_canvas 縮放之前。
            bg = _resolve_i2i_ref_bg(prompt, _border_color(src))
            if bg is not None and bg != _I2I_BG_WHITE:
                rgb = _composite_lineart_on_bg(im, bg)
                out = io.BytesIO()
                rgb.save(out, "PNG")
                logger.info("[i2i-ref] 色彩正規化：mode=%s，線稿底色=%s", mode, bg)
                return out.getvalue()
        out = io.BytesIO()
        im.convert("RGB").save(out, "PNG")
        logger.info("[i2i-ref] 色彩正規化：mode=%s", mode)
        return out.getvalue()
    except Exception as e:
        logger.warning("[i2i-ref] 正規化失敗（%s）→ 沿用原圖", e)
        return image_bytes


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

# [CN-077] 反向升級單向防呆：LLM 判 partial/bust 時用像素幾何反查是否其實已是全身，是則升級 full
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

# [CN-078] 外擴輸出行掃描攔截「幽靈下半身」：主體範圍內出現整段純背景空帶即判斷裂、回退方案1
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
