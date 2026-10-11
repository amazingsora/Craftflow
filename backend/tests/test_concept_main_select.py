"""概念圖 main 切換＋指定參與生成（CN-132）。in-memory SQLite 實跑 API helper 與生成過濾。"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.character import Character
from app.models.project import Project
from app.api.characters import (
    ConceptImagePatch, _CONCEPT, _patch_concept, _remove_image,
)
from app.services.ai.variant_helpers import _get_variants, active_concept_images

IMGS = ["zz_test_cn132_a.png", "zz_test_cn132_b.png", "zz_test_cn132_c.png"]


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    import app.models  # noqa: F401
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def char(db):
    p = Project(title="t", author="a")
    db.add(p)
    db.commit()
    c = Character(project_id=p.id, name="n", concept_images=list(IMGS),
                  variants=[{"concept_images": list(IMGS)}, {}])
    db.add(c)
    db.commit()
    return c


@pytest.mark.parametrize("slot", [None, 1])
def test_set_main_moves_to_front(db, char, slot):
    c = _patch_concept(db, char.id, slot, 2, ConceptImagePatch(main=True))
    imgs = c.concept_images if slot is None else _get_variants(c)[0]["concept_images"]
    assert imgs == [IMGS[2], IMGS[0], IMGS[1]]


@pytest.mark.parametrize("slot", [None, 1])
def test_disable_then_generation_filters(db, char, slot):
    c = _patch_concept(db, char.id, slot, 1, ConceptImagePatch(enabled=False))
    src = c if slot is None else None
    imgs = src.concept_images if src else _get_variants(c)[0]["concept_images"]
    exc = src.concept_excluded if src else _get_variants(c)[0]["concept_excluded"]
    assert exc == [IMGS[1]]
    assert active_concept_images(imgs, exc) == [IMGS[0], IMGS[2]]
    c = _patch_concept(db, char.id, slot, 1, ConceptImagePatch(enabled=True))
    exc = c.concept_excluded if slot is None else _get_variants(c)[0]["concept_excluded"]
    assert exc == []


def test_cannot_disable_main(db, char):
    with pytest.raises(HTTPException) as e:
        _patch_concept(db, char.id, None, 0, ConceptImagePatch(enabled=False))
    assert e.value.status_code == 400


def test_promoting_excluded_image_to_main_reenables_it(db, char):
    _patch_concept(db, char.id, None, 2, ConceptImagePatch(enabled=False))
    c = _patch_concept(db, char.id, None, 2, ConceptImagePatch(main=True))
    assert c.concept_images[0] == IMGS[2]
    assert c.concept_excluded == []


def test_delete_prunes_excluded_and_new_main_is_enabled(db, char):
    _patch_concept(db, char.id, None, 1, ConceptImagePatch(enabled=False))
    c = _remove_image(db, char.id, None, _CONCEPT, 0)   # 刪 main → 被排除的 b 升為 main
    assert c.concept_images == [IMGS[1], IMGS[2]]
    assert c.concept_excluded == []


def test_active_concept_images_keeps_main_even_if_listed():
    assert active_concept_images(IMGS, [IMGS[0], IMGS[2]]) == [IMGS[0], IMGS[1]]
    assert active_concept_images(None, None) == []
