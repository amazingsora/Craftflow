"""
test_pro_mode.py — 用假 provider 驗 pro 模式整條管線
（避免依賴本地 Ollama 也能驗證 semantic scan 與 consistency-driven rewrite）。

執行方式：
    cd tools/Craftflow
    python3 test_pro_mode.py
"""

import sys
from pathlib import Path

# 確保以 tools/Craftflow 為工作目錄時 import 正常
sys.path.insert(0, str(Path(__file__).parent))

from core.rhythm_analyzer import RhythmAnalyzer
from core.consistency_analyzer import ConsistencyAnalyzer
from core.consistency_report_writer import ConsistencyReportWriter
from core.worldbook_loader import WorldbookLoader
from rules import InterventionEngine
from rewrite_engine import RewriteEngine


class FakeProvider:
    """Provider stub，根據 prompt 內容回傳對應的假輸出。"""

    def __init__(self):
        self.calls = []

    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)

        # 一致性檢查 prompt → 回 JSON 陣列
        if "JSON 輸出" in prompt or "JSON output" in prompt:
            if "大聲叫罵" in prompt:
                return """[
  {
    "type": "character_voice",
    "severity": "medium",
    "target": "艾莉絲",
    "description": "情緒外顯方式不符 voice_style 短句、克制",
    "evidence": "情緒激動到難以自抑"
  }
]"""
            if "手機" in prompt:
                return "[]"  # 已被 surface scan 覆蓋
            return "[]"

        # 否則視為 rewrite prompt
        return "（這是假 LLM 回的改寫示例段落。）"


def main():
    test_file = Path("writing/drafts/consistency_test.md")
    text = test_file.read_text(encoding="utf-8")

    fake = FakeProvider()

    # 1. 節奏
    rhythm = RhythmAnalyzer().analyze(text)

    # 2. 一致性（pro: 開 semantic）
    wb = WorldbookLoader(Path("worldbook")).load()
    analyzer = ConsistencyAnalyzer(
        worldbook=wb,
        provider=fake,
        enable_semantic=True,
    )
    consistency = analyzer.analyze(text)

    # 3. 介入
    engine = InterventionEngine(mode="pro")
    decisions = engine.evaluate(rhythm, consistency)

    # ----- 驗證 -----
    assert wb.characters, "Worldbook should have characters"

    surface_count = sum(
        1 for r in consistency for i in r.issues if i.source == "surface"
    )
    semantic_count = sum(
        1 for r in consistency for i in r.issues if i.source == "semantic"
    )
    assert surface_count == 3, f"Expected 3 surface issues, got {surface_count}"
    assert semantic_count >= 1, f"Expected ≥1 semantic issue, got {semantic_count}"

    # decisions: 至少含三個 high consistency 違規（surface），且 kind 標記正確
    consistency_decisions = [d for d in decisions if d.kind == "consistency"]
    assert len(consistency_decisions) >= 3, \
        f"Expected ≥3 consistency decisions, got {len(consistency_decisions)}"
    assert all(d.severity == "high" for d in consistency_decisions), \
        "pro mode 應只把 high 嚴重度的一致性違規送進 rewrite"

    # 跑 rewrite，確認 reason 被正確傳入
    rewrite_engine = RewriteEngine(fake)
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    for d in consistency_decisions:
        out = rewrite_engine.rewrite(
            paragraphs[d.paragraph_index - 1], d.reason, mode="pro"
        )
        assert out, "rewrite output 不該為空"
        # 確認 prompt 內含上下文
        last_prompt = fake.calls[-1]
        assert d.reason in last_prompt, "rewrite prompt 應包含 decision.reason"

    # 寫報告
    report_path = ConsistencyReportWriter().write(
        test_file, consistency, warnings=analyzer.warnings
    )
    print(f"[OK] Pro 模式管線通過。Consistency report: {report_path}")
    print(f"     surface={surface_count}, semantic={semantic_count}, "
          f"consistency_decisions={len(consistency_decisions)}")
    print(f"     Total fake LLM calls: {len(fake.calls)}")


if __name__ == "__main__":
    main()
