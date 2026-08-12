from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.models.progress import DailyProgressLogDB
from app.database.models.user import UserDB, UserProfileDB
from app.user.dependencies import require_current_user
from app.services.activity_service import calculate_activity_calories, find_activity_met, load_activities
from app.services.common_utils import json_loads, monday_of_week, parse_date, safe_float, today
from app.services.food_service import search_tracker_foods
from app.services.health_score_service import calculate_weekly_health_score
from app.services.progress_service import (
    baseline_calories_out,
    build_week_view,
    daily_weight_change_label,
    date_nav_payload,
    diet_status_message,
    estimate_bmr,
    log_selected_meal_ids,
    macro_validation_messages,
    meal_plan_item_options,
    meal_plan_totals,
    selected_database_foods,
    selected_meal_item_totals,
    serialize_log_foods,
    split_saved_foods,
    summarize_week,
)
from app.services.weekly_insight_service import build_weekly_insight

router = APIRouter(prefix="/progress", tags=["progress-tracker"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[3] / "templates"))

KG_PER_KCAL = 7700.0




def get_profile_analysis(db: Session, user_id: int) -> tuple[dict[str, Any], dict[str, Any], UserProfileDB]:
    row = db.query(UserProfileDB).filter(UserProfileDB.user_id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profil belum tersedia. Isi kuisioner dulu.")
    profile_data = json_loads(row.full_profile_data, {})
    analysis = json_loads(row.analysis_result, {})
    return profile_data, analysis, row


def get_dashboard_progress_context(db: Session, user_id: int) -> dict[str, Any]:
    """Return the same weekly score/insight used by the V1 tracker dashboard."""
    current = today()
    start = monday_of_week(current)
    end = start + timedelta(days=6)
    logs = (
        db.query(DailyProgressLogDB)
        .filter(DailyProgressLogDB.user_id == user_id)
        .filter(DailyProgressLogDB.tanggal >= start)
        .filter(DailyProgressLogDB.tanggal <= end)
        .order_by(DailyProgressLogDB.tanggal.asc())
        .all()
    )
    if not logs:
        return {
            "health_score": None,
            "weekly_insight": None,
            "dashboard_progress_summary": {"days_logged": 0},
            "week_start": start,
            "week_end": end,
        }
    summary = summarize_week(logs)
    return {
        "health_score": calculate_weekly_health_score(logs),
        "weekly_insight": build_weekly_insight(logs),
        "dashboard_progress_summary": summary,
        "week_start": start,
        "week_end": end,
    }


@router.get("/api/search-foods")
async def api_search_foods(
    q: str = "",
    limit: int = 10,
    current_user: UserDB = Depends(require_current_user),
):
    # current_user tetap dipakai sebagai auth guard.
    return {"items": search_tracker_foods(q, limit)}


@router.get("", response_class=HTMLResponse)
async def progress_page(
    request: Request,
    week_start: Optional[str] = None,
    tanggal: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_current_user),
):
    profile_data, analysis, _ = get_profile_analysis(db, current_user.id)

    today_date = today()
    selected_date = parse_date(tanggal, today_date) if tanggal else today_date
    if selected_date > today_date:
        selected_date = today_date

    start = monday_of_week(selected_date)
    if week_start:
        start = parse_date(week_start, start)
    end = start + timedelta(days=6)

    logs = (
        db.query(DailyProgressLogDB)
        .filter(DailyProgressLogDB.user_id == current_user.id)
        .filter(DailyProgressLogDB.tanggal >= start)
        .filter(DailyProgressLogDB.tanggal <= end)
        .order_by(DailyProgressLogDB.tanggal.asc())
        .all()
    )

    meal_plan = analysis.get("meal_plan") or []
    meal_totals = meal_plan_totals(meal_plan)
    bmr = estimate_bmr(profile_data)
    baseline_out = baseline_calories_out(profile_data)
    tdee = safe_float(analysis.get("tdee_mifflin"), 0.0) or 0.0
    profile_weight = safe_float(profile_data.get("berat_badan"), 0.0) or 0.0
    week_days, chart_data = build_week_view(
        start,
        logs,
        safe_float(analysis.get("target_kalori"), 0.0) or 0.0,
        profile_weight,
    )

    selected_log = next((log for log in logs if log.tanggal == selected_date), None)
    previous_log = (
        db.query(DailyProgressLogDB)
        .filter(DailyProgressLogDB.user_id == current_user.id)
        .filter(DailyProgressLogDB.tanggal == selected_date - timedelta(days=1))
        .first()
    )

    selected_meal_ids = log_selected_meal_ids(selected_log)
    saved_meal_foods, saved_db_foods = split_saved_foods(selected_log)
    meal_items = meal_plan_item_options(meal_plan)
    selected_counts = Counter(selected_meal_ids)
    for item in meal_items:
        item["count"] = selected_counts.get(item["id"], 0)
        item["checked"] = item["count"] > 0

    target_kalori_today = safe_float(analysis.get("target_kalori"), 0.0) or 0.0
    selected_activity_calories = round(float(selected_log.activity_calories or 0), 1) if selected_log else 0.0
    selected_calories_out = round(float(selected_log.calories_out or 0), 1) if selected_log else baseline_out
    selected_actual_kalori = round(float(selected_log.actual_kalori or 0), 1) if selected_log else 0.0
    selected_remaining_calories = round(target_kalori_today - selected_actual_kalori, 1)
    selected_deficit = round(float(selected_log.deficit_calories or 0), 1) if selected_log else 0.0

    macro_messages: list[str] = []
    if selected_log:
        macro_messages = macro_validation_messages(
            analysis,
            float(selected_log.actual_kalori or 0),
            float(selected_log.actual_karbo or 0),
            float(selected_log.actual_protein or 0),
            float(selected_log.actual_lemak or 0),
        )

    date_nav = date_nav_payload(selected_date, selected_log)
    today_log = next((log for log in logs if log.tanggal == today_date), None)
    summary = summarize_week(logs)
    weekly_insight = build_weekly_insight(logs)
    health_score = calculate_weekly_health_score(logs)

    return templates.TemplateResponse(
        request=request,
        name="progress_tracker.html",
        context={
            "user": current_user,
            "profile": profile_data,
            "analysis": analysis,
            "meal_plan": meal_plan,
            "meal_items": meal_items,
            "meal_totals": meal_totals,
            "activities": load_activities(),
            "logs": logs,
            "week_days": week_days,
            "chart_data": chart_data,
            "summary": summary,
            "weekly_insight": weekly_insight,
            "health_score": health_score,
            "week_start": start,
            "week_end": end,
            "prev_week": (start - timedelta(days=7)).isoformat(),
            "next_week": (start + timedelta(days=7)).isoformat(),
            "today": today_date.isoformat(),
            "today_log": today_log,
            "selected_log": selected_log,
            "previous_log": previous_log,
            "saved_meal_foods": saved_meal_foods,
            "saved_db_foods": saved_db_foods,
            "saved_db_foods_json": saved_db_foods,
            "selected_activity_calories": selected_activity_calories,
            "selected_calories_out": selected_calories_out,
            "selected_actual_kalori": selected_actual_kalori,
            "selected_remaining_calories": selected_remaining_calories,
            "selected_deficit": selected_deficit,
            "selected_weight_change_text": daily_weight_change_label(selected_deficit) if selected_log else "Belum ada estimasi",
            "macro_messages": macro_messages,
            "diet_status_message": diet_status_message(profile_data, analysis),
            "bmr_estimated": bmr,
            "baseline_calories_out": baseline_out,
            "tdee_reference": tdee,
            **date_nav,
            # Alias field yang masih dipakai template.
            "today_activity_calories": selected_activity_calories,
            "today_calories_out": selected_calories_out,
            "today_actual_kalori": selected_actual_kalori,
            "today_remaining_calories": selected_remaining_calories,
            "tracker_activity_today": selected_activity_calories,
            "tracker_burn_today": selected_calories_out,
        },
    )


