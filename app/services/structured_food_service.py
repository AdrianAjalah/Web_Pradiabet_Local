"""Deterministic structured retrieval for the local nutrition dataset."""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from app.core.nutrition_database import NutritionDatabase
from app.services.food_service import food_public_payload, load_nutrition_foods


class StructuredFoodService:
    def __init__(self, foods: list[dict[str, Any]] | None = None, database: NutritionDatabase | None = None) -> None:
        self.database = database or NutritionDatabase(foods if foods is not None else load_nutrition_foods())

    @staticmethod
    def _public(food: dict[str, Any]) -> dict[str, Any]:
        # Test fixtures may already contain a public payload.
        if "search_text" in food or "recommendation_label" in food:
            return food_public_payload(food)
        result = dict(food)
        for key in ("gram_porsi", "kalori_kkal", "karbohidrat_g", "protein_g", "lemak_g", "serat_g", "gula_g", "natrium_mg"):
            if key in result:
                result[key] = round(float(result.get(key) or 0), 2)
        return result

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        normalized_query = self.database.normalize(query)
        if not normalized_query:
            return []
        query_tokens = normalized_query.split()
        candidates: list[tuple[tuple[float, ...], dict[str, Any]]] = []
        for food in self.database.all_foods():
            name = str(food.get("nama") or "")
            normalized_name = self.database.normalize(name)
            name_tokens = normalized_name.split()
            if not normalized_name:
                continue
            exact = normalized_name == normalized_query
            starts = normalized_name.startswith(normalized_query)
            ends = normalized_name.endswith(normalized_query)
            all_tokens = all(token in name_tokens for token in query_tokens)
            contains = normalized_query in normalized_name
            overlap = len(set(query_tokens) & set(name_tokens)) / max(1, len(set(query_tokens)))
            fuzzy = SequenceMatcher(None, normalized_query, normalized_name).ratio()
            if not (exact or starts or ends or all_tokens or contains or overlap >= 0.5 or fuzzy >= 0.55):
                continue
            # Exact first; food names beginning with query beat names such as "Sagu Rendang".
            rank = (
                1.0 if exact else 0.0,
                1.0 if starts else 0.0,
                1.0 if all_tokens else 0.0,
                1.0 if ends else 0.0,
                overlap,
                fuzzy,
                -abs(len(name_tokens) - len(query_tokens)),
            )
            candidates.append((rank, self._public(food)))
        candidates.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in candidates[: max(1, min(limit, 20))]]

    def lookup(self, query: str, limit: int = 8) -> dict[str, Any]:
        candidates = self.search(query, limit=limit)
        if not candidates:
            return {"status": "not_found", "query": query, "candidates": []}
        normalized_query = self.database.normalize(query)
        query_tokens = normalized_query.split()
        # Untuk nama majemuk, kandidat harus memuat semua kata. Contohnya
        # "sate padang" tidak boleh diarahkan ke sate ayam hanya karena sama-sama sate.
        if len(query_tokens) >= 2:
            strong_candidates = [
                item for item in candidates
                if all(token in self.database.normalize(item.get("nama", "")).split() for token in query_tokens)
            ]
            if not strong_candidates:
                return {"status": "not_found", "query": query, "candidates": []}
            candidates = strong_candidates
        exact = [item for item in candidates if self.database.normalize(item.get("nama", "")) == normalized_query]
        if len(exact) == 1:
            return {"status": "found", "query": query, "food": exact[0], "candidates": candidates}
        token_matches = [
            item for item in candidates
            if all(token in self.database.normalize(item.get("nama", "")).split() for token in query_tokens)
        ]
        if len(token_matches) == 1:
            return {"status": "found", "query": query, "food": token_matches[0], "candidates": candidates}
        # A specific multi-token query with a clearly dominant first result is safe to resolve.
        if len(normalized_query.split()) >= 2 and candidates:
            first_name = self.database.normalize(candidates[0].get("nama", ""))
            if normalized_query in first_name or first_name in normalized_query:
                return {"status": "found", "query": query, "food": candidates[0], "candidates": candidates}
        return {"status": "ambiguous", "query": query, "candidates": candidates}

    def filter_foods(
        self,
        *,
        max_calories: float | None = None,
        min_protein: float | None = None,
        max_sugar: float | None = None,
        min_fiber: float | None = None,
        category: str | None = None,
        recommended_only: bool = False,
        sort_by: str = "kalori_kkal",
        descending: bool = False,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        allowed_sort = {"kalori_kkal", "protein_g", "gula_g", "serat_g", "natrium_mg"}
        sort_column = sort_by if sort_by in allowed_sort else "kalori_kkal"
        clauses: list[str] = []
        params: list[Any] = []
        if max_calories is not None:
            clauses.append("kalori_kkal <= ?")
            params.append(float(max_calories))
        if min_protein is not None:
            clauses.append("protein_g >= ?")
            params.append(float(min_protein))
        if max_sugar is not None:
            clauses.append("gula_g <= ?")
            params.append(float(max_sugar))
        if min_fiber is not None:
            clauses.append("serat_g >= ?")
            params.append(float(min_fiber))
        if category:
            clauses.append("LOWER(kelompok_makanan) LIKE ?")
            params.append(f"%{str(category).casefold()}%")
        if recommended_only:
            clauses.append("is_recommended = 1")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        direction = "DESC" if descending else "ASC"
        sql = f"SELECT payload FROM foods{where} ORDER BY {sort_column} {direction}, nama ASC LIMIT ?"
        params.append(max(1, min(int(limit), 50)))
        return [self._public(item) for item in self.database.query(sql, tuple(params))]
