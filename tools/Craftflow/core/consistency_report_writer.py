# tools/Craftflow/core/consistency_report_writer.py
from pathlib import Path
from datetime import datetime
from typing import List

from core.consistency_analyzer import ParagraphConsistency
from utils.path_utils import get_output_path


class ConsistencyReportWriter:
    """
    寫出 *_consistency.md 報告。
    與 RhythmReportWriter / RewriteReportWriter 並列，互不干擾。
    """

    SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

    def write(
        self,
        input_file: Path,
        results: List[ParagraphConsistency],
        warnings: List[str] = None,
    ) -> Path:
        output_path = get_output_path(input_file, "consistency")

        lines = []
        lines.append("# Craftflow Consistency Report")
        lines.append("")
        lines.append(f"- Source file: `{input_file}`")
        lines.append(f"- Generated at: {datetime.now().isoformat(timespec='seconds')}")
        lines.append("")

        # Summary
        total_issues = sum(len(r.issues) for r in results)
        high = sum(1 for r in results for i in r.issues if i.severity == "high")
        medium = sum(1 for r in results for i in r.issues if i.severity == "medium")
        low = sum(1 for r in results for i in r.issues if i.severity == "low")

        lines.append("## Summary")
        lines.append("")
        lines.append(f"- Paragraphs analyzed: {len(results)}")
        lines.append(f"- Total issues: **{total_issues}** "
                     f"(high: {high}, medium: {medium}, low: {low})")
        lines.append("")

        if warnings:
            lines.append("## Warnings")
            lines.append("")
            for w in warnings:
                lines.append(f"- {w}")
            lines.append("")

        lines.append("---")
        lines.append("")

        for r in results:
            lines.append(f"## Paragraph {r.index}")
            mentioned = ", ".join(r.mentioned_characters) if r.mentioned_characters else "(none)"
            lines.append(f"- Mentioned characters: {mentioned}")
            lines.append(f"- Issues: {len(r.issues)}")
            lines.append("")
            lines.append("> " + r.preview)
            lines.append("")

            if r.issues:
                # 依 severity 排序，再依 source（surface 先於 semantic 方便對照）
                sorted_issues = sorted(
                    r.issues,
                    key=lambda i: (self.SEVERITY_ORDER.get(i.severity, 9), i.source),
                )
                for i in sorted_issues:
                    badge = i.severity.upper()
                    lines.append(f"### [{badge}] {i.type} → {i.target}")
                    lines.append(f"- Source: `{i.source}`")
                    lines.append(f"- {i.description}")
                    if i.evidence:
                        lines.append(f"- Evidence: `{i.evidence}`")
                    lines.append("")

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path
