"""installer/checks.py 單元測試＋對照表反向護欄（列舉真實 workflow／後端原始碼，防漏登錄）。"""
import re
import sys
from pathlib import Path

import pytest

INSTALLER = Path(__file__).resolve().parents[1]
REPO = INSTALLER.parent
sys.path.insert(0, str(INSTALLER))

import checks  # noqa: E402
from checks import FAIL, OK, WARN, Gpu  # noqa: E402


# ── nvidia-smi 解析 ────────────────────────────────────────────────

def test_parse_nvidia_smi_with_compute_cap():
    out = "NVIDIA GeForce RTX 5070 Ti, 16303, 576.88, 12.0\r\nNVIDIA GeForce RTX 3060, 12288, 576.88, 8.6\n"
    gpus = checks.parse_nvidia_smi(out)
    assert [g.name for g in gpus] == ["NVIDIA GeForce RTX 5070 Ti", "NVIDIA GeForce RTX 3060"]
    assert gpus[0].compute_cap == (12, 0) and gpus[0].vram_mb == 16303


def test_parse_nvidia_smi_legacy_and_garbage():
    gpus = checks.parse_nvidia_smi("NVIDIA GeForce GTX 1080, 8192, 472.12\n\nNo devices were found\nX, [N/A], 1\n")
    assert len(gpus) == 1 and gpus[0].compute_cap is None


# ── GPU 判定 ──────────────────────────────────────────────────────

@pytest.mark.parametrize("gpus,others,level", [
    ([], ["AMD Radeon RX 7900 XTX"], FAIL),
    ([], ["Intel(R) UHD Graphics"], FAIL),
    ([], ["NVIDIA GeForce RTX 4070"], FAIL),                                   # 有卡沒驅動
    ([Gpu("RTX 3050 6GB", 6144, "560.0", (8, 6))], [], FAIL),                  # VRAM 不足
    ([Gpu("GTX 1080", 8192, "560.0", (6, 1))], [], FAIL),                      # 架構過舊
    ([Gpu("RTX 4060", 8188, "560.0", (8, 9))], [], WARN),                      # 可用但低於建議
    ([Gpu("RTX 3060", 12288, "560.0", (8, 6))], [], OK),
    ([Gpu("RTX 5070 Ti", 16303, "576.88", (12, 0))], [], OK),
    ([Gpu("RTX 5070 Ti", 16303, "566.14", (12, 0))], [], WARN),                # 50 系驅動太舊
    ([Gpu("RTX 3060", 12288, "472.0", None)], [], OK),                         # 舊 smi 無 compute_cap
])
def test_evaluate_gpu(gpus, others, level):
    assert checks.evaluate_gpu(gpus, others).level == level


def test_evaluate_gpu_picks_largest_vram():
    v = checks.evaluate_gpu([Gpu("small", 6144, "560", (8, 6)), Gpu("big", 24576, "560", (8, 9))])
    assert v.level == OK and v.gpu.name == "big"


def test_parse_version():
    assert checks.parse_version("v20.11.1") == (20, 11, 1)
    assert checks.parse_version("576.02") == (576, 2)
    assert checks.parse_version("") == ()


# ── workflow 需求抽取 ─────────────────────────────────────────────

def test_extract_needs_skips_node_refs_and_maps_folders():
    wf = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ["9", 0]}},
        "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "a.safetensors", "weight_dtype": "default"}},
        "3": {"class_type": "UltralyticsDetectorProvider", "inputs": {"model_name": "bbox/face.pt"}},
        "4": {"class_type": "Mystery", "inputs": {"thing": "x.safetensors"}},
    }
    n = checks.extract_needs("wf", wf)
    assert n.valid and n.classes == {"CheckpointLoaderSimple", "UNETLoader", "UltralyticsDetectorProvider", "Mystery"}
    assert n.models == {(("diffusion_models", "unet"), "a.safetensors"),
                        (("ultralytics",), "bbox/face.pt"), ((), "x.safetensors")}


