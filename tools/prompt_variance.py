#!/usr/bin/env python3
"""A3 P3-3：prompt 穩定度量測（2026-08-22）。

同一輸入呼叫 compiler.compile() N 次，統計每個 tag 的出現率，找出「同輸入不同次
編譯結果不同」的不穩定來源。背景見 doc/target/角色管理品質改進_開發規劃_20260822.md
第 0-2 節：seed 之外，prompt 每次重新 LLM 編譯（temperature=0.3、無 seed）也是
「按同一按鈕兩次結果不同」的成因之一，過去只能靠感覺猜「哪個 tag 常掉」（如
tactical vest 時有時無），這支工具把它換成數據。

⚠️ 需要真的連上 Ollama（本機執行，非沙箱 —— 沙箱內 localhost:11434 連不到）：
    cd backend && python ../tools/prompt_variance.py --text "戰術背心的白髮少女"

驗收標準對應（規劃書「三、驗收標準」第 3 點）：
    草圖既有服裝品項出現率 ≥ 9/10 → 對應本工具 --threshold 0.9（預設值）。

用法：
    python tools/prompt_variance.py --text "戰術背心的白髮少女，銀色長髮，紅色眼睛"
    python tools/prompt_variance.py --text "..." --style anima --n 20 --threshold 0.8
    python tools/prompt_variance.py --text "..." --anchor "銀色長髮"
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--text", required=True, help="中文描述（同 character_design_service 的 raw_desc）")
    parser.add_argument("--style", default="illustrious",
                        help="PromptStyle 名稱（sdxl/illustrious/anima/pony/noobai/flux/...），預設 illustrious")
    parser.add_argument("--anchor", default="", help="anchor_text（core_traits 顏色錨點，可留空）")
    parser.add_argument("--n", type=int, default=10, help="重複編譯次數，預設 10")
    parser.add_argument("--threshold", type=float, default=0.9,
                        help="出現率門檻，低於此值標記為不穩定 tag，預設 0.9（對應驗收標準 9/10）")
    args = parser.parse_args()

    # 延後 import：先插好 sys.path，且讓「未安裝 backend 依賴」的錯誤訊息更好懂。
    try:
        from app.services.ai.prompt_engine import compiler
        from app.services.ai.prompt_engine.styles import PromptStyle
    except ImportError as e:
        print(f"匯入 backend 模組失敗：{e}\n請在 backend/ 的 venv 下執行，或確認相依套件已安裝。",
              file=sys.stderr)
        return 1

    try:
        style = PromptStyle(args.style)
    except ValueError:
        print(f"未知 style '{args.style}'，可用值：{[s.value for s in PromptStyle]}", file=sys.stderr)
        return 1

    tag_counts: Counter[str] = Counter()
    failures = 0

    print(f"編譯 {args.n} 次（style={style.value}）：\n")
    for i in range(args.n):
        try:
            positive, _negative = compiler.compile(args.text, style=style, anchor_text=args.anchor)
        except RuntimeError as e:
            failures += 1
            print(f"[{i + 1}/{args.n}] 編譯失敗（Ollama 未啟動或文字模型未安裝？）：{e}", file=sys.stderr)
            continue
        # 每次生成內同一 tag 只計一次，避免句子裡剛好重複同詞把出現率洗高。
        tags = {t.strip().lower() for t in positive.split(",") if t.strip()}
        tag_counts.update(tags)
        print(f"[{i + 1}/{args.n}] {positive}")

    n_ok = args.n - failures
    if n_ok == 0:
        print("\n全部編譯失敗，無法統計（先確認 Ollama 是否啟動、文字模型是否已安裝）。", file=sys.stderr)
        return 1

    print(f"\n=== 出現率統計（{n_ok}/{args.n} 次成功） ===")
    unstable: list[str] = []
    for tag, count in sorted(tag_counts.items(), key=lambda kv: kv[1] / n_ok):
        rate = count / n_ok
        marker = " ← 不穩定" if rate < args.threshold else ""
        print(f"{rate:5.0%}  ({count}/{n_ok})  {tag}{marker}")
        if rate < args.threshold:
            unstable.append(tag)

    print(f"\n低於門檻 {args.threshold:.0%} 的不穩定 tag 共 {len(unstable)} 個：{unstable}")
    if failures:
        print(f"（另有 {failures}/{args.n} 次編譯失敗，未列入統計）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
