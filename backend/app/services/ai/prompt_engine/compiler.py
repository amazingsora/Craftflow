"""
Prompt Compiler — 中文描述 → 對應模型的最終 prompt

流程：
  1. 依 style 選擇 LLM template
  2. Ollama 翻譯生成 raw tags / 描述
  3. Sanitizer：移除 banned_tags
  4. Anchor Extraction：從原始中文抽取髮色/眼色/長度
  5. Semantic Cleaning：移除與 Anchor 衝突的標籤
  6. Reordering & Weighting：按類別排序標籤，並對 Anchor 加權
  7. 拼接 quality_prefix
  8. 回傳 (positive_prompt, negative_prompt)
"""
from __future__ import annotations

import re
from typing import List, Set

from app.services.ai import ollama_client
from app.services.ai.prompt_engine.styles import PromptStyle, STYLE_CONFIG
from app.services.ai.prompt_engine import lexicon


def _extract_color_anchors(text: str, anchor_source: str = "") -> list[str]:
    """
    Deterministically extract hair/eye traits from Chinese text.
    Returns English SD tags like ["white hair", "short hair", "golden eyes"].
    """
    def _scan(src: str) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for m in lexicon.HAIR_RE.finditer(src):
            prefix_zh = m.group(1)
            color_zh = m.group(2)
            style_zh = m.group(3)
            
            # Extract color if present
            if color_zh:
                color_en = lexicon.COLOR_MAP.get(color_zh, color_zh)
                tag = f"{color_en} hair"
                if tag not in seen:
                    seen.add(tag); result.append(tag)
            
            # Extract length/style from either prefix or keyword
            combined_style = (prefix_zh or "") + style_zh
            if "短" in combined_style:
                tag = "short hair"
                if tag not in seen:
                    seen.add(tag); result.append(tag)
            elif "長" in combined_style:
                tag = "long hair"
                if tag not in seen:
                    seen.add(tag); result.append(tag)
                    
        for m in lexicon.EYE_RE.finditer(src):
            color_zh = m.group(1)
            color_en = lexicon.COLOR_MAP.get(color_zh, color_zh)
            tag = f"{color_en} eyes"
            if tag not in seen:
                seen.add(tag); result.append(tag)
        return result

    if anchor_source:
        anchors = _scan(anchor_source)
        if anchors:
            return anchors
    return _scan(text)


def _remove_conflicting_tags(tags: list[str], anchors: list[str]) -> list[str]:
    """Remove LLM-generated tags that conflict with our authoritative anchors."""
    has_hair_color = any(a in lexicon.HAIR_COLORS for a in anchors)
    has_hair_length = any(a in lexicon.HAIR_LENGTHS for a in anchors)
    has_eye_color  = any(a in lexicon.EYE_COLORS for a in anchors)
    
    if not has_hair_color and not has_hair_length and not has_eye_color:
        return tags

    result = []
    anchor_set = set(anchors)
    for t in tags:
        tl = t.lower()
        # Conflict if our anchors have hair color and LLM outputs a different hair color
        if has_hair_color and tl in lexicon.HAIR_COLORS and tl not in anchor_set:
            continue
        # Conflict if our anchors have hair length and LLM outputs a different hair length
        if has_hair_length and tl in lexicon.HAIR_LENGTHS and tl not in anchor_set:
            continue
        # Conflict if our anchors have eye color and LLM outputs a different eye color
        if has_eye_color and tl in lexicon.EYE_COLORS and tl not in anchor_set:
            continue
        result.append(t)
    return result


def _reorder_tags(tags: list[str], anchors: list[str]) -> str:
    """
    Sort tags into logical categories and apply weighting to anchors.
    Order: Subject > Anchors > Others > Meta
    """
    subject_tags = []
    anchor_tags = []
    meta_tags = []
    other_tags = []

    # Weighted anchors (e.g. (short hair:1.1))
    weighted_anchors = [f"({a}:1.1)" for a in anchors]
    anchor_set = set(anchors)

    for t in tags:
        tl = t.lower()
        if tl in anchor_set:
            continue  # Already handled by weighted_anchors
        
        if tl in lexicon.TAG_CATEGORIES["subject"]:
            subject_tags.append(t)
        elif tl in lexicon.TAG_CATEGORIES["meta"]:
            meta_tags.append(t)
        else:
            other_tags.append(t)

    # Combine in specific order
    final_list = subject_tags + weighted_anchors + other_tags + meta_tags
    return ", ".join(final_list)


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
    cleaned_tags = _sanitize_to_list(extracted, config.banned_tags)

    # 3.5 Processing (tag-based styles only; Flux uses natural language)
    if style is not PromptStyle.FLUX:
        # Extract authoritative anchors
        anchors = _extract_color_anchors(text, anchor_source=anchor_text)
        
        # Clean conflicts
        cleaned_tags = _remove_conflicting_tags(cleaned_tags, anchors)
        
        # Reorder and weight
        final_body = _reorder_tags(cleaned_tags, anchors)
    else:
        final_body = extracted

    # 4. 拼接 quality_prefix（art_style 覆寫優先）
    prefix = quality_prefix_override if quality_prefix_override else config.quality_prefix
    positive = f"{prefix}, {final_body}" if prefix and final_body else (prefix or final_body)

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


def _sanitize_to_list(prompt: str, banned: set[str]) -> list[str]:
    """Remove banned tags and return a list of tags."""
    tags = [t.strip() for t in prompt.split(",")]
    if not banned:
        return [t for t in tags if t]
    return [t for t in tags if t and t.lower() not in banned]
