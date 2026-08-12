from types import SimpleNamespace

from app.rag.embeddings.factory import build_embedder
from app.rag.embeddings.ollama_bge_m3 import OllamaBgeM3Embedder


def test_embedding_factory_builds_local_bge_m3_provider():
    settings = SimpleNamespace(
        ollama_base_url="http://ollama:11434",
        ollama_timeout_seconds=10,
        embedding_model="bge-m3",
    )

    embedder = build_embedder(settings)

    assert isinstance(embedder, OllamaBgeM3Embedder)
    assert embedder.model == "bge-m3"
