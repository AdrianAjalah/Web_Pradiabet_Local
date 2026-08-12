from app.rag.chunkers.csv_two_layer_chunker import CsvTwoLayerChunker


def test_csv_chunker_has_two_layers_and_natural_fruit_sugar_note():
    rows = [
        {
            "kode": "B01",
            "nama_makanan": "Pisang",
            "kelompok_makanan": "Buah",
            "gula_g": "12",
            "kalori_kkal": "89",
            "slot_meal_plan": "snack",
        },
        {
            "kode": "M01",
            "nama_makanan": "Minuman Manis",
            "kelompok_makanan": "Minuman",
            "gula_g": "15",
            "kalori_kkal": "160",
            "slot_meal_plan": "snack",
        },
    ]

    chunks = CsvTwoLayerChunker().chunk_rows(rows, source_id="food-v1", source_name="food.csv")

    assert {chunk.layer for chunk in chunks} == {0, 1}
    banana = next(chunk for chunk in chunks if chunk.metadata.get("food_name") == "pisang")
    drink = next(chunk for chunk in chunks if chunk.metadata.get("food_name") == "minuman manis")
    assert "gula alami" in banana.content.lower()
    assert "perlu dibatasi" in drink.content.lower()
    assert not any(chunk.chunk_type == "qa" for chunk in chunks)


def test_food_row_keeps_structured_nutrition_metadata_for_retrieval():
    rows = [
        {
            "kode": "B01",
            "nama_makanan": "Pisang",
            "kelompok_makanan": "Buah",
            "gula_g": "12",
            "kalori_kkal": "89",
            "karbohidrat_g": "23",
            "protein_g": "1.1",
            "lemak_g": "0.3",
            "serat_g": "2.6",
            "natrium_mg": "1",
            "indeks_glikemik": "51",
            "slot_meal_plan": "snack",
        }
    ]

    chunk = CsvTwoLayerChunker().chunk_rows(rows, "food-v1", "food.csv")[0]

    assert chunk.metadata["gula_g"] == 12.0
    assert chunk.metadata["kalori_kkal"] == 89.0
    assert chunk.metadata["karbohidrat_g"] == 23.0
    assert chunk.metadata["is_fruit"] is True
    assert chunk.metadata["sugar_interpretation"] == "natural_fruit_sugar"
