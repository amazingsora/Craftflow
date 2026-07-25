#!/usr/bin/env python3
"""DWPose 腳 keypoint 召回率探針（T1B-3 前置驗證，2026-07-15）。

用途：在**你本機的 ComfyUI**上，量測 DWPose 對「淡鉛筆 / 動漫線稿」能不能偵測到
腳踝（ankle）keypoint。這是 T1B（DWPose 根治 coverage 誤判）能否採用的 go/no-go 依據——
規劃文件 T1B-3 要求淡線稿召回率 ≥ 80% 才採用，否則改走 T1C。

沙箱無 GPU/ComfyUI/onnxruntime，此腳本**必須在本機跑**。

用法：
    cd backend
    # 對指定草圖
    python tools/dwpose_recall_probe.py path/to/sketch1.png path/to/sketch2.png
    # 或不給參數 → 掃 uploads/portraits 最近 N 張
    python tools/dwpose_recall_probe.py

環境變數：
    COMFYUI_BASE        預設 http://localhost:8188
    DWPOSE_RESOLUTION   預設 512（pose 估計解析度）
    DWPOSE_BBOX         預設 None（跳過 bbox detector，直跑 pose；半身稿 detector 常抓不到人）
    DWPOSE_ANKLE_CONF   預設 0.30（ankle keypoint 信心 ≥ 此值才算「偵測到腳」）
    DWPOSE_POSE_MODEL   預設 dw-ll_ucoco_384_bs5.torchscript.pt

輸出：每張圖印出偵測到的人數、hip/knee/ankle 信心，與「有無偵測到腳」判定；最後印整體召回率。
第一張會 dump 完整 outputs JSON，方便核對 ComfyUI 回傳的實際 key 路徑。
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

import requests

COMFYUI_BASE = os.getenv("COMFYUI_BASE", "http://localhost:8188").rstrip("/")
RESOLUTION = int(os.getenv("DWPOSE_RESOLUTION", "512"))
BBOX = os.getenv("DWPOSE_BBOX", "None")
ANKLE_CONF = float(os.getenv("DWPOSE_ANKLE_CONF", "0.30"))
POSE_MODEL = os.getenv("DWPOSE_POSE_MODEL", "dw-ll_ucoco_384_bs5.torchscript.pt")

# OpenPose-18 (COCO) keypoint 索引
KP = {"nose": 0, "neck": 1, "r_hip": 8, "r_knee": 9, "r_ankle": 10,
      "l_hip": 11, "l_knee": 12, "l_ankle": 13}


def _upload(img_path: Path) -> str:
    with open(img_path, "rb") as f:
        r = requests.post(
            f"{COMFYUI_BASE}/upload/image",
            files={"image": (img_path.name, f, "image/png")},
            data={"overwrite": "true"},
            timeout=30,
        )
    r.raise_for_status()
    j = r.json()
    name = j.get("name") or img_path.name
    sub = j.get("subfolder") or ""
    return f"{sub}/{name}" if sub else name


def _workflow(image_name: str) -> dict:
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "2": {"class_type": "DWPreprocessor", "inputs": {
            "image": ["1", 0],
            "detect_hand": "disable",
            "detect_body": "enable",
            "detect_face": "disable",
            "resolution": RESOLUTION,
            "bbox_detector": BBOX,
            "pose_estimator": POSE_MODEL,
            "scale_stick_for_xinsr_cn": "disable",
        }},
        "3": {"class_type": "PreviewImage", "inputs": {"images": ["2", 0]}},
    }


def _submit(wf: dict) -> str:
    r = requests.post(f"{COMFYUI_BASE}/prompt",
                      json={"prompt": wf, "client_id": str(uuid.uuid4())}, timeout=30)
    r.raise_for_status()
    return r.json()["prompt_id"]


def _poll(prompt_id: str, timeout: int = 180) -> dict:
    deadline = time.time() + timeout
    interval = 0.5
    while time.time() < deadline:
        try:
            data = requests.get(f"{COMFYUI_BASE}/history/{prompt_id}", timeout=60).json()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            time.sleep(interval)
            interval = min(interval * 1.5, 3)
            continue
        if prompt_id in data:
            entry = data[prompt_id]
            if entry.get("status", {}).get("status_str") == "error":
                raise ValueError(f"ComfyUI error: {entry['status'].get('messages')}")
            return entry.get("outputs", {})
        time.sleep(interval)
        interval = min(interval * 1.5, 3)
    raise TimeoutError(f"job {prompt_id} timed out")


def _extract_keypoint_dicts(outputs: dict) -> list:
    """從 history outputs 撈 openpose_json（DWPreprocessor 的 ui 輸出）。"""
    for node_out in outputs.values():
        raw = node_out.get("openpose_json")
        if raw:
            s = raw[0] if isinstance(raw, list) else raw
            try:
                return json.loads(s)
            except Exception:
                pass
    return []


def _analyse(pose_dicts: list) -> dict:
    """回傳 {people, best_ankle_conf, hip/knee/ankle 明細, feet_detected}。"""
    best = {"people": 0, "feet_detected": False, "detail": []}
    for d in pose_dicts:
        people = d.get("people") or d.get("animals") or []
        best["people"] = max(best["people"], len(people))
        for p in people:
            kps = p.get("pose_keypoints_2d") or p.get("keypoints") or []
            def conf(idx):
                base = idx * 3
                return kps[base + 2] if base + 2 < len(kps) else 0.0
            row = {k: round(conf(i), 2) for k, i in KP.items()}
            row["feet"] = max(conf(KP["r_ankle"]), conf(KP["l_ankle"])) >= ANKLE_CONF
            best["detail"].append(row)
            if row["feet"]:
                best["feet_detected"] = True
    return best


def _pick_default_images() -> list[Path]:
    pdir = Path("uploads/portraits")
    if not pdir.exists():
        return []
    files = sorted(pdir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:8]


def main(argv: list[str]) -> int:
    imgs = [Path(a) for a in argv] or _pick_default_images()
    if not imgs:
        print("找不到圖檔。請給草圖路徑，或在 backend/ 下有 uploads/portraits/。")
        return 2
    try:
        requests.get(f"{COMFYUI_BASE}/system_stats", timeout=5).raise_for_status()
    except Exception as e:
        print(f"連不到 ComfyUI（{COMFYUI_BASE}）：{e}\n請先啟動 ComfyUI。")
        return 2

    print(f"ComfyUI={COMFYUI_BASE}  resolution={RESOLUTION}  bbox={BBOX}  ankle_conf>={ANKLE_CONF}")
    print(f"pose_model={POSE_MODEL}\n")
    hits = 0
    total = 0
    for i, img in enumerate(imgs):
        if not img.exists():
            print(f"[skip] {img} 不存在")
            continue
        total += 1
        try:
            name = _upload(img)
            pid = _submit(_workflow(name))
            outputs = _poll(pid)
            if i == 0:
                print("── 第一張完整 outputs（核對 key 路徑）──")
                print(json.dumps(outputs, ensure_ascii=False)[:1500])
                print("──────────────────────────────────────\n")
            res = _analyse(_extract_keypoint_dicts(outputs))
            mark = "✅有腳" if res["feet_detected"] else "❌無腳"
            hits += 1 if res["feet_detected"] else 0
            print(f"[{mark}] {img.name}  people={res['people']}")
            for row in res["detail"][:2]:
                print(f"        hip(R/L)={row['r_hip']}/{row['l_hip']} "
                      f"knee={row['r_knee']}/{row['l_knee']} "
                      f"ankle={row['r_ankle']}/{row['l_ankle']}")
        except Exception as e:
            print(f"[err ] {img.name}: {type(e).__name__}: {e}")
    if total:
        rate = hits / total
        print(f"\n召回率：{hits}/{total} = {rate:.0%}  "
              f"→ {'✅ ≥80%，T1B 可採用' if rate >= 0.8 else '❌ <80%，依規劃改走 T1C（VL 二段式問答）'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
