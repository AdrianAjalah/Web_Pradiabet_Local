from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_db
from app.database.models.user import UserDB, UserProfileDB
from app.main import create_app
from app.user.security import hash_password


@pytest.fixture()
def client(chatbot_db_factory, monkeypatch):
    monkeypatch.setattr('app.api.routes.chatbot.word_food_answer', lambda question, answer: (answer, False))
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


def test_stream_endpoint_delivers_events_and_saves_complete_history(client, chatbot_db_factory, monkeypatch):
    from app.api.routes import chatbot
    user_id = _login_with_profile(client, chatbot_db_factory)
    chatbot.clear_user_chat_state(user_id)
    class StreamingOrchestrator:
        def respond_events(self, *args):
            yield {"type": "ready"}
            yield {"type": "delta", "text": "Halo"}
            yield {"type": "done", "result": {"answer": "Halo", "source": "test", "confidence": 1, "mode": "ollama"}}
    monkeypatch.setattr(chatbot, "get_chatbot_orchestrator", lambda: StreamingOrchestrator())
    response = client.post("/tanya", json={"pertanyaan": "halo", "stream": True})
    assert response.status_code == 200
    assert "application/x-ndjson" in response.headers["content-type"]
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0] == {"type": "delta", "text": "Halo"}
    assert events[-1]["data"]["jawaban"] == "Halo"
    assert chatbot.chat_histories[user_id][-1]["content"] == "Halo"


def test_stream_error_does_not_save_partial_answer(client, chatbot_db_factory, monkeypatch):
    from app.api.routes import chatbot
    user_id = _login_with_profile(client, chatbot_db_factory)
    chatbot.clear_user_chat_state(user_id)
    class BrokenOrchestrator:
        def respond_events(self, *args):
            yield {"type": "ready"}
            yield {"type": "delta", "text": "Sebagian"}
            raise RuntimeError("lost connection")
    monkeypatch.setattr(chatbot, "get_chatbot_orchestrator", lambda: BrokenOrchestrator())
    response = client.post("/tanya", json={"pertanyaan": "halo", "stream": True})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]["type"] == "error"
    assert not chatbot.chat_histories.get(user_id)


def test_chatbot_page_uses_v1_title(client, chatbot_db_factory):
    _login_with_profile(client, chatbot_db_factory)
    response = client.get("/chatbot")
    assert response.status_code == 200
    assert "Konsultasi Dr. Predia AI" in response.text


def test_action_question_returns_confirmation_without_executing(client, chatbot_db_factory, monkeypatch):
    _login_with_profile(client, chatbot_db_factory)
    from app.api.routes import chatbot

    monkeypatch.setattr(
        chatbot.PersonalChatService,
        "preview",
        lambda *args, **kwargs: {
            "type": "replace_meal_plan",
            "title": "Generate Ulang Meal Plan?",
            "message": "Meal plan akan diganti.",
            "confirm_label": "Generate Ulang Meal Plan",
        },
    )
    response = client.post("/tanya", json={"pertanyaan": "generate ulang meal plan saya"})
    payload = response.json()

    assert response.status_code == 200
    assert payload["action"]["type"] == "replace_meal_plan"
    assert payload["action"]["id"]
    assert "menu" in payload["jawaban"].lower()


