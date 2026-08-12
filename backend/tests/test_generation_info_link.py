"""已存圖 ↔ 生成資訊關聯（2026-07-26 需求1）。

用 in-memory SQLite 實際跑一遍綁定與反查，不只驗欄位存在。
執行：cd backend && pytest tests/test_generation_info_link.py -v
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.generation_history import GenerationHistory
from app.api.characters import _bind_history_to_file, _history_for_file, _nth_ai_image


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    import app.models  # noqa: F401 — 註冊全部 ORM model
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()


def _mk(db, **kw):
    rec = GenerationHistory(
        endpoint="character_design", seed=123, workflow="Standard_V37.json",
        style="illustrious", positive="1girl, solo", negative="worst quality",
        params={"width": 768, "height": 1344, "timings": {"total": 81.9}}, **kw,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def test_bind_then_lookup_roundtrip(db):
    rec = _mk(db)
    assert rec.saved_filename is None
    _bind_history_to_file(db, rec.id, "ai_1_abc.png")
    db.commit()

    found = _history_for_file(db, "ai_1_abc.png")
    assert found.id == rec.id
    assert found.positive == "1girl, solo"
    assert found.params["timings"]["total"] == 81.9


def test_lookup_missing_raises_404(db):
    from fastapi import HTTPException
    _mk(db)
    with pytest.raises(HTTPException) as e:
        _history_for_file(db, "never_saved.png")
    assert e.value.status_code == 404


def test_bind_with_none_history_id_is_noop(db):
    """未帶 history_id（例如舊版前端）不得炸掉存圖流程。"""
    rec = _mk(db)
    _bind_history_to_file(db, None, "x.png")
    db.commit()
    db.refresh(rec)
    assert rec.saved_filename is None


def test_bind_with_bad_history_id_is_silent(db):
    """resilient errors：綁不到不該讓存圖失敗。"""
    _bind_history_to_file(db, 999999, "x.png")  # 不存在的 id
    db.commit()


def test_latest_wins_when_filename_reused(db):
    """同檔名理論上不會重複（uuid），但真撞到時取最新一筆，不得回傳舊資料。"""
    old = _mk(db)
    new = _mk(db)
    _bind_history_to_file(db, old.id, "dup.png")
    _bind_history_to_file(db, new.id, "dup.png")
    db.commit()
    assert _history_for_file(db, "dup.png").id == new.id


@pytest.mark.parametrize("index", [-1, 3, 99])
def test_nth_ai_image_out_of_range(index):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _nth_ai_image(["a.png", "b.png", "c.png"], index)
    assert e.value.status_code == 404


def test_nth_ai_image_ok():
    assert _nth_ai_image(["a.png", "b.png"], 1) == "b.png"


def test_migration_registers_saved_filename_column():
    """ALTER TABLE 遷移清單要涵蓋新欄位，否則舊庫升級後端點恆 500。"""
    import inspect
    from app.core import database
    src = inspect.getsource(database._migrate)
    assert "generation_history" in src and "saved_filename" in src
