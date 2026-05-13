# tools/Craftflow/prompts/consistency_prompt_builder.py
"""
Consistency 語意檢查的 Prompt 建構器。

設計重點：
- 輸出嚴格要求為 JSON 陣列，方便後段解析。
- 不要求 LLM 改寫，只要求它「指認違規」與「給出證據」。
- 中英分流，遵守原文語言。
"""

import json
from typing import List
from core.worldbook_loader import Character, WorldRules


class ConsistencyPromptBuilder:

    @staticmethod
    def build(
        paragraph: str,
        characters_in_scope: List[Character],
        worlds: List[WorldRules],
        language: str = "zh",
    ) -> str:
        char_block = ConsistencyPromptBuilder._format_characters(characters_in_scope)
        world_block = ConsistencyPromptBuilder._format_worlds(worlds)

        if language == "zh":
            return f"""
你是一名創作一致性檢查員。
你的任務是：根據下面提供的「角色設定」與「世界規則」，檢查段落內容是否有違反設定的地方。

判斷原則：
- 只指認「明確違反」或「強烈衝突」的點，不要對風格、敘事節奏發表意見。
- 如果段落沒有問題，回傳空陣列 []。
- 不要修改段落、不要建議改寫、不要解釋。
- 只輸出 JSON，不要附加任何前言、結語或 Markdown code fence。

輸出格式（JSON 陣列）：
[
  {{
    "type": "character_behavior" | "character_voice" | "world_rule",
    "severity": "high" | "medium" | "low",
    "target": "<角色名稱或世界規則名稱>",
    "description": "<簡短描述衝突點>",
    "evidence": "<段落中支持此判斷的原文片段>"
  }}
]

角色設定：
{char_block}

世界規則：
{world_block}

待檢段落：
{paragraph}

JSON 輸出：
"""
        else:
            return f"""
You are a fiction consistency checker.
Given the character definitions and world rules below, identify clear contradictions in the paragraph.

Rules:
- Only flag explicit conflicts. Do not comment on style or pacing.
- If the paragraph is consistent, return an empty array [].
- Do not rewrite. Do not explain.
- Output JSON only. No preamble, no code fences.

Output format (JSON array):
[
  {{
    "type": "character_behavior" | "character_voice" | "world_rule",
    "severity": "high" | "medium" | "low",
    "target": "<character name or world rule name>",
    "description": "<short description of the conflict>",
    "evidence": "<exact text from the paragraph that supports the finding>"
  }}
]

Character definitions:
{char_block}

World rules:
{world_block}

Paragraph to check:
{paragraph}

JSON output:
"""

    @staticmethod
    def _format_characters(chars: List[Character]) -> str:
        if not chars:
            return "(none)"
        out = []
        for c in chars:
            out.append(json.dumps({
                "name": c.name,
                "aliases": c.aliases,
                "core_traits": c.core_traits,
                "behavior_rules": c.behavior_rules,
                "forbidden_actions": c.forbidden_actions,
                "voice_style": c.voice_style,
            }, ensure_ascii=False, indent=2))
        return "\n".join(out)

    @staticmethod
    def _format_worlds(worlds: List[WorldRules]) -> str:
        if not worlds:
            return "(none)"
        out = []
        for w in worlds:
            out.append(json.dumps({
                "name": w.name,
                "hard_rules": w.hard_rules,
                "soft_rules": w.soft_rules,
                "forbidden_keywords": w.forbidden_keywords,
            }, ensure_ascii=False, indent=2))
        return "\n".join(out)
