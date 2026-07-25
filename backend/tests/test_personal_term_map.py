"""
P3（個人詞庫，LLM 翻譯前確定性替換）單元測試。
doc/2026-07-12_工作流提示詞優化規劃.md「七、提示詞精度條目」。

執行：cd backend && pytest tests/test_personal_term_map.py
"""
from unittest.mock import patch

from app.services.ai import ollama_client
from app.services.ai.prompt_engine import compiler, lexicon
from app.services.ai.prompt_engine.styles import PromptStyle


# ── lexicon.apply_personal_term_map（純函式）────────────────────────────────────

# P3.1（2026-07-12）：替換值前後補逗號分隔（", tag, "），杜絕相鄰兩詞替換後英文黏字。
# 以下斷言改為「英文 tag 出現、中文原文消失、無黏字」的不變量，避免綁死逗號/空白排版。

def test_apply_term_map_replaces_multiple_known_terms():
    out = lexicon.apply_personal_term_map("蔚藍檔案的角色，垂眼，馬靴")
    assert "blue archive" in out and "tareme" in out and "riding boots" in out
    assert "蔚藍檔案" not in out and "垂眼" not in out and "馬靴" not in out


def test_apply_term_map_basic_replacement():
    out = lexicon.apply_personal_term_map("蔚藍檔案的角色")
    assert out == ", blue archive, 的角色"


def test_apply_term_map_longest_match_wins():
    """「大小姐衣裝」要贏過「大小姐」——短詞不可先吃掉長詞的子字串。"""
    out = lexicon.apply_personal_term_map("穿著大小姐衣裝的少女")
    assert "ojou-sama" in out
    assert "大小姐" not in out
    assert "ojou-sama衣裝" not in out


def test_apply_term_map_standalone_short_term_still_matches():
    out = lexicon.apply_personal_term_map("她是大小姐")
    assert "ojou-sama" in out and "大小姐" not in out


def test_apply_term_map_p31_adjacent_terms_do_not_glue():
    """P3.1 核心回歸：相鄰兩詞替換不可黏字。
    「黑色長窄裙長度蓋過小腿」→ 窄裙=pencil skirt、長度蓋過小腿=long skirt，
    補分隔符前會黏成 'pencil skirtlong skirt'（skirtlong），LLM 只認出前者。"""
    out = lexicon.apply_personal_term_map("黑色長窄裙長度蓋過小腿")
    assert "pencil skirt" in out
    assert "long skirt" in out
    assert "skirtlong" not in out


def test_apply_term_map_unregistered_text_passthrough():
    out = lexicon.apply_personal_term_map("白髮金眼的少女")
    assert out == "白髮金眼的少女"


def test_apply_term_map_white_hair_fixed():
    """詞庫補條（第五輪）：白色頭髮 → white hair，杜絕 LLM 翻成 silver hair。"""
    out = lexicon.apply_personal_term_map("白色頭髮的少女")
    assert "white hair" in out and "白色頭髮" not in out


def test_apply_term_map_empty_text():
    assert lexicon.apply_personal_term_map("") == ""


def test_apply_term_map_missing_yml_falls_back_to_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(lexicon, "_PERSONAL_TERM_MAP_YML", tmp_path / "nope.yml")
    assert lexicon.apply_personal_term_map("蔚藍檔案") == "蔚藍檔案"


# ── compiler.compile() 接線：翻譯前替換 ─────────────────────────────────────────

def test_compile_applies_term_map_before_llm_call():
    """替換後的文字要出現在送進 Ollama 的 prompt 裡（翻譯「前」替換，非翻譯後修正）。"""
    captured = {}

    def _fake_generate(prompt, **kwargs):
        captured["prompt"] = prompt
        return "white hair, solo"

    with patch.object(ollama_client, "generate", side_effect=_fake_generate):
        compiler.compile("蔚藍檔案風格的白髮少女", style=PromptStyle.ILLUSTRIOUS)

    assert "blue archive" in captured["prompt"]
    assert "蔚藍檔案" not in captured["prompt"]


def test_compile_unregistered_text_is_zero_regression():
    """不含詞庫詞彙的輸入 → 送進 LLM 的 prompt 與改動前完全一致。"""
    captured = {}

    def _fake_generate(prompt, **kwargs):
        captured["prompt"] = prompt
        return "white hair, solo"

    with patch.object(ollama_client, "generate", side_effect=_fake_generate):
        compiler.compile("白髮少女", style=PromptStyle.ILLUSTRIOUS)

    assert "白髮少女" in captured["prompt"]
