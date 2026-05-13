from dataclasses import dataclass
from typing import List


@dataclass
class ParagraphAnalysis:
    index: int
    char_count: int
    status: str
    preview: str
    score: int


class RhythmAnalyzer:
    """
    Analyze paragraph rhythm based on character count.
    This analyzer NEVER modifies the original text.
    """

    def __init__(
        self,
        short_threshold: int = 50,
        long_threshold: int = 200
    ):
        self.short_threshold = short_threshold
        self.long_threshold = long_threshold

    def analyze(self, text: str) -> List[ParagraphAnalysis]:
        paragraphs = self._split_paragraphs(text)
        results: List[ParagraphAnalysis] = []

        for idx, para in enumerate(paragraphs, start=1):
            char_count = len(para)
            score = self._calculate_score(char_count)
            if char_count < self.short_threshold:
                status = "TOO_SHORT"
            elif char_count > self.long_threshold:
                status = "TOO_LONG"
            else:
                status = "NORMAL"

            results.append(
                ParagraphAnalysis(
                    index=idx,
                    char_count=char_count,
                    status=status,
                    preview=self._make_preview(para),
                    score=score
                )
            )

        return results

    def _split_paragraphs(self, text: str) -> List[str]:
        """
        Split text by empty lines.
        """
        return [p.strip() for p in text.split("\n\n") if p.strip()]

    def _make_preview(self, paragraph: str, length: int = 30) -> str:
        """
        Return the first N characters as preview.
        """
        return paragraph[:length].replace("\n", " ") + ("..." if len(paragraph) > length else "")
    def _calculate_score(self, char_count):
        if char_count < 20:
            return 30
        elif 20 <= char_count < 40:
            return 60
        elif 40 <= char_count <= 120:
            return 90
        elif 120 < char_count <= 180:
            return 70
        else:
            return 40