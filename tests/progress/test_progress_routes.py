import json
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.progress_tracker import router
from app.database.connection import get_db
from app.database.models.progress import DailyProgressLogDB
from app.database.models.user import UserDB, UserProfileDB
from app.user.dependencies import require_current_user


def test_v1_progress_form_saves_duplicate_meal_plan_items(progress_db_factory):
    db = progress_db_factory()
    user = UserDB(
        username="tester",
        username_normalized="tester",
        email="tester@example.com",
        email_normalized="tester@example.com",
        hashed_password="x",
        role="user",
    )
    db.add(user)
    db.flush()
    profile = {"berat_badan": 70, "tinggi_badan": 170, "usia": 30, "jenis_kelamin": "Laki-laki"}
    analysis = {
        "target_kalori": 1800,
        "target_karbo": 225,
        "target_protein": 90,
        "target_lemak": 60,
        "tdee_mifflin": 2200,
        "meal_plan": [{"waktu": "Makan Siang", "items": [{"nama": "Nasi merah", "kalori": 200, "karbo": 40, "protein": 4, "lemak": 1}]}],
    }
    db.add(UserProfileDB(user_id=user.id, full_profile_data=json.dumps(profile), analysis_result=json.dumps(analysis)))
    db.commit()
    db.refresh(user)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_current_user] = lambda: user
    client = TestClient(app)

    page = client.get("/progress")
    assert page.status_code == 200
    assert "Simpan Catatan Harian" in page.text
    assert "meal-count-plus" in page.text

    response = client.post(
        "/progress/log",
        data={
            "tanggal": date.today().isoformat(),
            "selected_meal_item_counts": json.dumps({"mp:0:0": 2}),
            "selected_database_food_ids": "[]",
            "activity_name": "",
            "activity_type": "",
            "duration_minutes": "0",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    row = db.query(DailyProgressLogDB).one()
    assert row.actual_kalori == 400.0
    assert json.loads(row.selected_meal_indices) == ["mp:0:0", "mp:0:0"]
    db.close()
