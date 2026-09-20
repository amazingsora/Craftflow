"""_lora_arch 架構偵測單元測試（2026-06-21）。

以 tmp_path 造最小 safetensors header（含 __metadata__.ss_base_model_version）驗證偵測；
不需真實 LoRA 檔。執行：cd backend && pytest tests/test_lora_arch.py
"""
import json
import struct

import pytest

from app.services.ai import workflow_builder as wb


def _write_safetensors(path, metadata: dict):
    """寫一個最小可解析的 safetensors：8-byte header_len + JSON header。"""
    header = {
        "__metadata__": metadata,
        "dummy": {"dtype": "F16", "shape": [1], "data_offsets": [0, 2]},
    }
    blob = json.dumps(header).encode("utf-8")
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(blob)))
        f.write(blob)
        f.write(b"\x00\x00")


@pytest.fixture(autouse=True)
def _clear_cache():
    wb._LORA_ARCH_CACHE.clear()
    yield
    wb._LORA_ARCH_CACHE.clear()


def test_sdxl_base_detected(tmp_path, monkeypatch):
    monkeypatch.setattr(wb, "COMFYUI_LORAS_DIR", tmp_path)
    _write_safetensors(tmp_path / "x.safetensors", {"ss_base_model_version": "sdxl_base_v1-0"})
    assert wb._lora_arch("x.safetensors") == "sdxl"


def test_sd15_base_detected(tmp_path, monkeypatch):
    monkeypatch.setattr(wb, "COMFYUI_LORAS_DIR", tmp_path)
    _write_safetensors(tmp_path / "y.safetensors", {"ss_base_model_version": "sd_v1-5"})
    assert wb._lora_arch("y.safetensors") == "sd15"


def test_unknown_metadata_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(wb, "COMFYUI_LORAS_DIR", tmp_path)
    _write_safetensors(tmp_path / "z.safetensors", {})
    assert wb._lora_arch("z.safetensors") is None


def test_missing_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(wb, "COMFYUI_LORAS_DIR", tmp_path)
    assert wb._lora_arch("nope.safetensors") is None


def test_cache_hit(tmp_path, monkeypatch):
    monkeypatch.setattr(wb, "COMFYUI_LORAS_DIR", tmp_path)
    _write_safetensors(tmp_path / "c.safetensors", {"ss_base_model_version": "sdxl_base_v1-0"})
    assert wb._lora_arch("c.safetensors") == "sdxl"
    # 移除檔案後仍回 sdxl → 證明走快取
    (tmp_path / "c.safetensors").unlink()
    assert wb._lora_arch("c.safetensors") == "sdxl"


# ── lora_trigger_words（SYNC-005 軌 L，2026-09-19）────────────────────────────
# 「新增會被執行的東西時，測試必須真的執行它」（CLAUDE.md 編程檢查點 1）：
# 下面每一項都真的讀檔並比對字串，不是只驗欄位存在。

def _write_civitai_info(path, trained_words):
    path.write_text(json.dumps({"trainedWords": trained_words}), encoding="utf-8")


def test_trigger_words_preserves_zero_width_space(tmp_path, monkeypatch):
    """核心回歸：觸發詞的 U+200B 是訓練 caption 的一部分，strip 掉就打不中。

    實例 Blue_archive_style.safetensors 的 trainedWords 是 'Blue archive style\u200b'，
    使用者手打打不出零寬空格 —— 自動注入的價值就在這裡，正規化等於白做。
    """
    monkeypatch.setattr(wb, "COMFYUI_LORAS_DIR", tmp_path)
    wb._LORA_TRIGGER_CACHE.clear()
    _write_civitai_info(tmp_path / "ba.civitai.info", ["Blue archive style\u200b"])
    out = wb.lora_trigger_words([{"model": "ba.safetensors", "weight": 0.8}])
    assert out == ["Blue archive style\u200b"]
    assert "\u200b" in out[0]          # 零寬空格必須還在
    assert out[0] != out[0].replace("\u200b", "")


