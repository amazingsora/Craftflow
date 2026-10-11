# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
"""本機客製化標籤（作品／繪師）：清單讀 CUSTOM_TAGS_FILE，依家族格式化成畫風段。"""
from __future__ import annotations

import json
import logging
import os

from app.core.config import CUSTOM_TAGS_FILE, CUSTOM_TAGS_MAX_PER_KIND
from app.services.ai.tag_dictionary import parse_rows, to_prompt_tag

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


class CustomTagsError(ValueError):
    """使用者送來的清單或匯入檔不合法（API 轉 400）"""


def _dedupe_key(tag: str) -> str:
    return tag.replace("\\", "").lower()


def _clean_entry(entry: dict) -> dict | None:
    tag = to_prompt_tag(str(entry.get("tag") or ""))
    if not tag or "," in tag:
        return None
    label = " ".join(str(entry.get("label") or "").split()) or tag
    return {"label": label, "tag": tag}


def _extra_keys() -> dict:
    """保留檔案裡非清單的頂層鍵（如 `_說明`），整份覆寫時不吃掉使用者的註記"""
    try:
        raw = json.loads(CUSTOM_TAGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in raw.items() if k not in TAG_KINDS} if isinstance(raw, dict) else {}


def save_custom_tags(data: dict) -> dict:
    """正規化 tag、各類去重後原子寫入 CUSTOM_TAGS_FILE，回傳寫入後清單 [FD-127]"""
    clean = _empty()
    for k in TAG_KINDS:
        seen: set[str] = set()
        for e in data.get(k) or []:
            c = _clean_entry(e) if isinstance(e, dict) else None
            if c and _dedupe_key(c["tag"]) not in seen:
                seen.add(_dedupe_key(c["tag"]))
                clean[k].append(c)
        if len(clean[k]) > CUSTOM_TAGS_MAX_PER_KIND:
            raise CustomTagsError(f"{k} 共 {len(clean[k])} 筆，超過上限 {CUSTOM_TAGS_MAX_PER_KIND}")
    CUSTOM_TAGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CUSTOM_TAGS_FILE.with_name(CUSTOM_TAGS_FILE.name + ".tmp")
    tmp.write_text(json.dumps({**_extra_keys(), **clean}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, CUSTOM_TAGS_FILE)
    _cache.update(mtime=CUSTOM_TAGS_FILE.stat().st_mtime, data=clean)
    return clean


def _parse_import(content: bytes, filename: str) -> dict:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise CustomTagsError("檔案需為 UTF-8 編碼") from e
    name = (filename or "").lower()
    if name.endswith(".json"):
        try:
            raw = json.loads(text)
        except ValueError as e:
            raise CustomTagsError(f"JSON 格式錯誤：{e}") from e
        if not isinstance(raw, dict):
            raise CustomTagsError("JSON 需為 {\"series\": [...], \"artists\": [...]}")
        return {k: [e for e in raw.get(k) or [] if isinstance(e, dict)] for k in TAG_KINDS}
    if name.endswith(".csv"):
        incoming = _empty()
        for e in parse_rows(text):
            incoming[e.kind].append({"tag": e.name})
        return incoming
    raise CustomTagsError("只支援 .json（custom_tags 格式）或 .csv（Danbooru 標籤格式）")


def import_custom_tags(content: bytes, filename: str) -> dict:
    """匯入檔合併進現有清單（既有條目優先、同 tag 不覆蓋 label），回傳清單＋統計 [FD-128]"""
    incoming = _parse_import(content, filename)
    merged = {k: list(v) for k, v in load_custom_tags().items()}
    stats = {"added": 0, "duplicate": 0, "invalid": 0}
    for k in TAG_KINDS:
        seen = {_dedupe_key(to_prompt_tag(e["tag"])) for e in merged[k]}
        for e in incoming[k]:
            c = _clean_entry(e)
            if not c:
                stats["invalid"] += 1
            elif _dedupe_key(c["tag"]) in seen:
                stats["duplicate"] += 1
            else:
                seen.add(_dedupe_key(c["tag"]))
                merged[k].append(c)
                stats["added"] += 1
    return {"tags": save_custom_tags(merged), **stats}
