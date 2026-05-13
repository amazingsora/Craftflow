from dataclasses import dataclass, field

from llm.vision_provider import VisionProvider

_COLOR_PROMPT = """\
你是一位專業的色彩設計師，請分析這張線稿並提供具體的配色建議。

請依以下結構回應（使用繁體中文）：

## 整體色調方向
建議的主色調（暖色 / 冷色 / 中性），想營造的情緒氛圍。

## 主要區域配色
針對線稿中各主要區域（人物膚色、服裝、背景等）提供建議顏色，
並附上大概的色值（例如 #F5C5A3）。

## 配色方案（提供 2-3 套）
每套方案包含：
- 方案名稱（例如「溫暖日系」、「冷調賽博」）
- 主色 × 2-3、輔助色 × 1-2、強調色 × 1
- 適用情境說明

## 陰影與高光建議
陰影色的色相傾向（偏冷？偏暖？），高光的處理方式。

## 上色注意事項
上色時需要特別留意的技術重點（3點以內）。\
"""


@dataclass
class ColorAdvice:
    image_path: str
    content: str
    warnings: list[str] = field(default_factory=list)


class ColorAdvisor:
    def __init__(self, model: str = "llava"):
        self.vision = VisionProvider(model=model)

    def advise(self, image_path: str) -> ColorAdvice:
        content = self.vision.analyze(image_path, _COLOR_PROMPT)
        warnings = []
        if content.startswith("["):
            warnings.append(content)
            content = ""
        return ColorAdvice(image_path=image_path, content=content, warnings=warnings)
