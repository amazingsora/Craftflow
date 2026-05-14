"""
Character AI services:
  1. extract_from_text  — scan chapter content and suggest character traits
  2. design_chat        — conversational Q&A to help author design a character
  3. describe_portrait  — given an illustration, describe visual appearance
"""
from __future__ import annotations

from app.services.ai import ollama_client


def generate_summary(
    name: str,
    core_traits: str | None = None,
    behavior_rules: str | None = None,
    voice_style: str | None = None,
    notes: str | None = None,
    model: str = ollama_client.DEFAULT_TEXT_MODEL,
) -> str:
    """
    Take raw user-input character fields and produce a structured AI-organized profile summary.
    Output is in Traditional Chinese, formatted for display.
    """
    raw_notes = "\n".join(filter(None, [
        f"外貌/個性：{core_traits}" if core_traits else None,
        f"行為模式：{behavior_rules}" if behavior_rules else None,
        f"說話風格：{voice_style}" if voice_style else None,
        f"補充筆記：{notes}" if notes else None,
    ])) or "（無補充資料）"

    prompt = f"""你是一位專業的角色設定整理師，正在為小說角色「{name}」建立角色檔案。

以下是作者提供的原始筆記：
{raw_notes}

請將上述資料整理成一份結構清晰的角色設定檔，使用繁體中文，格式如下：

## 角色概述
（一段話總結這個角色的核心定位與魅力，50字以內）

## 外貌與氣質
（外貌特徵、穿著風格、整體氣質）

## 性格特質
（核心個性、優點、缺點或矛盾面）

## 行為模式
（面對事情的反應方式、習慣、癖好）

## 說話方式
（語氣、常用詞彙、說話特色）

## 創作備注
（對作者有用的額外提示、潛在故事線等）

請只輸出格式化內容，不要加入任何前言或說明。"""

    return ollama_client.generate(
        prompt, model=model,
        options={"num_predict": 600, "temperature": 0.7},
    )


def extract_from_text(
    chapter_text: str,
    character_name: str,
    model: str = ollama_client.DEFAULT_TEXT_MODEL,
) -> dict:
    """
    Analyse chapter text and extract/suggest character profile fields.
    Returns a dict with keys matching the Character model fields.
    """
    prompt = f"""You are a character profile assistant for a novel.

Analyse the following chapter text and extract information about the character "{character_name}".

Return a JSON object with these fields:
{{
  "core_traits": "personality traits observed (string, or null)",
  "behavior_rules": "how this character tends to act / react (string, or null)",
  "voice_style": "how this character speaks / their dialogue style (string, or null)",
  "notes": "other notable observations (string, or null)",
  "aliases": ["any alternative names or nicknames mentioned"]
}}

Return ONLY the JSON object, nothing else.

Chapter text:
{chapter_text}"""

    raw = ollama_client.generate(prompt, model=model)
    return _parse_json_object(raw) or {}


def design_chat(
    question: str,
    character_name: str,
    existing_profile: dict | None = None,
    model: str = ollama_client.DEFAULT_TEXT_MODEL,
) -> str:
    """
    Answer a single design question about a character.
    existing_profile is the current Character fields as a dict (optional context).
    """
    profile_ctx = ""
    if existing_profile:
        parts = [f"  {k}: {v}" for k, v in existing_profile.items() if v]
        if parts:
            profile_ctx = "Current profile:\n" + "\n".join(parts) + "\n\n"

    prompt = f"""You are a creative writing assistant helping design a character for a novel.
Character name: {character_name}
{profile_ctx}Author's question: {question}

Provide a helpful, specific, and creative answer in Traditional Chinese (繁體中文).
Focus on the character design question. Keep it concise."""

    return ollama_client.generate(prompt, model=model)


def describe_portrait(
    image_path: str,
    character_name: str,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> str:
    """
    Given an illustration/portrait, describe the character's visual appearance
    to be used as reference for the character profile.
    """
    prompt = f"""你正在為小說角色「{character_name}」建立視覺設定檔。
請仔細分析這張插畫，用繁體中文描述：

1. **外貌特徵**：髮色、髮型、眼睛顏色、膚色、臉型
2. **體型與身形**：高矮、體型、姿態
3. **服裝與配件**：衣著風格、顏色、特殊配件
4. **視覺氛圍**：整體氣質、給人的第一印象

請以結構化方式呈現，方便作者參考與後續創作使用。"""

    return ollama_client.analyze_image(image_path, prompt, model=model)


def describe_portrait_bytes(
    image_bytes: bytes,
    character_name: str,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> str:
    prompt = f"""你正在為小說角色「{character_name}」建立視覺設定檔。
請仔細分析這張插畫，用繁體中文描述：

1. **外貌特徵**：髮色、髮型、眼睛顏色、膚色、臉型
2. **體型與身形**：高矮、體型、姿態
3. **服裝與配件**：衣著風格、顏色、特殊配件
4. **視覺氛圍**：整體氣質、給人的第一印象

請以結構化方式呈現，方便作者參考與後續創作使用。"""

    return ollama_client.analyze_image_bytes(image_bytes, prompt, model=model)


import json
import re


def _parse_json_object(raw: str) -> dict | None:
    if not raw:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", cleaned)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None
