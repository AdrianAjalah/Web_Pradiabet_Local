from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.database.models.user import (
    HealthAssessmentHistoryDB,
    QuestionnaireDraftDB,
    UserDB,
    UserProfileDB,
)
from app.user.questionnaire_service import (
    QuestionnaireValidationError,
    build_profile_from_form,
    save_completed_assessment,
    save_draft,
)
from app.user.security import hash_password


class FakeForm(dict):
    def getlist(self, key: str):
        value = self.get(key, [])
        return value if isinstance(value, list) else [value]


def valid_form() -> FakeForm:
    return FakeForm(
        usia="35",
        jenis_kelamin="Laki-laki",
        berat_badan="75",
        tinggi_badan="170",
        lingkar_pinggang="",
        frekuensi_minum_manis="1-3x per minggu",
        porsi_nasi_per_hari="2 porsi",
        frekuensi_olahraga="1-2x per minggu",
        durasi_duduk_rebahan="4-6 jam",
        durasi_tidur="7-8 jam",
        riwayat_keluarga_diabetes="false",
        gejala_klasik=["Tidak ada gejala"],
        pantangan_alergi="",
        penyakit_lain_obat="",
        hasil_lab="",
        frekuensi_makan="3x",
        waktu_makan=["Pagi", "Siang", "Malam"],
        pola_waktu_makan="normal",
        pola_puasa="",
        jam_makan_mulai="",
        jam_makan_selesai="",
    )


def make_user(db):
    user = UserDB(
        username="member",
        username_normalized="member",
        email="member@example.com",
        email_normalized="member@example.com",
        hashed_password=hash_password("password123"),
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_build_profile_validates_required_fields_and_allows_optional_blanks():
    form = valid_form()
    profile = build_profile_from_form(form)
    assert profile.usia == 35
    assert profile.lingkar_pinggang is None
    assert profile.pantangan_alergi is None
    assert profile.hasil_lab is None

    form["tinggi_badan"] = ""
    with pytest.raises(QuestionnaireValidationError) as exc:
        build_profile_from_form(form)
    assert "tinggi_badan" in exc.value.missing_fields


def test_save_draft_upserts_single_record(db_session_factory):
    with db_session_factory() as db:
        user = make_user(db)
        save_draft(db, user.id, {"usia": "30"}, last_section=2)
        save_draft(db, user.id, {"usia": "31"}, last_section=3)

        rows = db.scalars(select(QuestionnaireDraftDB)).all()
        assert len(rows) == 1
        assert json.loads(rows[0].draft_data)["usia"] == "31"
        assert rows[0].last_section == 3


def test_completed_assessment_archives_previous_profile_and_clears_draft(db_session_factory):
    with db_session_factory() as db:
        user = make_user(db)
        db.add(
            UserProfileDB(
                user_id=user.id,
                full_profile_data='{"usia": 30}',
                analysis_result='{"skor_risiko": 2}',
            )
        )
        db.add(
            QuestionnaireDraftDB(
                user_id=user.id,
                draft_data='{"usia": 31}',
                last_section=4,
            )
        )
        db.commit()

        save_completed_assessment(
            db,
            user.id,
            profile_data={"usia": 31, "jenis_kelamin": "Laki-laki"},
            analysis_data={"skor_risiko": 3},
        )

        profile = db.scalar(select(UserProfileDB).where(UserProfileDB.user_id == user.id))
        history = db.scalars(select(HealthAssessmentHistoryDB)).all()
        draft = db.scalar(select(QuestionnaireDraftDB).where(QuestionnaireDraftDB.user_id == user.id))
        assert json.loads(profile.full_profile_data)["usia"] == 31
        assert len(history) == 1
        assert json.loads(history[0].full_profile_data)["usia"] == 30
        assert draft is None
