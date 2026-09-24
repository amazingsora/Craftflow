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


# ── P1: prompt_profiles.yml（SYNC-007 起以底模家族為鍵，[CN-114]）───────────────
# 機制測試一律用 _as_family() 固定家族：profile 查詢會經 _detect_style() 讀 workflow 取
# checkpoint，不 mock 就會依賴磁碟上有哪些檔（Gemini §2.3 Q5 指出的假陽性來源）。

def _as_family(monkeypatch, style=PromptStyle.ILLUSTRIOUS):
    monkeypatch.setattr(wb, "_detect_style", lambda _w: style)


def test_load_prompt_profiles_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(wb, "_PROMPT_PROFILES_YML", tmp_path / "nope.yml")
    assert wb._load_prompt_profiles() == {}


def test_load_prompt_profiles_reads_yaml(tmp_path, monkeypatch):
    yml = tmp_path / "prompt_profiles.yml"
    yml.write_text(
        "families:\n"
        "  illustrious:\n"
        "    quality_prefix: \"masterpiece, best quality, absurdres\"\n"
        "    negative: \"worst quality, low quality\"\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(wb, "_PROMPT_PROFILES_YML", yml)
    profiles = wb._load_prompt_profiles()
    assert profiles["illustrious"]["quality_prefix"] == "masterpiece, best quality, absurdres"


def test_load_prompt_profiles_ignores_legacy_profiles_key(tmp_path, monkeypatch, caplog):
    """SYNC-007：舊格式 `profiles:`（檔名為鍵）不再讀取，且要告警一次。"""
    yml = tmp_path / "prompt_profiles.yml"
    yml.write_text(
        "profiles:\n  Standard_V38.json:\n    negative: \"old\"\n"
        "families:\n  illustrious:\n    negative: \"new\"\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(wb, "_PROMPT_PROFILES_YML", yml)
    monkeypatch.setattr(wb, "_LEGACY_PROFILES_WARNED", False)
    with caplog.at_level("WARNING"):
        assert wb._load_prompt_profiles() == {"illustrious": {"negative": "new"}}
        assert wb._load_prompt_profiles() == {"illustrious": {"negative": "new"}}
    hits = [r for r in caplog.records if "profiles:" in r.getMessage()]
    assert len(hits) == 1


def test_workflow_profile_overrides_unregistered_workflow_is_noop(monkeypatch):
    _as_family(monkeypatch, PromptStyle.SDXL)
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {})
    assert wb._workflow_profile_overrides("text_to_image.json") == {}


def test_workflow_profile_overrides_only_includes_set_fields(monkeypatch):
    _as_family(monkeypatch, PromptStyle.ILLUSTRIOUS)
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {
        "illustrious": {"quality_prefix": "masterpiece, absurdres", "negative": "worst quality"},
    })
    out = wb._workflow_profile_overrides("Standard_V38.json")
    assert out == {
        "quality_prefix_override": "masterpiece, absurdres",
        "negative_override": "worst quality",
    }
    # quality_suffix 未登錄 → 不佔位（compile() 預設行為才生效）
    assert "quality_suffix_override" not in out


def test_workflow_profile_overrides_includes_negative_extra(monkeypatch):
    """R4：negative（取代）與 negative_extra（補充）可同時登錄，各自映射到獨立 override key。"""
    _as_family(monkeypatch, PromptStyle.ILLUSTRIOUS)
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {
        "illustrious": {"negative": "worst quality", "negative_extra": "extra neg"},
    })
    out = wb._workflow_profile_overrides("Standard_V38.json")
    assert out["negative_override"] == "worst quality"
    assert out["negative_extra_override"] == "extra neg"


def test_workflow_profile_overrides_negative_extra_alone(monkeypatch):
    """只登錄 negative_extra（無 negative 取代）→ 只放 negative_extra_override，不佔 negative_override。"""
    _as_family(monkeypatch, PromptStyle.ILLUSTRIOUS)
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {
        "illustrious": {"negative_extra": "just extra"},
    })
    out = wb._workflow_profile_overrides("Standard_V38.json")
    assert out == {"negative_extra_override": "just extra"}


