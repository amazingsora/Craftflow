# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
"""角色「外觀年齡」與「身材」卡片：讀 backend/appearance_cards.yml，依性別回傳正／負向 tag。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

APPEARANCE_CARDS_FILE = Path(__file__).resolve().parents[3] / "appearance_cards.yml"
NO_CARD = "none"
_GENDER_KEYS = {"female": "female", "male": "male"}
_GENDERS = ("female", "male", "neutral")
_ALL_GENDERS = "all"
_cache: dict = {"mtime": None, "data": None}


@dataclass(frozen=True)
class CardTags:
    key: str
    positive: str
    negative: str
    adult_male_pack: bool


@dataclass(frozen=True)
class BodyTags:
    positive: str
    negative: str


def _load_raw() -> dict:
    """讀整份 yml（mtime 快取）；檔案不存在或格式錯回空 dict [FD-122]"""
    try:
        mtime = APPEARANCE_CARDS_FILE.stat().st_mtime
    except OSError:
        return {}
    if _cache["mtime"] == mtime and _cache["data"] is not None:
        return _cache["data"]
    try:
        data = yaml.safe_load(APPEARANCE_CARDS_FILE.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise AttributeError("頂層不是 mapping")
    except (OSError, yaml.YAMLError, AttributeError) as e:
        logger.warning("[appearance-cards] %s 讀取失敗（%s）→ 視為沒有卡片", APPEARANCE_CARDS_FILE, e)
        data = {}
    _cache.update(mtime=mtime, data=data)
    return data


def _mapping(value) -> dict:
    return {str(k): v for k, v in value.items() if isinstance(v, dict)} if isinstance(value, dict) else {}


def load_cards() -> dict:
    """外觀年齡卡片定義 {key: card}（不含 none）。"""
    return {k: v for k, v in _mapping(_load_raw().get("cards")).items() if k != NO_CARD}


def load_body_groups() -> dict:
    """身材卡片組 {group_key: {label, cards: {key: card}}}，順序同 yml。"""
    return {k: {**g, "cards": _mapping(g.get("cards"))} for k, g in _mapping(_load_raw().get("body_groups")).items()}


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


def list_body_groups() -> list[dict]:
    """UI 用身材卡片組；tags[性別] 為 None＝該性別不適用。"""
    out = []
    for gkey, group in load_body_groups().items():
        cards = [{
            "key": ckey,
            "label": str(card.get("label") or ckey),
            "hint": str(card.get("hint") or ""),
            "tags": {g: _body_side(card, g) for g in _GENDERS},
        } for ckey, card in group["cards"].items()]
        out.append({"key": gkey, "label": str(group.get("label") or gkey), "cards": cards})
    return out


def resolve_body(keys: str | None, gender: str | None, age_key: str | None) -> BodyTags:
    """身材卡片 key 串＋性別＋外觀年齡 → 合併後的正／負向；不適用的卡略過，每組只取第一張。"""
    wanted = {k.strip() for k in (keys or "").split(",") if k.strip()}
    if not wanted:
        return BodyTags("", "")
    gender_key = _GENDER_KEYS.get(gender or "", "neutral")
    pos: list[str] = []
    neg: list[str] = []
    found: set[str] = set()
    for group in load_body_groups().values():
        found |= wanted & group["cards"].keys()
        for ckey, card in group["cards"].items():
            if ckey not in wanted:
                continue
            side = _body_side(card, gender_key)
            
            pos += [side["positive"]] if side["positive"] else []
            neg += [side["negative"]] if side["negative"] else []
            break
    if wanted - found:
        logger.warning("[appearance-cards] 未知身材卡 %s（yml 已移除？）→ 略過", sorted(wanted - found))
    return BodyTags(", ".join(pos), ", ".join(neg))


def _body_side(card: dict, gender_key: str) -> dict | None:
    if not isinstance(card.get(gender_key) or card.get(_ALL_GENDERS), dict):
        return None
    return _side({gender_key: card.get(gender_key) or card.get(_ALL_GENDERS)}, gender_key)


def _side(card: dict, gender_key: str) -> dict:
    side = card.get(gender_key) or {}
    return {"positive": str(side.get("positive") or "").strip(" ,"),
            "negative": str(side.get("negative") or "").strip(" ,")}