@router.post("/log")
async def save_daily_progress(
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_current_user),
):
    form = await request.form()
    profile_data, analysis, _ = get_profile_analysis(db, current_user.id)

    tanggal = parse_date(form.get("tanggal"), today())
    today_date = today()
    min_log_date = today_date - timedelta(days=6)
    if tanggal > today_date:
        raise HTTPException(status_code=400, detail="Log tidak bisa diisi untuk tanggal masa depan.")
    if tanggal < min_log_date:
        raise HTTPException(status_code=400, detail="Catatan hanya dapat diisi untuk hari ini sampai 7 hari terakhir.")

    existing_log = (
        db.query(DailyProgressLogDB)
        .filter(DailyProgressLogDB.user_id == current_user.id)
        .filter(DailyProgressLogDB.tanggal == tanggal)
        .first()
    )
    if existing_log and tanggal < today_date:
        raise HTTPException(status_code=400, detail="Catatan tanggal sebelumnya yang sudah tersimpan tidak dapat diedit.")

    weight_kg = safe_float(profile_data.get("berat_badan"), 0.0) or 0.0

    selected_meal_ids: list[str] = []
    meal_counts = json_loads(form.get("selected_meal_item_counts"), {})
    if isinstance(meal_counts, dict):
        for meal_id, raw_count in meal_counts.items():
            try:
                count = max(0, min(int(raw_count), 20))
            except (TypeError, ValueError):
                count = 0
            selected_meal_ids.extend([str(meal_id)] * count)
    if not selected_meal_ids:
        selected_meal_ids = [str(value) for value in form.getlist("selected_meal_items") if str(value).strip()]

    database_food_ids = json_loads(form.get("selected_database_food_ids"), [])
    if not isinstance(database_food_ids, list):
        database_food_ids = []

    meal_plan = analysis.get("meal_plan") or []
    meal_total = meal_plan_totals(meal_plan)
    selected_meal_total, selected_meal_foods = selected_meal_item_totals(meal_plan, selected_meal_ids)
    selected_db_total, selected_db_foods = selected_database_foods([str(x) for x in database_food_ids])

    actual_kalori = round(selected_meal_total["kalori"] + selected_db_total["kalori"], 1)
    actual_karbo = round(selected_meal_total["karbo"] + selected_db_total["karbo"], 1)
    actual_protein = round(selected_meal_total["protein"] + selected_db_total["protein"], 1)
    actual_lemak = round(selected_meal_total["lemak"] + selected_db_total["lemak"], 1)
    selected_foods = selected_meal_foods + selected_db_foods

    adherence = 0.0
    if meal_total["kalori"] > 0:
        adherence = min(100.0, round((selected_meal_total["kalori"] / meal_total["kalori"]) * 100.0, 1))

    activity_name = str(form.get("activity_name") or "").strip()
    activity_type = str(form.get("activity_type") or "").strip()
    duration_minutes = safe_float(form.get("duration_minutes"), 0.0) or 0.0
    activity, met = find_activity_met(activity_name, activity_type)
    activity_category = activity.get("kategori") if activity else None
    activity_calories = calculate_activity_calories(met, weight_kg or 0.0, duration_minutes)

    bmr = estimate_bmr(profile_data)
    baseline_out = baseline_calories_out(profile_data)
    tdee = safe_float(analysis.get("tdee_mifflin"), 0.0) or 0.0

    calories_out = round(baseline_out + activity_calories, 1)
    deficit = round(calories_out - actual_kalori, 1)
    estimated_weight_change = round(-deficit / KG_PER_KCAL, 3)

    log = existing_log
    if not log:
        log = DailyProgressLogDB(user_id=current_user.id, tanggal=tanggal)
        db.add(log)

    log.weight_kg = weight_kg
    log.waist_cm = None

    log.target_kalori = safe_float(analysis.get("target_kalori"), 0.0) or 0.0
    log.target_karbo = safe_float(analysis.get("target_karbo"), 0.0) or 0.0
    log.target_protein = safe_float(analysis.get("target_protein"), 0.0) or 0.0
    log.target_lemak = safe_float(analysis.get("target_lemak"), 0.0) or 0.0
    log.tdee_reference = tdee
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

    log.activity_name = activity_name or None
    log.activity_type = activity_type or None
    log.activity_category = activity_category
    log.activity_met = met
    log.duration_minutes = duration_minutes
    log.activity_calories = activity_calories

    log.calories_out = calories_out
    log.deficit_calories = deficit
    log.estimated_weight_change_kg = estimated_weight_change

    log.notes = serialize_log_foods(selected_foods)
    log.updated_at = datetime.now(timezone.utc)

    db.commit()
    return RedirectResponse(url=f"/progress?tanggal={tanggal.isoformat()}", status_code=303)


@router.post("/delete/{log_id}")
async def delete_progress_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_current_user),
):
    log = db.query(DailyProgressLogDB).filter(DailyProgressLogDB.id == log_id, DailyProgressLogDB.user_id == current_user.id).first()
    if log:
        if log.tanggal < today():
            return RedirectResponse(url=f"/progress?tanggal={log.tanggal.isoformat()}", status_code=303)
        db.delete(log)
        db.commit()
    return RedirectResponse(url="/progress", status_code=303)
