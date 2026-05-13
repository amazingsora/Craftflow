# tools/Craftflow/core/consistency_analyzer.py
"""
ConsistencyAnalyzer — 創作一致性檢查器。

設計兩階段：
1. Surface scan：純規則 / 關鍵字比對，無 LLM，必跑。
   - 偵測段落提及哪些角色（name + aliases 子字串匹配）
   - forbidden_actions 關鍵字命中 → high severity
   - world.forbidden_keywords 命中 → high severity

2. Semantic scan：LLM 推論，可關閉。
   - 對提及到角色的段落，把該角色設定 + 段落丟給 LLM
   - LLM 回傳 JSON 陣列，描述隱性違規
   - LLM 不可用時自動跳過（不阻斷流程）

本分析器不修改原文。輸出僅為結構化 ConsistencyIssue 列表。
"""

import json
import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional

from core.worldbook_loader import Worldbook, Character, WorldRules


@dataclass
class ConsistencyIssue:
    paragraph_index: int
    type: str               # "character_behavior" | "character_voice" | "world_rule" | "forbidden_keyword"
    severity: str           # "high" | "medium" | "low"
    target: str             # 角色名稱 or 世界規則名稱
    description: str
    evidence: str
    source: str = "surface" # "surface" | "semantic"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParagraphConsistency:
    """單一段落的一致性結果，含命中的角色與所有 issue。"""
    index: int
    preview: str
    mentioned_characters: List[str] = field(default_factory=list)
    issues: List[ConsistencyIssue] = field(default_factory=list)


