from pathlib import Path

from app.user.diet_recommendation import recommend_programs
from app.user.diet_service import DietCatalogService, normalize_diet_id


HEADER = (
    'nama_diet,deskripsi,target,prinsip utama,boleh_dikonsumsi,'
    'batasi_hindari,kelebihan_manfaat,kekurangan_risiko\n'
)


def write_catalog(path: Path) -> None:
    path.write_text(
        HEADER
        + 'Diet Mediterania,Seimbang,{},"[""Sayur""]",[],[],[],[]\n'
        + 'Diet Rendah Karbohidrat,Batasi karbo,{},"[""Karbo kompleks""]",[],[],[],[]\n'
        + 'Intermittent Fasting,Atur waktu,{},"[""Jendela makan""]",[],[],[],[]\n'
        + 'Diet DASH,Batasi natrium,{},"[""Rendah natrium""]",[],[],[],[]\n',
        encoding='utf-8',
    )


def test_catalog_marks_only_three_programs_supported(tmp_path: Path):
    path = tmp_path / 'diets.csv'
    write_catalog(path)
    service = DietCatalogService(path)

    items = {item['id']: item for item in service.list_diets()}

    assert items['mediterania']['supported'] is True
    assert items['mediterania']['program_type'] == 'diet'
    assert items['rendah_karbo']['supported'] is True
    assert items['intermittent_fasting']['supported'] is True
    assert items['intermittent_fasting']['program_type'] == 'time_pattern'
    assert items['dash']['supported'] is False
    assert items['dash']['coming_soon'] is True
    assert normalize_diet_id('Diet Rendah Karbohidrat') == 'rendah_karbo'


def test_recommendation_prefers_low_carb_for_high_sugar_and_rice_pattern():
    profile = {
        'usia': 42,
        'frekuensi_minum_manis': 'Setiap hari',
        'porsi_nasi_per_hari': 'Lebih dari 2 porsi',
        'frekuensi_makan': '3x',
        'pola_waktu_makan': 'normal',
        'penyakit_lain_obat': '',
    }
    analysis = {
        'kategori_risiko': 'Tinggi (Sangat Berisiko Prediabetes)',
        'target_kalori': 1500,
        'bmi': 27.0,
    }

    results = recommend_programs(profile, analysis)

    assert results[0]['id'] == 'rendah_karbo'
    assert results[0]['score'] > results[1]['score']
    assert any('manis' in reason.lower() for reason in results[0]['reasons'])
    assert all(item['target_kalori'] == 1500 for item in results)


def test_if_is_independent_and_has_consultation_warning_for_risky_profile():
    profile = {
        'usia': 35,
        'frekuensi_minum_manis': 'Jarang',
        'porsi_nasi_per_hari': '1 porsi',
        'frekuensi_makan': '2x',
        'pola_waktu_makan': 'intermittent_fasting',
        'pola_puasa': '16:8',
        'penyakit_lain_obat': 'Menggunakan insulin dan pernah hipoglikemia',
    }
    analysis = {'kategori_risiko': 'Sedang (Waspada)', 'target_kalori': 1700, 'bmi': 23.0}

    results = {item['id']: item for item in recommend_programs(profile, analysis)}

    assert results['intermittent_fasting']['program_type'] == 'time_pattern'
    assert results['intermittent_fasting']['needs_consultation'] is True
    assert results['intermittent_fasting']['warning']
