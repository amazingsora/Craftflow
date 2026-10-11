"""SYNC-009：FaceDetailer 注入（CN-120）與男角 tag 包（CN-121）。"""
import copy
import json

import pytest

from app.core.config import CUSTOM_WORKFLOWS_DIR
from app.services.ai.character_design_service import _gender_extras
from app.services.ai.gen_profile import GEN_PROFILE
from app.services.ai.image_ops import _reorder_subject_first
from app.services.ai.wf_node_ops import _find_main_ksampler_id, _inject_face_detailer

_ANIMA_V9 = ["AnimaStandardV9_miaomiaoHarem.json", "AnimaStandardV9_aesthetic.json", "AnimaStandardV9_turbo.json"]


def _load(name: str) -> dict:
    p = CUSTOM_WORKFLOWS_DIR / name
    if not p.exists():
        pytest.skip(f"{name} 不在磁碟")
    return json.loads(p.read_text(encoding="utf-8"))


def _fd_nodes(wf: dict) -> list[str]:
    return [k for k, n in wf.items() if isinstance(n, dict) and n.get("class_type") == "FaceDetailerPipe"]


@pytest.mark.parametrize("name", _ANIMA_V9)
def test_anima_v9_face_detailer_wired_and_same_source(name):
    wf = _load(name)
    ks = wf[_find_main_ksampler_id(wf)]["inputs"]
    decode_id = next(k for k, n in wf.items() if n.get("class_type") == "VAEDecode")
    consumers = [(k, key) for k, n in wf.items() for key, v in n.get("inputs", {}).items() if v == [decode_id, 0]]

    assert _inject_face_detailer(wf, 0.5, 18) is True
    (fd_id,) = _fd_nodes(wf)
    fd = wf[fd_id]["inputs"]
    assert wf[fd["detailer_pipe"][0]]["class_type"] == "ToDetailerPipe"
    assert fd["image"] == [decode_id, 0]
    for key in ("seed", "cfg", "sampler_name", "scheduler"):
        assert fd[key] == ks[key], key
    assert (fd["denoise"], fd["steps"]) == (0.5, 18)
    assert consumers and all(wf[k]["inputs"][key] == [fd_id, 0] for k, key in consumers)


def test_v38_with_existing_face_detailer_is_noop():
    wf = _load("Standard_V38.json")
    before = copy.deepcopy(wf)
    assert _inject_face_detailer(wf, 0.5, 18) is False
    assert wf == before


def test_inject_is_idempotent():
    wf = _load(_ANIMA_V9[0])
    assert _inject_face_detailer(wf, 0.5, 18) is True
    snap = copy.deepcopy(wf)
    assert _inject_face_detailer(wf, 0.5, 18) is False
    assert wf == snap


def test_no_detailer_pipe_is_noop():
    wf = {
        "1": {"class_type": "KSampler", "inputs": {"seed": 1, "denoise": 1.0}},
        "2": {"class_type": "VAEDecode", "inputs": {"samples": ["1", 0]}},
        "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0]}},
    }
    before = copy.deepcopy(wf)
    assert _inject_face_detailer(wf, 0.5, 18) is False
    assert wf == before


def test_face_detailer_enabled_only_for_anima():
    assert GEN_PROFILE["anima"].face_detailer_denoise == 0.5
    for fam, prof in GEN_PROFILE.items():
        if fam != "anima":
            assert prof.face_detailer_denoise is None, fam


def test_anima_lllite_matches_comfyui_f2():
    prof = GEN_PROFILE["anima"]
    assert round(0.85 * prof.lllite_strength_scale, 2) == 1.25
    assert prof.coverage_cn_end_pct["full"] == 1.0


def test_gender_extras_boy():
    pos, neg = _gender_extras("1boy")
    assert pos == ", male focus, bishounen"
    for t in ("1girl", "breasts", "old man", "thick eyebrows", "shirtless", "skirt"):
        assert t in neg
    assert "shirt, pants" not in pos


def test_gender_extras_man_has_no_anti_aging():
    pos, neg = _gender_extras("1man, mature male")
    assert pos == ", male focus"
    assert "old man" not in neg and "1girl" in neg


@pytest.mark.parametrize("tag", ["1girl", "1woman, mature female"])
def test_gender_extras_female_unchanged(tag):
    assert _gender_extras(tag) == ("", ", male face, masculine features")


@pytest.mark.parametrize("tag", ["", "androgynous"])
def test_gender_extras_other_empty(tag):
    assert _gender_extras(tag) == ("", "")


def test_male_focus_moves_to_subject_bucket():
    out = _reorder_subject_first("masterpiece, 1boy, black hair, solo, male focus", "masterpiece", "")
    assert out == "masterpiece, 1boy, solo, male focus, black hair"


# ── 能力旗標：「增強臉部輪廓」顯示與否（與注入共用 _wf_face_detailer_injectable）──

from app.services.ai.wf_node_ops import _wf_face_detailer_injectable  # noqa: E402


@pytest.mark.parametrize("name, expected", [
    ("AnimaStandardV9_miaomiaoHarem.json", True),
    ("Standard_V38.json", False),
])
def test_face_detailer_injectable_by_workflow(name, expected):
    assert _wf_face_detailer_injectable(_load(name)) is expected


def test_capability_reports_face_detailer(monkeypatch):
    from app.services.ai import capability as cap
    monkeypatch.setattr(cap, "_resolve_lllite_weight", lambda: None)
    anima = cap.resolve_capability(_load("AnimaStandardV9_miaomiaoHarem.json"), "miaomiaoHarem_anima12.safetensors")
    v38 = cap.resolve_capability(_load("Standard_V38.json"), "fabricatedXL_v70.safetensors")
    assert anima["face_detailer_supported"] is True
    assert v38["face_detailer_supported"] is False


# ── 修臉強度滑桿（使用者指定 denoise，後端夾區間）──

@pytest.mark.parametrize("requested, expected", [(None, 0.5), (0.35, 0.35), (0.05, 0.2), (0.95, 0.7)])
def test_face_detailer_strength_clamped(requested, expected):
    assert GEN_PROFILE["anima"].face_detailer_strength(requested) == expected


def test_face_detailer_strength_none_when_family_disabled():
    assert GEN_PROFILE["illustrious"].face_detailer_strength(0.5) is None


def test_design_routes_accept_face_detailer_denoise():
    import inspect
    from app.api import art_generate as ag
    for fn in (ag.generate_character_design, ag.generate_variant_design):
        assert inspect.signature(fn).parameters["face_detailer_denoise"].default is None
