"""Craftflow 一鍵安裝：GPU 檢查 → 相依套件 → ComfyUI 指定與體檢 → 後端/前端安裝 → .env → Ollama 模型 → 冒煙測試。
可重複執行（已完成的步驟會略過）。打包：installer/build_exe.bat。"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checks  # noqa: E402
from checks import FAIL, OK, SKIP, WARN  # noqa: E402

REPO_URL = "https://github.com/amazingsora/Craftflow.git"
PYTHON_MINOR = (3, 11)
NODE_MIN = (18,)                       # Vite 5 最低需求
WINGET_IDS = {
    "python": "Python.Python.3.11",
    "node": "OpenJS.NodeJS.LTS",
    "ollama": "Ollama.Ollama",
    "git": "Git.Git",
}
DEFAULT_COMFY_URL = "http://localhost:8188"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
COMFY_BOOT_TIMEOUT_SEC = 240
BACKEND_SMOKE_PORT = 8000
BACKEND_SMOKE_TIMEOUT_SEC = 90
HTTP_TIMEOUT_SEC = 5
IS_WIN = os.name == "nt"
CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


# ── 輸出／互動 ────────────────────────────────────────────────────────

class UI:
    ICON = {OK: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]", SKIP: "[SKIP]"}

    def __init__(self, assume_yes: bool):
        self.yes = assume_yes
        self.rows: list[tuple[str, str, str]] = []
        self.log_lines: list[str] = []

    def log(self, msg: str) -> None:
        self.log_lines.append(f"{datetime.now():%H:%M:%S} {msg}")

    def say(self, msg: str = "") -> None:
        print(msg, flush=True)
        self.log(msg)

    def step(self, n: int, total: int, title: str) -> None:
        self.say("")
        self.say(f"━━ [{n}/{total}] {title}")

    def result(self, step: str, level: str, detail: str) -> str:
        self.rows.append((step, level, detail))
        self.say(f"  {self.ICON[level]} {detail}")
        return level

    def ask(self, question: str, default: bool = True) -> bool:
        if self.yes:
            return default
        hint = "Y/n" if default else "y/N"
        while True:
            try:
                ans = input(f"  ? {question} [{hint}] ").strip().lower()
            except EOFError:
                return default
            if not ans:
                return default
            if ans in ("y", "yes", "是"):
                return True
            if ans in ("n", "no", "否"):
                return False

    def ask_text(self, question: str, default: str = "") -> str:
        if self.yes:
            return default
        try:
            ans = input(f"  ? {question}" + (f" [{default}]" if default else "") + " ").strip().strip('"')
        except EOFError:
            ans = ""
        return ans or default

    def ask_folder(self, title: str, initial: str = "") -> str:
        """優先開資料夾對話框；沒有 GUI 就改文字輸入。"""
        if not self.yes:
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                path = filedialog.askdirectory(title=title, initialdir=initial or None, mustexist=True)
                root.destroy()
                if path:
                    return str(Path(path))
            except Exception as e:  # 無 tkinter／無顯示環境
                self.log(f"folder dialog unavailable: {e}")
        return self.ask_text(f"{title}（貼上路徑）：", initial)

    def pause(self) -> None:
        if not self.yes and IS_WIN:
            try:
                input("\n按 Enter 結束...")
            except EOFError:
                pass


# ── 系統工具 ──────────────────────────────────────────────────────────

def run(cmd: list[str], ui: UI, cwd: Path | None = None, capture: bool = True,
        timeout: int | None = None) -> subprocess.CompletedProcess:
    """capture=False 時直接輸出到主控台（pip／npm／winget 進度）。找不到執行檔回 returncode=127。"""
    ui.log(f"$ {' '.join(map(str, cmd))}" + (f"  (cwd={cwd})" if cwd else ""))
    try:
        cp = subprocess.run([str(c) for c in cmd], cwd=cwd, timeout=timeout, text=True,
                            capture_output=capture, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 127, "", "not found")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", "timeout")
    if capture:
        ui.log((cp.stdout or "")[-2000:] + (cp.stderr or "")[-2000:])
    return cp


def which(name: str, extra: list[Path] = ()) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for p in extra:
        if p.is_file():
            return str(p)
    return None


def refresh_path_from_registry() -> None:
    """winget 裝完不會更新目前行程的 PATH → 從登錄檔重讀 系統＋使用者 PATH。"""
    if not IS_WIN:
        return
    import winreg
    parts: list[str] = []
    for hive, sub in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                      (winreg.HKEY_CURRENT_USER, r"Environment")):
        try:
            with winreg.OpenKey(hive, sub) as k:
                val, _ = winreg.QueryValueEx(k, "Path")
                parts += [os.path.expandvars(p) for p in val.split(";") if p]
        except OSError:
            pass
    if parts:
        seen, merged = set(), []
        for p in parts + os.environ.get("PATH", "").split(os.pathsep):
            if p and p.lower() not in seen:
                seen.add(p.lower())
                merged.append(p)
        os.environ["PATH"] = os.pathsep.join(merged)


def http_get_json(url: str, timeout: float = HTTP_TIMEOUT_SEC) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def winget_install(key: str, ui: UI) -> bool:
    if not which("winget"):
        ui.say("  找不到 winget（Windows 10 請從 Microsoft Store 安裝「應用程式安裝程式」）")
        return False
    pkg = WINGET_IDS[key]
    ui.say(f"  → winget install {pkg}（可能跳出 UAC 確認視窗）")
    cp = run(["winget", "install", "--id", pkg, "-e", "--silent",
              "--accept-package-agreements", "--accept-source-agreements"], ui, capture=False)
    refresh_path_from_registry()
    return cp.returncode == 0


def localappdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))


def program_files() -> Path:
    return Path(os.environ.get("ProgramFiles", r"C:\Program Files"))


# ── 步驟 ─────────────────────────────────────────────────────────────

class Installer:
    TOTAL = 10

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.ui = UI(args.yes)
        self.repo: Path | None = None
        self.comfy_root: Path | None = None
        self.python: str | None = None
        self.npm: str | None = None
        self.ollama: str | None = None
        self.gpu: checks.Gpu | None = None
        self.env_vals: dict[str, str] = {}
        self.launcher: Path | None = None
        self._comfy_report: checks.ComfyReport | None = None

    def may_install(self, question: str) -> bool:
        """--check-only 一律不裝；否則詢問。"""
        return not self.args.check_only and self.ui.ask(question, True)

    # 1 ─ 系統
    def step_system(self) -> str:
        ui = self.ui
        ui.step(1, self.TOTAL, "作業系統")
        if not IS_WIN:
            return ui.result("系統", FAIL, f"僅支援 Windows 10/11 64-bit（目前 {platform.system()}）")
        if platform.machine().upper() not in ("AMD64", "X86_64"):
            return ui.result("系統", FAIL, f"僅支援 64-bit（目前 {platform.machine()}）")
        return ui.result("系統", OK, f"Windows {platform.release()}（build {platform.version()}）")

    # 2 ─ GPU
    def step_gpu(self) -> str:
        ui = self.ui
        ui.step(2, self.TOTAL, "顯示卡")
        smi = which("nvidia-smi", [Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe",
                                   program_files() / "NVIDIA Corporation" / "NVSMI" / "nvidia-smi.exe"])
        gpus: list[checks.Gpu] = []
        if smi:
            base = ["--format=csv,noheader,nounits"]
            cp = run([smi, "--query-gpu=name,memory.total,driver_version,compute_cap"] + base, ui, timeout=30)
            if cp.returncode != 0:     # 舊驅動不認得 compute_cap
                cp = run([smi, "--query-gpu=name,memory.total,driver_version"] + base, ui, timeout=30)
            if cp.returncode == 0:
                gpus = checks.parse_nvidia_smi(cp.stdout)
        others = []
        if not gpus and IS_WIN:
            cp = run(["powershell", "-NoProfile", "-Command",
                      "(Get-CimInstance Win32_VideoController).Name"], ui, timeout=30)
            others = [l.strip() for l in (cp.stdout or "").splitlines() if l.strip()]
        v = checks.evaluate_gpu(gpus, others)
        self.gpu = v.gpu
        for extra in v.messages[1:]:
            ui.say(f"         {extra}")
        return ui.result("顯示卡", v.level, v.messages[0])

    # 3 ─ repo
    def step_repo(self) -> str:
        ui = self.ui
        ui.step(3, self.TOTAL, "Craftflow 專案資料夾")
        cand = [Path(self.args.repo).resolve()] if self.args.repo else []
        here = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
        cand += [here, *here.parents, Path.cwd(), *Path.cwd().parents]
        for c in cand:
            if self._is_repo(c):
                self.repo = c
                return ui.result("專案", OK, str(c))

        ui.say("  找不到 Craftflow 專案（需有 backend/main.py 與 frontend/package.json）")
        if self.may_install("要從 GitHub 下載（git clone）一份嗎？選 n 則手動指定已存在的資料夾"):
            return self._clone()
        path = ui.ask_folder("選擇 Craftflow 專案資料夾")
        if path and self._is_repo(Path(path)):
            self.repo = Path(path)
            return ui.result("專案", OK, path)
        return ui.result("專案", FAIL, f"不是 Craftflow 專案資料夾：{path or '（未選擇）'}")

    @staticmethod
    def _is_repo(p: Path) -> bool:
        return (p / "backend" / "main.py").is_file() and (p / "frontend" / "package.json").is_file()

    def _clone(self) -> str:
        ui = self.ui
        git = which("git", [program_files() / "Git" / "cmd" / "git.exe"])
        if not git and ui.ask("需要 Git，用 winget 安裝？", True) and winget_install("git", ui):
            git = which("git", [program_files() / "Git" / "cmd" / "git.exe"])
        if not git:
            return ui.result("專案", FAIL, "沒有 git，無法下載。請安裝 Git 或手動 clone 後把本程式放進專案資料夾")
        parent = ui.ask_folder("選擇要放 Craftflow 的上層資料夾", str(Path.home()))
        if not parent:
            return ui.result("專案", FAIL, "未選擇資料夾")
        target = Path(parent) / "Craftflow"
        if target.exists() and any(target.iterdir()):
            return ui.result("專案", FAIL, f"{target} 已存在且非空，請改選或刪除後重跑")
        cp = run([git, "clone", REPO_URL, str(target)], ui, capture=False)
        if cp.returncode != 0 or not self._is_repo(target):
            return ui.result("專案", FAIL, f"git clone 失敗（exit {cp.returncode}）")
        self.repo = target
        return ui.result("專案", OK, f"已下載到 {target}")

    # 4 ─ 相依套件
    def step_deps(self) -> str:
        ui = self.ui
        ui.step(4, self.TOTAL, "相依套件（Python 3.11 / Node.js / Ollama）")
        levels = [self._ensure_python(), self._ensure_node(), self._ensure_ollama()]
        return FAIL if FAIL in levels else (WARN if WARN in levels else OK)

    def _find_python311(self) -> str | None:
        cands: list[list[str]] = [["py", f"-{PYTHON_MINOR[0]}.{PYTHON_MINOR[1]}"]]
        for p in (localappdata() / "Programs" / "Python" / "Python311" / "python.exe",
                  program_files() / "Python311" / "python.exe"):
            if p.is_file():
                cands.append([str(p)])
        if shutil.which("python"):
            cands.append([shutil.which("python")])
        for c in cands:
            cp = run(c + ["-c", "import sys;print(sys.version_info[:2]==(3,11), sys.executable)"], self.ui, timeout=30)
            out = (cp.stdout or "").strip()
            if cp.returncode == 0 and out.startswith("True"):
                return out.split(" ", 1)[1]
        return None

    def _ensure_python(self) -> str:
        ui = self.ui
        self.python = self._find_python311()
        if not self.python and self.may_install("找不到 Python 3.11，用 winget 安裝？") and winget_install("python", ui):
            self.python = self._find_python311()
        if not self.python:
            return ui.result("Python", FAIL, "需要 Python 3.11：https://www.python.org/downloads/ （勾選 Add to PATH）")
        return ui.result("Python", OK, f"3.11 → {self.python}")

    def _node_version(self) -> tuple[int, ...]:
        node = which("node", [program_files() / "nodejs" / "node.exe"])
        if not node:
            return ()
        cp = run([node, "--version"], self.ui, timeout=30)
        return checks.parse_version(cp.stdout) if cp.returncode == 0 else ()

    def _ensure_node(self) -> str:
        ui = self.ui
        ver = self._node_version()
        if (not ver or ver < NODE_MIN) and self.may_install(
                f"Node.js {'.'.join(map(str, ver)) or '未安裝'}，需 {NODE_MIN[0]}+，用 winget 安裝 LTS？"):
            winget_install("node", ui)
            ver = self._node_version()
        if not ver or ver < NODE_MIN:
            return ui.result("Node.js", FAIL, f"需要 Node.js {NODE_MIN[0]}+：https://nodejs.org/")
        self.npm = which("npm.cmd", [program_files() / "nodejs" / "npm.cmd"]) or which("npm")
        return ui.result("Node.js", OK, f"v{'.'.join(map(str, ver))}")

    def _find_ollama(self) -> str | None:
        return which("ollama", [localappdata() / "Programs" / "Ollama" / "ollama.exe"])

    def _ensure_ollama(self) -> str:
        ui = self.ui
        self.ollama = self._find_ollama()
        if not self.ollama and self.may_install("找不到 Ollama（小說 AI 分析用），用 winget 安裝？") \
                and winget_install("ollama", ui):
            self.ollama = self._find_ollama()
        if not self.ollama:
            return ui.result("Ollama", WARN, "未安裝：AI 文字／視覺功能不可用。https://ollama.com/download")
        return ui.result("Ollama", OK, self.ollama)

    # 5 ─ ComfyUI
    def step_comfy(self) -> str:
        ui = self.ui
        ui.step(5, self.TOTAL, "ComfyUI 指定與體檢")
        env = self._read_env()
        initial = self.args.comfyui or env.get("COMFYUI_DIR", "")
        root = checks.resolve_comfy_root(Path(initial)) if initial else None
        if root and not self.args.comfyui and not ui.ask(f"使用 ComfyUI：{root}？", True):
            root = None
        while not root:
            path = ui.ask_folder("選擇 ComfyUI 資料夾（portable 根目錄或含 main.py 的 ComfyUI 目錄）", initial)
            if not path:
                return ui.result("ComfyUI", FAIL, "未指定 ComfyUI（安裝說明：https://github.com/comfyanonymous/ComfyUI）")
            root = checks.resolve_comfy_root(Path(path))
            if not root:
                ui.say(f"  {path} 不是 ComfyUI（找不到 main.py + comfy/）")
                if ui.yes or not ui.ask("重新選擇？", True):
                    return ui.result("ComfyUI", FAIL, f"無效的 ComfyUI 路徑：{path}")
        self.comfy_root = root
        ui.say(f"  ComfyUI 目錄：{root}")

        base = env.get("COMFYUI_BASE", DEFAULT_COMFY_URL).rstrip("/")
        obj = http_get_json(f"{base}/object_info", timeout=30)
        self.launcher = self._pick_launcher(root, env.get("COMFYUI_LAUNCHER", ""))
        if obj is None and self.launcher and ui.ask(
                f"ComfyUI 未啟動。現在用 {self.launcher.name} 啟動，做完整節點驗證？", True):
            obj = self._boot_comfy(self.launcher, base)
        if obj is not None:
            stats = http_get_json(f"{base}/system_stats") or {}
            dev = next(iter(stats.get("devices") or []), {})
            if dev and dev.get("type") != "cuda":
                ui.say(f"  ⚠ ComfyUI 目前跑在 {dev.get('type')}（非 CUDA），生圖會極慢")

        needs = checks.load_workflow_needs(self.repo / "data" / "custom_workflows")
        rep = checks.check_comfy(needs, root, obj)
        self._comfy_report = rep
        self._print_comfy(rep)
        mode = "即時驗證" if rep.mode == "live" else "靜態掃描（ComfyUI 未啟動，節點僅比對資料夾）"
        detail = f"{len(rep.ready)}/{len(rep.ready) + len(rep.broken)} 支 workflow 可用｜{mode}"
        # 缺件不擋安裝：小說功能不需要 ComfyUI，補完模型後重跑本程式即可驗證
        return ui.result("ComfyUI", OK if rep.level == OK else WARN, detail)

    def _pick_launcher(self, root: Path, saved: str) -> Path | None:
        if saved and Path(saved).is_file():
            return Path(saved)
        bats = checks.find_launchers(root)
        if len(bats) <= 1:
            return bats[0] if bats else None
        self.ui.say("  找到多個 ComfyUI 啟動檔：")
        for i, b in enumerate(bats, 1):
            self.ui.say(f"    {i}. {b.name}")
        ans = self.ui.ask_text("用哪一個啟動 ComfyUI？輸入編號", "1")
        idx = int(ans) - 1 if ans.isdigit() and 0 < int(ans) <= len(bats) else 0
        return bats[idx]

    def _boot_comfy(self, bat: Path, base: str) -> dict | None:
        ui = self.ui
        try:
            subprocess.Popen([str(bat)], cwd=bat.parent, creationflags=CREATE_NEW_CONSOLE)
        except OSError as e:
            ui.say(f"  無法啟動 {bat.name}：{e}，改用靜態掃描")
            return None
        ui.say(f"  等待 ComfyUI 就緒（最多 {COMFY_BOOT_TIMEOUT_SEC}s）...")
        deadline = time.monotonic() + COMFY_BOOT_TIMEOUT_SEC
        while time.monotonic() < deadline:
            time.sleep(3)
            obj = http_get_json(f"{base}/object_info", timeout=30)
            if obj is not None:
                return obj
        ui.say("  ComfyUI 未在時限內就緒，改用靜態掃描")
        return None

    def _print_comfy(self, rep: checks.ComfyReport) -> None:
        say = self.ui.say
        for name in rep.ready:
            say(f"    ✔ {name}")
        for name, probs in rep.broken.items():
            say(f"    ✘ {name}")
            for p in probs:
                say(f"        - {p}")
        for name in rep.invalid:
            say(f"    ? {name}（非 API 格式或無法解析，略過）")
        if rep.missing_packs:
            say("  缺少的節點包（ComfyUI Manager 搜尋名稱，或 git clone 到 custom_nodes/）：")
            for p in rep.missing_packs.values():
                say(f"    - {p.name}：{p.url}")
        if rep.unknown_classes:
            say("  未登錄的節點（請在 ComfyUI Manager →「Install Missing Custom Nodes」處理）：")
            for c in sorted(rep.unknown_classes):
                say(f"    - {c}")
        say("  選配功能（缺了會自動降級，不影響基本生圖）：")
        for name, ok, detail in rep.optional:
            say(f"    {'✔' if ok else '·'} {name}：{detail}")

    # 6 ─ .env
    def _read_env(self) -> dict[str, str]:
        f = self.repo / ".env" if self.repo else None
        return checks.read_env_values(f.read_text(encoding="utf-8")) if f and f.is_file() else {}

    def step_env(self) -> str:
        ui = self.ui
        ui.step(6, self.TOTAL, "環境設定 .env")
        env_file, example = self.repo / ".env", self.repo / ".env.example"
        created = False
        if not env_file.exists():
            if not example.is_file():
                return ui.result(".env", FAIL, ".env.example 不存在")
            shutil.copyfile(example, env_file)
            created = True
        text = env_file.read_text(encoding="utf-8")
        current = checks.read_env_values(text)
        updates: dict[str, str] = {}
        if self.comfy_root:
            want = {"COMFYUI_DIR": str(self.comfy_root),
                    "COMFYUI_LORAS_DIR": str(self.comfy_root / "models" / "loras")}
            if self.launcher:
                want["COMFYUI_LAUNCHER"] = str(self.launcher)
            for k, v in want.items():
                old = current.get(k)
                if old == v:
                    continue
                if old and not created and not ui.ask(f"{k} 目前是 {old}，改成 {v}？", True):
                    continue
                updates[k] = v
        if updates:
            text = checks.upsert_env(text, updates)
            env_file.write_bytes(text.encode("utf-8"))
        self.env_vals = checks.read_env_values(text)
        what = ("新建自 .env.example" if created else "已存在") + (f"，更新 {', '.join(updates)}" if updates else "")
        return ui.result(".env", OK, what)

    # 7 ─ 後端
    def step_backend(self) -> str:
        ui = self.ui
        ui.step(7, self.TOTAL, "後端（Python venv + 套件）")
        venv = self.repo / "backend" / ".venv"
        vpy = venv / ("Scripts/python.exe" if IS_WIN else "bin/python")
        if vpy.is_file():
            cp = run([vpy, "-c", "import sys;print(sys.version_info[:2]==(3,11))"], ui, timeout=30)
            if (cp.stdout or "").strip() != "True":
                if not ui.ask("既有 backend/.venv 不是 Python 3.11，刪除重建？", True):
                    return ui.result("後端", FAIL, "venv Python 版本不符")
                shutil.rmtree(venv)
        if not vpy.is_file():
            ui.say("  建立 venv...")
            cp = run([self.python, "-m", "venv", venv], ui, capture=False)
            if cp.returncode != 0:
                return ui.result("後端", FAIL, "建立 venv 失敗")
        ui.say("  pip install -r backend/requirements.txt（首次約 2–3 分鐘）...")
        cp = run([vpy, "-m", "pip", "install", "-r", self.repo / "backend" / "requirements.txt",
                  "--disable-pip-version-check"], ui, capture=False)
        if cp.returncode != 0:
            return ui.result("後端", FAIL, f"pip install 失敗（exit {cp.returncode}）")
        return ui.result("後端", OK, f"venv：{venv}")

    # 8 ─ 前端
    def step_frontend(self) -> str:
        ui = self.ui
        ui.step(8, self.TOTAL, "前端（npm）")
        fe = self.repo / "frontend"
        if not self.npm:
            return ui.result("前端", FAIL, "找不到 npm")
        sub = "ci" if (fe / "package-lock.json").is_file() else "install"
        ui.say(f"  npm {sub}...")
        cp = run([self.npm, sub, "--no-audit", "--no-fund"], ui, cwd=fe, capture=False)
        if cp.returncode != 0:
            return ui.result("前端", FAIL, f"npm {sub} 失敗（exit {cp.returncode}）")
        cp = run([self.npm, "run", "build"], ui, cwd=fe, capture=False)
        if cp.returncode != 0:
            return ui.result("前端", WARN, "npm run build 失敗（dev 模式仍可用）")
        return ui.result("前端", OK, "套件已安裝，dist 已建置")

    # 9 ─ Ollama 模型
    def step_ollama(self) -> str:
        ui = self.ui
        ui.step(9, self.TOTAL, "Ollama 服務與模型")
        if not self.ollama:
            return ui.result("Ollama 模型", SKIP, "Ollama 未安裝")
        base = self.env_vals.get("OLLAMA_BASE", DEFAULT_OLLAMA_URL).rstrip("/")
        if http_get_json(f"{base}/api/version") is None:
            ui.say("  Ollama 未啟動，嘗試背景啟動 ollama serve...")
            subprocess.Popen([self.ollama, "serve"], creationflags=DETACHED,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(20):
                time.sleep(1)
                if http_get_json(f"{base}/api/version") is not None:
                    break
            else:
                return ui.result("Ollama 模型", WARN, f"連不上 {base}，請手動開啟 Ollama")
        tags = http_get_json(f"{base}/api/tags") or {}
        have = {m.get("name", "") for m in tags.get("models", [])}
        have |= {n.split(":")[0] for n in have if n.endswith(":latest")}
        wanted = [self.env_vals.get("TEXT_MODEL") or "llama3.2:3b",
                  self.env_vals.get("VISION_MODEL") or "moondream"]
        missing = [m for m in dict.fromkeys(wanted) if m not in have]
        if not missing:
            return ui.result("Ollama 模型", OK, "、".join(wanted) + " 已就緒")
        if not ui.ask(f"下載 .env 指定的模型 {', '.join(missing)}？（之後可在前端設定頁換）", True):
            return ui.result("Ollama 模型", WARN, f"缺 {', '.join(missing)}（ollama pull 手動下載）")
        failed = [m for m in missing if run([self.ollama, "pull", m], ui, capture=False).returncode != 0]
        if failed:
            return ui.result("Ollama 模型", WARN, f"下載失敗：{', '.join(failed)}")
        return ui.result("Ollama 模型", OK, f"已下載 {', '.join(missing)}")

    # 10 ─ 冒煙測試
    def step_smoke(self) -> str:
        ui = self.ui
        ui.step(10, self.TOTAL, "後端啟動測試")
        if port_in_use(BACKEND_SMOKE_PORT):
            return ui.result("冒煙測試", SKIP, f"port {BACKEND_SMOKE_PORT} 已被占用（Craftflow 可能已在執行）")
        vpy = self.repo / "backend" / ".venv" / ("Scripts/python.exe" if IS_WIN else "bin/python")
        log = self.repo / "data" / "logs" / "installer_smoke.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "w", encoding="utf-8") as fh:
            proc = subprocess.Popen([str(vpy), "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
                                     "--port", str(BACKEND_SMOKE_PORT)],
                                    cwd=self.repo / "backend", stdout=fh, stderr=subprocess.STDOUT,
                                    creationflags=CREATE_NO_WINDOW)
            try:
                deadline = time.monotonic() + BACKEND_SMOKE_TIMEOUT_SEC
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        return ui.result("冒煙測試", FAIL, f"後端啟動即結束，見 {log}")
                    if http_get_json(f"http://127.0.0.1:{BACKEND_SMOKE_PORT}/", timeout=2) is not None:
                        return ui.result("冒煙測試", OK, "後端可正常啟動（DB 已自動建立）")
                    time.sleep(1)
                return ui.result("冒煙測試", FAIL, f"{BACKEND_SMOKE_TIMEOUT_SEC}s 內未回應，見 {log}")
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()

    # ── 收尾 ──
    def create_shortcut(self) -> None:
        ui = self.ui
        if not IS_WIN or not ui.ask("在桌面建立「Craftflow」捷徑（執行 start.bat）？", True):
            return
        def q(p: Path) -> str:              # PowerShell 單引號字串跳脫
            return str(p).replace("'", "''")
        ps = ("$d=[Environment]::GetFolderPath('Desktop');"
              "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Craftflow.lnk'));"
              f"$s.TargetPath='{q(self.repo / 'start.bat')}';$s.WorkingDirectory='{q(self.repo)}';$s.Save()")
        cp = run(["powershell", "-NoProfile", "-Command", ps], ui, timeout=30)
        ui.say("  捷徑已建立" if cp.returncode == 0 else "  捷徑建立失敗（可直接執行 start.bat）")

    def write_report(self) -> Path | None:
        if not self.repo:
            return None
        out = self.repo / "data" / "logs" / "install_report.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"Craftflow install report  {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
        lines += [f"{lv:5} {st}：{d}" for st, lv, d in self.ui.rows]
        rep = self._comfy_report
        if rep:
            lines += ["", "[ComfyUI 缺件]"] + sorted(rep.missing_models)
            lines += [f"{p.name} {p.url}" for p in rep.missing_packs.values()]
        lines += ["", "[詳細 log]"] + self.ui.log_lines
        out.write_text("\n".join(lines), encoding="utf-8")
        return out

    def summary(self) -> bool:
        ui = self.ui
        ui.say("\n" + "═" * 60)
        for st, lv, d in ui.rows:
            ui.say(f"  {ui.ICON[lv]} {st:<10} {d}")
        ui.say("═" * 60)
        return not any(lv == FAIL for _, lv, _ in ui.rows)

    def run_all(self) -> int:
        # --check-only 盡量把問題一次列完，只有找不到專案才停
        for fn in (self.step_system, self.step_gpu, self.step_repo, self.step_deps):
            if self._safe(fn) == FAIL and (not self.args.check_only or fn == self.step_repo):
                return self._finish(False)
        self._safe(self.step_comfy)     # 缺件只警告
        if self.args.check_only:
            return self._finish(True)
        for fn in (self.step_env, self.step_backend, self.step_frontend):
            if self._safe(fn) == FAIL:
                return self._finish(False)
        self._safe(self.step_ollama)
        self._safe(self.step_smoke)
        return self._finish(True)

    def _safe(self, fn) -> str:
        """未預期例外記成 FAIL 並寫進報告，不讓視窗直接噴 traceback 關掉。"""
        try:
            return fn()
        except Exception as e:
            import traceback
            self.ui.log(traceback.format_exc())
            return self.ui.result(fn.__name__.removeprefix("step_"), FAIL, f"未預期錯誤：{type(e).__name__}: {e}")

    def _finish(self, ok: bool) -> int:
        ok = self.summary() and ok
        report = self.write_report()
        if report:
            self.ui.say(f"報告：{report}")
        if ok and not self.args.check_only:
            self.ui.say("\n安裝完成。啟動：雙擊專案根目錄的 start.bat（先開 ComfyUI 與 Ollama）")
            self.create_shortcut()
        elif not ok:
            self.ui.say("\n有 FAIL 項目，修正後重新執行本程式即可（已完成的步驟會略過）")
        self.ui.pause()
        return 0 if ok else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Craftflow 一鍵安裝")
    p.add_argument("--repo", help="Craftflow 專案路徑（預設：從本程式位置往上找）")
    p.add_argument("--comfyui", help="ComfyUI 路徑（portable 根目錄或 ComfyUI 目錄）")
    p.add_argument("--yes", "-y", action="store_true", help="所有詢問採預設值（無人值守）")
    p.add_argument("--check-only", action="store_true", help="只做環境體檢，不安裝任何東西")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            os.system("")                 # 啟用 ANSI／UTF-8 主控台
        except Exception:
            pass
    print("Craftflow 一鍵安裝程式\n")
    return Installer(parse_args(argv)).run_all()


if __name__ == "__main__":
    sys.exit(main())
