"""AI Nutrition Coach routes with safe internal tool calling."""
from __future__ import annotations

from pathlib import Path
import re
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.models.user import UserDB, UserProfileDB
from app.services.chatbot_action_service import (
    ChatbotActionError,
    ChatbotActionExecutor,
    PendingActionError,
    PendingActionStore,
    build_pending_action,
)
from app.services.chatbot_intent_service import plan_chat_action
from app.services.chatbot_orchestrator_service import ChatbotOrchestratorService
from app.services.chatbot_llm_service import ChatbotLlmService  # compatibility for existing tests
from app.user.dependencies import get_current_user_optional, require_current_user
from app.services.chatbot_personal_service import PersonalChatService, personal_intent, meal_scope, normalize
from app.user.action_service import UserActionError, UserProgramActionService
from app.services.chatbot_wording_service import word_food_answer

router = APIRouter(tags=["AI Nutrition Coach"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[3] / "templates"))

chat_histories: dict[int, list[dict[str, str]]] = {}
pending_actions = PendingActionStore(ttl_seconds=600)

_chatbot_orchestrator: ChatbotOrchestratorService | None = None


def get_chatbot_orchestrator() -> ChatbotOrchestratorService:
    global _chatbot_orchestrator
    if _chatbot_orchestrator is None:
        _chatbot_orchestrator = ChatbotOrchestratorService()
    return _chatbot_orchestrator



class ChatRequest(BaseModel):
    pertanyaan: str = Field(min_length=1, max_length=2000)
    stream: bool = False


class ConfirmActionRequest(BaseModel):
    action_id: str = Field(min_length=8, max_length=64)
    selections: list[dict[str, Any]] = Field(default_factory=list)


class CancelActionRequest(BaseModel):
    action_id: str = Field(min_length=8, max_length=64)


def _append_history(user_id: int, role: str, content: str) -> None:
    history = chat_histories.setdefault(user_id, [])
    history.append({"role": role, "content": str(content)[:3000]})
    chat_histories[user_id] = history[-10:]


def _contextual_food_names(question: str, history: list[dict[str, str]]) -> list[str]:
    """Resolve follow-ups such as 'boleh memakannya?' from the last answer."""
    q = normalize(question)
    refers_to_previous = bool(re.search(
        r"\bmemakan+nya\b|\bmakanannya\b|\b(?:makanan|menu) (?:itu|tadi|tersebut)\b"
        r"|\byang (?:itu|tadi|tersebut)\b|\b(?:keduanya|semuanya)\b",
        q,
    ))
    if not refers_to_previous:
        return []

    last_answer = next(
        (str(item.get("content") or "") for item in reversed(history) if item.get("role") == "assistant"),
        "",
    )
    names = []
    for match in re.finditer(r"^\s*[-*]\s+\**([^:\n]+?)\**\s*:\s*", last_answer, re.MULTILINE):
        name = match.group(1).strip(" *")
        if name and normalize(name) not in {normalize(existing) for existing in names}:
            names.append(name)
    return names[:8]


def _confirmation_decision(text: str) -> str | None:
    normalized = re.sub(r"[^a-z0-9]+", " ", str(text or "").casefold()).strip()
    if not normalized or len(normalized.split()) > 6:
        return None
    positive = {
        "ya", "iya", "y", "yes", "ok", "oke", "setuju", "lanjut",
        "tambahkan", "ya tambahkan", "iya tambahkan", "oke tambahkan",
        "konfirmasi", "ya konfirmasi", "gas",
        "pakai menu ini", "simpan menu ini",
    }
    negative = {
        "tidak", "tidak batalkan", "batal", "batalkan", "jangan",
        "ga", "gak", "nggak", "enggak", "no",
        "tetap pakai menu sebelumnya", "pakai menu sebelumnya",
    }
    if normalized in positive:
        return "confirm"
    if normalized in negative:
        return "cancel"
    return None


