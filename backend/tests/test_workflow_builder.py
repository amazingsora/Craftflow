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


# ── P5-5: _workflow_style_extra（畫風 tag／權重 profile 層）────────────────────

def test_workflow_style_extra_unregistered_workflow_is_noop(monkeypatch):
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {})
    assert wb._workflow_style_extra("text_to_image.json") == ("", None)


def test_workflow_style_extra_registered_workflow_reads_both_fields(monkeypatch):
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {
        "Standard_V37.json": {"style_extra": "flat color, thick outlines", "style_extra_weight": 1.2},
    })
    extra, weight = wb._workflow_style_extra("Standard_V37.json")
    assert extra == "flat color, thick outlines"
    assert weight == 1.2


def test_workflow_style_extra_weight_absent_returns_none(monkeypatch):
    """只登錄 style_extra、不登錄 weight → weight 回 None，呼叫端落回 .env PERSONAL_STYLE_WEIGHT。"""
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {
        "Standard_V37.json": {"style_extra": "flat color"},
    })
    extra, weight = wb._workflow_style_extra("Standard_V37.json")
    assert extra == "flat color"
    assert weight is None


def test_workflow_style_extra_registered_but_fields_blank_is_noop(monkeypatch):
    """workflow 有登錄但兩欄位皆留白／未填（只登錄其他欄位如 quality_prefix）→ 視同未登錄，零介入。"""
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {
        "Standard_V37.json": {"quality_prefix": "x"},
    })
    assert wb._workflow_style_extra("Standard_V37.json") == ("", None)


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


# ── P5-6/7/8: 實檔配方鎖（backend/prompt_profiles.yml 真實登錄值）────────────
# 上面四組 _workflow_style_extra 測試都 monkeypatch 掉 _load_prompt_profiles，
# 驗的是**機制**；這一組刻意**不 mock**，直接讀專案內的 prompt_profiles.yml，
# 驗的是**配方本身**。理由：style_extra 是名單制設定，機制正確但漏登錄某支
# workflow 時，該 workflow 會靜默落回 .env（本專案反覆踩過的「零介入＝零訊號」）。

# SYNC-001（2026-09-15）：補上**現役**檔名。原本這兩個 tuple 只有歷史檔名，於是
# 「六個現役 workflow 全部未登錄」這件事，整組 real-profile 測試一條都沒擋到——
# 測試鎖的是已經不在磁碟上的檔，鎖得再嚴也沒用。新檔名透過 prompt_profiles.yml 的
# YAML anchor 沿用同一份配方，所以下面的參數化測試對新舊檔名期望值完全相同。
_ILLUSTRIOUS_PROFILES = (
    "Standard_V37.json", "Standard_V35.json",       # 歷史（anchor 來源）
    "Standard_V38.json", "Advanced_V38.json",       # 現役
)
_ANIMA_PROFILES = (
    "AnimaStandardV8.json", "AnimaStandardV8turbo.json",                # 歷史（anchor 來源）
    "AnimaStandardV8_Aesthetic.json", "AnimaStandardV8_trubo11.json",   # 現役
    "AnimaAdvancedV8_Aesthetic.json", "AnimaAdvancedV8_trubo11.json",   # 現役
)
# 設計約束（規劃書 §4.1）：版權詞、score_*（Aesthetic/Turbo 官方明令）、
# 與 quality_prefix 重複的品質詞、以及會被 styles._LINEART_ARTIFACT_RE 命中的字樣。
_BANNED_SUBSTRINGS = (
    "blue archive", "score_", "lineart", "line art",
    "masterpiece", "best quality", "absurdres",
)
_MAX_STYLE_TAGS = 5


@pytest.mark.parametrize("workflow,expected_weight", [
    *[(w, 1.2) for w in _ILLUSTRIOUS_PROFILES],
    *[(w, 2.0) for w in _ANIMA_PROFILES],
])
def test_real_profiles_register_style_extra(workflow, expected_weight):
    """四支主力 workflow 都必須登錄 style_extra ＋ 對應量級的 weight。"""
    extra, weight = wb._workflow_style_extra(workflow)
    assert extra, f"{workflow} 未登錄 style_extra → 會靜默落回 .env"
    assert weight == expected_weight, f"{workflow} weight={weight}，期望 {expected_weight}"


