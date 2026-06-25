"""
test_vision_models.py — 對所有 Ollama 視覺模型跑同一張圖 + 同一個 prompt。

完全對齊 Craftflow 線上行為：
  - 圖片 resize 最長邊 768px（單圖，同 ollama_client._VISION_MAX_PX）
  - think:false、num_predict、temperature:0.1（同 vision_extract 合併呼叫）
  - 解析時先去除 <think>…</think>，再抽 COVERAGE / FEATURES（同 vision_extract）

診斷「回空」：自動抓 Ollama 回傳的 thinking 欄位、done_reason、eval_count，
判斷 token 是燒在思考（thinking 有料但 response 空）還是被截斷（done_reason=length）。

用法：
  python test_vision_models.py F:/TESTPIC/t1.png
  python test_vision_models.py F:/TESTPIC/t1.png --prompt portrait
  python test_vision_models.py F:/TESTPIC/t1.png --models qwen2.5vl:7b,llava:13b
  python test_vision_models.py F:/TESTPIC/t1.png --max-params 14
  python test_vision_models.py F:/TESTPIC/t1.png --num-predict 1024
  python test_vision_models.py F:/TESTPIC/t1.png --host http://localhost:11434
  python test_vision_models.py F:/TESTPIC/t1.png --all-models   # 不過濾，全部硬跑

依賴：requests、Pillow（專案 backend 已裝；若無：pip install requests pillow）
"""
from __future__ import annotations

import argparse
import base64
import io
import re
import sys
import time
from pathlib import Path

import requests
from PIL import Image

# ── 與專案一致的常數 ─────────────────────────────────────────────────────────
VISION_MAX_PX = 768
DEFAULT_NUM_PREDICT = 512
TIMEOUT = 300

# ── Prompt B'：coverage + 特徵（生圖實際走這條，_detect_coverage_and_extract_visual）──
# v2：針對「無上色線稿」加兩條硬規則，防止把粉紅背景滲進服裝色、防止臆測不存在的顏色。
PROMPT_COVERAGE = (
    "【線稿警告】這很可能是未上色的鉛筆稿／線稿，且常帶有單色（如粉紅色）背景。\n"
    "規則一：完全忽略背景顏色——粉紅色或任何單色背景，絕不可當成髮色或服裝顏色。\n"
    "規則二：若畫面只有線條、沒有實際填色，請直接省略顏色、不要寫出任何顏色詞，也不要寫「線稿未上色」這類字樣，"
    "只描述髮型長度與形狀、服裝款式與材質、明顯特徵。嚴禁臆測顏色。只觀察「角色線條內」的特徵。\n\n"
    "請回答以下兩個問題：\n\n"
    "A. 身體遮蔽程度（只回答一個英文詞）：\n"
    "- 'full'    腳踝和腳都清晰可見（完整全身）\n"
    "- 'partial' 膝蓋或腳踝以下被切掉，或腳超出畫面（大腿可見但無腳也算partial）\n"
    "- 'bust'    只有腰部以上可見\n\n"
    "B. 視覺特徵（逗號分隔的中文短語，控制在70字以內）：\n"
    "① 髮型與髮色 ② 眼睛 ③ 膚色 ④ 體型輪廓 ⑤ 服裝款式與顏色 ⑥ 明顯特殊特徵（配件、拉鍊、頸環等）\n\n"
    "回答格式（嚴格遵守）：\n"
    "COVERAGE: [一個英文詞]\n"
    "FEATURES: [逗號分隔的中文短語]"
)

