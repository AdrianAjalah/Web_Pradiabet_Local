import sys
from types import ModuleType, SimpleNamespace

import app.bootstrap as bootstrap


def test_build_pdf_retriever_uses_embedding_factory(monkeypatch):
    fake_embedder = object()
    fake_client = object()
    settings = SimpleNamespace(
        qdrant_url="https://qdrant.example",
        qdrant_api_key="key",
        pdf_chunks_collection="chunks",
        pdf_qa_collection="qa",
        food_chunks_collection="food",
    )

    monkeypatch.setattr(bootstrap, "Settings", lambda: settings)
    monkeypatch.setattr(bootstrap, "build_embedder", lambda value: fake_embedder)
    fake_module = ModuleType("qdrant_client")
    fake_module.QdrantClient = lambda **kwargs: fake_client
    monkeypatch.setitem(sys.modules, "qdrant_client", fake_module)

    retriever = bootstrap.build_pdf_retriever()

    assert retriever.client is fake_client
    assert retriever.embedder is fake_embedder
