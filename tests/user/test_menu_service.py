from pathlib import Path

from app.user.menu_service import MenuDatasetService


def write_food_csv(path: Path):
    path.write_text(
        'kode;nama_makanan;kelompok_makanan;jenis_bahan_utama;tingkat_proses;slot_meal_plan;gram_porsi;kalori_kkal;karbohidrat_g;protein_g;lemak_g;serat_g;gula_g;natrium_mg;indeks_glikemik;adalah_gorengan;mengandung_babi;mengandung_alkohol\n'
        'F1;Mangga;Buah;Buah;Mentah bisa dimakan;Buah;100;60;15;1;0;2;24;2;51;false;false;false\n'
        'F2;Tempe Goreng;Lauk Nabati;Kedelai;Minimal proses;Lauk;100;220;18;15;12;4;1;180;35;true;false;false\n'
        'F3;Ayam Kukus;Lauk Hewani;Daging Putih;Minimal proses;Lauk;100;170;0;28;5;0;0;90;0;false;false;false\n',
        encoding='utf-8',
    )


def test_menu_search_filter_sort_and_fruit_sugar(tmp_path: Path):
    path = tmp_path / 'food.csv'
    write_food_csv(path)
    service = MenuDatasetService(path)

    result = service.query(q='mangga', page=1, per_page=24)
    assert result['total_filtered'] == 1
    assert result['items'][0]['is_natural_fruit_sugar'] is True
    assert result['items'][0]['is_high_sugar'] is False

    fried = service.query(filter_key='fried', page=1, per_page=24)
    assert [item['nama'] for item in fried['items']] == ['Tempe Goreng']

    protein = service.query(sort='protein_desc', page=1, per_page=24)
    assert protein['items'][0]['nama'] == 'Ayam Kukus'
