from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database.connection import get_db
from app.database.models.user import QuestionnaireDraftDB, UserDB, UserProfileDB
from app.main import create_app
from app.user.security import hash_password


@pytest.fixture()
def client(db_session_factory):
    app = create_app()

    def override_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client


def register(client: TestClient, username="new-user", email="new@example.com"):
    return client.post(
        "/register",
        data={"username": username, "email": email, "password": "password123"},
        follow_redirects=False,
    )


def valid_assessment_form():
    return {
        "usia": "35",
        "jenis_kelamin": "Laki-laki",
        "berat_badan": "75",
        "tinggi_badan": "170",
        "lingkar_pinggang": "",
        "frekuensi_minum_manis": "1-3x per minggu",
        "porsi_nasi_per_hari": "2 porsi",
        "frekuensi_olahraga": "1-2x per minggu",
        "durasi_duduk_rebahan": "4-6 jam",
        "durasi_tidur": "7-8 jam",
        "riwayat_keluarga_diabetes": "false",
        "gejala_klasik": "Tidak ada gejala",
        "pantangan_alergi": "",
        "penyakit_lain_obat": "",
        "hasil_lab": "",
        "frekuensi_makan": "3x",
        "waktu_makan": "Pagi",
        "pola_waktu_makan": "normal",
    }


def fake_analysis():
    payload = {
        "bmi": 26.0,
        "kategori_bmi": "Kelebihan berat badan",
        "tdee_mifflin": 2200.0,
        "kategori_tdee": "deficit",
        "skor_risiko": 3,
        "kategori_risiko": "Risiko Sedang",
        "target_kalori": 1800.0,
        "target_karbo": 200.0,
        "target_protein": 100.0,
        "target_lemak": 67.0,
        "profil_singkat": "Profil uji",
        "active_diet": None,
        "active_diet_label": None,
        "pantangan": [],
        "meal_plan": [],
        "frekuensi_makan": "3x",
        "waktu_makan": ["Pagi", "Siang", "Malam"],
        "pola_waktu_makan": "normal",
        "pola_puasa": None,
        "jam_makan_mulai": None,
        "jam_makan_selesai": None,
        "catatan_pola_makan": [],
    }
    return SimpleNamespace(model_dump=lambda: payload)


def test_landing_and_registration_auto_login_to_questionnaire(client, db_session_factory):
    assert client.get("/").status_code == 200

    response = register(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/questionnaire"
    assert "predibeat_session" in response.cookies

    with db_session_factory() as db:
        user = db.scalar(select(UserDB).where(UserDB.username_normalized == "new-user"))
        assert user is not None
        assert user.email_normalized == "new@example.com"


def test_registration_rejects_case_insensitive_duplicate(client):
    assert register(client, "Daniel", "daniel@example.com").status_code == 303
    response = register(client, "DANIEL", "other@example.com")
    assert response.status_code == 400
    assert "Username sudah digunakan" in response.text


def test_login_accepts_username_or_email_and_routes_by_profile(client, db_session_factory):
    with db_session_factory() as db:
        user = UserDB(
            username="Daniel",
            username_normalized="daniel",
            email="Daniel@example.com",
            email_normalized="daniel@example.com",
            hashed_password=hash_password("password123"),
            role="user",
        )
        db.add(user)
        db.commit()
        user_id = user.id

    response = client.post(
        "/login",
        data={"username": "DANIEL@example.com", "password": "password123"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/questionnaire"

    with db_session_factory() as db:
        db.add(
            UserProfileDB(
                user_id=user_id,
                full_profile_data='{"usia": 35}',
                analysis_result='{"skor_risiko": 3}',
            )
        )
        db.commit()

    response = client.post(
        "/login",
        data={"username": "Daniel", "password": "password123"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"


def test_questionnaire_draft_and_final_submission(client, db_session_factory, monkeypatch):
    register(client)
    draft_response = client.post(
        "/api/questionnaire/draft",
        json={"data": {"usia": "35", "jenis_kelamin": "Laki-laki"}, "last_section": 2},
    )
    assert draft_response.status_code == 200
    assert draft_response.json()["saved"] is True

    with db_session_factory() as db:
        draft = db.scalar(select(QuestionnaireDraftDB))
        assert json.loads(draft.draft_data)["usia"] == "35"
        assert draft.last_section == 2

    from app.api.routes import user_portal

    monkeypatch.setattr(user_portal, "analisis_user", lambda _profile: fake_analysis())
    response = client.post("/api/submit-assessment", data=valid_assessment_form())
    assert response.status_code == 200
    assert response.json()["success"] is True

    with db_session_factory() as db:
        assert db.scalar(select(UserProfileDB)) is not None
        assert db.scalar(select(QuestionnaireDraftDB)) is None

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "Halo, new-user" in dashboard.text


def test_dashboard_requires_login(client):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
