"""Factory embedding lokal BGE-M3 melalui Ollama."""
from __future__ import annotations

from app.rag.clients.ollama_client import OllamaHttpClient
from app.rag.embeddings.ollama_bge_m3 import OllamaBgeM3Embedder


def build_embedder(settings):
    client = OllamaHttpClient(settings.ollama_base_url, settings.ollama_timeout_seconds)
    return OllamaBgeM3Embedder(client, settings.embedding_model)
