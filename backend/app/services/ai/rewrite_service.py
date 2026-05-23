"""
Rewrite suggestion engine — calls Ollama to produce rewritten paragraph suggestions.
Never modifies source text; output is always written to a separate report.
Ported from tools/Craftflow/rewrite_engine.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.ai import ollama_client
from app.services.ai.prompt_loader import load_prompt


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
    instruction = load_prompt(f"rewrite/instruction_{mode}").strip()
    prompt = load_prompt("rewrite/rewrite", instruction=instruction, reason=reason, paragraph_text=paragraph_text)

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
