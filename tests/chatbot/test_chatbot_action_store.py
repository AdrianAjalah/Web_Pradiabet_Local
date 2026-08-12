from datetime import datetime, timedelta, timezone

import pytest

from app.services.chatbot_action_service import PendingActionError, PendingActionStore


def test_pending_action_is_scoped_to_owner():
    store = PendingActionStore(ttl_seconds=600)
    action = store.create(11, {"type": "regenerate_meal_plan"})
    assert store.get(11, action["id"])["type"] == "regenerate_meal_plan"
    with pytest.raises(PendingActionError):
        store.get(12, action["id"])


def test_pending_action_expires():
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    store = PendingActionStore(ttl_seconds=60, now_factory=lambda: now)
    action = store.create(11, {"type": "regenerate_meal_plan"})
    store.now_factory = lambda: now + timedelta(seconds=61)
    with pytest.raises(PendingActionError, match="kedaluwarsa"):
        store.get(11, action["id"])


def test_add_food_pending_action_keeps_ambiguous_candidates(monkeypatch):
    from app.services import chatbot_action_service

    monkeypatch.setattr(
        chatbot_action_service,
        "search_tracker_foods",
        lambda query, limit=5: [
            {"id": "FM001", "nama": "Nasi Goreng Ayam"},
            {"id": "FM002", "nama": "Nasi Goreng Seafood"},
            {"id": "FM003", "nama": "Nasi Goreng Kampung"},
        ],
    )

    action = chatbot_action_service.build_pending_action(
        {"type": "add_food", "items": [{"query": "nasi goreng", "quantity": 1}]}
    )

    assert action["type"] == "add_food"
    assert action["groups"][0]["quantity"] == 1
    assert [item["id"] for item in action["groups"][0]["candidates"]] == [
        "FM001",
        "FM002",
        "FM003",
    ]
    assert action["groups"][0]["selected_food_id"] == "FM001"
