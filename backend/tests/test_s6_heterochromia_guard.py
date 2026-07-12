"""
S6（2026-07-12）：A5 異色瞳防護單獨重啟 + 方向瞳色 tag 擴充。
doc/2026-07-12_工作流提示詞優化規劃.md「八、第四輪」。

無異色瞳來源時，compile() 必須清除 LLM 幻覺的 heterochromia / odd eyes，
並（S6 擴充）連同幻覺的方向瞳色 tag "{color} eye (left/right)" 一併清除；
有異色瞳來源時，方向瞳色 tag 必須保留 / 依原文注入。

執行：cd backend && pytest tests/test_s6_heterochromia_guard.py
"""
from unittest.mock import patch

from app.services.ai import ollama_client
from app.services.ai.prompt_engine import compiler
from app.services.ai.prompt_engine.styles import PromptStyle


def _compile_with_mock(text, mock_raw):
    with patch.object(ollama_client, "generate", return_value=mock_raw):
        positive, _ = compiler.compile(text, style=PromptStyle.ILLUSTRIOUS)
    return positive.lower()


def test_s6_no_source_removes_hallucinated_heterochromia_and_directional_eyes():
    """無「異色瞳」來源 → heterochromia 與方向瞳色（本輪 golden eye (left) 漏網案）全清。"""
    pos = _compile_with_mock(
        "白髮金眼的少女",
        "1girl, solo, white hair, heterochromia, golden eye (left), blue eye (right)",
    )
    assert "heterochromia" not in pos
    assert "eye (left)" not in pos
    assert "eye (right)" not in pos
    assert "white hair" in pos  # 正常 tag 不受影響


def test_s6_with_source_preserves_directional_eyes():
    """有「異色瞳」來源 → 方向瞳色與 heterochromia 必須保留。"""
    pos = _compile_with_mock(
        "左眼為紅色，右眼為綠色的異色瞳少女",
        "1girl, solo, heterochromia, red eye (left), green eye (right)",
    )
    assert "heterochromia" in pos
    assert "red eye (left)" in pos
    assert "green eye (right)" in pos


def test_s6_zero_regression_plain_eyes_untouched():
    """無 heterochromia、無方向瞳色的普通輸出不受 S6 影響。"""
    pos = _compile_with_mock("白髮少女", "1girl, solo, white hair, golden eyes")
    assert "white hair" in pos
    assert "golden eyes" in pos
