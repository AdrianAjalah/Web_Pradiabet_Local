from types import SimpleNamespace

from app.services.progress_service import serialize_log_foods
from app.services.weekly_insight_service import build_weekly_insight


def test_weekly_insight_uses_v1_rule_output():
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

    insight = build_weekly_insight([log])

    assert insight["title"].startswith("Insight minggu ini:")
    assert insight["positives"]
    assert insight["priorities"]
