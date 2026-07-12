"""
Golden regression 一鍵 diff 腳本（P2，2026-07-02 規劃）。

用法（在 backend/ 目錄下）：
    python -m tests.golden.run_diff           # 比對現有 snapshot，有差異印 diff 並以非 0 結束
    python -m tests.golden.run_diff --update   # 用目前程式碼行為覆寫 snapshot（改動 prompt/過濾器後，
                                                 確認 diff 是預期內才執行，然後 review 再 commit）

原理：monkeypatch ollama_client.generate() 回傳每個 case 固定的 mock_raw，
呼叫真正的 compiler.compile()，把 (positive, negative) 結果與 tests/golden/snapshots.json 比對。
不需要真的連 Ollama。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

from app.services.ai import ollama_client
from app.services.ai.prompt_engine import compiler

from tests.golden.cases import CASES

SNAPSHOT_FILE = Path(__file__).parent / "snapshots.json"


def _run_case(case) -> dict:
    with patch.object(ollama_client, "generate", return_value=case.mock_raw):
        positive, negative = compiler.compile(
            case.text,
            style=case.style,
            anchor_text=case.anchor_text,
            quality_prefix_override=case.quality_prefix_override,
            negative_override=case.negative_override,
        )
    return {"positive": positive, "negative": negative}


def _load_snapshots() -> dict:
    if not SNAPSHOT_FILE.exists():
        return {}
    return json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))


def _save_snapshots(data: dict) -> None:
    SNAPSHOT_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    update = "--update" in sys.argv
    snapshots = _load_snapshots()
    new_snapshots: dict = {}
    mismatches: list[str] = []

    for case in CASES:
        result = _run_case(case)
        new_snapshots[case.name] = result
        expected = snapshots.get(case.name)
        if expected is None:
            print(f"[NEW]  {case.name}: 尚無 snapshot（{'將寫入' if update else '需先 --update'}）")
            if not update:
                mismatches.append(case.name)
            continue
        if expected != result:
            mismatches.append(case.name)
            print(f"[DIFF] {case.name}  ({case.note})")
            print(f"  - positive expected: {expected['positive']}")
            print(f"  + positive actual:   {result['positive']}")
            print(f"  - negative expected: {expected['negative']}")
            print(f"  + negative actual:   {result['negative']}")
        else:
            print(f"[OK]   {case.name}")

    if update:
        _save_snapshots(new_snapshots)
        print(f"\n已寫入 {len(new_snapshots)} 筆 snapshot → {SNAPSHOT_FILE}")
        return 0

    if mismatches:
        print(f"\n{len(mismatches)} 筆案例與 snapshot 不符：{mismatches}")
        print("若為預期內改動（如調整 sanitizer/prompt），確認無誤後執行 --update 覆寫。")
        return 1

    print(f"\n全部 {len(CASES)} 筆案例與 snapshot 一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
