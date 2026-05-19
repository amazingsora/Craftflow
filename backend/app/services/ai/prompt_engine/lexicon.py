"""
Lexicon — Vocabulary and patterns for trait extraction and tag classification.
"""
from __future__ import annotations
import re

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

# ── Trait Sets for Cleaning & Conflict Removal ─────────────────────────────────

HAIR_COLORS = {
    "white hair", "black hair", "brown hair", "blonde hair", "golden hair",
    "silver hair", "red hair", "blue hair", "purple hair", "pink hair",
    "green hair", "orange hair", "grey hair", "gray hair", "amber hair",
}

HAIR_LENGTHS = {"short hair", "medium hair", "long hair", "very long hair"}

EYE_COLORS = {
    "white eyes", "black eyes", "brown eyes", "golden eyes", "silver eyes",
    "red eyes", "blue eyes", "purple eyes", "pink eyes", "green eyes",
    "orange eyes", "grey eyes", "gray eyes", "amber eyes",
}

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