# ── Prompt B：純特徵抽取（_visual_extract_prompt(1)）─────────────────────────
PROMPT_FEATURES = (
    "【重要警告】這是一張草稿或帶有單色背景的參考圖。請完全忽略背景顏色（例如：如果背景是純粉色，"
    "請勿將其判定為衣服或髮色）。背景不屬於角色特徵。請只觀察「角色線條內」的特徵。\n"
    "請仔細觀察這張角色參考圖，描述以下視覺特徵：\n"
    "① 髮色與髮型（顏色、長度、形狀，請根據角色本身的髮色判斷）"
    "② 眼睛顏色③ 膚色④ 體型輪廓（高挑/嬌小、胖瘦）"
    "⑤ 服裝主要顏色與風格（僅描述角色穿著的部分，無視背景）"
    "⑥ 明顯特殊特徵（獸耳、印記、武器等）\n"
    "格式：逗號分隔的中文短語，不加標號，不寫句子，控制在70字以內。"
)

# ── Prompt A：肖像描述（character/describe_portrait.txt）─────────────────────
PROMPT_PORTRAIT = (
    "[TASK]\n"
    "Analyze the provided illustration for the character \"{name}\" and create a structured visual profile.\n\n"
    "[OUTPUT FORMAT]\n"
    "Provide a detailed description in Traditional Chinese (繁體中文) using the following sections:\n\n"
    "1. **外貌特徵 (Physical Traits)**: 髮色、髮型、瞳色、膚色、五官特色。\n"
    "2. **身形體態 (Body & Posture)**: 體型描述、身高感、當前姿勢、給人的動態感。\n"
    "3. **服裝細節 (Outfit & Accessories)**: 衣著層次、材質感、配色方案、特殊配件或武器。\n"
    "4. **視覺氣質 (Atmosphere)**: 整體氣氛、光影表現、性格映射到視覺上的感覺。\n\n"
    "[CONSTRAINTS]\n"
    "- Be precise: Instead of \"long hair\", use \"silver waist-length straight hair\" if applicable.\n"
    "- Semantic Focus: Focus on details that define the character's identity.\n"
    "- Language: Use professional Traditional Chinese creative writing vocabulary.\n\n"
    "[RESULT]\n"
)

PROMPTS = {
    "coverage": PROMPT_COVERAGE,   # 預設：等同生圖前自動抽取
    "features": PROMPT_FEATURES,
    "portrait": PROMPT_PORTRAIT,
}


def resize_for_vision(image_bytes: bytes, max_px: int = VISION_MAX_PX) -> bytes:
    """同 ollama_client._resize_for_vision：最長邊縮到 max_px，失敗回原圖。"""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        fmt = img.format or "PNG"
        w, h = img.size
        if max(w, h) <= max_px:
            return image_bytes
        scale = max_px / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        return buf.getvalue()
    except Exception:
        return image_bytes


def parse_params(detail: dict) -> float | None:
    """details.parameter_size（如 '9.0B' / '14B' / '134M'）→ 十億(B)為單位的 float。"""
    s = (detail or {}).get("parameter_size")
    if not s:
        return None
    m = re.search(r"([\d.]+)\s*([BM])", str(s), re.IGNORECASE)
    if not m:
        return None
    val = float(m.group(1))
    return val / 1000 if m.group(2).upper() == "M" else val


def list_models(host: str) -> list[dict]:
    """回傳 [{'name':..., 'params': float|None}]，params 為十億參數量。"""
    r = requests.get(f"{host}/api/tags", timeout=10)
    r.raise_for_status()
    return [
        {"name": m["name"], "params": parse_params(m.get("details"))}
        for m in r.json().get("models", [])
    ]


def is_vision_model(host: str, name: str) -> bool | None:
    """用 /api/show 的 capabilities 判斷是否含 vision；舊版無此欄位回 None（未知）。"""
    try:
        r = requests.post(f"{host}/api/show", json={"model": name}, timeout=15)
        r.raise_for_status()
        caps = r.json().get("capabilities")
        if caps is None:
            return None
        return "vision" in caps
    except Exception:
        return None


