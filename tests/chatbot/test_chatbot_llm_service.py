from types import SimpleNamespace

from app.services.chatbot_llm_service import ChatbotLlmService


class FakeOllama:
    def __init__(self, answer="Jawaban Ollama"):
        self.answer_text = answer
        self.calls = []

    def chat(self, prompt, model, system=None, **kwargs):
        self.calls.append((prompt, model, system, kwargs))
        return self.answer_text


class JsonPlanOllama(FakeOllama):
    def __init__(self):
        super().__init__('{"intent":"food_lookup","food_name":"nasi tim","requested_fields":["kalori_kkal"]}')


def local_settings():
    return SimpleNamespace(
        ollama_base_url="http://ollama",
        ollama_timeout_seconds=10,
        qa_model="llama3.1:8b",
    )


def test_ollama_is_primary_for_answer():
    ollama = FakeOllama("Jawaban lokal")
    service = ChatbotLlmService(settings=local_settings(), ollama_client=ollama)

    answer = service.answer("Halo", "Konteks", [])

    assert answer == "Jawaban lokal"
    assert service.last_provider == "ollama"
    assert ollama.calls[0][1] == "llama3.1:8b"


def test_ollama_can_return_structured_request_plan():
    service = ChatbotLlmService(settings=local_settings(), ollama_client=JsonPlanOllama())

    plan = service.plan_request("berapa kalori nasi tim", [])

    assert plan["intent"] == "food_lookup"
    assert plan["food_name"] == "nasi tim"
    assert service.last_provider == "ollama"


def test_ollama_failure_returns_local_service_message():
    class BrokenOllama:
        def chat(self, *args, **kwargs):
            raise RuntimeError("ollama down")

    service = ChatbotLlmService(settings=local_settings(), ollama_client=BrokenOllama())
    answer = service.answer("Apa?", "Konteks tersedia", [])

    assert "layanan AI lokal" in answer
    assert "ollama down" in (service.last_ollama_error or "")


def test_local_planner_requests_json_mode_and_zero_temperature():
    class CapturingOllama:
        def __init__(self):
            self.kwargs = None
        def chat(self, prompt, model, system=None, **kwargs):
            self.kwargs = kwargs
            return '{"intent":"greeting"}'

    ollama = CapturingOllama()
    service = ChatbotLlmService(settings=local_settings(), ollama_client=ollama)
    plan = service.plan_request("halo", [])

    assert plan["intent"] == "greeting"
    assert ollama.kwargs["format"] == "json"
    assert ollama.kwargs["temperature"] == 0