def test_trigger_words_strips_only_ordinary_whitespace(tmp_path, monkeypatch):
    monkeypatch.setattr(wb, "COMFYUI_LORAS_DIR", tmp_path)
    wb._LORA_TRIGGER_CACHE.clear()
    _write_civitai_info(tmp_path / "x.civitai.info", ["  padded  ", "", "   "])
    assert wb.lora_trigger_words([{"model": "x.safetensors"}]) == ["padded"]


def test_trigger_words_dedups_across_loras(tmp_path, monkeypatch):
    monkeypatch.setattr(wb, "COMFYUI_LORAS_DIR", tmp_path)
    wb._LORA_TRIGGER_CACHE.clear()
    _write_civitai_info(tmp_path / "a.civitai.info", ["shared", "only_a"])
    _write_civitai_info(tmp_path / "b.civitai.info", ["shared", "only_b"])
    out = wb.lora_trigger_words([{"model": "a.safetensors"}, {"model": "b.safetensors"}])
    assert out == ["shared", "only_a", "only_b"]


@pytest.mark.parametrize("loras", [
    None, [], [{}], [{"model": ""}], [{"model": "   "}], ["壞資料"], [{"model": "缺檔.safetensors"}],
])
def test_trigger_words_is_best_effort(tmp_path, monkeypatch, loras):
    """resilient errors：任何壞輸入都回 []，絕不讓生成失敗。"""
    monkeypatch.setattr(wb, "COMFYUI_LORAS_DIR", tmp_path)
    wb._LORA_TRIGGER_CACHE.clear()
    assert wb.lora_trigger_words(loras) == []


def test_trigger_words_survives_broken_json(tmp_path, monkeypatch):
    monkeypatch.setattr(wb, "COMFYUI_LORAS_DIR", tmp_path)
    wb._LORA_TRIGGER_CACHE.clear()
    (tmp_path / "bad.civitai.info").write_text("{ not json", encoding="utf-8")
    assert wb.lora_trigger_words([{"model": "bad.safetensors"}]) == []


# ── LoRA 目錄不存在的靜默失效（SYNC-005 L3，2026-09-20）──────────────────────

def test_missing_lora_dir_warns_once_and_degrades_safely(tmp_path, monkeypatch, caplog):
    """實錘回歸：`COMFYUI_LORAS_DIR` 指到不存在的目錄時，`_lora_arch` 與
    `lora_trigger_words` 都會安靜回 None／[]，於是架構健檢空轉、觸發詞永遠是空的。

    2026-09-20 實況：.env 那行被註解掉 → 吃預設 `C:\\ComfyUI\\models\\loras`（不存在）
    → #648/#649 掛了 LoRA 但 log 沒有「LoRA 觸發詞已補入正向」，軌 L 等於沒做。
    要求：**不得讓生成失敗，但必須留下一次 WARNING**。
    """
    import logging
    missing = tmp_path / "does_not_exist"
    monkeypatch.setattr(wb, "COMFYUI_LORAS_DIR", missing)
    monkeypatch.setattr(wb, "_LORA_DIR_WARNED", False)
    wb._LORA_ARCH_CACHE.clear()
    wb._LORA_TRIGGER_CACHE.clear()

    with caplog.at_level(logging.WARNING):
        assert wb.lora_trigger_words([{"model": "x.safetensors"}]) == []   # 不炸
        assert wb._lora_arch("x.safetensors") is None                      # 不炸
        assert wb.lora_trigger_words([{"model": "y.safetensors"}]) == []   # 再叫一次

    warns = [r for r in caplog.records if "LoRA 目錄不存在" in r.message]
    assert len(warns) == 1, "warn-once：同一個問題只能吵一次（沿用 _PROFILE_MISS_WARNED 慣例）"


def test_existing_lora_dir_does_not_warn(tmp_path, monkeypatch, caplog):
    import logging
    monkeypatch.setattr(wb, "COMFYUI_LORAS_DIR", tmp_path)
    monkeypatch.setattr(wb, "_LORA_DIR_WARNED", False)
    wb._LORA_TRIGGER_CACHE.clear()
    with caplog.at_level(logging.WARNING):
        wb.lora_trigger_words([{"model": "x.safetensors"}])
    assert not [r for r in caplog.records if "LoRA 目錄不存在" in r.message]
