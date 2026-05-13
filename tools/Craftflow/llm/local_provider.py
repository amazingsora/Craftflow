import requests
from llm.base import LLMProvider


class LocalProvider(LLMProvider):

    def __init__(self, model="llama3"):
        self.model = model

    def generate(self, prompt: str) -> str:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False
            },
            timeout=120
        )

        if response.status_code != 200:
            raise RuntimeError("Local LLM request failed.")

        return response.json()["response"]
