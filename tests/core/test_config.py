from app.core.config import Settings


def test_settings_default_to_local_ollama_models(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11435")
    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    settings = Settings()

    assert settings.embedding_model == "bge-m3"
    assert settings.vector_size == 1024
    assert settings.ollama_base_url == "http://host.docker.internal:11435"
    assert settings.qa_model == "llama3.1:8b"
    assert settings.pdf_chunks_collection == "predibeat_pdf_chunks"
    assert settings.pdf_qa_collection == "predibeat_pdf_qa"
    assert len({settings.pdf_chunks_collection, settings.pdf_qa_collection, settings.food_chunks_collection}) == 3
