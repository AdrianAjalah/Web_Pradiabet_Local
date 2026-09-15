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


def test_multi_food_total_uses_fast_deterministic_plan():
    planner = DeterministicRequestPlanner()
    plan = planner.fast_plan("semisalnya saya makan sate ayam dan sate padang berapa total kalori yang saya makan")
    assert plan is not None
    assert plan["intent"] == "meal_total"
    assert [item["food_name"] for item in plan["items"]] == ["sate ayam", "sate padang"]


def test_total_calories_without_makan_keyword_and_with_sama():
    plan = DeterministicRequestPlanner().fast_plan("berapa total kalori rasbi sama domba panggang")
    assert plan == {
        "intent": "meal_total",
        "items": [
            {"food_name": "rasbi", "quantity": 1},
            {"food_name": "domba panggang", "quantity": 1},
        ],
    }


def test_comparison_with_sama_uses_fast_deterministic_plan():
    plan = DeterministicRequestPlanner().fast_plan("bandingkan rasbi sama domba panggang")
    assert plan == {
        "intent": "compare_foods",
        "food_names": ["rasbi", "domba panggang"],
    }
