# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
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

# Groups: 1＝前置長短修飾、2＝顏色、3＝髮字關鍵詞（頭髮／髮…）
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

HAIR_STYLE_MAP: dict[str, str] = {
    "長髮": "long hair",
    "短髮": "short hair",
    "捲髮": "wavy hair",
    "直髮": "straight hair",
}

# [CN-033] Personal Term Map：LLM 翻譯「前」的確定性替換，與已停用的 TRAIT_MAP 是不同機制

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


def personal_term_map_tags() -> list[str]:
    """個人詞庫所有英文 tag 值（逗號展開），供 compiler 召回 LLM 漏掉的詞。"""
    terms = _load_personal_term_map()
    tags: list[str] = []
    for v in terms.values():
        tags.extend(t.strip() for t in v.split(",") if t.strip())
    return tags


# [CN-117] 詞條前緊貼的顏色／長短修飾語併入替換值；否則切剩的「黑色長」被 LLM 配成 black hair, long hair
_LENGTH_MODIFIER_MAP: dict[str, str] = {"長": "long", "短": "short"}
_SHADE_MODIFIER_MAP: dict[str, str] = {"深": "dark", "淺": "light"}   # 只在後接顏色時生效（深藍色）
# 單獨的「長／短」（前面沒有顏色）只有在片語開頭才視為修飾語，避免吃掉「隊長」「團長」的尾字
_MODIFIER_BOUNDARY = set(",，、;；:：。.!！?？()（）[]「」 \t\r\n")


def _fold_modifiers(match: re.Match, value: str) -> str:
    """把 match 到的深淺／顏色／長短修飾語翻成英文，前置到替換值的第一個 tag。"""
    shade_zh, color_zh, length_zh = match.group("shade"), match.group("color"), match.group("length")
    kept_zh = ""
    if length_zh and not color_zh:
        start = match.start("length")
        if start > 0 and match.string[start - 1] not in _MODIFIER_BOUNDARY:
            kept_zh, length_zh = length_zh, None   # 前一字的詞尾（隊長），原樣留在中文側
    mods = [w for w in (_SHADE_MODIFIER_MAP.get(shade_zh or ""), COLOR_MAP.get(color_zh or ""),
                        _LENGTH_MODIFIER_MAP.get(length_zh or "")) if w]
    if mods:
        head, sep, rest = value.partition(",")
        value = f"{' '.join(mods)} {head.strip()}{sep}{rest}"
    return f"{kept_zh}, {value}, "


def apply_personal_term_map(text: str) -> str:
    """套用個人詞庫：中文子字串 → 英文 tag，由長到短匹配（避免短詞吃掉長詞）。
    替換值前後補逗號防黏字；[CN-117] 緊貼的顏色＋長短修飾一併併入同一 tag。"""
    terms = _load_personal_term_map()
    if not terms or not text:
        return text
    for zh in sorted(terms, key=len, reverse=True):
        if zh in text:
            pattern = re.compile(
                rf"(?:(?P<shade>[深淺])?(?P<color>{_COLOR_ALTS}))?(?P<length>[長短])?{re.escape(zh)}"
            )
            text = pattern.sub(lambda m, v=terms[zh]: _fold_modifiers(m, v), text)
    return text
