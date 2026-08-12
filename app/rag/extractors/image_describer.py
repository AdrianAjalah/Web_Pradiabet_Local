"""Deskripsi gambar MinerU memakai LLaVA melalui tunnel HPC."""
from __future__ import annotations

import base64
from pathlib import Path


class OllamaImageDescriber:
    def __init__(self, client, model: str = "llava") -> None:
        self.client = client
        self.model = model

    def describe_image(self, image_path: Path) -> str:
        image_path = Path(image_path)
        if not image_path.exists():
            return ""
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": "Jelaskan isi gambar atau grafik ini secara faktual untuk basis pengetahuan prediabetes.",
                    "images": [encoded],
                }
            ],
            "stream": False,
        }
        response = self.client._post("/api/chat", payload)
        return str(response.json().get("message", {}).get("content") or "").strip()
