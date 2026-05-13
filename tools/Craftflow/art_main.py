#!/usr/bin/env python3
"""
Craftflow Art Module — entry point

Modes:
  enhance           草稿 + 自己的作品 → 同風格商業品質參考圖  ★ 主要
  style_explore     草稿 + 任意風格參考圖 → 探索不同畫風呈現  ★ 次要
  sketch_critique   草稿 → 文字改進意見
  line_color        線稿 → 配色建議
  finished_critique 完成圖 → 詳細改進意見
  sketch_to_line    草稿 → 線稿化

Usage examples:
  python art_main.py draft.png --mode enhance --style-ref my_art1.png my_art2.png
  python art_main.py draft.png --mode style_explore --style-ref ghibli_ref.png
  python art_main.py draft.png --mode sketch_critique
  python art_main.py lineart.png --mode line_color
  python art_main.py final.png --mode finished_critique --model qwen2-vl
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from art.sketch_critic import SketchCritic
from art.color_advisor import ColorAdvisor
from art.lineart_generator import LineartGenerator
from art.art_enhancer import ArtEnhancer
from art.art_report_writer import ArtReportWriter


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Craftflow Art Analysis Module",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input_image", help="Path to the input image file")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["enhance", "style_explore", "sketch_critique", "line_color", "finished_critique", "sketch_to_line"],
        help=(
            "enhance: 草稿→同風格商業品質圖 ★ | "
            "style_explore: 草稿→不同風格探索 | "
            "sketch_critique: 草稿→改進意見 | "
            "line_color: 線稿→配色意見 | "
            "finished_critique: 完成圖→改進意見 | "
            "sketch_to_line: 草稿→線稿化"
        ),
    )
    parser.add_argument(
        "--style-ref",
        nargs="+",
        metavar="IMAGE",
        help=(
            "風格參考圖路徑（enhance / style_explore 模式必填）。"
            "enhance 模式請提供自己的完成作品；"
            "style_explore 模式請提供目標風格的參考圖。"
            "可一次指定多張：--style-ref a.png b.png"
        ),
    )
    parser.add_argument(
        "--model",
        default="llava",
        help="Ollama vision model to use (default: llava). Alternatives: llava:13b, qwen2-vl, bakllava",
    )
    parser.add_argument(
        "--output-dir",
        default="./analysis",
        help="Directory for output reports and images (default: ./analysis)",
    )
    parser.add_argument(
        "--comfyui-url",
        default="http://localhost:8188",
        help="ComfyUI server URL (default: http://localhost:8188)",
    )

    args = parser.parse_args()
    image_path = Path(args.input_image)

    if not image_path.exists():
        print(f"[Art] Error: input image not found: {image_path}")
        sys.exit(1)

    writer = ArtReportWriter(output_dir=args.output_dir)

    if args.mode in ("enhance", "style_explore"):
        if not args.style_ref:
            print(f"[Art] Error: --style-ref is required for --mode {args.mode}")
            print("  enhance:      --style-ref 你的完成作品.png")
            print("  style_explore: --style-ref 目標風格參考圖.png")
            sys.exit(1)

        missing = [p for p in args.style_ref if not Path(p).exists()]
        if missing:
            for p in missing:
                print(f"[Art] Error: style reference not found: {p}")
            sys.exit(1)

        enhancer = ArtEnhancer(output_dir=args.output_dir, comfyui_url=args.comfyui_url)

        if args.mode == "enhance":
            print(f"[Art] 風格強化中: {image_path.name}")
            print(f"[Art] 風格參考: {', '.join(args.style_ref)}")
            result = enhancer.enhance(str(image_path), args.style_ref)
        else:
            print(f"[Art] 風格探索中: {image_path.name}")
            print(f"[Art] 目標風格: {', '.join(args.style_ref)}")
            result = enhancer.style_explore(str(image_path), args.style_ref)

        _print_warnings(result.warnings)
        out = writer.write_enhance_result(result)
        if result.success:
            print(f"[Art] 輸出圖片: {result.output_path}")
        else:
            print(f"[Art] 失敗: {result.message}")
        print(f"[Art] 報告: {out}")

    elif args.mode == "sketch_critique":
        print(f"[Art] 草稿分析中: {image_path.name} (model: {args.model})")
        critic = SketchCritic(model=args.model)
        result = critic.critique_sketch(str(image_path))
        _print_warnings(result.warnings)
        out = writer.write_critique(result)
        print(f"[Art] 改進意見已儲存至: {out}")

    elif args.mode == "sketch_to_line":
        print(f"[Art] 線稿化中: {image_path.name} (ComfyUI: {args.comfyui_url})")
        generator = LineartGenerator(output_dir=args.output_dir, comfyui_url=args.comfyui_url)
        result = generator.generate(str(image_path))
        out = writer.write_lineart_result(result)
        if result.success:
            print(f"[Art] 線稿已儲存至: {result.output_path}")
        else:
            print(f"[Art] 線稿化失敗: {result.message}")
        print(f"[Art] 結果報告已儲存至: {out}")

    elif args.mode == "line_color":
        print(f"[Art] 配色分析中: {image_path.name} (model: {args.model})")
        advisor = ColorAdvisor(model=args.model)
        result = advisor.advise(str(image_path))
        _print_warnings(result.warnings)
        out = writer.write_color_advice(result)
        print(f"[Art] 配色建議已儲存至: {out}")

    elif args.mode == "finished_critique":
        print(f"[Art] 完成圖分析中: {image_path.name} (model: {args.model})")
        critic = SketchCritic(model=args.model)
        result = critic.critique_finished(str(image_path))
        _print_warnings(result.warnings)
        out = writer.write_critique(result)
        print(f"[Art] 改進意見已儲存至: {out}")

    print("[Art] 完成。")


def _print_warnings(warnings: list[str]) -> None:
    for w in warnings:
        print(f"[Art] 警告: {w}")


if __name__ == "__main__":
    main()
