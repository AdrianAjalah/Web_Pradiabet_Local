"""Grounded deterministic tools used by the nutrition chatbot."""
from __future__ import annotations

from typing import Any

from app.services.structured_food_service import StructuredFoodService

NUTRIENT_KEYS = ("kalori_kkal", "karbohidrat_g", "protein_g", "lemak_g", "serat_g", "gula_g", "natrium_mg")


class ChatbotToolService:
    def __init__(self, food_service: StructuredFoodService | None = None) -> None:
        self.food_service = food_service or StructuredFoodService()

    def execute(self, plan: dict[str, Any]) -> dict[str, Any]:
        intent = str(plan.get("intent") or "general_chat")
        if intent == "food_lookup":
            result = self.food_service.lookup(str(plan.get("food_name") or ""))
            result["intent"] = intent
            result["requested_fields"] = list(plan.get("requested_fields") or [])
            return result
        if intent == "meal_total":
            return self._calculate_total(plan)
        if intent == "compare_foods":
            return self._compare(plan)
        if intent in {"food_filter", "recommend_foods"}:
            foods = self.food_service.filter_foods(
                max_calories=plan.get("max_calories"), min_protein=plan.get("min_protein"),
                max_sugar=plan.get("max_sugar"), min_fiber=plan.get("min_fiber"),
                category=plan.get("category"), recommended_only=bool(plan.get("recommended_only", intent == "recommend_foods")),
                sort_by=str(plan.get("sort_by") or "kalori_kkal"), descending=bool(plan.get("descending")),
                limit=int(plan.get("limit") or 5),
            )
            return {"intent": intent, "status": "found" if foods else "not_found", "foods": foods, "criteria": plan}
        return {"intent": intent, "status": "no_tool"}

    def _resolve_item(self, item: dict[str, Any]) -> dict[str, Any]:
        lookup = self.food_service.lookup(str(item.get("food_name") or ""))
        if lookup.get("status") != "found":
            return {"status": lookup.get("status"), "query": item.get("food_name"), "candidates": lookup.get("candidates", [])}
        food = dict(lookup["food"])
        quantity = float(item.get("quantity") or 1)
        requested_grams = item.get("grams")
        base_grams = float(food.get("gram_porsi") or 100)
        factor = float(requested_grams) / base_grams if requested_grams else quantity
        scaled = {key: round(float(food.get(key) or 0) * factor, 2) for key in NUTRIENT_KEYS}
        return {"status": "found", "query": item.get("food_name"), "food": food, "quantity": quantity, "grams": requested_grams or base_grams * quantity, "scaled": scaled}

    def _calculate_total(self, plan: dict[str, Any]) -> dict[str, Any]:
        resolved = [self._resolve_item(item) for item in (plan.get("items") or [])]
        unresolved = [item for item in resolved if item.get("status") != "found"]
        if unresolved:
            return {"intent": "meal_total", "status": "needs_clarification", "items": resolved, "unresolved": unresolved}
        missing_nutrition = [
            item for item in resolved
            if float(item.get("food", {}).get("kalori_kkal") or 0) <= 0
        ]
        if missing_nutrition:
            return {
                "intent": "meal_total",
                "status": "missing_nutrition",
                "items": resolved,
                "missing_nutrition": missing_nutrition,
            }
        totals = {key: round(sum(float(item["scaled"].get(key) or 0) for item in resolved), 2) for key in NUTRIENT_KEYS}
        return {"intent": "meal_total", "status": "calculated", "items": resolved, "totals": totals}

    def _compare(self, plan: dict[str, Any]) -> dict[str, Any]:
        items = [self._resolve_item({"food_name": name, "quantity": 1}) for name in (plan.get("food_names") or [])]
        if any(item.get("status") != "found" for item in items):
            return {"intent": "compare_foods", "status": "needs_clarification", "items": items}
        return {"intent": "compare_foods", "status": "calculated", "items": items}
