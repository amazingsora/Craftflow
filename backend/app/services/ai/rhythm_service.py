"""
Rhythm analysis — rule-based, no LLM required.
Ported from tools/Craftflow/core/rhythm_analyzer.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ParagraphRhythm:
    index: int
    char_count: int
    status: str       # NORMAL | TOO_SHORT | TOO_LONG
    score: int        # 30–90
    preview: str


@dataclass
class RhythmResult:
    paragraphs: list[ParagraphRhythm]
    total: int
    issues: int

    @property
    def summary(self) -> str:
        return f"{self.total} paragraphs, {self.issues} issue(s)"


def analyze(text: str, short_threshold: int = 50, long_threshold: int = 200) -> RhythmResult:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    results: list[ParagraphRhythm] = []

    for idx, para in enumerate(paragraphs, start=1):
        n = len(para)
        if n < short_threshold:
            status = "TOO_SHORT"
        elif n > long_threshold:
            status = "TOO_LONG"
        else:
            status = "NORMAL"

        results.append(ParagraphRhythm(
            index=idx,
            char_count=n,
            status=status,
            score=_score(n),
            preview=para[:30].replace("\n", " ") + ("..." if len(para) > 30 else ""),
        ))

    issues = sum(1 for r in results if r.status != "NORMAL")
    return RhythmResult(paragraphs=results, total=len(results), issues=issues)


def _score(n: int) -> int:
    if n < 20:
        return 30
    if n < 40:
        return 60
    if n <= 120:
        return 90
    if n <= 180:
        return 70
    return 40
