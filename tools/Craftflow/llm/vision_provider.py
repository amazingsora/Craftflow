import base64
from pathlib import Path

import requests


class VisionProvider:
    """Wraps Ollama vision models (e.g. llava, qwen2-vl) for image analysis."""

    def __init__(self, model: str = "llava", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    def analyze(self, image_path: str, prompt: str) -> str:
        image_bytes = Path(image_path).read_bytes()
        image_b64 = base64.b64encode(image_bytes).decode()

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "images": [image_b64],
                    "stream": False,
                },
                timeout=180,
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except requests.exceptions.ConnectionError:
            return "[Vision analysis unavailable: Ollama is not running. Start it with `ollama serve`.]"
        except Exception as e:
            return f"[Vision analysis failed: {e}]"
