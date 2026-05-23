from app.services.ai.prompt_engine.character_pipeline import CharacterIntent, run_pipeline
from app.services.ai.prompt_engine.styles import PromptStyle


def _fake_compile(prompt: str, **kwargs):
    # Return deterministic tag output for tests.
    return prompt, ""


def _run(intent: CharacterIntent, use_ai_prompt: bool = True):
    return run_pipeline(
        intent=intent,
        style=PromptStyle.SDXL,
        model="dummy-model",
        use_ai_prompt=use_ai_prompt,
        quality_prefix_override="",
        negative_override="",
        compile_prompt_fn=_fake_compile,
    )


def test_outfit_empty_adds_outfit_hallucination_blockers():
    out = _run(
        CharacterIntent(
            name="alice",
            core_traits="short hair",
            outfit=None,
            ai_prompt=None,
        ),
        use_ai_prompt=False,
    )
    assert "maid outfit" in out.negative
    assert "nurse outfit" in out.negative


def test_ai_prompt_high_priority_but_hard_outfit_survives():
    out = _run(
        CharacterIntent(
            name="bob",
            core_traits="",
            outfit="robe",
            ai_prompt="maid outfit, apron",
        ),
        use_ai_prompt=True,
    )
    assert "robe" in out.positive


def test_heterochromia_hard_tag_preserved():
    out = _run(
        CharacterIntent(
            name="eve",
            core_traits="heterochromia",
            ai_prompt=None,
        ),
        use_ai_prompt=False,
    )
    assert "heterochromia" in out.positive


def test_pipeline_emits_debug_payloads():
    out = _run(
        CharacterIntent(
            name="k",
            core_traits="silver hair",
            visual_traits="blue eyes",
            concept_images_count=2,
        ),
        use_ai_prompt=False,
    )
    assert isinstance(out.stage_a_json, dict)
    assert isinstance(out.conflict_decisions, list)
