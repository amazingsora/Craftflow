import json
import time
import uuid
from pathlib import Path

import requests


class ComfyUIProvider:
    """Thin wrapper around the ComfyUI REST API."""

    def __init__(self, base_url: str = "http://localhost:8188"):
        self.base_url = base_url.rstrip("/")
        self.client_id = str(uuid.uuid4())

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/system_stats", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def upload_image(self, image_path: str) -> str:
        """Upload an image to ComfyUI's input folder and return the filename."""
        with open(image_path, "rb") as f:
            resp = requests.post(
                f"{self.base_url}/upload/image",
                files={"image": (Path(image_path).name, f, "image/png")},
                data={"overwrite": "true"},
                timeout=30,
            )
        resp.raise_for_status()
        return resp.json()["name"]

    def submit_workflow(self, workflow: dict) -> str:
        """Submit a workflow dict and return the prompt_id."""
        payload = {"prompt": workflow, "client_id": self.client_id}
        resp = requests.post(f"{self.base_url}/prompt", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()["prompt_id"]

    def wait_for_result(self, prompt_id: str, timeout: int = 300) -> list[str]:
        """Poll until the job completes and return output image filenames."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = requests.get(f"{self.base_url}/history/{prompt_id}", timeout=10)
            data = resp.json()
            if prompt_id in data:
                outputs = data[prompt_id].get("outputs", {})
                images = []
                for node_out in outputs.values():
                    for img in node_out.get("images", []):
                        images.append(img["filename"])
                return images
            time.sleep(2)
        raise TimeoutError(f"ComfyUI job {prompt_id} timed out after {timeout}s")

    def download_image(self, filename: str) -> bytes:
        resp = requests.get(
            f"{self.base_url}/view",
            params={"filename": filename, "type": "output"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.content
