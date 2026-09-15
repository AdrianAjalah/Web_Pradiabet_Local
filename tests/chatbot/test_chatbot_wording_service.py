import json
from types import SimpleNamespace

from app.services.chatbot_wording_service import word_food_answer, wording_options


def test_llm_can_change_wording_but_not_numeric_facts():
    facts = 'Sate Ayam:\nSebaiknya tidak dijadikan pilihan menu Anda karena natrium/sodium tinggi.\nDataset mencatat natrium 530 mg per 150 g.'
    def chat(**kwargs):
        options = json.loads(kwargs['prompt'])['pilihan_kalimat']
        return json.dumps({'choices': [len(group)-1 for group in options], 'answer': 'Aman, natrium nol.'})
    answer, used = word_food_answer('boleh sate ayam?', facts, llm=SimpleNamespace(_ollama_chat=chat))
    assert used and answer != facts
    assert '530 mg per 150 g' in answer and 'Sate Ayam' in answer
    assert 'Aman, natrium nol' not in answer


def test_invalid_or_missing_llm_output_keeps_facts():
    facts = 'Dataset mencatat gula 12 g per 100 g.'
    for output in [None, '{}', '{"choices": [-1]}', '{"choices": [true]}', '{"choices": [99]}', '{"choices": []}', 'aman dimakan']:
        answer, used = word_food_answer('gula?', facts, llm=SimpleNamespace(_ollama_chat=lambda **kw: output))
        assert answer == facts and not used


def test_every_positive_variant_preserves_caveat_about_missing_data():
    facts = 'Sayur asem:\nMakanan ini ada di dataset dan bisa dipertimbangkan: tidak ada kecocokan dengan pantangan profil atau alasan penolakan yang terdeteksi. Tetap sesuaikan porsinya dengan meal plan Anda.\nData belum lengkap untuk gula, natrium. Nilai kosong bukan berarti kandungannya nol.'
    groups = wording_options(facts)
    for variant in groups[1]:
        assert 'pantangan' in variant and ('dipertimbangkan' in variant or 'mempertimbangkannya' in variant)
    for variant in groups[2]:
        assert 'gula, natrium' in variant and 'bukan berarti' in variant
