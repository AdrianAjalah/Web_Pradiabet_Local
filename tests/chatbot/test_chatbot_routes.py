from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_db
from app.database.models.user import UserDB, UserProfileDB
from app.main import create_app
from app.user.security import hash_password


@pytest.fixture()
def client(chatbot_db_factory):
    app = create_app()

    def override_db():
        db = chatbot_db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client


def _login_with_profile(client, factory):
    with factory() as db:
        user = UserDB(
            username="chat-route-user",
            username_normalized="chat-route-user",
            email="chat-route@example.com",
            email_normalized="chat-route@example.com",
            hashed_password=hash_password("password123"),
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
                    "berat_badan": 70,
                    "tinggi_badan": 170,
                    "frekuensi_makan": "3x",
                    "waktu_makan": ["Pagi", "Siang", "Malam"],
                    "pola_waktu_makan": "normal",
                }),
                analysis_result=json.dumps({
                    "kategori_risiko": "Risiko Sedang",
                    "target_kalori": 1800,
                    "target_karbo": 200,
                    "target_protein": 100,
                    "target_lemak": 67,
                    "meal_plan": [],
                }),
            )
        )
        db.commit()
        user_id = user.id
    response = client.post(
        "/login",
        data={"username": "chat-route-user", "password": "password123"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return user_id


def test_chatbot_requires_login(client):
    response = client.get("/chatbot", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_chatbot_page_uses_v1_title(client, chatbot_db_factory):
    _login_with_profile(client, chatbot_db_factory)
    response = client.get("/chatbot")
    assert response.status_code == 200
    assert "Konsultasi Dr. Predia AI" in response.text


def test_action_question_returns_confirmation_without_executing(client, chatbot_db_factory, monkeypatch):
    _login_with_profile(client, chatbot_db_factory)
    from app.api.routes import chatbot

    monkeypatch.setattr(
        chatbot,
        "build_pending_action",
        lambda plan: {
            "type": "regenerate_meal_plan",
            "title": "Generate Ulang Meal Plan?",
            "message": "Meal plan akan diganti.",
            "confirm_label": "Generate Ulang Meal Plan",
        },
    )
    response = client.post("/tanya", json={"pertanyaan": "generate ulang meal plan saya"})
    payload = response.json()

    assert response.status_code == 200
    assert payload["action"]["type"] == "regenerate_meal_plan"
    assert payload["action"]["id"]
    assert "belum dijalankan" in payload["jawaban"].lower()


def test_confirm_endpoint_executes_pending_action(client, chatbot_db_factory, monkeypatch):
    _login_with_profile(client, chatbot_db_factory)
    from app.api.routes import chatbot

    monkeypatch.setattr(
        chatbot,
        "build_pending_action",
        lambda plan: {
            "type": "regenerate_meal_plan",
            "title": "Generate Ulang Meal Plan?",
            "message": "Meal plan akan diganti.",
            "confirm_label": "Generate Ulang Meal Plan",
        },
    )
    monkeypatch.setattr(
        chatbot.ChatbotActionExecutor,
        "execute",
        lambda self, **kwargs: {"message": "Meal plan berhasil dibuat ulang.", "redirect": "/dashboard"},
    )
    planned = client.post("/tanya", json={"pertanyaan": "generate ulang meal plan saya"}).json()
    action_id = planned["action"]["id"]

    response = client.post(
        "/api/chatbot/actions/confirm",
        json={"action_id": action_id, "selections": []},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["message"] == "Meal plan berhasil dibuat ulang."


def test_cancel_endpoint_removes_pending_action(client, chatbot_db_factory, monkeypatch):
    _login_with_profile(client, chatbot_db_factory)
    from app.api.routes import chatbot

    monkeypatch.setattr(
        chatbot,
        "build_pending_action",
        lambda plan: {
            "type": "regenerate_meal_plan",
            "title": "Generate Ulang Meal Plan?",
            "message": "Meal plan akan diganti.",
            "confirm_label": "Generate Ulang Meal Plan",
        },
    )
    action_id = client.post("/tanya", json={"pertanyaan": "generate ulang meal plan saya"}).json()["action"]["id"]
    response = client.post("/api/chatbot/actions/cancel", json={"action_id": action_id})
    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Tindakan dibatalkan."}


def test_logout_clears_temporary_chat_state(client, chatbot_db_factory):
    user_id = _login_with_profile(client, chatbot_db_factory)
    from app.api.routes import chatbot

    chatbot.chat_histories[user_id] = [{"role": "user", "content": "halo"}]
    action = chatbot.pending_actions.create(user_id, {"type": "regenerate_meal_plan"})

    response = client.get("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert user_id not in chatbot.chat_histories
    with pytest.raises(chatbot.PendingActionError):
        chatbot.pending_actions.get(user_id, action["id"])


def test_change_diet_confirmation_shows_current_and_new_program(client, chatbot_db_factory):
    user_id = _login_with_profile(client, chatbot_db_factory)
    with chatbot_db_factory() as db:
        row = db.query(UserProfileDB).filter(UserProfileDB.user_id == user_id).first()
        profile = json.loads(row.full_profile_data)
        analysis = json.loads(row.analysis_result)
        profile["active_diet"] = "mediterania"
        analysis["active_diet"] = "mediterania"
        analysis["active_diet_label"] = "Diet Mediterania"
        row.full_profile_data = json.dumps(profile)
        row.analysis_result = json.dumps(analysis)
        db.commit()

    response = client.post("/tanya", json={"pertanyaan": "ganti diet saya ke low carb"})

    assert response.status_code == 200
    message = response.json()["action"]["message"]
    assert "Program saat ini: Diet Mediterania" in message
    assert "Program baru: Low Carbohydrate" in message
    assert "meal plan" in message.lower()


def test_direct_ganti_menu_returns_confirmation_instead_of_llm_answer(
    client, chatbot_db_factory, monkeypatch
):
    _login_with_profile(client, chatbot_db_factory)
    from app.api.routes import chatbot

    def fail_if_llm_is_called(*args, **kwargs):
        raise AssertionError("LLM tidak boleh dipanggil untuk perintah perubahan meal plan")

    monkeypatch.setattr(chatbot.ChatbotLlmService, "answer", fail_if_llm_is_called)

    response = client.post(
        "/tanya",
        json={"pertanyaan": "Saya mau ganti menu meal plan saya"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["action"]["type"] == "regenerate_meal_plan"
    assert "belum dijalankan" in payload["jawaban"].lower()



def test_chatbot_status_reports_local_ollama_provider(client, chatbot_db_factory, monkeypatch):
    _login_with_profile(client, chatbot_db_factory)
    from types import SimpleNamespace
    from app.api.routes import chatbot

    fake_llm = SimpleNamespace(
        settings=SimpleNamespace(
            ollama_base_url="http://ollama:11434",
            qa_model="llama3.1:8b",
        ),
        last_provider="ollama",
        last_ollama_error=None,
    )
    monkeypatch.setattr(chatbot, "_chatbot_orchestrator", SimpleNamespace(llm=fake_llm))

    response = client.get("/api/chatbot/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["provider"] == "ollama"
    assert payload["model"] == "llama3.1:8b"
    assert payload["last_provider"] == "ollama"
    assert payload["last_ollama_error"] is None
