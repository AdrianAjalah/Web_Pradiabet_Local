"""Deterministic program recommendations from an existing user profile.

The output is decision support only. It does not auto-activate a diet and does
not replace professional medical advice.
"""
from __future__ import annotations

from typing import Any


PROGRAM_NAMES = {
    "mediterania": "Diet Mediterania",
    "rendah_karbo": "Diet Rendah Karbohidrat",
    "intermittent_fasting": "Intermittent Fasting",
}


def _text(value: Any) -> str:
    return str(value or "").strip().casefold()


def _contains_any(value: Any, terms: tuple[str, ...]) -> bool:
    text = _text(value)
    return any(term in text for term in terms)


def _clamp_score(value: float) -> int:
    return int(max(0, min(100, round(value))))


def recommend_programs(profile: dict[str, Any], analysis: dict[str, Any]) -> list[dict[str, Any]]:
    target_kalori = int(round(float(analysis.get("target_kalori") or 0)))
    risk = _text(analysis.get("kategori_risiko"))
    bmi = float(analysis.get("bmi") or 0)
    disease = _text(profile.get("penyakit_lain_obat"))
    lab = _text(profile.get("hasil_lab"))
    sweet = _text(profile.get("frekuensi_minum_manis"))
    rice = _text(profile.get("porsi_nasi_per_hari"))
    eating_frequency = _text(profile.get("frekuensi_makan"))
    time_pattern = _text(profile.get("pola_waktu_makan"))
    age = int(profile.get("usia") or 0)

    med_score = 55.0
    med_reasons = ["Pola ini seimbang dan dapat mengikuti target kalori harian Anda."]
    med_warning = ""
    if any(term in risk for term in ("tinggi", "prediabetes", "diabetes")):
        med_score += 12
        med_reasons.append("Profil menunjukkan risiko metabolik yang perlu didukung kualitas makanan lebih baik.")
    if _contains_any(disease, ("hipertensi", "tensi", "kolesterol", "jantung")):
        med_score += 18
        med_reasons.append("Riwayat kesehatan Anda mendukung prioritas sayur, ikan, serat, dan lemak tidak jenuh.")
    if bmi >= 23:
        med_score += 8
        med_reasons.append("Target kalori dan berat badan dapat dijalankan dengan pola makan seimbang jangka panjang.")

    low_score = 45.0
    low_reasons = ["Target kalori tetap dipertahankan, sementara porsi karbo dikontrol lebih ketat."]
    low_warning = ""
    if _contains_any(sweet, ("setiap hari", "sering")):
        low_score += 26
        low_reasons.append("Frekuensi konsumsi manis Anda tinggi.")
    elif _contains_any(sweet, ("3-5", "3–5")):
        low_score += 16
        low_reasons.append("Konsumsi manis beberapa kali per minggu perlu dikendalikan.")
    if _contains_any(rice, ("lebih dari 2", ">2")):
        low_score += 22
        low_reasons.append("Porsi nasi harian Anda relatif tinggi.")
    elif "2 porsi" in rice:
        low_score += 10
        low_reasons.append("Porsi karbo harian dapat dikontrol lebih terarah.")
    if any(term in risk for term in ("tinggi", "prediabetes", "diabetes")) or _contains_any(
        lab, ("prediabetes", "hba1c", "gula darah", "gdp")
    ):
        low_score += 12
        low_reasons.append("Hasil risiko/laboratorium mendukung pengendalian karbohidrat yang lebih terukur.")
    if _contains_any(disease, ("ginjal", "dialisis", "gagal ginjal")):
        low_score -= 30
        low_warning = "Perlu konsultasi tenaga kesehatan karena perubahan makro harus disesuaikan dengan kondisi ginjal."

    if_score = 30.0
    if_reasons = ["IF hanya mengatur waktu makan; target kalori dan diet makanan tetap terpisah."]
    if_warning = ""
    if time_pattern == "intermittent_fasting":
        if_score += 25
        if_reasons.append("Anda sudah memilih pola Intermittent Fasting pada questionnaire.")
    if eating_frequency.startswith("2"):
        if_score += 12
        if_reasons.append("Frekuensi makan dua kali sehari lebih mudah ditempatkan dalam jendela makan.")
    risky_if_terms = (
        "insulin",
        "hipoglikemia",
        "hamil",
        "menyusui",
        "gangguan makan",
        "maag berat",
        "ulkus",
    )
    if age and age < 18:
        if_score -= 50
        if_warning = "IF tidak disarankan untuk pengguna di bawah 18 tahun tanpa pengawasan tenaga kesehatan."
    elif _contains_any(disease, risky_if_terms):
        if_score -= 40
        if_warning = "Perlu konsultasi tenaga kesehatan sebelum membatasi waktu makan karena kondisi/obat yang dicantumkan."

    rows = [
        {
            "id": "mediterania",
            "name": PROGRAM_NAMES["mediterania"],
            "program_type": "diet",
            "score": _clamp_score(med_score),
            "reasons": med_reasons,
            "warning": med_warning,
            "needs_consultation": bool(med_warning),
            "target_kalori": target_kalori,
        },
        {
            "id": "rendah_karbo",
            "name": PROGRAM_NAMES["rendah_karbo"],
            "program_type": "diet",
            "score": _clamp_score(low_score),
            "reasons": low_reasons,
            "warning": low_warning,
            "needs_consultation": bool(low_warning),
            "target_kalori": target_kalori,
        },
        {
            "id": "intermittent_fasting",
            "name": PROGRAM_NAMES["intermittent_fasting"],
            "program_type": "time_pattern",
            "score": _clamp_score(if_score),
            "reasons": if_reasons,
            "warning": if_warning,
            "needs_consultation": bool(if_warning),
            "target_kalori": target_kalori,
        },
    ]
    return sorted(rows, key=lambda item: (-item["score"], item["id"]))