def _handle_pending_text_confirmation(
    *,
    question: str,
    db: Session,
    current_user: UserDB,
) -> dict[str, Any] | None:
    decision = _confirmation_decision(question)
    if decision is None:
        return None
    try:
        action = pending_actions.latest(current_user.id)
    except PendingActionError:
        return None

    _append_history(current_user.id, "user", question)
    if decision == "cancel":
        pending_actions.cancel(current_user.id, action["id"])
        message = "Tindakan dibatalkan. Tidak ada perubahan pada data Anda."
        _append_history(current_user.id, "assistant", message)
        return {
            "jawaban": message,
            "sumber": "PrediBeat Internal Tools",
            "confidence": 100.0,
            "action": None,
            "mode": "deterministic",
            "redirect": None,
        }

    try:
        result = ChatbotActionExecutor(db).execute(
            user_id=current_user.id,
            action=action,
            selections=[],
        )
        pending_actions.pop(current_user.id, action["id"])
    except (PendingActionError, ChatbotActionError) as exc:
        message = str(exc)
        _append_history(current_user.id, "assistant", message)
        return {
            "jawaban": message,
            "sumber": "PrediBeat Internal Tools",
            "confidence": 100.0,
            "action": _public_action(action),
            "mode": "deterministic",
            "redirect": None,
        }

    message = str(result.get("message") or "Tindakan berhasil dijalankan.")
    _append_history(current_user.id, "assistant", message)
    return {
        "jawaban": message,
        "sumber": "PrediBeat Internal Tools",
        "confidence": 100.0,
        "action": None,
        "mode": "deterministic",
        "redirect": result.get("redirect"),
        **{key: value for key, value in result.items() if key not in {"message", "redirect"}},
    }


def clear_user_chat_state(user_id: int) -> None:
    chat_histories.pop(user_id, None)
    pending_actions.clear_user(user_id)


def _public_action(action: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in action.items() if key not in {"created_at", "candidate", "base_snapshot", "seen", "validation"}}


def _personal_response(user_id, question, answer, action=None):
    _append_history(user_id, "user", question)
    _append_history(user_id, "assistant", answer)
    return {"jawaban": answer, "sumber": "Profil, meal plan & dataset PrediBeat", "mode": "deterministic",
            "action": _public_action(action) if action else None}


def _store_menu_action(user_id, prepared, previous=None):
    if previous and previous.get("type") in {"meal_plan_display", "replace_meal_plan"}:
        pending_actions.cancel(user_id, previous['id'])
    return pending_actions.create(user_id, prepared)


def _current_diet_label(db: Session, user_id: int) -> str:
    row = db.query(UserProfileDB).filter(UserProfileDB.user_id == user_id).first()
    if row is None:
        return "Tidak ada"
    try:
        import json

        profile = json.loads(row.full_profile_data or "{}")
        analysis = json.loads(row.analysis_result or "{}")
    except (TypeError, json.JSONDecodeError):
        return "Tidak ada"
    active = analysis.get("active_diet") or profile.get("active_diet")
    label = analysis.get("active_diet_label")
    if label:
        return str(label)
    if active == "mediterania":
        return "Diet Mediterania"
    if active == "rendah_karbo":
        return "Low Carbohydrate"
    return "Tidak ada"


def _add_current_program_to_confirmation(
    prepared: dict[str, Any],
    *,
    current_diet_label: str,
) -> dict[str, Any]:
    action = dict(prepared)
    if action.get("type") == "change_diet":
        action["message"] = (
            f"Program saat ini: {current_diet_label}. "
            f"Program baru: {action.get('diet_label')}. "
            "Mengganti program diet akan otomatis mengganti seluruh meal plan aktif "
            "sesuai target dan aturan diet baru."
        )
    elif action.get("type") == "deactivate_diet":
        action["message"] = (
            f"Program saat ini: {current_diet_label}. "
            "Diet aktif akan dinonaktifkan dan seluruh meal plan akan otomatis diganti "
            "dengan pola makan seimbang bawaan PrediBeat."
        )
    return action


