from __future__ import annotations

import json

from app.database.models.progress import DailyProgressLogDB
from app.database.models.user import UserDB, UserProfileDB
from app.services.chatbot_context_service import build_local_food_context, build_profile_progress_context
from app.services.common_utils import today


def _seed(factory):
    with factory() as db:
        user = UserDB(
            username="context-user",
            username_normalized="context-user",
            email="context@example.com",
            email_normalized="context@example.com",
            hashed_password="hash",
            role="user",
        )
        db.add(user)
        db.flush()
        db.add(
            UserProfileDB(
                user_id=user.id,
                full_profile_data=json.dumps({
                    "usia": 35,
                    "jenis_kelamin": "Laki-laki",
                    "berat_badan": 70,
                    "tinggi_badan": 170,
                    "active_diet": "mediterania",
                    "pantangan_alergi": "kacang",
                }),
                analysis_result=json.dumps({
                    "kategori_risiko": "Risiko Sedang",
                    "target_kalori": 1800,
                    "target_karbo": 200,
                    "target_protein": 100,
                    "target_lemak": 67,
                    "active_diet": "mediterania",
                    "active_diet_label": "Mediterranean",
                    "meal_plan": [{
                        "waktu": "Pagi",
                        "items": [{"nama": "Oatmeal", "kalori": 300, "porsi": "1 mangkuk"}],
                    }],
                }),
            )
        )
        db.add(
            DailyProgressLogDB(
                user_id=user.id,
                tanggal=today(),
                actual_kalori=900,
                actual_karbo=100,
                actual_protein=50,
                actual_lemak=30,
                target_kalori=1800,
                duration_minutes=30,
                activity_name="Jalan kaki",
            )
        )
        db.commit()
        return user.id


def test_profile_progress_context_contains_active_user_data(chatbot_db_factory):
    user_id = _seed(chatbot_db_factory)
    with chatbot_db_factory() as db:
        context = build_profile_progress_context(db, user_id)

    assert "Risiko Sedang" in context
    assert "Mediterranean" in context
    assert "Oatmeal" in context
    assert "900" in context
    assert "Jalan kaki" in context


def test_local_food_context_uses_gula_g_and_natural_fruit_rule(monkeypatch):
    monkeypatch.setattr(
        "app.services.chatbot_context_service.search_tracker_foods",
        lambda query, limit=5: [{
            "nama": "Mangga",
            "kelompok_makanan": "Buah",
            "kalori_kkal": 60,
            "gula_g": 14,
            "natrium_mg": 1,
            "is_fruit": True,
            "is_recommended": True,
            "not_recommended_reasons": [],
        }],
    )

    context = build_local_food_context("Apakah mangga aman?")
    assert "gula_g 14" in context
    assert "gula alami buah" in context
    assert "gula_tambahan_g" not in context

class FakePdfRetriever:
    def __init__(self):
        self.calls = []
    def search(self, question, limit=3):
        self.calls.append((question, limit))
        return [{"content": "Serat membantu pengelolaan pola makan.", "score": 0.9, "source_name": "pedoman.pdf"}]


class FailFoodRetriever:
    def search(self, question, limit=3):
        raise AssertionError("Food vector retriever tidak boleh dipanggil oleh chatbot V3")


def test_rag_context_keeps_pdf_and_disables_food_vector_retrieval():
    from app.services.chatbot_context_service import build_rag_context
    pdf = FakePdfRetriever()
    context, source, confidence = build_rag_context(
        "kenapa serat penting untuk prediabetes",
        retrievers_factory=lambda: (pdf, FailFoodRetriever()),
    )
    assert "Serat membantu" in context
    assert source == "pedoman.pdf"
    assert confidence == 0.9
    assert pdf.calls
