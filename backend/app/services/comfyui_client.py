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
    payload = {"prompt": workflow, "client_id": str(uuid.uuid4())}
    r = requests.post(f"{COMFYUI_BASE}/prompt", json=payload, timeout=30)
    if not r.ok:
        # Extract ComfyUI's actual validation error instead of the generic HTTPError
        try:
            data = r.json()
            node_errors = data.get("node_errors", {})
            if node_errors:
                msgs = []
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
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(f"{COMFYUI_BASE}/history/{prompt_id}", timeout=10)
        data = r.json()
        if prompt_id in data:
            outputs = data[prompt_id].get("outputs", {})
            images = []
            for node_out in outputs.values():
                for img in node_out.get("images", []):
                    images.append(img["filename"])
            return images
        time.sleep(2)
    raise TimeoutError(f"ComfyUI job {prompt_id} timed out after {timeout}s")


def download_image(filename: str) -> bytes:
    r = requests.get(
        f"{COMFYUI_BASE}/view",
        params={"filename": filename, "type": "output"},
        timeout=30,
    )
    r.raise_for_status()
    return r.content
