"""
P1 (workflow 級 prompt profile) + P2 (banned_tags 權重語法) 單元測試。
doc/2026-07-12_工作流提示詞優化規劃.md 開發條目。

執行：cd backend && pytest tests/test_prompt_profile_p1_p2.py
"""
from unittest.mock import patch

from app.services.ai import ollama_client
from app.services.ai.prompt_engine import compiler
from app.services.ai.prompt_engine.styles import PromptStyle, StyleConfig


# ── P2: _sync_banned_tags 權重語法 ──────────────────────────────────────────────

def test_sync_banned_tags_expands_weight_group():
    """(highres, absurdres, very aesthetic:0.8) 群組不可被逗號拆爛成破碎字串。"""
    cfg = StyleConfig(
        quality_prefix="masterpiece, best quality, (newest:0.6), (highres, absurdres, very aesthetic:0.8)",
        negative="",
        banned_tags=set(),
        llm_template="{prompt}",
    )
    assert cfg.banned_tags == {
        "masterpiece", "best quality", "newest", "highres", "absurdres", "very aesthetic",
    }
    # 破碎字串不可殘留
    assert "(highres" not in cfg.banned_tags
    assert "very aesthetic:0.8)" not in cfg.banned_tags


def test_sync_banned_tags_plain_prefix_unchanged():
    """無權重語法時行為不變（既有 STYLE_CONFIG 全部走這條路，零回歸）。"""
    cfg = StyleConfig(
        quality_prefix="masterpiece, best quality, absurdres",
        negative="",
        banned_tags=set(),
        llm_template="{prompt}",
    )
    assert cfg.banned_tags == {"masterpiece", "best quality", "absurdres"}


# ── P1: compile() quality_suffix_override ──────────────────────────────────────

def test_compile_quality_suffix_appended_after_body():
    # 注意：ILLUSTRIOUS banned_tags 含 _SUBJECT_COUNT_TAGS（1girl/solo 等）＋ quality 詞，
    # mock raw 需避開這些詞，否則會被 sanitizer 濾掉，看不出 quality_suffix 的接續行為。
    with patch.object(ollama_client, "generate", return_value="white hair, blue eyes"):
        positive, _ = compiler.compile(
            "白髮少女",
            style=PromptStyle.ILLUSTRIOUS,
            quality_prefix_override="masterpiece, best quality, absurdres",
            quality_suffix_override="(pixiv:0.6)",
        )
    assert positive == "masterpiece, best quality, absurdres, white hair, blue eyes, (pixiv:0.6)"


def test_compile_no_quality_suffix_is_noop():
    """未設定 quality_suffix_override（多數 workflow 現況）→ 輸出與改動前一致。"""
    with patch.object(ollama_client, "generate", return_value="white hair, blue eyes"):
        positive, _ = compiler.compile(
            "白髮少女",
            style=PromptStyle.ILLUSTRIOUS,
            quality_prefix_override="masterpiece, best quality, absurdres",
        )
    assert positive == "masterpiece, best quality, absurdres, white hair, blue eyes"


# ── P1.1: compile() 動態 banned（override tag 不在 family 靜態 banned_tags 內）───────

def test_compile_dynamic_banned_dedupes_override_tag_not_in_static_set():
    """"very aesthetic" 不在 ILLUSTRIOUS 靜態 quality_prefix/banned_tags 內（該家族的
    quality_prefix 是 "masterpiece, best quality, amazing quality, absurdres"）。
    若 workflow profile 的 quality_prefix_override 帶了它、LLM 又重複吐出，P1.1 前
    config.banned_tags 攔不住，會在 body 裡重複一次；P1.1 後應被動態 banned 剝除。"""
    with patch.object(ollama_client, "generate", return_value="very aesthetic, white hair"):
        positive, _ = compiler.compile(
            "白髮少女",
            style=PromptStyle.ILLUSTRIOUS,
            quality_prefix_override="masterpiece, best quality, very aesthetic",
        )
    assert positive == "masterpiece, best quality, very aesthetic, white hair"
    assert positive.count("very aesthetic") == 1


def test_compile_dynamic_banned_handles_weight_syntax_in_override():
    """override 本身帶權重語法（如 "(very aesthetic:0.8)"）也要能展開後正確去重。"""
    with patch.object(ollama_client, "generate", return_value="very aesthetic, white hair"):
        positive, _ = compiler.compile(
            "白髮少女",
            style=PromptStyle.ILLUSTRIOUS,
            quality_prefix_override="masterpiece, best quality, (very aesthetic:0.8)",
        )
    assert positive.count("very aesthetic") == 1


def test_compile_no_override_dynamic_banned_is_noop():
    """無 override（多數呼叫路徑現況）→ 動態 banned 與 config.banned_tags 完全相同，零回歸。"""
    with patch.object(ollama_client, "generate", return_value="amazing quality, white hair"):
        positive, _ = compiler.compile("白髮少女", style=PromptStyle.ILLUSTRIOUS)
    # "amazing quality" 是 ILLUSTRIOUS 家族靜態 quality_prefix 的一部分 → 本就會被
    # config.banned_tags 擋掉（LLM 重複吐出的那份被濾掉），行為與改動前一致。
    assert positive == "masterpiece, best quality, amazing quality, absurdres, white hair"


# ── R4: compile() negative_extra_override（補充語義，附加不取代）─────────────────

def test_compile_negative_extra_appends_after_negative_override():
    """negative（取代）＋ negative_extra（補充）同時登錄：extra 接在被取代後的 negative 之後。"""
    with patch.object(ollama_client, "generate", return_value="white hair"):
        _, negative = compiler.compile(
            "白髮少女",
            style=PromptStyle.ILLUSTRIOUS,
            negative_override="worst quality, low quality",
            negative_extra_override="extra artifact, unwanted tag",
        )
    assert negative == "worst quality, low quality, extra artifact, unwanted tag"


def test_compile_negative_extra_appends_to_family_negative_when_no_override():
    """只登錄 negative_extra：family 預設 negative 主體保留，extra 附加於尾（非取代）。"""
    with patch.object(ollama_client, "generate", return_value="white hair"):
        _, negative = compiler.compile(
            "白髮少女",
            style=PromptStyle.ILLUSTRIOUS,
            negative_extra_override="my extra neg tag",
        )
    assert negative.endswith("my extra neg tag")
    # family 主體未被取代 → extra 之前仍有既有內容
    assert negative != "my extra neg tag"
    assert ", my extra neg tag" in negative


def test_compile_no_negative_extra_is_noop():
    """未設定 negative_extra（多數呼叫路徑現況）→ negative 與改動前一致，零回歸。"""
    with patch.object(ollama_client, "generate", return_value="white hair"):
        _, negative = compiler.compile(
            "白髮少女",
            style=PromptStyle.ILLUSTRIOUS,
            negative_override="worst quality, low quality",
        )
    assert negative == "worst quality, low quality"
