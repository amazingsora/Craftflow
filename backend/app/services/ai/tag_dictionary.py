# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
"""Danbooru 標籤字典（唯讀 CSV）：搜尋作品／繪師，並把原文轉成 prompt 寫法。"""
from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from pathlib import Path

from app.core.config import TAG_DICTIONARY_CSV, TAG_DICTIONARY_SEARCH_LIMIT

logger = logging.getLogger(__name__)

# [CN-131] 只收 Danbooru 的 繪師(1)／作品(3)；merged CSV 的 e621 分類 ≥7 一律不收
CATEGORY_KIND = {1: "artists", 3: "series"}
_HEADER_ALIASES = {
    "name": "name", "tag": "name", "category": "category", "type": "category",
    "count": "count", "post_count": "count", "aliases": "aliases", "alias": "aliases",
}
_TAGCOMPLETE_COLUMNS = ("name", "category", "count", "aliases")
_ALIAS_PREVIEW = 5
_cache: dict = {"key": None, "rows": []}


@dataclass(frozen=True)
class DictEntry:
    name: str
    kind: str
    count: int
    aliases: tuple[str, ...]

    @property
    def tag(self) -> str:
        return to_prompt_tag(self.name)


def to_prompt_tag(name: str) -> str:
    """Danbooru 原文 → prompt 寫法：去 @、底線轉空白、未跳脫的括號補 `\\` [FD-124]"""
    t = " ".join((name or "").strip().lstrip("@").replace("_", " ").split())
    out = []
    for i, ch in enumerate(t):
        if ch in "()" and (i == 0 or t[i - 1] != "\\"):
            out.append("\\")
        out.append(ch)
    return "".join(out)


def parse_rows(text: str) -> list[DictEntry]:
    """CSV 文字 → 作品／繪師條目；支援 tagcomplete（無表頭）與有表頭兩種格式 [FD-125]"""
    columns: tuple = _TAGCOMPLETE_COLUMNS
    out: list[DictEntry] = []
    for i, row in enumerate(csv.reader(io.StringIO(text))):
        if not row:
            continue
        if i == 0:
            header = tuple(_HEADER_ALIASES.get(c.strip().lower()) for c in row)
            if "name" in header and "category" in header:
                columns = header
                continue
        rec = dict(zip(columns, row))
        try:
            kind = CATEGORY_KIND.get(int(rec.get("category") or -1))
        except ValueError:
            continue
        name = (rec.get("name") or "").strip()
        if not kind or not name:
            continue
        try:
            count = int(float(rec.get("count") or 0))
        except ValueError:
            count = 0
        aliases = tuple(a.strip() for a in (rec.get("aliases") or "").split(",") if a.strip())
        out.append(DictEntry(name, kind, count, aliases))
    return out


def _rows() -> list[DictEntry]:
    """讀 TAG_DICTIONARY_CSV（路徑＋mtime 快取）；未設定或讀不到回空清單，同一狀態只 warn 一次"""
    if not TAG_DICTIONARY_CSV:
        return []
    path = Path(TAG_DICTIONARY_CSV)
    try:
        key = (str(path), path.stat().st_mtime)
    except OSError as e:
        if _cache["key"] != (str(path), None):
            logger.warning("[tag-dict] %s 讀不到（%s）→ 字典搜尋停用", path, e)
        _cache.update(key=(str(path), None), rows=[])
        return []
    if _cache["key"] != key:
        try:
            rows = parse_rows(path.read_text(encoding="utf-8-sig"))
            logger.info("[tag-dict] 載入 %s：作品／繪師 %d 筆", path, len(rows))
        except (OSError, UnicodeDecodeError, csv.Error) as e:
            logger.warning("[tag-dict] %s 解析失敗（%s）→ 視為空字典", path, e)
            rows = []
        _cache.update(key=key, rows=rows)
    return _cache["rows"]


def dictionary_status() -> dict:
    return {"configured": bool(TAG_DICTIONARY_CSV), "size": len(_rows())}


def _rank(entry: DictEntry, q: str) -> int | None:
    best = None
    for n in (entry.name.lower(), *(a.lower() for a in entry.aliases)):
        if n == q:
            return 0
        if n.startswith(q):
            best = 1
        elif q in n and best is None:
            best = 2
    return best


def search(query: str, kind: str | None = None, limit: int | None = None) -> list[dict]:
    """name／alias 子字串搜尋；完全相符 > 開頭相符 > 包含，同級依投稿數 [FD-126]"""
    q = "_".join((query or "").replace("\\", "").lstrip("@").lower().split())
    if not q:
        return []
    hits = []
    for e in _rows():
        if kind and e.kind != kind:
            continue
        r = _rank(e, q)
        if r is not None:
            hits.append((r, -e.count, e))
    hits.sort(key=lambda h: (h[0], h[1]))
    return [
        {"name": e.name, "tag": e.tag, "kind": e.kind, "count": e.count, "aliases": list(e.aliases[:_ALIAS_PREVIEW])}
        for _, _, e in hits[: limit or TAG_DICTIONARY_SEARCH_LIMIT]
    ]
