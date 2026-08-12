"""VRAM coexist 判定回歸測試（2026-07-27）。

固化 2026-07-26 23:45-23:56 實測 log 的每一筆數值 —— 舊邏輯對這些全回 True，
其中 free=0.1G/reserved=16.2G 那筆是明顯誤判，且對應到一次 504（>300s）。

執行：cd backend && pytest tests/test_vram_coexist.py -v
"""
from __future__ import annotations

import pytest

from app.services.ai import vram_manager as vm

_GIB = 1024 ** 3
_TOTAL = int(15.9 * _GIB)   # RTX 5070 Ti 16GB 實際可報告值


@pytest.fixture()
def guardian(monkeypatch):
    g = vm.VRAMGuardian()
    return g


def _stub(monkeypatch, free_g, reserved_g, total_g=15.9):
    monkeypatch.setattr(
        vm.VRAMGuardian, "_comfyui_vram",
        lambda self: (int(free_g * _GIB), int(reserved_g * _GIB), int(total_g * _GIB)),
    )


# ── 實測 log 逐筆固化 ────────────────────────────────────────────────────────

@pytest.mark.parametrize("ts, free, reserved, expected", [
    # 時間          free  reserved  應否共存
    ("23:45:47",    1.8,   13.0,    False),   # 舊版 True（勉強成功）
    ("23:48:30",    5.0,    9.9,    False),   # 舊版 True
    ("23:49:21",    5.0,    9.9,    False),   # 舊版 True
    ("23:50:09",    5.0,    9.9,    False),   # 舊版 True → 這次 504
    ("23:56:00",    0.1,   16.2,    False),   # 舊版 True → 最離譜；且已 overcommit
])
def test_real_log_samples_are_rejected(monkeypatch, guardian, ts, free, reserved, expected):
    _stub(monkeypatch, free, reserved)
    assert guardian._comfyui_can_coexist() is expected, ts


# ── 決策表 ──────────────────────────────────────────────────────────────────

def test_plenty_of_free_coexists(monkeypatch, guardian):
    """free 達 COMFYUI_REQUIRED_VRAM_GB → 共存（不必卸載，省冷載時間）。"""
    _stub(monkeypatch, free_g=9.0, reserved_g=0.5)
    assert guardian._comfyui_can_coexist() is True


def test_resident_with_enough_free_coexists(monkeypatch, guardian):
    """checkpoint 已駐留 + free 達 resident 門檻 → 共存（需求降為增量）。"""
    _stub(monkeypatch, free_g=6.5, reserved_g=8.0)
    assert guardian._comfyui_can_coexist() is True


def test_resident_but_free_below_threshold_rejected(monkeypatch, guardian):
    """核心回歸：reserved 高不再等於安全。舊版此情境回 True。"""
    _stub(monkeypatch, free_g=5.9, reserved_g=12.0)
    assert guardian._comfyui_can_coexist() is False


def test_overcommit_rejected_even_with_free(monkeypatch, guardian):
    """torch 保留超過顯卡容量 → 已溢出系統 RAM，即使 free 看起來夠也不共存。"""
    _stub(monkeypatch, free_g=9.0, reserved_g=16.2)
    assert guardian._comfyui_can_coexist() is False


def test_unknown_total_does_not_trigger_overcommit(monkeypatch, guardian):
    """/system_stats 缺 vram_total（回 0）時不得誤判成 overcommit。"""
    _stub(monkeypatch, free_g=9.0, reserved_g=5.0, total_g=0)
    assert guardian._comfyui_can_coexist() is True


def test_query_failure_falls_back_to_unload(monkeypatch, guardian):
    """任何查詢失敗 → False（保守退回卸載），不得因例外而放行。"""
    def boom(self):
        raise RuntimeError("comfyui down")
    monkeypatch.setattr(vm.VRAMGuardian, "_comfyui_vram", boom)
    assert guardian._can_coexist("comfyui") is False


# ── /free 真釋放 ────────────────────────────────────────────────────────────

def test_unload_comfyui_sends_free_memory(monkeypatch, guardian):
    """必須同時送 unload_models 與 free_memory —— 只送前者不會降 reserved。"""
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent["url"] = url
        sent["json"] = json
        class R:
            status_code = 200
        return R()

    _stub(monkeypatch, free_g=1.0, reserved_g=12.0)
    monkeypatch.setattr(vm.requests, "post", fake_post)
    guardian._unload_comfyui_sync()

    assert sent["json"] == {"unload_models": True, "free_memory": True}
    assert sent["url"].endswith("/free")


def test_unload_comfyui_survives_post_failure(monkeypatch, guardian):
    """resilient errors：ComfyUI 沒開也不能讓 focus 切換炸掉。"""
    def boom(*a, **kw):
        raise ConnectionError("refused")
    _stub(monkeypatch, free_g=1.0, reserved_g=12.0)
    monkeypatch.setattr(vm.requests, "post", boom)
    guardian._unload_comfyui_sync()  # 不得 raise