class ConsistencyAnalyzer:

    def __init__(
        self,
        worldbook: Worldbook,
        provider=None,
        enable_semantic: bool = False,
        max_semantic_paragraphs: int = 20,
    ):
        """
        :param worldbook: 已載入的 Worldbook
        :param provider: LLMProvider，semantic 階段使用；可為 None
        :param enable_semantic: 是否啟用 LLM 語意檢查（建議 pro 模式啟用）
        :param max_semantic_paragraphs: 防止整篇長文一次燒爆 LLM
        """
        self.worldbook = worldbook
        self.provider = provider
        self.enable_semantic = enable_semantic and provider is not None
        self.max_semantic_paragraphs = max_semantic_paragraphs
        self.warnings: List[str] = []

    # ============ public ============

    def analyze(self, text: str) -> List[ParagraphConsistency]:
        if self.worldbook.is_empty:
            self.warnings.append(
                "Worldbook is empty — consistency check skipped. "
                "Add YAML files under worldbook/characters/ or worldbook/world/."
            )
            return []

        paragraphs = self._split_paragraphs(text)
        results: List[ParagraphConsistency] = []

        for idx, para in enumerate(paragraphs, start=1):
            mentioned = self._detect_characters(para)
            pc = ParagraphConsistency(
                index=idx,
                preview=self._make_preview(para),
                mentioned_characters=[c.name for c in mentioned],
            )

            # Phase 1: surface scan
            pc.issues.extend(self._surface_scan(idx, para, mentioned))

            results.append(pc)

        # Phase 2: semantic scan (跨段落迴圈分開做，方便日後加快取與 batching)
        if self.enable_semantic:
            self._semantic_scan(results, paragraphs)

        return results

    # ============ phase 1 ============

    def _surface_scan(
        self,
        idx: int,
        paragraph: str,
        mentioned: List[Character],
    ) -> List[ConsistencyIssue]:
        issues: List[ConsistencyIssue] = []

        # 角色層：forbidden_actions 關鍵字命中
        for c in mentioned:
            for action in c.forbidden_actions:
                if action and action in paragraph:
                    issues.append(ConsistencyIssue(
                        paragraph_index=idx,
                        type="character_behavior",
                        severity="high",
                        target=c.name,
                        description=f"Forbidden action keyword hit: '{action}'",
                        evidence=self._extract_around(paragraph, action),
                        source="surface",
                    ))

        # 世界層：forbidden_keywords 命中
        for w in self.worldbook.worlds:
            for kw in w.forbidden_keywords:
                if kw and kw in paragraph:
                    issues.append(ConsistencyIssue(
                        paragraph_index=idx,
                        type="forbidden_keyword",
                        severity="high",
                        target=w.name,
                        description=f"World forbidden keyword hit: '{kw}'",
                        evidence=self._extract_around(paragraph, kw),
                        source="surface",
                    ))

        return issues

    # ============ phase 2 ============

    def _semantic_scan(
        self,
        results: List[ParagraphConsistency],
        paragraphs: List[str],
    ) -> None:
        # Lazy import 避免在無 LLM 環境執行時載入 prompts module 的副作用
        from prompts.consistency_prompt_builder import ConsistencyPromptBuilder
        from core.language_detector import LanguageDetector

        scanned = 0
        for pc, para in zip(results, paragraphs):
            if scanned >= self.max_semantic_paragraphs:
                self.warnings.append(
                    f"Semantic scan capped at {self.max_semantic_paragraphs} paragraphs; "
                    f"remaining paragraphs skipped."
                )
                break

            chars = [self.worldbook.find_character(n) for n in pc.mentioned_characters]
            chars = [c for c in chars if c is not None]
            if not chars and not self.worldbook.worlds:
                continue

            language = LanguageDetector.detect(para)
            prompt = ConsistencyPromptBuilder.build(
                paragraph=para,
                characters_in_scope=chars,
                worlds=self.worldbook.worlds,
                language=language,
            )

            try:
                raw = self.provider.generate(prompt)
            except Exception as e:
                self.warnings.append(
                    f"Semantic scan failed at paragraph {pc.index}: {e}"
                )
                # 繼續下一段，不放棄整次分析
                continue

            scanned += 1
            parsed = self._parse_llm_json(raw)
            if parsed is None:
                self.warnings.append(
                    f"Paragraph {pc.index}: LLM output not valid JSON, skipped. "
                    f"Raw head: {raw[:80]!r}"
                )
                continue

            for item in parsed:
                if not isinstance(item, dict):
                    continue
                pc.issues.append(ConsistencyIssue(
                    paragraph_index=pc.index,
                    type=str(item.get("type") or "character_behavior"),
                    severity=str(item.get("severity") or "medium"),
                    target=str(item.get("target") or "?"),
                    description=str(item.get("description") or ""),
                    evidence=str(item.get("evidence") or ""),
                    source="semantic",
                ))

    # ============ helpers ============

    def _split_paragraphs(self, text: str) -> List[str]:
        return [p.strip() for p in text.split("\n\n") if p.strip()]

    def _make_preview(self, paragraph: str, length: int = 30) -> str:
        return paragraph[:length].replace("\n", " ") + ("..." if len(paragraph) > length else "")

    def _detect_characters(self, paragraph: str) -> List[Character]:
        """以 name + aliases 子字串比對偵測段落中提及的角色。
        以 name 為 key 去重，避免同一角色因多個 alias 命中重複。"""
        seen = {}
        for c in self.worldbook.characters:
            for n in c.all_names:
                if n and n in paragraph:
                    seen[c.name] = c
                    break
        return list(seen.values())

    def _extract_around(self, paragraph: str, needle: str, window: int = 20) -> str:
        i = paragraph.find(needle)
        if i < 0:
            return needle
        start = max(0, i - window)
        end = min(len(paragraph), i + len(needle) + window)
        snippet = paragraph[start:end].replace("\n", " ")
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(paragraph) else ""
        return f"{prefix}{snippet}{suffix}"

    def _parse_llm_json(self, raw: str) -> Optional[list]:
        """LLM 常回傳被 ``` 包起來的 JSON。盡量寬鬆地抓出第一個陣列。"""
        if not raw:
            return None
        # 去除 code fence
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
        # 直接解
        try:
            data = json.loads(cleaned)
            return data if isinstance(data, list) else None
        except json.JSONDecodeError:
            pass
        # 後備：抓第一個 [...] 區塊
        m = re.search(r"\[[\s\S]*\]", cleaned)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, list) else None
        except json.JSONDecodeError:
            return None
