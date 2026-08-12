from app.services.chatbot_request_planner import DeterministicRequestPlanner


def test_greeting_is_not_food_lookup():
    plan = DeterministicRequestPlanner().plan("hai")
    assert plan["intent"] == "greeting"


def test_out_of_domain_question_is_detected():
    plan = DeterministicRequestPlanner().plan("siapa presiden pertama di indonesia")
    assert plan["intent"] == "out_of_scope"


def test_natural_lookup_extracts_food_and_field():
    plan = DeterministicRequestPlanner().plan("saya pengen makan nasi tim kira-kira berapa kalorinya")
    assert plan["intent"] == "food_lookup"
    assert plan["food_name"] == "nasi tim"
    assert plan["requested_fields"] == ["kalori_kkal"]


def test_multi_food_total_extracts_two_items():
    plan = DeterministicRequestPlanner().plan("saya makan nasi goreng dan bubur ayam berapa total kalori saya")
    assert plan["intent"] == "meal_total"
    assert [item["food_name"] for item in plan["items"]] == ["nasi goreng", "bubur ayam"]
