from app.services.chatbot_tool_service import ChatbotToolService
from app.services.structured_food_service import StructuredFoodService
from tests.chatbot.test_structured_food_service import sample_foods


def tool_service():
    return ChatbotToolService(food_service=StructuredFoodService(foods=sample_foods()))


def test_lookup_returns_grounded_food_payload():
    result = tool_service().execute({"intent":"food_lookup","food_name":"nasi goreng","requested_fields":["kalori_kkal"]})
    assert result["status"] == "found"
    assert result["food"]["kalori_kkal"] == 336


def test_meal_total_is_calculated_by_python():
    result = tool_service().execute({"intent":"meal_total","items":[{"food_name":"nasi goreng","quantity":1},{"food_name":"bubur ayam","quantity":1}]})
    assert result["status"] == "calculated"
    assert result["totals"]["kalori_kkal"] == 634
    assert len(result["items"]) == 2


def test_ambiguous_lookup_returns_choices_instead_of_guessing():
    result = tool_service().execute({"intent":"food_lookup","food_name":"rendang","requested_fields":["protein_g"]})
    assert result["status"] == "ambiguous"
    assert result["candidates"][0]["nama"] == "Rendang Sapi"
