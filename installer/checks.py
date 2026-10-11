"""Craftflow 安裝程式的純邏輯：GPU 判定、workflow 需求抽取、ComfyUI 體檢、.env upsert（無 I/O 副作用，可單測）。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# ── 等級 ─────────────────────────────────────────────────────────────
OK, WARN, FAIL, SKIP = "OK", "WARN", "FAIL", "SKIP"

# ── GPU 門檻（改規格只改這裡）────────────────────────────────────────
MIN_VRAM_GB = 7.5              # 8 GB 級卡（nvidia-smi 回報約 7.8–8.0 GiB）以下直接擋
RECOMMENDED_VRAM_GB = 11.0     # 對齊 core/config.py 的 COMFYUI_REQUIRED_VRAM_GB 預設
COEXIST_VRAM_GB = 18.0         # COMFYUI_REQUIRED(11) + OLLAMA_REQUIRED(7)：低於此值兩者會輪流佔用 VRAM
MIN_COMPUTE_CAP = (7, 5)       # Turing（RTX 20 系）以上
BLACKWELL_COMPUTE_CAP = (12, 0)
BLACKWELL_MIN_DRIVER = (570, 0)


@dataclass
class Gpu:
    name: str
    vram_mb: int
    driver: str
    compute_cap: tuple[int, int] | None = None

    @property
    def vram_gb(self) -> float:
        return self.vram_mb / 1024


@dataclass
class Verdict:
    level: str
    messages: list[str] = field(default_factory=list)
    gpu: Gpu | None = None


def parse_version(text: str) -> tuple[int, ...]:
    """'v20.11.1' / 'Python 3.11.9' / '576.02' → (20, 11, 1)；抓不到回 ()。"""
    m = re.search(r"(\d+(?:\.\d+)*)", text or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def parse_nvidia_smi(csv_text: str) -> list[Gpu]:
    """解析 `nvidia-smi --query-gpu=name,memory.total,driver_version[,compute_cap] --format=csv,noheader,nounits`。"""
    gpus: list[Gpu] = []
    for line in (csv_text or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3 or not parts[0]:
            continue
        try:
            vram = int(float(parts[1]))
        except ValueError:
            continue
        cap = None
        if len(parts) >= 4:
            v = parse_version(parts[3])
            if len(v) >= 2:
                cap = (v[0], v[1])
        gpus.append(Gpu(name=parts[0], vram_mb=vram, driver=parts[2], compute_cap=cap))
    return gpus


def evaluate_gpu(gpus: list[Gpu], other_adapters: list[str] | None = None) -> Verdict:
    """挑 VRAM 最大的 NVIDIA 卡判定；無 NVIDIA 卡＝FAIL。"""
    others = [a for a in (other_adapters or []) if a]
    if not gpus:
        if any("nvidia" in a.lower() for a in others):
            return Verdict(FAIL, ["偵測到 NVIDIA 顯示卡但 nvidia-smi 無法執行：請安裝／更新 NVIDIA 驅動後重跑"])
        found = "、".join(others) if others else "無"
        return Verdict(FAIL, [f"找不到 NVIDIA 顯示卡（偵測到：{found}）。Craftflow 生圖需要 NVIDIA CUDA GPU"])

    g = max(gpus, key=lambda x: x.vram_mb)
    msgs = [f"{g.name}｜VRAM {g.vram_gb:.1f} GB｜驅動 {g.driver}"
            + (f"｜compute {g.compute_cap[0]}.{g.compute_cap[1]}" if g.compute_cap else "")]
    level = OK

    if g.vram_gb < MIN_VRAM_GB:
        return Verdict(FAIL, msgs + ["VRAM 低於最低需求（8 GB 級）"], g)
    if g.compute_cap and g.compute_cap < MIN_COMPUTE_CAP:
        return Verdict(FAIL, msgs + [
            f"GPU 架構過舊（compute {g.compute_cap[0]}.{g.compute_cap[1]}），需 RTX 20 系列（7.5）以上"], g)

    if g.vram_gb < RECOMMENDED_VRAM_GB:
        level = WARN
        msgs.append(f"VRAM 低於建議值 {RECOMMENDED_VRAM_GB:.0f} GB：SDXL＋CN＋IPA 同時載入可能 OOM，建議優先用 Anima workflow")
    if g.vram_gb < COEXIST_VRAM_GB:
        msgs.append(f"VRAM < {COEXIST_VRAM_GB:.0f} GB：Ollama 與 ComfyUI 會輪流佔用顯存（後端自動處理，僅速度較慢）")
    if g.compute_cap and g.compute_cap >= BLACKWELL_COMPUTE_CAP and parse_version(g.driver) < BLACKWELL_MIN_DRIVER:
        level = WARN
        msgs.append(f"RTX 50 系列需驅動 {BLACKWELL_MIN_DRIVER[0]} 以上，目前 {g.driver}")
    if g.compute_cap is None:
        msgs.append("驅動未回報 compute capability（舊版 nvidia-smi），略過架構檢查")
    return Verdict(level, msgs, g)


# ── ComfyUI 節點／模型需求 ────────────────────────────────────────────

# ComfyUI 本體內建（含 comfy_extras）；Primitive*/String*/Regex*/SeedNode 需較新版 ComfyUI
CORE_NODES = frozenset({
    "CheckpointLoaderSimple", "UNETLoader", "CLIPLoader", "CLIPSetLastLayer", "CLIPTextEncode",
    "CLIPVisionLoader", "VAELoader", "VAEDecode", "VAEEncode", "VAEEncodeForInpaint",
    "EmptyLatentImage", "KSampler", "LatentUpscaleBy", "LoadImage", "ImageToMask",
    "LoraLoader", "LoraLoaderModelOnly", "ControlNetLoader", "ControlNetApplyAdvanced",
    "SetUnionControlNetType", "DifferentialDiffusion",
    "PrimitiveBoolean", "PrimitiveFloat", "StringConcatenate", "RegexReplace", "SeedNode",
})


@dataclass(frozen=True)
class NodePack:
    name: str
    url: str
    classes: frozenset[str]
    optional: bool = False   # 後端注入、缺了會降級（不擋生圖）

    @property
    def dir_key(self) -> str:
        return normalize_dir_name(self.url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git"))


NODE_PACKS: tuple[NodePack, ...] = (
    NodePack("ComfyUI Impact Pack", "https://github.com/ltdrdata/ComfyUI-Impact-Pack", frozenset({
        "FaceDetailerPipe", "EditDetailerPipe", "ToDetailerPipe", "SAMLoader",
        "ImpactSwitch", "ImpactWildcardProcessor"})),
    NodePack("ComfyUI Impact Subpack", "https://github.com/ltdrdata/ComfyUI-Impact-Subpack",
             frozenset({"UltralyticsDetectorProvider"})),
    NodePack("rgthree-comfy", "https://github.com/rgthree/rgthree-comfy",
             frozenset({"Image Comparer (rgthree)"})),
    NodePack("ComfyUI Image Saver", "https://github.com/alexopus/ComfyUI-Image-Saver", frozenset({
        "Image Saver", "Image Saver Simple", "Image Saver Metadata", "Input Parameters (Image Saver)"})),
    NodePack("ComfyUI LoRA Manager", "https://github.com/willmiao/ComfyUI-Lora-Manager",
             frozenset({"Lora Loader (LoraManager)", "TriggerWord Toggle (LoraManager)"})),
    NodePack("ComfyUI KJNodes", "https://github.com/kijai/ComfyUI-KJNodes", frozenset({"WidgetToString"})),
    NodePack("ComfyUI Easy Use", "https://github.com/yolain/ComfyUI-Easy-Use",
             frozenset({"easy int", "easy showAnything"})),
    NodePack("ComfyUI ppm", "https://github.com/pamparamm/ComfyUI-ppm", frozenset({"CLIPNegPip"})),
    NodePack("ComfyUI IPAdapter Plus", "https://github.com/cubiq/ComfyUI_IPAdapter_plus",
             frozenset({"IPAdapterModelLoader", "IPAdapterAdvanced"}), optional=True),
    NodePack("ComfyUI Anima LLLite", "https://github.com/kohya-ss/ComfyUI-Anima-LLLite",
             frozenset({"AnimaLLLiteApply_sdscripts", "AnimaLLLiteApply"}), optional=True),
)

# (class_type, input 名) → 模型子資料夾（依序找）
MODEL_INPUTS: dict[tuple[str, str], tuple[str, ...]] = {
    ("CheckpointLoaderSimple", "ckpt_name"): ("checkpoints",),
    ("UNETLoader", "unet_name"): ("diffusion_models", "unet"),
    ("CLIPLoader", "clip_name"): ("text_encoders", "clip"),
    ("VAELoader", "vae_name"): ("vae",),
    ("LoraLoader", "lora_name"): ("loras",),
    ("LoraLoaderModelOnly", "lora_name"): ("loras",),
    ("UltralyticsDetectorProvider", "model_name"): ("ultralytics",),
    ("SAMLoader", "model_name"): ("sams",),
}
_MODEL_EXT = (".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".sft")


@dataclass(frozen=True)
class OptionalFeature:
    name: str
    family: str
    pack: str | None                          # NodePack.name
    models: tuple[tuple[str, str], ...]       # (子資料夾, 檔名)


# 對照 backend/app/services/ai/capability.py 的 _SDXL_MODELS 與 comfyui_client.py 的 LLLITE_PREFERRED_WEIGHTS（測試反向驗證）
OPTIONAL_FEATURES: tuple[OptionalFeature, ...] = (
    OptionalFeature("IP-Adapter（角色參考）", "illustrious", "ComfyUI IPAdapter Plus", (
        ("clip_vision", "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"),
        ("ipadapter", "ip-adapter-plus_sdxl_vit-h.safetensors"))),
    OptionalFeature("ControlNet Union（構圖控制）", "illustrious", None, (
        ("controlnet", "diffusion_pytorch_model_promax.safetensors"),)),
    OptionalFeature("Anima LLLite（結構控制）", "anima", "ComfyUI Anima LLLite", (
        ("controlnet", "anima-lllite-any-test-like-v2.safetensors"),)),
)


def normalize_dir_name(name: str) -> str:
    return name.lower().replace("_", "-").strip()


def pack_for_class(class_type: str) -> NodePack | None:
    return next((p for p in NODE_PACKS if class_type in p.classes), None)


def pack_by_name(name: str) -> NodePack | None:
    return next((p for p in NODE_PACKS if p.name == name), None)


@dataclass
class WorkflowNeeds:
    name: str
    classes: set[str] = field(default_factory=set)
    models: set[tuple[tuple[str, ...], str]] = field(default_factory=set)   # (候選資料夾, 相對路徑)
    valid: bool = True


def extract_needs(name: str, wf: object) -> WorkflowNeeds:
    """API 格式 workflow → 需要的節點與模型；UI 格式或壞檔 → valid=False。"""
    needs = WorkflowNeeds(name)
    if not isinstance(wf, dict) or not wf:
        needs.valid = False
        return needs
    nodes = [n for n in wf.values() if isinstance(n, dict) and "class_type" in n]
    if not nodes:
        needs.valid = False
        return needs
    for n in nodes:
        ct = n["class_type"]
        needs.classes.add(ct)
        for key, val in (n.get("inputs") or {}).items():
            if not isinstance(val, str):          # 節點參照 ["12", 0] 不是檔名
                continue
            folders = MODEL_INPUTS.get((ct, key))
            if folders:
                needs.models.add((folders, val))
            elif val.lower().endswith(_MODEL_EXT):
                needs.models.add(((), val))       # 未登錄的輸入：全 models 目錄搜尋
    return needs


def load_workflow_needs(wf_dir: Path) -> list[WorkflowNeeds]:
    """只看 runtime 目錄第一層（history/ 是退役檔）。"""
    out = []
    for f in sorted(Path(wf_dir).glob("*.json")):
        try:
            wf = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            out.append(WorkflowNeeds(f.stem, valid=False))
            continue
        out.append(extract_needs(f.stem, wf))
    return out


def resolve_comfy_root(path: Path) -> Path | None:
    """接受 portable 根目錄或 ComfyUI 本體目錄，回傳含 main.py／models／custom_nodes 的那層。"""
    path = Path(path)
    for cand in (path, path / "ComfyUI"):
        if (cand / "main.py").is_file() and (cand / "comfy").is_dir():
            return cand
    return None


def find_launchers(comfy_root: Path) -> list[Path]:
    """portable 根目錄下的 run_*.bat，run_nvidia_gpu.bat 排第一。"""
    base = comfy_root.parent if (comfy_root.parent / "python_embeded").is_dir() else comfy_root
    bats = sorted(base.glob("run_*.bat"))
    bats = [b for b in bats if "cpu" not in b.name.lower()]
    bats.sort(key=lambda b: (b.name.lower() != "run_nvidia_gpu.bat", b.name.lower()))
    return bats


def index_models(models_dir: Path) -> dict[str, set[str]]:
    """{子資料夾: {相對路徑(/)}}，另以 '*' 收所有檔名（供未登錄輸入搜尋）。"""
    idx: dict[str, set[str]] = {"*": set()}
    if not models_dir.is_dir():
        return idx
    for sub in models_dir.iterdir():
        if not sub.is_dir():
            continue
        files = set()
        for f in sub.rglob("*"):
            if f.is_file() and f.suffix.lower() in _MODEL_EXT:
                rel = f.relative_to(sub).as_posix()
                files.add(rel)
                idx["*"].add(f.name)
        idx[sub.name] = files
    return idx


def model_present(folders: tuple[str, ...], rel: str, idx: dict[str, set[str]],
                  live_options: set[str] | None = None) -> bool:
    rel = rel.replace("\\", "/")
    if live_options is not None and rel in live_options:
        return True
    if not folders:
        return rel.rsplit("/", 1)[-1] in idx.get("*", set())
    return any(rel in idx.get(f, set()) for f in folders)


def installed_pack_dirs(custom_nodes: Path) -> set[str]:
    if not custom_nodes.is_dir():
        return set()
    return {normalize_dir_name(d.name) for d in custom_nodes.iterdir()
            if d.is_dir() and not d.name.endswith(".disabled")}


def live_model_options(object_info: dict) -> set[str]:
    """/object_info 裡所有 loader 的下拉選項（含 extra_model_paths 設定的路徑）。"""
    opts: set[str] = set()
    for (ct, key) in MODEL_INPUTS:
        spec = ((object_info.get(ct) or {}).get("input") or {}).get("required", {}).get(key)
        if isinstance(spec, list) and spec and isinstance(spec[0], list):
            opts.update(str(o).replace("\\", "/") for o in spec[0])
    return opts


@dataclass
class ComfyReport:
    mode: str                                        # "live"（/object_info）或 "static"（掃資料夾）
    ready: list[str] = field(default_factory=list)
    broken: dict[str, list[str]] = field(default_factory=dict)
    missing_packs: dict[str, NodePack] = field(default_factory=dict)
    unknown_classes: set[str] = field(default_factory=set)
    missing_models: set[str] = field(default_factory=set)
    optional: list[tuple[str, bool, str]] = field(default_factory=list)   # (功能, 可用, 說明)
    invalid: list[str] = field(default_factory=list)

    @property
    def level(self) -> str:
        return OK if self.ready and not self.broken else (WARN if self.ready else FAIL)


def check_comfy(needs: list[WorkflowNeeds], comfy_root: Path, object_info: dict | None) -> ComfyReport:
    models_idx = index_models(comfy_root / "models")
    live = object_info is not None
    rep = ComfyReport("live" if live else "static")
    live_classes = set(object_info) if live else set()
    live_opts = live_model_options(object_info) if live else None
    dirs = installed_pack_dirs(comfy_root / "custom_nodes")

    def class_ok(ct: str) -> bool:
        if live:
            return ct in live_classes
        if ct in CORE_NODES:
            return True
        pack = pack_for_class(ct)
        return bool(pack and pack.dir_key in dirs)

    for w in needs:
        if not w.valid:
            rep.invalid.append(w.name)
            continue
        problems = []
        for ct in sorted(w.classes):
            if class_ok(ct):
                continue
            pack = pack_for_class(ct)
            if pack:
                rep.missing_packs[pack.name] = pack
                problems.append(f"缺節點包 {pack.name}（{ct}）")
            else:
                rep.unknown_classes.add(ct)
                problems.append(f"缺節點 {ct}")
        for folders, rel in sorted(w.models):
            if not model_present(folders, rel, models_idx, live_opts):
                where = f"models/{folders[0]}/" if folders else "models/"
                rep.missing_models.add(where + rel)
                problems.append(f"缺模型 {where}{rel}")
        if problems:
            rep.broken[w.name] = problems
        else:
            rep.ready.append(w.name)

    for feat in OPTIONAL_FEATURES:
        pack = pack_by_name(feat.pack) if feat.pack else None
        pack_ok = True
        if pack:
            pack_ok = any(class_ok(c) for c in pack.classes)
        miss = [f"models/{sub}/{fn}" for sub, fn in feat.models
                if not model_present((sub,), fn, models_idx, None)]
        detail = []
        if not pack_ok:
            detail.append(f"缺 {pack.name}")
        detail += [f"缺 {m}" for m in miss]
        rep.optional.append((f"{feat.name}［{feat.family}］", pack_ok and not miss,
                             "、".join(detail) if detail else "可用"))
    return rep


# ── .env ─────────────────────────────────────────────────────────────

_ENV_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


def read_env_values(text: str) -> dict[str, str]:
    vals = {}
    for line in text.splitlines():
        m = _ENV_LINE.match(line)
        if m:
            vals[m.group(1)] = m.group(2).strip()
    return vals


def upsert_env(text: str, updates: dict[str, str], header: str = "# ── 安裝程式寫入 ──") -> str:
    """改寫未註解的 KEY=；缺的補在檔尾。沿用原檔換行符，註解與順序不動。"""
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    done = set()
    for i, line in enumerate(lines):
        m = _ENV_LINE.match(line)
        if m and m.group(1) in updates and m.group(1) not in done:
            lines[i] = f"{m.group(1)}={updates[m.group(1)]}"
            done.add(m.group(1))
    rest = [k for k in updates if k not in done]
    if rest:
        if lines and lines[-1].strip():
            lines.append("")
        if header not in lines:
            lines.append(header)
        lines += [f"{k}={updates[k]}" for k in rest]
    return nl.join(lines) + nl
