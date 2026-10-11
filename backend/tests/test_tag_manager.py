"""CN-131：tag 管理（清單寫入／匯入合併／Danbooru 字典搜尋）。"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.ai import custom_tags as ct
from app.services.ai import tag_dictionary as td

# tagcomplete 格式（無表頭）：name,category,count,aliases；含 e621 分類（≥7）與一般 tag
TAGCOMPLETE_CSV = (
    "1girl,0,6008644,\"1girls,sole_female\"\n"
    "sample_series,3,244929,\n"
    "mori_taarou,1,599,mori_tarou\n"
    "fate_(series),3,500000,\n"
    "mori_artist_e621,8,9999,\n"
    "ui_(sample_series),4,3412,sample_ui\n"
    "sample_series_fan,1,10,\n"
)
HEADER_CSV = "tag,category,alias,count\nsample_series,3,\"サンプル,範例作品\",244929\n"


@pytest.fixture
def tags_file(tmp_path, monkeypatch):
    p = tmp_path / "custom_tags.json"
    monkeypatch.setattr(ct, "CUSTOM_TAGS_FILE", p)
    monkeypatch.setattr(ct, "_cache", {"mtime": None, "data": None})
    return p


@pytest.fixture
def dict_csv(tmp_path, monkeypatch):
    p = tmp_path / "danbooru.csv"
    p.write_text(TAGCOMPLETE_CSV, encoding="utf-8")
    monkeypatch.setattr(td, "TAG_DICTIONARY_CSV", str(p))
    monkeypatch.setattr(td, "_cache", {"key": None, "rows": []})
    return p


@pytest.mark.parametrize("raw, expected", [
    ("mori_taarou", "mori taarou"),
    ("@mori_taarou", "mori taarou"),
    ("fate_(series)", r"fate \(series\)"),
    (r"fate \(series\)", r"fate \(series\)"),
    ("  sample   series ", "sample series"),
])
def test_to_prompt_tag(raw, expected):
    assert td.to_prompt_tag(raw) == expected


def test_parse_rows_keeps_only_danbooru_series_and_artists():
    rows = {e.name: e for e in td.parse_rows(TAGCOMPLETE_CSV)}
    assert set(rows) == {"sample_series", "mori_taarou", "fate_(series)", "sample_series_fan"}
    assert rows["mori_taarou"].kind == "artists" and rows["mori_taarou"].aliases == ("mori_tarou",)
    assert rows["sample_series"].kind == "series" and rows["sample_series"].count == 244929


def test_parse_rows_with_header():
    (e,) = td.parse_rows(HEADER_CSV)
    assert (e.name, e.kind, e.count) == ("sample_series", "series", 244929)
    assert "範例作品" in e.aliases


def test_search_ranks_exact_then_prefix_then_count(dict_csv):
    names = [r["name"] for r in td.search("sample series")]
    assert names == ["sample_series", "sample_series_fan"]
    assert td.search("tarou")[0]["tag"] == "mori taarou"       # alias 命中
    assert [r["name"] for r in td.search("sample", kind="artists")] == ["sample_series_fan"]
    assert td.search("") == []


def test_search_without_dictionary_is_empty(monkeypatch):
    monkeypatch.setattr(td, "TAG_DICTIONARY_CSV", "")
    assert td.search("sample") == [] and td.dictionary_status() == {"configured": False, "size": 0}


def test_missing_dictionary_file_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(td, "TAG_DICTIONARY_CSV", str(tmp_path / "nope.csv"))
    monkeypatch.setattr(td, "_cache", {"key": None, "rows": []})
    assert td.search("sample") == []
    assert td.dictionary_status() == {"configured": True, "size": 0}


def test_save_normalizes_dedupes_and_keeps_extra_keys(tags_file):
    tags_file.write_text(json.dumps({"_說明": "note", "series": []}, ensure_ascii=False), encoding="utf-8")
    saved = ct.save_custom_tags({
        "series": [{"label": "", "tag": "fate_(series)"}, {"label": "重複", "tag": "Fate (series)"}],
        "artists": [{"label": "森太郎", "tag": "@mori_taarou"}, {"label": "壞", "tag": "a, b"}],
    })
    assert saved == {
        "series": [{"label": r"fate \(series\)", "tag": r"fate \(series\)"}],
        "artists": [{"label": "森太郎", "tag": "mori taarou"}],
    }
    on_disk = json.loads(tags_file.read_text(encoding="utf-8"))
    assert on_disk["_說明"] == "note" and on_disk["artists"] == saved["artists"]
    assert ct.load_custom_tags() == saved
    assert not tags_file.with_name(tags_file.name + ".tmp").exists()


def test_save_rejects_over_limit(tags_file, monkeypatch):
    monkeypatch.setattr(ct, "CUSTOM_TAGS_MAX_PER_KIND", 1)
    with pytest.raises(ct.CustomTagsError):
        ct.save_custom_tags({"series": [{"tag": "a"}, {"tag": "b"}]})
    assert not tags_file.exists()


def test_saved_artist_still_gets_anima_prefix(tags_file):
    ct.save_custom_tags({"artists": [{"label": "森太郎", "tag": "mori_taarou"}]})
    assert ct.format_custom_tags("mori taarou", "anima") == "@mori taarou"


def test_import_json_merges_existing_first(tags_file):
    ct.save_custom_tags({"series": [{"label": "範例作品", "tag": "sample series"}]})
    payload = {"series": [{"label": "SS", "tag": "sample_series"}, {"label": "FGO", "tag": "fate/grand order"}],
               "artists": [{"tag": ""}]}
    res = ct.import_custom_tags(json.dumps(payload).encode(), "tags.json")
    assert (res["added"], res["duplicate"], res["invalid"]) == (1, 1, 1)
    assert res["tags"]["series"][0] == {"label": "範例作品", "tag": "sample series"}


def test_import_csv_only_series_and_artists(tags_file):
    res = ct.import_custom_tags(TAGCOMPLETE_CSV.encode(), "list.CSV")
    assert res["added"] == 4
    assert {e["tag"] for e in res["tags"]["artists"]} == {"mori taarou", "sample series fan"}


@pytest.mark.parametrize("content, name", [(b"x", "a.txt"), (b"{bad", "a.json"), (b"[]", "a.json"), (b"\xff\xfe", "a.csv")])
def test_import_rejects_bad_files(tags_file, content, name):
    with pytest.raises(ct.CustomTagsError):
        ct.import_custom_tags(content, name)


@pytest.fixture
def client(tags_file, dict_csv, monkeypatch):
    from app.api import art_generate as ag
    monkeypatch.setattr(ag, "CUSTOM_TAGS_IMPORT_MAX_BYTES", 64)
    app = FastAPI()
    app.include_router(ag.router)
    return TestClient(app)


def test_routes_end_to_end(client, tags_file):
    r = client.put("/art/custom-tags", json={"series": [{"label": "範例作品", "tag": "sample_series"}], "artists": []})
    assert r.status_code == 200 and r.json()["series"][0]["tag"] == "sample series"
    assert client.get("/art/custom-tags").json()["series"][0]["label"] == "範例作品"

    r = client.post("/art/custom-tags/import",
                    files={"file": ("a.json", json.dumps({"artists": [{"tag": "mori_taarou"}]}), "application/json")})
    assert r.status_code == 200 and r.json()["added"] == 1

    assert client.post("/art/custom-tags/import", files={"file": ("big.csv", "x" * 65, "text/csv")}).status_code == 400
    assert client.post("/art/custom-tags/import", files={"file": ("a.txt", "x", "text/plain")}).status_code == 400

    r = client.get("/art/tag-dictionary/search", params={"q": "mori", "kind": "artists"})
    body = r.json()
    assert body["configured"] is True and body["results"][0]["count"] == 599
    assert client.get("/art/tag-dictionary/search", params={"q": "a", "kind": "characters"}).status_code == 400


def test_put_over_limit_is_400(client, monkeypatch):
    monkeypatch.setattr(ct, "CUSTOM_TAGS_MAX_PER_KIND", 0)
    assert client.put("/art/custom-tags", json={"series": [{"tag": "a"}]}).status_code == 400
