import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.services.chatbot_personal_service import PersonalChatService, personal_intent, meal_scope, snapshot
from app.user.action_service import UserProgramActionService, UserActionError
from app.user.assessment import _filter_foods_for_pantangan


def meal(label, name):
    return {"waktu": label, "items": [{"nama": name, "gram_porsi": 100, "kalori": 300,
        "karbo": 40, "protein": 20, "lemak": 7, "slot_label": "Makanan Utama"}]}


class Program:
    _decode = staticmethod(UserProgramActionService._decode)
    _save = staticmethod(UserProgramActionService._save)

    def __init__(self):
        self.db = SimpleNamespace(flush=lambda: None)
        self.row = SimpleNamespace(full_profile_data=json.dumps({"pantangan_alergi": "Seafood"}),
            analysis_result=json.dumps({"meal_plan": [meal('Pagi', 'A'), meal('Siang', 'B')],
                "target_kalori": 600, "target_karbo": 80, "target_protein": 40, "target_lemak": 14,
                "kategori_risiko": "Risiko Sedang"}))
        self.calls = 0

    def _row(self, user_id):
        return self.row

    def regenerate_meal_plan(self, user_id, *, preview):
        assert preview
        self.calls += 1
        return {"meal_plan": [meal('Pagi', 'Baru pagi'), meal('Siang', f'Baru {self.calls}')]}


def test_preview_is_read_only_partial_and_saves_exact_candidate():
    p = Program()
    svc = PersonalChatService(None, program=p)
    before = snapshot(p.row)
    draft = svc.preview(1, 'siang')
    assert snapshot(p.row) == before
    assert draft['candidate'][0] == meal('Pagi', 'A')
    assert 'Baru 1' in draft['message']
    svc.apply(1, draft)
    assert json.loads(p.row.analysis_result)['meal_plan'] == draft['candidate']


def test_retry_varies_only_part_of_menu_and_stale_candidate_rejected():
    p = Program()
    svc = PersonalChatService(None, program=p)
    first = svc.preview(1, 'siang')
    second = svc.preview(1, 'siang', first)
    assert first['candidate'][0] == second['candidate'][0]
    assert first['candidate'][1] != second['candidate'][1]
    p.row.full_profile_data = json.dumps({'pantangan_alergi': 'Kacang'})
    with pytest.raises(UserActionError, match='berubah'):
        svc.apply(1, second)


def test_identical_candidates_are_not_offered():
    p = Program()
    p.regenerate_meal_plan = lambda *a, **kw: {'meal_plan': json.loads(p.row.analysis_result)['meal_plan']}
    with pytest.raises(UserActionError, match='Belum menemukan'):
        PersonalChatService(None, program=p).preview(1)


def test_recommend_uses_saved_meal_not_low_calorie_search():
    svc = PersonalChatService(None, program=Program(), foods=[])
    result = svc.recommend(1, 'siang')
    assert 'B — 100 g, 300 kkal' in result['message']
    assert 'Pagi' not in result['message']
    assert '600' not in result['message']


def test_exact_food_required_and_allergy_reason_grounded():
    foods = [{'nama': 'Nasi Goreng', 'gram_porsi': 200, 'natrium_mg': 830, 'adalah_gorengan': True,
              'slot_meal_plan': 'Karbo'},
             {'nama': 'Nasi Goreng Tuna', 'mengandung_seafood': True, 'adalah_gorengan': True,
              'slot_meal_plan': 'Lauk'}]
    svc = PersonalChatService(None, program=Program(), foods=foods)
    missing = svc.check(1, 'apakah saya boleh makan nasi goreng seafood?')
    assert 'belum ada kecocokan pasti' in missing and '830' not in missing
    answer = svc.check(1, 'apakah saya boleh makan nasi goreng tuna?')
    assert 'pantangan' in answer and 'Seafood' in answer and 'gorengan' in answer
    sodium = svc.check(1, 'apakah saya boleh makan nasi goreng?')
    assert '830 mg per 200 g' in sodium


def test_beef_excluded_and_seafood_meal_not_recommended():
    assert not _filter_foods_for_pantangan([{'nama': 'Sop Sapi'}], 'Daging Sapi')
    p = Program()
    a = json.loads(p.row.analysis_result)
    a['meal_plan'][0]['items'][0]['mengandung_seafood'] = True
    p.row.analysis_result = json.dumps(a)
    with pytest.raises(UserActionError, match='pantangan'):
        PersonalChatService(None, program=p).recommend(1)


