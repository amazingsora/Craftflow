# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
"""NSFW／未成年內容護欄 —— 全專案唯一入口（2026-09-24 整合）。

歷史：S9（2026-07-13）的 `_NSFW_BANNED`（compiler sanitize 層）＋人設圖固定補 nsfw 負向，
在 ca2267f（09-21）被拔除；本檔把原本散在 compiler／character_design_service 的規則集中，
並補上「送進 ComfyUI 前最後一道閘」（wf_node_ops._inject_prompts）。

兩層、兩種強度：
  1. 未成年情境（角色年齡 < MINOR_AGE_LIMIT，或正向含 child/loli/… 等標記）
     → **一律強制**：剝除性相關 tag（含 cleavage/lingerie 等擦邊詞）＋負向補 MINOR_NEGATIVE_GUARD。
       不受 NSFW_GUARD_ENABLED 控制，沒有開關，也不應該加開關。
  2. 一般情境 → 受 `.env` 的 NSFW_GUARD_ENABLED（預設 true）控制：
       剝除正向露骨 tag；負向只在 adult_negative=True 的呼叫點（人設圖，沿用 S9）補 NSFW_NEGATIVE_GUARD，
       其餘路徑不動負向 → 未含露骨 tag 的 prompt 逐字不變（illustrious golden 鎖零回歸）。
       false＝成人內容不過濾（debug 用）。

Debug：每次實際剝除都會 logger.info 一行 `[nsfw-guard] layer=… minor=… age=… removed=[…]`，
grep `nsfw-guard` 即可看到每一層拿掉了什麼。
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from app.core import config as _cfg

logger = logging.getLogger(__name__)

MINOR_AGE_LIMIT = 18

# 露骨詞（一般情境）：tag 內以「全字」比對，涵蓋 "completely nude"、"nipple slip"、"(Nude:1.2)"
_EXPLICIT_TERMS = (
    "nsfw", "explicit", "hentai", "porn", "erotic", "sexual", "sex", "cum",
    "nude", "naked", "nudity", "topless", "bottomless",
    "nipple", "nipples", "areola", "areolae", "pubic hair",
    "pussy", "vagina", "penis", "genitals", "genitalia", "cameltoe",
    "bare breasts", "exposed breasts",
)
# 擦邊詞（只在未成年情境剝除；成人情境屬正常服裝描述）
_SUGGESTIVE_TERMS = (
    "cleavage", "lingerie", "underwear", "panties", "no panties", "bra", "no bra",
    "see-through", "suggestive", "seductive", "bikini",
)
# 未成年標記：正向出現即視為未成年情境（寧可誤判成未成年，也不漏放）
_MINOR_MARKERS = (
    "child", "children", "toddler", "infant", "kid", "kids", "preteen",
    "loli", "lolicon", "shota", "shotacon",
    "young girl", "young boy", "little girl", "little boy",
    "teen", "teenage", "teenager", "elementary school", "middle school", "junior high",
)

NSFW_NEGATIVE_GUARD = "nsfw, nude, naked, nipples, pubic hair, topless, bottomless, exposed breasts"
MINOR_NEGATIVE_GUARD = f"{NSFW_NEGATIVE_GUARD}, cleavage, lingerie, underwear, suggestive, sexualized"


def _word_re(terms: tuple[str, ...]) -> re.Pattern:
    alt = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<![\w-])(?:{alt})(?![\w-])", re.IGNORECASE)


_EXPLICIT_RE = _word_re(_EXPLICIT_TERMS)
_MINOR_SEXUAL_RE = _word_re(_EXPLICIT_TERMS + _SUGGESTIVE_TERMS)
_MINOR_MARKER_RE = _word_re(_MINOR_MARKERS)
_AGE_PHRASE_RE = re.compile(r"\b(\d{1,2})\s*(?:-\s*)?years?[\s-]*old\b", re.IGNORECASE)


def _norm(tag: str) -> str:
    """去 SD 權重語法與括號：'(Nude:1.2)' → 'nude'。"""
    n = tag.strip().lower().strip("() ")
    if ":" in n:
        n = n.rsplit(":", 1)[0].strip().strip("() ")
    return n


def _split(prompt: str) -> list[str]:
    return [t.strip() for t in (prompt or "").split(",") if t.strip()]


def nsfw_guard_enabled() -> bool:
    """呼叫時才讀，讓測試可 monkeypatch config.NSFW_GUARD_ENABLED。"""
    return bool(getattr(_cfg, "NSFW_GUARD_ENABLED", True))


def is_explicit_tag(tag: str) -> bool:
    return bool(_EXPLICIT_RE.search(_norm(tag)))


def is_minor_context(positive: str, age: Optional[int] = None) -> bool:
    """角色年齡 < 18，或正向含未成年標記／「N years old」且 N < 18。"""
    if age is not None and age < MINOR_AGE_LIMIT:
        return True
    text = ", ".join(_norm(t) for t in _split(positive))
    if _MINOR_MARKER_RE.search(text):
        return True
    return any(int(m.group(1)) < MINOR_AGE_LIMIT for m in _AGE_PHRASE_RE.finditer(text))


def _append_missing(negative: str, guard: str) -> str:
    have = {_norm(t) for t in _split(negative)}
    extra = [t for t in _split(guard) if _norm(t) not in have]
    if not extra:
        return negative
    return ", ".join([*_split(negative), *extra])


def apply_content_guard(positive: str, negative: str, age: Optional[int] = None,
                        layer: str = "", adult_negative: bool = False) -> tuple[str, str]:
    """回傳 (正向, 負向)。冪等：同一組輸入重複套用結果不變。

    adult_negative：一般情境是否也在負向補 NSFW_NEGATIVE_GUARD（未成年情境一律補）。
    """
    minor = is_minor_context(positive, age)
    if minor:
        pattern, neg_guard = _MINOR_SEXUAL_RE, MINOR_NEGATIVE_GUARD
    elif nsfw_guard_enabled():
        pattern, neg_guard = _EXPLICIT_RE, (NSFW_NEGATIVE_GUARD if adult_negative else "")
    else:
        return positive, negative

    kept, removed = [], []
    for t in _split(positive):
        (removed if pattern.search(_norm(t)) else kept).append(t)
    if removed:
        logger.info("[nsfw-guard] layer=%s minor=%s age=%s removed=%s", layer or "-", minor, age, removed)
        positive = ", ".join(kept)
    return positive, (_append_missing(negative, neg_guard) if neg_guard else negative)


if not nsfw_guard_enabled():
    logger.warning("[nsfw-guard] NSFW_GUARD_ENABLED=false：成人內容過濾已關閉（debug 模式）；未成年護欄仍強制生效")
