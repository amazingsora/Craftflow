"""Art AI services — all powered by Ollama vision model [FD-031]"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.services.ai import ollama_client
from app.services.ai.prompt_loader import load_prompt


def analyze_sketch_bytes(
    image_bytes: bytes,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> str:
    return ollama_client.analyze_image_bytes(image_bytes, load_prompt("art/sketch_critique"), model=model)


def analyze_finished_bytes(
    image_bytes: bytes,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> str:
    return ollama_client.analyze_image_bytes(image_bytes, load_prompt("art/finished_critique"), model=model)


def suggest_lineart_colors_bytes(
    image_bytes: bytes,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> str:
    return ollama_client.analyze_image_bytes(image_bytes, load_prompt("art/line_color"), model=model)


# [CN-126] LLM tag 輸出清理規則；Danbooru 真實存在的 no_* tag 保留
_HEDGE_PREFIXES = ("without ", "not ", "slightly ", "somewhat ", "possibly ", "maybe ", "probably ")
_DANBOORU_NO_TAGS = frozenset({"no humans", "no pupils", "no nose", "no mouth", "no shoes",
                               "no headwear", "no eyes", "no sclera"})
_MAX_TAG_WORDS = 4


def sanitize_tags(text: str, drop_negations: bool = True) -> str:
    """清理逗號分隔 tag：去空、去重（保留首次順序）；drop_negations 再去否定／二選一／長句 [FD-121]"""
    seen: set[str] = set()
    out: list[str] = []
    for raw in re.split(r"[,\n]", text or ""):
        tag = re.sub(r"\s+", " ", raw.strip().strip(".").strip())
        if not tag:
            continue
        low = tag.lower()
        if drop_negations and _is_unfit_tag(low):
            continue
        if low in seen:
            continue
        seen.add(low)
        out.append(tag)
    return ", ".join(out)


def _is_unfit_tag(low: str) -> bool:
    if low.startswith("no ") and low not in _DANBOORU_NO_TAGS:
        return True
    if low.startswith(_HEDGE_PREFIXES) or " or " in f" {low} ":
        return True
    return len(low.split()) > _MAX_TAG_WORDS


def analyze_composition_bytes(
    image_bytes: bytes,
    user_question: str | None = None,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> tuple[str, str]:
    """上傳草稿並提問構圖，Vision 模型給建議並產出對齊草稿的 SDXL prompt [FD-032]"""
    if user_question:
        prompt = load_prompt("art/composition_analysis", user_question=user_question)
    else:
        prompt = load_prompt("art/composition_analysis_auto")

    raw = ollama_client.analyze_image_bytes(
        image_bytes, prompt, model=model,
        options={"num_predict": 450, "temperature": 0.2},  # 降低溫度以確保精準度與穩定度
    )

    advice = raw.strip()

    # 預設更加中性且安全的 Prompt，防止拉扯 ControlNet
    sdxl_prompt = "1girl, anime style, character design, clear lines, smile, simple background, white background"

    if "[ADVICE]" in raw or "[PROMPT]" in raw:
        try:
            parts = raw.split("[PROMPT]")
            advice = parts[0].replace("[ADVICE]", "").strip()
            if len(parts) > 1:
                candidate = parts[1].strip()
                if candidate:
                    sdxl_prompt = candidate
        except Exception:
            if "PROMPT:" in raw:
                parts = raw.split("PROMPT:", 1)
                advice = parts[0].replace("ADVICE:", "").strip()
                sdxl_prompt = parts[1].strip()

    return advice, sanitize_tags(sdxl_prompt)


def describe_illustration(
    image_path: str,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> str:
    prompt = load_prompt("art/describe_illustration")
    return ollama_client.analyze_image(image_path, prompt, model=model)


# 舊接口相容轉接層 (Backward Compatibility)

@dataclass
class ArtAnalysisResult:
    mode: str
    content: str
    warnings: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return bool(self.content) and not ollama_client.is_error(self.content)


def critique_sketch(image_path: str, model: str = ollama_client.DEFAULT_VISION_MODEL) -> ArtAnalysisResult:
    content = analyze_sketch_bytes(Path(image_path).read_bytes(), model=model)
    return ArtAnalysisResult(mode="sketch_critique", content=content)


def critique_finished(image_path: str, model: str = ollama_client.DEFAULT_VISION_MODEL) -> ArtAnalysisResult:
    content = analyze_finished_bytes(Path(image_path).read_bytes(), model=model)
    return ArtAnalysisResult(mode="finished_critique", content=content)


def advise_color(image_path: str, model: str = ollama_client.DEFAULT_VISION_MODEL) -> ArtAnalysisResult:
    content = suggest_lineart_colors_bytes(Path(image_path).read_bytes(), model=model)
    return ArtAnalysisResult(mode="line_color", content=content)


def composition_ask(
    question: str,
    image_path: str | None = None,
    image_bytes: bytes | None = None,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> str:
    prompt = load_prompt("art/composition_advisor", question=question)
    if image_path:
        return ollama_client.analyze_image(image_path, prompt, model=model)
    if image_bytes:
        return ollama_client.analyze_image_bytes(image_bytes, prompt, model=model)
    return ollama_client.generate(prompt, model=model)


def compose_ask(
    user_question: str | None,
    image_bytes: bytes,
    model: str = ollama_client.DEFAULT_VISION_MODEL
) -> tuple[str, str]:
    return analyze_composition_bytes(
        image_bytes=image_bytes,
        user_question=user_question or None,
        model=model
    )