def test_confirm_endpoint_executes_pending_action(client, chatbot_db_factory, monkeypatch):
    _login_with_profile(client, chatbot_db_factory)
    from app.api.routes import chatbot

    monkeypatch.setattr(
        chatbot.PersonalChatService,
        "preview",
        lambda *args, **kwargs: {
            "type": "replace_meal_plan",
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
        chatbot.PersonalChatService,
        "preview",
        lambda *args, **kwargs: {
            "type": "replace_meal_plan",
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
    monkeypatch.setattr(chatbot.PersonalChatService, "preview", lambda *a, **k: {"type": "replace_meal_plan", "message": "Kandidat menu belum disimpan."})

    response = client.post(
        "/tanya",
        json={"pertanyaan": "Saya mau ganti menu meal plan saya"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["action"]["type"] == "replace_meal_plan"
    assert "menu" in payload["jawaban"].lower()



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


def test_menu_preview_retry_cancel_and_confirm_are_isolated(client, chatbot_db_factory, monkeypatch):
    from app.api.routes import chatbot
    from app.user.action_service import UserProgramActionService
    from tests.chatbot.test_personal_recommendations import meal

    uid = _login_with_profile(client, chatbot_db_factory)
    original = [meal('Pagi', 'Menu pagi'), meal('Siang', 'Menu siang')]
    with chatbot_db_factory() as db:
        row = db.query(UserProfileDB).filter_by(user_id=uid).first()
        analysis = json.loads(row.analysis_result)
        analysis['meal_plan'] = original
        row.analysis_result = json.dumps(analysis)
        db.commit()

    count = [0]
    def generate(self, user_id, *, preview=False):
        assert preview
        count[0] += 1
        return {'meal_plan': [meal('Pagi', 'Pagi baru'), meal('Siang', f'Siang baru {count[0]}')]}
    monkeypatch.setattr(UserProgramActionService, 'regenerate_meal_plan', generate)
    def stored():
        with chatbot_db_factory() as db:
            return json.loads(db.query(UserProfileDB).filter_by(user_id=uid).first().analysis_result)['meal_plan']

    action = client.post('/tanya', json={'pertanyaan': 'rekomendasi makan siang hari ini', 'stream': True}).json()['action']
    assert action['type'] == 'meal_plan_display'
    assert 'Menu siang' in action['message'] and 'Menu pagi' not in action['message']
    draft = client.post('/api/chatbot/actions/another', json={'action_id': action['id']}).json()['action']
    assert stored() == original
    assert not {'candidate', 'base_snapshot', 'seen', 'validation'} & draft.keys()
    retry = client.post('/api/chatbot/actions/another', json={'action_id': draft['id']}).json()['action']
    assert 'Siang baru 2' in retry['message'] and stored() == original
    assert client.post('/api/chatbot/actions/confirm', json={'action_id': draft['id']}).status_code == 400
    assert client.post('/api/chatbot/actions/cancel', json={'action_id': retry['id']}).status_code == 200
    assert stored() == original
    new = client.post('/tanya', json={'pertanyaan': 'ganti menu makan siang'}).json()['action']
    assert client.post('/api/chatbot/actions/confirm', json={'action_id': new['id']}).status_code == 200
    assert stored()[0] == original[0]
    assert stored()[1]['items'][0]['nama'] == 'Siang baru 3'


def test_similar_food_followup_stays_grounded(client, chatbot_db_factory, monkeypatch):
    _login_with_profile(client, chatbot_db_factory)
    from app.services import chatbot_personal_service
    from app.api.routes import chatbot
    monkeypatch.setattr(chatbot_personal_service, 'load_nutrition_foods', lambda: [
        {'nama': 'Sarimi, Mie goreng', 'tingkat_proses': 'Ultraproses', 'slot_meal_plan': 'No Meal'},
    ])
    def no_llm():
        raise AssertionError('Food selection must stay deterministic')
    monkeypatch.setattr(chatbot, 'get_chatbot_orchestrator', no_llm)
    response = client.post('/tanya', json={'pertanyaan': 'apakah saya boleh makan makan mie goreng?'}).json()
    assert 'nama yang mirip' in response['jawaban']
    selected = client.post('/tanya', json={'pertanyaan': 'Sarimi, Mie goreng'}).json()
    assert selected['jawaban'].startswith('Sarimi, Mie goreng:')
    assert 'ultra proses' in selected['jawaban']


@pytest.mark.parametrize('followup', [
    'apakah saya boleh memakannya?',
    'apakah saya boleh memakannnya?',
    'apakah saya boleh makan keduanya?',
    'apakah makanan itu boleh saya makan?',
])
def test_contextual_food_followup_resolves_previous_total(client, chatbot_db_factory, monkeypatch, followup):
    uid = _login_with_profile(client, chatbot_db_factory)
    from app.services import chatbot_personal_service
    from app.api.routes import chatbot

    foods = [
        {'nama': 'Sate Ayam', 'gram_porsi': 150, 'kalori_kkal': 338,
         'kelompok_makanan': 'Lauk Hewani', 'tingkat_proses': 'Olahan',
         'slot_meal_plan': 'Lauk', 'natrium_mg': 530, 'gula_g': 4.2,
         'missing_nutrients': []},
        {'nama': 'Sate Maranggi', 'gram_porsi': 250, 'kalori_kkal': 520,
         'kelompok_makanan': 'Lauk Hewani', 'tingkat_proses': 'Olahan',
         'slot_meal_plan': 'Lauk', 'natrium_mg': 850, 'gula_g': 10.2,
         'missing_nutrients': []},
    ]
    monkeypatch.setattr(chatbot_personal_service, 'load_nutrition_foods', lambda: foods)
    chatbot.chat_histories[uid] = [{
        'role': 'assistant',
        'content': 'Berdasarkan porsi pada dataset:\n\n- Sate Ayam: 338 kkal untuk 150 g\n- Sate Maranggi: 520 kkal untuk 250 g\n\nTotal: **858 kkal**.',
    }]

    response = client.post('/tanya', json={'pertanyaan': followup}).json()
    assert 'Sate Ayam:' in response['jawaban']
    assert 'Sate Maranggi:' in response['jawaban']
    assert "'memakannnya'" not in response['jawaban']


def test_profile_read_uses_logged_in_account_without_llm(client, chatbot_db_factory, monkeypatch):
    uid = _login_with_profile(client, chatbot_db_factory)
    from app.api.routes import chatbot
    def no_llm(*args, **kwargs):
        raise AssertionError('Profile values must not be generated by an LLM')
    monkeypatch.setattr(chatbot, 'get_chatbot_orchestrator', no_llm)
    monkeypatch.setattr(chatbot, 'word_food_answer', no_llm)
    with chatbot_db_factory() as db:
        # An unrelated profile must never be selected by a caller-supplied ID.
        db.add(UserProfileDB(user_id=uid + 1000, full_profile_data=json.dumps({'usia': 99}), analysis_result='{}'))
        db.commit()
    response = client.post('/tanya', json={'pertanyaan': 'cek profil kesehatan saya', 'stream': True, 'user_id': uid + 1000})
    assert response.status_code == 200
    result = response.json()
    assert '35 tahun' in result['jawaban'] and '70 kg' in result['jawaban'] and '170 cm' in result['jawaban']
    assert '99 tahun' not in result['jawaban'] and '[Nilai' not in result['jawaban']
    assert 'Prediabetes' not in result['jawaban']
    assert result['mode'] == 'verified_data'
