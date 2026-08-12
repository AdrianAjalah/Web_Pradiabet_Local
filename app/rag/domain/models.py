"""Model domain netral yang tidak bergantung pada FastAPI, SQLAlchemy, atau Qdrant."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DocumentElement:
    element_id: str
    element_type: str
    content: str
    page: int
    heading_level: int | None = None
    bbox: list[float] | None = None
    image_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Chunk:
    chunk_id: str
    source_id: str
    source_name: str
    source_type: str
    layer: int
    chunk_type: str
    content: str
    page_start: int | None = None
    page_end: int | None = None
    parent_chunk_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "layer": self.layer,
            "chunk_type": self.chunk_type,
            "content": self.content,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "parent_chunk_id": self.parent_chunk_id,
            **self.metadata,
        }


@dataclass(slots=True)
class QaPair:
    qa_id: str
    source_id: str
    source_name: str
    source_chunk_id: str
    question: str
    answer: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def embedding_text(self) -> str:
        return f"Pertanyaan: {self.question}\nJawaban: {self.answer}"

    def to_payload(self) -> dict[str, Any]:
        return {
            "qa_id": self.qa_id,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_type": "pdf_qa",
            "source_chunk_id": self.source_chunk_id,
            "question": self.question,
            "answer": self.answer,
            "content": self.embedding_text,
            **self.metadata,
        }


@dataclass(slots=True)
class IngestionResult:
    source_id: str
    source_name: str
    chunk_count: int
    qa_count: int
    status: str = "completed"
