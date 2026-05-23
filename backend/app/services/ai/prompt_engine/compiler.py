"""
Prompt Compiler — 中文描述 → 對應模型的最終 prompt

流程：
  1. 依 style 選擇 LLM template
  2. Ollama 翻譯生成 raw tags / 描述
  3. Sanitizer：移除 banned_tags
  3.6 服飾防幻覺與情緒召回過濾器（草稿強化核心）
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
            
            eng_color = lexicon.COLOR_MAP.get(color_zh)
            eng_style = lexicon.HAIR_STYLE_MAP.get(style_zh) if style_zh else None
            
            if eng_color:
                tag = f"{eng_color} hair"
                if tag not in seen:
                    seen.add(tag)
                    result.append(tag)
            if eng_style:
                if eng_style not in seen:
                    seen.add(eng_style)
                    result.append(eng_style)

        for m in lexicon.EYE_RE.finditer(src):
            color_zh = m.group(1)
            eng_color = lexicon.COLOR_MAP.get(color_zh)
            if eng_color:
                tag = f"{eng_color} eyes"
                if tag not in seen:
                    seen.add(tag)
                    result.append(tag)
        return result

    res = _scan(text)
    if not res and anchor_source:
        res = _scan(anchor_source)
    return res


_COLOR_ALT_RE = re.compile(
    "|".join(re.escape(k) for k in sorted(lexicon.COLOR_MAP, key=len, reverse=True))
)
_HETERO_DETECT_RE = re.compile(r'異色瞳|異色眼')
_LEFT_EYE_RE  = re.compile(rf'左眼(?:為|是|呈)?({_COLOR_ALT_RE.pattern})')
_RIGHT_EYE_RE = re.compile(rf'右眼(?:為|是|呈)?({_COLOR_ALT_RE.pattern})')


def _inject_heterochromia(tags: list[str], text: str, anchor_source: str = "") -> list[str]:
    """
    Detect 異色瞳 in source text and guarantee correct heterochromia tags are present.
    Runs after LLM translation so it's model-agnostic.
    """
    combined = f"{text} {anchor_source}"
    if not _HETERO_DETECT_RE.search(combined):
        return tags

    tag_lowers = {t.lower().strip("() ") for t in tags}
    to_prepend: list[str] = []

    if "heterochromia" not in tag_lowers:
        to_prepend.append("heterochromia")

    for side, side_re in (("left", _LEFT_EYE_RE), ("right", _RIGHT_EYE_RE)):
        m = side_re.search(combined)
        if m:
            eng = lexicon.COLOR_MAP.get(m.group(1))
            if eng:
                tag = f"{eng} eye ({side})"
                if tag not in tag_lowers:
                    to_prepend.append(tag)

    # Remove any single-color eye tag that would conflict (e.g. LLM picked one color)
    if to_prepend:
        eye_color_tags = {f"{c} eyes" for c in lexicon.COLOR_MAP.values()}
        tags = [t for t in tags if t.lower().strip("() ") not in eye_color_tags]

    return to_prepend + tags


def _clean_clothing_hallucinations(tags: list[str], text_to_check: str) -> list[str]:
    """
    防幻覺過濾器：偵測是否有休閒/背心類關鍵字，若是，自動拔除腦補的正式西裝標籤。
    """
    lower_src = text_to_check.lower()
    casual_signals = ["背心", "連帽", "休閒", "vest", "hoodie", "tank top", "casual", "sleeveless"]
    
    if any(sig in lower_src for sig in casual_signals):
        formal_banned = {
            "formal suit", "suit", "jacket", "tie", "necktie", "business suit", 
            "professional attire", "formal background", "formal attire", 
            "formal setting", "office", "tuxedo", "blazer", "suited"
        }
        return [t for t in tags if t.strip().lower().strip("()") not in formal_banned]
    return tags


def compile(
    text: str,
    style: PromptStyle = PromptStyle.SDXL,
    model: str = ollama_client.DEFAULT_TEXT_MODEL,
    anchor_text: str = "",
    quality_prefix_override: str | None = None,
    negative_override: str | None = None,
) -> tuple[str, str]:
    """
    Main entrypoint to compile Chinese creative text into fine-tuned SD prompts.
    """
    config = STYLE_CONFIG[style]

    # 1. 構建 Prompt 並呼叫 LLM
    prompt = config.llm_template.format(prompt=text)
    raw_response = ollama_client.generate(
        prompt,
        model=model,
        options={"num_predict": 250, "temperature": 0.3}
    )
    if raw_response.startswith("["):
        raise RuntimeError(raw_response)

    # 2. 擷取輸出與標籤清洗
    extracted = _extract_output(raw_response)
    cleaned_tags = _sanitize_to_list(extracted, config.banned_tags)

    # 3. 處理防幻覺與特徵修正 (非自然語言的 tag 類模型才執行)
    if style is not PromptStyle.FLUX:
        # 【新增】服飾防幻覺過濾
        combined_text = f"{text} {anchor_text} {extracted}"
        cleaned_tags = _clean_clothing_hallucinations(cleaned_tags, combined_text)
        
        # 【新增】情緒/微笑強制召回機制
        if any(kw in combined_text for kw in ["笑", "微笑", "高興", "smile", "happy"]):
            if "smile" not in [t.lower().strip() for t in cleaned_tags]:
                cleaned_tags.insert(0, "smile")

        # 【新增】異色瞳強制注入（model-agnostic，不依賴 LLM 能否正確翻譯）
        cleaned_tags = _inject_heterochromia(cleaned_tags, text, anchor_source=anchor_text)

        # Extract authoritative anchors
        anchors = _extract_color_anchors(text, anchor_source=anchor_text)
        
        # Clean conflicts
        cleaned_tags = _remove_conflicting_tags(cleaned_tags, anchors)
        
        # Reorder and weight
        final_body = _reorder_tags(cleaned_tags, anchors)
    else:
        final_body = extracted

    # 4. 拼接 quality_prefix
    prefix = quality_prefix_override if quality_prefix_override else config.quality_prefix
    positive = f"{prefix}, {final_body}" if prefix and final_body else (prefix or final_body)

    # 5. Negative preset
    negative = negative_override if negative_override else config.negative

    return positive.strip(", "), negative


def _extract_output(raw: str) -> str:
    if "Output:" in raw:
        return raw.split("Output:")[-1].strip()
    return raw.strip()


def _sanitize_to_list(tag_string: str, banned_set: set[str]) -> list[str]:
    raw_tags = re.split(r'[,\n#]', tag_string)
    cleaned = []
    seen = set()
    for t in raw_tags:
        t_clean = t.strip().strip('."\'')
        if not t_clean:
            continue
        normalized = t_clean.lower().strip("()")
        if normalized in banned_set or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(t_clean)
    return cleaned


def _remove_conflicting_tags(tags: list[str], anchors: list[str]) -> list[str]:
    anchor_colors = set()
    for a in anchors:
        parts = a.split()
        if len(parts) == 2 and parts[1] in ("hair", "eyes"):
            anchor_colors.add((parts[0], parts[1]))

    if not anchor_colors:
        return tags

    filtered = []
    for tag in tags:
        tag_lower = tag.lower()
        conflict = False
        for c_eng, category in anchor_colors:
            if category in tag_lower and c_eng not in tag_lower:
                conflict = True
                break
        if not conflict:
            filtered.append(tag)
    return filtered


def _reorder_tags(tags: list[str], anchors: list[str]) -> str:
    subjects = []
    clothing = []
    meta = []
    others = []

    anchor_set = {a.lower() for a in anchors}
    clothing_keywords = ["suit", "vest", "shirt", "pants", "dress", "skirt", "jacket", "hoodie", "clothes", "attire"]

    for tag in tags:
        tl = tag.lower()
        if tl in anchor_set:
            continue
        if any(kw in tl for kw in ["1girl", "1boy", "solo", "woman", "man", "character"]):
            subjects.append(tag)
        elif any(kw in tl for kw in clothing_keywords):
            clothing.append(tag)
        elif any(kw in tl for kw in ["background", "monochrome", "lineart", "clean lines", "shading"]):
            meta.append(tag)
        else:
            others.append(tag)

    weighted_anchors = [f"({a}:1.1)" for a in anchors]
    final_list = subjects + weighted_anchors + clothing + others + meta
    return ", ".join(final_list)
