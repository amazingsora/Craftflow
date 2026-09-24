# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
"""Vision 抽取與角色 SD 標籤：coverage 偵測、視覺特徵抽取與快取、
角色屬性（性別/年齡/身高）→ SD 標籤、服裝/髮型詞過濾。"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from app.core import state
from app.services.ai import ollama_client as _oc
from app.services.ai.vram_manager import guardian

logger = logging.getLogger(__name__)

# ── Persistent cache file ─────────────────────────────────────────────────────
_VISION_CACHE_FILE = Path(__file__).resolve().parents[3] / "data" / "vision_cache.json"


# [CN-116] 視覺特徵題目（combined 與 plain 兩條路共用）。字數上限隨題目變多而放寬。
_FEATURE_CHARS_SINGLE = 120
_FEATURE_CHARS_MULTI = 140
_FEATURE_ITEMS = (
    "① 髮色與髮型（長度與形狀） ② 眼睛顏色 ③ 膚色 "
    "④ 服裝逐件列出（上身、下身、腿部、鞋子、配件，每件一個短語） "
    "⑤ 姿勢（站姿與雙手位置） ⑥ 表情 ⑦ 明顯特殊特徵"
)
_FEATURE_ITEMS_MULTI = (
    "① 髮色與髮型（長度與形狀） ② 眼睛顏色 ③ 膚色 "
    "④ 服裝逐件列出（上身、下身、腿部、鞋子、配件，每件一個短語） "
    "⑤ 各圖均出現的姿勢與表情 ⑥ 各圖均出現的特殊特徵"
)


def _detect_coverage_and_extract_visual(images_bytes: list[bytes]) -> tuple[str, str]:
    """Single Ollama call that combines body-coverage classification and visual feature extraction [FD-089]"""
    ignore_bg = (
        "【線稿警告】這可能是未上色的鉛筆稿／線稿，且常帶單色（如粉紅色）背景。"
        "規則一：完全忽略背景顏色——粉紅色或任何單色背景，絕不可當成髮色或服裝顏色。"
        "規則二：若畫面只有線條、沒有實際填色，請直接省略顏色、不要寫出任何顏色詞，也不要寫「線稿未上色」這類字樣，"
        "只描述髮型長度與形狀、逐件服裝的款式、姿勢、表情與明顯特徵。嚴禁臆測顏色。只觀察「角色線條內」的特徵。"
    )
    n = len(images_bytes)
    # [CN-116] 不抽體型（由年齡/身高決定）；服裝逐件＋姿勢＋表情。線稿顏色由規則二與
    # _filter_visual_for_llm(decolor_all) 擋掉
    if n == 1:
        feature_q = (
            f"B. 視覺特徵（逗號分隔的中文短語，控制在{_FEATURE_CHARS_SINGLE}字以內）：\n"
            f"{_FEATURE_ITEMS}"
        )
    else:
        feature_q = (
            f"B. {n}張圖共同視覺特徵（逗號分隔的中文短語，控制在{_FEATURE_CHARS_MULTI}字以內）：\n"
            f"{_FEATURE_ITEMS_MULTI}"
        )
    prompt = (
        f"{ignore_bg}\n\n"
        "請回答以下兩個問題：\n\n"
        "A. 身體遮蔽程度（只回答一個英文詞，依下列步驟判斷）：\n"
        "  步驟1：畫面最底部有沒有畫出「腳掌、腳趾或鞋子」？\n"
        "    - 有看到腳掌／鞋子 → 'full'\n"
        "    - 沒看到腳掌／鞋子 → 進入步驟2（此時絕不可判 full）\n"
        "  步驟2：（沒有腳的前提下）最多能看到身體到哪裡？\n"
        "    - 看得到大腿、膝蓋或小腿（但沒有腳） → 'partial'\n"
        "    - 只看得到腰部以上（看不到大腿） → 'bust'\n"
        "  ⚠️ 關鍵規則：只要畫面底部沒有腳掌或鞋子，即使角色已畫到大腿、"
        "即使人物佔滿整個畫面高度，都一律判 'partial'，絕對不是 'full'。\n\n"
        f"{feature_q}\n\n"
        "回答格式（嚴格遵守）：\n"
        "COVERAGE: [一個英文詞]\n"
        "FEATURES: [逗號分隔的中文短語]"
    )
    try:
        result = _oc.analyze_multi_images_bytes(
            images_bytes, prompt,
            model=state.get_vision_model(),
            # num_predict 放寬：thinking 類模型需額外 token 才能在推理後吐出格式輸出。
            options={"num_predict": 512, "temperature": 0.1},
            # 用完即退 VRAM，避免與後續 compile() 的文字模型同時駐留
            keep_alive=0,
        )
        # 診斷用：印出模型原始回應（含 think 段）→ 判斷回空主因（think 燒光/不照格式/真空回）
        logger.info("[combined-vision] RAW(len=%d): %r", len(result or ""), (result or "")[:300])
        # thinking 類模型（如 Qwen3-VL abliterated）即使送 think:false，response 仍可能
        # 內嵌 <think>…</think>。先去除再解析，避免推理段落污染或排擠格式輸出。
        cleaned = re.sub(r"<think>.*?</think>", "", result or "", flags=re.DOTALL | re.IGNORECASE).strip()

        coverage = ""
        visual = ""
        for line in cleaned.split('\n'):
            line = line.strip()
            if line.upper().startswith('COVERAGE:'):
                parts = line.split(':', 1)
                cov_word = parts[1].strip().lower().split()[0] if len(parts) > 1 and parts[1].strip() else ""
                if cov_word in ("full", "partial", "bust"):
                    coverage = cov_word
                elif any(k in cov_word for k in ("full", "whole", "entire", "feet", "leg")):
                    coverage = "full"
                elif any(k in cov_word for k in ("bust", "face", "head", "shoulder")):
                    coverage = "bust"
            elif line.upper().startswith('FEATURES:'):
                parts = line.split(':', 1)
                visual = parts[1].strip() if len(parts) > 1 else ""

        # Fallback 1：模型沒照 COVERAGE: 格式 → 在全文掃關鍵詞推斷
        if not coverage:
            low = cleaned.lower()
            if any(k in low for k in ("full body", "full-body", "feet", "ankle", "全身", "腳踝")):
                coverage = "full"
            elif any(k in low for k in ("bust", "headshot", "shoulder", "半身", "胸像", "肩")):
                coverage = "bust"
            elif any(k in low for k in ("partial", "thigh", "knee", "大腿", "膝")):
                coverage = "partial"

        # Fallback 2：沒抓到 FEATURES: 但有可用文字 → 取非 coverage 行當特徵
        if not visual and cleaned:
            desc = "\n".join(
                ln.strip() for ln in cleaned.split('\n')
                if ln.strip() and not ln.strip().upper().startswith('COVERAGE:')
            ).strip()
            visual = desc[:120]

        # 防呆：仍判不出 coverage（模型回空/格式不符）→ 預設 full 跳過外擴，
        # 避免視覺模型異常時 silent 觸發 40GB Flux 外擴拖垮速度（Resilient errors）。
        if not coverage:
            logger.warning("[combined-vision] 無法解析 coverage（模型回空或格式不符）→ 預設 full 跳過外擴")
            coverage = "full"

        logger.info("[combined-vision] coverage=%s visual_len=%d", coverage, len(visual))
        return coverage, visual
    except Exception as e:
        logger.warning("[combined-vision] failed: %s — 預設 full/empty（跳過外擴）", e)
        return "full", ""


def _age_gender_tag(gender: str | None, age: int | None) -> str:
    """Return the primary SD subject tag(s) based on gender + age [FD-090]"""
    if gender == "female":
        base = "1girl" if (age is None or age < 25) else "1woman"
        suffix = ", mature female" if age is not None and age >= 40 else ""
        return base + suffix
    if gender == "male":
        base = "1boy" if (age is None or age < 25) else "1man"
        suffix = ", mature male" if age is not None and age >= 40 else ""
        return base + suffix
    if gender == "neutral":
        return "androgynous"
    return ""


def _age_body_tags(age: int | None) -> str:
    """角色年齡 → SD 比例 tag。≤12 只給單一 `child`（多 tag 會壓成 chibi 比例）；
    15–17 不給 tag（體型交給 _height_body_tags）。"""
    if age is None:
        return ""
    if age <= 6:
        return "toddler, very young, chubby cheeks, round face"
    if age <= 12:
        return "child"
    if age <= 14:
        return "young girl, youthful, flat chest"
    if age <= 17:
        return ""
    return ""


def _height_body_tags(height: int | None) -> str:
    """Convert character height (cm) to SD stature tags."""
    if height is None:
        return ""
    if height < 130:
        return "very short stature, tiny, small figure"
    if height < 150:
        return "short stature, petite"
    if height < 160:
        return "petite"
    if height < 170:
        return ""
    if height < 180:
        return "tall, long legs"
    return "very tall, long legs"


_CLOTHING_KW = {
    "外套", "大衣", "風衣", "夾克", "上衣", "衫", "褲", "短褲", "長褲",
    "裙", "短裙", "長裙", "服裝", "衣服", "制服", "連帽", "背心",
    "毛衣", "套裝", "腰帶", "圍巾", "手套", "鞋", "靴",
    "襪", "護膝", "綁帶",
}
_HAIRSTYLE_KW = {
    "馬尾", "雙馬尾", "辮子", "捲髮", "直髮", "髮型", "長髮",
}
# [CN-103][CN-116] 線稿膚色洩漏詞族一律剝除；不含「線條」（會誤殺服裝線條裝飾）
_SKINTONE_LEAK_KW = {
    "膚色", "膚", "未上色", "未填色", "無色", "線稿",
    "tan skin", "skin tone", "uncolored", "colorless", "unpainted",
}
# [CN-116] 表情詞：表情變體（expression 模式）由 _EXPRESSION_MAP 決定，不可被草圖表情蓋掉
_EXPRESSION_KW = {
    "表情", "微笑", "笑", "哭", "怒", "生氣", "驚訝", "害羞", "臉紅", "嘟嘴", "閉眼",
}
_HAIR_PHRASE_KW = ("髮", "馬尾", "辮")
# [CN-116] 顏色詞：「(深淺)＋1～2 個色字＋色」與「深淺＋色字」兩型；刻意要求「色」或深淺前綴，
#          避免誤傷「金屬」「白皙」這類非顏色用法。
_COLOR_NAMES = "粉紅|咖啡|白|黑|灰|紅|藍|綠|黃|紫|粉|棕|褐|金|銀|橙|橘|青|米"
_COLOR_WORD_RE = re.compile(
    rf"(?:深|淺|淡|亮|暗|鮮)?(?:{_COLOR_NAMES}){{1,2}}色"
    rf"|(?:深|淺|淡|亮|暗|鮮)色"
    rf"|(?:深|淺|淡)(?:{_COLOR_NAMES})"
)
_LEADING_JOINER_RE = re.compile(r"^[的之與和及、\s]+")
# 去掉顏色後只剩部位名詞＝沒有資訊，整句丟棄（例：「淡色眼眸」→「眼眸」）
_EMPTY_AFTER_DECOLOR = {
    "眼眸", "眼睛", "雙眼", "眼瞳", "瞳", "瞳孔", "眼",
    "頭髮", "髮", "髮色", "皮膚", "肌膚", "服裝", "衣服", "",
}


def _decolor_phrase(p: str) -> str:
    """移除片語中的顏色詞；只剩部位名詞時回傳空字串。"""
    out = _LEADING_JOINER_RE.sub("", _COLOR_WORD_RE.sub("", p)).strip()
    return "" if out in _EMPTY_AFTER_DECOLOR else out


def _filter_visual_for_llm(
    visual: str, *, strip_clothing: bool, strip_hairstyle: bool, strip_skin: bool = False,
    strip_expression: bool = False, decolor_all: bool = False,
    decolor_clothing: bool = False, decolor_hair: bool = False,
) -> str:
    """送 LLM 前過濾視覺描述，避免與角色設定衝突（[CN-116] 顏色歸欄位、結構歸視覺）。
    decolor_* 只去顏色詞、保留款式／件數／形狀；strip_* 整句剝除。"""
    if not (strip_clothing or strip_hairstyle or strip_skin or strip_expression
            or decolor_all or decolor_clothing or decolor_hair):
        return visual
    phrases = [p.strip() for p in visual.replace(",", "，").split("，") if p.strip()]
    result = []
    for p in phrases:
        is_clothing = any(kw in p for kw in _CLOTHING_KW)
        is_hair = any(kw in p for kw in _HAIR_PHRASE_KW)
        if strip_clothing and is_clothing:
            continue
        if strip_hairstyle and any(kw in p for kw in _HAIRSTYLE_KW):
            continue
        if strip_skin and any(kw in p for kw in _SKINTONE_LEAK_KW):
            continue
        if strip_expression and any(kw in p for kw in _EXPRESSION_KW):
            continue
        if decolor_all or (decolor_clothing and is_clothing) or (decolor_hair and is_hair):
            p = _decolor_phrase(p)
            if not p:
                continue
        result.append(p)
    return "，".join(result)


def _visual_extract_prompt(n: int) -> str:
    """Return a vision prompt tuned for single or multi-image analysis."""
    ignore_bg = (
        "【線稿警告】這可能是未上色的鉛筆稿／線稿，且常帶單色（如粉紅色）背景。"
        "規則一：完全忽略背景顏色——粉紅色或任何單色背景，絕不可當成髮色或服裝顏色。"
        "規則二：若畫面只有線條、沒有實際填色，請直接省略顏色、不要寫出任何顏色詞，也不要寫「線稿未上色」這類字樣，"
        "只描述髮型長度與形狀、逐件服裝的款式、姿勢、表情與明顯特徵。嚴禁臆測顏色。只觀察「角色線條內」的特徵。"
    )
    if n == 1:
        return (
            f"{ignore_bg}\n"
            "請仔細觀察這張角色參考圖，描述以下視覺特徵（僅描述角色本身，無視背景）：\n"
            f"{_FEATURE_ITEMS}\n"
            f"格式：逗號分隔的中文短語，不加標號，不寫句子，控制在{_FEATURE_CHARS_SINGLE}字以內。"
        )
    return (
        f"{ignore_bg}\n"
        f"你收到了 {n} 張同一角色的不同參考圖。"
        "請綜合比較所有圖片，找出在多張圖中一致出現的視覺特徵：\n"
        f"{_FEATURE_ITEMS_MULTI}\n"
        "以共同特徵為主，忽略只在單張圖出現的細節。"
        f"格式：逗號分隔的中文短語，不加標號，不寫句子，控制在{_FEATURE_CHARS_MULTI}字以內。"
    )

# [CN-104] vision 快取以 image hash+模式+模型為 key，持久化至 data/vision_cache.json；錯誤結果不快取
_VISION_CACHE_MAX = 32

# [CN-105] 凡動到 coverage 判定或 vision prompt 就 bump 版本號，否則舊誤判結果被鎖死命中
_VISION_FLOW_VERSION = "v5-2026-09-24"  # 改 coverage／vision 邏輯時遞增，使舊快取失效


def _load_vision_cache() -> dict[str, tuple[str, str]]:
    """Load persisted vision cache from disk; return empty dict on any error."""
    try:
        if _VISION_CACHE_FILE.exists():
            raw = json.loads(_VISION_CACHE_FILE.read_text(encoding="utf-8"))
            # raw: {key: [coverage, visual]}
            cache = {k: (v[0], v[1]) for k, v in raw.items() if isinstance(v, list) and len(v) == 2}
            logger.info("[vision-cache] loaded %d entries from disk", len(cache))
            return cache
    except Exception as e:
        logger.warning("[vision-cache] could not load from disk: %s", e)
    return {}


def _save_vision_cache(cache: dict[str, tuple[str, str]]) -> None:
    """Persist vision cache to disk; silently skip on any error."""
    try:
        _VISION_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _VISION_CACHE_FILE.write_text(
            json.dumps({k: list(v) for k, v in cache.items()}, ensure_ascii=False, indent=None),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("[vision-cache] could not save to disk: %s", e)


_VISION_CACHE: dict[str, tuple[str, str]] = _load_vision_cache()


def _vision_cache_key(images_bytes: list[bytes], mode: str) -> str:
    h = hashlib.sha256()
    for b in images_bytes:
        h.update(len(b).to_bytes(8, "little"))
        h.update(b)
    # 前綴流程版本號：邏輯改版後舊快取自動失效
    return f"{_VISION_FLOW_VERSION}|{mode}|{state.get_vision_model()}|{h.hexdigest()}"


async def _vision_extract_cached(
    valid_images: list[bytes], need_coverage: bool,
) -> tuple[str, str]:
    """Shared vision-extraction step for character / variant design generation [FD-091]"""
    mode = "coverage" if need_coverage else f"plain{len(valid_images)}"
    key = _vision_cache_key(valid_images, mode)
    cached = _VISION_CACHE.get(key)
    if cached is not None:
        logger.info("[vision-cache] hit (%s)", mode)
        return cached

    await guardian.request_focus("ollama")
    if need_coverage:
        coverage, visual = await run_in_threadpool(
            _detect_coverage_and_extract_visual, valid_images
        )
    else:
        coverage = "full"
        visual = await run_in_threadpool(
            _oc.analyze_multi_images_bytes,
            valid_images, _visual_extract_prompt(len(valid_images)),
            model=state.get_vision_model(),
            options={"num_predict": 320, "temperature": 0.1},  # [CN-116] 字數上限放寬，160 會截斷
            # 用完即退 VRAM
            keep_alive=0,
        )

    if visual and not _oc.is_error(visual):
        _VISION_CACHE[key] = (coverage, visual)
        while len(_VISION_CACHE) > _VISION_CACHE_MAX:
            _VISION_CACHE.pop(next(iter(_VISION_CACHE)))
        _save_vision_cache(_VISION_CACHE)
    return coverage, visual
