from pathlib import Path

import pytest

from app.services import progress_service


def _meal_plan():
    return [
        {
            "waktu": "Makan Siang",
            "items": [
                {
                    "nama": "Nasi merah",
                    "kalori": 200,
                    "karbo": 40,
                    "protein": 4,
                    "lemak": 1,
                }
            ],
        }
    ]


def test_same_meal_plan_item_can_be_counted_more_than_once():
    total, foods = progress_service.selected_meal_item_totals(
        _meal_plan(),
        ["mp:0:0", "mp:0:0"],
    )

    assert total == {"kalori": 400.0, "karbo": 80.0, "protein": 8.0, "lemak": 2.0}
    assert len(foods) == 2
    assert [food["nama"] for food in foods] == ["Nasi merah", "Nasi merah"]


def test_same_database_food_id_can_be_counted_more_than_once(monkeypatch):
    food = {
        "id": "7",
        "nama": "Nasi putih",
        "kalori_kkal": 180,
        "karbohidrat_g": 39,
        "protein_g": 3.5,
        "lemak_g": 0.4,
        "serat_g": 0.6,
        "gula_g": 0.1,
        "natrium_mg": 2,
        "is_recommended": True,
        "recommendation_label": "Rekomendasi meal plan",
        "not_recommended_reasons": [],
        "is_ultra_processed": False,
        "is_fruit": False,
    }
    monkeypatch.setattr(progress_service, "get_food_by_id", lambda food_id: food if food_id == "7" else None)
    monkeypatch.setattr(progress_service, "food_public_payload", lambda value: value)

    total, foods = progress_service.selected_database_foods(["7", "7"])

    assert total == {"kalori": 360.0, "karbo": 78.0, "protein": 7.0, "lemak": 0.8}
    assert len(foods) == 2


def test_progress_template_uses_quantity_stepper_and_v1_save_flow():
    template = Path("templates/progress_tracker.html").read_text(encoding="utf-8")

    assert "Simpan Catatan Harian" in template
    assert "meal-count-minus" in template
    assert "meal-count-plus" in template
    assert "selected_meal_item_counts" in template
    assert "Tambahkan makanan lain" in template
    assert "autosave" not in template.casefold()
