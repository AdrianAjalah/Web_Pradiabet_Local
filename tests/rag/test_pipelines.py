from pathlib import Path

from app.rag.domain.models import Chunk, DocumentElement, QaPair
from app.rag.pipelines.csv_pipeline import CsvIngestionPipeline
from app.rag.pipelines.pdf_pipeline import PdfIngestionPipeline


class FakeExtractor:
    def extract(self, source_path, output_dir):
        return [DocumentElement("e1", "text", "Isi PDF", 1)]


class FakePdfChunker:
    def chunk(self, elements, source_id, source_name, document_summary):
        return [Chunk("c1", source_id, source_name, "pdf", 0, "element", "Isi PDF")]


class FakeCsvChunker:
    def chunk_file(self, source_path, source_id, source_name):
        return [Chunk("f1", source_id, source_name, "csv", 0, "food_row", "Pisang")]


class FakeQa:
    called = False

    def generate_for_chunks(self, chunks):
        self.called = True
        return [QaPair("q1", chunks[0].source_id, chunks[0].source_name, chunks[0].chunk_id, "Apa?", "Isi")]


class FakeEmbedder:
    def embed_texts(self, texts):
        return [[0.1, 0.2] for _ in texts]


class FakeStore:
    def __init__(self):
        self.chunk_calls = []
        self.qa_calls = []
        self.delete_calls = []

    def upsert_chunks(self, chunks, vectors, target):
        self.chunk_calls.append((chunks, vectors, target))

    def upsert_qa(self, pairs, vectors):
        self.qa_calls.append((pairs, vectors))

    def delete_source(self, source_id, targets):
        self.delete_calls.append((source_id, tuple(targets)))


class FakeSummary:
    def summarize(self, text):
        return "Ringkasan"


def test_pdf_pipeline_generates_qa(tmp_path: Path):
    qa = FakeQa()
    store = FakeStore()
    pipeline = PdfIngestionPipeline(FakeExtractor(), FakePdfChunker(), qa, FakeEmbedder(), store, FakeSummary())
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"pdf")

    result = pipeline.run(pdf, "doc1", tmp_path / "out")

    assert qa.called is True
    assert result.qa_count == 1
    assert len(store.qa_calls) == 1


def test_csv_pipeline_never_generates_qa(tmp_path: Path):
    store = FakeStore()
    pipeline = CsvIngestionPipeline(FakeCsvChunker(), FakeEmbedder(), store)
    csv_file = tmp_path / "food.csv"
    csv_file.write_text("nama_makanan\nPisang", encoding="utf-8")

    result = pipeline.run(csv_file, "food1")

    assert result.qa_count == 0
    assert store.qa_calls == []
    assert store.delete_calls == [("food1", ("food",))]

class FakeImageExtractor:
    def extract(self, source_path, output_dir):
        image_path = Path(output_dir) / "chart.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(b"image")
        return [DocumentElement("e1", "image", "Caption awal", 1, image_path=str(image_path))]


class CapturingPdfChunker:
    def __init__(self):
        self.elements = []

    def chunk(self, elements, source_id, source_name, document_summary):
        self.elements = elements
        return [Chunk("c1", source_id, source_name, "pdf", 0, "element", elements[0].content)]


class FakeImageDescriber:
    def describe_image(self, image_path):
        return "Grafik menunjukkan tren gula darah menurun."


def test_pdf_pipeline_adds_llava_description_to_image_element(tmp_path: Path):
    chunker = CapturingPdfChunker()
    pipeline = PdfIngestionPipeline(
        FakeImageExtractor(),
        chunker,
        FakeQa(),
        FakeEmbedder(),
        FakeStore(),
        FakeSummary(),
        image_describer=FakeImageDescriber(),
    )
    pdf = tmp_path / "chart.pdf"
    pdf.write_bytes(b"pdf")

    pipeline.run(pdf, "doc-image", tmp_path / "out")

    assert "Caption awal" in chunker.elements[0].content
    assert "Grafik menunjukkan tren gula darah menurun." in chunker.elements[0].content