def test_resolve_prompt_overrides_priority_art_style_over_workflow(monkeypatch):
    """art_style 有值時必須贏過 workflow profile（即便 workflow profile 也有登錄該欄位）。"""
    _as_family(monkeypatch, PromptStyle.ILLUSTRIOUS)
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {
        "illustrious": {"quality_prefix": "wf-prefix", "negative": "wf-negative"},
    })
    st = ArtStyle(name="s", quality_prefix="style-prefix", negative="")
    out = wb._resolve_prompt_overrides(st, "Standard_V38.json")
    assert out["quality_prefix_override"] == "style-prefix"  # art_style 贏
    assert out["negative_override"] == "wf-negative"          # art_style 該欄位留白 → workflow 生效


def test_resolve_prompt_overrides_no_art_style_uses_workflow_profile(monkeypatch):
    _as_family(monkeypatch, PromptStyle.ILLUSTRIOUS)
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {
        "illustrious": {"quality_prefix": "wf-prefix", "negative": "wf-negative"},
    })
    out = wb._resolve_prompt_overrides(None, "Standard_V38.json")
    assert out == {"quality_prefix_override": "wf-prefix", "negative_override": "wf-negative"}


def test_resolve_prompt_overrides_unregistered_workflow_zero_regression(monkeypatch):
    """未登錄 workflow：無 art_style → 空 dict，與改動前 _compile_overrides(None) 行為一致。"""
    _as_family(monkeypatch, PromptStyle.SDXL)
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {})
    assert wb._resolve_prompt_overrides(None, "text_to_image.json") == {}


# ── P4: _prompt_profile_source（debug 來源標註）────────────────────────────────

def test_prompt_profile_source_registered_workflow(monkeypatch):
    _as_family(monkeypatch, PromptStyle.ILLUSTRIOUS)
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {
        "illustrious": {"quality_prefix": "x"},
    })
    assert wb._prompt_profile_source(None, "Standard_V38.json") == "family: illustrious"


def test_prompt_profile_source_unregistered_is_family_fallback(monkeypatch):
    _as_family(monkeypatch, PromptStyle.SDXL)
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {})
    assert wb._prompt_profile_source(None, "text_to_image.json") == "family fallback (STYLE_CONFIG: sdxl)"


def test_prompt_profile_source_art_style_overlay(monkeypatch):
    """art_style 有覆寫欄位時附加 +art_style# 標註（疊加於 profile 或 family fallback）。"""
    _as_family(monkeypatch, PromptStyle.SDXL)
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {})
    st = ArtStyle(name="s", quality_prefix="style-prefix", negative="")
    st.id = 7
    assert wb._prompt_profile_source(st, "text_to_image.json") == "family fallback (STYLE_CONFIG: sdxl) +art_style#7"


# ── P5-5: _workflow_style_extra（畫風 tag／權重 profile 層）────────────────────

def test_workflow_style_extra_unregistered_workflow_is_noop(monkeypatch):
    _as_family(monkeypatch, PromptStyle.SDXL)
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {})
    assert wb._workflow_style_extra("text_to_image.json") == ("", None)


def test_workflow_style_extra_registered_workflow_reads_both_fields(monkeypatch):
    _as_family(monkeypatch, PromptStyle.ILLUSTRIOUS)
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {
        "illustrious": {"style_extra": "flat color, thick outlines", "style_extra_weight": 1.2},
    })
    extra, weight = wb._workflow_style_extra("Standard_V38.json")
    assert extra == "flat color, thick outlines"
    assert weight == 1.2


def test_workflow_style_extra_weight_absent_returns_none(monkeypatch):
    """只登錄 style_extra、不登錄 weight → weight 回 None，呼叫端落回 .env PERSONAL_STYLE_WEIGHT。"""
    _as_family(monkeypatch, PromptStyle.ILLUSTRIOUS)
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {
        "illustrious": {"style_extra": "flat color"},
    })
    extra, weight = wb._workflow_style_extra("Standard_V38.json")
    assert extra == "flat color"
    assert weight is None


