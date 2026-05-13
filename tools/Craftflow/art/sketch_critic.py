from dataclasses import dataclass, field

from llm.vision_provider import VisionProvider

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
列出 3-5 個具體可執行的改進動作，由重要到次要排序。\
"""

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
列出 3-5 個最值得改進的具體問題，由重要到次要排序。\
"""


@dataclass
class ArtCritique:
    mode: str
    image_path: str
    content: str
    warnings: list[str] = field(default_factory=list)


class SketchCritic:
    def __init__(self, model: str = "llava"):
        self.vision = VisionProvider(model=model)

    def critique_sketch(self, image_path: str) -> ArtCritique:
        return self._run("sketch_critique", image_path, _SKETCH_PROMPT)

    def critique_finished(self, image_path: str) -> ArtCritique:
        return self._run("finished_critique", image_path, _FINISHED_PROMPT)

    def _run(self, mode: str, image_path: str, prompt: str) -> ArtCritique:
        content = self.vision.analyze(image_path, prompt)
        warnings = []
        if content.startswith("["):
            warnings.append(content)
            content = ""
        return ArtCritique(mode=mode, image_path=image_path, content=content, warnings=warnings)
