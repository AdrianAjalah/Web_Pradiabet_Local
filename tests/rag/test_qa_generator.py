from app.rag.domain.models import Chunk
from app.rag.qa.pdf_qa_generator import PdfQaGenerator


class FakeClient:
    def chat(self, prompt, model, system=None):
        return '```json\n[{"question":"Apa itu prediabetes?","answer":"Kondisi awal sebelum diabetes."}]\n```'


def test_qa_generator_parses_json_and_keeps_source_chunk():
    chunk = Chunk("c1", "doc", "panduan.pdf", "pdf", 1, "section", "Prediabetes adalah kondisi awal")
    pairs = PdfQaGenerator(FakeClient(), model="llama3.1:8b").generate_for_chunks([chunk])

    assert len(pairs) == 1
    assert pairs[0].source_chunk_id == "c1"
    assert pairs[0].question.startswith("Apa")
