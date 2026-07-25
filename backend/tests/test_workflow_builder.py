"""workflow_builder 單元測試（A3，2026-06-13）。

ComfyUI / 檔案系統以 tmp_path 與 monkeypatch 隔離；不測 _run（需 ComfyUI）。
執行：cd backend && pytest tests/test_workflow_builder.py
"""
import json

import pytest
from fastapi import HTTPException

from app.models.art_style import ArtStyle
from app.services.ai import workflow_builder as wb
from app.services.ai.prompt_engine import PromptStyle


def _api_wf(ckpt="embedded.safetensors") -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["1", 1]}},
        "3": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "seed": -1, "noise_seed": -1, "steps": 20,
        }},
    }


# ── _replace_negative_seeds ───────────────────────────────────────────────────

def test_replace_negative_seeds():
    wf = _api_wf()
    wf["3"]["inputs"]["seed"] = -1
    wf["4"] = {"class_type": "SomeNode", "inputs": {"seed": 42}}          # 正值不動
    wf["5"] = {"class_type": "Other", "inputs": {"seed": ["3", 0]}}       # link 不動
    wb._replace_negative_seeds(wf, 12345)
    assert wf["3"]["inputs"]["seed"] == 12345
    assert wf["3"]["inputs"]["noise_seed"] == 12345
    assert wf["4"]["inputs"]["seed"] == 42
    assert wf["5"]["inputs"]["seed"] == ["3", 0]


# ── _inject_loras ─────────────────────────────────────────────────────────────

def test_inject_loras_chain_and_rewire():
    wf = _api_wf()
    wf["6"] = {"class_type": "IPAdapterAdvanced", "inputs": {"model": ["1", 0]}}
    wb._inject_loras(wf, [
        {"model": "styleA.safetensors", "weight": 0.8},
        {"model": "styleB.safetensors", "weight": 0.6},
    ])
    # 鏈：ckpt → _lora_0 → _lora_1
    assert wf["_lora_0"]["inputs"]["model"] == ["1", 0]
    assert wf["_lora_1"]["inputs"]["model"] == ["_lora_0", 0]
    assert wf["_lora_1"]["inputs"]["strength_model"] == 0.6
    # KSampler / IPA / CLIP 全部改接最後一顆 LoRA
    assert wf["3"]["inputs"]["model"] == ["_lora_1", 0]
    assert wf["6"]["inputs"]["model"] == ["_lora_1", 0]
    assert wf["2"]["inputs"]["clip"] == ["_lora_1", 1]


@pytest.mark.parametrize("loras", [None, [], [{"model": "  "}], [{"weight": 1.0}]])
def test_inject_loras_noop_on_empty(loras):
    wf = _api_wf()
    before = json.dumps(wf, sort_keys=True)
    wb._inject_loras(wf, loras)
    assert json.dumps(wf, sort_keys=True) == before


def test_inject_loras_no_checkpoint_noop():
    wf = {"3": {"class_type": "KSampler", "inputs": {"model": ["9", 0]}}}
    wb._inject_loras(wf, [{"model": "x.safetensors"}])
    assert "_lora_0" not in wf


# ── Art style helpers ─────────────────────────────────────────────────────────

def test_compile_overrides_and_extra_tags():
    assert wb._compile_overrides(None) == {}
    st = ArtStyle(name="t", quality_prefix="best quality", negative="bad", extra_tags=" tag1, tag2 ")
    assert wb._compile_overrides(st) == {
        "quality_prefix_override": "best quality",
        "negative_override": "bad",
    }
    assert wb._extra_tags(st) == "tag1, tag2"
    assert wb._extra_tags(None) == ""


def test_resolve_style_priority(monkeypatch):
    monkeypatch.setattr(wb, "_detect_style", lambda w="x": PromptStyle.SDXL)
    # base_style 有效 → 直接採用
    assert wb._resolve_style(ArtStyle(name="a", base_style="illustrious")) == PromptStyle.ILLUSTRIOUS
    # base_style 無效字串 → 落回偵測
    assert wb._resolve_style(ArtStyle(name="b", base_style="not-a-style")) == PromptStyle.SDXL
    # 無 art_style → 偵測
    assert wb._resolve_style(None) == PromptStyle.SDXL


# ── P1: prompt_profiles.yml（workflow 級 override）─────────────────────────────

def test_load_prompt_profiles_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(wb, "_PROMPT_PROFILES_YML", tmp_path / "nope.yml")
    assert wb._load_prompt_profiles() == {}


def test_load_prompt_profiles_reads_yaml(tmp_path, monkeypatch):
    yml = tmp_path / "prompt_profiles.yml"
    yml.write_text(
        "profiles:\n"
        "  Standard_V37.json:\n"
        "    quality_prefix: \"masterpiece, best quality, absurdres\"\n"
        "    negative: \"worst quality, low quality\"\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(wb, "_PROMPT_PROFILES_YML", yml)
    profiles = wb._load_prompt_profiles()
    assert profiles["Standard_V37.json"]["quality_prefix"] == "masterpiece, best quality, absurdres"


def test_workflow_profile_overrides_unregistered_workflow_is_noop(monkeypatch):
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {})
    assert wb._workflow_profile_overrides("text_to_image.json") == {}


