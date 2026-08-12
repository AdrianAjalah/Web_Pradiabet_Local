from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database.connection import get_db
from app.database.models.user import UserDB, UserProfileDB
from app.main import create_app


@pytest.fixture()
def client(db_session_factory):
    app = create_app()

    def override_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client


def write_diets(path: Path):
    path.write_text(
        'nama_diet,deskripsi,target,prinsip utama,boleh_dikonsumsi,batasi_hindari,kelebihan_manfaat,kekurangan_risiko\n'
        'Diet Mediterania,Pola seimbang,{},"[""Sayur""]",[],[],[],[]\n'
        'Diet Rendah Karbohidrat,Batasi karbo,{},"[""Karbo kompleks""]",[],[],[],[]\n'
        'Intermittent Fasting,Atur waktu,{},"[""Jendela makan""]",[],[],[],[]\n'
        'Diet DASH,Batasi natrium,{},"[""Natrium""]",[],[],[],[]\n',
        encoding='utf-8',
    )


def make_profile(client: TestClient, factory):
    response = client.post(
        '/register',
        data={'username': 'portaluser', 'email': 'portaluser@example.com', 'password': 'password123'},
    )
    assert response.status_code in {200, 303}
    profile = {
        'usia': 42,
        'jenis_kelamin': 'Laki-laki',
        'berat_badan': 78,
        'tinggi_badan': 170,
        'lingkar_pinggang': 93,
        'frekuensi_minum_manis': 'Setiap hari',
        'porsi_nasi_per_hari': 'Lebih dari 2 porsi',
        'frekuensi_olahraga': '1-2x per minggu',
        'durasi_duduk_rebahan': '4-6 jam',
        'durasi_tidur': '7-8 jam',
        'riwayat_keluarga_diabetes': True,
        'gejala_klasik': [],
        'pantangan_alergi': '',
        'penyakit_lain_obat': '',
        'hasil_lab': '',
        'frekuensi_makan': '3x',
        'waktu_makan': ['Pagi', 'Siang', 'Malam'],
        'active_diet': None,
        'pola_waktu_makan': 'normal',
        'pola_puasa': None,
        'jam_makan_mulai': None,
        'jam_makan_selesai': None,
    }
    analysis = {
        'bmi': 27.0,
        'kategori_bmi': 'Obesitas',
        'tdee_mifflin': 2300,
        'kategori_tdee': 'deficit',
        'skor_risiko': 60,
        'kategori_risiko': 'Tinggi (Sangat Berisiko Prediabetes)',
        'target_kalori': 1800,
        'target_karbo': 202,
        'target_protein': 112,
        'target_lemak': 60,
        'profil_singkat': 'test',
        'active_diet': None,
        'active_diet_label': None,
        'pantangan': [],
        'meal_plan': [{'waktu': 'Pagi', 'items': [{'nama': 'Lama'}]}],
        'frekuensi_makan': '3x',
        'waktu_makan': ['Pagi', 'Siang', 'Malam'],
        'pola_waktu_makan': 'normal',
        'pola_puasa': None,
        'jam_makan_mulai': None,
        'jam_makan_selesai': None,
        'catatan_pola_makan': [],
    }
    with factory() as db:
        user = db.scalar(select(UserDB).where(UserDB.username_normalized == 'portaluser'))
        db.add(
            UserProfileDB(
                user_id=user.id,
                full_profile_data=json.dumps(profile),
                analysis_result=json.dumps(analysis),
            )
        )
        db.commit()
    return profile, analysis


