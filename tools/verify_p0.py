"""A3 P0 可重現實驗台 —— 本機驗收腳本。

驗收命題（doc/BACKLOG.md A3 P0）：
    同 seed ＋ 沿用 prompt 連按兩次 → 輸出一致。

為什麼要跑三次而不是兩次：
    Run A（reuse_prompt=False）只是「造樣本」—— 它必須先寫一筆 generation_history，
    Run B 才有東西可沿用。A 自己走 compile_prompt()（LLM temperature=0.3、無 seed），
    本來就不保證可重現，**不列入 PASS 判定**。
    真正的驗收是 B vs C：兩次都 reuse_prompt=True + 同 seed，必須逐位元組相同。

零依賴（只用標準庫），請在**本機**執行（沙箱連不到 ComfyUI/Ollama）：
    python tools/verify_p0.py --character 1 --seed 12345
    python tools/verify_p0.py --character 1 --slot 2 --seed 12345   # 變體端點
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_BASE = "http://localhost:8000"
API_PREFIX = "/api/v1"
# 生圖含外擴可能數分鐘，逾時放寬；比 poll timeout 寬鬆即可
HTTP_TIMEOUT_SEC = 900
# P0-4 要求 params 內必須有的實際值
REQUIRED_PARAM_KEYS = ("workflow", "cfg", "steps")


def _decode_header(value: str | None) -> str:
    """X-Prompt / X-Coverage / X-Timings 都是 base64（header 不能放非 ASCII）。"""
    if not value:
        return ""
    try:
        return base64.b64decode(value).decode("utf-8", "replace")
    except Exception:
        return value


def _post_generate(base: str, character: int, slot: int | None, seed: int,
                   reuse_prompt: bool, extra: dict[str, str]) -> tuple[bytes, dict[str, str], float]:
    if slot is None:
        path = f"{API_PREFIX}/characters/{character}/generate-design"
    else:
        path = f"{API_PREFIX}/characters/{character}/variants/{slot}/generate-design"
    query = {"seed": str(seed), "reuse_prompt": "true" if reuse_prompt else "false"}
    query.update(extra)
    url = f"{base}{path}?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(url, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
            body = resp.read()
            headers = {k: v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise SystemExit(f"[FAIL] {url}\n  HTTP {exc.code}: {detail}")
    except urllib.error.URLError as exc:
        raise SystemExit(f"[FAIL] 連不上後端 {base}（{exc.reason}）—— 請確認後端已啟動。")
    return body, headers, round(time.perf_counter() - t0, 1)


def _get_json(base: str, path: str, query: dict[str, str] | None = None):
    url = f"{base}{API_PREFIX}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # 查詢失敗不該擋住主驗收，降級為警告
        print(f"  ⚠ 查詢 {path} 失敗：{exc}")
        return None


def _run(base: str, character: int, slot: int | None, seed: int, reuse: bool,
         label: str, out_dir: Path, extra: dict[str, str]) -> dict:
    print(f"\n▶ Run {label}（seed={seed}, reuse_prompt={reuse}）…", flush=True)
    body, headers, elapsed = _post_generate(base, character, slot, seed, reuse, extra)
    png = out_dir / f"p0_{label}.png"
    png.write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    prompt = _decode_header(headers.get("X-Prompt"))
    info = {
        "label": label,
        "sha256": digest,
        "bytes": len(body),
        "seed_header": headers.get("X-Seed", ""),
        "prompt": prompt,
        "prompt_sha": hashlib.sha256(prompt.encode()).hexdigest()[:12],
        "profile": _decode_header(headers.get("X-Prompt-Profile")),
        "coverage": _decode_header(headers.get("X-Coverage")),
        "timings": _decode_header(headers.get("X-Timings")),
        "cn_mode": headers.get("X-CN-Mode", ""),
        "elapsed": elapsed,
        "file": str(png),
    }
    print(f"  {elapsed}s  sha256={digest[:16]}…  X-Seed={info['seed_header']}  "
          f"profile={info['profile']}  prompt_sha={info['prompt_sha']}")
    if info["coverage"]:
        print(f"  coverage: {info['coverage']}")
    return info


def main() -> int:
    ap = argparse.ArgumentParser(description="A3 P0 可重現實驗台驗收")
    ap.add_argument("--character", type=int, required=True, help="角色 ID")
    ap.add_argument("--slot", type=int, default=None, help="變體 slot（省略＝主角色端點）")
    ap.add_argument("--seed", type=int, default=12345, help="固定 seed（須 >=0）")
    ap.add_argument("--base", default=DEFAULT_BASE, help=f"後端位址（預設 {DEFAULT_BASE}）")
    ap.add_argument("--out", default="data/p0_verify", help="輸出圖片目錄")
    ap.add_argument("--expression", default=None, help="表情 key（省略＝全身人設圖）")
    ap.add_argument("--check-random", action="store_true",
                    help="額外跑一次 seed=-1，確認零回歸（隨機路徑仍在）")
    args = ap.parse_args()

    if args.seed < 0:
        print("[FAIL] --seed 必須 >=0（-1 是隨機路徑，無法驗可重現）")
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    extra: dict[str, str] = {}
    if args.expression:
        extra["expression"] = args.expression

    endpoint_desc = f"character {args.character}" + (f" / variant {args.slot}" if args.slot is not None else "")
    print(f"=== A3 P0 驗收：{endpoint_desc} @ {args.base} ===")

    a = _run(args.base, args.character, args.slot, args.seed, False, "A_compile", out_dir, extra)
    b = _run(args.base, args.character, args.slot, args.seed, True, "B_reuse1", out_dir, extra)
    c = _run(args.base, args.character, args.slot, args.seed, True, "C_reuse2", out_dir, extra)

    print("\n=== 判定 ===")
    failures: list[str] = []

    # 主判定：B vs C 逐位元組相同
    if b["sha256"] == c["sha256"]:
        print("✅ P0 主判定：B/C 兩次輸出逐位元組相同")
    else:
        failures.append("B/C 圖片不同 —— 同 seed + 沿用 prompt 仍不可重現")
        print(f"❌ P0 主判定：B={b['sha256'][:16]}… C={c['sha256'][:16]}…")

    # prompt 凍結（P0-3）
    if b["prompt"] == c["prompt"] and b["prompt"]:
        print("✅ P0-3：兩次 prompt 逐字相同")
    else:
        failures.append("B/C prompt 不同 —— reuse_prompt 未真正凍結")
        print("❌ P0-3：prompt 不同")
    if b["profile"] == "reused-history":
        print("✅ P0-3：X-Prompt-Profile=reused-history（確實走沿用分支）")
    else:
        failures.append(f"B 的 profile={b['profile']!r}，未走 reuse 分支（可能查不到 history）")
        print(f"❌ P0-3：profile={b['profile']!r}，未走 reuse 分支")

    # seed 貫通（P0-1）
    if b["seed_header"] == str(args.seed) == c["seed_header"]:
        print(f"✅ P0-1：X-Seed 回傳指定值 {args.seed}")
    else:
        failures.append("X-Seed 與指定 seed 不符 —— seed 未貫通到 service")
        print(f"❌ P0-1：X-Seed B={b['seed_header']} C={c['seed_header']} 期望 {args.seed}")

    # 參考資訊：A vs B（compile 端穩定度，不列入 PASS）
    same_prompt = "相同" if a["prompt"] == b["prompt"] else "不同"
    same_img = "相同" if a["sha256"] == b["sha256"] else "不同"
    print(f"ℹ 參考：A(compile) vs B(reuse) → prompt {same_prompt}、圖片 {same_img}"
          "（A 走 LLM 編譯，不同屬預期，見 P3-3 variance 量測）")

    # P0-4：params 補記
    hist = _get_json(args.base, "/generation-history",
                     {"character_id": str(args.character), "limit": "3"})
    if hist:
        latest = _get_json(args.base, f"/generation-history/{hist[0]['id']}")
        params = (latest or {}).get("params") or {}
        missing = [k for k in REQUIRED_PARAM_KEYS if k not in params]
        if missing:
            failures.append(f"generation_history.params 缺 {missing}")
            print(f"❌ P0-4：params 缺 {missing}（現有 keys: {sorted(params)}）")
        else:
            print(f"✅ P0-4：params 已記 workflow={params.get('workflow')} "
                  f"cfg={params.get('cfg')} steps={params.get('steps')}")

    # 零回歸：seed=-1 仍是隨機
    if args.check_random:
        print("\n▶ 零回歸檢查（seed=-1 應為隨機）…", flush=True)
        body, headers, elapsed = _post_generate(args.base, args.character, args.slot, -1, True, extra)
        rnd_seed = headers.get("X-Seed", "")
        (out_dir / "p0_D_random.png").write_bytes(body)
        if rnd_seed and rnd_seed != str(args.seed):
            print(f"✅ P0-1 零回歸：seed=-1 產生隨機 seed {rnd_seed}（{elapsed}s）")
        else:
            failures.append(f"seed=-1 未走隨機路徑（X-Seed={rnd_seed}）")
            print(f"❌ P0-1 零回歸：X-Seed={rnd_seed}")

    report = {"args": vars(args), "runs": [a, b, c], "failures": failures}
    (out_dir / "p0_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n輸出：{out_dir.resolve()}")
    if failures:
        print("\n=== ❌ P0 未通過 ===")
        for f in failures:
            print(f"  - {f}")
        print("依 BACKLOG 規定：P0 未過，不進 P1 之後的任何 A/B。")
        return 1
    print("\n=== ✅ P0 通過 —— 可解鎖 P2-4 / P4-3 / P5 A/B 與 A2 Q1~Q5 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
