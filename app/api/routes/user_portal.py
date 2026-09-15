"""Landing, authentication, questionnaire, and dashboard routes."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.connection import get_db
from app.database.models.user import QuestionnaireDraftDB, UserDB, UserProfileDB
from app.user.assessment import analisis_user, generate_meal_plan_tervalidasi, get_diet_info
from app.user.dependencies import get_current_user_optional, require_current_user
from app.user.diet_recommendation import recommend_programs
from app.user.diet_service import get_diet_catalog_service, normalize_diet_id
from app.user.menu_service import get_menu_dataset_service
from app.user.action_service import UserActionError, UserProgramActionService
from app.user.questionnaire_service import (
    QuestionnaireValidationError,
    build_profile_from_form,
    save_completed_assessment,
    save_draft,
)
from app.user.repository import UserRepository, normalize_email, normalize_username
from app.user.security import create_session_token, hash_password, verify_password
from app.user.schemas import ProfilUser

router = APIRouter(tags=["User Portal"])
TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


def _set_auth_cookie(response: RedirectResponse, user_id: int) -> None:
    settings = Settings()
    max_age = settings.auth_session_minutes * 60
    token = create_session_token(
        user_id=user_id,
        secret=settings.auth_secret_key,
        expires_seconds=max_age,
    )
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def _login_destination(db: Session, user_id: int) -> str:
    return "/dashboard" if UserRepository(db).has_completed_profile(user_id) else "/questionnaire"


def _render_auth_error(
    request: Request,
    template_name: str,
    error: str,
    *,
    status_code: int = status.HTTP_400_BAD_REQUEST,
):
    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context={"error": error},
        status_code=status_code,
    )


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def landing(request: Request):
    return templates.TemplateResponse(request=request, name="landing.html")


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    current_user: UserDB | None = Depends(get_current_user_optional),
):
    if current_user:
        return _redirect("/dashboard")
    return templates.TemplateResponse(request=request, name="login.html")


@router.post("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    login_value = str(form.get("username") or "").strip()
    password = str(form.get("password") or "")
    user = UserRepository(db).find_by_login(login_value)
    if user is None or not verify_password(password, user.hashed_password):
        return _render_auth_error(
            request,
            "login.html",
            "Username/email atau password salah!",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if user.role.casefold() == "admin":
        return _render_auth_error(
            request,
            "login.html",
            "Akun admin dikelola melalui portal admin terpisah.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    response = _redirect(_login_destination(db, user.id))
    _set_auth_cookie(response, user.id)
    return response


@router.get("/register", response_class=HTMLResponse)
def register_page(
    request: Request,
    current_user: UserDB | None = Depends(get_current_user_optional),
):
    if current_user:
        return _redirect("/dashboard")
    return templates.TemplateResponse(request=request, name="register.html")


@router.post("/register")
async def register(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    username = str(form.get("username") or "").strip()
    email = str(form.get("email") or "").strip()
    password = str(form.get("password") or "")

    if not (3 <= len(username) <= 100):
        return _render_auth_error(request, "register.html", "Username minimal 3 karakter.")
    if not _EMAIL_PATTERN.match(email):
        return _render_auth_error(request, "register.html", "Format email tidak valid.")
    if len(password) < 8:
        return _render_auth_error(request, "register.html", "Password minimal 8 karakter.")

    duplicate = UserRepository(db).find_duplicate(username, email)
    if duplicate == "username":
        return _render_auth_error(request, "register.html", "Username sudah digunakan.")
    if duplicate == "email":
        return _render_auth_error(request, "register.html", "Email sudah terdaftar.")

    user = UserDB(
        username=username,
        username_normalized=normalize_username(username),
        email=email,
        email_normalized=normalize_email(email),
        hashed_password=hash_password(password),
        role="user",
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        return _render_auth_error(
            request,
            "register.html",
            "Username atau email sudah digunakan.",
        )

    response = _redirect("/questionnaire")
    _set_auth_cookie(response, user.id)
    return response


@router.get("/logout")
def logout(
    current_user: UserDB | None = Depends(get_current_user_optional),
):
    if current_user is not None:
        # Runtime import avoids a router import cycle while ensuring temporary
        # chat history and pending confirmations disappear on logout.
        from app.api.routes.chatbot import clear_user_chat_state

        clear_user_chat_state(current_user.id)
    settings = Settings()
    response = _redirect("/login")
    response.delete_cookie(settings.auth_cookie_name, path="/")
    return response


def _authenticated_or_redirect(user: UserDB | None):
    if user is None:
        return _redirect("/login")
    return None


@router.get("/questionnaire", response_class=HTMLResponse)
def questionnaire_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserDB | None = Depends(get_current_user_optional),
):
    redirect = _authenticated_or_redirect(current_user)
    if redirect:
        return redirect
    assert current_user is not None

    profile = db.scalar(select(UserProfileDB).where(UserProfileDB.user_id == current_user.id))
    draft = db.scalar(
        select(QuestionnaireDraftDB).where(QuestionnaireDraftDB.user_id == current_user.id)
    )
    profile_data = None
    is_draft = False
    last_section = 1
    if draft:
        try:
            profile_data = json.loads(draft.draft_data)
            is_draft = True
            last_section = draft.last_section
        except json.JSONDecodeError:
            profile_data = None
    elif profile:
        try:
            profile_data = json.loads(profile.full_profile_data)
        except json.JSONDecodeError:
            profile_data = None

    return templates.TemplateResponse(
        request=request,
        name="questionnaire.html",
        context={
            "user": current_user,
            "profile_data": profile_data,
            "is_edit": profile is not None,
            "is_draft": is_draft,
            "draft_last_section": last_section,
        },
    )


@router.post("/api/questionnaire/draft")
async def questionnaire_draft(
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_current_user),
):
    payload = await request.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="Data draft tidak valid.")
    serialized_size = len(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    if serialized_size > 128 * 1024:
        raise HTTPException(status_code=413, detail="Data draft terlalu besar.")
    draft = save_draft(
        db,
        current_user.id,
        data,
        last_section=int(payload.get("last_section") or 1),
    )
    return {"saved": True, "last_section": draft.last_section}


@router.post("/api/submit-assessment")
async def submit_assessment(
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_current_user),
):
    form = await request.form()
    try:
        profile = build_profile_from_form(form)
        result = analisis_user(profile)
    except QuestionnaireValidationError as exc:
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": str(exc),
                "missing_fields": exc.missing_fields,
            },
        )
    except ValueError as exc:
        return JSONResponse(status_code=422, content={"success": False, "error": str(exc)})

    profile_data = profile.model_dump()
    profile_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_completed_assessment(
        db,
        current_user.id,
        profile_data=profile_data,
        analysis_data=result.model_dump(),
    )
    return {"success": True, "redirect": "/dashboard"}


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserDB | None = Depends(get_current_user_optional),
):
    redirect = _authenticated_or_redirect(current_user)
    if redirect:
        return redirect
    assert current_user is not None
    profile = db.scalar(select(UserProfileDB).where(UserProfileDB.user_id == current_user.id))
    if profile is None:
        return _redirect("/questionnaire")
    UserProgramActionService(
        db,
        analyzer=analisis_user,
        meal_plan_generator=generate_meal_plan_tervalidasi,
    ).ensure_daily_meal_plan(current_user.id)
    db.commit()
    profile = db.scalar(select(UserProfileDB).where(UserProfileDB.user_id == current_user.id))
    assert profile is not None
    try:
        profile_data = json.loads(profile.full_profile_data)
        analysis_data = json.loads(profile.analysis_result)
    except json.JSONDecodeError:
        return _redirect("/questionnaire")

    active_diet = analysis_data.get("active_diet") or profile_data.get("active_diet")
    from app.api.routes.progress_tracker import get_dashboard_progress_context
    progress_context = get_dashboard_progress_context(db, current_user.id)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": current_user,
            "has_profile": True,
            "needs_update": False,
            "profile": profile_data,
            "analysis": analysis_data,
            "active_diet_info": get_diet_info(active_diet),
            **progress_context,
        },
    )


@router.get("/menu", response_class=HTMLResponse)
def menu_page(
    request: Request,
    q: str = "",
    kategori: str = "",
    filter: str = "all",
    sort: str = "nama_asc",
    page: int = 1,
    per_page: int = 24,
    current_user: UserDB = Depends(require_current_user),
):
    context = get_menu_dataset_service().query(
        q=q,
        kategori=kategori.strip(),
        filter_key=filter.strip() or "all",
        sort=sort.strip() or "nama_asc",
        page=page,
        per_page=per_page,
    )
    context["user"] = current_user
    return templates.TemplateResponse(request=request, name="menu_list.html", context=context)


def _profile_row_or_404(db: Session, user_id: int) -> UserProfileDB:
    row = db.scalar(select(UserProfileDB).where(UserProfileDB.user_id == user_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Profil belum tersedia.")
    return row


def _decode_profile_row(row: UserProfileDB) -> tuple[dict, dict]:
    try:
        return json.loads(row.full_profile_data), json.loads(row.analysis_result)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Data profil/analisis tidak valid.") from exc


def _recalculate_for_profile(row: UserProfileDB, profile_data: dict) -> dict:
    model = ProfilUser(**profile_data)
    result = analisis_user(model).model_dump()
    from app.services.common_utils import today
    result["meal_plan_date"] = today().isoformat()
    row.full_profile_data = json.dumps(profile_data, ensure_ascii=False)
    row.analysis_result = json.dumps(result, ensure_ascii=False)
    row.updated_at = datetime.now(timezone.utc)
    return result


def _program_state(profile_data: dict, analysis_data: dict) -> tuple[str | None, bool]:
    active_diet = normalize_diet_id(
        analysis_data.get("active_diet") or profile_data.get("active_diet")
    )
    if active_diet not in {"mediterania", "rendah_karbo"}:
        active_diet = None
    if_active = str(profile_data.get("pola_waktu_makan") or "normal") == "intermittent_fasting"
    return active_diet, if_active


@router.get("/diet", response_class=HTMLResponse)
def diet_list_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_current_user),
):
    row = _profile_row_or_404(db, current_user.id)
    profile_data, analysis_data = _decode_profile_row(row)
    active_diet, if_active = _program_state(profile_data, analysis_data)
    recommendations = recommend_programs(profile_data, analysis_data)
    recommendation_map = {item["id"]: item for item in recommendations}
    recommended_id = recommendations[0]["id"] if recommendations else None

    programs = get_diet_catalog_service().list_diets()
    for program in programs:
        program["recommendation"] = recommendation_map.get(program["id"])
        program["is_recommended"] = program["id"] == recommended_id
        program["is_active"] = (
            if_active
            if program["id"] == "intermittent_fasting"
            else active_diet == program["id"]
        )
    programs.sort(key=lambda item: (not item["supported"], item["nama"].casefold()))

    return templates.TemplateResponse(
        request=request,
        name="diet_list.html",
        context={
            "user": current_user,
            "diets": programs,
            "active_diet": active_diet,
            "if_active": if_active,
            "target_kalori": int(round(float(analysis_data.get("target_kalori") or 0))),
            "recommendations": recommendations,
            "recommended_id": recommended_id,
        },
    )


@router.get("/diet/{diet_id}", response_class=HTMLResponse)
def diet_detail_page(
    diet_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_current_user),
):
    diet = get_diet_catalog_service().get_diet(diet_id)
    if diet is None:
        raise HTTPException(status_code=404, detail="Program diet tidak ditemukan.")
    row = _profile_row_or_404(db, current_user.id)
    profile_data, analysis_data = _decode_profile_row(row)
    active_diet, if_active = _program_state(profile_data, analysis_data)
    recommendation_map = {
        item["id"]: item for item in recommend_programs(profile_data, analysis_data)
    }
    diet["is_active"] = (
        if_active if diet["id"] == "intermittent_fasting" else active_diet == diet["id"]
    )
    return templates.TemplateResponse(
        request=request,
        name="diet_detail.html",
        context={
            "user": current_user,
            "diet": diet,
            "active_diet": active_diet,
            "if_active": if_active,
            "target_kalori": int(round(float(analysis_data.get("target_kalori") or 0))),
            "recommendation": recommendation_map.get(diet["id"]),
        },
    )


@router.post("/api/activate-diet/{diet_id}")
def activate_diet(
    diet_id: str,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_current_user),
):
    diet = get_diet_catalog_service().get_diet(diet_id)
    if diet is None:
        raise HTTPException(status_code=404, detail="Diet tidak ditemukan.")
    try:
        UserProgramActionService(
            db,
            analyzer=analisis_user,
            meal_plan_generator=generate_meal_plan_tervalidasi,
        ).activate_diet(current_user.id, diet["id"])
        db.commit()
    except UserActionError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _redirect("/dashboard")


@router.post("/api/deactivate-diet")
def deactivate_diet(
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_current_user),
):
    try:
        UserProgramActionService(
            db,
            analyzer=analisis_user,
            meal_plan_generator=generate_meal_plan_tervalidasi,
        ).deactivate_diet(current_user.id)
        db.commit()
    except UserActionError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _redirect("/dashboard")


@router.post("/api/activate-intermittent-fasting")
def activate_intermittent_fasting(
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_current_user),
):
    row = _profile_row_or_404(db, current_user.id)
    profile_data, _ = _decode_profile_row(row)
    profile_data["pola_waktu_makan"] = "intermittent_fasting"
    profile_data["pola_puasa"] = profile_data.get("pola_puasa") or "16:8"
    profile_data["jam_makan_mulai"] = profile_data.get("jam_makan_mulai") or "10:00"
    profile_data["jam_makan_selesai"] = profile_data.get("jam_makan_selesai") or "18:00"
    profile_data["time_pattern_updated_at"] = datetime.now(timezone.utc).isoformat()
    _recalculate_for_profile(row, profile_data)
    db.commit()
    return _redirect("/dashboard")


@router.post("/api/deactivate-intermittent-fasting")
def deactivate_intermittent_fasting(
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_current_user),
):
    row = _profile_row_or_404(db, current_user.id)
    profile_data, _ = _decode_profile_row(row)
    profile_data["pola_waktu_makan"] = "normal"
    profile_data["pola_puasa"] = None
    profile_data["jam_makan_mulai"] = None
    profile_data["jam_makan_selesai"] = None
    profile_data["time_pattern_updated_at"] = datetime.now(timezone.utc).isoformat()
    _recalculate_for_profile(row, profile_data)
    db.commit()
    return _redirect("/dashboard")


@router.post("/api/regenerate-meal-plan")
def regenerate_meal_plan(
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_current_user),
):
    try:
        UserProgramActionService(
            db,
            analyzer=analisis_user,
            meal_plan_generator=generate_meal_plan_tervalidasi,
        ).regenerate_meal_plan(current_user.id)
        db.commit()
    except UserActionError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True}
