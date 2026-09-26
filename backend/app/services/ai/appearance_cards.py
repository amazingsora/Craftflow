# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
"""角色「外觀年齡」卡片：讀 backend/appearance_cards.yml，依性別回傳正／負向 tag。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

APPEARANCE_CARDS_FILE = Path(__file__).resolve().parents[3] / "appearance_cards.yml"
NO_CARD = "none"
_GENDER_KEYS = {"female": "female", "male": "male"}
_cache: dict = {"mtime": None, "data": None}


@dataclass(frozen=True)
class CardTags:
    key: str
    positive: str
    negative: str
    adult_male_pack: bool


def load_cards() -> dict:
    """讀卡片定義（mtime 快取）；檔案不存在或格式錯回空 dict [FD-122]"""
    try:
        mtime = APPEARANCE_CARDS_FILE.stat().st_mtime
    except OSError:
        return {}
    if _cache["mtime"] == mtime and _cache["data"] is not None:
        return _cache["data"]
    try:
        raw = yaml.safe_load(APPEARANCE_CARDS_FILE.read_text(encoding="utf-8")) or {}
        cards = raw.get("cards") or {}
        data = {str(k): v for k, v in cards.items() if isinstance(v, dict) and str(k) != NO_CARD}
    except (OSError, yaml.YAMLError, AttributeError) as e:
        logger.warning("[appearance-cards] %s 讀取失敗（%s）→ 視為沒有卡片", APPEARANCE_CARDS_FILE, e)
        data = {}
    _cache.update(mtime=mtime, data=data)
    return data


def list_cards() -> list[dict]:
    """UI 用清單（含每個性別的預覽 tag），順序同 yml。"""
    out = []
    for key, card in load_cards().items():
        out.append({
            "key": key,
            "label": str(card.get("label") or key),
            "hint": str(card.get("hint") or ""),
            "tags": {g: _side(card, g) for g in ("female", "male", "neutral")},
        })
    return out


def resolve_card(key: str | None, gender: str | None) -> CardTags | None:
    """卡片 key＋性別 → CardTags；未選／未知 key 回 None（未知 key 會告警） [FD-123]"""
    if not key or key == NO_CARD:
        return None
    card = load_cards().get(key)
    if card is None:
        logger.warning("[appearance-cards] 未知卡片 %r（yml 已移除？）→ 不加外觀 tag", key)
        return None
    side = _side(card, _GENDER_KEYS.get(gender or "", "neutral"))
    return CardTags(key=key, positive=side["positive"], negative=side["negative"],
                    adult_male_pack=bool(card.get("adult_male_pack")))


def _side(card: dict, gender_key: str) -> dict:
    side = card.get(gender_key) or {}
    return {"positive": str(side.get("positive") or "").strip(" ,"),
            "negative": str(side.get("negative") or "").strip(" ,")}
