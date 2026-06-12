"""Vision 抽取與角色 SD 標籤工具。

自 api/art_generate.py 下沉（2026-06-11 A1 階段 1）：
身體 coverage 偵測、視覺特徵抽取（含合併單次呼叫版）、vision 結果快取、
角色屬性（性別/年齡/身高）→ SD 標籤、服裝/髮型詞過濾。
"""
from __future__ import annotations

import hashlib
import logging

from starlette.concurrency import run_in_threadpool

from app.core import state
from app.services.ai import ollama_client as _oc
from app.services.ai.vram_manager import guardian

logger = logging.getLogger(__name__)


def _detect_body_coverage(image_bytes: bytes) -> str:
    """
    Use the configured vision model to classify how much of the body is shown.
    Returns: "full" | "partial" | "bust"
    - full:    legs and feet visible
    - partial: torso visible but legs cut off (upper body / three-quarter)
    - bust:    face / shoulders only
    Falls back to "partial" on any error.
    """
    prompt = (
        "Look at this character illustration. How much of the body is shown?\n"
        "Reply with exactly one word:\n"
        "- 'full' if ankles AND feet are clearly visible (complete full body)\n"
        "- 'partial' if knees or ankles are cut off (thighs visible but no feet = partial)\n"
        "- 'bust' if only waist-up or less is shown\n"
        "One word only."
    )
    try:
        result = _oc.analyze_image_bytes(image_bytes, prompt, model=state.get_vision_model())
        result = result.strip().lower().split()[0] if result.strip() else ""
        if result in ("full", "partial", "bust"):
            return result
        # fuzzy match
        if any(k in result for k in ("full", "whole", "entire", "feet", "leg")):
            return "full"
        if any(k in result for k in ("bust", "face", "head", "shoulder")):
            return "bust"
        return "partial"
    except Exception as e:
        logger.warning("[body-coverage] detection failed: %s — defaulting to partial", e)
        return "partial"


def _detect_coverage_and_extract_visual(images_bytes: list[bytes]) -> tuple[str, str]:
    """
    Single Ollama call that combines body-coverage classification and visual feature extraction.
    Returns (coverage: "full"|"partial"|"bust", visual_description: str).
    Saves one full vision-model round-trip vs calling _detect_body_coverage + analyze_multi_images_bytes separately.
    """
    ignore_bg = (
        "【重要警告】這是一張草稿或帶有單色背景的參考圖。請完全忽略背景顏色。"
        "背景不屬於角色特徵。請只觀察「角色線條內」的特徵。"
    )
    n = len(images_bytes)
    if n == 1:
        feature_q = (
            "B. 視覺特徵（逗號分隔的中文短語，控制在70字以內）：\n"
            "① 髮色與髮型 ② 眼睛顏色 ③ 膚色 ④ 體型輪廓 ⑤ 服裝主要顏色與風格 ⑥ 明顯特殊特徵"
        )
    else:
        feature_q = (
            f"B. {n}張圖共同視覺特徵（逗號分隔的中文短語，控制在90字以內）：\n"
            "① 髮色與髮型 ② 眼睛顏色 ③ 膚色 ④ 體型輪廓 ⑤ 服裝主要顏色與風格 ⑥ 各圖均出現的特殊特徵"
        )
    prompt = (
        f"{ignore_bg}\n\n"
        "請回答以下兩個問題：\n\n"
        "A. 身體遮蔽程度（只回答一個英文詞）：\n"
        "- 'full'    腳踝和腳都清晰可見（完整全身）\n"
        "- 'partial' 膝蓋或腳踝以下被切掉（大腿可見但無腳也算partial）\n"
        "- 'bust'    只有腰部以上可見\n\n"
        f"{feature_q}\n\n"
        "回答格式（嚴格遵守）：\n"
        "COVERAGE: [一個英文詞]\n"
        "FEATURES: [逗號分隔的中文短語]"
    )
    try:
        result = _oc.analyze_multi_images_bytes(
            images_bytes, prompt,
            model=state.get_vision_model(),
            options={"num_predict": 240, "temperature": 0.1},
        )
        coverage = "partial"
        visual = ""
        for line in result.split('\n'):
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
        logger.info("[combined-vision] coverage=%s visual_len=%d", coverage, len(visual))
        return coverage, visual
    except Exception as e:
        logger.warning("[combined-vision] failed: %s — defaulting to partial/empty", e)
        return "partial", ""


