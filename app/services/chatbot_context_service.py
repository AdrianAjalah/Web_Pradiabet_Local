"""Build grounded context for the PrediBeat nutrition chatbot."""
from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.bootstrap import build_pdf_retriever, build_retrievers
from app.database.models.progress import DailyProgressLogDB
from app.database.models.user import UserProfileDB
from app.services.common_utils import monday_of_week, today
from app.services.food_service import search_tracker_foods
from app.services.health_score_service import calculate_weekly_health_score
from app.services.progress_service import get_log_foods, summarize_week
from app.services.weekly_insight_service import build_weekly_insight

FOOD_TRIGGERS = {
    "makan", "minum", "kalori", "gula", "natrium", "sodium", "gi", "protein",
    "karbo", "lemak", "serat", "porsi", "aman", "boleh", "rekomendasi",
}
PROFILE_TRIGGERS = {
    "profil", "diet saya", "diet aktif", "meal plan", "menu saya", "menu hari ini",
    "progress", "health score", "skor", "aktivitas saya", "olahraga saya", "target saya",
}


def _decode(value: str | None) -> dict[str, Any]:
    try:
        data = json.loads(value or "{}")
        return data if isinstance(data, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _is_food_question(question: str) -> bool:
    q = str(question or "").casefold()
    return any(trigger in q for trigger in FOOD_TRIGGERS)


def _is_profile_question(question: str) -> bool:
    q = str(question or "").casefold()
    return any(trigger in q for trigger in PROFILE_TRIGGERS)


def build_profile_progress_context(db: Session, user_id: int) -> str:
    row = db.query(UserProfileDB).filter(UserProfileDB.user_id == user_id).first()
    if row is None:
        return "PROFIL USER: belum tersedia."
    profile = _decode(row.full_profile_data)
    analysis = _decode(row.analysis_result)

    lines = [
        "PROFIL DAN TARGET USER:",
        f"- Usia: {profile.get('usia', '-')} tahun",
        f"- Jenis kelamin: {profile.get('jenis_kelamin', '-')}",
        f"- Berat/Tinggi: {profile.get('berat_badan', '-')} kg / {profile.get('tinggi_badan', '-')} cm",
        f"- Kategori risiko: {analysis.get('kategori_risiko', '-')}",
        f"- Target kalori: {analysis.get('target_kalori', '-')} kkal",
        f"- Target makro: karbo {analysis.get('target_karbo', '-')} g, protein {analysis.get('target_protein', '-')} g, lemak {analysis.get('target_lemak', '-')} g",
        f"- Diet aktif: {analysis.get('active_diet_label') or analysis.get('active_diet') or profile.get('active_diet') or 'Tidak ada'}",
        f"- Pantangan/alergi: {profile.get('pantangan_alergi') or 'Tidak ada'}",
        f"- Kondisi/obat lain: {profile.get('penyakit_lain_obat') or 'Tidak ada'}",
    ]

    meal_plan = analysis.get("meal_plan") or []
    if meal_plan:
        lines.append("MEAL PLAN AKTIF:")
        for meal in meal_plan[:5]:
            label = meal.get("waktu") or meal.get("waktu_asli") or "Waktu makan"
            names = [str(item.get("nama") or item.get("name") or "Makanan") for item in (meal.get("items") or [])]
            lines.append(f"- {label}: {', '.join(names) if names else 'Belum ada menu'}")

    current = today()
    start = monday_of_week(current)
    end = start + timedelta(days=6)
    logs = (
        db.query(DailyProgressLogDB)
        .filter(
            DailyProgressLogDB.user_id == user_id,
            DailyProgressLogDB.tanggal >= start,
            DailyProgressLogDB.tanggal <= end,
        )
        .order_by(DailyProgressLogDB.tanggal.asc())
        .all()
    )
    summary = summarize_week(logs)
    health = calculate_weekly_health_score(logs)
    insight = build_weekly_insight(logs)
    lines.extend([
        "PROGRESS MINGGU INI:",
        f"- Hari tercatat: {summary.get('days_logged', 0)}/7",
        f"- Health Score: {health.get('score', 0)}/100 ({health.get('status', 'Belum ada data')})",
        f"- Aktivitas: {summary.get('total_exercise_minutes', 0)}/150 menit",
        f"- Rata-rata kalori: {summary.get('avg_actual_kalori', 0)} kkal/hari tercatat",
        f"- Insight: {insight.get('message') or health.get('summary') or 'Belum ada insight'}",
    ])

    today_log = next((log for log in logs if log.tanggal == current), None)
    if today_log:
        lines.extend([
            "CATATAN HARI INI:",
            f"- Kalori dimakan: {float(today_log.actual_kalori or 0):.0f} kkal",
            f"- Aktivitas: {today_log.activity_name or 'Tidak ada'} {float(today_log.duration_minutes or 0):g} menit",
        ])
        foods = get_log_foods(today_log)
        if foods:
            lines.append("- Makanan: " + ", ".join(str(food.get("nama") or "Makanan") for food in foods[:10]))
    else:
        lines.append("CATATAN HARI INI: belum ada.")
    return "\n".join(lines)


def build_local_food_context(question: str) -> str:
    if not _is_food_question(question):
        return ""
    foods = search_tracker_foods(question, limit=5)
    if not foods:
        # Coba kata kunci penting saja agar pertanyaan panjang tetap menemukan makanan.
        stopwords = {"apakah", "aman", "boleh", "untuk", "saya", "makan", "minum", "berapa", "porsi", "prediabetes"}
        terms = [term for term in re.findall(r"[a-z0-9]+", question.casefold()) if len(term) > 2 and term not in stopwords]
        for term in terms:
            foods = search_tracker_foods(term, limit=5)
            if foods:
                break
    if not foods:
        return (
            "DATA MAKANAN LOKAL: tidak ditemukan. Jangan mengarang angka nutrisi. "
            "Sampaikan bahwa data makanan belum tersedia di PrediBeat."
        )

    lines = [
        "DATA MAKANAN LOKAL:",
        "Gunakan hanya field gula_g untuk pembahasan gula.",
    ]
    for food in foods:
        fruit_note = "; gula alami buah" if food.get("is_fruit") else ""
        reasons = ", ".join(food.get("not_recommended_reasons") or []) or "-"
        lines.append(
            f"- {food.get('nama')} | kategori {food.get('kelompok_makanan') or '-'} | "
            f"kalori {food.get('kalori_kkal', 0)} kkal | gula_g {food.get('gula_g', 0)} g | "
            f"natrium {food.get('natrium_mg', 0)} mg | "
            f"status {'direkomendasikan' if food.get('is_recommended') else 'perlu dibatasi'} | "
            f"alasan {reasons}{fruit_note}"
        )
    lines.append(
        "Khusus kategori Buah, gula alami buah tidak diperlakukan seperti gula pada minuman manis, snack, dessert, atau makanan ultra-proses."
    )
    return "\n".join(lines)


def _result_text(item: dict[str, Any]) -> str:
    if item.get("answer"):
        return f"Pertanyaan: {item.get('question', '')}\nJawaban: {item.get('answer')}"
    return str(item.get("content") or item.get("text") or "").strip()


def build_rag_context(
    question: str,
    retrievers_factory: Callable[[], Any] = build_pdf_retriever,
) -> tuple[str, str, float]:
    if _is_profile_question(question):
        return "", "Profil User / Meal Plan / Progress", 1.0
    try:
        retriever_result = retrievers_factory()
        pdf_retriever = retriever_result[0] if isinstance(retriever_result, tuple) else retriever_result
        # Fakta makanan diambil dari database terstruktur lokal.
        # Qdrant remains active only for PDF education/reference retrieval.
        results: list[dict[str, Any]] = []
        results.extend(pdf_retriever.search(question, limit=5))
        results = sorted(results, key=lambda item: float(item.get("score") or 0), reverse=True)[:5]
        texts = [_result_text(item) for item in results]
        texts = [text for text in texts if text]
        confidence = max((float(item.get("score") or 0) for item in results), default=0.0)
        sources = [str(item.get("source_name") or item.get("collection") or "RAG V2") for item in results]
        return "\n\n---\n\n".join(texts), (sources[0] if sources else "RAG V2"), confidence
    except Exception:
        return "", "Data Profil & Dataset Lokal", 0.0

