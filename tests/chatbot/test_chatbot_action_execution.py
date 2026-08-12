from __future__ import annotations

import json

from app.database.models.progress import DailyProgressLogDB
from app.database.models.user import UserDB, UserProfileDB
from app.services.chatbot_action_service import ChatbotActionExecutor
from app.services.common_utils import today
from app.services.progress_service import get_log_foods, serialize_log_foods


def _seed_user(factory):
    with factory() as db:
        user = UserDB(
            username="chat-user",
            username_normalized="chat-user",
            email="chat@example.com",
            email_normalized="chat@example.com",
            hashed_password="hash",
            role="user",
        )
        db.add(user)
        db.flush()
        profile = {
            "usia": 35,
            "jenis_kelamin": "Laki-laki",
            "berat_badan": 70,
            "tinggi_badan": 170,
            "frekuensi_makan": "3x",
            "waktu_makan": ["Pagi", "Siang", "Malam"],
            "pola_waktu_makan": "normal",
        }
        analysis = {
            "target_kalori": 1800,
            "target_karbo": 200,
            "target_protein": 100,
            "target_lemak": 67,
            "tdee_mifflin": 2200,
            "kategori_risiko": "Risiko Sedang",
            "meal_plan": [],
        }
        db.add(
            UserProfileDB(
                user_id=user.id,
                full_profile_data=json.dumps(profile),
                analysis_result=json.dumps(analysis),
            )
        )
        db.commit()
        return user.id


def _food():
    return {
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


def _patch_food(monkeypatch):
    food = _food()
    monkeypatch.setattr(
        "app.services.progress_service.get_food_by_id",
        lambda food_id: food if str(food_id) == "7" else None,
    )
    monkeypatch.setattr("app.services.progress_service.food_public_payload", lambda value: value)
    monkeypatch.setattr(
        "app.services.chatbot_action_service.get_food_by_id",
        lambda food_id: food if str(food_id) == "7" else None,
    )


def _action(quantity=2):
    return {
        "type": "add_food",
        "groups": [{
            "query": "nasi putih",
            "quantity": quantity,
            "selected_food_id": "7",
            "candidates": [{"id": "7", "nama": "Nasi putih"}],
        }],
    }


def test_add_food_creates_today_log_and_counts_quantity(chatbot_db_factory, monkeypatch):
    user_id = _seed_user(chatbot_db_factory)
    _patch_food(monkeypatch)

    with chatbot_db_factory() as db:
        result = ChatbotActionExecutor(db).execute(user_id=user_id, action=_action(2))

    with chatbot_db_factory() as db:
        log = db.query(DailyProgressLogDB).filter_by(user_id=user_id, tanggal=today()).one()
        foods = get_log_foods(log)

    assert result["foods_added"] == {"Nasi putih": 2}
    assert log.actual_kalori == 360
    assert len(foods) == 2


def test_add_food_preserves_existing_foods_and_activity(chatbot_db_factory, monkeypatch):
    user_id = _seed_user(chatbot_db_factory)
    _patch_food(monkeypatch)
    existing = {
        "source": "database",
        "id": "7",
        "nama": "Nasi putih",
        "kalori": 180,
        "karbo": 39,
        "protein": 3.5,
        "lemak": 0.4,
        "is_recommended": True,
    }
    with chatbot_db_factory() as db:
        db.add(
            DailyProgressLogDB(
                user_id=user_id,
                tanggal=today(),
                actual_kalori=180,
                actual_karbo=39,
                actual_protein=3.5,
                actual_lemak=0.4,
                activity_name="Jalan Kaki",
                activity_type="Cepat",
                activity_met=4.5,
                duration_minutes=30,
                activity_calories=120,
                notes=serialize_log_foods([existing]),
            )
        )
        db.commit()

    with chatbot_db_factory() as db:
        ChatbotActionExecutor(db).execute(user_id=user_id, action=_action(2))

    with chatbot_db_factory() as db:
        log = db.query(DailyProgressLogDB).filter_by(user_id=user_id, tanggal=today()).one()
        foods = get_log_foods(log)

    assert log.actual_kalori == 540
    assert len(foods) == 3
    assert log.activity_name == "Jalan Kaki"
    assert log.activity_calories == 120
