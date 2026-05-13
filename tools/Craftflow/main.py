# tools/craftflow/main.py

import sys
from pathlib import Path
import argparse

from core.rhythm_analyzer import RhythmAnalyzer
from core.report_writer import RhythmReportWriter
from core.consistency_analyzer import ConsistencyAnalyzer
from core.consistency_report_writer import ConsistencyReportWriter
from core.worldbook_loader import WorldbookLoader
from rules import InterventionEngine
from rewrite_engine import RewriteEngine
from core.rewrite_report_writer import RewriteReportWriter


def read_input_text(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")
    return file_path.read_text(encoding="utf-8")


def _build_provider(name: str):
    if name == "openai":
        from llm.openai_provider import OpenAIProvider
        return OpenAIProvider()
    from llm.local_provider import LocalProvider
    return LocalProvider()


def main():
    parser = argparse.ArgumentParser(description="Craftflow analysis pipeline.")
    parser.add_argument("input_file")
    parser.add_argument("--mode", default="gentle", choices=["gentle", "pro"])
    parser.add_argument("--provider", default="local", choices=["local", "openai"])
    parser.add_argument(
        "--worldbook",
        default="worldbook",
        help="Worldbook directory (default: ./worldbook). Skipped silently if missing.",
    )
    parser.add_argument(
        "--no-consistency",
        action="store_true",
        help="Disable consistency check entirely.",
    )
    parser.add_argument(
        "--no-semantic-consistency",
        action="store_true",
        help="Disable LLM-based semantic consistency scan (surface scan still runs).",
    )

    args = parser.parse_args()

    input_file = Path(args.input_file)
    mode = args.mode

    try:
        provider = _build_provider(args.provider)
        rewrite_engine = RewriteEngine(provider)

        # 1️⃣ 讀檔
        text = read_input_text(input_file)

        # 2️⃣ 節奏分析
        rhythm_analyzer = RhythmAnalyzer()
        rhythm = rhythm_analyzer.analyze(text)

        print("\n[Craftflow] Rhythm Analysis Result\n")
        for p in rhythm:
            print(
                f"Paragraph {p.index}: "
                f"{p.char_count} chars | {p.status} | "
                f"Score: {p.score} | {p.preview}"
            )

        # 3️⃣ 一致性分析（可關閉）
        consistency = []
        consistency_warnings = []
        if not args.no_consistency:
            wb_root = Path(args.worldbook)
            loader = WorldbookLoader(wb_root)
            worldbook = loader.load()
            consistency_warnings.extend(loader.errors)

            if worldbook.is_empty:
                print(
                    f"\n[Craftflow] Worldbook at '{wb_root}' is empty or missing — "
                    f"consistency check skipped."
                )
            else:
                # gentle 模式不跑 LLM semantic scan，保持輕量
                enable_semantic = (
                    mode == "pro"
                    and not args.no_semantic_consistency
                )
                analyzer = ConsistencyAnalyzer(
                    worldbook=worldbook,
                    provider=provider,
                    enable_semantic=enable_semantic,
                )
                consistency = analyzer.analyze(text)
                consistency_warnings.extend(analyzer.warnings)

                total = sum(len(r.issues) for r in consistency)
                print(
                    f"\n[Craftflow] Consistency check: "
                    f"{len(worldbook.characters)} character(s), "
                    f"{len(worldbook.worlds)} world rule set(s), "
                    f"{total} issue(s) found."
                )
                for r in consistency:
                    if r.issues:
                        for i in r.issues:
                            print(
                                f"  P{r.index} [{i.severity.upper()}] "
                                f"{i.type} → {i.target}: {i.description}"
                            )

        # 4️⃣ 介入決策
        engine = InterventionEngine(mode=mode)
        decisions = engine.evaluate(rhythm, consistency)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        if decisions:
            print("\n[Craftflow] Generating rewrite suggestions...\n")
            rewrites = []
            for d in decisions:
                # decisions 用 paragraph_index (1-based)；對 paragraphs 取 index-1
                if not (1 <= d.paragraph_index <= len(paragraphs)):
                    continue
                paragraph_text = paragraphs[d.paragraph_index - 1]
                suggestion = rewrite_engine.rewrite(paragraph_text, d.reason, mode=mode)
                rewrites.append((d.paragraph_index, suggestion))

                print(f"\n--- Rewrite Suggestion (Paragraph {d.paragraph_index}, "
                      f"{d.kind}/{d.severity}) ---\n")
                print(suggestion)

            writer = RewriteReportWriter()
            output_path = writer.write(input_file, rewrites)
            print(f"\n[Craftflow] Rewrite report generated: {output_path}")
        else:
            print("\n[Craftflow] No intervention needed.")

        # 5️⃣ 產生報告
        rhythm_writer = RhythmReportWriter()
        rhythm_path = rhythm_writer.write(input_file, rhythm)
        print(f"\n[Craftflow] Rhythm report generated: {rhythm_path}")

        if consistency:
            consistency_writer = ConsistencyReportWriter()
            consistency_path = consistency_writer.write(
                input_file, consistency, warnings=consistency_warnings
            )
            print(f"[Craftflow] Consistency report generated: {consistency_path}")

        print("[Craftflow] Analysis completed. (v0.3)")

    except Exception as e:
        print(f"[Craftflow] Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
