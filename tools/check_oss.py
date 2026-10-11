#!/usr/bin/env python3
"""公開 repo 隱私閘門：擋不該進 git 的檔案與內容。[CN-135]

用法：
    python tools/check_oss.py                     # 掃已追蹤＋未忽略的新檔（工作樹內容）；CI 與手動檢查
    python tools/check_oss.py --staged            # 只掃 staged 內容；.githooks/pre-commit 呼叫
    python tools/check_oss.py --emit-replace-text replacements.txt   # 給 git filter-repo 改寫歷史

個人詞只在本機存在（CI 讀不到 → 自動略過這一類）：
    .env 的 PERSONAL_STYLE_EXTRA_*／data/custom_tags.json 的 tag 與 label／data/private_terms.txt（一行一詞）
單行豁免：在該行任意位置寫 oss-allow。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 不可被追蹤的路徑（posix 相對路徑）。與 .gitignore 重疊是刻意的：擋的是「已被 add」的情況。
FORBIDDEN_PATHS = [
    r"(^|/)\.env$",
    r"^\.claude/settings\.local\.json$",
    r"^data/(custom_tags\.json|private_terms\.txt|personal_term_map\.local\.yml)$",
    r"^data/(logs|debug|tag_imports|training_images)/",
    r"^doc/",
    r"^Claude outputs/",
    r"^backend/uploads/",
    r"^backend/data/(vision_cache\.json|expand_cache/)",
    r"\.(db|sqlite3)$",
    r"(^|/)mailmap\.txt$",
    r"\.log(\.\d+)?$",
]

# (規則名, 樣式, 允許出現的路徑樣式 or None)
CONTENT_RULES = [
    ("credential",
     r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|\bsk-[A-Za-z0-9_-]{20,}|\bhf_[A-Za-z0-9]{20,}"
     r"|\bAKIA[0-9A-Z]{16}\b|xox[abp]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----",
     None),
    ("home-path", r"[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9][^\\/\s\"'<>]*|/(?:Users|home)/[a-z][\w.-]*", None),
    ("email", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}", None),
    ("bind-all", r"\b0\.0\.0\.0\b", r"(^|/)(Dockerfile|docker-compose\.ya?ml)$"),
]
EMAIL_ALLOWED = re.compile(r"(@users\.noreply\.github\.com|@example\.(com|org)|^git@github\.com)$", re.I)
ALLOW_MARKER = "oss-allow"
BINARY_SNIFF_BYTES = 8192
MIN_ASCII_TERM = 4   # 太短的英文詞（例：ai）誤判率過高
MIN_CJK_TERM = 2
PRIVATE_ENV_KEY = re.compile(r"^\s*(PERSONAL_STYLE_EXTRA_[A-Z0-9_]+)\s*=\s*(.*)$")


def _git(*args: str, raw: bool = False):
    out = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True)
    return out.stdout if raw else out.stdout.decode("utf-8", "replace")


def norm(text: str) -> str:
    """比對用正規化：小寫、底線視為空白、去跳脫反斜線、壓空白。foo_bar 與 Foo Bar 視為同一詞。"""
    return re.sub(r"\s+", " ", text.lower().replace("_", " ").replace("\\", ""))


def _clean_term(raw: str) -> str:
    t = re.sub(r":\s*[\d.]+\s*\)?\s*$", "", raw.strip())     # (tag:1.5) 權重
    return t.strip(" ()@\t").replace("\\", "").strip()


def _keep(term: str) -> bool:
    if not term:
        return False
    has_cjk = re.search(r"[぀-ヿ一-鿿]", term)
    return len(term) >= (MIN_CJK_TERM if has_cjk else MIN_ASCII_TERM)


def load_private_terms(root: Path | None = None) -> dict[str, str]:
    """回傳 {正規化詞: 來源}。檔案不存在（CI）就是空的。"""
    root = root or ROOT
    found: dict[str, str] = {}

    def add(raw: str, source: str) -> None:
        term = _clean_term(raw)
        if _keep(term):
            found.setdefault(norm(term), source)

    env = root / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            m = PRIVATE_ENV_KEY.match(line)
            if m:
                for part in m.group(2).split(","):
                    add(part, f".env:{m.group(1)}")
    tags = root / "data" / "custom_tags.json"
    if tags.exists():
        try:
            data = json.loads(tags.read_text(encoding="utf-8"))
        except ValueError:
            data = {}
        for kind, items in data.items():
            for item in items if isinstance(items, list) else []:
                if isinstance(item, dict):
                    for key in ("tag", "label"):
                        if isinstance(item.get(key), str):
                            add(item[key], f"custom_tags:{kind}")
    extra = root / "data" / "private_terms.txt"
    if extra.exists():
        for line in extra.read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                add(line, "private_terms.txt")
    return found


def mask(term: str) -> str:
    return term if len(term) <= 2 else f"{term[0]}{'*' * (len(term) - 2)}{term[-1]}"


def list_files(staged: bool) -> list[str]:
    if staged:
        out = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    else:   # 已追蹤＋未追蹤但沒被忽略（下次 git add -A 會進去的）
        out = _git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return [p for p in out.split("\0") if p]


def read_blob(path: str, staged: bool) -> bytes | None:
    if staged:
        return _git("show", f":{path}", raw=True)
    full = ROOT / path
    return full.read_bytes() if full.is_file() else None


def scan_text(path: str, text: str, private_re: re.Pattern | None, private: dict[str, str]) -> list[str]:
    findings = []
    rules = [(n, re.compile(p), re.compile(a) if a else None) for n, p, a in CONTENT_RULES]
    for no, line in enumerate(text.splitlines(), 1):
        if ALLOW_MARKER in line:
            continue
        for name, pattern, allowed in rules:
            if allowed and allowed.search(path):
                continue
            for m in pattern.finditer(line):
                hit = m.group(0)
                if name == "email" and EMAIL_ALLOWED.search(hit):
                    continue
                findings.append(f"{path}:{no} [{name}] {hit[:60]}")
        if private_re:
            for m in private_re.finditer(norm(line)):
                findings.append(f"{path}:{no} [private-term] {mask(m.group(0))}（{private[m.group(0)]}）")
    return findings


def scan(files: list[str], staged: bool, private: dict[str, str]) -> list[str]:
    findings = []
    forbidden = [re.compile(p) for p in FORBIDDEN_PATHS]
    private_re = None
    if private:
        alts = sorted(private, key=len, reverse=True)
        private_re = re.compile("|".join(re.escape(t) for t in alts))
    for path in files:
        if any(f.search(path) for f in forbidden):
            findings.append(f"{path} [forbidden-path] 這個檔案不可進 git（git rm --cached 後確認 .gitignore）")
            continue
        blob = read_blob(path, staged)
        if blob is None or b"\0" in blob[:BINARY_SNIFF_BYTES]:
            continue
        findings.extend(scan_text(path, blob.decode("utf-8", "replace"), private_re, private))
    return findings


def replace_text_rules(private: dict[str, str]) -> list[str]:
    """git filter-repo --replace-text 格式；空白與底線互通、不分大小寫。"""
    rules = []
    for term in sorted(private, key=len, reverse=True):
        pattern = r"[ _\\]+".join(re.escape(w) for w in term.split(" "))
        rules.append(f"regex:(?i){pattern}==>***REDACTED***")
    return rules


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="公開 repo 隱私閘門")
    ap.add_argument("--staged", action="store_true", help="只掃 staged 內容（pre-commit 用）")
    ap.add_argument("--emit-replace-text", metavar="PATH", help="輸出 filter-repo 取代規則後結束")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    private = load_private_terms()
    if args.emit_replace_text:
        rules = replace_text_rules(private)
        Path(args.emit_replace_text).write_text("\n".join(rules) + "\n", encoding="utf-8")
        print(f"[check-oss] 已寫出 {len(rules)} 條取代規則 → {args.emit_replace_text}")
        return 0
    try:
        files = list_files(args.staged)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"[check-oss] 無法讀取 git 清單：{exc}", file=sys.stderr)
        return 2
    findings = scan(files, args.staged, private)
    scope = "staged" if args.staged else "repo"
    note = f"個人詞 {len(private)} 個" if private else "個人詞來源不存在（CI 模式）"
    if findings:
        print(f"[check-oss] {scope} {len(files)} 檔，發現 {len(findings)} 處：")
        for f in findings:
            print("  " + f)
        print("修正後重試；確定是誤判就在該行加註 oss-allow。")
        return 1
    print(f"[check-oss] OK — {scope} {len(files)} 檔，{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
