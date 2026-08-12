"""Pembacaan chunk dataset makanan untuk portal admin."""
from __future__ import annotations

import math
import re
from pathlib import Path

from app.services.rag_artifact_service import RagArtifactWriter


class AdminDatasetChunkService:
    SOURCE_ID = "reference-food-master"

    def __init__(self, settings, store) -> None:
        self.settings = settings
        self.store = store

    def list_food_chunks(
        self,
        *,
        query: str = "",
        layer: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        payloads = self.store.list_source_payloads(self.SOURCE_ID, target="food")
        output_dir = Path(self.settings.rag_output_dir) / self.SOURCE_ID
        output_dir.mkdir(parents=True, exist_ok=True)
        artifact_writer = RagArtifactWriter()
        if not (output_dir / "chunks.md").is_file() or not (output_dir / "chunks.json").is_file():
            artifact_writer.write_chunk_payloads(output_dir, payloads)
        if not (output_dir / "reindex_summary.json").is_file():
            collection_name = getattr(getattr(self.store, "collections", None), "food_chunks", "predibeat_food_chunks")
            artifact_writer.write_reindex_summary(
                output_dir,
                source_id=self.SOURCE_ID,
                source_name="master_makanan_kategori_flag_mealplan.csv",
                collection_name=collection_name,
                chunk_count=len(payloads),
                status="completed",
            )
        normalized_query = str(query or "").strip().casefold()
        normalized_layer = layer if layer in {0, 1} else None

        filtered = [
            item
            for item in payloads
            if self._matches(item, normalized_query, normalized_layer)
        ]
        filtered.sort(key=self._sort_key)

        page_size = min(max(int(page_size or 50), 1), 50)
        page = max(int(page or 1), 1)
        total_items = len(filtered)
        total_pages = math.ceil(total_items / page_size) if total_items else 0
        start = (page - 1) * page_size
        end = start + page_size

        return {
            "source_id": self.SOURCE_ID,
            "query": query,
            "layer": normalized_layer,
            "chunks": filtered[start:end],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages,
                "has_previous": page > 1 and total_items > 0,
                "has_next": end < total_items,
            },
            "artifact_files": RagArtifactWriter.list_artifacts(output_dir),
            "output_path": str(output_dir),
        }

    def get_artifact_path(self, filename: str) -> Path:
        output_dir = Path(self.settings.rag_output_dir) / self.SOURCE_ID
        return RagArtifactWriter.resolve_artifact(output_dir, filename)

    @staticmethod
    def _matches(item: dict, query: str, layer: int | None) -> bool:
        if layer is not None and int(item.get("layer", -1)) != layer:
            return False
        if not query:
            return True
        haystack = " ".join(
            str(item.get(key, ""))
            for key in (
                "food_name_display",
                "food_name",
                "food_code",
                "food_category",
                "content",
                "chunk_id",
            )
        ).casefold()
        return query in haystack

    @classmethod
    def _sort_key(cls, item: dict):
        return (
            int(item.get("layer", 99) if item.get("layer") is not None else 99),
            cls._natural_key(
                str(
                    item.get("food_name_display")
                    or item.get("food_category")
                    or item.get("food_name")
                    or item.get("chunk_id")
                    or ""
                )
            ),
        )

    @staticmethod
    def _natural_key(value: str):
        return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value))
