"""VRAM coexist 判定回歸測試（2026-07-27）。

固化 2026-07-26 23:45-23:56 實測 log 的每一筆數值 —— 舊邏輯對這些全回 True，
其中 free=0.1G/reserved=16.2G 那筆是明顯誤判，且對應到一次 504（>300s）。

執行：cd backend && pytest tests/test_vram_coexist.py -v
"""
from __future__ import annotations

import pytest

from app.core.config import COMFYUI_REQUIRED_VRAM_GB, COMFYUI_RESIDENT_MIN_FREE_GB
from app.services.ai import vram_manager as vm

_GIB = 1024 ** 3
# SYNC-005 V3（2026-09-19）：決策表的輸入改為**從門檻推導**，不再寫死數字。
# 原本 free_g=9.0 / 6.5 是照 2026-07-26 的門檻（8 / 6）手算的常數；這次門檻依實測
# 調成 11 / 8（SDXL+CN+CLIPVision+LoRA patch 的真實佔用），那兩個常數就同時失效了。
# 改成符號化之後，測的是「**決策邏輯**是否照門檻走」而不是「門檻等於某個值」——
# 門檻本來就該隨實測調整，鎖住它等於鎖錯對象（同 SYNC-001「測試鎖錯對象」的教訓）。
_ABOVE_REQ = COMFYUI_REQUIRED_VRAM_GB + 1.0        # 足夠跑一次完整載入
_ABOVE_RESIDENT = COMFYUI_RESIDENT_MIN_FREE_GB + 0.5   # 駐留時的增量需求達標
_BELOW_RESIDENT = COMFYUI_RESIDENT_MIN_FREE_GB - 0.1   # 差一點點也不放行
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
# 這組是 2026-07-26 的**歷史誤判樣本**，期望值全 False。門檻調高只會讓它們更該被拒，
# 所以刻意保留原始數字不符號化 —— 它們鎖的是「這些具體情境不可以放行」這件事。

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
    _stub(monkeypatch, free_g=_ABOVE_REQ, reserved_g=0.5)
    assert guardian._comfyui_can_coexist() is True


def test_resident_with_enough_free_coexists(monkeypatch, guardian):
    """checkpoint 已駐留 + free 達 resident 門檻 → 共存（需求降為增量）。"""
    _stub(monkeypatch, free_g=_ABOVE_RESIDENT, reserved_g=8.0)
    assert guardian._comfyui_can_coexist() is True


def test_resident_but_free_below_threshold_rejected(monkeypatch, guardian):
    """核心回歸：reserved 高不再等於安全。舊版此情境回 True。"""
    _stub(monkeypatch, free_g=_BELOW_RESIDENT, reserved_g=12.0)
    assert guardian._comfyui_can_coexist() is False


def test_overcommit_rejected_even_with_free(monkeypatch, guardian):
    """torch 保留超過顯卡容量 → 已溢出系統 RAM，即使 free 看起來夠也不共存。"""
    _stub(monkeypatch, free_g=_ABOVE_REQ, reserved_g=16.2)
    assert guardian._comfyui_can_coexist() is False


def test_unknown_total_does_not_trigger_overcommit(monkeypatch, guardian):
    """/system_stats 缺 vram_total（回 0）時不得誤判成 overcommit。"""
    _stub(monkeypatch, free_g=_ABOVE_REQ, reserved_g=5.0, total_g=0)
    assert guardian._comfyui_can_coexist() is True


def test_query_failure_falls_back_to_unload(monkeypatch, guardian):
    """任何查詢失敗 → False（保守退回卸載），不得因例外而放行。"""
    def boom(self):
        raise RuntimeError("comfyui down")
    monkeypatch.setattr(vm.VRAMGuardian, "_comfyui_vram", boom)
    assert guardian._can_coexist("comfyui") is False


