"""capability 邊界測試（B2, 2026-06-20）。
執行：cd backend && pytest tests/test_capability.py
"""
from app.services.ai import capability as cap


def test_resolve_family_known():
    assert cap.resolve_family("fabricatedXL_v70.safetensors") == "illustrious"
    assert cap.resolve_family("illustriousXL.safetensors") == "illustrious"
    assert cap.resolve_family("flux1-dev.safetensors") == "flux"
    assert cap.resolve_family("ponyDiffusionXL.safetensors") == "pony"


def test_resolve_family_unknown_fallback_sdxl():
    assert cap.resolve_family("totallyUnknownModel.safetensors") == "sdxl"
    assert cap.resolve_family("") == "sdxl"


def test_capability_illustrious_supports_injection():
    c = cap.resolve_capability({}, "fabricatedXL_v70.safetensors")
    assert c["family"] == "illustrious"
    assert c["ipa_supported"] is True
    assert c["cn_supported"] is True
    assert c["models"] is not None


def test_capability_flux_no_injection():
    c = cap.resolve_capability({}, "flux1-dev.safetensors")
    assert c["family"] == "flux"
    assert c["ipa_supported"] is False
    assert c["cn_supported"] is False
    assert c["models"] is None


def test_capability_node_present_overrides(monkeypatch):
    import app.services.ai.capability as capmod
    monkeypatch.setattr(capmod, "_wf_has_ipa", lambda wf: True)
    monkeypatch.setattr(capmod, "_wf_has_controlnet", lambda wf: True)
    c = cap.resolve_capability({}, "flux1-dev.safetensors")
    assert c["ipa_supported"] is True
    assert c["cn_supported"] is True


# ── SYNC-002 A1b（2026-09-15）：LLLite 偵測快取不得被失敗毒化 ──────────────────
# 實錘（data/logs/backend.log）：09-14 23:27 探測 ok → 09-15 02:08 探測失敗
# （ComfyUI 該瞬間沒開）→ 02:23 起出圖成功（ComfyUI 已恢復）卻再也沒有第 19 次探測，
# 「LLLite 不可用」印了 28 次全是讀毒化快取。純重開 ComfyUI 救不回來，只能重啟後端。
import time

from app.services import comfyui_client as cc


def _reset():
    cc.reset_lllite_cache()
    cap._LLLITE_UNAVAILABLE_WARNED.clear()


def test_detect_lllite_failure_is_not_cached_forever(monkeypatch):
    """失敗只快取到退避期滿；期滿後會真的重探，ComfyUI 起來即自動復原。"""
    _reset()
    calls = {"n": 0}

    def boom(*a, **kw):
        calls["n"] += 1
        raise OSError("connection refused")

    monkeypatch.setattr(cc.requests, "get", boom)
    assert cc.detect_lllite()["available"] is False
    assert calls["n"] == 1
    # 退避期內：不重打 API，直接回上次結果
    assert cc.detect_lllite()["available"] is False
    assert calls["n"] == 1, "退避期內不應重複打 /object_info"
    # 退避期滿 → 下一次呼叫必須真的重探（這就是原缺陷缺的那一步）
    cc._lllite_fail["until"] = time.monotonic() - 1
    assert cc.detect_lllite()["available"] is False
    assert calls["n"] == 2, "退避期滿後必須重新探測，否則就是永久毒化"
    _reset()


def test_detect_lllite_recovers_after_comfyui_comes_up(monkeypatch):
    """先失敗、ComfyUI 起來後重探要能成功，且成功結果永久快取。"""
    _reset()
    state = {"up": False, "n": 0}

    class _Resp:
        ok = True

        @staticmethod
        def json():
            return {"AnimaLLLiteApply_sdscripts": {"input": {"required": {
                "lllite_name": [["anima-lllite-any-test-like-v2.safetensors"]]}}}}

    def fake_get(*a, **kw):
        state["n"] += 1
        if not state["up"]:
            raise OSError("connection refused")
        return _Resp()

    monkeypatch.setattr(cc.requests, "get", fake_get)
    assert cc.detect_lllite()["available"] is False
    state["up"] = True
    cc._lllite_fail["until"] = time.monotonic() - 1      # 模擬退避期滿
    info = cc.detect_lllite()
    assert info["available"] is True
    assert info["weights"] == ["anima-lllite-any-test-like-v2.safetensors"]
    n_after_success = state["n"]
    # 成功後永久快取：再呼叫不得重打 API
    assert cc.detect_lllite()["available"] is True
    assert state["n"] == n_after_success
    _reset()


def test_reset_lllite_cache_clears_failure_backoff(monkeypatch):
    """reset 必須同時清失敗退避——只清成功快取的話，使用者按「重新探測」會沒反應。"""
    _reset()
    monkeypatch.setattr(cc.requests, "get", lambda *a, **kw: (_ for _ in ()).throw(OSError("down")))
    cc.detect_lllite()
    assert cc._lllite_fail is not None
    cc.reset_lllite_cache()
    assert cc._lllite_cache is None and cc._lllite_fail is None
    _reset()


