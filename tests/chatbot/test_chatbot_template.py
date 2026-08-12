from pathlib import Path


def test_chatbot_template_keeps_v1_layout_and_has_action_controls():
    template = Path("templates/chatbot.html").read_text(encoding="utf-8")

    assert "Konsultasi Dr. Predia AI" in template
    assert "chat-history" in template
    assert "marked.min.js" in template
    assert "renderActionCard" in template
    assert "Konfirmasi" in template
    assert "Batal" in template
    assert "food-candidate-select" in template
    assert "action-quantity-plus" in template


def test_chatbot_action_error_keeps_confirmation_controls_available():
    template = Path("templates/chatbot.html").read_text(encoding="utf-8")

    assert "function showActionResult(card, message, success, hideControls = true)" in template
    assert "showActionResult(card, error.message || 'Tindakan gagal dijalankan.', false, false);" in template
