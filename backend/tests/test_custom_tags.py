"""CN-122：客製化標籤（作品／繪師）本機 JSON 清單與家族格式化。"""
import inspect
import json

import pytest

from app.services.ai import custom_tags as ct


@pytest.fixture
def tags_file(tmp_path, monkeypatch):
    p = tmp_path / "custom_tags.json"
    monkeypatch.setattr(ct, "CUSTOM_TAGS_FILE", p)
    monkeypatch.setattr(ct, "_cache", {"mtime": None, "data": None})
    return p


def _write(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_missing_file_is_empty(tags_file):
    assert ct.load_custom_tags() == {"series": [], "artists": []}


def test_broken_json_is_empty(tags_file):
    tags_file.write_text("{not json", encoding="utf-8")
    assert ct.load_custom_tags() == {"series": [], "artists": []}


def test_load_drops_entries_without_tag_and_defaults_label(tags_file):
    _write(tags_file, {"series": [{"label": "作品A", "tag": "series a"}, {"label": "空"}],
                       "artists": [{"tag": "artist b"}], "_說明": "ignored"})
    assert ct.load_custom_tags() == {
        "series": [{"label": "作品A", "tag": "series a"}],
        "artists": [{"label": "artist b", "tag": "artist b"}],
    }


def test_anima_prefixes_listed_artist_only(tags_file):
    _write(tags_file, {"artists": [{"label": "B", "tag": "artist b"}]})
    assert ct.format_custom_tags("series a, artist b, other c", "anima") == "series a, @artist b, other c"


def test_non_anima_strips_at(tags_file):
    _write(tags_file, {"artists": [{"label": "B", "tag": "artist b"}]})
    assert ct.format_custom_tags("@artist b, series a", "illustrious") == "artist b, series a"


def test_empty_and_dedup(tags_file):
    assert ct.format_custom_tags("", "anima") == ""
    assert ct.format_custom_tags(None, "anima") == ""
    assert ct.format_custom_tags("a, a,\nb", "sdxl") == "a, b"


def test_design_routes_accept_new_params():
    from app.api import art_generate as ag
    for fn in (ag.generate_character_design, ag.generate_variant_design):
        params = inspect.signature(fn).parameters
        assert params["face_detailer"].default is True
        assert params["custom_tags"].default == ""


def test_custom_tags_route_registered():
    from app.api import art_generate as ag
    assert any(getattr(r, "path", "") == "/art/custom-tags" for r in ag.router.routes)
