"""Retrieval gabungan chunk PDF dan QA PDF."""
from __future__ import annotations


class PdfRetriever:
    def __init__(self, client, embedder, collections) -> None:
        self.client = client
        self.embedder = embedder
        self.collections = collections

    def search(self, query: str, limit: int = 5) -> list[dict]:
        vector = self.embedder.embed_query(query)
        results: list[dict] = []
        for collection in (self.collections.pdf_qa, self.collections.pdf_chunks):
            hits = self.client.query_points(
                collection_name=collection,
                query=vector,
                limit=limit,
                with_payload=True,
            ).points
            for hit in hits:
                results.append({"score": float(hit.score), "collection": collection, **(hit.payload or {})})
        return sorted(results, key=lambda item: item["score"], reverse=True)[:limit]