def test_workflow_style_extra_registered_but_fields_blank_is_noop(monkeypatch):
    """workflow 有登錄但兩欄位皆留白／未填（只登錄其他欄位如 quality_prefix）→ 視同未登錄，零介入。"""
    _as_family(monkeypatch, PromptStyle.ILLUSTRIOUS)
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {
        "illustrious": {"quality_prefix": "x"},
    })
    assert wb._workflow_style_extra("Standard_V38.json") == ("", None)


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


# ── 實檔配方鎖（SYNC-007 起以家族為鍵，[CN-114]）──────────────────────────────
# 上面的機制測試都 mock 掉 _load_prompt_profiles／_detect_style；這一組刻意**不 mock**，
# 直接讀 backend/prompt_profiles.yml 與磁碟 workflow，鎖的是配方本身與家族解析。

# 設計約束（畫風強化規劃 §4.1）：版權詞、score_*、與 quality_prefix 重複的品質詞。
# SYNC-007 軌 R（2026-09-23）放寬兩項，理由見 CODE_NOTES CN-115：
#   ① 移除 "lineart"/"line art"：style_extra 在 compile 之後才組裝，不經 _LINEART_ARTIFACT_RE；
#      R1 的 `clean lineart` 已於 ComfyUI 驗證（避免的是「線稿感」，不是 lineart 這個字）。
#   ② tag 上限依位置分流：加權前置（weight != 1.0）會與 identity 爭注意力 → 維持 5；
#      不加權接尾端（weight == 1.0）→ 8（R1 為 7 個）。
#   版權詞（blue archive 等）仍禁止進 yml——個人畫風標籤改走 .env 分家族鍵（軌 P）。
_BANNED_SUBSTRINGS = (
    "blue archive", "score_",
    "masterpiece", "best quality", "absurdres",
)
_MAX_STYLE_TAGS_WEIGHTED = 5
_MAX_STYLE_TAGS_TAIL = 8


def _real_family(style: str) -> dict:
    return wb._load_prompt_profiles().get(style) or {}


def test_real_yml_uses_families_key_only():
    import yaml
    data = yaml.safe_load(wb._PROMPT_PROFILES_YML.read_text(encoding="utf-8"))
    assert "families" in data
    assert "profiles" not in data, "舊格式 profiles:（檔名為鍵）已於 SYNC-007 停用"


def test_real_illustrious_family_recipe():
    fam = _real_family("illustrious")
    assert fam.get("quality_prefix"), "illustrious 未設定 quality_prefix"
    assert fam.get("negative"), "illustrious 未設定 negative"
    assert fam.get("style_extra"), "illustrious 未設定 style_extra → 會靜默落回 .env"
    assert fam.get("style_extra_weight") == 1.0, "R1：畫風段不加權、接尾端（軌 R）"
    assert "flat color" not in fam["style_extra"].lower(), "舊平塗算子不得回流（SYNC-005）"


def test_real_anima_family_recipe():
    """官方：Aesthetic／Turbo 正負向皆不得含 score_*。style_extra 刻意留空（09-21 軌 S 續 C1）。"""
    fam = _real_family("anima")
    assert fam.get("quality_prefix") and fam.get("negative")
    for field in ("quality_prefix", "negative"):
        assert "score_" not in fam[field].lower(), f"anima {field} 含 score_*（官方明令禁用）"
    assert fam.get("style_extra") == ""


def test_real_style_extra_obeys_design_constraints():
    extra = _real_family("illustrious").get("style_extra", "")
    lowered = extra.lower()
    for banned in _BANNED_SUBSTRINGS:
        assert banned not in lowered, f"illustrious 的 style_extra 含禁用詞 {banned!r}"
    tags = [t.strip() for t in extra.split(",") if t.strip()]
    weight = _real_family("illustrious").get("style_extra_weight", 1.0)
    cap = _MAX_STYLE_TAGS_TAIL if weight == 1.0 else _MAX_STYLE_TAGS_WEIGHTED
    assert len(tags) <= cap, f"illustrious 有 {len(tags)} 個 tag（weight={weight}），超過上限 {cap} 會排擠角色 identity"


