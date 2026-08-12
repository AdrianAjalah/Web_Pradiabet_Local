from app.user import assessment


def _food(**overrides):
    data = {
        'nama': 'Udang',
        'kelompok_makanan': 'Lauk Hewani',
        'jenis_bahan_utama': 'Seafood',
        'tingkat_proses': 'Minimal proses',
        'slot_meal_plan': 'Lauk',
        'kalori': 120.0,
        'karbo': 2.0,
        'protein': 22.0,
        'lemak': 3.0,
        'serat_g': 0.0,
        'gula_g': 0.0,
        'gula_tambahan_g': 0.0,
        'sodium': 100.0,
        'mengandung_seafood': True,
        'mengandung_kacang': False,
        'mengandung_susu': False,
        'mengandung_telur': False,
        'mengandung_babi': False,
        'mengandung_alkohol': False,
        'mengandung_santan': False,
        'mengandung_sayur': False,
        'adalah_gorengan': False,
        'karbohidrat_kompleks': False,
        'karbohidrat_olahan': False,
        'is_high_added_sugar': False,
        'is_high_sugar': False,
        'is_seafood': True,
        'is_fish': True,
    }
    data.update(overrides)
    return data


def test_low_carb_preserves_1500_calorie_target_while_changing_macros():
    karbo, protein, lemak, note = assessment.terapkan_diet_pada_target_makro(
        1500, 'Tinggi', 169, 94, 50, 'rendah_karbo'
    )
    macro_calories = karbo * 4 + protein * 4 + lemak * 9
    assert karbo <= 98
    assert protein == 112
    assert abs(macro_calories - 1500) <= 10
    assert 'Rendah Karbo' in note


def test_if_schedule_does_not_change_macro_target():
    default = assessment.terapkan_diet_pada_target_makro(
        1500, 'Sedang', 188, 75, 50, None
    )
    if_value = assessment.terapkan_diet_pada_target_makro(
        1500, 'Sedang', 188, 75, 50, 'intermittent_fasting'
    )
    assert if_value[:3] == default[:3]
    schedule, notes, start, end = assessment._susun_jadwal_if(
        ['Siang', 'Malam'],
        pola_waktu_makan='intermittent_fasting',
        pola_puasa='16:8',
        jam_makan_mulai='10:00',
    )
    assert start == '10:00'
    assert end == '18:00'
    assert all('10:00' <= row['jam'] <= '18:00' for row in schedule)
    assert notes


def test_allergy_filter_is_never_relaxed(monkeypatch):
    monkeypatch.setattr(assessment, '_load_food_data', lambda: [_food()])
    result = assessment.generate_meal_plan(
        target_kalori=1500,
        frekuensi_makan='3x',
        waktu_makan=['Pagi', 'Siang', 'Malam'],
        kategori_risiko='Sedang',
        pantangan='alergi seafood',
    )
    assert result == []
