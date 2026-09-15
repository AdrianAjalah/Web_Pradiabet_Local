"""Pending chatbot actions and confirmed execution boundary."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.database.models.progress import DailyProgressLogDB
from app.database.models.user import UserProfileDB
from app.services.common_utils import json_loads, safe_float, today
from app.services.food_service import food_public_payload, get_food_by_id, search_tracker_foods
from app.services.progress_service import (
    baseline_calories_out,
    estimate_bmr,
    get_log_foods,
    log_selected_meal_ids,
    meal_plan_totals,
    selected_database_foods,
    selected_meal_item_totals,
    serialize_log_foods,
)
from app.user.action_service import UserActionError, UserProgramActionService

KG_PER_KCAL = 7700.0


class PendingActionError(ValueError):
    pass


class ChatbotActionError(ValueError):
    pass


class PendingActionStore:
    def __init__(
        self,
        ttl_seconds: int = 600,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.now_factory = now_factory or (lambda: datetime.now(timezone.utc))
        self._items: dict[tuple[int, str], dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        action = dict(payload)
        action["id"] = uuid.uuid4().hex
        action["created_at"] = self.now_factory()
        with self._lock:
            self._items[(user_id, action["id"])] = action
        return dict(action)

    def get(self, user_id: int, action_id: str) -> dict[str, Any]:
        with self._lock:
            action = self._items.get((user_id, action_id))
            if action is None:
                raise PendingActionError("Tindakan tidak ditemukan atau bukan milik akun ini.")
            created_at = action.get("created_at")
            if not isinstance(created_at, datetime) or self.now_factory() - created_at > timedelta(seconds=self.ttl_seconds):
                self._items.pop((user_id, action_id), None)
                raise PendingActionError("Konfirmasi tindakan sudah kedaluwarsa.")
            return dict(action)

    def latest(self, user_id: int) -> dict[str, Any]:
        now = self.now_factory()
        with self._lock:
            valid: list[dict[str, Any]] = []
            expired_keys: list[tuple[int, str]] = []
            for key, action in self._items.items():
                if key[0] != user_id:
                    continue
                created_at = action.get("created_at")
                if not isinstance(created_at, datetime) or now - created_at > timedelta(seconds=self.ttl_seconds):
                    expired_keys.append(key)
                    continue
                valid.append(action)
            for key in expired_keys:
                self._items.pop(key, None)
            if not valid:
                raise PendingActionError("Tidak ada tindakan yang menunggu konfirmasi.")
            latest_action = max(valid, key=lambda item: item["created_at"])
            return dict(latest_action)

    def pop(self, user_id: int, action_id: str) -> dict[str, Any]:
        action = self.get(user_id, action_id)
        with self._lock:
            self._items.pop((user_id, action_id), None)
        return action

    def cancel(self, user_id: int, action_id: str) -> None:
        self.get(user_id, action_id)
        with self._lock:
            self._items.pop((user_id, action_id), None)

    def clear_user(self, user_id: int) -> None:
        with self._lock:
            keys = [key for key in self._items if key[0] == user_id]
            for key in keys:
                self._items.pop(key, None)


def build_pending_action(plan: dict[str, Any]) -> dict[str, Any]:
    action_type = plan["type"]
    if action_type == "add_food":
        groups: list[dict[str, Any]] = []
        for item in plan.get("items") or []:
            candidates = search_tracker_foods(str(item.get("query") or ""), limit=5)
            if not candidates:
                raise ChatbotActionError(
                    f"Makanan '{item.get('query')}' tidak ditemukan di dataset PrediBeat."
                )
            normalized_query = str(item.get("query") or "").strip().casefold()
            exact = [c for c in candidates if str(c.get("nama") or "").strip().casefold() == normalized_query]
            ordered = exact + [c for c in candidates if c not in exact]
            groups.append({
                "query": item.get("query"),
                "quantity": max(1, min(int(item.get("quantity") or 1), 20)),
                "candidates": ordered,
                "selected_food_id": str(ordered[0]["id"]),
            })
        return {
            "type": "add_food",
            "title": "Tambahkan ke Progress Tracker?",
            "message": "Makanan berikut akan langsung ditambahkan ke catatan hari ini tanpa menghapus catatan yang sudah ada.",
            "confirm_label": "Tambahkan ke Tracker",
            "groups": groups,
        }

    if action_type == "change_diet":
        diet_id = plan["diet_id"]
        label = "Low Carbohydrate" if diet_id == "rendah_karbo" else "Mediterranean"
        return {
            "type": action_type,
            "diet_id": diet_id,
            "diet_label": label,
            "title": "Ganti Program Diet?",
            "message": (
                f"Program diet akan diganti menjadi {label}. Seluruh meal plan aktif akan otomatis "
                "diganti sesuai target dan aturan diet baru."
            ),
            "confirm_label": "Ganti Diet & Buat Meal Plan Baru",
        }

    if action_type == "deactivate_diet":
        return {
            "type": action_type,
            "title": "Nonaktifkan Program Diet?",
            "message": (
                "Diet aktif akan dinonaktifkan dan seluruh meal plan akan otomatis diganti "
                "dengan pola makan seimbang bawaan PrediBeat."
            ),
            "confirm_label": "Nonaktifkan & Buat Meal Plan Seimbang",
        }

    if action_type == "regenerate_meal_plan":
        return {
            "type": action_type,
            "title": "Generate Ulang Meal Plan?",
            "message": "Seluruh meal plan aktif akan diganti dengan menu baru. Menu lama tidak digunakan lagi.",
            "confirm_label": "Generate Ulang Meal Plan",
        }

    raise ChatbotActionError("Jenis tindakan tidak didukung.")


class ChatbotActionExecutor:
    def __init__(self, db: Session):
        self.db = db

    def execute(
        self,
        *,
        user_id: int,
        action: dict[str, Any],
        selections: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        action_type = action.get("type")
        if action_type == "add_food":
            return self._add_foods(user_id, action, selections or [])
        program = UserProgramActionService(self.db)
        try:
            if action_type == "replace_meal_plan":
                from app.services.chatbot_personal_service import PersonalChatService
                result = PersonalChatService(self.db).apply(user_id, action)
                self.db.commit()
                return result
            if action_type == "change_diet":
                result = program.activate_diet(user_id, str(action.get("diet_id") or ""))
                self.db.commit()
                return {
                    "message": f"Diet berhasil diubah menjadi {action.get('diet_label')}. Meal plan baru sudah dibuat.",
                    "redirect": "/dashboard",
                    **result,
                }
            if action_type == "deactivate_diet":
                result = program.deactivate_diet(user_id)
                self.db.commit()
                return {
                    "message": "Diet berhasil dinonaktifkan dan meal plan seimbang baru sudah dibuat.",
                    "redirect": "/dashboard",
                    **result,
                }
            if action_type == "regenerate_meal_plan":
                result = program.regenerate_meal_plan(user_id)
                self.db.commit()
                return {
                    "message": "Meal plan berhasil dibuat ulang.",
                    "redirect": "/dashboard",
                    **result,
                }
        except UserActionError as exc:
            self.db.rollback()
            raise ChatbotActionError(str(exc)) from exc
        raise ChatbotActionError("Jenis tindakan tidak didukung.")

    def _validated_food_ids(
        self,
        action: dict[str, Any],
        selections: list[dict[str, Any]],
    ) -> list[str]:
        selection_map = {
            str(item.get("group_index")): item for item in selections if isinstance(item, dict)
        }
        food_ids: list[str] = []
        for index, group in enumerate(action.get("groups") or []):
            selected = selection_map.get(str(index), {})
            food_id = str(selected.get("food_id") or group.get("selected_food_id") or "")
            allowed = {str(c.get("id")) for c in group.get("candidates") or []}
            if food_id not in allowed:
                raise ChatbotActionError("Pilihan makanan tidak valid.")
            try:
                quantity = int(selected.get("quantity") or group.get("quantity") or 1)
            except (TypeError, ValueError) as exc:
                raise ChatbotActionError("Jumlah makanan tidak valid.") from exc
            quantity = max(1, min(quantity, 20))
            food_ids.extend([food_id] * quantity)
        if not food_ids:
            raise ChatbotActionError("Tidak ada makanan yang dipilih.")
        return food_ids

    def _add_foods(
        self,
        user_id: int,
        action: dict[str, Any],
        selections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        new_food_ids = self._validated_food_ids(action, selections)
        profile_row = self.db.query(UserProfileDB).filter(UserProfileDB.user_id == user_id).first()
        if profile_row is None:
            raise ChatbotActionError("Profil belum tersedia.")
        profile_data = json_loads(profile_row.full_profile_data, {})
        analysis = json_loads(profile_row.analysis_result, {})
        entry_date = today()
        log = (
            self.db.query(DailyProgressLogDB)
            .filter(DailyProgressLogDB.user_id == user_id, DailyProgressLogDB.tanggal == entry_date)
            .first()
        )
        if log is None:
            log = DailyProgressLogDB(user_id=user_id, tanggal=entry_date)
            self.db.add(log)

        existing_foods = get_log_foods(log)
        existing_db_ids = [
            str(food.get("id"))
            for food in existing_foods
            if food.get("source") == "database" and food.get("id") is not None
        ]
        all_db_ids = existing_db_ids + new_food_ids
        selected_meal_ids = log_selected_meal_ids(log)
        meal_plan = analysis.get("meal_plan") or []
        meal_total = meal_plan_totals(meal_plan)
        selected_meal_total, selected_meal_foods = selected_meal_item_totals(meal_plan, selected_meal_ids)
        selected_db_total, selected_db_foods = selected_database_foods(all_db_ids)

        actual_kalori = round(selected_meal_total["kalori"] + selected_db_total["kalori"], 1)
        actual_karbo = round(selected_meal_total["karbo"] + selected_db_total["karbo"], 1)
        actual_protein = round(selected_meal_total["protein"] + selected_db_total["protein"], 1)
        actual_lemak = round(selected_meal_total["lemak"] + selected_db_total["lemak"], 1)

        adherence = 0.0
        if meal_total["kalori"] > 0:
            adherence = min(100.0, round((selected_meal_total["kalori"] / meal_total["kalori"]) * 100.0, 1))

        weight_kg = safe_float(profile_data.get("berat_badan"), 0.0) or 0.0
        bmr = estimate_bmr(profile_data)
        baseline_out = baseline_calories_out(profile_data)
        activity_calories = float(log.activity_calories or 0)
        calories_out = round(baseline_out + activity_calories, 1)
        deficit = round(calories_out - actual_kalori, 1)

        log.weight_kg = weight_kg
        log.target_kalori = safe_float(analysis.get("target_kalori"), 0.0) or 0.0
        log.target_karbo = safe_float(analysis.get("target_karbo"), 0.0) or 0.0
        log.target_protein = safe_float(analysis.get("target_protein"), 0.0) or 0.0
        log.target_lemak = safe_float(analysis.get("target_lemak"), 0.0) or 0.0
        log.tdee_reference = safe_float(analysis.get("tdee_mifflin"), 0.0) or 0.0
        log.bmr_estimated = bmr
        log.baseline_calories_out = baseline_out
        log.meal_plan_kalori = meal_total["kalori"]
        log.meal_plan_karbo = meal_total["karbo"]
        log.meal_plan_protein = meal_total["protein"]
        log.meal_plan_lemak = meal_total["lemak"]
        log.selected_meal_indices = json.dumps(selected_meal_ids, ensure_ascii=False)
        log.meal_plan_adherence_percent = adherence
        log.actual_kalori = actual_kalori
        log.actual_karbo = actual_karbo
        log.actual_protein = actual_protein
        log.actual_lemak = actual_lemak
        log.calories_out = calories_out
        log.deficit_calories = deficit
        log.estimated_weight_change_kg = round(-deficit / KG_PER_KCAL, 3)
        log.notes = serialize_log_foods(selected_meal_foods + selected_db_foods)
        log.updated_at = datetime.now(timezone.utc)
        self.db.commit()

        names: dict[str, int] = {}
        for food_id in new_food_ids:
            food = get_food_by_id(food_id)
            if not food:
                continue
            name = str(food.get("nama") or "Makanan")
            names[name] = names.get(name, 0) + 1
        label = ", ".join(f"{name} × {qty}" for name, qty in names.items())
        return {
            "message": f"Berhasil ditambahkan ke Progress Tracker hari ini: {label}.",
            "redirect": "/progress",
            "actual_kalori": actual_kalori,
            "foods_added": names,
        }