def test_extract_needs_rejects_ui_format():
    assert not checks.extract_needs("ui", {"nodes": [], "links": []}).valid
    assert not checks.extract_needs("bad", []).valid


# ── ComfyUI 體檢（假目錄）─────────────────────────────────────────

def _fake_comfy(tmp: Path, packs: list[str], models: dict[str, list[str]]) -> Path:
    root = tmp / "ComfyUI_portable" / "ComfyUI"
    (root / "comfy").mkdir(parents=True)
    (root / "main.py").write_text("")
    (root.parent / "python_embeded").mkdir()
    for b in ("run_cpu.bat", "run_custom.bat", "run_nvidia_gpu.bat"):
        (root.parent / b).write_text("")
    for p in packs:
        (root / "custom_nodes" / p).mkdir(parents=True)
    for sub, files in models.items():
        for f in files:
            fp = root / "models" / sub / f
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_bytes(b"")
    return root


WF_SDXL = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "nova.safetensors"}},
           "2": {"class_type": "FaceDetailerPipe", "inputs": {}},
           "3": {"class_type": "UltralyticsDetectorProvider", "inputs": {"model_name": "bbox/face.pt"}}}
WF_ANIMA = {"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "anima.safetensors"}},
            "2": {"class_type": "easy int", "inputs": {}}}


def test_resolve_root_and_launchers(tmp_path):
    root = _fake_comfy(tmp_path, [], {})
    assert checks.resolve_comfy_root(root.parent) == root
    assert checks.resolve_comfy_root(root) == root
    assert checks.resolve_comfy_root(tmp_path) is None
    assert [b.name for b in checks.find_launchers(root)] == ["run_nvidia_gpu.bat", "run_custom.bat"]


def test_check_comfy_static(tmp_path):
    # Manager 風格（小寫）與 git clone 風格（大小寫＋底線）目錄名都要認得
    root = _fake_comfy(tmp_path, ["comfyui-impact-pack", "ComfyUI-Impact-Subpack", "x.disabled"],
                       {"checkpoints": ["nova.safetensors"], "ultralytics": ["bbox/face.pt"]})
    needs = [checks.extract_needs("sdxl", WF_SDXL), checks.extract_needs("anima", WF_ANIMA)]
    rep = checks.check_comfy(needs, root, None)
    assert rep.mode == "static" and rep.ready == ["sdxl"]
    assert set(rep.missing_packs) == {"ComfyUI Easy Use"}
    assert rep.missing_models == {"models/diffusion_models/anima.safetensors"}
    assert rep.level == WARN


def test_check_comfy_live_uses_object_info(tmp_path):
    root = _fake_comfy(tmp_path, [], {})          # 資料夾全空，只靠 /object_info
    info = {"UNETLoader": {"input": {"required": {"unet_name": [["anima.safetensors"]]}}},
            "easy int": {}}
    rep = checks.check_comfy([checks.extract_needs("anima", WF_ANIMA)], root, info)
    assert rep.mode == "live" and rep.ready == ["anima"] and rep.level == OK


def test_check_comfy_all_broken_is_fail(tmp_path):
    root = _fake_comfy(tmp_path, [], {})
    rep = checks.check_comfy([checks.extract_needs("sdxl", WF_SDXL)], root, None)
    assert rep.level == FAIL and not rep.ready


# ── .env upsert ──────────────────────────────────────────────────

def test_upsert_env_preserves_crlf_comments_and_appends():
    src = "# c\r\nCOMFYUI_BASE=http://localhost:8188\r\n# COMFYUI_LORAS_DIR=C:\\old\r\n"
    out = checks.upsert_env(src, {"COMFYUI_BASE": "http://127.0.0.1:8188", "COMFYUI_LORAS_DIR": r"F:\c\loras"})
    assert "\n" not in out.replace("\r\n", "")
    assert "COMFYUI_BASE=http://127.0.0.1:8188" in out
    assert "# COMFYUI_LORAS_DIR=C:\\old" in out                     # 註解行不動
    assert out.rstrip().endswith(r"COMFYUI_LORAS_DIR=F:\c\loras")
    assert checks.upsert_env(out, {"COMFYUI_LORAS_DIR": r"F:\c\loras"}) == out   # 冪等


