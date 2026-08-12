from app.services.activity_service import calculate_activity_calories, find_activity_met


def test_find_activity_met_uses_dataset(monkeypatch):
    monkeypatch.setattr(
        "app.services.activity_service.load_activities",
        lambda force_reload=False: [
            {
                "nama": "Jalan Kaki",
                "kategori": "Kardio",
                "met_details": [{"tipe": "Jalan cepat", "met": 4.5}],
            }
        ],
    )

    activity, met = find_activity_met("Jalan Kaki", "Jalan cepat")

    assert activity["kategori"] == "Kardio"
    assert met == 4.5


def test_activity_calories_subtract_resting_met():
    # Resting 1 MET is subtracted because baseline calories are counted separately.
    assert calculate_activity_calories(5.0, 60.0, 30.0) == 120.0
