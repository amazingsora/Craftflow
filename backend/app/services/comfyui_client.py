"""
Thin wrapper around the ComfyUI REST API for use by FastAPI endpoints.
Mirrors tools/Craftflow/diffusion/comfyui_provider.py but accepts raw bytes
for image uploads (suitable for UploadFile data).
"""
import time
import uuid
from io import BytesIO

import requests

from app.core.config import COMFYUI_BASE

def is_available() -> bool:
    try:
        r = requests.get(f"{COMFYUI_BASE}/system_stats", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def upload_image_bytes(image_bytes: bytes, filename: str) -> str:
    """Upload raw image bytes to ComfyUI's input folder; return the stored filename."""
    r = requests.post(
        f"{COMFYUI_BASE}/upload/image",
        files={"image": (filename, BytesIO(image_bytes), "image/png")},
        data={"overwrite": "true"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["name"]


def submit_workflow(workflow: dict) -> str:
    """Submit a workflow dict and return its prompt_id."""
    # Build a synthetic UI-format workflow so that custom nodes which call
    # extra_pnginfo["workflow"]["nodes"] (e.g. KJNodes GetWidgetValue,
    # comfyui-easy-use EasyLog, Impact Pack util nodes) don't crash.
    # UI format: nodes is a list; each node has integer "id" and
    # "inputs" as a list of slot dicts {name, type?, link?} — NOT a dict.
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
        "client_id": str(uuid.uuid4()),
        "extra_data": {"extra_pnginfo": {"workflow": {"nodes": synthetic_nodes}}},
    }
    r = requests.post(f"{COMFYUI_BASE}/prompt", json=payload, timeout=30)
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
    return _poll_history(prompt_id, timeout, _extract_images)


def download_image(filename: str) -> bytes:
    r = requests.get(
        f"{COMFYUI_BASE}/view",
        params={"filename": filename, "type": "output"},
        timeout=30,
    )
    r.raise_for_status()
    return r.content


# ── WD14 Tagger support ───────────────────────────────────────────────────────

_WD14_CANDIDATES = [
    "WD14Tagger|pysssss",   # pythongosssss/ComfyUI-Custom-Scripts
    "WDTagger",             # various forks
    "WD14Tagger",           # generic
]


def detect_wd14_node() -> str | None:
    """Return the class_type of an available WD14 tagger node, or None."""
    try:
        r = requests.get(f"{COMFYUI_BASE}/object_info", timeout=8)
        if not r.ok:
            return None
        available = set(r.json().keys())
        for candidate in _WD14_CANDIDATES:
            if candidate in available:
                return candidate
    except Exception:
        pass
    return None


def wait_for_text_result(prompt_id: str, timeout: int = 90) -> list[str]:
    """Poll until job completes; return all text/tags outputs from any node."""
    return _poll_history(prompt_id, timeout, _extract_texts)


def _poll_history(prompt_id: str, timeout: int, extract) -> list[str]:
    deadline = time.time() + timeout
    interval = 0.5
    while time.time() < deadline:
        r = requests.get(f"{COMFYUI_BASE}/history/{prompt_id}", timeout=10)
        data = r.json()
        if prompt_id in data:
            outputs = data[prompt_id].get("outputs", {})
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