def parse_coverage_features(raw: str) -> tuple[str, str]:
    """同 vision_extract：去 <think>，抽 COVERAGE / FEATURES。"""
    cleaned = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL | re.IGNORECASE).strip()
    coverage, visual = "", ""
    for line in cleaned.split("\n"):
        line = line.strip()
        if line.upper().startswith("COVERAGE:"):
            p = line.split(":", 1)
            w = p[1].strip().lower().split()[0] if len(p) > 1 and p[1].strip() else ""
            if w in ("full", "partial", "bust"):
                coverage = w
        elif line.upper().startswith("FEATURES:"):
            p = line.split(":", 1)
            visual = p[1].strip() if len(p) > 1 else ""
    return coverage, visual


def diagnose(resp_field: str, think_field: str, done_reason: str,
             eval_count: int, raw_len: int) -> str:
    """根據 Ollama 回傳的欄位推斷『回空/異常』的主因，給可讀標籤。"""
    if raw_len > 0:
        return "ok" if done_reason != "length" else "ok(但被num_predict截斷)"
    # response 空
    if think_field:
        return "回空:token燒在thinking欄(此模型不吃think:false)"
    if done_reason == "length":
        return "回空:num_predict耗盡(調大--num-predict)"
    if eval_count and eval_count > 0:
        return "回空:有生成但response欄為空(模型輸出格式異常)"
    return "回空:模型完全沒輸出(eval_count=0，疑似載入/相容問題)"