def test_real_style_extra_survives_sheet_tag_strip():
    """final_positive 會過 _strip_sheet_tags，畫風段不得被 _SHEET_TAG_RE 誤傷。"""
    from app.services.ai.image_ops import _strip_sheet_tags
    for style, fam in wb._load_prompt_profiles().items():
        extra = fam.get("style_extra") or ""
        assert _strip_sheet_tags(extra).strip(" ,") == extra, f"{style} 的 style_extra 被 sheet 過濾誤傷"


# ── SYNC-007 反向護欄：列舉磁碟，要求每支 workflow 的家族都「解析得到」───────────
# 檔名不再是鍵，靜默降級點移到「checkpoint 沒登錄 checkpoint_styles.yml → 退 sdxl」。
# 同 SYNC-001「測試鎖錯對象 → 列舉真實來源反向驗證」。

def test_all_custom_workflows_resolve_to_known_family():
    from pathlib import Path
    from app.services.ai.capability import extract_checkpoint_from_wf
    wf_dir = wb.CUSTOM_WORKFLOWS_DIR
    if not wf_dir.exists():
        pytest.skip(f"custom workflow 目錄不存在：{wf_dir}")
    on_disk = sorted(p.name for p in wf_dir.glob("*.json"))
    if not on_disk:
        pytest.skip("custom workflow 目錄內無 .json")
    patterns = [str(p).lower() for p in wb._load_checkpoint_styles()]
    problems = []
    for name in on_disk:
        ckpt = extract_checkpoint_from_wf(wb._load_workflow(name))
        if not ckpt:
            problems.append(f"{name}: 抽不到 checkpoint")
        elif not any(p in Path(ckpt).stem.lower() for p in patterns):
            problems.append(f"{name}: checkpoint {ckpt} 未登錄 checkpoint_styles.yml checkpoints: 區")
    assert not problems, "這些 workflow 的家族會靜默退回 sdxl：\n" + "\n".join(problems)


def test_live_workflows_resolve_expected_family():
    """現役 workflow 的來源標註必須是有設定配方的家族（不是 STYLE_CONFIG fallback）。"""
    expected = {
        "Standard_V38.json": "illustrious", "Advanced_V38.json": "illustrious",
        "Standard_V38_NOVE.json": "illustrious",
        "AnimaStandardV9_aesthetic.json": "anima", "AnimaStandardV9_turbo.json": "anima",
    }
    for name, style in expected.items():
        if not (wb.CUSTOM_WORKFLOWS_DIR / name).exists():
            continue
        assert wb._prompt_profile_source(None, name) == f"family: {style}", name


def test_new_workflow_needs_no_registration(tmp_path, monkeypatch):
    """SYNC-007 目標①：複製一支 V38 改名成 V41，不動 yml 就吃到同一份家族配方。"""
    src = wb.CUSTOM_WORKFLOWS_DIR / "Standard_V38.json"
    if not src.exists():
        pytest.skip("Standard_V38.json 不在磁碟")
    (tmp_path / "Standard_V41_test.json").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(wb, "CUSTOM_WORKFLOWS_DIR", tmp_path)
    assert wb._profile_for("Standard_V41_test.json") == wb._load_prompt_profiles()["illustrious"]
    assert wb._prompt_profile_source(None, "Standard_V41_test.json") == "family: illustrious"


def test_profile_for_warns_once_per_family_on_miss(caplog, monkeypatch):
    """miss 要告警，且同一家族只告警一次（每張圖會查三次，不去重會洗版 log）。"""
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {"illustrious": {"negative": "x"}})
    monkeypatch.setattr(wb, "_PROFILE_MISS_WARNED", set())
    styles = {"a.json": PromptStyle.PONY, "b.json": PromptStyle.PONY, "c.json": PromptStyle.ILLUSTRIOUS}
    monkeypatch.setattr(wb, "_detect_style", lambda w: styles[w])
    with caplog.at_level("WARNING"):
        assert wb._profile_for("a.json") == {}
        assert wb._profile_for("b.json") == {}
        assert wb._profile_for("c.json") == {"negative": "x"}
    hits = [r for r in caplog.records if "prompt-profile" in r.getMessage()]
    assert len(hits) == 1, f"期望剛好一次 miss 告警，實得 {len(hits)}"
    assert "pony" in hits[0].getMessage()


