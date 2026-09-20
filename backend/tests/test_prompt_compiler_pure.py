"""
compiler._sanitize_to_list 純函式單測（P2，2026-07-02 規劃）。
不需要 Ollama；只測 compile() 拆出的確定性清洗邏輯。
執行：cd backend && pytest tests/test_prompt_compiler_pure.py
"""
from app.services.ai.prompt_engine.compiler import _sanitize_to_list


def test_sanitize_basic_split_and_strip():
    out = _sanitize_to_list("1girl, solo, white hair", banned_set=set())
    assert out == ["1girl", "solo", "white hair"]


def test_sanitize_dedup_case_insensitive():
    out = _sanitize_to_list("white hair, White Hair, solo", banned_set=set())
    assert out == ["white hair", "solo"]


def test_sanitize_banned_tags_removed():
    out = _sanitize_to_list("1girl, masterpiece, solo", banned_set={"masterpiece"})
    assert out == ["1girl", "solo"]


def test_sanitize_drops_cjk_leak():
    out = _sanitize_to_list("white hair, 角色名稱, solo", banned_set=set())
    assert out == ["white hair", "solo"]


def test_sanitize_quoted_meta_only_dropped_when_quote_not_symmetric():
    """
    已知邊界情況：t_clean.strip('."\\'') 會把「頭尾都是雙引號」的整段一次剝除，
    使內部殘留的單引號（如 let's）在剝除後不再含 '"'，因此 `if '"' in t_clean`
    偵測不到、不會被丟棄。這不是本次 P0-P3 範圍要修的 bug，這裡先固定住現況，
    未來要收斂這個漏洞時，此測試會提醒需要同步更新（對應 golden case cjk_and_meta_leak）。
    """
    out = _sanitize_to_list('white hair, "but let\'s stick to input", solo', banned_set=set())
    assert out == ["white hair", "but let's stick to input", "solo"]


def test_sanitize_drops_unbalanced_quote_meta_commentary():
    out = _sanitize_to_list('white hair, but let\'s stick to "input", solo', banned_set=set())
    assert out == ["white hair", "solo"]


def test_sanitize_drops_meta_label_colon():
    out = _sanitize_to_list("white hair, Conflict Resolution:, solo", banned_set=set())
    assert out == ["white hair", "solo"]


def test_sanitize_drops_alt_paren_explanation():
    out = _sanitize_to_list("white hair, (or maybe boots), solo", banned_set=set())
    assert "(or maybe boots)" not in out
    assert "white hair" in out and "solo" in out


def test_sanitize_keeps_short_direction_paren():
    out = _sanitize_to_list("red eye (left), green eye (right)", banned_set=set())
    assert out == ["red eye (left)", "green eye (right)"]


def test_sanitize_strips_inline_dash_reasoning():
    out = _sanitize_to_list("reasoning - wait actually blue", banned_set=set())
    assert out == ["reasoning"]


def test_sanitize_drops_numeric_age_phrase():
    out = _sanitize_to_list("1girl, 10 years old, child", banned_set=set())
    assert out == ["1girl", "child"]


def test_sanitize_drops_overlong_tag():
    long_tag = "this is a very long inference sentence that leaks reasoning text far beyond the eighty character limit"
    out = _sanitize_to_list(f"white hair, {long_tag}, solo", banned_set=set())
    assert out == ["white hair", "solo"]


def test_sanitize_takes_first_slash_alternative():
    out = _sanitize_to_list("shoes/boots, solo", banned_set=set())
    assert out == ["shoes", "solo"]


def test_sanitize_empty_string_returns_empty_list():
    assert _sanitize_to_list("", banned_set=set()) == []


# ── S9 NSFW 硬護欄（2026-07-13）────────────────────────────────────────────────

def test_sanitize_drops_nsfw_tags():
    out = _sanitize_to_list(
        "1girl, solo, nude, nipples, pubic hair, white dress, topless",
        banned_set=set(),
    )
    assert out == ["1girl", "solo", "white dress"]


def test_sanitize_nsfw_case_insensitive_and_weighted():
    out = _sanitize_to_list("1girl, (Nude:1.2), NIPPLES, solo", banned_set=set())
    assert out == ["1girl", "solo"]


# ── S7.1 線稿詞 regex（2026-07-13，含即丟，涵蓋舊枚舉＋變體）──────────────────

def test_sanitize_drops_lineart_artifact_variants():
    out = _sanitize_to_list(
        "1girl, colorless eyes, line art style skin, no iris detail, "
        "uncolored, pencil sketch, achromatic clothing, blue dress",
        banned_set=set(),
    )
    assert out == ["1girl", "blue dress"]


def test_sanitize_lineart_regex_keeps_legit_tags():
    """常見合法 tag 不被線稿 regex 誤傷（no iris/colorless 才丟，art/color 本身不丟）。"""
    out = _sanitize_to_list("1girl, blue eyes, colorful dress, fine art background", banned_set=set())
    assert out == ["1girl", "blue eyes", "colorful dress", "fine art background"]


# ── SYNC-002 B5'（2026-09-15）：眼色 tag 判定 ─────────────────────────────────
# 原實作白名單比對 lexicon.COLOR_MAP.values()，不在顏色表裡的眼色描述全部漏過去。
# 實際洩漏（generation_history id>=560）：pale eyes 15 / light colored eyes 9 /
# light eyes 5 / pale purple eyes 2 = 31 次，全與權威雙色並存 → 異色瞳身分保真被稀釋。
# 改成反向判定後，這組測試同時鎖「該清的有清」與「不該清的沒被誤殺」。
import pytest

from app.services.ai.prompt_engine.compiler import _is_eye_color_tag


@pytest.mark.parametrize("tag", [
    "pale eyes",            # 原正則完全不匹配 → 主要洩漏源（15 次）
    "light colored eyes",   # 三個詞，Gemini 提議的 \w+\s+eyes 也漏（9 次）
    "light eyes",
    "pale purple eyes",
    "red eyes", "green eyes", "golden eyes",   # 標準色：清掉後由 wanted 重新前置
    "(red eyes)",           # 帶權重括號
    "RED EYES",             # 大小寫
    "milky eyes",           # 顏色表沒有的新怪色 → 反向判定自動涵蓋
])
def test_is_eye_color_tag_true(tag):
    assert _is_eye_color_tag(tag) is True


@pytest.mark.parametrize("tag", [
    "big eyes", "thin eyes", "narrow eyes", "droopy eyes",  # 眼型，誤殺會失去角色特徵
    "closed eyes", "half-closed eyes",                      # 表情
    "glowing eyes", "sparkling eyes", "detailed eyes",      # 質感
    "slender eye shape",   # 不以 eye(s) 結尾
    "heterochromia",       # 不是眼色 tag
    "eyes",                # 沒有修飾語
    "brown hair",          # 完全無關
])
def test_is_eye_color_tag_false(tag):
    assert _is_eye_color_tag(tag) is False