@router.get("/chatbot", response_class=HTMLResponse)
def chatbot_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserDB | None = Depends(get_current_user_optional),
):
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    profile = db.query(UserProfileDB).filter(UserProfileDB.user_id == current_user.id).first()
    if profile is None:
        return RedirectResponse(url="/questionnaire", status_code=status.HTTP_303_SEE_OTHER)
    daily = UserProgramActionService(db).ensure_daily_meal_plan(current_user.id)
    db.commit()
    if daily.get("changed"):
        pending_actions.clear_user(current_user.id)
    return templates.TemplateResponse(
        request=request,
        name="chatbot.html",
        context={"user": current_user},
    )


@router.post("/tanya")
def ask_chatbot(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_current_user),
):
    question = payload.pertanyaan.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Pertanyaan tidak boleh kosong.")

    daily = UserProgramActionService(db).ensure_daily_meal_plan(current_user.id)
    db.commit()
    if daily.get("changed"):
        pending_actions.clear_user(current_user.id)

    pending_response = _handle_pending_text_confirmation(
        question=question,
        db=db,
        current_user=current_user,
    )
    if pending_response is not None:
        return pending_response

    history = chat_histories.get(current_user.id, [])
    personal = personal_intent(question)
    # Resolve high-confidence follow-ups from conversation history before intent
    # routing. A typo such as "memakannnya" may fail the ordinary keyword
    # classifier, but it still clearly refers to foods in the previous answer.
    contextual_foods = _contextual_food_names(question, history)
    if contextual_foods:
        personal = "check"
    if personal is None and history and history[-1].get('role') == 'assistant':
        offered_names = re.findall(r'^\d+\. (.+):$', history[-1].get('content', ''), re.MULTILINE)
        if normalize(question) in {normalize(name) for name in offered_names}:
            personal = 'check'
    try:
        previous = pending_actions.latest(current_user.id)
    except PendingActionError:
        previous = None
    if previous and previous.get('type') in {'meal_plan_display', 'replace_meal_plan'} and re.fullmatch(
        r"(?:coba |tolong )?(?:lagi|generate ulang(?: lagi)?|buat ulang(?: lagi)?|yang lain|ngga mau|nggak mau|tidak cocok)[.!? ]*",
        question.casefold().strip(),
    ):
        personal = 'preview'
    if personal:
        service = PersonalChatService(db)
        try:
            if personal == 'profile':
                response = _personal_response(current_user.id, question, service.profile_summary(current_user.id))
                response['sumber'] = 'Profil akun & hasil assessment tersimpan'
                response['mode'] = 'verified_data'
                return response
            if personal == "check":
                if contextual_foods:
                    facts = "\n\n".join(
                        service.check(current_user.id, f"apakah saya boleh makan {name}?")
                        for name in contextual_foods
                    )
                else:
                    facts = service.check(current_user.id, question)
                answer, rewritten = word_food_answer(question, facts)
                response = _personal_response(current_user.id, question, answer)
                response['mode'] = 'grounded_wording' if rewritten else 'verified_data'
                return response
            scope = meal_scope(question)
            if personal == "preview":
                if scope is None and previous and previous.get('type') in {'meal_plan_display', 'replace_meal_plan'}:
                    scope = previous.get('scope')
                prepared = service.preview(current_user.id, scope, previous)
            else:
                prepared = service.recommend(current_user.id, scope)
            stored = _store_menu_action(current_user.id, prepared, previous)
            return _personal_response(current_user.id, question, "Silakan periksa menu berikut.", stored)
        except UserActionError as exc:
            return _personal_response(current_user.id, question, str(exc))
    plan = plan_chat_action(question)
    if plan:
        try:
            prepared = build_pending_action(plan)
            prepared = _add_current_program_to_confirmation(
                prepared,
                current_diet_label=_current_diet_label(db, current_user.id),
            )
            stored = pending_actions.create(current_user.id, prepared)
        except ChatbotActionError as exc:
            answer = str(exc)
            _append_history(current_user.id, "user", question)
            _append_history(current_user.id, "assistant", answer)
            return {
                "jawaban": answer,
                "sumber": "Dataset PrediBeat",
                "confidence": 100.0,
                "action": None,
            }

        answer = (
            f"{prepared.get('message', 'Periksa perubahan berikut.')}\n\n"
            "Tindakan belum dijalankan. Periksa detailnya lalu tekan tombol konfirmasi."
        )
        _append_history(current_user.id, "user", question)
        _append_history(current_user.id, "assistant", answer)
        return {
            "jawaban": answer,
            "sumber": "PrediBeat Internal Tools",
            "confidence": 100.0,
            "action": _public_action(stored),
        }

    if payload.stream:
        user_id = current_user.id
        events = get_chatbot_orchestrator().respond_events(db, user_id, question, list(history))
        # Finish all database access before handing over the streaming response.
        next(events)

        def generate():
            try:
                for event in events:
                    if event["type"] == "done":
                        result = event["result"]
                        _append_history(user_id, "user", question)
                        _append_history(user_id, "assistant", result["answer"])
                        event = {"type": "done", "data": _chat_response(result, user_id)}
                    yield json.dumps(event, ensure_ascii=False) + "\n"
            except Exception:
                yield json.dumps({"type": "error", "message": "Jawaban terputus. Silakan coba lagi."}) + "\n"
            finally:
                events.close()

        return StreamingResponse(generate(), media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    result = get_chatbot_orchestrator().respond(db, current_user.id, question, history)
    answer = str(result["answer"])
    _append_history(current_user.id, "user", question)
    _append_history(current_user.id, "assistant", answer)
    return _chat_response(result, current_user.id)


def _chat_response(result, user_id=None):
    menu_action = None
    if result.get('menu_action') and user_id is not None:
        try:
            previous = pending_actions.latest(user_id)
        except PendingActionError:
            previous = None
        menu_action = _public_action(_store_menu_action(user_id, result['menu_action'], previous))
    return {
        "jawaban": result["answer"],
        "sumber": result["source"],
        "confidence": round(float(result["confidence"] or 0) * 100, 2),
        "action": menu_action,
        "mode": result.get("mode", "unknown"),
        "timings": result.get("timings", {}),
        "planner_mode": result.get("planner_mode", "unknown"),
    }


@router.get("/api/chatbot/status")
def chatbot_status(current_user: UserDB = Depends(require_current_user)):
    orchestrator = get_chatbot_orchestrator()
    llm = orchestrator.llm
    model = getattr(llm.settings, "qa_model", "llama3.1:8b")
    configured = bool(getattr(llm.settings, "ollama_base_url", "") and model)
    return {
        "configured": configured,
        "provider": "ollama",
        "model": model,
        "last_provider": getattr(llm, "last_provider", "none"),
        "last_ollama_error": getattr(llm, "last_ollama_error", None),
        "food_retrieval": "structured_sqlite",
        "pdf_retrieval": "hybrid_rag_qdrant",
    }


@router.post("/api/chatbot/actions/confirm")
def confirm_chatbot_action(
    payload: ConfirmActionRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_current_user),
):
    try:
        action = pending_actions.get(current_user.id, payload.action_id)
        result = ChatbotActionExecutor(db).execute(
            user_id=current_user.id,
            action=action,
            selections=payload.selections,
        )
        pending_actions.pop(current_user.id, payload.action_id)
    except (PendingActionError, ChatbotActionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    message = str(result.get("message") or "Tindakan berhasil dijalankan.")
    _append_history(current_user.id, "assistant", message)
    return {"success": True, **result}


@router.post("/api/chatbot/actions/cancel")
def cancel_chatbot_action(
    payload: CancelActionRequest,
    current_user: UserDB = Depends(require_current_user),
):
    try:
        pending_actions.cancel(current_user.id, payload.action_id)
    except PendingActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "message": "Tindakan dibatalkan."}


@router.post("/api/chatbot/actions/another")
def another_menu(payload: CancelActionRequest, db: Session = Depends(get_db), current_user: UserDB = Depends(require_current_user)):
    try:
        previous = pending_actions.get(current_user.id, payload.action_id)
        if previous.get('type') not in {'meal_plan_display', 'replace_meal_plan'}:
            raise UserActionError('Tindakan ini bukan pilihan menu.')
        prepared = PersonalChatService(db).preview(current_user.id, previous.get('scope'), previous)
        stored = _store_menu_action(current_user.id, prepared, previous)
        return {"success": True, "action": _public_action(stored)}
    except (PendingActionError, UserActionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
