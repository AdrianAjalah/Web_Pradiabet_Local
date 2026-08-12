from app.services.structured_food_service import StructuredFoodService


def sample_foods():
    return [
        {"id":"1","nama":"Nasi Goreng","gram_porsi":200,"kalori_kkal":336,"karbohidrat_g":42.1,"protein_g":12.6,"lemak_g":12.5,"serat_g":1.4,"gula_g":1.5,"natrium_mg":830,"kelompok_makanan":"Makanan Utama","tingkat_proses":"Masakan","slot_meal_plan":"Makan Siang","is_recommended":False,"not_recommended_reasons":["natrium/sodium tinggi"]},
        {"id":"2","nama":"Rendang Sapi","gram_porsi":100,"kalori_kkal":195,"karbohidrat_g":5,"protein_g":20,"lemak_g":11,"serat_g":1.5,"gula_g":1,"natrium_mg":0,"kelompok_makanan":"Lauk Hewani","tingkat_proses":"Masakan","slot_meal_plan":"Makan Siang","is_recommended":True,"not_recommended_reasons":[]},
        {"id":"3","nama":"Rendang sapi, masakan","gram_porsi":100,"kalori_kkal":193,"karbohidrat_g":7.8,"protein_g":22.6,"lemak_g":7.9,"serat_g":0,"gula_g":0,"natrium_mg":0,"kelompok_makanan":"Lauk Hewani","tingkat_proses":"Masakan","slot_meal_plan":"Makan Siang","is_recommended":True,"not_recommended_reasons":[]},
        {"id":"4","nama":"Sagu Rendang","gram_porsi":100,"kalori_kkal":364,"karbohidrat_g":90.5,"protein_g":0.1,"lemak_g":0.2,"serat_g":1.9,"gula_g":0,"natrium_mg":42,"kelompok_makanan":"Makanan Pokok","tingkat_proses":"Masakan","slot_meal_plan":"Makan Siang","is_recommended":True,"not_recommended_reasons":[]},
        {"id":"5","nama":"Bubur Ayam","gram_porsi":240,"kalori_kkal":298,"karbohidrat_g":36,"protein_g":14,"lemak_g":10,"serat_g":2,"gula_g":1,"natrium_mg":700,"kelompok_makanan":"Makanan Utama","tingkat_proses":"Masakan","slot_meal_plan":"Sarapan","is_recommended":False,"not_recommended_reasons":["natrium/sodium tinggi"]},
    ]


def test_exact_lookup_returns_exact_food():
    service = StructuredFoodService(foods=sample_foods())
    result = service.lookup("nasi goreng")
    assert result["status"] == "found"
    assert result["food"]["nama"] == "Nasi Goreng"


def test_single_word_rendang_prioritizes_rendang_sapi_over_sagu_rendang():
    service = StructuredFoodService(foods=sample_foods())
    result = service.lookup("rendang")
    names = [item["nama"] for item in result["candidates"]]
    assert names[:2] == ["Rendang Sapi", "Rendang sapi, masakan"]
    assert names.index("Sagu Rendang") > 1


def test_ambiguous_lookup_returns_candidates():
    service = StructuredFoodService(foods=sample_foods())
    result = service.lookup("rendang")
    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) >= 3


def test_filter_foods_uses_numeric_constraints_and_sorting():
    service = StructuredFoodService(foods=sample_foods())
    results = service.filter_foods(max_calories=300, min_protein=14, sort_by="protein_g", descending=True, limit=5)
    assert [item["nama"] for item in results] == ["Rendang sapi, masakan", "Rendang Sapi", "Bubur Ayam"]
