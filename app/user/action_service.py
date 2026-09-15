"""Shared user program mutations used by web routes and chatbot tools."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.database.models.user import UserProfileDB
from app.services.common_utils import today
from app.user.assessment import (
    _catatan_validasi_meal_plan,
    analisis_user,
    generate_meal_plan_tervalidasi,
    get_diet_info,
)
from app.user.diet_service import is_supported_diet, normalize_diet_id
from app.user.schemas import ProfilUser


class UserActionError(ValueError):
    """Raised when a requested program mutation is not valid."""


class UserProgramActionService:
    def __init__(
        self,
        db: Session,
        *,
        analyzer: Callable[[ProfilUser], Any] | None = None,
        meal_plan_generator: Callable[..., Any] | None = None,
    ):
        self.db = db
        self.analyzer = analyzer or analisis_user
        self.meal_plan_generator = meal_plan_generator or generate_meal_plan_tervalidasi

    def _row(self, user_id: int, *, for_update: bool = False) -> UserProfileDB:
        query = self.db.query(UserProfileDB).filter(UserProfileDB.user_id == user_id)
        if for_update:
            query = query.with_for_update()
        row = query.first()
        if row is None:
            raise UserActionError("Profil belum tersedia.")
        return row

    @staticmethod
    def _decode(row: UserProfileDB) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            return json.loads(row.full_profile_data), json.loads(row.analysis_result)
        except (TypeError, json.JSONDecodeError) as exc:
            raise UserActionError("Data profil atau analisis tidak valid.") from exc

    @staticmethod
    def _save(row: UserProfileDB, profile_data: dict[str, Any], analysis: dict[str, Any]) -> None:
        row.full_profile_data = json.dumps(profile_data, ensure_ascii=False)
        row.analysis_result = json.dumps(analysis, ensure_ascii=False)
        row.updated_at = datetime.now(timezone.utc)

    def _recalculate(self, row: UserProfileDB, profile_data: dict[str, Any]) -> dict[str, Any]:
        result = self.analyzer(ProfilUser(**profile_data)).model_dump()
        result["meal_plan_date"] = today().isoformat()
        self._save(row, profile_data, result)
        self.db.flush()
        return result

    def activate_diet(self, user_id: int, diet_id: str) -> dict[str, Any]:
        normalized = normalize_diet_id(diet_id)
        if not normalized or not is_supported_diet(normalized):
            raise UserActionError("Diet ini masih Coming Soon dan belum dapat diaktifkan.")
        row = self._row(user_id)
        profile_data, _ = self._decode(row)
        profile_data["active_diet"] = normalized
        profile_data["diet_updated_at"] = datetime.now(timezone.utc).isoformat()
        result = self._recalculate(row, profile_data)
        return {
            "active_diet": normalized,
            "active_diet_label": result.get("active_diet_label") or normalized,
            "meal_plan": result.get("meal_plan") or [],
        }

    def deactivate_diet(self, user_id: int) -> dict[str, Any]:
        row = self._row(user_id)
        profile_data, _ = self._decode(row)
        profile_data["active_diet"] = None
        profile_data["diet_updated_at"] = datetime.now(timezone.utc).isoformat()
        result = self._recalculate(row, profile_data)
        return {
            "active_diet": None,
            "active_diet_label": None,
            "meal_plan": result.get("meal_plan") or [],
        }

    @staticmethod
    def _plan_signature(plan: list[dict[str, Any]]) -> tuple[str, ...]:
        return tuple(
            str(item.get("id") or item.get("kode") or item.get("nama") or "").casefold()
            for meal in (plan or [])
            for item in (meal.get("items") or [])
        )

    def regenerate_meal_plan(
        self,
        user_id: int,
        *,
        preview: bool = False,
        avoid_current: bool = False,
    ) -> dict[str, Any]:
        row = self._row(user_id)
        profile_data, analysis = self._decode(row)
        if "target_kalori" not in analysis or "kategori_risiko" not in analysis:
            raise UserActionError("Target nutrisi belum tersedia.")

        active_diet = normalize_diet_id(
            analysis.get("active_diet") or profile_data.get("active_diet")
        )
        if active_diet not in {"mediterania", "rendah_karbo"}:
            active_diet = None

        generator_args = {
            "target_kalori": analysis["target_kalori"],
            "target_karbo": analysis.get("target_karbo", 0),
            "target_protein": analysis.get("target_protein", 0),
            "target_lemak": analysis.get("target_lemak", 0),
            "frekuensi_makan": analysis.get(
                "frekuensi_makan", profile_data.get("frekuensi_makan", "3x")
            ),
            "waktu_makan": analysis.get(
                "waktu_makan", profile_data.get("waktu_makan", ["Pagi", "Siang", "Malam"])
            ),
            "kategori_risiko": analysis["kategori_risiko"],
            "pantangan": profile_data.get("pantangan_alergi"),
            "pola_waktu_makan": profile_data.get("pola_waktu_makan", "normal"),
            "pola_puasa": profile_data.get("pola_puasa"),
            "jam_makan_mulai": profile_data.get("jam_makan_mulai"),
            "jam_makan_selesai": profile_data.get("jam_makan_selesai"),
            "active_diet": active_diet,
        }
        current_signature = self._plan_signature(analysis.get("meal_plan") or [])
        new_plan: list[dict[str, Any]] = []
        validation: dict[str, Any] = {}
        for _ in range(5 if avoid_current and current_signature else 1):
            new_plan, validation = self.meal_plan_generator(**generator_args)
            if not avoid_current or self._plan_signature(new_plan) != current_signature:
                break
        if preview:
            return {"meal_plan": new_plan, "validation": validation}
        analysis["meal_plan"] = new_plan
        analysis["meal_plan_date"] = today().isoformat()
        notes = [
            note
            for note in (analysis.get("catatan_pola_makan") or [])
            if not str(note).startswith("Validasi meal plan:")
        ]
        if validation:
            notes.append(_catatan_validasi_meal_plan(validation))
        analysis["catatan_pola_makan"] = notes
        analysis["active_diet"] = active_diet
        info = get_diet_info(active_diet)
        analysis["active_diet_label"] = info.get("nama") if info else None
        self._save(row, profile_data, analysis)
        self.db.flush()
        return {
            "active_diet": active_diet,
            "active_diet_label": analysis.get("active_diet_label"),
            "meal_plan": new_plan,
        }

    def ensure_daily_meal_plan(
        self,
        user_id: int,
        *,
        current_date: date | None = None,
    ) -> dict[str, Any]:
        """Rotate a user's plan once when the local calendar day changes."""
        plan_date = current_date or today()
        marker = plan_date.isoformat()
        row = self._row(user_id, for_update=True)
        profile_data, analysis = self._decode(row)

        if analysis.get("meal_plan_date") == marker:
            return {"changed": False, "date": marker, "meal_plan": analysis.get("meal_plan") or []}

        # Existing profiles predate this feature. Stamp their current plan so an
        # application update does not unexpectedly replace today's menu.
        if not analysis.get("meal_plan_date"):
            analysis["meal_plan_date"] = marker
            self._save(row, profile_data, analysis)
            self.db.flush()
            return {"changed": False, "date": marker, "meal_plan": analysis.get("meal_plan") or []}

        result = self.regenerate_meal_plan(user_id, avoid_current=True)
        # Tests and administrative backfills may request a specific date.
        if plan_date != today():
            row = self._row(user_id)
            profile_data, analysis = self._decode(row)
            analysis["meal_plan_date"] = marker
            self._save(row, profile_data, analysis)
            self.db.flush()
        return {"changed": True, "date": marker, "meal_plan": result.get("meal_plan") or []}
