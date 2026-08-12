from app.rag.chunkers.csv_two_layer_chunker import BOOL_FIELDS, CsvTwoLayerChunker
from app.services.rag_artifact_service import RagArtifactWriter


def test_csv_chunk_payload_and_artifacts_preserve_all_flags(tmp_path):
    row = {
        'kode': 'F1',
        'nama_makanan': 'Apel',
        'kelompok_makanan': 'Buah',
        'jenis_bahan_utama': 'Buah',
        'tingkat_proses': 'Mentah bisa dimakan',
        'slot_meal_plan': 'Buah',
        'gula_g': '14',
        'mengandung_sayur': 'false',
        'adalah_gorengan': 'false',
        'sumber_karbohidrat': 'true',
        'karbohidrat_kompleks': 'false',
        'karbohidrat_olahan': 'false',
        'mengandung_susu': 'false',
        'mengandung_telur': 'false',
        'mengandung_seafood': 'false',
        'mengandung_kacang': 'false',
        'mengandung_babi': 'false',
        'mengandung_santan': 'false',
        'mengandung_alkohol': 'false',
    }
    chunk = CsvTwoLayerChunker().chunk_rows([row], 'food', 'food.csv')[0]
    payload = chunk.to_payload()

    for flag in BOOL_FIELDS:
        assert flag in payload
        assert isinstance(payload[flag], bool)
    assert payload['sugar_interpretation'] == 'natural_fruit_sugar'
    assert 'Sumber Karbohidrat:' not in chunk.content

    markdown_path, json_path = RagArtifactWriter().write_chunks(tmp_path, [chunk])
    markdown = markdown_path.read_text(encoding='utf-8')
    assert 'Sumber Karbohidrat: Ya' in markdown
    assert 'Adalah Gorengan: Tidak' in markdown
    assert '"sumber_karbohidrat": true' in json_path.read_text(encoding='utf-8')
