from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_reports_local_rag_and_structured_nutrition_without_secrets():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["app"] == "PrediBeat V3 Structured Chatbot"
    assert payload["structured_nutrition"] is True
    assert payload["pdf_rag"] is True
    assert payload["embedding_provider"] == "ollama"
    assert payload["embedding_model"] == "bge-m3"
    assert payload["pdf_collections"]["chunks"] == "predibeat_pdf_chunks"
    assert payload["pdf_collections"]["qa"] == "predibeat_pdf_qa"
    assert "api_key" not in str(payload).casefold()