# ── /free 真釋放 ────────────────────────────────────────────────────────────
# ⚠️ 2026-09-20 訂正：本節原本 monkeypatch 的是 ``vm.requests.post``。
#    同日 http_local 重構後，vram_manager 改用共用的 ``SESSION``（一個
#    requests.Session **實例**），patch module-level 的 requests.post 就攔不到了 ——
#    測試從此對著空氣驗證：真的打出 HTTP 到 127.0.0.1:8188，sent 永遠是空 dict。
#    這是第三次「測試鎖錯對象」（前兩次：SYNC-001 名單制、SYNC-005 N13 門檻常數）。
#    型態相同：**驗的是替身，不是真實呼叫路徑**。改 patch ``vm.SESSION``。


def _fake_session(monkeypatch, sent: dict):
    """攔截 vram_manager 實際使用的 SESSION.post，回傳 200。"""
    class R:
        status_code = 200

    def fake_post(url, json=None, timeout=None):
        sent["url"] = url
        sent["json"] = json
        return R()

    monkeypatch.setattr(vm.SESSION, "post", fake_post)


def _fast_wait(monkeypatch, wait=0.2, poll=0.02):
    """把等待參數縮到毫秒級，免得每支測試真的睡 5 秒。"""
    monkeypatch.setattr(vm, "VRAM_FREE_WAIT_SEC", wait)
    monkeypatch.setattr(vm, "VRAM_FREE_POLL_SEC", poll)


def _stub_sequence(monkeypatch, samples):
    """讓 _comfyui_vram 依序回傳 samples 的 (free_g, reserved_g)，用完固定回最後一筆。"""
    box = {"i": 0}

    def _next(self):
        i = min(box["i"], len(samples) - 1)
        box["i"] += 1
        free_g, reserved_g = samples[i]
        return (int(free_g * _GIB), int(reserved_g * _GIB), _TOTAL)

    monkeypatch.setattr(vm.VRAMGuardian, "_comfyui_vram", _next)


def test_unload_comfyui_sends_free_memory(monkeypatch, guardian):
    """必須同時送 unload_models 與 free_memory —— 只送前者不會降 reserved。"""
    sent: dict = {}
    _fast_wait(monkeypatch)
    _stub(monkeypatch, free_g=1.0, reserved_g=12.0)
    _fake_session(monkeypatch, sent)
    guardian._unload_comfyui_sync()

    assert sent["json"] == {"unload_models": True, "free_memory": True}
    assert sent["url"].endswith("/free")


def test_unload_comfyui_survives_post_failure(monkeypatch, guardian):
    """resilient errors：ComfyUI 沒開也不能讓 focus 切換炸掉。"""
    def boom(*a, **kw):
        raise ConnectionError("refused")
    _fast_wait(monkeypatch)
    _stub(monkeypatch, free_g=1.0, reserved_g=12.0)
    monkeypatch.setattr(vm.SESSION, "post", boom)
    assert guardian._unload_comfyui_sync() is False   # 不得 raise，且必須回報失敗


# ── /free 等待驗證（SYNC-006 N14，2026-09-20）───────────────────────────────
# 舊版送出 /free 後隔 2~3ms 就回讀，量到的必然是舊值 → 7/7 次印「reserved 未下降」
# 的假警報後照樣放行 Ollama → ComfyUI 權重被擠進共享系統記憶體 → 主 KSampler
# 2.64 it/s 掉到 12.69 s/it。這組測的是「**有沒有真的等**」。


def test_free_waits_until_reserved_drops(monkeypatch, guardian):
    """/free 是非同步排進 executor thread 的，第一次回讀還沒降 → 要繼續等到降。"""
    sent: dict = {}
    _fast_wait(monkeypatch, wait=2.0, poll=0.01)
    # before=12.9 → 前兩次回讀仍是 12.9（尚未生效）→ 第三次才降到 5.0
    _stub_sequence(monkeypatch, [(0.9, 12.9), (0.9, 12.9), (0.9, 12.9), (10.5, 5.0)])
    _fake_session(monkeypatch, sent)
    assert guardian._unload_comfyui_sync() is True


