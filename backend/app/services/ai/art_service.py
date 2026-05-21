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
- **輪廓線**：外輪廓是否清晰定義？哪些部位輪廓線交叉或斷裂？

## 具體修改建議
請給出 2-3 點具體的修改步驟，指導創作者如何清線或修正人體結構。
"""

_FINISHED_PROMPT = """\
你是一位嚴苛但專業的插畫評審。請對這張**完稿作品**進行全方位的視覺品質審查。

請依以下結構回應（使用繁體中文）：

## 視覺衝擊力
構圖、剪影與主體是否突出？

## 光影與色彩
光源方向是否明確？色彩搭配（主色、輔色、點綴色）是否和諧？固有色與環境色處理？

## 骨架與人體結構
在完稿衣物下，人體骨架（特別是雙肩、骨盆、四肢關節）是否合理？

## 細節與精緻度
線條收尾、材質表現（金屬、布料、皮膚等）的完成度評估。

## 綜合改進方向
如果這張圖要達到商業級發佈標準，最急需修改的三個地方是什麼？
"""

_LINE_COLOR_PROMPT = """\
你是一位色彩設計師。這是一張**乾淨的線稿**，請為它規劃 3 套不同的配色方案。
請考慮角色的氣質與可能的場景氛圍。

請依以下結構回應（使用繁體中文）：

## 方案一：經典/預設風格
- **主色 (60%)**：
- **輔色 (30%)**：
- **點綴色 (10%)**：
- **氛圍描述**：

## 方案二：對比/強烈風格
- **主色 (60%)**：
- **輔色 (30%)**：
- **點綴色 (10%)**：
- **氛圍描述**：

## 方案三：特殊/情境風格（如夜間、魔法、黃昏）
- **主色 (60%)**：
- **輔色 (30%)**：
- **點綴色 (10%)**：
- **氛圍描述**：
"""


def analyze_sketch_bytes(
    image_bytes: bytes,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> str:
    return ollama_client.analyze_image_bytes(image_bytes, _SKETCH_PROMPT, model=model)


def analyze_finished_bytes(
    image_bytes: bytes,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> str:
    return ollama_client.analyze_image_bytes(image_bytes, _FINISHED_PROMPT, model=model)


def suggest_lineart_colors_bytes(
    image_bytes: bytes,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> str:
    return ollama_client.analyze_image_bytes(image_bytes, _LINE_COLOR_PROMPT, model=model)


def analyze_composition_bytes(
    image_bytes: bytes,
    user_question: str,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> tuple[str, str]:
    """
    上傳草稿並提出構圖問題，由 Vision 模型給出具體建議，並提煉出精準對齊草稿的 SDXL Prompt。
    """
    prompt = f"""\
你是一位精準的草稿轉提示詞大師與構圖專家。請分析這張**草稿**並回答使用者的問題。

使用者問題：{user_question}

請嚴格依循以下結構回應（使用繁體中文）：

[ADVICE]
（請在此處詳細回答使用者的問題，給出關於視角、光源、佈局或人體結構的具體優化建議。）

[PROMPT]
（請根據草稿內容，將其轉譯為適合 Stable Diffusion 生成的英文標籤(tags)。請遵守以下硬性規則：
1. 只描述草稿中「肉眼可見」的特徵，例如髮型、姿勢與表情（例如有微笑請務必加 smile）。
2. 對於服裝，請依據草稿的剪裁客觀描述（例如：vest, hoodie, sleeveless），絕不可無中生有添加西裝(suit)、禮服、夾克等無關風格。
3. 預設背景為純白或簡單背景（white background, simple background），禁止腦補任何複雜場景。
4. 格式請完全使用逗號分隔的標籤，不要有任何自然語言解釋。）
"""

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
    prompt = "請用繁體中文簡短描述這張插畫的內容、場景與視覺重點（100字以內）。"
    return ollama_client.analyze_image(image_path, prompt, model=model)


def describe_illustration_bytes(
    image_bytes: bytes,
    model: str = ollama_client.DEFAULT_VISION_MODEL,
) -> str:
    prompt = "請用繁體中文簡短描述這張插畫的內容、場景與視覺重點（100字以內）。"
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
    prompt = f"你是一位專業的插畫創作顧問。請用繁體中文回答以下問題：\n\n{question}\n\n請給出具體、實用的建議。"
    if image_path:
        return ollama_client.analyze_image(image_path, prompt, model=model)
    if image_bytes:
        return ollama_client.analyze_image_bytes(image_bytes, prompt, model=model)
    return ollama_client.generate(prompt, model=model)


def compose_ask(
    user_question: str, 
    image_bytes: bytes, 
    model: str = ollama_client.DEFAULT_VISION_MODEL
) -> tuple[str, str]:
    """
    相容舊版 API 路由的轉接函式。
    注意：舊版參數順序為 (user_question, image_bytes)，內部已自動調換。
    """
    # 呼叫我們全新優化的精準分析函式
    return analyze_composition_bytes(
        image_bytes=image_bytes,
        user_question=user_question,
        model=model
    )
