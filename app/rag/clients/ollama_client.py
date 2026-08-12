"""HTTP client sederhana untuk Ollama melalui SSH tunnel."""
from __future__ import annotations

import time
from typing import Any

import requests


class OllamaHttpClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: int = 180,
        retries: int = 2,
        session: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.session = session or requests.Session()

    def embed(self, texts: list[str], model: str = "bge-m3") -> list[list[float]]:
        if not texts:
            return []
        payload = {"model": model, "input": texts}
        try:
            response = self._post("/api/embed", payload)
            data = response.json()
            vectors = data.get("embeddings")
            if vectors:
                return vectors
        except Exception:
            pass

        vectors: list[list[float]] = []
        for text in texts:
            response = self._post("/api/embeddings", {"model": model, "prompt": text})
            vector = response.json().get("embedding")
            if not vector:
                raise RuntimeError("Ollama tidak mengembalikan embedding.")
            vectors.append(vector)
        return vectors

    def chat(
        self,
        prompt: str,
        model: str,
        system: str | None = None,
        *,
        format: str | dict[str, Any] | None = None,
        temperature: float | None = None,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if format is not None:
            payload["format"] = format
        if temperature is not None:
            payload["options"] = {"temperature": float(temperature)}
        response = self._post("/api/chat", payload)
        data = response.json()
        return str(data.get("message", {}).get("content") or data.get("response") or "").strip()

    def _post(self, path: str, payload: dict[str, Any]):
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.post(
                    f"{self.base_url}{path}",
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                return response
            except Exception as exc:  # requests dan fake session test memiliki exception berbeda
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"Gagal menghubungi Ollama di {self.base_url}: {last_error}")
