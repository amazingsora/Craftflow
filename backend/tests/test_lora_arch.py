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
