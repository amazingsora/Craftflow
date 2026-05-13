from pathlib import Path
from datetime import datetime
from typing import List
from .rhythm_analyzer import ParagraphAnalysis


class RhythmReportWriter:
    def write(
        self,
        source_file: Path,
        analysis: List[ParagraphAnalysis],
        output_dir: Path = Path("analysis")
    ) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)

        report_path = output_dir / f"{source_file.stem}_rhythm.md"

        lines = []
        lines.append(f"# Craftflow Rhythm Report")
        lines.append("")
        lines.append(f"- Source file: `{source_file}`")
        lines.append(f"- Generated at: {datetime.now().isoformat(timespec='seconds')}")
        lines.append("")
        lines.append("---")
        lines.append("")

        for p in analysis:
            lines.append(f"## Paragraph {p.index}")
            lines.append(f"- Characters: {p.char_count}")
            lines.append(f"- Status: **{p.status}**")
            lines.append("")
            lines.append("> " + p.preview)
            lines.append("")

        report_path.write_text("\n".join(lines), encoding="utf-8")
        return report_path
