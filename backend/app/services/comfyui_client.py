# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
"""Thin wrapper around the ComfyUI REST API for use by FastAPI endpoints [FD-113]"""
import logging
import time
import uuid
from io import BytesIO

import requests

from app.core import config as _cfg
from app.core.config import COMFYUI_BASE, COMFYUI_SLOW_JOB_WARN_SEC, VRAM_STUCK_RATIO
from app.services.http_local import SESSION

logger = logging.getLogger(__name__)

def is_available() -> bool:
    try:
        r = SESSION.get(f"{COMFYUI_BASE}/system_stats", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def upload_image_bytes(image_bytes: bytes, filename: str) -> str:
    """Upload raw image bytes to ComfyUI's input folder; return the stored filename."""
    r = SESSION.post(
        f"{COMFYUI_BASE}/upload/image",
        files={"image": (filename, BytesIO(image_bytes), "image/png")},
        data={"overwrite": "true"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["name"]


def submit_workflow(workflow: dict, client_id: str | None = None) -> str:
    """Submit a workflow dict and return its prompt_id."""
    # [CN-099] 送出前合成 UI-format workflow，避免讀 extra_pnginfo["workflow"]["nodes"] 的 custom node crash
    synthetic_nodes = []
    for nid, node in workflow.items():
        if not isinstance(node, dict) or "class_type" not in node:
            continue
        api_inputs = node.get("inputs", {})
        ui_inputs = [{"name": k} for k in api_inputs]
        synthetic_nodes.append({
            "id": int(nid) if str(nid).isdigit() else nid,
            "type": node["class_type"],
            "class_type": node["class_type"],
            "inputs": ui_inputs,
            "_meta": node.get("_meta", {}),
        })
    payload = {
        "prompt": workflow,
        "client_id": client_id or str(uuid.uuid4()),
        "extra_data": {"extra_pnginfo": {"workflow": {"nodes": synthetic_nodes}}},
    }
    r = SESSION.post(f"{COMFYUI_BASE}/prompt", json=payload, timeout=30)
    if not r.ok:
        try:
            data = r.json()
            node_errors = data.get("node_errors", {})
            msgs = []
            if node_errors:
                for node_err in node_errors.values():
                    class_type = node_err.get("class_type", "?")
                    for e in node_err.get("errors", []):
                        msgs.append(f"[{class_type}] {e.get('message', '')}")
                raise ValueError("; ".join(msgs) if msgs else data.get("error", {}).get("message", r.text))
            raise ValueError(data.get("error", {}).get("message", r.text))
        except ValueError:
            raise
        except Exception:
            r.raise_for_status()
    return r.json()["prompt_id"]


def wait_for_result(prompt_id: str, timeout: int = 300) -> list[str]:
    """Poll until the job completes; return output image filenames."""
    return _poll_history(prompt_id, timeout, _extract_images,
                         slow_warn_sec=COMFYUI_SLOW_JOB_WARN_SEC)


def download_image(filename: str) -> bytes:
    r = SESSION.get(
        f"{COMFYUI_BASE}/view",
        params={"filename": filename, "type": "output"},
        timeout=30,
    )
    r.raise_for_status()
    return strip_png_text_chunks(r.content) if _cfg.PNG_STRIP_METADATA else r.content


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_TEXT_CHUNKS = {b"tEXt", b"iTXt", b"zTXt"}


def strip_png_text_chunks(data: bytes) -> bytes:
    """移除 PNG 文字 chunk（ComfyUI 在此內嵌 prompt／workflow），像素不動；非 PNG 或格式異常原樣回傳。"""
    if not data.startswith(_PNG_SIGNATURE):
        return data
    out, pos = [_PNG_SIGNATURE], len(_PNG_SIGNATURE)
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        end = pos + 12 + length
        if end > len(data):
            return data
        if data[pos + 4:pos + 8] not in _PNG_TEXT_CHUNKS:
            out.append(data[pos:end])
        pos = end
    return b"".join(out) if pos == len(data) else data


# ── WD14 Tagger support ───────────────────────────────────────────────────────

_WD14_CANDIDATES = [
    "WD14Tagger|pysssss",   # pythongosssss/ComfyUI-Custom-Scripts
    "WDTagger",             # various forks
    "WD14Tagger",           # generic
]


def detect_wd14_node() -> str | None:
    """Return the class_type of an available WD14 tagger node, or None."""
    try:
        r = SESSION.get(f"{COMFYUI_BASE}/object_info", timeout=8)
        if not r.ok:
            return None
        available = set(r.json().keys())
        for candidate in _WD14_CANDIDATES:
            if candidate in available:
                return candidate
    except Exception:
        pass
    return None


# [CN-100] LLLite class_type 用候選清單探測（kohya 曾改註冊名），命中就記住實際名
LLLITE_NODE_CLASS_CANDIDATES = ("AnimaLLLiteApply_sdscripts", "AnimaLLLiteApply")
# [CN-101] ⚠️ 首選權重訓練基底是 Anima-Base v1.0，與本機在用的 turbo 隔兩代，不得用 strength 假裝補償
LLLITE_PREFERRED_WEIGHTS = ("anima-lllite-any-test-like-v2.safetensors",)

# [CN-102] 只永久快取成功結果；失敗只快取一小段並指數退避（舊版無條件快取會鎖死整個後端生命週期）
_lllite_cache: dict | None = None          # 只放 available=True 的結果，永久有效
_lllite_fail: dict | None = None           # {"result": dict, "until": float, "streak": int}
_LLLITE_FAIL_TTL_BASE = 30.0               # 第一次失敗後 30 秒才重試
_LLLITE_FAIL_TTL_MAX = 300.0               # 退避上限 5 分鐘（ComfyUI 載模型最久也夠了）


def detect_lllite() -> dict:
    """LLLite 可用性：{"available", "weights", "reason", "node_class"}。
    /object_info 同時回答節點是否安裝與可用權重；失敗回 available=False。
    成功永久快取，失敗只快取到退避期滿。"""
    global _lllite_cache, _lllite_fail
    if _lllite_cache is not None:
        return _lllite_cache
    if _lllite_fail is not None and time.monotonic() < _lllite_fail["until"]:
        return _lllite_fail["result"]
    result = {"available": False, "weights": [], "reason": "unknown", "node_class": None}
    tried = []
    try:
        for candidate in LLLITE_NODE_CLASS_CANDIDATES:
            r = SESSION.get(f"{COMFYUI_BASE}/object_info/{candidate}", timeout=8)
            if not r.ok:
                tried.append(f"{candidate}: HTTP {r.status_code}")
                continue
            info = (r.json() or {}).get(candidate) or {}
            if not info:
                tried.append(f"{candidate}: 節點未安裝")
                continue
            opts = (info.get("input", {}).get("required", {}).get("lllite_name") or [[]])[0]
            weights = [w for w in opts if isinstance(w, str)]
            result["node_class"] = candidate
            result["weights"] = weights
            if weights:
                result["available"] = True
                result["reason"] = "ok"
            else:
                result["reason"] = f"節點（{candidate}）已安裝，但 controlnet 目錄無任何權重檔"
            break
        else:
            result["reason"] = "候選 class 名皆未命中（" + "; ".join(tried) + "）"
    except Exception as e:
        result["reason"] = f"探測失敗：{e}"
    if result["available"]:
        _lllite_cache = result
        _lllite_fail = None
        logger.info("[lllite] 偵測結果：available=True node_class=%s weights=%d reason=%s",
                    result["node_class"], len(result["weights"]), result["reason"])
    else:
        # 失敗只快取到退避期滿，且退避時間隨連續失敗次數指數成長（上限 _LLLITE_FAIL_TTL_MAX）。
        # streak 從上一次失敗延續 —— 否則「每次都失敗但每次都算第一次」等於沒有退避。
        streak = (_lllite_fail or {}).get("streak", 0) + 1
        ttl = min(_LLLITE_FAIL_TTL_BASE * (2 ** (streak - 1)), _LLLITE_FAIL_TTL_MAX)
        _lllite_fail = {"result": result, "until": time.monotonic() + ttl, "streak": streak}
        # WARNING 而非 INFO：靜默降級是本專案反覆踩的坑，這一行是唯一的事前訊號。
        logger.warning("[lllite] 偵測失敗（第 %d 次，%.0fs 後重試）：node_class=%s weights=%d reason=%s",
                       streak, ttl, result["node_class"], len(result["weights"]), result["reason"])
    return result


def pick_lllite_weight(weights: list[str]) -> str | None:
    """從可用權重挑一支。首選清單命中優先，否則取第一個檔名含 'lllite' 的 [FD-114]"""
    for pref in LLLITE_PREFERRED_WEIGHTS:
        if pref in weights:
            return pref
    for w in weights:
        if "lllite" in w.lower():
            return w
    return None


def reset_lllite_cache() -> None:
    """重新探測前清除成功快取與失敗退避狀態（兩者都要清）。"""
    global _lllite_cache, _lllite_fail
    _lllite_cache = None
    _lllite_fail = None


def wait_for_text_result(prompt_id: str, timeout: int = 90) -> list[str]:
    """Poll until job completes; return all text/tags outputs from any node."""
    return _poll_history(prompt_id, timeout, _extract_texts)


def _vram_snapshot() -> tuple[str, bool]:
    """讀 /system_stats 的 free/reserved，回 (描述字串, 是否已塞滿需重啟 ComfyUI)。"""
    try:
        dev = (SESSION.get(f"{COMFYUI_BASE}/system_stats", timeout=5)
               .json().get("devices") or [{}])[0]
        gib = 1024 ** 3
        free = int(dev.get("vram_free", 0))
        reserved = int(dev.get("torch_vram_total", 0))
        total = int(dev.get("vram_total", 0))
        stuck = bool(total) and reserved >= VRAM_STUCK_RATIO * total
        return (f" free={free / gib:.1f}G reserved={reserved / gib:.1f}G"
                f" total={total / gib:.1f}G"), stuck
    except Exception:
        return "", False


def _warn_if_slow(prompt_id: str, elapsed: float, slow_warn_sec: int) -> None:
    """任務完成時記錄耗時與顯存（純診斷）：顯存溢出到共享記憶體時 ComfyUI 不會報錯。"""
    if slow_warn_sec <= 0 or elapsed < slow_warn_sec:
        return
    snapshot, stuck = _vram_snapshot()
    logger.error(
        "[comfyui] job %s 耗時 %.0fs（警戒值 %ds）—— 疑似顯存溢出到共享系統記憶體"
        "（sysmem fallback），採樣走 PCIe。當下顯存:%s%s",
        prompt_id, elapsed, slow_warn_sec, snapshot or " (讀取失敗)",
        "  ⚠️ reserved 已逼近卡容量：此狀態不會自行恢復，**請重啟 ComfyUI**；"
        "若重啟後 reserved 很快又回到高檔，代表啟動旗標仍是 --highvram。" if stuck else "",
    )


def _poll_history(prompt_id: str, timeout: int, extract, slow_warn_sec: int = 0) -> list[str]:
    started = time.time()
    deadline = started + timeout
    interval = 0.5
    while time.time() < deadline:
        try:
            r = SESSION.get(f"{COMFYUI_BASE}/history/{prompt_id}", timeout=60)
            data = r.json()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            # ComfyUI 載入大模型（如 Flux GGUF 冷啟動）期間 HTTP 會暫時無回應，單次 poll 逾時
            # 屬暫時性、非任務失敗 → 記錄後繼續輪詢，撐到外層 deadline 才放棄。
            logger.warning("[comfyui] poll %s 暫時逾時（%s），繼續等待", prompt_id, type(e).__name__)
            time.sleep(interval)
            interval = min(interval * 1.5, 3)
            continue
        if prompt_id in data:
            entry = data[prompt_id]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                msgs = [str(m) for m in status.get("messages", [])]
                logger.error("[comfyui] job %s failed: %s", prompt_id, "; ".join(msgs))
                raise ValueError(f"ComfyUI 執行錯誤: {'; '.join(msgs)}")
            outputs = entry.get("outputs", {})
            _warn_if_slow(prompt_id, time.time() - started, slow_warn_sec)
            return extract(outputs)
        time.sleep(interval)
        interval = min(interval * 1.5, 3)
    raise TimeoutError(f"ComfyUI job {prompt_id} timed out after {timeout}s")


def _extract_images(outputs: dict) -> list[str]:
    images: list[str] = []
    for node_out in outputs.values():
        for img in node_out.get("images", []):
            images.append(img["filename"])
    return images


def _extract_texts(outputs: dict) -> list[str]:
    texts: list[str] = []
    for node_out in outputs.values():
        for key in ("text", "tags", "result", "string"):
            raw = node_out.get(key)
            if raw is None:
                continue
            if isinstance(raw, list):
                texts.extend(str(t) for t in raw if t)
            elif isinstance(raw, str) and raw:
                texts.append(raw)
    return texts
