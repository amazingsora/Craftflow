#!/usr/bin/env python3
"""拆裝備可行性實測（不進產線）：本機 Ollama 視覺模型列出立繪上的裝備＋bbox，畫框輸出供目視。

用法（專案根目錄，用後端 venv，需要 Pillow）：
    backend\\.venv\\Scripts\\python tools\\probe_decompose.py <圖檔> [<圖檔> ...]
        [--model 模型名]   預設讀 data/runtime_state.json 的 vision_model
        [--max-px 768]     送圖前把長邊縮到這個值（與產線 _VISION_MAX_PX 相同）
        [--think]          開 thinking（預設關）
輸出：Claude outputs/decompose_probe/<圖名>__<模型>.png（同一組框用三種座標解讀並排）與 .json（原始回覆＋耗時）。
看哪一欄的框貼合衣物，就知道模型用哪種座標；三欄都不貼 ⇒ 這個模型不能直接拿來框。
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "Claude outputs" / "decompose_probe"
KINDS = ["garment", "footwear", "accessory", "weapon", "other"]
COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#46f0f0", "#f032e6", "#bcf60c", "#008080", "#9a6324"]
PANEL_HEIGHT = 900
TIMEOUT_SEC = 600

PROMPT = """You are looking at an anime character design image.
List every separately designable clothing item and accessory worn or carried by the main character
(for example jacket, shirt, skirt or pants, shoes, hair ornament, earrings, necklace, gloves, bag, belt, weapon).
Body parts, the face and the hair itself are not items; hair ornaments are.
If the image shows the same character several times, use only the largest full-body front view.
At most 10 items, ordered from head to toe.
For each item give:
- label: short English name
- name_zh: name in Traditional Chinese
- kind: one of garment, footwear, accessory, weapon, other
- bbox_2d: [x1, y1, x2, y2], the tight bounding box of that item in the image
Answer with JSON only."""

SCHEMA = {
    "type": "object",
    "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "required": ["label", "name_zh", "kind", "bbox_2d"],
        "properties": {
            "label": {"type": "string"}, "name_zh": {"type": "string"},
            "kind": {"type": "string", "enum": KINDS},
            "bbox_2d": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
        },
    }}},
}


def _env_value(key: str, default: str) -> str:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            m = re.match(rf"\s*{key}\s*=\s*(\S+)", line)
            if m:
                return m.group(1)
    return os.getenv(key, default)


def _default_model() -> str:
    try:
        return json.loads((ROOT / "data" / "runtime_state.json").read_text(encoding="utf-8"))["vision_model"]
    except (OSError, ValueError, KeyError):
        return "qwen2.5vl:7b"


def _encode(img: Image.Image, max_px: int) -> tuple[str, tuple[int, int]]:
    w, h = img.size
    if max(w, h) > max_px:
        scale = max_px / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode(), img.size


def ask(base: str, model: str, b64: str, think: bool) -> tuple[dict, float]:
    payload = {"model": model, "stream": False, "think": think, "format": SCHEMA, "keep_alive": 0,
               "options": {"temperature": 0, "num_predict": 4096},
               "messages": [{"role": "user", "content": PROMPT, "images": [b64]}]}
    req = urllib.request.Request(f"{base}/api/chat", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as r:
        body = json.loads(r.read())
    return body, time.time() - t0


def interpretations(box: list[float], sent: tuple[int, int], orig: tuple[int, int]) -> dict[str, tuple]:
    """同一組數字的三種讀法，全部換算成原圖像素。"""
    (sw, sh), (ow, oh) = sent, orig
    x1, y1, x2, y2 = box
    return {
        "unit(0-1)": (x1 * ow, y1 * oh, x2 * ow, y2 * oh),
        "norm(0-1000)": (x1 / 1000 * ow, y1 / 1000 * oh, x2 / 1000 * ow, y2 / 1000 * oh),
        "pixel(送出圖)": (x1 / sw * ow, y1 / sh * oh, x2 / sw * ow, y2 / sh * oh),
    }


def render(img: Image.Image, items: list[dict], sent: tuple[int, int], out: Path) -> dict[str, int]:
    names = list(interpretations([0, 0, 1, 1], sent, img.size))
    panels, inside = [], {n: 0 for n in names}
    for name in names:
        panel = img.convert("RGB").copy()
        draw = ImageDraw.Draw(panel)
        for i, it in enumerate(items):
            x1, y1, x2, y2 = interpretations(it["bbox_2d"], sent, img.size)[name]
            if 0 <= x1 < x2 <= img.width * 1.02 and 0 <= y1 < y2 <= img.height * 1.02:
                inside[name] += 1
            color = COLORS[i % len(COLORS)]
            draw.rectangle([x1, y1, x2, y2], outline=color, width=max(3, img.width // 200))
            draw.text((x1 + 4, y1 + 4), f"{i + 1}.{it.get('label', '')}", fill=color)
        draw.text((10, 10), name, fill="#000000")
        scale = PANEL_HEIGHT / panel.height
        panels.append(panel.resize((int(panel.width * scale), PANEL_HEIGHT)))
    sheet = Image.new("RGB", (sum(p.width for p in panels), PANEL_HEIGHT), "white")
    x = 0
    for p in panels:
        sheet.paste(p, (x, 0))
        x += p.width
    sheet.save(out)
    return inside


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("images", nargs="+")
    ap.add_argument("--model", default=None)
    ap.add_argument("--max-px", type=int, default=768)
    ap.add_argument("--think", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    base = _env_value("OLLAMA_BASE", "http://127.0.0.1:11434").rstrip("/")
    model = args.model or _default_model()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", model)
    print(f"model={model}  ollama={base}  max_px={args.max_px}")
    for path in map(Path, args.images):
        img = Image.open(path)
        b64, sent = _encode(img, args.max_px)
        try:
            body, sec = ask(base, model, b64, args.think)
        except Exception as exc:   # 連不上／逾時：印出來換下一張，不中斷整批
            print(f"[{path.name}] 失敗：{exc}")
            continue
        msg = body.get("message", {})
        raw = msg.get("content", "")
        print(f"[{path.name}] {sec:.1f}s  RAW(len={len(raw)})  thinking(len={len(msg.get('thinking') or '')})"
              f"  eval_count={body.get('eval_count')}")
        stem = f"{path.stem}__{slug}"
        (OUT_DIR / f"{stem}.json").write_text(json.dumps(
            {"model": model, "image": str(path), "orig_size": img.size, "sent_size": sent, "seconds": round(sec, 1),
             "raw": raw, "thinking": msg.get("thinking")}, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            items = [it for it in json.loads(raw)["items"] if len(it.get("bbox_2d", [])) == 4]
        except (ValueError, KeyError, TypeError):
            print("  回覆不是預期的 JSON，原文已存 .json")
            continue
        for i, it in enumerate(items, 1):
            print(f"  {i:>2}. {it.get('name_zh', ''):<10} {it.get('kind', ''):<9} {it['bbox_2d']}")
        inside = render(img, items, sent, OUT_DIR / f"{stem}.png")
        print(f"  框在圖內的數量（{len(items)} 件中）：{inside}")
        print(f"  → {OUT_DIR / (stem + '.png')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
