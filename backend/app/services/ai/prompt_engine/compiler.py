"""
Prompt Compiler — 中文描述 → 對應模型的最終 prompt

流程：
  1. 依 style 選擇 LLM template
  2. Ollama 翻譯生成 raw tags / 描述
  3. Sanitizer：移除 banned_tags
  3.5 Color anchor：從原始中文抽取髮色/眼色，覆蓋 LLM 的翻譯結果，注入最前端
  4. 拼接 quality_prefix
  5. 回傳 (positive_prompt, negative_prompt)
"""
from __future__ import annotations

import re

from app.services.ai import ollama_client
from app.services.ai.prompt_engine.styles import PromptStyle, STYLE_CONFIG


# ── Color anchor tables ────────────────────────────────────────────────────────
# Longer keys first so regex greedily matches "金黃色" before "金色" before "金"

_COLOR_MAP: dict[str, str] = {
    "白色": "white",   "白": "white",
    "金黃色": "blonde", "金黃": "blonde",
    "金色": "golden",  "金": "golden",
    "銀色": "silver",  "銀": "silver",
    "黑色": "black",   "黑": "black",
    "棕色": "brown",   "棕": "brown",   "茶色": "brown",   "褐色": "brown", "褐": "brown",
    "紅色": "red",     "紅": "red",
    "藍色": "blue",    "藍": "blue",
    "紫色": "purple",  "紫": "purple",
    "粉紅色": "pink",  "粉紅": "pink",  "粉色": "pink", "粉": "pink",
    "綠色": "green",   "綠": "green",
    "橘色": "orange",  "橘": "orange",
    "灰色": "grey",    "灰": "grey",
    "琥珀色": "amber", "琥珀": "amber",
}

_COLOR_ALTS = "|".join(re.escape(k) for k in sorted(_COLOR_MAP, key=len, reverse=True))

# 髮 covers: 頭髮 長髮 短髮 捲髮 直髮 金髮 銀髮 etc.
_HAIR_RE = re.compile(rf"({_COLOR_ALTS})?(長髮|短髮|捲髮|直髮|頭髮|髮|毛髮)")
_EYE_RE  = re.compile(rf"({_COLOR_ALTS})(眼睛|瞳孔|眼|瞳)")

# All English hair/eye color tags that LLM might output (used for conflict removal)
_HAIR_EN = {
    "white hair", "black hair", "brown hair", "blonde hair", "golden hair",
    "silver hair", "red hair", "blue hair", "purple hair", "pink hair",
    "green hair", "orange hair", "grey hair", "gray hair", "amber hair",
    "short hair", "long hair", "medium hair",
}
_EYE_EN = {
    "white eyes", "black eyes", "brown eyes", "golden eyes", "silver eyes",
    "red eyes", "blue eyes", "purple eyes", "pink eyes", "green eyes",
    "orange eyes", "grey eyes", "gray eyes", "amber eyes",
}


def _extract_color_anchors(text: str, anchor_source: str = "") -> list[str]:
    """
    Deterministically extract hair/eye traits from Chinese text.
    Returns English SD tags like ["white hair", "short hair", "golden eyes"].
    """
    def _scan(src: str) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for m in _HAIR_RE.finditer(src):
            color_zh = m.group(1)
            style_zh = m.group(2)
            
            # Extract color if present
            if color_zh:
                color_en = _COLOR_MAP.get(color_zh, color_zh)
                tag = f"{color_en} hair"
                if tag not in seen:
                    seen.add(tag); result.append(tag)
            
            # Extract length/style
            if "短" in style_zh:
                tag = "short hair"
                if tag not in seen:
                    seen.add(tag); result.append(tag)
            elif "長" in style_zh:
                tag = "long hair"
                if tag not in seen:
                    seen.add(tag); result.append(tag)
                    
        for m in _EYE_RE.finditer(src):
            tag = f"{_COLOR_MAP.get(m.group(1), m.group(1))} eyes"
            if tag not in seen:
                seen.add(tag); result.append(tag)
        return result

    if anchor_source:
        anchors = _scan(anchor_source)
        if anchors:
            return anchors
    return _scan(text)


