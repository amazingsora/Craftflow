#!/usr/bin/env python3
"""Craftflow 對話開場狀態摘要（2026-07-26）。

目的：用一次呼叫取代「列目錄 → 讀完整開發記錄 → 讀規劃文件 → 逐檔 grep 核碼」的多輪來回。
輸出刻意壓在 ~40 行以內，只給高訊號資訊；細節要看再針對性讀。

用法：
    python tools/session_status.py            # 狀態摘要
    python tools/session_status.py --todo 30  # 多列幾條未完成項
    python tools/session_status.py --test     # 額外跑 pytest（較慢）
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "doc"
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)\.md$")


def sh(*cmd: str, cwd: Path = ROOT) -> str:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
        return (r.stdout or "").strip()
    except Exception:
        return ""


def git_block() -> list[str]:
    out = []
    branch = sh("git", "rev-parse", "--abbrev-ref", "HEAD") or "?"
    last = sh("git", "log", "-1", "--format=%h %ad %s", "--date=short") or "?"
    status = sh("git", "status", "--porcelain")
    n = len([l for l in status.splitlines() if l.strip()])
    out.append(f"git      : {branch} | {last}")
    out.append(f"           未提交 {n} 檔" + ("" if n == 0 else "  → 提交前確認範圍"))
    if (ROOT / ".git" / "index.lock").exists():
        out.append("           ⚠️ .git/index.lock 存在 → 先刪除，否則 git 全被擋")
    return out


def docs_block() -> tuple[list[str], Path | None]:
    """回傳 (摘要行, 最新且含未完成項的文件)。"""
    files = []
    for p in DOC.glob("*.md"):
        m = DATE_RE.match(p.name)
        if m:
            files.append((m.group(1), m.group(2), p))
    files.sort(key=lambda x: x[0], reverse=True)
    if not files:
        return ["doc      : （無日期檔）"], None

    lines = []
    latest_record = next((f for f in files if "開發記錄" in f[1]), None)
    latest_plan = next((f for f in files if "開發記錄" not in f[1]), None)
    for label, f in (("最新記錄", latest_record), ("最新規劃", latest_plan)):
        if f:
            lines.append(f"{label} : {f[2].name}")

    # 挑「有未完成 checkbox 的最新文件」當待辦來源
    todo_src = None
    for _, _, p in files:
        if "🔲" in p.read_text(encoding="utf-8", errors="ignore"):
            todo_src = p
            break
    return lines, todo_src


def todo_block(src: Path | None, limit: int) -> list[str]:
    if src is None:
        return ["待辦     : （無 🔲 未完成項）"]
    text = src.read_text(encoding="utf-8", errors="ignore")
    done = text.count("✅")
    todos = []
    for line in text.splitlines():
        if "🔲" in line:
            # 抽掉 markdown 裝飾，保留代號與標題
            t = re.sub(r"^[\s\-*]*🔲\s*", "", line)
            t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
            t = re.sub(r"`([^`]*)`", r"\1", t)
            # 只砍「說明尾巴」，不砍開頭的括號註記（如「E-4（條件性）denoise 調校」）
            t = re.split(r"\s*——|\s{2,}#", t)[0].strip()
            todos.append(t[:78] + ("…" if len(t) > 78 else ""))
    out = [f"待辦     : {src.name}  未完成 {len(todos)} / 已完成 {done}"]
    for t in todos[:limit]:
        out.append(f"           🔲 {t}")
    if len(todos) > limit:
        out.append(f"           … 另 {len(todos) - limit} 項（--todo N 展開）")
    return out


def frontend_block() -> list[str]:
    """dist 比 src 舊 → 前端沒重建。2026-07-25 曾因此誤判成功能 bug。"""
    src = ROOT / "frontend" / "src"
    dist = ROOT / "frontend" / "dist"
    if not src.exists():
        return []
    newest_src = max((p.stat().st_mtime for p in src.rglob("*.jsx")), default=0)
    if not dist.exists():
        return ["前端     : 無 dist（開發模式 npm run dev 則正常）"]
    newest_dist = max((p.stat().st_mtime for p in dist.rglob("*")), default=0)
    fmt = lambda t: datetime.fromtimestamp(t).strftime("%m-%d %H:%M")
    if newest_src > newest_dist:
        return [f"前端     : ⚠️ dist({fmt(newest_dist)}) 舊於 src({fmt(newest_src)}) → 需 npm run build"]
    return [f"前端     : dist 已同步（{fmt(newest_dist)}）"]


def test_block() -> list[str]:
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q", "--no-header"],
                       cwd=ROOT / "backend", capture_output=True, text=True, timeout=600)
    tail = [l for l in (r.stdout or "").splitlines() if "passed" in l or "failed" in l]
    return [f"測試     : {tail[-1] if tail else '（無法解析輸出）'}"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--todo", type=int, default=12, help="列出幾條未完成項")
    ap.add_argument("--test", action="store_true", help="額外跑 pytest")
    a = ap.parse_args()

    print(f"=== Craftflow 狀態 @ {datetime.now():%Y-%m-%d %H:%M} ===")
    for l in git_block():
        print(l)
    doc_lines, todo_src = docs_block()
    for l in doc_lines:
        print(l)
    for l in frontend_block():
        print(l)
    if a.test:
        for l in test_block():
            print(l)
    print()
    for l in todo_block(todo_src, a.todo):
        print(l)


if __name__ == "__main__":
    main()