def test_read_env_values():
    assert checks.read_env_values("A=1\n# B=2\n C = x y \n") == {"A": "1", "C": "x y"}


# ── 反向護欄：對照表必須涵蓋真實來源 ─────────────────────────────

def _known(ct: str) -> bool:
    return ct in checks.CORE_NODES or checks.pack_for_class(ct) is not None


def _uncovered(classes: set[str]) -> set[str]:
    return {c for c in classes if not _known(c)}


def test_guard_negative_control():
    """負向對照：護欄真的抓得到未登錄節點（避免測試空轉）。"""
    assert _uncovered({"KSampler", "TotallyNewNode"}) == {"TotallyNewNode"}


WF_DIR = REPO / "data" / "custom_workflows"


@pytest.mark.skipif(not WF_DIR.is_dir(), reason="需在 repo 內執行")
def test_every_runtime_workflow_node_is_mapped():
    needs = checks.load_workflow_needs(WF_DIR)
    assert needs, "custom_workflows 沒有任何 workflow"
    classes = set().union(*(n.classes for n in needs if n.valid))
    assert not _uncovered(classes), f"新節點未登錄到 checks.NODE_PACKS／CORE_NODES：{_uncovered(classes)}"


BACKEND = REPO / "backend" / "app"


@pytest.mark.skipif(not BACKEND.is_dir(), reason="需在 repo 內執行")
def test_every_backend_injected_node_is_mapped():
    classes = set()
    for f in BACKEND.rglob("*.py"):
        classes |= set(re.findall(r'"class_type":\s*"([^"]+)"', f.read_text(encoding="utf-8")))
    assert classes
    assert not _uncovered(classes), f"後端注入的節點未登錄：{_uncovered(classes)}"


@pytest.mark.skipif(not BACKEND.is_dir(), reason="需在 repo 內執行")
def test_optional_features_match_backend_constants():
    cap = (BACKEND / "services" / "ai" / "capability.py").read_text(encoding="utf-8")
    client = (BACKEND / "services" / "comfyui_client.py").read_text(encoding="utf-8")
    block = re.search(r"_SDXL_MODELS[^{]*\{(.*?)\}", cap, re.S).group(1)
    backend_files = set(re.findall(r'"([^"]+\.safetensors)"', block))
    backend_files |= set(re.findall(r'"([^"]+\.safetensors)"',
                                    re.search(r"LLLITE_PREFERRED_WEIGHTS\s*=\s*\((.*?)\)", client, re.S).group(1)))
    lllite_classes = set(re.findall(r'"([^"]+)"',
                                    re.search(r"LLLITE_NODE_CLASS_CANDIDATES\s*=\s*\((.*?)\)", client, re.S).group(1)))
    ours = {fn for feat in checks.OPTIONAL_FEATURES for _, fn in feat.models}
    assert backend_files and backend_files <= ours, f"選配模型未同步：{backend_files - ours}"
    assert lllite_classes <= checks.pack_by_name("ComfyUI Anima LLLite").classes


def test_optional_features_reference_existing_packs():
    for feat in checks.OPTIONAL_FEATURES:
        assert feat.pack is None or checks.pack_by_name(feat.pack) is not None


# ── 打包腳本衛生（CLAUDE.md §10：.bat 純 ASCII）──────────────────

@pytest.mark.parametrize("bat", sorted(INSTALLER.glob("*.bat")), ids=lambda p: p.name)
def test_bat_is_ascii_crlf(bat):
    raw = bat.read_bytes()
    raw.decode("ascii")
    assert b"\n" not in raw.replace(b"\r\n", b"")
