"""vision_extract 單元測試（A3，2026-06-13）。

Ollama / guardian 全部 mock，不需要實際服務。
執行：cd backend && pytest tests/test_vision_extract.py
"""
import asyncio

import pytest

from app.services.ai import vision_extract as ve


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    """每個測試前清空 vision 快取，並固定 vision model 名稱。"""
    ve._VISION_CACHE.clear()
    monkeypatch.setattr(ve.state, "get_vision_model", lambda: "test-vision-model")
    yield
    ve._VISION_CACHE.clear()


# ── 角色屬性 → SD 標籤 ────────────────────────────────────────────────────────

@pytest.mark.parametrize("gender, age, expected", [
    ("female", 16, "1girl"),
    ("female", None, "1girl"),
    ("female", 30, "1woman"),
    ("female", 45, "1woman, mature female"),
    ("male", 16, "1boy"),
    ("male", 30, "1man"),
    ("male", 50, "1man, mature male"),
    ("neutral", 20, "androgynous"),
    (None, 20, ""),
])
def test_age_gender_tag(gender, age, expected):
    assert ve._age_gender_tag(gender, age) == expected


@pytest.mark.parametrize("age, keyword", [
    (None, ""),
    (5, "toddler"),
    (10, "child"),
    (13, "flat chest"),
    (16, ""),      # S3（2026-07-13）：15-17 歲檔改空
    (20, ""),
])
def test_age_body_tags(age, keyword):
    result = ve._age_body_tags(age)
    if keyword:
        assert keyword in result
    else:
        assert result == ""


def test_age_body_tags_s3_child_is_single_tag_no_flat_chest():
    """S3：≤12 歲檔縮為單一 `child`，拔 flat chest/small hands（防三頭身 chibi）。"""
    assert ve._age_body_tags(10) == "child"
    assert "flat chest" not in ve._age_body_tags(10)


@pytest.mark.parametrize("height, expected", [
    (None, ""),
    (120, "very short stature, tiny, small figure"),
    (140, "short stature, petite"),
    (155, "petite"),
    (165, ""),
    (175, "tall, long legs"),
    (185, "very tall, long legs"),
])
def test_height_body_tags(height, expected):
    assert ve._height_body_tags(height) == expected


# ── 服裝/髮型過濾 ─────────────────────────────────────────────────────────────

def test_filter_visual_noop_when_flags_off():
    v = "白色頭髮，黑色外套，金色眼睛"
    assert ve._filter_visual_for_llm(v, strip_clothing=False, strip_hairstyle=False) == v


def test_filter_visual_strips_clothing():
    out = ve._filter_visual_for_llm(
        "白色頭髮，黑色外套，金色眼睛，長窄裙",
        strip_clothing=True, strip_hairstyle=False,
    )
    assert "外套" not in out and "裙" not in out
    assert "白色頭髮" in out and "金色眼睛" in out


def test_filter_visual_strips_hairstyle():
    out = ve._filter_visual_for_llm(
        "雙馬尾，金色眼睛，黑色外套",
        strip_clothing=False, strip_hairstyle=True,
    )
    assert "雙馬尾" not in out
    assert "黑色外套" in out  # 只開髮型過濾時服裝保留


def test_filter_visual_handles_ascii_comma():
    out = ve._filter_visual_for_llm(
        "白色頭髮,黑色外套,金色眼睛",
        strip_clothing=True, strip_hairstyle=False,
    )
    assert "外套" not in out and "白色頭髮" in out


def test_filter_visual_strips_skin_leak():
    """S8（2026-07-13）：strip_skin 剝除線稿膚色洩漏句（膚色/未填色/tan skin tone），
    正常特徵保留。"""
    out = ve._filter_visual_for_llm(
        "金色眼睛，膚色未填色呈線條狀，tan skin tone，白色上衣",
        strip_clothing=False, strip_hairstyle=False, strip_skin=True,
    )
    assert "膚色" not in out and "tan skin" not in out
    assert "金色眼睛" in out and "白色上衣" in out