def test_workflow_profile_overrides_only_includes_set_fields(monkeypatch):
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {
        "Standard_V37.json": {"quality_prefix": "masterpiece, absurdres", "negative": "worst quality"},
    })
    out = wb._workflow_profile_overrides("Standard_V37.json")
    assert out == {
        "quality_prefix_override": "masterpiece, absurdres",
        "negative_override": "worst quality",
    }
    # quality_suffix 未登錄 → 不佔位（compile() 預設行為才生效）
    assert "quality_suffix_override" not in out


def test_workflow_profile_overrides_includes_negative_extra(monkeypatch):
    """R4：negative（取代）與 negative_extra（補充）可同時登錄，各自映射到獨立 override key。"""
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {
        "Standard_V37.json": {"negative": "worst quality", "negative_extra": "extra neg"},
    })
    out = wb._workflow_profile_overrides("Standard_V37.json")
    assert out["negative_override"] == "worst quality"
    assert out["negative_extra_override"] == "extra neg"


def test_workflow_profile_overrides_negative_extra_alone(monkeypatch):
    """只登錄 negative_extra（無 negative 取代）→ 只放 negative_extra_override，不佔 negative_override。"""
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {
        "Standard_V37.json": {"negative_extra": "just extra"},
    })
    out = wb._workflow_profile_overrides("Standard_V37.json")
    assert out == {"negative_extra_override": "just extra"}


def test_resolve_prompt_overrides_priority_art_style_over_workflow(monkeypatch):
    """art_style 有值時必須贏過 workflow profile（即便 workflow profile 也有登錄該欄位）。"""
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {
        "Standard_V37.json": {"quality_prefix": "wf-prefix", "negative": "wf-negative"},
    })
    st = ArtStyle(name="s", quality_prefix="style-prefix", negative="")
    out = wb._resolve_prompt_overrides(st, "Standard_V37.json")
    assert out["quality_prefix_override"] == "style-prefix"  # art_style 贏
    assert out["negative_override"] == "wf-negative"          # art_style 該欄位留白 → workflow 生效


def test_resolve_prompt_overrides_no_art_style_uses_workflow_profile(monkeypatch):
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {
        "Standard_V37.json": {"quality_prefix": "wf-prefix", "negative": "wf-negative"},
    })
    out = wb._resolve_prompt_overrides(None, "Standard_V37.json")
    assert out == {"quality_prefix_override": "wf-prefix", "negative_override": "wf-negative"}


def test_resolve_prompt_overrides_unregistered_workflow_zero_regression(monkeypatch):
    """未登錄 workflow：無 art_style → 空 dict，與改動前 _compile_overrides(None) 行為一致。"""
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {})
    assert wb._resolve_prompt_overrides(None, "text_to_image.json") == {}


# ── P4: _prompt_profile_source（debug 來源標註）────────────────────────────────

def test_prompt_profile_source_registered_workflow(monkeypatch):
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {
        "Standard_V37.json": {"quality_prefix": "x"},
    })
    assert wb._prompt_profile_source(None, "Standard_V37.json") == "profile: Standard_V37.json"


def test_prompt_profile_source_unregistered_is_family_fallback(monkeypatch):
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {})
    assert wb._prompt_profile_source(None, "text_to_image.json") == "family fallback"


def test_prompt_profile_source_art_style_overlay(monkeypatch):
    """art_style 有覆寫欄位時附加 +art_style# 標註（疊加於 profile 或 family fallback）。"""
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {})
    st = ArtStyle(name="s", quality_prefix="style-prefix", negative="")
    st.id = 7
    assert wb._prompt_profile_source(st, "text_to_image.json") == "family fallback +art_style#7"


# ── _load_workflow ────────────────────────────────────────────────────────────

@pytest.fixture
def wf_dirs(tmp_path, monkeypatch):
    custom = tmp_path / "custom"
    system = tmp_path / "system"
    custom.mkdir()
    system.mkdir()
    monkeypatch.setattr(wb, "CUSTOM_WORKFLOWS_DIR", custom)
    monkeypatch.setattr(wb, "_SYSTEM_WORKFLOW_DIR", system)
    return custom, system


def test_load_workflow_missing_raises(wf_dirs):
    with pytest.raises(FileNotFoundError):
        wb._load_workflow("nope.json")


def test_load_workflow_ui_format_rejected(wf_dirs):
    custom, _ = wf_dirs
    (custom / "ui.json").write_text(json.dumps({"nodes": [], "links": []}), encoding="utf-8")
    with pytest.raises(HTTPException) as exc:
        wb._load_workflow("ui.json")
    assert exc.value.status_code == 422


