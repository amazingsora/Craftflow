from datetime import datetime
from pathlib import Path

from art.sketch_critic import ArtCritique
from art.color_advisor import ColorAdvice
from art.lineart_generator import LineartResult
from art.art_enhancer import EnhanceResult

_MODE_LABELS = {
    "sketch_critique": "草稿分析",
    "finished_critique": "完成圖分析",
}


class ArtReportWriter:
    def __init__(self, output_dir: str = "./analysis"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_critique(self, critique: ArtCritique) -> str:
        label = _MODE_LABELS.get(critique.mode, critique.mode)
        stem = Path(critique.image_path).stem
        out_path = self.output_dir / f"{stem}_{critique.mode}.md"

        lines = [
            f"# {label} — {stem}",
            "",
            f"**輸入檔案**: `{critique.image_path}`  ",
            f"**分析時間**: {_now()}  ",
            f"**模式**: {critique.mode}",
            "",
            "---",
            "",
        ]

        if critique.warnings:
            lines += ["> **警告**", ""]
            for w in critique.warnings:
                lines.append(f"> {w}")
            lines.append("")

        if critique.content:
            lines.append(critique.content)
        else:
            lines.append("*（無法取得分析結果，請確認 Ollama 是否正在執行且已下載對應模型。）*")

        out_path.write_text("\n".join(lines), encoding="utf-8")
        return str(out_path)

    def write_color_advice(self, advice: ColorAdvice) -> str:
        stem = Path(advice.image_path).stem
        out_path = self.output_dir / f"{stem}_color_advice.md"

        lines = [
            f"# 配色建議 — {stem}",
            "",
            f"**輸入檔案**: `{advice.image_path}`  ",
            f"**分析時間**: {_now()}",
            "",
            "---",
            "",
        ]

        if advice.warnings:
            lines += ["> **警告**", ""]
            for w in advice.warnings:
                lines.append(f"> {w}")
            lines.append("")

        if advice.content:
            lines.append(advice.content)
        else:
            lines.append("*（無法取得配色建議，請確認 Ollama 是否正在執行且已下載對應模型。）*")

        out_path.write_text("\n".join(lines), encoding="utf-8")
        return str(out_path)

    def write_lineart_result(self, result: LineartResult) -> str:
        stem = Path(result.input_path).stem
        out_path = self.output_dir / f"{stem}_lineart_result.md"

        status = "成功" if result.success else "失敗"
        icon = "✅" if result.success else "❌"

        lines = [
            f"# 線稿化結果 — {stem}",
            "",
            f"**輸入檔案**: `{result.input_path}`  ",
            f"**執行時間**: {_now()}  ",
            f"**狀態**: {icon} {status}",
        ]

        if result.output_path:
            lines.append(f"**輸出檔案**: `{result.output_path}`")

        lines += ["", "---", "", f"**訊息**: {result.message}"]

        out_path.write_text("\n".join(lines), encoding="utf-8")
        return str(out_path)


    def write_enhance_result(self, result: EnhanceResult) -> str:
        stem = Path(result.input_path).stem
        out_path = self.output_dir / f"{stem}_{result.mode}_result.md"

        mode_label = "風格強化（個人風格）" if result.mode == "enhance" else "風格探索"
        status_icon = "✅" if result.success else "❌"
        status_text = "成功" if result.success else "失敗"

        lines = [
            f"# {mode_label} — {stem}",
            "",
            f"**輸入草稿**: `{result.input_path}`  ",
            f"**風格參考**: {', '.join(f'`{r}`' for r in result.style_refs)}  ",
            f"**執行時間**: {_now()}  ",
            f"**狀態**: {status_icon} {status_text}",
        ]

        if result.output_path:
            lines.append(f"**輸出圖片**: `{result.output_path}`")

        lines += ["", "---", "", f"**訊息**: {result.message}"]

        if result.warnings:
            lines += ["", "**注意事項**:"]
            for w in result.warnings:
                lines.append(f"- {w}")

        out_path.write_text("\n".join(lines), encoding="utf-8")
        return str(out_path)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
