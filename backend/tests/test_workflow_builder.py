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
