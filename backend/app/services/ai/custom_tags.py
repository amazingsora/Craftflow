# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
"""本機客製化標籤（作品／繪師）：清單讀 CUSTOM_TAGS_FILE，依家族格式化成畫風段。"""
from __future__ import annotations

import json
import logging

from app.core.config import CUSTOM_TAGS_FILE

logger = logging.getLogger(__name__)

TAG_KINDS = ("series", "artists")
_ARTIST_PREFIX_FAMILIES = {"anima"}
_cache: dict = {"mtime": None, "data": None}


def _empty() -> dict:
    return {k: [] for k in TAG_KINDS}


def load_custom_tags() -> dict:
    """讀清單（mtime 快取）；檔案不存在或格式錯回空清單 [FD-119]"""
    try:
        mtime = CUSTOM_TAGS_FILE.stat().st_mtime
    except OSError:
        return _empty()
    if _cache["mtime"] == mtime and _cache["data"] is not None:
        return _cache["data"]
    try:
        raw = json.loads(CUSTOM_TAGS_FILE.read_text(encoding="utf-8"))
        data = {
            k: [{"label": str(e.get("label") or e["tag"]).strip(), "tag": str(e["tag"]).strip()}
                for e in raw.get(k, []) if isinstance(e, dict) and str(e.get("tag") or "").strip()]
            for k in TAG_KINDS
        }
    except (OSError, ValueError, AttributeError, TypeError) as e:
        logger.warning("[custom-tags] %s 讀取失敗（%s）→ 視為空清單", CUSTOM_TAGS_FILE, e)
        data = _empty()
    _cache.update(mtime=mtime, data=data)
    return data


def format_custom_tags(text: str | None, family: str) -> str:
    """textarea 內容 → 畫風段 tag；anima 家族的清單內繪師補 `@`，其他家族去 `@` [FD-120]"""
    tags = [t.strip() for t in (text or "").replace("\n", ",").split(",") if t.strip()]
    if not tags:
        return ""
    artists = {e["tag"].lstrip("@").strip().lower() for e in load_custom_tags()["artists"]}
    out = []
    for t in tags:
        bare = t.lstrip("@").strip()
        if family in _ARTIST_PREFIX_FAMILIES:
            out.append(f"@{bare}" if bare.lower() in artists else t)
        else:
            out.append(bare)
    return ", ".join(dict.fromkeys(out))
