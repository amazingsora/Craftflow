"""
image_ops._dedup_tags 純函式單測（P2，2026-07-02 規劃）。
執行：cd backend && pytest tests/test_image_ops_pure.py
"""
from app.services.ai.image_ops import _dedup_tags


def test_dedup_tags_basic():
    assert _dedup_tags("1girl, solo, 1girl") == "1girl, solo"


def test_dedup_tags_case_and_paren_insensitive():
    assert _dedup_tags("(White Hair:1.1), white hair, solo") == "(White Hair:1.1), solo"


def test_dedup_tags_collapses_fullbody_synonyms():
    out = _dedup_tags("full body shot, standing, head to toe, whole body")
    assert out == "full body shot, standing"


def test_dedup_tags_empty_string():
    assert _dedup_tags("") == ""


def test_dedup_tags_ignores_blank_segments():
    assert _dedup_tags("1girl, , solo,") == "1girl, solo"
