"""gen_profile 單元測試（R3, 2026-06-20）。
執行：cd backend && pytest tests/test_gen_profile.py
"""
from app.services.ai import gen_profile as gp


def test_known_families_steps():
    assert gp.get_profile("sdxl").steps == 20
    assert gp.get_profile("illustrious").steps is None  # R3：不覆寫，沿用 workflow JSON
    assert gp.get_profile("pony").steps == 20
    assert gp.get_profile("noobai").steps == 20


def test_unknown_family_falls_back_to_default():
    p = gp.get_profile("does-not-exist")
    assert p.family == "sdxl" and p.steps == 20


def test_coverage_cn_defaults_unchanged():
    p = gp.get_profile("illustrious")
    assert p.coverage_cn_weight["partial"] == 0.6
    assert p.coverage_cn_weight["bust"] == 0.5
    assert p.coverage_cn_end_pct["full"] == 0.85
    assert p.full_cn_weight is None      # 預設沿用滑桿（維持 CN≥0.75 / 現況）


def test_resolve_profile_reads_embedded_checkpoint(monkeypatch):
    wf = {"1": {"class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "fabricatedXL_v70.safetensors"}}}
    monkeypatch.setattr("app.services.ai.workflow_builder._load_workflow", lambda name: wf)
    profile, family = gp.resolve_profile_for_workflow("Standard_V36.json")
    assert family == "illustrious"
    assert profile.steps is None


def test_resolve_profile_fallback_to_global_checkpoint(monkeypatch):
    monkeypatch.setattr("app.services.ai.workflow_builder._load_workflow",
                        lambda name: (_ for _ in ()).throw(RuntimeError("no wf")))
    monkeypatch.setattr("app.core.state.get_checkpoint", lambda: "illustriousXL.safetensors")
    profile, family = gp.resolve_profile_for_workflow("whatever.json")
    assert family == "illustrious"


def test_resolve_profile_total_failure_is_safe(monkeypatch):
    monkeypatch.setattr("app.services.ai.workflow_builder._load_workflow",
                        lambda name: (_ for _ in ()).throw(RuntimeError("no wf")))
    monkeypatch.setattr("app.core.state.get_checkpoint", lambda: "")
    profile, family = gp.resolve_profile_for_workflow("whatever.json")
    assert family == "sdxl" and profile.steps == 20


def test_illustrious_uses_anime_lineart_like_v35():
    # 對齊真 V35(data/custom_workflows)內建鏈：AnimeLineArt（非 Canny）
    assert gp.get_profile("illustrious").cn_preprocessor == "anime_lineart"
    assert gp.get_profile("sdxl").cn_preprocessor == "anime_lineart"


# ── G0 Anima 能力閘控（2026-07-14）────────────────────────────────────────────

def test_anima_profile_disables_ipa_and_cn():
    """Anima 非 SDXL：無 IP-Adapter、CN 僅 LLLite → 兩能力旗標皆 False（G0 閘控依據）。"""
    p = gp.get_profile("anima")
    assert p.family == "anima"
    assert p.ipa_enabled is False
    assert p.cn_enabled is False
    assert p.steps is None  # KSampler 由內部節點鏈驅動，後端不覆寫


def test_resolve_profile_reads_unet_loader_for_anima(monkeypatch):
    """Anima 工作流無 CheckpointLoaderSimple，須改讀 UNETLoader.unet_name → 解析到 anima family。"""
    wf = {"1": {"class_type": "UNETLoader",
                "inputs": {"unet_name": "anima_baseV10.safetensors"}}}
    monkeypatch.setattr("app.services.ai.workflow_builder._load_workflow", lambda name: wf)
    profile, family = gp.resolve_profile_for_workflow("AnimaStandardV7.json")
    assert family == "anima"
    assert profile.ipa_enabled is False and profile.cn_enabled is False


def test_resolve_profile_sdxl_checkpoint_loader_still_wins(monkeypatch):
    """零回歸：有 CheckpointLoaderSimple 的 SDXL 工作流不受 UNETLoader 分支影響。"""
    wf = {"1": {"class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "fabricatedXL_v70.safetensors"}},
          "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "anima_baseV10.safetensors"}}}
    monkeypatch.setattr("app.services.ai.workflow_builder._load_workflow", lambda name: wf)
    _, family = gp.resolve_profile_for_workflow("Standard_V37.json")
    assert family == "illustrious"  # CheckpointLoaderSimple 優先，UNETLoader 僅在其缺席時 fallback
