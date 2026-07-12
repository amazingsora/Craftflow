"""
Lexicon — Vocabulary and patterns for trait extraction and tag classification.
"""
from __future__ import annotations
import re
from pathlib import Path

import yaml

# ── Color Mapping ─────────────────────────────────────────────────────────────

COLOR_MAP: dict[str, str] = {
    "白色": "white",   "白": "white",
    "金黃色": "blonde", "金黃": "blonde",
    "金色": "golden",  "金": "golden",
    "銀色": "silver",  "銀": "silver",
    "黑色": "black",   "黑": "black",
    "棕色": "brown",   "棕": "brown",   "茶色": "brown",   "褐色": "brown", "褐": "brown",
    "紅色": "red",     "紅": "red",
    "藍色": "blue",    "藍": "blue",
    "紫色": "purple",  "紫": "purple",
    "粉紅色": "pink",  "粉紅": "pink",  "粉色": "pink", "粉": "pink",
    "綠色": "green",   "綠": "green",
    "橘色": "orange",  "橘": "orange",
    "灰色": "grey",    "灰": "grey",
    "琥珀色": "amber", "琥珀": "amber",
}

_COLOR_ALTS = "|".join(re.escape(k) for k in sorted(COLOR_MAP, key=len, reverse=True))

# ── Extraction Patterns ────────────────────────────────────────────────────────

# 髮 covers: 頭髮 長髮 短髮 捲髮 直髮 金髮 銀髮 etc.
# Group 1: leading modifier (長/短)
# Group 2: color
# Group 3: hair keyword (頭髮/髮/...) which might also contain長/短
HAIR_RE = re.compile(rf"([長短])?({_COLOR_ALTS})?(長髮|短髮|頭髮|髮|毛髮|捲髮|直髮)")
EYE_RE  = re.compile(rf"({_COLOR_ALTS})(眼睛|瞳孔|眼|瞳)")

# ── Trait Mapping ─────────────────────────────────────────────────────────────

TRAIT_MAP: dict[str, str] = {
    "下垂眼": "drooping eyes, tareme",
    "垂眼": "drooping eyes, tareme",
    "貓眼": "cat eyes",
    "大小姐": "noble female, ojou-sama",
    "窄裙": "tight skirt",
    "溫柔": "gentle expression",
    "黑絲": "black thighhighs",
    "黑絲襪": "black thighhighs",
}

_TRAIT_ALTS = "|".join(re.escape(k) for k in sorted(TRAIT_MAP, key=len, reverse=True))
TRAIT_RE = re.compile(rf"({_TRAIT_ALTS})")

# ── Trait Sets for Cleaning & Conflict Removal ─────────────────────────────────

HAIR_COLORS = {
    "white hair", "black hair", "brown hair", "blonde hair", "golden hair",
    "silver hair", "red hair", "blue hair", "purple hair", "pink hair",
    "green hair", "orange hair", "grey hair", "gray hair", "amber hair",
}

HAIR_LENGTHS = {"short hair", "medium hair", "long hair", "very long hair"}

HAIR_STYLE_MAP: dict[str, str] = {
    "長髮": "long hair",
    "短髮": "short hair",
    "捲髮": "wavy hair",
    "直髮": "straight hair",
}

EYE_COLORS = {
    "white eyes", "black eyes", "brown eyes", "golden eyes", "silver eyes",
    "red eyes", "blue eyes", "purple eyes", "pink eyes", "green eyes",
    "orange eyes", "grey eyes", "gray eyes", "amber eyes",
}

# ── Personal Term Map（P3，2026-07-12）─────────────────────────────────────────
# LLM 翻譯前的確定性字串替換：中文原文子字串 → 英文 tag，直接進 LLM 輸入，降低特定
# 詞彙（角色名、專有名詞、易誤譯的服裝/神韻描述）被誤譯或幻覺的機率。管理於
# personal_term_map.yml；未建檔／解析失敗 → {}（這層機制完全不介入，零回歸）。
# 與上方 TRAIT_MAP（掛在已停用的 _inject_traits，LLM 翻譯「後」修正）是不同機制。

_PERSONAL_TERM_MAP_YML = Path("/app/backend/personal_term_map.yml")
if not _PERSONAL_TERM_MAP_YML.exists():
    _PERSONAL_TERM_MAP_YML = Path(__file__).resolve().parents[4] / "personal_term_map.yml"


def _load_personal_term_map() -> dict[str, str]:
    """讀 personal_term_map.yml。未建檔/解析失敗 → {}。不快取，比照
    checkpoint_styles.yml/prompt_profiles.yml 慣例，調參期改 yml 免重啟即生效。"""
    try:
        with open(_PERSONAL_TERM_MAP_YML, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("terms", {}) or {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def apply_personal_term_map(text: str) -> str:
    """套用個人詞庫：中文原文子字串 → 英文 tag。由長到短匹配（比照 _TRAIT_ALTS 慣例），
    避免短詞（如「大小姐」）先吃掉長詞（如「大小姐衣裝」）的子字串，導致長詞規則失效。
    未登錄詞彙或空詞庫時原樣回傳（零回歸）。

    P3.1（2026-07-12）：替換值前後補逗號分隔（", tag, "），杜絕相鄰兩詞替換後英文黏字。
    根因：「黑色長窄裙長度蓋過小腿」兩次替換後成 "黑色長pencil skirtlong skirt"，
    skirtlong 黏字使 LLM 只認出前者、丟棄 long skirt（裙長變短）。補分隔符後兩個
    英文 tag 各自獨立（", pencil skirt, , long skirt, "），交由 _sanitize_to_list 收整。"""
    terms = _load_personal_term_map()
    if not terms or not text:
        return text
    for zh in sorted(terms, key=len, reverse=True):
        if zh in text:
            text = text.replace(zh, f", {terms[zh]}, ")
    return text


# ── Tag Ordering Categories ────────────────────────────────────────────────────

TAG_CATEGORIES = {
    "subject": {
        "1girl", "1boy", "1woman", "1man", "2girls", "2boys", "solo", "multiple girls", "multiple boys",
        "male focus", "female focus",
    },
    "meta": {
        "source_anime", "source_furry", "source_cartoon", "monochrome", "greyscale", "comic", "sketch",
    },
}