def test_load_workflow_system_respects_global_checkpoint(wf_dirs, monkeypatch):
    _, system = wf_dirs
    (system / "t2i.json").write_text(json.dumps(_api_wf("embedded.safetensors")), encoding="utf-8")
    monkeypatch.setattr(wb.state, "get_checkpoint", lambda: "global.safetensors")
    wf = wb._load_workflow("t2i.json")
    assert wf["1"]["inputs"]["ckpt_name"] == "global.safetensors"  # 系統 workflow 被全域覆寫


def test_load_workflow_custom_keeps_embedded_checkpoint(wf_dirs, monkeypatch):
    custom, _ = wf_dirs
    (custom / "my.json").write_text(json.dumps(_api_wf("embedded.safetensors")), encoding="utf-8")
    monkeypatch.setattr(wb.state, "get_checkpoint", lambda: "global.safetensors")
    wf = wb._load_workflow("my.json")
    assert wf["1"]["inputs"]["ckpt_name"] == "embedded.safetensors"  # 自訂 workflow 不覆寫


def test_load_workflow_custom_dir_has_priority(wf_dirs, monkeypatch):
    custom, system = wf_dirs
    (custom / "same.json").write_text(json.dumps(_api_wf("from-custom")), encoding="utf-8")
    (system / "same.json").write_text(json.dumps(_api_wf("from-system")), encoding="utf-8")
    monkeypatch.setattr(wb.state, "get_checkpoint", lambda: "")
    wf = wb._load_workflow("same.json")
    assert wf["1"]["inputs"]["ckpt_name"] == "from-custom"


def test_load_workflow_strips_comment(wf_dirs, monkeypatch):
    custom, _ = wf_dirs
    data = _api_wf()
    data["_comment"] = "note"
    (custom / "c.json").write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(wb.state, "get_checkpoint", lambda: "")
    assert "_comment" not in wb._load_workflow("c.json")


# ── _detect_style ─────────────────────────────────────────────────────────────

def test_detect_style_via_mapping(wf_dirs, monkeypatch):
    custom, _ = wf_dirs
    (custom / "t.json").write_text(
        json.dumps(_api_wf("novaAnimeXL_ilV190.safetensors")), encoding="utf-8")
    monkeypatch.setattr(wb.state, "get_checkpoint", lambda: "")
    monkeypatch.setattr(wb, "_load_checkpoint_styles", lambda: {"novaanime": "illustrious"})
    assert wb._detect_style("t.json") == PromptStyle.ILLUSTRIOUS


def test_detect_style_fallback_sdxl(wf_dirs, monkeypatch):
    monkeypatch.setattr(wb, "_load_checkpoint_styles", lambda: {})
    assert wb._detect_style("missing.json") == PromptStyle.SDXL


# ── _inject_loras：model/clip 路徑經中介節點時仍要接上（2026-06-20 回歸）──────

def test_inject_loras_through_intermediary_node():
    """model/clip 先經過內建的 'Lora Loader (LoraManager)' 再到 KSampler 時，
    注入的 LoRA 必須仍接上 pipeline（舊版型別比對會漏接 → 孤兒節點）。"""
    wf = {
        "30": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "base.safetensors"}},
        "5":  {"class_type": "Lora Loader (LoraManager)", "inputs": {"model": ["30", 0], "clip": ["30", 1]}},
        "43": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["5", 1]}},
        "46": {"class_type": "KSampler", "inputs": {"model": ["5", 0]}},
    }
    wb._inject_loras(wf, [{"model": "extra.safetensors", "weight": 0.8}])
    # 注入的 _lora_0 必須被某節點引用（真的生效，非孤兒）
    used = any(
        isinstance(n, dict) and any(
            isinstance(v, list) and v and str(v[0]) == "_lora_0"
            for v in n.get("inputs", {}).values()
        )
        for n in wf.values()
    )
    assert used, "_lora_0 應接上 pipeline"
    # LoraManager#5 的 model/clip 應改成吃 _lora_0；vae 不受影響
    assert wf["5"]["inputs"]["model"] == ["_lora_0", 0]
    assert wf["5"]["inputs"]["clip"] == ["_lora_0", 1]
    # _lora_0 的根仍是 checkpoint
    assert wf["_lora_0"]["inputs"]["model"] == ["30", 0]


def test_inject_loras_direct_consumer_still_works():
    """既有情境（KSampler.model 直接指向 checkpoint）不可退化。"""
    wf = _api_wf()
    wb._inject_loras(wf, [{"model": "x.safetensors", "weight": 0.7}])
    assert wf["3"]["inputs"]["model"] == ["_lora_0", 0]


# ── _is_custom_workflow：自訂 Workflow 模式判定（2026-06-20 全域 LoRA 閘控）──────

def test_is_custom_workflow(tmp_path, monkeypatch):
    (tmp_path / "Standard_V36.json").write_text("{}")
    monkeypatch.setattr(wb, "CUSTOM_WORKFLOWS_DIR", tmp_path)
    assert wb._is_custom_workflow("Standard_V36.json") is True      # 在 custom 目錄 → workflow 模式
    assert wb._is_custom_workflow("text_to_image.json") is False    # 不在 → checkpoint 模式（系統）
