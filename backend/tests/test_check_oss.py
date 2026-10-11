"""CN-135：公開 repo 隱私閘門 tools/check_oss.py。每條規則都配一組「該擋／不該擋」對照。"""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "check_oss", Path(__file__).resolve().parents[2] / "tools" / "check_oss.py")
oss = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(oss)

# 樣本字串用拼接寫成，避免本檔自己被閘門擋下
_EMAIL = "alice@" + "gmail.com"
_BIND = "0.0.0" + ".0"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="需要 git")


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q")
    monkeypatch.setattr(oss, "ROOT", tmp_path)
    return tmp_path


def _run(repo, files, *argv, add=True):
    for name, text in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    if add:
        _git(repo, "add", "-A")
    return oss.main(list(argv))


def test_clean_repo_passes(repo):
    assert _run(repo, {"a.py": "print('hello')\n", "b.md": "contact: someone@example.com\n"}) == 0


@pytest.mark.parametrize("text", [
    "token = 'ghp_" + "a" * 36 + "'",
    "key=sk-" + "b" * 32,
    "-----BEGIN OPENSSH " + "PRIVATE KEY-----",
    "path C:\\" + "Users\\alice\\Desktop",
    "/ho" + "me/alice/projects",
    "mail me: " + _EMAIL,
    "uvicorn main:app --host " + _BIND,
])
def test_generic_rules_block(repo, text):
    assert _run(repo, {"x.md": text + "\n"}) == 1


@pytest.mark.parametrize("text", [
    "git@github.com:someone/repo.git",
    "1+someone@users.noreply.github.com",
    r"C:\Users\<name>\Desktop",
    "host 127.0.0.1",
    "uvicorn --host 0.0.0.0  # oss-allow",
])
def test_generic_rules_allow(repo, text):
    assert _run(repo, {"x.md": text + "\n"}) == 0


def test_bind_all_allowed_in_docker_files(repo):
    assert _run(repo, {"Dockerfile": f'CMD ["uvicorn", "--host", "{_BIND}"]\n'}) == 0


@pytest.mark.parametrize("path", [".env", "data/custom_tags.json", ".claude/settings.local.json",
                                  "backend/craftflow.db", "doc/notes.md", "data/logs/backend.log"])
def test_forbidden_paths_block(repo, path):
    assert _run(repo, {path: "x\n"}) == 1


def test_env_example_is_not_forbidden(repo):
    assert _run(repo, {".env.example": "OLLAMA_BASE=http://localhost:11434\n"}) == 0


def _private_sources(repo):
    """本機個人詞來源本身不追蹤（如同真實 .gitignore）。"""
    (repo / ".gitignore").write_text(".env\ndata/custom_tags.json\ndata/private_terms.txt\n", encoding="utf-8")
    (repo / "data").mkdir(exist_ok=True)
    (repo / "data" / "custom_tags.json").write_text(json.dumps(
        {"series": [{"label": "範例作品", "tag": "sample series"}],
         "artists": [{"label": "ab", "tag": "ab"}]}, ensure_ascii=False), encoding="utf-8")
    (repo / ".env").write_text("PERSONAL_STYLE_EXTRA_ANIMA=(@mori taarou:1.5)\n"
                               "PERSONAL_NEGATIVE_EXTRA_ANIMA=(halo:1.5)\n", encoding="utf-8")
    (repo / "data" / "private_terms.txt").write_text("# 註解\n角色甲乙\n", encoding="utf-8")


@pytest.mark.parametrize("text", ["tags: Sample_Series, x", "畫風：範例作品", "prompt: @mori_taarou",
                                  r"mori \taarou", "主角是角色甲乙"])
def test_private_terms_block_variants(repo, text):
    _private_sources(repo)
    assert _run(repo, {"t.py": text + "\n"}) == 1


def test_private_terms_skip_negative_and_short(repo):
    """負向（halo）不是個人身分；太短的英文詞（ab）誤判率高，不收。"""
    _private_sources(repo)
    terms = oss.load_private_terms(repo)
    assert "sample series" in terms and "mori taarou" in terms and "角色甲乙" in terms
    assert "halo" not in terms and "ab" not in terms
    assert _run(repo, {"t.py": "negative: halo, ab\n"}) == 0


def test_without_private_sources_only_generic_rules(repo):
    """CI 模式：沒有 .env／custom_tags → 個人詞清單為空，不誤擋。"""
    assert oss.load_private_terms(repo) == {}
    assert _run(repo, {"t.py": "sample series\n"}) == 0


def test_staged_scans_index_not_worktree(repo):
    _run(repo, {"a.md": "fine\n"})
    (repo / "a.md").write_text(_EMAIL + "\n", encoding="utf-8")   # 只改工作樹、未 add
    assert oss.main(["--staged"]) == 0
    _git(repo, "add", "a.md")
    assert oss.main(["--staged"]) == 1


def test_untracked_files_are_scanned_in_repo_mode(repo):
    assert _run(repo, {"new.md": _EMAIL + "\n"}, add=False) == 1


def test_binary_files_are_skipped(repo):
    (repo / "img.png").write_bytes(b"\x89PNG\0\0 " + _EMAIL.encode())
    _git(repo, "add", "-A")
    assert oss.main([]) == 0


def test_replace_text_rules_cover_variants(repo, tmp_path):
    import re
    _private_sources(repo)
    out = tmp_path / "r.txt"
    assert oss.main(["--emit-replace-text", str(out)]) == 0
    rules = out.read_text(encoding="utf-8").splitlines()
    pats = [re.compile(r.split("==>")[0][len("regex:"):]) for r in rules]
    for sample in ("Sample_Series", "sample series", "MORI TAAROU", "角色甲乙"):
        assert any(p.search(sample) for p in pats), sample
    assert not any(p.search("halo") for p in pats)
