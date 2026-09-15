from __future__ import annotations

import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.database.models.user import UserDB, UserProfileDB
from app.user.action_service import UserActionError, UserProgramActionService


def _seed(factory):
    with factory() as db:
        user = UserDB(
            username="action-user",
            username_normalized="action-user",
            email="action@example.com",
            email_normalized="action@example.com",
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
                    "berat_badan": 75,
                    "tinggi_badan": 170,
                    "frekuensi_makan": "3x",
                    "waktu_makan": ["Pagi", "Siang", "Malam"],
                    "pola_waktu_makan": "normal",
                    "active_diet": "mediterania",
                }),
                analysis_result=json.dumps({
                    "target_kalori": 1800,
                    "target_karbo": 200,
                    "target_protein": 100,
                    "target_lemak": 67,
                    "kategori_risiko": "Risiko Sedang",
                    "frekuensi_makan": "3x",
                    "waktu_makan": ["Pagi", "Siang", "Malam"],
                    "meal_plan": [{"waktu": "Pagi", "items": [{"nama": "Menu lama"}]}],
                    "active_diet": "mediterania",
                }),
            )
        )
        db.commit()
        return user.id


def _fake_analysis(profile):
    return SimpleNamespace(model_dump=lambda: {
        "target_kalori": 1700,
        "target_karbo": 130,
        "target_protein": 110,
        "target_lemak": 70,
        "kategori_risiko": "Risiko Sedang",
        "frekuensi_makan": "3x",
        "waktu_makan": ["Pagi", "Siang", "Malam"],
        "meal_plan": [{"waktu": "Pagi", "items": [{"nama": f"Menu {profile.active_diet or 'seimbang'}"}]}],
        "active_diet": profile.active_diet,
        "active_diet_label": profile.active_diet,
        "catatan_pola_makan": [],
    })


def test_activate_diet_recalculates_and_replaces_meal_plan(db_session_factory, monkeypatch):
    user_id = _seed(db_session_factory)
    monkeypatch.setattr("app.user.action_service.analisis_user", _fake_analysis)

    with db_session_factory() as db:
        result = UserProgramActionService(db).activate_diet(user_id, "rendah_karbo")
        db.commit()
        row = db.query(UserProfileDB).filter_by(user_id=user_id).one()
        profile = json.loads(row.full_profile_data)
        analysis = json.loads(row.analysis_result)

    assert result["active_diet"] == "rendah_karbo"
    assert profile["active_diet"] == "rendah_karbo"
    assert analysis["meal_plan"][0]["items"][0]["nama"] == "Menu rendah_karbo"


def test_deactivate_diet_recalculates_balanced_meal_plan(db_session_factory, monkeypatch):
    user_id = _seed(db_session_factory)
    monkeypatch.setattr("app.user.action_service.analisis_user", _fake_analysis)

    with db_session_factory() as db:
        result = UserProgramActionService(db).deactivate_diet(user_id)
        db.commit()

    assert result["active_diet"] is None
    assert result["meal_plan"][0]["items"][0]["nama"] == "Menu seimbang"


def test_activate_unsupported_diet_is_rejected(db_session_factory):
    user_id = _seed(db_session_factory)
    with db_session_factory() as db:
        with pytest.raises(UserActionError, match="belum dapat diaktifkan"):
            UserProgramActionService(db).activate_diet(user_id, "keto")


def test_first_daily_check_stamps_existing_plan_without_replacing_it(db_session_factory):
    user_id = _seed(db_session_factory)
    current = date(2026, 9, 15)

    def must_not_generate(**kwargs):
        raise AssertionError("existing plan must be preserved on migration day")

    with db_session_factory() as db:
        result = UserProgramActionService(db, meal_plan_generator=must_not_generate).ensure_daily_meal_plan(
            user_id, current_date=current
        )
        db.commit()
        analysis = json.loads(db.query(UserProfileDB).filter_by(user_id=user_id).one().analysis_result)

    assert result["changed"] is False
    assert analysis["meal_plan_date"] == "2026-09-15"
    assert analysis["meal_plan"][0]["items"][0]["nama"] == "Menu lama"


def test_daily_check_replaces_plan_only_once_on_next_day(db_session_factory):
    user_id = _seed(db_session_factory)
    first_day = date(2026, 9, 15)
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        return ([{"waktu": "Pagi", "items": [{"nama": f"Menu harian {len(calls)}"}]}], {})

    with db_session_factory() as db:
        service = UserProgramActionService(db, meal_plan_generator=generate)
        service.ensure_daily_meal_plan(user_id, current_date=first_day)
        service.ensure_daily_meal_plan(user_id, current_date=first_day + timedelta(days=1))
        repeated = service.ensure_daily_meal_plan(user_id, current_date=first_day + timedelta(days=1))
        db.commit()
        analysis = json.loads(db.query(UserProfileDB).filter_by(user_id=user_id).one().analysis_result)

    assert len(calls) == 1
    assert repeated["changed"] is False
    assert analysis["meal_plan_date"] == "2026-09-16"
    assert analysis["meal_plan"][0]["items"][0]["nama"] == "Menu harian 1"