def test_free_returns_false_when_reserved_never_drops(monkeypatch, guardian):
    """等到逾時仍沒降 → False。這正是 --highvram 下實測 7/7 次的情況。"""
    sent: dict = {}
    _fast_wait(monkeypatch, wait=0.1, poll=0.02)
    _stub(monkeypatch, free_g=0.9, reserved_g=12.9)   # 恆定不降
    _fake_session(monkeypatch, sent)
    assert guardian._unload_comfyui_sync() is False


def test_free_does_not_block_forever(monkeypatch, guardian):
    """等待必須有上限 —— 不可因為 ComfyUI 不放就把 LLM 呼叫卡死。"""
    import time as _t
    sent: dict = {}
    _fast_wait(monkeypatch, wait=0.3, poll=0.02)
    _stub(monkeypatch, free_g=0.9, reserved_g=12.9)
    _fake_session(monkeypatch, sent)
    t0 = _t.monotonic()
    guardian._unload_comfyui_sync()
    assert _t.monotonic() - t0 < 2.0


def test_free_optimistic_when_stats_unavailable(monkeypatch, guardian):
    """讀不到基準值就無從驗證 → 樂觀放行，不因診斷不到而擋住功能。"""
    sent: dict = {}
    _fast_wait(monkeypatch)

    def boom(self):
        raise RuntimeError("system_stats down")

    monkeypatch.setattr(vm.VRAMGuardian, "_comfyui_vram", boom)
    _fake_session(monkeypatch, sent)
    assert guardian._unload_comfyui_sync() is True


# ── 微幅下降不算釋放（2026-09-21 實測訂正）─────────────────────────────────
# 實測：`before: free=0.0G reserved=15.2G` → `after: free=0.1G reserved=15.1G`，
# 舊條件 `after < before` 成立 ⇒ 回報「已歸還 0.1G」並判定成功。
# 那不是釋放，是量測雜訊 —— 而且緊接著那一輪跑了 732 秒。


def test_tiny_reserved_drop_is_not_a_release(monkeypatch, guardian):
    """15.2G 只降 0.1G ⇒ 必須判定失敗（低於 VRAM_FREE_MIN_DROP_GB）。"""
    sent: dict = {}
    _fast_wait(monkeypatch, wait=0.1, poll=0.02)
    monkeypatch.setattr(vm, "VRAM_FREE_MIN_DROP_GB", 1.0)
    _stub_sequence(monkeypatch, [(0.0, 15.2), (0.1, 15.1)])
    _fake_session(monkeypatch, sent)
    assert guardian._unload_comfyui_sync() is False


def test_meaningful_drop_is_a_release(monkeypatch, guardian):
    """降幅達門檻才算真的讓出來。"""
    sent: dict = {}
    _fast_wait(monkeypatch, wait=1.0, poll=0.01)
    monkeypatch.setattr(vm, "VRAM_FREE_MIN_DROP_GB", 1.0)
    _stub_sequence(monkeypatch, [(0.0, 15.2), (5.7, 9.5)])
    _fake_session(monkeypatch, sent)
    assert guardian._unload_comfyui_sync() is True


def test_stuck_state_is_logged(monkeypatch, guardian, caplog):
    """reserved 逼近卡容量 ⇒ 要明講「重啟 ComfyUI」，不能只說這張慢。"""
    import logging
    sent: dict = {}
    _fast_wait(monkeypatch, wait=0.1, poll=0.02)
    _stub(monkeypatch, free_g=0.0, reserved_g=15.2)
    _fake_session(monkeypatch, sent)
    with caplog.at_level(logging.ERROR, logger=vm.logger.name):
        guardian._unload_comfyui_sync()
    assert any("重啟 ComfyUI" in r.getMessage() for r in caplog.records)
