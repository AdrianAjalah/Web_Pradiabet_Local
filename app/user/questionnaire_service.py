"""Validation and persistence for questionnaire drafts and completed assessments."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.user import (
    HealthAssessmentHistoryDB,
    QuestionnaireDraftDB,
    UserProfileDB,
)
from app.user.schemas import ProfilUser


class QuestionnaireValidationError(ValueError):
    def __init__(self, message: str, missing_fields: list[str] | None = None):
        super().__init__(message)
        self.missing_fields = missing_fields or []


_REQUIRED_FIELDS = (
    "usia",
    "jenis_kelamin",
    "berat_badan",
    "tinggi_badan",
    "frekuensi_minum_manis",
    "porsi_nasi_per_hari",
    "frekuensi_olahraga",
    "durasi_duduk_rebahan",
    "durasi_tidur",
    "riwayat_keluarga_diabetes",
)


def _clean_optional(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _to_float(value: Any, field_name: str, *, optional: bool = False) -> float | None:
    text = str(value or "").strip()
    if optional and not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError) as exc:
        raise QuestionnaireValidationError(f"Nilai {field_name} tidak valid.", [field_name]) from exc
    if number <= 0:
        raise QuestionnaireValidationError(f"Nilai {field_name} harus lebih dari 0.", [field_name])
    return number


def _getlist(form: Mapping[str, Any], key: str) -> list[str]:
    getter = getattr(form, "getlist", None)
    if callable(getter):
        values = getter(key)
    else:
        value = form.get(key, [])
        values = value if isinstance(value, list) else [value]
    return [str(value).strip() for value in values if str(value).strip()]


def normalize_time_pattern(value: Any) -> str:
    text = str(value or "normal").strip().casefold()
    if text in {"if", "intermittent", "intermittent fasting", "intermittent_fasting", "puasa"}:
        return "intermittent_fasting"
    return "normal"


def build_profile_from_form(form: Mapping[str, Any]) -> ProfilUser:
    missing = [field for field in _REQUIRED_FIELDS if not str(form.get(field, "")).strip()]
    if missing:
        raise QuestionnaireValidationError(
            "Lengkapi seluruh pertanyaan wajib sebelum melihat hasil analisis.", missing
        )

    frekuensi_makan = str(form.get("frekuensi_makan") or "3x").strip()
    pola_waktu_makan = normalize_time_pattern(form.get("pola_waktu_makan"))
    waktu_makan = _getlist(form, "waktu_makan")
    if not waktu_makan:
        if frekuensi_makan == "2x":
            waktu_makan = ["Siang", "Malam"]
        elif pola_waktu_makan == "intermittent_fasting":
            waktu_makan = ["Siang", "Sore", "Malam"]
        else:
            waktu_makan = ["Pagi", "Siang", "Malam"]

    try:
        usia = int(str(form.get("usia") or "0"))
    except ValueError as exc:
        raise QuestionnaireValidationError("Usia tidak valid.", ["usia"]) from exc
    if usia <= 0:
        raise QuestionnaireValidationError("Usia harus lebih dari 0.", ["usia"])

    profile = ProfilUser(
        usia=usia,
        jenis_kelamin=str(form.get("jenis_kelamin") or "").strip(),
        berat_badan=float(_to_float(form.get("berat_badan"), "berat_badan")),
        tinggi_badan=float(_to_float(form.get("tinggi_badan"), "tinggi_badan")),
        lingkar_pinggang=_to_float(form.get("lingkar_pinggang"), "lingkar_pinggang", optional=True),
        frekuensi_minum_manis=str(form.get("frekuensi_minum_manis") or "").strip(),
        porsi_nasi_per_hari=str(form.get("porsi_nasi_per_hari") or "").strip(),
        frekuensi_olahraga=str(form.get("frekuensi_olahraga") or "").strip(),
        durasi_duduk_rebahan=str(form.get("durasi_duduk_rebahan") or "").strip(),
        durasi_tidur=str(form.get("durasi_tidur") or "").strip(),
        riwayat_keluarga_diabetes=str(form.get("riwayat_keluarga_diabetes") or "").casefold()
        == "true",
        gejala_klasik=_getlist(form, "gejala_klasik"),
        pantangan_alergi=_clean_optional(form.get("pantangan_alergi")),
        penyakit_lain_obat=_clean_optional(form.get("penyakit_lain_obat")),
        hasil_lab=_clean_optional(form.get("hasil_lab")),
        frekuensi_makan=frekuensi_makan,
        waktu_makan=waktu_makan,
        active_diet=_clean_optional(form.get("active_diet")),
        pola_waktu_makan=pola_waktu_makan,
        pola_puasa=_clean_optional(form.get("pola_puasa")),
        jam_makan_mulai=_clean_optional(form.get("jam_makan_mulai")),
        jam_makan_selesai=_clean_optional(form.get("jam_makan_selesai")),
    )
    return profile


def save_draft(
    db: Session,
    user_id: int,
    payload: Mapping[str, Any],
    *,
    last_section: int,
) -> QuestionnaireDraftDB:
    safe_section = min(4, max(1, int(last_section or 1)))
    existing = db.scalar(
        select(QuestionnaireDraftDB).where(QuestionnaireDraftDB.user_id == user_id)
    )
    serialized = json.dumps(dict(payload), ensure_ascii=False)
    if existing:
        existing.draft_data = serialized
        existing.last_section = safe_section
        existing.updated_at = datetime.now(timezone.utc)
        draft = existing
    else:
        draft = QuestionnaireDraftDB(
            user_id=user_id,
            draft_data=serialized,
            last_section=safe_section,
        )
        db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def save_completed_assessment(
    db: Session,
    user_id: int,
    *,
    profile_data: Mapping[str, Any],
    analysis_data: Mapping[str, Any],
) -> UserProfileDB:
    profile_json = json.dumps(dict(profile_data), ensure_ascii=False)
    analysis_json = json.dumps(dict(analysis_data), ensure_ascii=False)
    existing = db.scalar(select(UserProfileDB).where(UserProfileDB.user_id == user_id))
    if existing:
        db.add(
            HealthAssessmentHistoryDB(
                user_id=user_id,
                full_profile_data=existing.full_profile_data,
                analysis_result=existing.analysis_result,
            )
        )
        existing.full_profile_data = profile_json
        existing.analysis_result = analysis_json
        existing.questionnaire_completed_at = datetime.now(timezone.utc)
        existing.updated_at = datetime.now(timezone.utc)
        profile = existing
    else:
        profile = UserProfileDB(
            user_id=user_id,
            full_profile_data=profile_json,
            analysis_result=analysis_json,
        )
        db.add(profile)

    draft = db.scalar(
        select(QuestionnaireDraftDB).where(QuestionnaireDraftDB.user_id == user_id)
    )
    if draft:
        db.delete(draft)
    db.commit()
    db.refresh(profile)
    return profile
