from app.services import progress_service


def meal_plan():
    return [{"waktu": "Makan Siang", "items": [{"nama": "Nasi", "kalori": 200, "karbo": 40, "protein": 4, "lemak": 1}]}]


def test_duplicate_meal_plan_ids_are_not_deduplicated():
    totals, foods = progress_service.selected_meal_item_totals(meal_plan(), ["mp:0:0", "mp:0:0"])

    assert totals["kalori"] == 400.0
    assert totals["karbo"] == 80.0
    assert len(foods) == 2


def test_duplicate_database_food_ids_are_not_deduplicated(monkeypatch):
    food = {
        "id": "1", "nama": "Nasi", "kalori_kkal": 180, "karbohidrat_g": 39,
        "protein_g": 3, "lemak_g": 0.5, "serat_g": 0.5, "gula_g": 0,
        "natrium_mg": 1, "is_recommended": True, "recommendation_label": "Sesuai",
        "not_recommended_reasons": [], "is_ultra_processed": False, "is_fruit": False,
    }
    monkeypatch.setattr(progress_service, "get_food_by_id", lambda food_id: food)
    monkeypatch.setattr(progress_service, "food_public_payload", lambda value: value)

    totals, foods = progress_service.selected_database_foods(["1", "1"])

    assert totals["kalori"] == 360.0
    assert len(foods) == 2
