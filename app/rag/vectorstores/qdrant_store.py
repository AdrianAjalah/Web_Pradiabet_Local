"""Penyimpanan Qdrant dengan collection PDF, QA, dan makanan yang terpisah."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Iterable

from app.rag.domain.models import Chunk, QaPair

logger = logging.getLogger("predibeat.qdrant_store")


@dataclass(frozen=True, slots=True)
class CollectionNames:
    pdf_chunks: str
    pdf_qa: str
    food_chunks: str


def deterministic_point_id(key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


class QdrantVectorStore:
    def __init__(
        self,
        client,
        collections: CollectionNames,
        vector_size: int = 1024,
        upsert_batch_size: int = 128,
    ) -> None:
        if upsert_batch_size <= 0:
            raise ValueError("Ukuran batch upsert harus lebih dari 0.")
        self.client = client
        self.collections = collections
        self.vector_size = vector_size
        self.upsert_batch_size = upsert_batch_size

    def ensure_collections(self) -> None:
        from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

        existing = {item.name for item in self.client.get_collections().collections}
        collection_names = (
            self.collections.pdf_chunks,
            self.collections.pdf_qa,
            self.collections.food_chunks,
        )
        for name in collection_names:
            if name not in existing:
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
                )

        required_indexes = {
            self.collections.pdf_chunks: ("source_id",),
            self.collections.pdf_qa: ("source_id",),
            self.collections.food_chunks: ("source_id", "food_name"),
        }
        for collection_name, field_names in required_indexes.items():
            collection_info = self.client.get_collection(collection_name=collection_name)
            payload_schema = getattr(collection_info, "payload_schema", {}) or {}
            for field_name in field_names:
                if field_name in payload_schema:
                    continue
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=PayloadSchemaType.KEYWORD,
                    wait=True,
                )

    def upsert_chunks(self, chunks: list[Chunk], vectors: list[list[float]], target: str) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("Jumlah chunk dan vector harus sama.")
        from qdrant_client.models import PointStruct

        collection = self._collection_for_target(target)
        points = [
            PointStruct(
                id=deterministic_point_id(chunk.chunk_id),
                vector=vector,
                payload=chunk.to_payload(),
            )
            for chunk, vector in zip(chunks, vectors)
        ]
        self._upsert_points(collection, points)

    def upsert_qa(self, pairs: list[QaPair], vectors: list[list[float]]) -> None:
        if len(pairs) != len(vectors):
            raise ValueError("Jumlah QA dan vector harus sama.")
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(
                id=deterministic_point_id(pair.qa_id),
                vector=vector,
                payload=pair.to_payload(),
            )
            for pair, vector in zip(pairs, vectors)
        ]
        self._upsert_points(self.collections.pdf_qa, points)

    def _upsert_points(self, collection_name: str, points: list) -> None:
        total = len(points)
        if total == 0:
            return

        total_batches = (total + self.upsert_batch_size - 1) // self.upsert_batch_size
        for batch_number, start in enumerate(range(0, total, self.upsert_batch_size), start=1):
            batch = points[start : start + self.upsert_batch_size]
            logger.info(
                "Upload Qdrant %s: batch %s/%s (%s points)",
                collection_name,
                batch_number,
                total_batches,
                len(batch),
            )
            self.client.upsert(
                collection_name=collection_name,
                points=batch,
                wait=True,
            )

    def list_source_payloads(
        self,
        source_id: str,
        target: str,
        batch_size: int = 100,
    ) -> list[dict]:
        """Ambil seluruh payload satu sumber memakai pagination Qdrant scroll."""

        if batch_size <= 0:
            raise ValueError("Ukuran batch scroll harus lebih dari 0.")
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        source_filter = Filter(
            must=[FieldCondition(key="source_id", match=MatchValue(value=source_id))]
        )
        collection_name = self._collection_for_target(target)
        offset = None
        payloads: list[dict] = []
        while True:
            points, next_offset = self.client.scroll(
                collection_name=collection_name,
                scroll_filter=source_filter,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in points:
                payload = dict(getattr(point, "payload", None) or {})
                payloads.append({"point_id": str(point.id), **payload})
            if next_offset is None:
                break
            offset = next_offset
        return payloads

    def delete_source(self, source_id: str, targets: Iterable[str] = ("pdf", "qa", "food")) -> None:
        from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

        selector = FilterSelector(
            filter=Filter(must=[FieldCondition(key="source_id", match=MatchValue(value=source_id))])
        )
        for target in targets:
            self.client.delete(
                collection_name=self._collection_for_target(target),
                points_selector=selector,
                wait=True,
            )

    def _collection_for_target(self, target: str) -> str:
        mapping = {
            "pdf": self.collections.pdf_chunks,
            "qa": self.collections.pdf_qa,
            "food": self.collections.food_chunks,
        }
        try:
            return mapping[target]
        except KeyError as exc:
            raise ValueError(f"Target Qdrant tidak dikenal: {target}") from exc