def test_filter_visual_strip_skin_off_by_default():
    """strip_skin 預設 False，未開時不影響既有行為（零回歸）。"""
    v = "膚色偏白，金色眼睛"
    assert ve._filter_visual_for_llm(v, strip_clothing=False, strip_hairstyle=False) == v


# ── vision prompt 模板 ────────────────────────────────────────────────────────

def test_visual_extract_prompt_single_vs_multi():
    single = ve._visual_extract_prompt(1)
    multi = ve._visual_extract_prompt(3)
    assert "70字" in single
    assert "90字" in multi and "3 張" in multi


# ── 快取 key ──────────────────────────────────────────────────────────────────

def test_cache_key_deterministic_and_sensitive(monkeypatch):
    imgs = [b"img-a", b"img-b"]
    k1 = ve._vision_cache_key(imgs, "coverage")
    assert k1 == ve._vision_cache_key([b"img-a", b"img-b"], "coverage")  # 同輸入同 key
    assert k1 != ve._vision_cache_key(imgs, "plain2")                    # 模式不同
    assert k1 != ve._vision_cache_key([b"img-a", b"img-X"], "coverage")  # 內容不同
    monkeypatch.setattr(ve.state, "get_vision_model", lambda: "other-model")
    assert k1 != ve._vision_cache_key(imgs, "coverage")                  # 模型不同


def test_cache_key_includes_flow_version():
    """H1（2026-07-13）：cache key 前綴流程版本號，改 coverage 邏輯後舊快取自動失效。"""
    key = ve._vision_cache_key([b"img"], "coverage")
    assert key.startswith(ve._VISION_FLOW_VERSION + "|")


# ── _vision_extract_cached ────────────────────────────────────────────────────

def _setup_mocks(monkeypatch, visual="白髮，金眼", coverage="full"):
    calls = {"detect": 0, "focus": 0}

    def fake_detect(images):
        calls["detect"] += 1
        return coverage, visual

    async def fake_focus(target):
        calls["focus"] += 1

    monkeypatch.setattr(ve, "_detect_coverage_and_extract_visual", fake_detect)
    monkeypatch.setattr(ve.guardian, "request_focus", fake_focus)
    return calls


def test_cached_miss_then_hit(monkeypatch):
    calls = _setup_mocks(monkeypatch)
    r1 = asyncio.run(ve._vision_extract_cached([b"img"], need_coverage=True))
    r2 = asyncio.run(ve._vision_extract_cached([b"img"], need_coverage=True))
    assert r1 == r2 == ("full", "白髮，金眼")
    assert calls["detect"] == 1   # 第二次走快取
    assert calls["focus"] == 1    # cache hit 連 request_focus 都跳過


def test_cached_error_result_not_cached(monkeypatch):
    calls = _setup_mocks(monkeypatch, visual="[vision 分析失敗]")
    asyncio.run(ve._vision_extract_cached([b"img"], need_coverage=True))
    asyncio.run(ve._vision_extract_cached([b"img"], need_coverage=True))
    assert calls["detect"] == 2   # 錯誤結果不快取，重打


def test_cached_fifo_eviction(monkeypatch):
    _setup_mocks(monkeypatch)
    monkeypatch.setattr(ve, "_VISION_CACHE_MAX", 2)
    for img in (b"a", b"b", b"c"):
        asyncio.run(ve._vision_extract_cached([img], need_coverage=True))
    assert len(ve._VISION_CACHE) == 2
    assert ve._vision_cache_key([b"a"], "coverage") not in ve._VISION_CACHE  # 最舊被淘汰


def test_cached_plain_mode_uses_ollama_multi(monkeypatch):
    calls = {"multi": 0}

    def fake_multi(images, prompt, model=None, options=None, keep_alive=None):
        calls["multi"] += 1
        return "共同特徵描述"

    async def fake_focus(target):
        pass

    monkeypatch.setattr(ve._oc, "analyze_multi_images_bytes", fake_multi)
    monkeypatch.setattr(ve.guardian, "request_focus", fake_focus)

    coverage, visual = asyncio.run(ve._vision_extract_cached([b"x", b"y"], need_coverage=False))
    assert coverage == "full"  # need_coverage=False 時為佔位值
    assert visual == "共同特徵描述"
    assert calls["multi"] == 1
