"""
P3（個人詞庫，LLM 翻譯前確定性替換）單元測試。
doc/2026-07-12_工作流提示詞優化規劃.md「七、提示詞精度條目」。

執行：cd backend && pytest tests/test_personal_term_map.py
"""
import re
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


# ── A3 P3-1（2026-08-22）：服裝關鍵詞召回 ──────────────────────────────────────
# D0-1 樣本矩陣實錘案例：tactical vest 時有時無（同輸入兩次編譯結果不同）。
# apply_personal_term_map 已把「戰術背心」→"tactical vest" 塞進 LLM 輸入文字，
# 但 LLM 仍可能漏譯——這裡鎖住「有塞進去、輸出卻沒有 → 補回」的召回行為。

def test_recall_dropped_outfit_terms_reinserts_missing_tag():
    out = compiler._recall_dropped_outfit_terms(
        ["1girl", "solo", "white hair"], "1girl, tactical vest, white hair"
    )
    assert "tactical vest" in out


def test_recall_dropped_outfit_terms_noop_when_already_present():
    """已存在時不重複附加。"""
    tags = ["1girl", "solo", "tactical vest"]
    out = compiler._recall_dropped_outfit_terms(tags, "1girl, tactical vest")
    assert out.count("tactical vest") == 1


def test_recall_dropped_outfit_terms_noop_when_not_in_source():
    """來源文字根本沒有該詞彙時不可誤補（只召回「本該在」的，不猜測）。"""
    tags = ["1girl", "solo", "white hair"]
    out = compiler._recall_dropped_outfit_terms(tags, "1girl, white hair")
    assert out == tags
    assert "tactical vest" not in out


def test_compile_recalls_dropped_tactical_vest():
    """端到端：compile() 輸入含「戰術背心」，LLM 模擬輸出漏掉 tactical vest，
    最終 positive 仍須補回（不是只在送進 LLM 前存在，輸出也要有）。"""

    def _fake_generate(prompt, **kwargs):
        # 模擬 LLM 收到 "tactical vest" 但翻譯時漏掉（D0-1 實測症狀）。
        return "1girl, solo, white hair"

    with patch.object(ollama_client, "generate", side_effect=_fake_generate):
        positive, _ = compiler.compile("戰術背心的白髮少女", style=PromptStyle.ILLUSTRIOUS)

    assert "tactical vest" in positive


def test_compile_flux_style_skips_tag_based_recall():
    """FLUX 走自然語言句子，非 tag 清單——召回機制不應介入（避免把 tag 硬塞進句子）。"""

    def _fake_generate(prompt, **kwargs):
        return "A girl with white hair standing outdoors."

    with patch.object(ollama_client, "generate", side_effect=_fake_generate):
        positive, _ = compiler.compile("戰術背心的白髮少女", style=PromptStyle.FLUX)

    assert "tactical vest" not in positive


# ── [CN-117]（2026-09-24）詞條前緊貼的修飾語併入替換值 ─────────────────────────
# 實錘：聖真希「黑色長窄裙長度蓋過小腿」→ P3.1 切成 "黑色長, pencil skirt, , long skirt"，
# 孤兒片語「黑色長」被 Anima 範例（黑色長髮 → black hair, long hair）配成 black hair，
# 最終 prompt 白髮角色同時帶 black hair，出圖變黑白雙色髮。

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def test_apply_term_map_folds_color_and_length_no_orphan():
    out = lexicon.apply_personal_term_map("黑色長窄裙長度蓋過小腿")
    assert "black long pencil skirt" in out
    assert "long skirt" in out
    # 負向不變量：修飾語不可被切成孤兒中文片語殘留在 LLM 輸入
    assert not _CJK_RE.search(out), out


def test_apply_term_map_real_outfit_field_has_no_orphan_modifier():
    """聖真希實際服裝欄整段：替換後不可殘留「黑色長」。"""
    out = lexicon.apply_personal_term_map("黑褲襪,大小姐衣裝,白襯衫,黑色長窄裙長度蓋過小腿,馬靴")
    assert "黑色長" not in out
    assert "black long pencil skirt" in out and "riding boots" in out


def test_apply_term_map_folds_shade_prefix():
    out = lexicon.apply_personal_term_map("深藍色窄裙")
    assert "dark blue pencil skirt" in out and not _CJK_RE.search(out)


def test_apply_term_map_length_not_folded_mid_word():
    """「隊長」的長是前一詞的詞尾，不可被當成 long 修飾語吃掉。"""
    out = lexicon.apply_personal_term_map("隊長大小姐")
    assert "隊長" in out
    assert "long ojou-sama" not in out and "ojou-sama" in out


def test_apply_term_map_length_folded_at_phrase_start():
    out = lexicon.apply_personal_term_map("白襯衫,短窄裙")
    assert "short pencil skirt" in out and "短" not in out


def test_recall_treats_modified_tag_as_present():
    """修飾語併入後 LLM 吐 black pencil skirt，召回不可再補一個重複的 pencil skirt。"""
    out = compiler._recall_dropped_outfit_terms(
        ["1girl", "black pencil skirt", "long skirt"], ", black long pencil skirt, , long skirt, "
    )
    assert "pencil skirt" not in out


def test_recall_still_reinserts_when_truly_missing():
    out = compiler._recall_dropped_outfit_terms(["1girl"], ", black long pencil skirt, ")
    assert "pencil skirt" in out


def test_compile_llm_input_has_no_orphan_modifier():
    """端到端：compile() 實際送進 LLM 的 prompt 不含孤兒片語「黑色長」。"""
    captured = {}

    def _fake_generate(prompt, **kwargs):
        captured["prompt"] = prompt
        return "1girl, solo, black pencil skirt, long skirt"

    with patch.object(ollama_client, "generate", side_effect=_fake_generate):
        positive, _ = compiler.compile("服裝設定：白襯衫,黑色長窄裙長度蓋過小腿", style=PromptStyle.ANIMA)

    # 模板 EXAMPLES 本身含「黑色長髮」，只檢查 [INPUT] 段
    llm_input = captured["prompt"].split("[INPUT]")[-1]
    assert "黑色長" not in llm_input
    assert "black long pencil skirt" in llm_input
    assert "black hair" not in positive
