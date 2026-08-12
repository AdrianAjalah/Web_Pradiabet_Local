"""Factory client text-generation lokal."""
from __future__ import annotations

from app.rag.clients.ollama_client import OllamaHttpClient


def build_text_generation_client(settings):
    return OllamaHttpClient(settings.ollama_base_url, settings.ollama_timeout_seconds)
