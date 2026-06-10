"""
SQLite 定時備份 — VACUUM INTO 產生一致性快照至 BACKUP_DIR。
啟動時備份一次，之後每 BACKUP_INTERVAL_HOURS 一次（0 = 停用）。
備份失敗只記 log，不影響 app 運作（resilient errors）。
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime

from app.core.config import DB_PATH, BACKUP_DIR, BACKUP_KEEP, BACKUP_INTERVAL_HOURS

logger = logging.getLogger(__name__)

_BACKUP_PREFIX = "craftflow_"
_BACKUP_SUFFIX = ".db"


def backup_db() -> str | None:
    """執行一次備份，回傳備份檔路徑（失敗回 None）。"""
    if not DB_PATH.exists():
        logger.warning("[backup] DB 不存在，跳過：%s", DB_PATH)
        return None
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = BACKUP_DIR / f"{_BACKUP_PREFIX}{stamp}{_BACKUP_SUFFIX}"
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("VACUUM INTO ?", (str(dest),))
        _prune_old_backups()
        logger.info("[backup] 完成：%s", dest)
        return str(dest)
    except Exception as e:
        logger.error("[backup] 失敗：%s", e)
        return None


def _prune_old_backups() -> None:
    """只保留最新 BACKUP_KEEP 份（依檔名時間戳排序）。"""
    backups = sorted(BACKUP_DIR.glob(f"{_BACKUP_PREFIX}*{_BACKUP_SUFFIX}"))
    for old in backups[:-BACKUP_KEEP] if BACKUP_KEEP > 0 else []:
        try:
            old.unlink()
            logger.info("[backup] 淘汰舊備份：%s", old.name)
        except Exception as e:
            logger.warning("[backup] 淘汰失敗 %s：%s", old.name, e)


async def backup_loop() -> None:
    """背景任務：啟動先備份一次，之後依間隔執行。"""
    if BACKUP_INTERVAL_HOURS <= 0:
        logger.info("[backup] 定時備份已停用（BACKUP_INTERVAL_HOURS=0）")
        return
    while True:
        await asyncio.to_thread(backup_db)
        await asyncio.sleep(BACKUP_INTERVAL_HOURS * 3600)
