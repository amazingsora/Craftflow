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
