"""Character AI services [FD-044]"""
from __future__ import annotations


from app.services.ai import ollama_client
from app.services.ai.llm_json import extract_json
from app.services.ai.prompt_loader import load_prompt


def generate_summary(
    name: str,
    core_traits: str | None = None,
    behavior_rules: str | None = None,
    voice_style: str | None = None,
    notes: str | None = None,
    model: str = ollama_client.DEFAULT_TEXT_MODEL,
) -> str:
    """Take raw user-input character fields and produce a structured AI-organized profile summary [FD-045]"""
    raw_notes = "\n".join(filter(None, [
        f"外貌/個性：{core_traits}" if core_traits else None,
        f"行為模式：{behavior_rules}" if behavior_rules else None,
        f"說話風格：{voice_style}" if voice_style else None,
        f"補充筆記：{notes}" if notes else None,
    ])) or "（無補充資料）"

    prompt = load_prompt("character/generate_summary", name=name, raw_notes=raw_notes)

    return ollama_client.generate(
        prompt, model=model,
        options={"num_predict": 600, "temperature": 0.7},
    )


def extract_from_text(
    chapter_text: str,
    character_name: str,
    model: str = ollama_client.DEFAULT_TEXT_MODEL,
) -> dict:
    """Analyse chapter text and extract/suggest character profile fields [FD-046]"""
    prompt = load_prompt("character/extract_from_text", character_name=character_name, chapter_text=chapter_text)

    raw = ollama_client.generate(prompt, model=model)
    return _parse_json_object(raw) or {}


def design_chat(
    question: str,
    character_name: str,
    existing_profile: dict | None = None,
    model: str = ollama_client.DEFAULT_TEXT_MODEL,
) -> str:
    """Answer a single design question about a character [FD-047]"""
    profile_ctx = ""
    if existing_profile:
        parts = [f"  {k}: {v}" for k, v in existing_profile.items() if v]
        if parts:
            profile_ctx = "Current profile:\n" + "\n".join(parts) + "\n\n"

    prompt = load_prompt("character/design_chat", character_name=character_name, profile_ctx=profile_ctx, question=question)

    return ollama_client.generate(prompt, model=model)


def describe_portrait(
    image_path: str,
    character_name: str,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> str:
    """Given an illustration/portrait, describe the character's visual appearance [FD-048]"""
    prompt = load_prompt("character/describe_portrait", character_name=character_name)

    return ollama_client.analyze_image(image_path, prompt, model=model)


def _parse_json_object(raw: str) -> dict | None:
    return extract_json(raw, dict)
