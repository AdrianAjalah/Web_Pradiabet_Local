from types import SimpleNamespace

from app.rag.retrieval.pdf_retriever import PdfRetriever


class FakeEmbedder:
    def embed_query(self, text):
        return [0.1, 0.2]


class FakeClient:
    def __init__(self):
        self.calls = []

    def query_points(self, **kwargs):
        self.calls.append(kwargs)
        score = 0.9 if kwargs["collection_name"] == "qa" else 0.8
        return SimpleNamespace(
            points=[SimpleNamespace(score=score, payload={"content": kwargs["collection_name"]})]
        )


def test_pdf_retriever_uses_modern_query_points_for_qa_and_chunks():
    client = FakeClient()
    collections = SimpleNamespace(pdf_qa="qa", pdf_chunks="chunks")
    retriever = PdfRetriever(client, FakeEmbedder(), collections)

    results = retriever.search("Apa isi dokumen?", limit=3)

    assert [call["collection_name"] for call in client.calls] == ["qa", "chunks"]
    assert all(call["with_payload"] is True for call in client.calls)
    assert results[0]["collection"] == "qa"
