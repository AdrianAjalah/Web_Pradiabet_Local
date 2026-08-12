"""Retrieval makanan: exact match lebih dahulu, vector search sebagai fallback."""
from __future__ import annotations


class FoodRetriever:
    def __init__(self, client, embedder, collection_name: str) -> None:
        self.client = client
        self.embedder = embedder
        self.collection_name = collection_name

    def search(self, query: str, limit: int = 5) -> list[dict]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        normalized = query.strip().lower()
        exact, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=Filter(must=[FieldCondition(key="food_name", match=MatchValue(value=normalized))]),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        if exact:
            return [{"score": 1.0, **(point.payload or {})} for point in exact]
        vector = self.embedder.embed_query(query)
        hits = self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            limit=limit,
            with_payload=True,
        ).points
        return [{"score": float(hit.score), **(hit.payload or {})} for hit in hits]
