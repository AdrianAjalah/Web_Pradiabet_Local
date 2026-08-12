"""Orkestrasi ingestion CSV dua layer tanpa QA."""
from __future__ import annotations

from pathlib import Path

from app.rag.domain.models import IngestionResult
from app.services.rag_artifact_service import RagArtifactWriter


class CsvIngestionPipeline:
    def __init__(self, chunker, embedder, store, artifact_writer=None) -> None:
        self.chunker = chunker
        self.embedder = embedder
        self.store = store
        self.artifact_writer = artifact_writer or RagArtifactWriter()

    def run(self, source_path: Path, source_id: str, output_dir: Path | None = None) -> IngestionResult:
        # Reindex dengan source_id yang sama harus mengganti vector lama, bukan menambah duplikat.
        self.store.delete_source(source_id, targets=("food",))
        chunks = self.chunker.chunk_file(source_path, source_id=source_id, source_name=source_path.name)
        output_dir = Path(output_dir) if output_dir is not None else source_path.parent / source_id
        self.artifact_writer.write_chunks(output_dir, chunks)
        vectors = self.embedder.embed_texts([chunk.content for chunk in chunks])
        self.store.upsert_chunks(chunks, vectors, target="food")
        collection_name = getattr(getattr(self.store, "collections", None), "food_chunks", "predibeat_food_chunks")
        self.artifact_writer.write_reindex_summary(
            output_dir,
            source_id=source_id,
            source_name=source_path.name,
            collection_name=collection_name,
            chunk_count=len(chunks),
            status="completed",
        )
        return IngestionResult(source_id, source_path.name, len(chunks), 0)
