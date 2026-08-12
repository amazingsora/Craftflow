"""ComfyUI VRAM 取樣探針（2026-07-27）。

用途：查清「工作流內嵌 checkpoint 與全域設定不同時，ComfyUI 是否同時快取兩個模型」。
2026-07-26 log 中 torch_vram_total 一路漲到 16.2G（超過 16GB 卡容量），懷疑雙模型駐留。

執行（本機，ComfyUI 要開著）：
    cd backend && python tools/vram_probe.py               # 每 2 秒取樣，Ctrl-C 結束
    cd backend && python tools/vram_probe.py --interval 1 --csv probe.csv

判讀方式：
    1. 重啟 ComfyUI → 跑本探針 → 記下 baseline reserved（應接近 0）
    2. 用 Standard_V37（內嵌 fabricatedXL_v70）生一張 → reserved 停在 A
    3. 把全域 checkpoint 切成別的模型再生一張 → reserved 停在 B
       B ≈ A          → 只快取一個，會換出換入
       B ≈ A + 單模型  → **雙模型同時駐留**，即 16.2G 的來源
"""
from __future__ import annotations

import argparse
import sys
import time

import requests

_GIB = 1024 ** 3
_DEFAULT_BASE = "http://127.0.0.1:8188"


def sample(base: str) -> dict:
    stats = requests.get(f"{base}/system_stats", timeout=5).json()
    dev = (stats.get("devices") or [{}])[0]
    return {
        "name": dev.get("name", "?"),
        "total": int(dev.get("vram_total", 0)) / _GIB,
        "free": int(dev.get("vram_free", 0)) / _GIB,
        "reserved": int(dev.get("torch_vram_total", 0)) / _GIB,
        "torch_free": int(dev.get("torch_vram_free", 0)) / _GIB,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=_DEFAULT_BASE, help="ComfyUI base URL")
    ap.add_argument("--interval", type=float, default=2.0, help="取樣間隔（秒）")
    ap.add_argument("--csv", default=None, help="同時寫出 CSV")
    args = ap.parse_args()

    try:
        first = sample(args.base)
    except Exception as e:
        print(f"無法連線 ComfyUI（{args.base}）：{e}", file=sys.stderr)
        return 1

    print(f"device: {first['name']}  total={first['total']:.1f}G")
    print(f"{'time':>8}  {'free':>7}  {'reserved':>9}  {'peak':>7}  note")

    csv = open(args.csv, "w", encoding="utf-8", newline="") if args.csv else None
    if csv:
        csv.write("time,free_g,reserved_g,total_g,overcommit\n")

    peak = 0.0
    try:
        while True:
            s = sample(args.base)
            peak = max(peak, s["reserved"])
            over = bool(s["total"]) and s["reserved"] > s["total"]
            note = "OVERCOMMIT → 已溢出系統 RAM" if over else ""
            ts = time.strftime("%H:%M:%S")
            print(f"{ts:>8}  {s['free']:>6.1f}G  {s['reserved']:>8.1f}G  {peak:>6.1f}G  {note}")
            if csv:
                csv.write(f"{ts},{s['free']:.2f},{s['reserved']:.2f},{s['total']:.2f},{int(over)}\n")
                csv.flush()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print(f"\npeak reserved = {peak:.1f}G / total {first['total']:.1f}G")
        if first["total"] and peak > first["total"]:
            print("→ 峰值已超過顯卡容量，確認有系統 RAM 溢出（生成會慢上數倍）。")
    finally:
        if csv:
            csv.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
