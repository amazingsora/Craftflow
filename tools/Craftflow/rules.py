from typing import List, Optional
from core.rhythm_analyzer import ParagraphAnalysis
from core.consistency_analyzer import ParagraphConsistency, ConsistencyIssue


class InterventionDecision:
    """
    一次介入決定。可能來自節奏分析，也可能來自一致性檢查。
    為了讓 RewriteEngine 不必判斷來源，把脈絡資訊統一放進 context 字典。
    """

    def __init__(
        self,
        paragraph_index: int,
        reason: str,
        kind: str = "rhythm",          # "rhythm" | "consistency"
        severity: str = "medium",       # "high" | "medium" | "low"
        context: Optional[dict] = None,
    ):
        self.paragraph_index = paragraph_index
        self.reason = reason
        self.kind = kind
        self.severity = severity
        self.context = context or {}


class InterventionEngine:
    """
    根據節奏 + 一致性兩種分析結果，決定是否要在「介入層」對作者提出回饋。

    模式行為：
        gentle —— 只回應節奏異常（保留現行 v0.2 行為）。一致性高度違規會被
                  收進報告，但不觸發 rewrite，避免打斷創作節奏。
        pro    —— 節奏異常 + 連續長段 + 一致性 high 嚴重度都會觸發 rewrite。
    """

    def __init__(self, mode: str = "gentle"):
        if mode not in ("gentle", "pro"):
            raise ValueError(f"Unknown mode: {mode}")
        self.mode = mode

    def evaluate(
        self,
        rhythm_analysis: List[ParagraphAnalysis],
        consistency_results: Optional[List[ParagraphConsistency]] = None,
    ) -> List[InterventionDecision]:
        decisions: List[InterventionDecision] = []

        # ----- Rhythm（兩種模式共用基本判斷） -----
        for i, p in enumerate(rhythm_analysis):
            if p.status in ("TOO_LONG", "TOO_SHORT"):
                decisions.append(InterventionDecision(
                    paragraph_index=p.index,
                    reason=f"Rhythm issue detected ({p.status}).",
                    kind="rhythm",
                    severity="medium",
                ))

            # Pro 模式：連續長段檢查
            if self.mode == "pro" and i > 0:
                prev = rhythm_analysis[i - 1]
                if p.status == "TOO_LONG" and prev.status == "TOO_LONG":
                    decisions.append(InterventionDecision(
                        paragraph_index=p.index,
                        reason="Consecutive long paragraphs – pacing drag risk.",
                        kind="rhythm",
                        severity="medium",
                    ))

        # ----- Consistency（pro 模式才會觸發 rewrite） -----
        if self.mode == "pro" and consistency_results:
            for pc in consistency_results:
                for issue in pc.issues:
                    if issue.severity != "high":
                        continue
                    decisions.append(InterventionDecision(
                        paragraph_index=pc.index,
                        reason=self._format_consistency_reason(issue),
                        kind="consistency",
                        severity=issue.severity,
                        context={
                            "issue_type": issue.type,
                            "target": issue.target,
                            "evidence": issue.evidence,
                        },
                    ))

        return decisions

    @staticmethod
    def _format_consistency_reason(issue: ConsistencyIssue) -> str:
        return (
            f"Consistency violation ({issue.type}, target={issue.target}): "
            f"{issue.description}"
        )