def fake_result(profile):
    diet = profile.active_diet
    diet_label = {
        'mediterania': 'Diet Mediterania',
        'rendah_karbo': 'Diet Rendah Karbohidrat',
    }.get(diet)
    payload = {
        'bmi': 27.0,
        'kategori_bmi': 'Obesitas',
        'tdee_mifflin': 2300,
        'kategori_tdee': 'deficit',
        'skor_risiko': 60,
        'kategori_risiko': 'Tinggi (Sangat Berisiko Prediabetes)',
        'target_kalori': 1800,
        'target_karbo': 117 if diet == 'rendah_karbo' else 202,
        'target_protein': 135 if diet == 'rendah_karbo' else 112,
        'target_lemak': 88 if diet == 'rendah_karbo' else 60,
        'profil_singkat': 'test',
        'active_diet': diet,
        'active_diet_label': diet_label,
        'pantangan': [],
        'meal_plan': [{'waktu': 'Pagi', 'items': [{'nama': 'Baru'}]}],
        'frekuensi_makan': profile.frekuensi_makan,
        'waktu_makan': profile.waktu_makan,
        'pola_waktu_makan': profile.pola_waktu_makan,
        'pola_puasa': profile.pola_puasa,
        'jam_makan_mulai': profile.jam_makan_mulai,
        'jam_makan_selesai': profile.jam_makan_selesai,
        'catatan_pola_makan': [],
    }
    return SimpleNamespace(model_dump=lambda: payload)


def test_diet_page_shows_target_recommendation_supported_and_coming_soon(
    client, db_session_factory, tmp_path, monkeypatch
):
    make_profile(client, db_session_factory)
    path = tmp_path / 'diets.csv'
    write_diets(path)
    monkeypatch.setenv('DIET_DATASET_PATH', str(path))

    response = client.get('/diet')

    assert response.status_code == 200
    assert '1.800' in response.text or '1800' in response.text
    assert 'Paling Direkomendasikan' in response.text
    assert 'Diet Mediterania' in response.text
    assert 'Diet Rendah Karbohidrat' in response.text
    assert 'Intermittent Fasting' in response.text
    assert 'Diet DASH' in response.text
    assert 'Coming Soon' in response.text


def test_supported_diet_and_if_are_independent(client, db_session_factory, tmp_path, monkeypatch):
    make_profile(client, db_session_factory)
    path = tmp_path / 'diets.csv'
    write_diets(path)
    monkeypatch.setenv('DIET_DATASET_PATH', str(path))
    from app.api.routes import user_portal

    monkeypatch.setattr(user_portal, 'analisis_user', fake_result)

    response = client.post('/api/activate-diet/mediterania', follow_redirects=False)
    assert response.status_code == 303

    response = client.post('/api/activate-intermittent-fasting', follow_redirects=False)
    assert response.status_code == 303

    with db_session_factory() as db:
        row = db.scalar(select(UserProfileDB))
        profile = json.loads(row.full_profile_data)
        analysis = json.loads(row.analysis_result)
        assert profile['active_diet'] == 'mediterania'
        assert profile['pola_waktu_makan'] == 'intermittent_fasting'
        assert profile['pola_puasa'] == '16:8'
        assert analysis['active_diet'] == 'mediterania'
        assert analysis['target_kalori'] == 1800

    response = client.post('/api/deactivate-intermittent-fasting', follow_redirects=False)
    assert response.status_code == 303
    with db_session_factory() as db:
        row = db.scalar(select(UserProfileDB))
        profile = json.loads(row.full_profile_data)
        assert profile['active_diet'] == 'mediterania'
        assert profile['pola_waktu_makan'] == 'normal'


def test_coming_soon_program_cannot_be_activated(client, db_session_factory, tmp_path, monkeypatch):
    make_profile(client, db_session_factory)
    path = tmp_path / 'diets.csv'
    write_diets(path)
    monkeypatch.setenv('DIET_DATASET_PATH', str(path))

    response = client.post('/api/activate-diet/dash', follow_redirects=False)

    assert response.status_code == 409
    with db_session_factory() as db:
        row = db.scalar(select(UserProfileDB))
        assert json.loads(row.full_profile_data)['active_diet'] is None


def test_coming_soon_detail_is_read_only(client, db_session_factory, tmp_path, monkeypatch):
    make_profile(client, db_session_factory)
    path = tmp_path / 'diets.csv'
    write_diets(path)
    monkeypatch.setenv('DIET_DATASET_PATH', str(path))

    response = client.get('/diet/dash')

    assert response.status_code == 200
    assert 'Coming Soon' in response.text
    assert 'Belum dapat diaktifkan' in response.text