@pytest.mark.parametrize('text,intent,scope', [
    ('tolong rekomendasikan makanan untuk saya', 'recommend', None),
    ('rekomendasi makan siang hari ini', 'recommend', 'siang'),
    ('ngga suka makanan itu', 'preview', None),
    ('ganti menu makan malam', 'preview', 'malam'),
    ('boleh makan nasi goreng seafood?', 'check', None),
])
def test_personal_routing(text, intent, scope):
    assert personal_intent(text) == intent
    assert meal_scope(text) == scope


def test_model_classified_recommendation_also_uses_saved_menu(monkeypatch):
    from app.services.chatbot_orchestrator_service import ChatbotOrchestratorService
    llm = SimpleNamespace(plan_request=lambda *args: {'intent': 'recommend_foods'})
    expected = {'type': 'meal_plan_display', 'message': 'Menu tersimpan'}
    monkeypatch.setattr(PersonalChatService, 'recommend', lambda *args: expected)
    result = ChatbotOrchestratorService(llm=llm).respond(None, 1, 'aku lapar', [])
    assert result['menu_action'] == expected
    assert result['mode'] == 'deterministic'


@pytest.mark.parametrize('question', [
    'apakah saya boleh makan makan mie goreng?',
    'apakah saya boleh makan mi goreng?',
    'apakah saya boleh makan mie gorengg?',
])
def test_similar_noodles_have_individual_dataset_reasons(question):
    foods = [
        {'nama': 'Indomie, mie goreng', 'tingkat_proses': 'Ultraproses', 'adalah_gorengan': True,
         'slot_meal_plan': 'No Meal', 'natrium_mg': 0},
        {'nama': 'Sarimi, mie goreng', 'tingkat_proses': 'Ultraproses', 'slot_meal_plan': 'No Meal',
         'natrium_mg': 900, 'gram_porsi': 100, 'mengandung_seafood': True},
        {'nama': 'Mi kuah ayam', 'slot_meal_plan': 'Karbo'},
    ]
    answer = PersonalChatService(None, program=Program(), foods=foods).check(1, question)
    assert "'makan mie goreng'" not in answer
    assert 'nama yang mirip' in answer
    assert 'Indomie, mie goreng' in answer and 'Sarimi, mie goreng' in answer
    assert 'Mi kuah ayam' not in answer
    indomie = answer.split('Indomie, mie goreng:')[1].split('Sarimi, mie goreng:')[0]
    assert 'ultra proses' in indomie and 'gorengan' in indomie
    assert 'natrium/sodium tinggi' not in indomie
    sarimi = answer.split('Sarimi, mie goreng:')[1]
    assert '900 mg per 100 g' in sarimi and 'Seafood' in sarimi


def test_repeated_makan_still_finds_exact_name_without_candidates():
    food = {'nama': 'Mie Goreng', 'adalah_gorengan': True, 'slot_meal_plan': 'Karbo'}
    answer = PersonalChatService(None, program=Program(), foods=[food]).check(1, 'boleh makan makan mie goreng?')
    assert 'belum ada' not in answer
    assert 'gorengan' in answer


def test_similarity_never_drops_qualifiers_or_invents_matches():
    from app.services.chatbot_personal_service import similar_foods
    foods = [{'nama': 'Nasi Goreng'}, {'nama': 'Mie Goreng'}, {'nama': 'Mie Goreng Seafood'}]
    assert similar_foods('nasi goreng seafood', foods) == []
    assert similar_foods('makanan xyzabc', foods) == []
    assert similar_foods('', foods) == []


def test_profile_summary_uses_real_values_and_no_invented_diagnosis():
    p = Program()
    p.row.full_profile_data = json.dumps({'usia': 42, 'berat_badan': 72.5, 'tinggi_badan': 168,
        'pantangan_alergi': 'Seafood', 'waktu_makan': ['Pagi', 'Sore']})
    text = PersonalChatService(None, program=p).profile_summary(1)
    assert '42 tahun' in text and '72.5 kg' in text and '168 cm' in text
    assert 'Seafood' in text and 'Pagi, Sore' in text
    assert 'Hasil lab yang Anda masukkan: Belum diisi' in text
    assert 'Risiko Sedang' in text and 'Prediabetes' not in text
    assert '[Nilai' not in text
    p.row.full_profile_data = json.dumps({'usia': 43, 'berat_badan': 0})
    updated = PersonalChatService(None, program=p).profile_summary(1)
    assert '43 tahun' in updated and 'Berat badan: Belum diisi' in updated


@pytest.mark.parametrize('question', ['cek profil kesehatan saya', 'lihat profil saya', 'berapa berat badan saya', 'apa hasil lab saya'])
def test_profile_read_intent(question):
    assert personal_intent(question) == 'profile'


def test_profile_reference_does_not_override_recommendation():
    assert personal_intent('rekomendasikan makanan sesuai profil saya') == 'recommend'