def run_one(host: str, model: str, prompt: str, image_b64: str, num_predict: int) -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
        "think": False,
        "options": {"num_predict": num_predict, "temperature": 0.1},
    }
    t0 = time.time()
    try:
        r = requests.post(f"{host}/api/generate", json=payload, timeout=TIMEOUT)
        r.raise_for_status()
        j = r.json()
        raw = (j.get("response") or "").strip()
        think = (j.get("thinking") or "").strip()
        done_reason = j.get("done_reason") or ""
        eval_count = int(j.get("eval_count") or 0)
        elapsed = time.time() - t0
        cov, feat = parse_coverage_features(raw)
        return {"model": model, "ok": True, "elapsed": elapsed, "raw": raw,
                "thinking": think, "done_reason": done_reason, "eval_count": eval_count,
                "coverage": cov, "features": feat, "raw_len": len(raw),
                "diag": diagnose(raw, think, done_reason, eval_count, len(raw))}
    except Exception as e:
        return {"model": model, "ok": False, "elapsed": time.time() - t0,
                "raw": f"[error] {e}", "thinking": "", "done_reason": "", "eval_count": 0,
                "coverage": "", "features": "", "raw_len": 0, "diag": f"ERR:{e}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", help="測試圖路徑，例如 F:/TESTPIC/t1.png")
    ap.add_argument("--host", default="http://localhost:11434", help="Ollama base URL")
    ap.add_argument("--prompt", default="coverage", choices=list(PROMPTS), help="prompt 類型")
    ap.add_argument("--name", default="測試角色", help="portrait 模式用的角色名")
    ap.add_argument("--models", default="", help="逗號分隔指定模型；不給則自動偵測視覺模型")
    ap.add_argument("--all-models", action="store_true", help="不過濾，所有模型硬跑")
    ap.add_argument("--max-params", type=float, default=14.0,
                    help="只測參數量 < 此值(十億B)的模型；預設 14 擋掉 14B 以上。設 0 不限制")
    ap.add_argument("--num-predict", type=int, default=DEFAULT_NUM_PREDICT,
                    help="生成 token 上限（預設 512）。診斷 thinking 模型回空時調大，如 1024/2048")
    ap.add_argument("--out", default="vision_test_result.md", help="完整結果輸出檔")
    args = ap.parse_args()

    img_path = Path(args.image)
    if not img_path.exists():
        print(f"找不到圖片：{img_path}", file=sys.stderr)
        return 1
    image_b64 = base64.b64encode(resize_for_vision(img_path.read_bytes())).decode()

    prompt = PROMPTS[args.prompt]
    if args.prompt == "portrait":
        prompt = prompt.format(name=args.name)

    # 決定要測哪些模型
    if args.models:
        models = [m.strip() for m in args.models.split(",") if m.strip()]
    else:
        entries = list_models(args.host)  # [{'name','params'}]

        # 參數量過濾（--max-params，0=不限制）；params 未知者保留並提示
        if args.max_params and args.max_params > 0:
            kept, too_big, no_size = [], [], []
            for e in entries:
                if e["params"] is None:
                    no_size.append(e)
                    kept.append(e)
                elif e["params"] < args.max_params:
                    kept.append(e)
                else:
                    too_big.append(e)
            if too_big:
                print(f"（已過濾 {len(too_big)} 個 >={args.max_params}B 的模型："
                      + ", ".join(f"{e['name']}={e['params']}B" for e in too_big) + "）")
            if no_size:
                print(f"（{len(no_size)} 個模型無參數量資訊，保留待測："
                      + ", ".join(e["name"] for e in no_size) + "）")
            entries = kept

        all_names = [e["name"] for e in entries]
        if args.all_models:
            models = all_names
        else:
            models = []
            unknown = []
            for name in all_names:
                v = is_vision_model(args.host, name)
                if v is True:
                    models.append(name)
                elif v is None:
                    unknown.append(name)
            if not models and unknown:
                print("⚠ 你的 Ollama 版本無 capabilities 欄位，無法自動判斷視覺模型。")
                print("  請用 --models 指定，或 --all-models 全部硬跑。")
                print("  可用模型：", ", ".join(all_names))
                return 1
            if unknown:
                print(f"（略過 {len(unknown)} 個無法判定的模型；如需強跑用 --all-models）")

    if not models:
        print("沒有可測試的模型。", file=sys.stderr)
        return 1

    print(f"圖片：{img_path.name}  prompt：{args.prompt}  num_predict：{args.num_predict}  模型數：{len(models)}\n")

    results = []
    for i, m in enumerate(models, 1):
        print(f"[{i}/{len(models)}] {m} …", end=" ", flush=True)
        res = run_one(args.host, m, prompt, image_b64, args.num_predict)
        results.append(res)
        print(f"{res['diag']}  {res['elapsed']:.1f}s  len={res['raw_len']}")

    # ── 終端對照表 ──
    print("\n" + "=" * 78)
    print(f"{'模型':<38} {'秒':>6} {'len':>5} {'cov':>8}  診斷")
    print("-" * 78)
    for r in results:
        print(f"{r['model']:<38} {r['elapsed']:>6.1f} {r['raw_len']:>5} {r['coverage'] or '-':>8}  {r['diag']}")

    # ── 寫完整 markdown ──
    out = Path(args.out)
    lines = [f"# 視覺模型測試 — {img_path.name}", "",
             f"- prompt 類型：`{args.prompt}`",
             f"- host：{args.host}",
             f"- num_predict：{args.num_predict}", ""]
    lines.append("| 模型 | 秒 | len | coverage | done_reason | eval | 診斷 | features 摘要 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in results:
        feat = (r["features"] or "")[:40].replace("|", "/")
        lines.append(f"| {r['model']} | {r['elapsed']:.1f} | {r['raw_len']} | {r['coverage'] or '-'} "
                     f"| {r['done_reason'] or '-'} | {r['eval_count']} | {r['diag']} | {feat} |")
    lines.append("\n---\n## 各模型完整回應\n")
    for r in results:
        lines.append(f"### {r['model']}  （{r['elapsed']:.1f}s，{r['diag']}）\n")
        lines.append("**response：**\n")
        lines.append("```\n" + (r["raw"] or "") + "\n```\n")
        if r["thinking"]:
            lines.append("**thinking（模型把推理放這欄，response 才會空）：**\n")
            lines.append("```\n" + r["thinking"][:1500] + "\n```\n")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n完整結果已寫入：{out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