def test_lllite_unavailable_warns_once_per_reason(caplog, monkeypatch):
    """同一 reason 只吵一次（實測 log 曾印 28 次），reason 變了才會再吵。"""
    _reset()
    monkeypatch.setattr(cc, "detect_lllite",
                        lambda: {"available": False, "reason": "探測失敗：down",
                                 "weights": [], "node_class": None})
    with caplog.at_level("WARNING"):
        assert cap._resolve_lllite_weight() is None
        assert cap._resolve_lllite_weight() is None
    assert len([r for r in caplog.records if r.levelname == "WARNING"]) == 1
    caplog.clear()
    monkeypatch.setattr(cc, "detect_lllite",
                        lambda: {"available": False, "reason": "節點未安裝",
                                 "weights": [], "node_class": None})
    with caplog.at_level("WARNING"):
        assert cap._resolve_lllite_weight() is None
    assert len([r for r in caplog.records if r.levelname == "WARNING"]) == 1, "reason 換了要再告警一次"
    _reset()


# ── SYNC-003 A2（2026-09-16）：名稱判定與載入節點矛盾時，不得依名稱注入 ──────────
# 實錘：animagineXL40（SDXL，CheckpointLoaderSimple）被子字串 "anima" 判成 Anima →
# 注入 AnimaLLLiteApply → comfyui.log `created 0 modules`（靜默空轉），IPA/CN 也被閘掉。
# 以下用 monkeypatch 造一個「被判成 anima 的假 SDXL 檔名」，不依賴 yml 內容。
_CKPT_ONLY_WF = {
    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "fakeXL40.safetensors"}},
    "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0]}},
}
_UNET_WF = {
    "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "fakeXL40.safetensors"}},
    "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0]}},
}


def _force_anima(monkeypatch):
    """讓 fakeXL40 被判成 anima，並記錄是否真的去探測 LLLite。"""
    _reset()
    monkeypatch.setattr(cap, "_load_families", lambda: {"xl40": "anima"})
    monkeypatch.setattr(cap, "_LOADER_CONFLICT_WARNED", set())
    calls = []

    def _fake_detect():
        calls.append(1)
        return {"available": True, "reason": "ok", "node_class": "AnimaLLLiteApply_sdscripts",
                "weights": ["anima-lllite-any-test-like-v2.safetensors"]}

    monkeypatch.setattr(cc, "detect_lllite", _fake_detect)
    return calls


def test_loader_family_conflict_blocks_all_fallbacks(monkeypatch, caplog):
    """矛盾 → 不注入任何東西、不去打 /object_info、只告警一次。"""
    calls = _force_anima(monkeypatch)
    with caplog.at_level("WARNING"):
        c = cap.resolve_capability(_CKPT_ONLY_WF, "fakeXL40.safetensors")
        cap.resolve_capability(_CKPT_ONLY_WF, "fakeXL40.safetensors")
    assert c["family"] == "anima"                      # 不猜、不改判
    assert c["family_conflict"] == "loader_mismatch"
    assert c["cn_fallback"] is None                    # → API 閘門會關掉 use_controlnet
    assert c["lllite_weight"] is None
    assert c["lllite_node_class"] is None
    assert c["models"] is None
    assert c["ipa_supported"] is False
    assert c["cn_supported"] is False
    assert calls == [], "矛盾時不應再去探測 LLLite"
    warned = [r for r in caplog.records if r.levelname == "WARNING" and "fakeXL40" in r.getMessage()]
    assert len(warned) == 1, "同一 checkpoint 只告警一次"
    _reset()


def test_unet_workflow_keeps_anima_fallback_chain(monkeypatch):
    """反向對照：真正用 UNETLoader 的 Anima 工作流不受護欄影響，LLLite 候選鏈照舊。"""
    calls = _force_anima(monkeypatch)
    c = cap.resolve_capability(_UNET_WF, "fakeXL40.safetensors")
    assert c["family"] == "anima"
    assert c["family_conflict"] is None
    assert c["cn_fallback"] == "lllite"
    assert c["lllite_weight"] == "anima-lllite-any-test-like-v2.safetensors"
    assert calls, "非矛盾時仍應探測 LLLite"
    _reset()


def test_loader_conflict_needs_structure_info(monkeypatch):
    """讀不到工作流（呼叫端傳 {}）時沒有結構資訊 → 不下判斷，維持依名稱的既有行為。"""
    _force_anima(monkeypatch)
    c = cap.resolve_capability({}, "fakeXL40.safetensors")
    assert c["family_conflict"] is None
    assert c["cn_fallback"] == "lllite"
    _reset()


def test_sdxl_family_never_flagged_as_conflict():
    """SDXL 系家族本來就用 CheckpointLoaderSimple，護欄不得介入（V37/V38 零回歸）。"""
    c = cap.resolve_capability(_CKPT_ONLY_WF, "fabricatedXL_v70.safetensors")
    assert c["family"] == "illustrious"
    assert c["family_conflict"] is None
    assert c["cn_supported"] is True
    assert c["models"] is not None
    assert cap._is_loader_family_conflict(_CKPT_ONLY_WF, "flux") is False, "flux 有一體包，不列入"