@pytest.mark.parametrize("workflow", _ILLUSTRIOUS_PROFILES + _ANIMA_PROFILES)
def test_real_style_extra_obeys_design_constraints(workflow):
    extra, _ = wb._workflow_style_extra(workflow)
    lowered = extra.lower()
    for banned in _BANNED_SUBSTRINGS:
        assert banned not in lowered, f"{workflow} 的 style_extra 含禁用詞 {banned!r}"
    tags = [t.strip() for t in extra.split(",") if t.strip()]
    assert len(tags) <= _MAX_STYLE_TAGS, f"{workflow} 有 {len(tags)} 個 tag，超過上限會排擠角色 identity"


def test_real_style_extra_survives_sheet_tag_strip():
    """規劃書 §5「必查的呼叫端」：final_positive 會過 _strip_sheet_tags，
    新配方（含 "anime style illustration"）不得被 _SHEET_TAG_RE 誤傷。"""
    from app.services.ai.image_ops import _strip_sheet_tags
    for workflow in _ILLUSTRIOUS_PROFILES + _ANIMA_PROFILES:
        extra, _ = wb._workflow_style_extra(workflow)
        assert _strip_sheet_tags(extra).strip(" ,") == extra, f"{workflow} 的 style_extra 被 sheet 過濾誤傷"


def test_real_ab_pairs_share_identical_style_extra():
    """V35/V37 是 P4-3 的架構級對照組、V8/V8turbo 是採樣檔位對照組——
    兩組內部的 prompt 配方必須逐字相同，否則 A/B 多一個變因（P4-4 同款理由）。"""
    assert wb._workflow_style_extra("Standard_V37.json") == wb._workflow_style_extra("Standard_V35.json")
    assert wb._workflow_style_extra("AnimaStandardV8.json") == wb._workflow_style_extra("AnimaStandardV8turbo.json")


def test_real_anima_v7_intentionally_unregistered():
    """AnimaStandardV7.json 刻意不登錄（AC-3 決策，落回 family）→ 零介入。
    這條同時是「未登錄＝落回 .env」零回歸路徑的實檔證明。"""
    assert wb._workflow_style_extra("AnimaStandardV7.json") == ("", None)


def test_real_anima_profiles_share_identical_quality_prefix():
    """P5-9（2026-08-26）：V8/V8turbo 登錄 quality_prefix 拿掉 ultra detailed / high contrast。

    刻意**不鎖死**那兩個詞的有無 —— 它們是 P5-9 A/B 的變因，鎖死會讓對照組（回滾成
    family 原值）跑不了測試。這裡只鎖兩個不變量：
      1. 兩支 Anima profile 的 quality_prefix 必須一致（否則採樣檔位 A/B 多一個變因）。
      2. 不得含 score_*（Aesthetic/Turbo 官方明令，正負向皆禁——這條不是變因、不可回滾）。
    """
    v8 = wb._workflow_profile_overrides("AnimaStandardV8.json").get("quality_prefix_override")
    turbo = wb._workflow_profile_overrides("AnimaStandardV8turbo.json").get("quality_prefix_override")
    assert v8 == turbo, "V8 / V8turbo 的 quality_prefix 不一致 → A/B 多變因"
    for value in (v8, turbo):
        if value:  # 未登錄（落回 family）時本條不適用
            assert "score_" not in value.lower(), "Aesthetic/Turbo 官方明令禁用 score_* tag"


# ── SYNC-001（2026-09-15）：檔名脫鉤護欄 ──────────────────────────────────────
# 上面那組「實檔配方鎖」只驗**被點名的檔名**配方對不對，驗不到「磁碟上多出一支沒人
# 點名的 workflow」。2026-09-15 六支現役 workflow 全部未登錄、三輪調校成果 100% 失效，
# 就是從這個缺口漏過去的（同型缺陷第三次：07-25 novaAnimeXL、08-22 V8turbo、本次改名）。
# 這條改成**反向**驗證：列舉磁碟，逐一要求登錄——新增或改名 workflow 時會直接紅燈。

def test_all_custom_workflows_are_registered():
    """data/custom_workflows/*.json 每一支都必須在 prompt_profiles.yml 登錄。

    未登錄＝靜默落回 checkpoint family + .env（`_profile_for` 只記一行 WARNING，
    出圖照跑），事後只能靠比對 prompt 字串才查得出來。這裡把它變成 CI 紅燈。

    新增 workflow 的正確做法：在 prompt_profiles.yml 用 `<<: *anchor` 沿用同底模的
    既有配方；真的需要不同配方才另外寫一份。`history/` 子目錄不列入（已退役）。
    """
    wf_dir = wb.CUSTOM_WORKFLOWS_DIR
    if not wf_dir.exists():
        pytest.skip(f"custom workflow 目錄不存在：{wf_dir}")
    on_disk = sorted(p.name for p in wf_dir.glob("*.json"))
    if not on_disk:
        pytest.skip("custom workflow 目錄內無 .json")
    registered = wb._load_prompt_profiles()
    missing = [name for name in on_disk if name not in registered]
    assert not missing, (
        f"這些 workflow 未登錄 prompt_profiles.yml → prompt 配方會靜默落回 "
        f".env/family：{missing}"
    )


