"""
Consistency analysis — checks chapter text against character settings stored in DB.

Two phases:
  1. Surface scan (rule-based, always runs): forbidden_actions + name/alias detection
  2. Semantic scan (LLM, opt-in): sends paragraph + character profile to Ollama

Ported from tools/Craftflow/core/consistency_analyzer.py.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from app.services.ai import ollama_client


@dataclass
class ConsistencyIssue:
    paragraph_index: int
    type: str        # character_behavior | character_voice | forbidden_keyword
    severity: str    # high | medium | low
    target: str      # character name
    description: str
    evidence: str
    source: str = "surface"  # surface | semantic


@dataclass
class ParagraphConsistency:
    index: int
    preview: str
    mentioned_characters: list[str] = field(default_factory=list)
    issues: list[ConsistencyIssue] = field(default_factory=list)


@dataclass
class CharacterProfile:
    name: str
    aliases: list[str]
    forbidden_actions: list[str]
    behavior_rules: Optional[str]
    voice_style: Optional[str]

    @property
    def all_names(self) -> list[str]:
        return [self.name] + (self.aliases or [])


def analyze(
    text: str,
    characters: list[CharacterProfile],
    enable_semantic: bool = False,
    model: str = ollama_client.DEFAULT_TEXT_MODEL,
    max_semantic_paragraphs: int = 20,
) -> tuple[list[ParagraphConsistency], list[str]]:
    """
    Returns (results, warnings).
    """
    warnings: list[str] = []
    if not characters:
        return [], warnings

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    results: list[ParagraphConsistency] = []

    for idx, para in enumerate(paragraphs, start=1):
        mentioned = _detect_characters(para, characters)
        pc = ParagraphConsistency(
            index=idx,
            preview=para[:30].replace("\n", " ") + ("..." if len(para) > 30 else ""),
            mentioned_characters=[c.name for c in mentioned],
        )
        pc.issues.extend(_surface_scan(idx, para, mentioned))
        results.append(pc)

    if enable_semantic:
        scanned = 0
        for pc, para in zip(results, paragraphs):
            if scanned >= max_semantic_paragraphs:
                warnings.append(f"Semantic scan capped at {max_semantic_paragraphs} paragraphs.")
                break
            chars = [c for c in characters if c.name in pc.mentioned_characters]
            if not chars:
                continue
            issues, w = _semantic_scan_paragraph(pc.index, para, chars, model)
            pc.issues.extend(issues)
            warnings.extend(w)
            scanned += 1

    return results, warnings


def _detect_characters(paragraph: str, characters: list[CharacterProfile]) -> list[CharacterProfile]:
    seen: dict[str, CharacterProfile] = {}
    for c in characters:
        for name in c.all_names:
            if name and name in paragraph:
                seen[c.name] = c
                break
    return list(seen.values())


def _surface_scan(idx: int, paragraph: str, mentioned: list[CharacterProfile]) -> list[ConsistencyIssue]:
    issues: list[ConsistencyIssue] = []
    for c in mentioned:
        for action in (c.forbidden_actions or []):
            if action and action in paragraph:
                i = paragraph.find(action)
                start, end = max(0, i - 20), min(len(paragraph), i + len(action) + 20)
                evidence = ("..." if start > 0 else "") + paragraph[start:end] + ("..." if end < len(paragraph) else "")
                issues.append(ConsistencyIssue(
                    paragraph_index=idx,
                    type="character_behavior",
                    severity="high",
                    target=c.name,
                    description=f"Forbidden action keyword: '{action}'",
                    evidence=evidence,
                    source="surface",
                ))
    return issues


def _semantic_scan_paragraph(
    idx: int,
    paragraph: str,
    characters: list[CharacterProfile],
    model: str,
) -> tuple[list[ConsistencyIssue], list[str]]:
    warnings: list[str] = []
    char_desc = "\n".join(
        f"- {c.name}: behavior_rules={c.behavior_rules!r}, voice_style={c.voice_style!r}"
        for c in characters
    )
    prompt = f"""You are a consistency checker for creative writing.

Characters in this paragraph:
{char_desc}

Paragraph:
{paragraph}

Check if the paragraph violates any character settings above.
Return a JSON array of issues. Each issue: {{"type": "character_behavior"|"character_voice", "severity": "high"|"medium"|"low", "target": "<name>", "description": "<what is wrong>", "evidence": "<quote from paragraph>"}}
Return [] if no issues.
Return ONLY the JSON array, nothing else."""

    raw = ollama_client.generate(prompt, model=model)
    if raw.startswith("["):
        pass  # already unavailable message
    parsed = _parse_json(raw)
    if parsed is None:
        warnings.append(f"Paragraph {idx}: semantic scan returned invalid JSON.")
        return [], warnings

    issues = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        issues.append(ConsistencyIssue(
            paragraph_index=idx,
            type=str(item.get("type", "character_behavior")),
            severity=str(item.get("severity", "medium")),
            target=str(item.get("target", "?")),
            description=str(item.get("description", "")),
            evidence=str(item.get("evidence", "")),
            source="semantic",
        ))
    return issues, warnings


def _parse_json(raw: str) -> Optional[list]:
    if not raw:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, list) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\[[\s\S]*\]", cleaned)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, list) else None
    except json.JSONDecodeError:
        return None
