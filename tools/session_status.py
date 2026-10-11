#!/usr/bin/env python3
"""Craftflow 對話開場狀態摘要：git、前端 build、最新記錄的接續摘要、BACKLOG 未完成數。

用法：
    python tools/session_status.py                    # 狀態摘要
    python tools/session_status.py --area VRAM        # 列出 BACKLOG 標題含 VRAM 的未完成項
    python tools/session_status.py --section 新發現    # 印出最新記錄中標題含「新發現」的段落
    python tools/session_status.py --section P-09 --file doc/BACKLOG.md   # 非標題時改列出含該字的行
    python tools/session_status.py --test             # 額外跑 pytest（較慢）
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
BACKLOG = DOC / "BACKLOG.md"
RECORD_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_開發記錄\.md$")
SUMMARY_HEADING = "接續摘要"
OPEN_MARKS = ("🔲", "🟡")
ITEM_WIDTH = 78


def sh(*cmd: str, cwd: Path = ROOT) -> str:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
        return (r.stdout or "").strip()
    except Exception:
        return ""


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


def git_block() -> list[str]:
    branch = sh("git", "rev-parse", "--abbrev-ref", "HEAD") or "?"
    last = sh("git", "log", "-1", "--format=%h %ad %s", "--date=short") or "?"
    n = len([l for l in sh("git", "status", "--porcelain").splitlines() if l.strip()])
    out = [f"git      : {branch} | {last}",
           f"           未提交 {n} 檔" + ("" if n == 0 else "  → 提交前確認範圍")]
    if (ROOT / ".git" / "index.lock").exists():
        out.append("           ⚠️ .git/index.lock 存在 → 先刪除，否則 git 全被擋")
    return out


def frontend_block() -> list[str]:
    """dist 比 src 舊＝前端沒重建，實測會被誤判成功能 bug。"""
    src, dist = ROOT / "frontend" / "src", ROOT / "frontend" / "dist"
    if not src.exists():
        return []
    newest_src = max((p.stat().st_mtime for p in src.rglob("*.js*")), default=0)
    if not dist.exists():
        return ["前端     : 無 dist（開發模式 npm run dev 則正常）"]
    newest_dist = max((p.stat().st_mtime for p in dist.rglob("*")), default=0)
    fmt = lambda t: datetime.fromtimestamp(t).strftime("%m-%d %H:%M")
    if newest_src > newest_dist:
        return [f"前端     : ⚠️ dist({fmt(newest_dist)}) 舊於 src({fmt(newest_src)}) → 需 npm run build"]
    return [f"前端     : dist 已同步（{fmt(newest_dist)}）"]


def latest_record() -> Path | None:
    recs = sorted((p for p in DOC.glob("*.md") if RECORD_RE.match(p.name)), key=lambda p: p.name)
    return recs[-1] if recs else None


def section(text: str, keyword: str) -> list[str]:
    """回傳第一個標題含 keyword 的段落（到下一個同級或更高級標題為止）。"""
    lines = text.splitlines()
    for i, l in enumerate(lines):
        m = re.match(r"^(#+)\s", l)
        if m and keyword in l:
            level = len(m.group(1))
            body = [l]
            for nxt in lines[i + 1:]:
                m2 = re.match(r"^(#+)\s", nxt)
                if m2 and len(m2.group(1)) <= level:
                    break
                body.append(nxt)
            while body and not body[-1].strip():
                body.pop()
            return body
    return []


def summary_block(rec: Path | None) -> list[str]:
    if rec is None:
        return ["最新記錄 : （無）"]
    text = read(rec)
    out = [f"最新記錄 : doc/{rec.name}"]
    body = section(text, SUMMARY_HEADING)
    if body:
        out += ["", *body]
    else:
        heads = [l for l in text.splitlines() if l.startswith("## ")]
        out.append(f"           （無「{SUMMARY_HEADING}」，章節：{' / '.join(h[3:] for h in heads) or '無'}）")
    return out


def _clean(t: str) -> str:
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    return t[:ITEM_WIDTH] + ("…" if len(t) > ITEM_WIDTH else "")


REJECTED = re.compile(r"否決|推翻|排除|方向錯")
PENDING = re.compile(r"待|驗收|未處理|^⚠️")


def _status_cell(cells: list[str], idx: int | None) -> str:
    if idx is not None and idx < len(cells):
        return cells[idx]
    return [c for c in cells if c][-1]


def open_items(text: str) -> list[tuple[str, str, str]]:
    """(所屬 ## 標題, 標記, 項目摘要)。🔲＝未做；⏳＝程式完成、待本機驗收或待決定。狀態欄依表頭「狀態」定位。"""
    items, sec, status_idx = [], "", None
    lines = text.splitlines()
    sep = re.compile(r"^\|\s*:?-{2,}")
    for i, l in enumerate(lines):
        if l.startswith("## "):
            sec = l[3:].strip()
            continue
        if l.startswith("|") and not sep.match(l):
            cells = [c.strip() for c in l.strip().strip("|").split("|")]
            if i + 1 < len(lines) and sep.match(lines[i + 1]):
                status_idx = next((k for k, c in enumerate(cells) if "狀態" in c), None)
                continue
            if len(cells) < 2 or any(m in cells[0] for m in OPEN_MARKS):
                continue
            st = _status_cell(cells, status_idx)
            if st.startswith(OPEN_MARKS) or (st.startswith("❌") and not REJECTED.search(l)):
                mark = "🔲"
            elif PENDING.search(st) and not st.startswith(("⬛", "⏭", "⏸", "✅")) or (st.startswith("✅") and PENDING.search(st)):
                mark = "⏳"
            else:
                continue
            label = cells[0] if len(cells) > 2 and len(cells[0]) <= 12 else ""
            middle = [c for k, c in enumerate(cells) if k not in (0, status_idx)] if label else [cells[0]]
            desc = max(middle, key=len) if middle else ""
            items.append((sec, mark, _clean(f"{label} {desc}".strip())))
        elif re.match(r"^\s*[-*]\s*(🔲|🟡)", l):
            items.append((sec, "🔲", _clean(re.sub(r"^\s*[-*]\s*(🔲|🟡)\s*", "", l))))
    return items


def backlog_block(area: str | None) -> list[str]:
    if not BACKLOG.exists():
        return ["BACKLOG  : （無）"]
    items = open_items(read(BACKLOG))
    counts: dict[str, list[int]] = {}
    for sec, mark, _ in items:
        c = counts.setdefault(sec, [0, 0])
        c[0 if mark == "🔲" else 1] += 1
    todo = sum(c[0] for c in counts.values())
    out = [f"BACKLOG  : 🔲 未做 {todo}／⏳ 待驗收或待決定 {len(items) - todo}（已完成項在 doc/archive/BACKLOG_done.md）"]
    out += [f"           🔲{c[0]:3d} ⏳{c[1]:3d}  {sec[:56]}" for sec, c in counts.items()]
    if area:
        picked = [(m, t) for sec, m, t in items if area in sec]
        out += ["", f"── 區塊含「{area}」的未完成項（{len(picked)}）"] + [f"  {m} {t}" for m, t in picked]
    return out


def test_block() -> list[str]:
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q", "--no-header"],
                       cwd=ROOT / "backend", capture_output=True, text=True, timeout=600)
    tail = [l for l in (r.stdout or "").splitlines() if "passed" in l or "failed" in l]
    return [f"測試     : {tail[-1] if tail else '（無法解析輸出）'}"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", help="列出 BACKLOG 標題含此字串的未完成項")
    ap.add_argument("--section", help="只印出標題含此字串的段落")
    ap.add_argument("--file", help="--section 的來源檔（預設最新開發記錄）")
    ap.add_argument("--test", action="store_true", help="額外跑 pytest")
    a = ap.parse_args()

    if a.section:
        src = Path(a.file) if a.file else latest_record()
        if src is not None and not src.is_absolute():
            src = ROOT / src
        if src is None or not src.exists():
            print(f"（找不到檔案：{src}）")
            return
        text = read(src)
        body = section(text, a.section) or [
            f"{i}: {l}" for i, l in enumerate(text.splitlines(), 1) if a.section in l]
        print("\n".join(body) if body else f"（{src.name} 沒有含「{a.section}」的標題或行）")
        return

    print(f"=== Craftflow 狀態 @ {datetime.now():%Y-%m-%d %H:%M} ===")
    for l in git_block() + frontend_block() + (test_block() if a.test else []):
        print(l)
    print()
    for l in backlog_block(a.area):
        print(l)
    print()
    for l in summary_block(latest_record()):
        print(l)


if __name__ == "__main__":
    main()
