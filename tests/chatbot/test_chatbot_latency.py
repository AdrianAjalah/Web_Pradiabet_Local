from types import SimpleNamespace

import pytest

from app.services.chatbot_request_planner import DeterministicRequestPlanner
from app.services.chatbot_llm_service import ChatbotLlmService
from tests.chatbot.test_chatbot_orchestrator_service import FakeLlm, make_service


def test_clear_lookup_skips_model_planning():
    llm = FakeLlm()
    def unexpected(*args):
        raise AssertionError("Planner AI must not run")
    llm.plan_request = unexpected
    result = make_service(llm).respond(None, 1, "berapa kalori nasi goreng", [])
    assert "336" in llm.contexts[0]
    assert result["planner_mode"] == "deterministic"
    assert result["timings"]["total_ms"] >= 0


@pytest.mark.parametrize("question", [
    "berapa kalori 200 gram nasi", "berapa kalori makanan tadi",
    "halo berapa kalori nasi", "berapa kalori nasi dan ayam",
    "berapa kalori itu", "rekomendasi menu untuk alergi kacang",
])
def test_complex_requests_keep_model_planning(question):
    assert DeterministicRequestPlanner().fast_plan(question) is None


def test_history_has_total_budget_and_keeps_recent_messages():
    service = ChatbotLlmService(settings=SimpleNamespace(chatbot_history_chars=2200), ollama_client=object())
    history = [{"role": "user", "content": "a" * 2000}, {"role": "assistant", "content": "b" * 2000}]
    result = service._safe_history(history)
    assert sum(len(item["content"]) for item in result) == 2200
    assert result[-1]["content"] == "b" * 2000


def test_stream_emits_chunks_before_final_result():
    llm = FakeLlm()
    llm.answer_stream = lambda *args: iter(["Halo ", "Anda"])
    events = make_service(llm).respond_events(None, 1, "halo", [])
    assert next(events)["type"] == "ready"
    assert next(events) == {"type": "delta", "text": "Halo "}
    assert next(events)["text"] == "Anda"
    assert next(events)["result"]["answer"] == "Halo Anda"


def test_local_failure_uses_structured_fallback():
    llm = FakeLlm(answer_text="Maaf, layanan AI lokal sedang tidak dapat dihubungi.")
    result = make_service(llm).respond(None, 1, "berapa kalori nasi goreng", [])
    assert result["mode"] == "deterministic"
    assert "336" in result["answer"]


def test_partial_stream_failure_is_not_silently_saved_as_complete():
    class BrokenStream:
        def chat_stream(self, *args, **kwargs):
            yield "Sebagian"
            raise RuntimeError("connection lost")
    service = ChatbotLlmService(settings=SimpleNamespace(qa_model="test"), ollama_client=BrokenStream())
    stream = service.answer_stream("halo", "", [])
    assert next(stream) == "Sebagian"
    with pytest.raises(RuntimeError, match="terputus"):
        next(stream)
