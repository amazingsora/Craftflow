
import asyncio
from types import SimpleNamespace

import pytest

_H922 = ("masterpiece, best quality, absurdres, safe, 1girl, solo, ***REDACTED***, @***REDACTED***, "
         "child, petite, ultra detailed, high contrast, nude, pubic hair, nipples, red eyes, "
         "green eyes, heterochromia, brown hair, short hair, porcelain skin, full body")
_SEXUAL = {"nude", "pubic hair", "nipples"}


def _tags(s):
    return [t.strip() for t in s.split(",") if t.strip()]


@pytest.mark.parametrize("variant", ["(nude:1.2)", "completely nude", "NIPPLES", "nipple slip",
                                     "(no panties)", "cleavage", "lingerie"])
def test_minor_guard_strips_sexual_variants(variant):
    assert _tags(pos) == ["1girl", "child", "smile"]


def test_h922_real_prompt_is_cleaned():
    assert not _SEXUAL & set(_tags(pos))
    assert {"child", "petite", "brown hair", "full body"} <= set(_tags(pos))



def test_inject_prompts_is_last_gate():
    from app.services.ai.wf_node_ops import _inject_prompts
    wf = {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "3": {"class_type": "KSampler", "inputs": {"positive": ["1", 0], "negative": ["2", 0]}},
    }
    _inject_prompts(wf, "1girl, child, nude, smile", "worst quality")
    assert "nude" not in _tags(wf["1"]["inputs"]["text"])
    assert "nude" in _tags(wf["2"]["inputs"]["text"])


def test_llm_output_nsfw_filter_restored():
    from app.services.ai.prompt_engine.compiler import _sanitize_to_list
    assert _sanitize_to_list("1girl, nude, white dress", banned_set=set()) == ["1girl", "white dress"]


class _Db:
    def __init__(self, char):
        self.char = char

    def get(self, model, pk):
        return self.char if model.__name__ == "Character" and pk == self.char.id else None


def _char(**kw):
    base = dict(id=1, name="露碧娜", gender="female", age=12, height=152, core_traits="短褐色頭髮",
                outfit="深灰色戰鬥服", ai_prompt=None, art_style_id=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _patch_identity(monkeypatch, compile_fn):
    from app.services.ai import character_design_service as cds

    async def _no_focus(*a, **k):
        return None

    monkeypatch.setattr(cds.guardian, "request_focus", _no_focus)
    monkeypatch.setattr(cds, "prompt_cache_hit", lambda *a, **k: True)
    monkeypatch.setattr(cds, "compile_prompt", compile_fn)
    monkeypatch.setattr(cds, "Character", type("Character", (), {}))
    return cds


def test_identity_prompt_minor_is_guarded_and_has_no_name(monkeypatch):
    seen = []

    def fake_compile(text, **kw):
        seen.append(text)
        return "masterpiece, best quality, brown hair, short hair, nude, nipples", "worst quality"

    cds = _patch_identity(monkeypatch, fake_compile)
    res = asyncio.run(cds.build_identity_prompt(1, _Db(_char(ai_prompt="裸體"))))
    assert res["source"] == "compiled"
    tags = _tags(res["positive"])
    assert "1girl" in tags and "child" in tags and "brown hair" in tags
    assert not {"nude", "nipples"} & set(tags)
    assert all("露碧娜" not in t for t in seen), "名字不可送進 LLM（CN-038）"
    # 不含人設圖構圖段
    assert not {"full body", "front view", "simple background"} & set(tags)


def test_identity_prompt_fallback_zh_has_no_name(monkeypatch):
    def boom(text, **kw):
        raise RuntimeError("ollama down")

    cds = _patch_identity(monkeypatch, boom)
    res = asyncio.run(cds.build_identity_prompt(1, _Db(_char())))
    assert res["source"] == "fallback" and res["positive"] == ""
    assert "短褐色頭髮" in res["zh"] and "露碧娜" not in res["zh"]


def test_identity_route_and_character_id_field_exist():
    from main import app
    from app.schemas.art_generate import GenerateAsyncRequest
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/api/v1/characters/{character_id}/identity-prompt" in paths
    assert "character_id" in GenerateAsyncRequest.model_fields


def test_txt2img_uses_character_age(monkeypatch):
    """16 歲角色（無年齡標記 tag）經「以此角色生圖」帶 character_id → 仍被擋。"""
    from app.services.ai import workflow_builder as wb
    from app.schemas.art_generate import GenerateAsyncRequest
    monkeypatch.setattr(wb, "Character", type("Character", (), {}))
    monkeypatch.setattr(wb, "_load_workflow", lambda name: {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "3": {"class_type": "KSampler", "inputs": {"positive": ["1", 0], "negative": ["2", 0], "seed": 0}},
    })
    monkeypatch.setattr(wb.state, "get_lora", lambda: {})
    req = GenerateAsyncRequest(prompt="1girl, solo, nude, brown hair", negative_prompt="worst quality",
                               character_id=1)
    wf, _seed, _style, prompt, negative, _l = wb._build_txt2img(req, _Db(_char(age=16)))
    assert _tags(prompt) == ["1girl", "solo", "brown hair"]
    assert "nude" in _tags(negative)
    assert "nude" not in _tags(wf["1"]["inputs"]["text"])
