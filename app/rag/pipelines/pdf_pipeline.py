"""Orkestrasi penuh ingestion PDF."""
from __future__ import annotations

from pathlib import Path

from app.rag.domain.models import IngestionResult
from app.services.rag_artifact_service import RagArtifactWriter


class PdfIngestionPipeline:
    def __init__(
        self,
        extractor,
        chunker,
        qa_generator,
        embedder,
        store,
        summarizer,
        image_describer=None,
        artifact_writer=None,
    ) -> None:
        self.extractor = extractor
        self.chunker = chunker
        self.qa_generator = qa_generator
        self.embedder = embedder
        self.store = store
        self.summarizer = summarizer
        self.image_describer = image_describer
        self.artifact_writer = artifact_writer or RagArtifactWriter()

    def run(self, source_path: Path, source_id: str, output_dir: Path) -> IngestionResult:
        elements = self.extractor.extract(source_path, output_dir)
        self._enrich_images(elements)
        self.artifact_writer.write_pdf_extraction(output_dir, source_path.name, elements)
        full_text = "\n".join(element.content for element in elements if element.content)
        summary = self.summarizer.summarize(full_text)
        chunks = self.chunker.chunk(
            elements,
            source_id=source_id,
            source_name=source_path.name,
            document_summary=summary,
        )
        self.artifact_writer.write_chunks(output_dir, chunks)
        vectors = self.embedder.embed_texts([chunk.content for chunk in chunks])
        self.store.upsert_chunks(chunks, vectors, target="pdf")

        qa_pairs = self.qa_generator.generate_for_chunks(chunks)
        self.artifact_writer.write_qa(output_dir, qa_pairs)
        qa_vectors = self.embedder.embed_texts([pair.embedding_text for pair in qa_pairs])
        self.store.upsert_qa(qa_pairs, qa_vectors)
        return IngestionResult(source_id, source_path.name, len(chunks), len(qa_pairs))
    def _enrich_images(self, elements) -> None:
        """Tambahkan deskripsi LLaVA ke elemen gambar tanpa menghapus caption MinerU."""

        if self.image_describer is None:
            return
        for element in elements:
            if element.element_type != "image" or not element.image_path:
                continue
            try:
                description = self.image_describer.describe_image(Path(element.image_path)).strip()
            except Exception as exc:
                element.metadata["image_description_error"] = str(exc)[:500]
                continue
            if description and description not in element.content:
                element.content = f"{element.content}\nDeskripsi visual: {description}".strip()
                element.metadata["image_described_by"] = "llava"

