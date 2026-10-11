# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
"""[CN-118] NSFW／未成年內容護欄（全專案唯一入口）。
未成年情境一律強制、無開關；一般情境受 NSFW_GUARD_ENABLED 控制。log 關鍵字 `nsfw-guard`。"""
from __future__ import annotations

import logging
import re
from typing import Optional

from app.core import config as _cfg

logger = logging.getLogger(__name__)

def _word_re(terms: tuple[str, ...]) -> re.Pattern:
    alt = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<![\w-])(?:{alt})(?![\w-])", re.IGNORECASE)

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


if not nsfw_guard_enabled():
    logger.warning("[nsfw-guard] NSFW_GUARD_ENABLED=false：成人內容過濾已關閉（debug 模式）；未成年護欄仍強制生效")
