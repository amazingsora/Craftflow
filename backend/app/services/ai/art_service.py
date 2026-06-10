"""
Art AI services — all powered by Ollama vision model.

Modes:
  sketch_critique   — draft image → written improvement suggestions
  finished_critique — finished illustration → detailed critique
  line_color        — lineart → colour scheme suggestions
  composition_ask   — freeform Q&A about composition / action / framing
  describe          — general image description (for illustration metadata)
"""
from __future__ import annotations

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


def analyze_composition_bytes(
    image_bytes: bytes,
    user_question: str | None = None,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> tuple[str, str]:
    """
    上傳草稿並提出構圖問題，由 Vision 模型給出具體建議，並提煉出精準對齊草稿的 SDXL Prompt。
    user_question 為 None 時，AI 自動分析構圖（不需使用者輸入問題）。
    """
    if user_question:
        prompt = load_prompt("art/composition_analysis", user_question=user_question)
    else:
        prompt = load_prompt("art/composition_analysis_auto")

    raw = ollama_client.analyze_image_bytes(
        image_bytes, prompt, model=model,
        options={"num_predict": 450, "temperature": 0.2},  # 降低溫度以確保精準度與穩定度
    )

    # 移除原本錯誤的 raw.startswith("[") 判定，直接進行切分
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

    return advice, sdxl_prompt


def describe_illustration(
    image_path: str,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> str:
    prompt = load_prompt("art/describe_illustration")
    return ollama_client.analyze_image(image_path, prompt, model=model)


def describe_illustration_bytes(
    image_bytes: bytes,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> str:
    prompt = load_prompt("art/describe_illustration")
    return ollama_client.analyze_image_bytes(image_bytes, prompt, model=model)

# ==========================================
# 舊接口相容轉接層 (Backward Compatibility)
# ==========================================

@dataclass
class ArtAnalysisResult:
    mode: str
    content: str
    warnings: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return bool(self.content) and not self.content.startswith("[")


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
