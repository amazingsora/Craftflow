from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Callable

from app.services.ai import ollama_client
from app.services.ai.prompt_engine.styles import PromptStyle, STYLE_CONFIG

_TAG_SPLIT_RE = re.compile(r"[,\n]+")
_TAG_SAFE_RE = re.compile(r"^[a-z0-9 ()_\-]+$")
_EN_COLOR = r"(white|black|red|blue|green|purple|pink|brown|gray|grey|blonde|gold|silver)"
_HAIR_COLOR_RE = re.compile(rf"\b{_EN_COLOR}\s+hair\b")
_EYE_COLOR_RE = re.compile(rf"\b{_EN_COLOR}\s+eyes\b")
_SIDE_EYE_RE = re.compile(rf"\b{_EN_COLOR}\s+eye\s+\((left|right)\)\b")


@dataclass
class CharacterIntent:
    name: str
    gender: str | None = None
    age: int | None = None
    height: int | None = None
    core_traits: str | None = None
    outfit: str | None = None
    color: str | None = None
    expression: str | None = None
    ai_prompt: str | None = None
    visual_traits: str | None = None
    concept_images_count: int = 0
    all_flat_draft: bool = True
    ipa_enabled: bool = False
    vision_confidence: float = 0.0


@dataclass
class PipelineResult:
    positive: str
    negative: str
    ai_prompt_compiled: str = ""
    stage_a_raw: str = ""
    stage_a_json: dict = field(default_factory=dict)
    conflict_decisions: list[dict] = field(default_factory=list)
    removed_tags: list[str] = field(default_factory=list)
    hard_tags: list[str] = field(default_factory=list)
    soft_tags: list[str] = field(default_factory=list)