def test_profile_for_warns_once_on_miss(caplog, monkeypatch):
    """miss 要告警，且同一檔名只告警一次（每張圖會查三次，不去重會洗版 log）。"""
    monkeypatch.setattr(wb, "_load_prompt_profiles", lambda: {"known.json": {"negative": "x"}})
    monkeypatch.setattr(wb, "_PROFILE_MISS_WARNED", set())
    with caplog.at_level("WARNING"):
        assert wb._profile_for("ghost.json") == {}
        assert wb._profile_for("ghost.json") == {}
        assert wb._profile_for("known.json") == {"negative": "x"}
    hits = [r for r in caplog.records if "prompt-profile" in r.getMessage()]
    assert len(hits) == 1, f"期望剛好一次 miss 告警，實得 {len(hits)}"
    assert "ghost.json" in hits[0].getMessage()


def test_live_workflows_resolve_expected_recipe():
    """現役六支的實際解析結果鎖定（anchor 展開後的值，不是抄一份期望字串）。

    鎖三個不變量，對應 2026-09-15 文件二四張圖暴露的三個症狀：
      1. Illustrious 側 quality_prefix 不得含 `amazing quality`（那是 family 預設，
         代表 profile 沒吃到）。
      2. Anima 側 quality_prefix 不得含 `ultra detailed` / `high contrast`
         （P5-9 已判定對 Aesthetic/Turbo 是解藥變毒藥）。
      3. Anima 側 negative 不得含 `score_*`（官方明令，非變因、不可回滾）。
    """
    live_illustrious = ("Standard_V38.json", "Advanced_V38.json")
    live_anima = (
        "AnimaStandardV8_Aesthetic.json", "AnimaStandardV8_trubo11.json",
        "AnimaAdvancedV8_Aesthetic.json", "AnimaAdvancedV8_trubo11.json",
    )
    for wf_name in live_illustrious:
        qp = wb._workflow_profile_overrides(wf_name).get("quality_prefix_override", "")
        assert qp, f"{wf_name} 未登錄 quality_prefix"
        assert "amazing quality" not in qp.lower(), (
            f"{wf_name} 吃到 illustrious family 預設 → profile 未生效")
    for wf_name in live_anima:
        overrides = wb._workflow_profile_overrides(wf_name)
        qp = overrides.get("quality_prefix_override", "").lower()
        neg = overrides.get("negative_override", "").lower()
        assert qp, f"{wf_name} 未登錄 quality_prefix"
        assert "ultra detailed" not in qp and "high contrast" not in qp, (
            f"{wf_name} 吃到 anima family 預設 → profile 未生效")
        assert neg, f"{wf_name} 未登錄 negative"
        assert "score_" not in neg, f"{wf_name} negative 含 score_*（官方明令禁用）"


def test_live_and_anchor_workflows_share_identical_recipe():
    """現役檔名與其 anchor 來源必須逐字相同——否則 YAML anchor 被人拆開抄成兩份，
    本次修復的核心（單一真相）就失效了。"""
    pairs = (
        ("Standard_V38.json", "Standard_V37.json"),
        ("Advanced_V38.json", "Standard_V37.json"),
        ("AnimaStandardV8_Aesthetic.json", "AnimaStandardV8.json"),
        ("AnimaStandardV8_trubo11.json", "AnimaStandardV8.json"),
        ("AnimaAdvancedV8_Aesthetic.json", "AnimaStandardV8.json"),
        ("AnimaAdvancedV8_trubo11.json", "AnimaStandardV8.json"),
    )
    for live, anchor in pairs:
        assert wb._workflow_profile_overrides(live) == wb._workflow_profile_overrides(anchor), (
            f"{live} 與 anchor 來源 {anchor} 的 prompt override 不一致")
        assert wb._workflow_style_extra(live) == wb._workflow_style_extra(anchor), (
            f"{live} 與 anchor 來源 {anchor} 的 style_extra 不一致")