def _age_gender_tag(gender: str | None, age: int | None) -> str:
    """
    Return the primary SD subject tag(s) based on gender + age.
    Placed at the very front of the positive prompt to anchor subject count.
    Returns empty string when gender is unset.
    """
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
    """Convert character age to SD body proportion tags."""
    if age is None:
        return ""
    if age <= 6:
        return "toddler, very young, chubby cheeks, round face"
    if age <= 12:
        return "child, young girl, youthful, childlike features, round face, flat chest, small hands"
    if age <= 14:
        return "young girl, youthful, flat chest"
    if age <= 17:
        return "teenage girl, youthful"
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
}
_HAIRSTYLE_KW = {
    "馬尾", "雙馬尾", "辮子", "捲髮", "直髮", "髮型", "長髮",
}


def _filter_visual_for_llm(visual: str, *, strip_clothing: bool, strip_hairstyle: bool) -> str:
    """
    Remove clothing / hairstyle phrases from a comma-separated vision description
    before sending it to the LLM, so it cannot hallucinate outfits or hairstyles
    that conflict with explicitly defined character settings.
    """
    if not (strip_clothing or strip_hairstyle):
        return visual
    phrases = [p.strip() for p in visual.replace(",", "，").split("，") if p.strip()]
    result = []
    for p in phrases:
        drop = False
        if strip_clothing and any(kw in p for kw in _CLOTHING_KW):
            drop = True
        if not drop and strip_hairstyle and any(kw in p for kw in _HAIRSTYLE_KW):
            drop = True
        if not drop:
            result.append(p)
    return "，".join(result)


def _visual_extract_prompt(n: int) -> str:
    """Return a vision prompt tuned for single or multi-image analysis."""
    ignore_bg = (
        "【重要警告】這是一張草稿或帶有單色背景的參考圖。請完全忽略背景顏色（例如：如果背景是純粉色，請勿將其判定為衣服或髮色）。"
        "背景不屬於角色特徵。請只觀察「角色線條內」的特徵。"
    )
    if n == 1:
        return (
            f"{ignore_bg}\n"
            "請仔細觀察這張角色參考圖，描述以下視覺特徵：\n"
            "① 髮色與髮型（顏色、長度、形狀，請根據角色本身的髮色判斷）"
            "② 眼睛顏色"
            "③ 膚色"
            "④ 體型輪廓（高挑/嬌小、胖瘦）"
            "⑤ 服裝主要顏色與風格（僅描述角色穿著的部分，無視背景）"
            "⑥ 明顯特殊特徵（獸耳、印記、武器等）\n"
            "格式：逗號分隔的中文短語，不加標號，不寫句子，控制在70字以內。"
        )
    return (
        f"{ignore_bg}\n"
        f"你收到了 {n} 張同一角色的不同參考圖。"
        "請綜合比較所有圖片，找出在多張圖中一致出現的視覺特徵：\n"
        "① 髮色與髮型"
        "② 眼睛顏色"
        "③ 膚色"
        "④ 體型輪廓"
        "⑤ 服裝主要顏色與風格"
        "⑥ 各圖均出現的特殊特徵\n"
        "以共同特徵為主，忽略只在單張圖出現的細節。"
        "格式：逗號分隔的中文短語，不加標號，不寫句子，控制在90字以內。"
    )

# ── Vision extraction cache ──────────────────────────────────────────────────
# concept images 不變 → vision 抽取結果不變。以 image bytes hash + 模式 + 模型為
# key 快取，重複生成同角色時跳過最貴的 Ollama vision 呼叫（5~20s）。
# 錯誤結果（"[...]" 開頭）不快取。dict 依插入序淘汰最舊項目。
_VISION_CACHE: dict[str, tuple[str, str]] = {}
_VISION_CACHE_MAX = 32


def _vision_cache_key(images_bytes: list[bytes], mode: str) -> str:
    h = hashlib.sha256()
    for b in images_bytes:
        h.update(len(b).to_bytes(8, "little"))
        h.update(b)
    return f"{mode}|{state.get_vision_model()}|{h.hexdigest()}"


async def _vision_extract_cached(
    valid_images: list[bytes], need_coverage: bool,
) -> tuple[str, str]:
    """
    Shared vision-extraction step for character / variant design generation.
    Returns (coverage, visual); coverage is "full" placeholder when
    need_coverage=False.  Cache hit skips the Ollama call entirely
    (including request_focus, so ComfyUI stays warm).
    """
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
            options={"num_predict": 160, "temperature": 0.1},
        )

    if visual and not visual.startswith("["):
        _VISION_CACHE[key] = (coverage, visual)
        while len(_VISION_CACHE) > _VISION_CACHE_MAX:
            _VISION_CACHE.pop(next(iter(_VISION_CACHE)))
    return coverage, visual
