from types import SimpleNamespace

from app.services.health_score_service import calculate_weekly_health_score
from app.services.progress_service import serialize_log_foods


def test_health_score_keeps_v1_breakdown():
    log = SimpleNamespace(
        target_kalori=1800,
        actual_kalori=1700,
        meal_plan_adherence_percent=80,
        duration_minutes=150,
        activity_calories=300,
        calories_out=2200,
        deficit_calories=500,
        actual_karbo=200,
        actual_protein=90,
        actual_lemak=55,
        notes=serialize_log_foods([]),
    )

    result = calculate_weekly_health_score([log])

    assert result["status"] in {"Sangat Baik", "Baik", "Cukup", "Perlu Ditingkatkan"}
    assert set(result["breakdown"]) == {"meal_plan", "activity", "calorie_balance", "food_quality"}
    assert result["metrics"]["total_exercise_minutes"] == 150.0
