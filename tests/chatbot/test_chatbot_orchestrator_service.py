from app.services.chatbot_orchestrator_service import ChatbotOrchestratorService
from app.services.chatbot_tool_service import ChatbotToolService
from app.services.structured_food_service import StructuredFoodService
from tests.chatbot.test_structured_food_service import sample_foods


class FakeLlm:
    def __init__(self, plan=None, answer_text="Jawaban natural"):
        self.plan = plan
        self.answer_text = answer_text
        self.contexts = []
        self.answer_calls = 0
    def plan_request(self, question, history):
        return self.plan
    def answer(self, question, context, history):
        self.answer_calls += 1
        self.contexts.append(context)
        return self.answer_text


def make_service(llm, rag_result=("", "Hybrid RAG PDF", 0.0)):
    return ChatbotOrchestratorService(
        llm=llm,
        tool_service=ChatbotToolService(StructuredFoodService(foods=sample_foods())),
        profile_context_builder=lambda db, user_id: "PROFIL TEST",
        rag_context_builder=lambda question: rag_result,
    )


def test_greeting_uses_conversation_without_food_lookup():
    llm = FakeLlm(plan={"intent":"greeting"})
    result = make_service(llm).respond(None, 1, "hai", [])
    assert result["source"] == "Percakapan Dr. Predia"
    assert result["answer"] == "Jawaban natural"


def test_natural_food_lookup_includes_structured_result_in_llm_context():
    llm = FakeLlm(plan={"intent":"food_lookup","food_name":"nasi goreng","requested_fields":["kalori_kkal"]})
    result = make_service(llm).respond(None, 1, "berapa kalori nasi goreng", [])
    assert result["source"] == "Structured Nutrition Database"
    assert "336" in llm.contexts[0]
    assert "Nasi Goreng" in llm.contexts[0]


def test_meal_total_is_grounded_in_python_result():
    llm = FakeLlm(plan={"intent":"meal_total","items":[{"food_name":"nasi goreng","quantity":1},{"food_name":"bubur ayam","quantity":1}]})
    result = make_service(llm).respond(None, 1, "saya makan nasi goreng dan bubur ayam berapa total kalori saya", [])
    assert "634" in result["answer"]
    assert result["mode"] == "deterministic"
    assert llm.answer_calls == 0


def test_food_comparison_is_rendered_without_llm_rewriting_numbers():
    llm = FakeLlm(plan={"intent":"compare_foods","food_names":["nasi goreng","bubur ayam"]})
    result = make_service(llm).respond(None, 1, "bandingkan nasi goreng dan bubur ayam", [])
    assert "336" in result["answer"] and "298" in result["answer"]
    assert result["mode"] == "deterministic"
    assert llm.answer_calls == 0


def test_pdf_education_keeps_hybrid_pdf_context():
    llm = FakeLlm(plan={"intent":"pdf_education","question":"kenapa serat penting"})
    result = make_service(llm, ("ISI PDF SERAT", "pedoman.pdf", 0.88)).respond(None, 1, "kenapa serat penting", [])
    assert result["source"] == "pedoman.pdf"
    assert result["confidence"] == 0.88
    assert "ISI PDF SERAT" in llm.contexts[0]


def test_unavailable_llm_uses_natural_deterministic_fallback():
    llm = FakeLlm(plan={"intent":"food_lookup","food_name":"nasi goreng","requested_fields":["kalori_kkal"]}, answer_text="Maaf, layanan AI sedang tidak dapat dihubungi.")
    result = make_service(llm).respond(None, 1, "berapa kalori nasi goreng", [])
    assert "336" in result["answer"]
    assert "Nasi Goreng" in result["answer"]


def test_mode_defaults_to_ollama_when_llm_does_not_expose_provider():
    llm = FakeLlm(plan={"intent":"greeting"})
    result = make_service(llm).respond(None, 1, "hai", [])
    assert result["mode"] == "ollama"
