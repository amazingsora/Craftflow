"""
test_structured_output_support.py — P1 Step 1（2026-07-02 規劃「Prompt 改生成時約束」）

用途：在真正動 vision_extract.py / compiler.py 之前，先實測目前設定的
文字模型與視覺模型是否確實遵守 Ollama `format: <json schema>` 參數
（0.5+ 支援，但「支援」不代表每個模型都會乖乖照 schema 輸出 —— 部分未特別
微調過的模型仍可能亂回、把 tag 塞進錯的欄位、或输出非 JSON 文字）。

這支腳本不動任何線上程式碼，只做驗證。跑法對齊 test_vision_models.py 慣例
（同 resize / think:false / timeout 設定），可在本機直接執行：

  python test_structured_output_support.py --text-model dolphin-llama3
  python test_structured_output_support.py --vision-model qwen2.5vl:7b --image F:/TESTPIC/t1.png
  python test_structured_output_support.py --host http://localhost:11434 --text-model xxx --vision-model yyy --image xxx.png

判讀：
  [PASS] 回應是合法 JSON 且欄位齊全 → 可以推進 P1 Step 2/3
  [PARTIAL] 是 JSON 但缺欄位/型別不對 → 需加 prompt 引導或該模型不適合，先別上
  [FAIL] 完全不是 JSON（模型不理會 format 參數）→ 保留舊的 regex/關鍵詞解析路徑，此模型不要切 P1
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

import requests

TIMEOUT = 120

# 對應規劃 P1 Step 2：vision 抽取 schema
VISION_SCHEMA = {
    "type": "object",
    "properties": {
        "coverage": {"type": "string", "enum": ["full", "partial", "bust"]},
        "hair": {"type": "string"},
        "eyes": {"type": "string"},
        "skin": {"type": "string"},
        "clothing": {"type": "string"},
        "features": {"type": "string"},
    },
    "required": ["coverage", "hair", "eyes", "skin", "clothing", "features"],
}

# 對應規劃 P1 Step 3：compile() schema
TAGS_SCHEMA = {
    "type": "object",
    "properties": {
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["tags"],
}

VISION_PROMPT = (
    "分析這張角色插畫。用指定的 JSON 格式回答，不要輸出 JSON 以外的任何文字。\n"
    "coverage: full(腳踝腳都可見)/partial(大腿可見無腳)/bust(只到腰部以上) 三選一。\n"
    "hair/eyes/skin/clothing/features 各用簡短中文短語描述。"
)

TEXT_PROMPT = (
    "把這段中文角色描述轉成 Danbooru 風格的 SD tags，"
    "用指定的 JSON 格式回答（tags 是字串陣列），不要輸出 JSON 以外的任何文字。\n"
    "輸入：左眼為紅色，右眼為綠色的異色瞳少女，短褐色頭髮"
)


def _post(host: str, payload: dict) -> dict:
    r = requests.post(f"{host}/api/generate", json=payload, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _judge(raw_response: str, required_keys: list[str]) -> str:
    try:
        parsed = json.loads(raw_response)
    except (json.JSONDecodeError, TypeError):
        return "FAIL", None
    if not isinstance(parsed, dict):
        return "FAIL", None
    missing = [k for k in required_keys if k not in parsed]
    if missing:
        return "PARTIAL", parsed
    return "PASS", parsed


def test_text_model(host: str, model: str) -> None:
    print(f"\n[TEXT] model={model}")
    payload = {
        "model": model,
        "prompt": TEXT_PROMPT,
        "stream": False,
        "think": False,
        "format": TAGS_SCHEMA,
        "options": {"temperature": 0.1, "num_predict": 250},
    }
    try:
        resp = _post(host, payload)
    except Exception as e:
        print(f"  [ERROR] 連線/請求失敗：{e}")
        return
    raw = resp.get("response", "")
    verdict, parsed = _judge(raw, ["tags"])
    print(f"  RAW: {raw[:300]!r}")
    print(f"  => [{verdict}]" + (f" parsed={parsed}" if parsed else ""))


def test_vision_model(host: str, model: str, image_path: str) -> None:
    print(f"\n[VISION] model={model} image={image_path}")
    try:
        image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
    except Exception as e:
        print(f"  [ERROR] 讀圖失敗：{e}")
        return
    payload = {
        "model": model,
        "prompt": VISION_PROMPT,
        "images": [image_b64],
        "stream": False,
        "think": False,
        "format": VISION_SCHEMA,
        "options": {"temperature": 0.1, "num_predict": 400},
    }
    try:
        resp = _post(host, payload)
    except Exception as e:
        print(f"  [ERROR] 連線/請求失敗：{e}")
        return
    raw = resp.get("response", "")
    verdict, parsed = _judge(raw, list(VISION_SCHEMA["required"]))
    print(f"  RAW: {raw[:400]!r}")
    print(f"  => [{verdict}]" + (f" parsed={parsed}" if parsed else ""))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--text-model", default=None, help="目前設定的文字模型（見 runtime_state.json / .env DEFAULT_TEXT_MODEL）")
    ap.add_argument("--vision-model", default=None, help="目前設定的視覺模型（見 runtime_state.json / .env DEFAULT_VISION_MODEL）")
    ap.add_argument("--image", default=None, help="測試視覺模型用的圖片路徑")
    args = ap.parse_args()

    if not args.text_model and not args.vision_model:
        print("至少指定 --text-model 或 --vision-model 其中之一。")
        sys.exit(1)

    if args.text_model:
        test_text_model(args.host, args.text_model)

    if args.vision_model:
        if not args.image:
            print("\n[VISION] 略過：指定 --vision-model 時需同時提供 --image")
        else:
            test_vision_model(args.host, args.vision_model, args.image)

    print(
        "\n判讀：PASS → 可推進 P1 Step 2/3；PARTIAL → 該模型需要更明確引導或暫緩；"
        "FAIL → 此模型不遵守 format 參數，P1 對它上線前必須保留舊 regex/關鍵詞解析路徑 fallback。"
    )


if __name__ == "__main__":
    main()
