from app.services.chatbot_intent_service import plan_chat_action


def test_add_food_defaults_to_one_portion():
    action = plan_chat_action("Catat nasi putih ke tracker")
    assert action["type"] == "add_food"
    assert action["items"] == [{"query": "nasi putih", "quantity": 1}]


def test_add_food_parses_multiple_items_and_quantities():
    action = plan_chat_action("Tambahkan nasi putih 2 porsi dan ayam bakar satu kali ke tracker hari ini")
    assert action["type"] == "add_food"
    assert action["items"] == [
        {"query": "nasi putih", "quantity": 2},
        {"query": "ayam bakar", "quantity": 1},
    ]


def test_change_diet_low_carb():
    action = plan_chat_action("Ganti diet saya ke low carbohydrate")
    assert action == {"type": "change_diet", "diet_id": "rendah_karbo"}


def test_deactivate_diet():
    assert plan_chat_action("Nonaktifkan diet saya") == {"type": "deactivate_diet"}


def test_regenerate_meal_plan():
    assert plan_chat_action("Saya bosan, generate ulang meal plan saya") == {"type": "regenerate_meal_plan"}


def test_normal_question_has_no_action():
    assert plan_chat_action("Apakah nasi merah aman untuk prediabetes?") is None


def test_add_food_does_not_require_tracker_word():
    action = plan_chat_action("Catat nasi putih")
    assert action == {
        "type": "add_food",
        "items": [{"query": "nasi putih", "quantity": 1}],
    }


def test_add_food_accepts_for_today_wording():
    action = plan_chat_action("Masukkan nasi putih 2 porsi untuk hari ini")
    assert action == {
        "type": "add_food",
        "items": [{"query": "nasi putih", "quantity": 2}],
    }


def test_add_food_strips_tracking_saya_suffix():
    action = plan_chat_action("Tolong tambahkan mie ayam di tracking saya")
    assert action == {
        "type": "add_food",
        "items": [{"query": "mie ayam", "quantity": 1}],
    }


def test_add_food_accepts_spaced_tambahkan_typo():
    action = plan_chat_action("Tolong tambah kan nasi goreng di tracking saya")
    assert action == {
        "type": "add_food",
        "items": [{"query": "nasi goreng", "quantity": 1}],
    }


def test_regenerate_meal_plan_accepts_direct_ganti_menu_wording():
    assert plan_chat_action("Saya mau ganti menu meal plan saya") == {
        "type": "regenerate_meal_plan"
    }


def test_regenerate_meal_plan_accepts_direct_ganti_meal_plan_wording():
    assert plan_chat_action("Tolong ganti meal plan saya") == {
        "type": "regenerate_meal_plan"
    }
