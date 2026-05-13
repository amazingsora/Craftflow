"""
Rewrite suggestion engine — calls Ollama to produce rewritten paragraph suggestions.
Never modifies source text; output is always written to a separate report.
Ported from tools/Craftflow/rewrite_engine.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.ai import ollama_client


@dataclass
class RewriteSuggestion:
    paragraph_index: int
    original: str
    suggestion: str
    reason: str


def rewrite(
    paragraph_text: str,
    reason: str,
    mode: str = "gentle",
    model: str = ollama_client.DEFAULT_TEXT_MODEL,
) -> str:
    if mode == "gentle":
        instruction = (
            "Lightly revise the paragraph to improve rhythm and clarity. "
            "Preserve the author's voice and structure. Avoid major restructuring."
        )
    else:
        instruction = (
            "Rewrite the paragraph to significantly improve rhythm, flow, and impact. "
            "You may restructure sentences and enhance stylistic expression "
            "while preserving original meaning."
        )

    prompt = f"""You are a rewriting assistant.

RULES:
- Output ONLY the rewritten paragraph.
- No introductions, no explanations, no quotation marks, no extra text.
- The rewritten paragraph MUST be in the same language as the original.

Instruction: {instruction}
Reason: {reason}

Paragraph:
{paragraph_text}

Rewritten paragraph:"""

    return ollama_client.generate(prompt, model=model).strip()


def batch_rewrite(
    paragraphs: list[tuple[int, str, str]],  # (index, text, reason)
    mode: str = "gentle",
    model: str = ollama_client.DEFAULT_TEXT_MODEL,
) -> list[RewriteSuggestion]:
    results = []
    for idx, text, reason in paragraphs:
        suggestion = rewrite(text, reason, mode=mode, model=model)
        results.append(RewriteSuggestion(
            paragraph_index=idx,
            original=text,
            suggestion=suggestion,
            reason=reason,
        ))
    return results
