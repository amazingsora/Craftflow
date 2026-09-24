"""文字→生圖 AI 編譯（/art/compile-prompt）三個缺陷的回歸鎖（2026-09-24）。

使用者回報：「露碧娜，(左眼紅右眼綠的異色瞳)、短褐色頭髮,白皙皮膚」編出
  masterpiece, best quality, absurdres, ultra detailed, high contrast,
  red eyes, green eyes, lobitina, heterochromia, brown hair, short hair, porcelain skin
根因：
  1. 主體 tag（1girl, solo）被 banned_tags 剝除；人設圖由 gender_prefix 補回，文字→生圖沒有 → 永遠缺主體。
  2. endpoint 只吃 art_style 覆寫，沒吃 prompt_profiles.yml 家族配方 → Anima 無 safe、負向含官方禁用 score_*。
  3. 角色名被 LLM 音譯成拉丁字（lobitina）；CJK 過濾只擋得到中文，擋不到音譯。→ 模板加 NAMES 規則（機率性）。
"""
import asyncio

import pytest

from app.services.ai.prompt_engine import compiler
from app.services.ai.prompt_engine.styles import STYLE_CONFIG, PromptStyle

_USER_TEXT = "露碧娜，(左眼為紅色，右眼為綠色的異色瞳)、短褐色頭髮,白皙皮膚，"
# 依回報結果反推的 LLM 原始輸出（主體在前、名字音譯、眼色順序任意）
_LLM_OUT = "1girl, solo, lobitina, heterochromia, green eyes, red eyes, brown hair, short hair, pale skin"


@pytest.fixture
def fake_llm(monkeypatch):
    monkeypatch.setattr(compiler, "PROMPT_CACHE_TTL_SEC", 0)
    monkeypatch.setattr(compiler, "PROMPT_UPSAMPLE_ENABLED", False)
    monkeypatch.setattr(compiler.ollama_client, "generate", lambda *a, **k: _LLM_OUT)


def _body(positive: str, prefix: str) -> list[str]:
    assert positive.startswith(prefix)
    return [t.strip() for t in positive[len(prefix):].split(",") if t.strip()]


def test_keep_subject_puts_1girl_solo_first(fake_llm):
    cfg = STYLE_CONFIG[PromptStyle.ANIMA]
    pos, _ = compiler.compile(_USER_TEXT, style=PromptStyle.ANIMA, keep_subject=True)
    body = _body(pos, cfg.quality_prefix)
    assert body[:2] == ["1girl", "solo"], body
    assert {"heterochromia", "red eyes", "green eyes"} <= set(body)


def test_default_still_strips_subject_for_character_design_path(fake_llm):
    """人設圖路徑（keep_subject 預設 False）行為不變：主體由 gender_prefix 補，這裡不可出現。"""
    pos, _ = compiler.compile(_USER_TEXT, style=PromptStyle.ANIMA)
    tags = {t.strip() for t in pos.split(",")}
    assert "1girl" not in tags and "solo" not in tags


def test_compile_endpoint_uses_family_profile_and_keeps_subject(fake_llm, monkeypatch):
    from app.api import art_generate as ag
    from app.schemas.art_generate import CompilePromptRequest
    from app.services.ai import workflow_builder as wb

    async def _no_focus(*a, **k):
        return None

    monkeypatch.setattr(ag.guardian, "request_focus", _no_focus)
    monkeypatch.setattr(ag, "_resolve_style", lambda art_style: PromptStyle.ANIMA)
    monkeypatch.setattr(wb, "_detect_style", lambda wf: PromptStyle.ANIMA)
    monkeypatch.setattr(ag.state, "get_workflow", lambda: "AnyAnimaWorkflow.json")

    family = wb._load_prompt_profiles()["anima"]
    res = asyncio.run(ag.compile_prompt_endpoint(CompilePromptRequest(prompt=_USER_TEXT), db=_NoDb()))

    assert res["positive"].startswith(family["quality_prefix"]), res["positive"]
    body = _body(res["positive"], family["quality_prefix"])
    assert body[:2] == ["1girl", "solo"]
    # 負向＝家族配方，不是 STYLE_CONFIG 內建（內建含 Anima aesthetic 官方禁用的 score_*）
    assert res["negative"] == family["negative"]
    assert "score_1" not in res["negative"]


class _NoDb:
    def get(self, *a, **k):
        return None


def test_anima_template_has_name_rule_and_name_example():
    tpl = STYLE_CONFIG[PromptStyle.ANIMA].llm_template
    assert "NAMES:" in tpl
    # few-shot 至少一例「輸入含人名、輸出不含」
    assert "Input: 莉莉絲，" in tpl
    out_line = tpl.split("Input: 莉莉絲，", 1)[1].split("\n")[1]
    assert out_line.startswith("Output: 1girl") and "lilith" not in out_line.lower()
