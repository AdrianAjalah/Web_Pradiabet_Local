"""Provider embedding tunggal untuk indexing dan query."""
from __future__ import annotations

from app.rag.clients.ollama_client import OllamaHttpClient


class OllamaBgeM3Embedder:
    def __init__(self, client: OllamaHttpClient, model: str = "bge-m3", batch_size: int = 32) -> None:
        self.client = client
        self.model = model
        self.batch_size = batch_size

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(self.client.embed(texts[start : start + self.batch_size], model=self.model))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_texts([text])
        if not vectors:
            raise RuntimeError("Embedding query kosong.")
        return vectors[0]
