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

from app.services.ai import ollama_client

_SKETCH_PROMPT = """\
你是一位專業的插畫指導老師，請分析這張草稿並提供詳細的改進意見。

請依以下結構回應（使用繁體中文）：

## 優點
指出草稿中做得好的部分（1-3點）。

## 構圖（Composition）
畫面佈局、重心、視線引導是否合理？有何問題？

## 人體 / 結構（Anatomy & Structure）
比例、透視、空間感的問題。

## 線條品質（Line Quality）
線條流暢度、粗細變化、自信度評估。

## 優先修正建議
列出 3-5 個具體可執行的改進動作，由重要到次要排序。"""

_FINISHED_PROMPT = """\
你是一位專業的插畫評審，請對這張完成圖進行詳細的技術分析。

請依以下結構回應（使用繁體中文）：

## 整體評估
一段話總結這張圖的完成度與整體印象。

## 構圖與設計（Composition）
畫面平衡、主次關係、視覺動線。

## 解剖與結構（Anatomy）
人體比例、透視準確性、空間感。

## 光影（Lighting）
光源一致性、立體感、陰影邏輯。

## 色彩（Color）
配色和諧度、色溫、飽和度控制。

## 細節與完成度
整體完成度、需要加強的細節部分。

## 優先修正建議
列出 3-5 個最值得改進的具體問題，由重要到次要排序。"""

_COLOR_PROMPT = """\
你是一位專業的色彩設計師，請為這張線稿提供配色建議。

請依以下結構回應（使用繁體中文）：

## 主色調建議
推薦 2-3 種主色調方案，說明各方案的視覺氛圍。

## 配色比例
建議主色 / 副色 / 強調色的比例配置。

## 光影色彩
陰影色與高光色的建議（避免直接用黑白）。

## 注意事項
配色時需要特別留意的地方。"""


@dataclass
class ArtAnalysisResult:
    mode: str
    content: str
    warnings: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return bool(self.content) and not self.content.startswith("[")


def critique_sketch(image_path: str, model: str = ollama_client.DEFAULT_VISION_MODEL) -> ArtAnalysisResult:
    return _run("sketch_critique", image_path, _SKETCH_PROMPT, model)


def critique_finished(image_path: str, model: str = ollama_client.DEFAULT_VISION_MODEL) -> ArtAnalysisResult:
    return _run("finished_critique", image_path, _FINISHED_PROMPT, model)


def advise_color(image_path: str, model: str = ollama_client.DEFAULT_VISION_MODEL) -> ArtAnalysisResult:
    return _run("line_color", image_path, _COLOR_PROMPT, model)


def composition_ask(
    question: str,
    image_path: str | None = None,
    image_bytes: bytes | None = None,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> str:
    """
    Freeform art assistant Q&A.
    Can be called with an image (path or bytes) or as pure text.
    """
    prompt = f"""你是一位專業的插畫創作顧問。請用繁體中文回答以下問題：

{question}

請給出具體、實用的建議。"""

    if image_path:
        return ollama_client.analyze_image(image_path, prompt, model=model)
    if image_bytes:
        return ollama_client.analyze_image_bytes(image_bytes, prompt, model=model)
    return ollama_client.generate(prompt, model=model)


def compose_ask(
    question: str,
    image_bytes: bytes,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> tuple[str, str]:
    """
    Analyze a sketch and answer a composition question.
    Returns (advice_zh, sdxl_prompt_en).
    The SDXL prompt is used downstream to generate a reference image via ComfyUI.
    """
    prompt = f"""你是一位專業的插畫構圖顧問，同時熟悉 Stable Diffusion 提示詞寫法。

用戶針對這張草圖提問：「{question}」

請依照以下格式嚴格回應，保持簡潔專業（約 100-200 字）：

ADVICE:
（用繁體中文，針對問題給出 2-3 個具體的構圖或視覺改進點，不要廢話）

PROMPT:
（用英文 tag 描述根據你的建議所改善後的畫面，適合 SDXL 動漫插畫風格，以逗號分隔）"""

    raw = ollama_client.analyze_image_bytes(image_bytes, prompt, model=model)
    print(f"DEBUG: Ollama raw response: {raw}")

    if raw.startswith("["):
        raise RuntimeError(raw)

    advice = raw.strip()
    sdxl_prompt = "1girl, detailed illustration, dynamic composition, high quality, best quality, anime style"

    if "ADVICE:" in raw and "PROMPT:" in raw:
        parts = raw.split("PROMPT:", 1)
        advice = parts[0].replace("ADVICE:", "").strip()
        candidate = parts[1].strip()
        if candidate:
            sdxl_prompt = candidate

    return advice, sdxl_prompt


def describe_illustration(
    image_path: str,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> str:
    prompt = "請用繁體中文簡短描述這張插畫的內容、場景與視覺重點（100字以內）。"
    return ollama_client.analyze_image(image_path, prompt, model=model)


def describe_illustration_bytes(
    image_bytes: bytes,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> str:
    prompt = "請用繁體中文簡短描述這張插畫的內容、場景與視覺重點（100字以內）。"
    return ollama_client.analyze_image_bytes(image_bytes, prompt, model=model)


def _run(mode: str, image_path: str, prompt: str, model: str) -> ArtAnalysisResult:
    content = ollama_client.analyze_image(image_path, prompt, model=model)
    warnings = []
    if content.startswith("["):
        warnings.append(content)
        content = ""
    return ArtAnalysisResult(mode=mode, content=content, warnings=warnings)