def _uniq(tags: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for t in tags:
        n = t.strip().lower()
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def _sanitize_tags(items: list[str]) -> list[str]:
    tags: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        for part in _TAG_SPLIT_RE.split(item):
            t = part.strip().lower()
            if not t:
                continue
            if len(t) > 64:
                continue
            if _TAG_SAFE_RE.match(t):
                tags.append(t)
    return _uniq(tags)


def _extract_tags_from_positive(positive: str, quality_prefix: str) -> list[str]:
    raw = [x.strip() for x in positive.split(",") if x.strip()]
    quality_tags = {q.strip().lower() for q in quality_prefix.split(",") if q.strip()}
    return _uniq([t.lower() for t in raw if t.lower() not in quality_tags])


def _json_or_none(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
    if text.startswith("["):
        return None
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        v = json.loads(m.group(0))
        return v if isinstance(v, dict) else None
    except json.JSONDecodeError:
        return None


def _stage_a_prompt(intent: CharacterIntent) -> str:
    return (
        "You are a strict tag planner for anime character generation.\n"
        "Return JSON only. No markdown. No explanation.\n"
        "Schema:\n"
        "{\n"
        '  "subject_tags": ["..."],\n'
        '  "appearance_tags": ["..."],\n'
        '  "outfit_tags": ["..."],\n'
        '  "mood_tags": ["..."],\n'
        '  "background_tags": ["..."],\n'
        '  "forbidden_tags": ["..."],\n'
        '  "notes": ["short machine-readable notes"]\n'
        "}\n"
        "Rules:\n"
        "1) Keep tags lowercase english SD tags.\n"
        "2) Do not invent concrete outfit/background details not present in input.\n"
        "3) If IPA enabled, treat visual hints as weaker than text constraints.\n"
        "4) When confidence is low, avoid hard visual claims.\n"
        "5) Preserve heterochromia left/right if given.\n"
        f"INPUT_JSON={json.dumps(asdict(intent), ensure_ascii=True)}"
    )


def _hard_constraints(intent: CharacterIntent) -> list[str]:
    hard: list[str] = []
    src = " ".join(
        x for x in [intent.core_traits or "", intent.outfit or "", intent.ai_prompt or ""] if x
    ).lower()

    # Keep outfit source explicit when user filled outfit.
    if intent.outfit and intent.outfit.strip():
        hard.extend(_sanitize_tags([intent.outfit]))

    if "heterochromia" in src:
        hard.append("heterochromia")

    return _uniq(hard)


def _remove_conflicts(base: list[str], incoming: list[str]) -> tuple[list[str], list[str], list[dict]]:
    removed: list[str] = []
    decisions: list[dict] = []
    out = list(base)

    def remove_with_reason(pred: Callable[[str], bool], reason: str) -> None:
        nonlocal out, removed, decisions
        kept: list[str] = []
        for tag in out:
            if pred(tag):
                removed.append(tag)
                decisions.append({"reason": reason, "removed": tag})
            else:
                kept.append(tag)
        out = kept

    for t in incoming:
        if _HAIR_COLOR_RE.search(t):
            remove_with_reason(lambda x: bool(_HAIR_COLOR_RE.search(x)), "hair_color_conflict")
        if _EYE_COLOR_RE.search(t):
            remove_with_reason(lambda x: bool(_EYE_COLOR_RE.search(x)), "eye_color_conflict")
        if _SIDE_EYE_RE.search(t):
            remove_with_reason(lambda x: bool(_EYE_COLOR_RE.search(x)), "heterochromia_conflict")
        out.append(t)

    return _uniq(out), _uniq(removed), decisions


def run_pipeline(
    intent: CharacterIntent,
    style: PromptStyle,
    model: str,
    use_ai_prompt: bool,
    quality_prefix_override: str | None = None,
    negative_override: str | None = None,
    compile_prompt_fn: Callable[..., tuple[str, str]] | None = None,
) -> PipelineResult:
    cfg = STYLE_CONFIG[style]
    quality_prefix = quality_prefix_override if quality_prefix_override is not None else cfg.quality_prefix
    negative = negative_override if negative_override is not None else cfg.negative

    stage_a_raw = ollama_client.generate(
        _stage_a_prompt(intent),
        model=model,
        options={"temperature": 0.1, "num_predict": 350},
    )
    parsed = _json_or_none(stage_a_raw) or {}
    subject = _sanitize_tags(parsed.get("subject_tags", []))
    appearance = _sanitize_tags(parsed.get("appearance_tags", []))
    outfit = _sanitize_tags(parsed.get("outfit_tags", []))
    mood = _sanitize_tags(parsed.get("mood_tags", []))
    bg = _sanitize_tags(parsed.get("background_tags", []))
    forbidden = _sanitize_tags(parsed.get("forbidden_tags", []))

    stage_soft = _uniq(subject + appearance + outfit + mood + bg)
    hard = _hard_constraints(intent)

    ai_tags: list[str] = []
    ai_compiled = ""
    if use_ai_prompt and intent.ai_prompt and intent.ai_prompt.strip() and compile_prompt_fn:
        ai_compiled, _ = compile_prompt_fn(
            intent.ai_prompt.strip(),
            style=style,
            model=model,
            quality_prefix_override="",
            negative_override="",
        )
        ai_tags = _extract_tags_from_positive(ai_compiled, quality_prefix="")

    # AI prompt is high priority, but hard-field conflicts must be overwritten by hard tags.
    merged, removed1, decisions1 = _remove_conflicts([], ai_tags + stage_soft)
    merged, removed2, decisions2 = _remove_conflicts(merged, hard)
    removed = _uniq(removed1 + removed2 + forbidden)
    merged = [t for t in merged if t not in forbidden]

    # Hallucination firewall for unspecified outfit/background.
    extra_negative = [
        "detailed background",
        "complex background",
        "scenery",
        "landscape",
        "buildings",
        "environment",
    ]
    if not (intent.outfit and intent.outfit.strip()):
        extra_negative.extend(
            [
                "maid outfit",
                "apron",
                "nurse outfit",
                "police uniform",
                "sailor uniform",
                "armor",
                "wedding dress",
            ]
        )

    positive_body = ", ".join(merged)
    positive = f"{quality_prefix}, {positive_body}" if quality_prefix and positive_body else (quality_prefix or positive_body)
    full_negative = ", ".join([x for x in [negative] + extra_negative if x]).strip(", ")

    return PipelineResult(
        positive=positive,
        negative=full_negative,
        ai_prompt_compiled=ai_compiled,
        stage_a_raw=stage_a_raw,
        stage_a_json=parsed,
        conflict_decisions=decisions1 + decisions2,
        removed_tags=removed,
        hard_tags=hard,
        soft_tags=stage_soft,
    )
