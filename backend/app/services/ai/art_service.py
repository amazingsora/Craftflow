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
你是一位專業的插畫指導老師，請分析這張**草稿**的線條品質。
注意：這是草稿階段，請只聚焦在線條結構問題，不要評論上色或完成度。

請依以下結構回應（使用繁體中文）：

## 整體草稿狀態
一句話描述草稿的整體狀況（例如：結構清晰但線條猶豫、比例大致正確但細節需補強等）。

## 逐部位線條分析
僅列出有問題的部位，沒問題可略過：

- **眼睛 / 五官**：位置比例是否正確？線條是否乾淨有力？有無歪斜？
- **頭髮**：流向是否自然？外輪廓線是否流暢？分組是否清晰？
- **手部 / 手指**：結構是否正確？關節比例？
- **身體 / 姿勢**：重心是否穩定？肩頸腰髖比例？
- **衣物 / 皺褶**：皺褶走向是否符合動作？線條是否過多或過少？
- **輪廓線**：外輪廓是否清晰定義？哪些部位輪廓線需要加強？

## 優先修正清單
列出 3-5 個最重要的修正動作，由重要到次要排序。
每項要具體到部位（例如：「右手食指第二關節偏短，需拉長約 1/3」而非「修正手指」）。

## 值得保留的部分
1-2 點做得好的地方，讓作者知道不需要改。"""

_FINISHED_PROMPT = """\
你是一位專業的插畫評審，請對這張**半完成或完成插畫**進行分析。
注意：聚焦在配色、光影、構圖等完成階段的重點，線稿結構問題請略過。

請依以下結構回應（使用繁體中文）：

## 整體評估
一段話總結這張圖的整體氛圍與完成度印象。

## 配色分析
- 主色調是否統一？冷暖色溫是否協調？
- 配色是否有效傳達畫面氛圍？
- 強調色（accent color）的使用是否到位？
- 建議保留或調整的配色方案。

## 光影分析
- 光源方向是否清晰且一致？
- 陰影是否有效強化立體感？
- 哪些部位（臉部、衣物、背景）的光影表現最需要加強？
- 反光與高光的處理建議。

## 構圖與視覺重心
- 主體是否夠突出？視線是否被有效引導？
- 畫面留白與密度的平衡感如何？
- 前中後景的空間層次是否清晰？

## 優先改進建議
列出 3-5 個最值得改進的具體問題，由重要到次要排序。每項需指出具體部位或區域。"""

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

重要規則：
- 這張草圖可能不完整（只畫了頭、只有上半身等），這是正常的創作過程
- PROMPT 必須描述**補全後的完整畫面**，想像草圖完成後應該是什麼樣子
- PROMPT 絕對不可以描述「草稿」或「不完整」的狀態，要描述理想的完整結果
- 保持草圖中已畫出的角色數量、大致姿勢方向、構圖位置

請依照以下格式嚴格回應：

ADVICE:
（繁體中文，針對「{question}」給出 2-3 個具體建議，不要廢話）

PROMPT:
（英文 tag，描述補全後的完整畫面。必須包含：完整人物描述（頭+身體+四肢+服裝）、姿勢、構圖。以逗號分隔，20 個 tag 以內）"""

    raw = ollama_client.analyze_image_bytes(
        image_bytes, prompt, model=model,
        options={"num_predict": 350, "temperature": 0.4},
    )

    if raw.startswith("["):
        raise RuntimeError(raw)

    advice = raw.strip()
    sdxl_prompt = "1girl, detailed illustration, same pose as reference, same composition, same framing, high quality, best quality, anime style"

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