def _remove_conflicting_colors(tags_str: str, anchors: list[str]) -> str:
    """Remove LLM-generated hair/eye color/length tags that conflict with our anchors."""
    has_hair_color = any(" hair" in a and a not in {"short hair", "long hair"} for a in anchors)
    has_hair_length = any(a in {"short hair", "long hair"} for a in anchors)
    has_eye_color  = any(" eyes" in a for a in anchors)
    
    if not has_hair_color and not has_hair_length and not has_eye_color:
        return tags_str

    result = []
    for t in (t.strip() for t in tags_str.split(",")):
        tl = t.lower()
        # Conflict if our anchors have hair color and LLM outputs a different hair color
        if has_hair_color and tl in _HAIR_EN and tl not in {"short hair", "long hair"}:
            continue
        # Conflict if our anchors have hair length and LLM outputs a different hair length
        if has_hair_length and tl in {"short hair", "long hair", "medium hair"}:
            continue
        # Conflict if our anchors have eye color and LLM outputs a different eye color
        if has_eye_color and tl in _EYE_EN:
            continue
        result.append(t)
    return ", ".join(result)


# ── Main compile ───────────────────────────────────────────────────────────────

def compile(
    text: str,
    style: PromptStyle = PromptStyle.SDXL,
    model: str = ollama_client.DEFAULT_TEXT_MODEL,
    anchor_text: str = "",
    quality_prefix_override: str | None = None,
    negative_override: str | None = None,
) -> tuple[str, str]:
    """
    Compile Chinese text into (positive_prompt, negative_prompt) for the given style.

    anchor_text: authoritative Chinese text for color anchor extraction (e.g. core_traits).
                 When set, color anchors are derived from this text rather than the full
                 compiled input, so the author's explicit colors always win over vision-extract.

    quality_prefix_override / negative_override: when non-empty, replace the style preset.
        Pass None (or "") to keep the style's built-in value.

    Returns:
        (positive, negative) — both ready to inject into ComfyUI workflow
    """
    config = STYLE_CONFIG[style]

    # 1. LLM 翻譯
    llm_prompt = config.llm_template.format(prompt=text)
    raw = ollama_client.generate(
        llm_prompt,
        model=model,
        options={
            "temperature": 0.3,
            "num_predict": 250,
            "stop": ["\nInput:", "\n\nInput"],
        },
    )

    # 2. 提取 LLM 實際回答
    extracted = _extract_output(raw)

    # 3. Sanitizer — 移除 banned_tags
    cleaned = _sanitize(extracted, config.banned_tags)

    # 3.5 Color anchors (tag-based styles only; Flux uses natural language)
    if style is not PromptStyle.FLUX:
        anchors = _extract_color_anchors(text, anchor_source=anchor_text)
        if anchors:
            cleaned = _remove_conflicting_colors(cleaned, anchors)
            anchor_str = ", ".join(anchors)
            cleaned = f"{anchor_str}, {cleaned}" if cleaned else anchor_str

    # 4. 拼接 quality_prefix（art_style 覆寫優先）
    prefix = quality_prefix_override if quality_prefix_override else config.quality_prefix
    positive = f"{prefix}, {cleaned}" if prefix and cleaned else (prefix or cleaned)

    # 5. Negative preset（art_style 覆寫優先）
    negative = negative_override if negative_override else config.negative

    return positive.strip(", "), negative


def _extract_output(raw: str) -> str:
    """
    如果 LLM 把 few-shot 範例一起輸出（例如包含 'Output:' 字樣），
    只取最後一個 'Output:' 之後的內容作為真正的答案。
    """
    if "Output:" in raw:
        return raw.split("Output:")[-1].strip()
    return raw.strip()


def _sanitize(prompt: str, banned: set[str]) -> str:
    """Remove banned tags from a comma-separated tag string."""
    if not banned:
        return prompt
    tags = [t.strip() for t in prompt.split(",")]
    filtered = [t for t in tags if t.lower() not in banned]
    return ", ".join(filtered)