def test_detect_style_fallback_warns_once_per_cause(caplog, monkeypatch, tmp_path):
    """Gemini §2.3 Q3：退 sdxl 的兩個成因（讀檔失敗／checkpoint 未登錄）各自 warn-once、訊息不同。"""
    monkeypatch.setattr(wb, "_STYLE_FALLBACK_WARNED", set())
    monkeypatch.setattr(wb, "CUSTOM_WORKFLOWS_DIR", tmp_path)
    (tmp_path / "unknown_ckpt.json").write_text(
        json.dumps(_api_wf("mystery_model_v1.safetensors")), encoding="utf-8")
    with caplog.at_level("WARNING"):
        for _ in range(2):
            assert wb._detect_style("missing_wf.json") is PromptStyle.SDXL
            assert wb._detect_style("unknown_ckpt.json") is PromptStyle.SDXL
    msgs = [r.getMessage() for r in caplog.records
            if r.levelname == "WARNING" and "[prompt-style]" in r.getMessage()]
    assert len(msgs) == 2, msgs
    assert any("讀不到" in m for m in msgs)
    assert any("checkpoint_styles.yml" in m for m in msgs)


# ── [CN-115] SYNC-007 軌 P：.env 分家族個人標籤（wb 端：來源標註、@ 警告）────────
# tests/conftest.py 已在每個測試前清掉使用者真實 .env 的 PERSONAL_*_EXTRA_<家族>。

def test_prompt_profile_source_marks_personal_env(monkeypatch):
    _as_family(monkeypatch, PromptStyle.ILLUSTRIOUS)
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {"illustrious": {"quality_prefix": "x"}})
    monkeypatch.setenv("PERSONAL_NEGATIVE_EXTRA_ILLUSTRIOUS", "halo")
    assert wb._prompt_profile_source(None, "Standard_V38.json") == "family: illustrious +personal(.env)"


def test_prompt_profile_source_ignores_other_family_personal_env(monkeypatch):
    """ANIMA 的個人鍵不得讓 illustrious 的來源標註誤標 +personal。"""
    _as_family(monkeypatch, PromptStyle.ILLUSTRIOUS)
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {"illustrious": {"quality_prefix": "x"}})
    monkeypatch.setenv("PERSONAL_STYLE_EXTRA_ANIMA", "@some artist")
    assert wb._prompt_profile_source(None, "Standard_V38.json") == "family: illustrious"


def test_personal_extra_reads_detected_family_key(monkeypatch):
    _as_family(monkeypatch, PromptStyle.ANIMA)
    monkeypatch.setenv("PERSONAL_STYLE_EXTRA_ANIMA", "  some series, @some artist  ")
    monkeypatch.setenv("PERSONAL_STYLE_EXTRA_ILLUSTRIOUS", "some artist")
    assert wb._personal_extra("STYLE", "AnimaStandardV9_miaomiaoHarem.json") == "some series, @some artist"
    assert wb._personal_extra("NEGATIVE", "AnimaStandardV9_miaomiaoHarem.json") == ""


def test_personal_extra_warns_once_on_at_prefix_outside_anima(monkeypatch, caplog):
    _as_family(monkeypatch, PromptStyle.ILLUSTRIOUS)
    monkeypatch.setattr(wb, "_PERSONAL_AT_WARNED", set())
    monkeypatch.setenv("PERSONAL_STYLE_EXTRA_ILLUSTRIOUS", "@some artist")
    with caplog.at_level("WARNING"):
        for _ in range(3):
            assert wb._personal_extra("STYLE", "Standard_V38.json") == "@some artist"
    hits = [r for r in caplog.records if "[personal]" in r.getMessage()]
    assert len(hits) == 1


def test_personal_extra_at_prefix_is_silent_for_anima(monkeypatch, caplog):
    _as_family(monkeypatch, PromptStyle.ANIMA)
    monkeypatch.setattr(wb, "_PERSONAL_AT_WARNED", set())
    monkeypatch.setenv("PERSONAL_STYLE_EXTRA_ANIMA", "@some artist")
    with caplog.at_level("WARNING"):
        wb._personal_extra("STYLE", "AnimaStandardV9_miaomiaoHarem.json")
    assert not [r for r in caplog.records if "[personal]" in r.getMessage()]
