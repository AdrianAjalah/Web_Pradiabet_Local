"""Deterministic personal menus and food checks; drafts never mutate a profile."""
from __future__ import annotations

from copy import deepcopy
from difflib import SequenceMatcher
import hashlib
import json
import re
from html import escape

from app.services.food_service import load_nutrition_foods, recommendation_reasons
from app.user.action_service import UserActionError, UserProgramActionService
from app.user.assessment import _filter_foods_for_pantangan, _evaluasi_kesesuaian_meal_plan
from app.services.common_utils import today


def normalize(text):
    return re.sub(r"[^\w]+", " ", str(text).casefold()).strip()


def similar_foods(name, foods, limit=5):
    """Suggest candidates without treating a partial/typo match as an identity.

    Every query token must have a close counterpart: a missing qualifier such
    as seafood must not silently turn into ordinary fried rice.
    """
    def tokens(text):
        return ['mie' if word == 'mi' else word for word in normalize(text).split()]

    query = tokens(name)
    if not query:
        return []
    ranked = []
    seen = set()
    for food in foods:
        candidate = tokens(food.get('nama', ''))
        key = normalize(food.get('nama', ''))
        if not candidate or key in seen:
            continue
        # Consume tokens so one word cannot satisfy two different query words.
        remaining = list(candidate)
        scores = []
        for word in query:
            if not remaining:
                break
            matches = [1.0 if word == other else
                       SequenceMatcher(None, word, other).ratio() if min(len(word), len(other)) >= 4 else 0.0
                       for other in remaining]
            best = max(matches)
            if best < 0.8:
                break
            remaining.pop(matches.index(best))
            scores.append(best)
        if len(scores) != len(query):
            continue
        seen.add(key)
        rank = (sum(scores) / len(scores), -len(remaining), SequenceMatcher(None, ' '.join(query), ' '.join(candidate)).ratio())
        ranked.append((rank, key, food))
    ranked.sort(key=lambda entry: (tuple(-value for value in entry[0]), entry[1]))
    return [food for _, _, food in ranked[:limit]]


def meal_scope(question):
    q = normalize(question)
    for name in ("pagi", "siang", "sore", "malam"):
        if re.search(rf"\b{name}\b", q):
            return name
    match = re.search(r"\bmakan ([123])\b", q)
    return f"makan {match[1]}" if match else None


def personal_intent(question):
    q = normalize(question)
    profile_query = not re.search(r'\b(rekomendasi\w*|makan|makanan|menu|boleh|aman|ganti|ubah|hapus|edit|perbarui)\b', q)
    if (re.search(r'\bprofil(?: kesehatan)?(?: saya| aku|ku)?\b', q)
            and re.search(r'\b(cek|lihat|tampilkan|ringkas|bagaimana|gimana|apa|saya|aku)\b', q)
            and profile_query):
        return 'profile'
    if profile_query and re.search(r'\b(usia|umur|berat badan|tinggi badan|hasil lab|hba1c|gula darah|target kalori|target protein|target karbohidrat|pantangan|alergi)\s+(saya|aku)\b', q):
        return 'profile'
    if re.search(r"\b(buat ulang|generate ulang|regenerate|acak|ganti|ubah|perbarui)\b.*\b(menu|meal plan|makan|makanan)\b|\b(cari menu lain|tidak suka|nggak suka|ngga suka|gak suka|kurang cocok|menu lain|makanan lain)\b", q):
        return "preview"
    if re.search(r"\b(rekomendasi\w*|rekomendasiin|saran\w*|pilihkan)\b", q) and re.search(r"\b(makan\w*|menu|meal plan)\b", q):
        return "recommend"
    if re.search(r"\b(menu|meal plan)\b.*\b(saya|hari ini)\b|\bmakan(?:an)? apa\b", q):
        return "recommend"
    if re.search(r"\b(boleh|aman|sehat|baik|direkomendasikan)\b", q) and re.search(r"\b(makan\w*|minum\w*)\b", q):
        return "check"
    if re.search(r"\b(boleh|aman|sehat|baik)\b", q) and not re.search(r"\b(mengapa|kenapa|jelaskan)\b", q):
        return "check"
    return None


def selected_meals(meals, scope):
    if not scope:
        return meals
    return [m for m in meals if scope in {normalize(m.get("waktu")), normalize(m.get("waktu_asli")), normalize(m.get("waktu")).removeprefix("makan ")}]


def signature(meals):
    return json.dumps([[m.get("waktu"), [(i.get("nama"), i.get("gram_porsi"), i.get("porsi")) for i in m.get("items", [])]] for m in meals], ensure_ascii=False, sort_keys=True)


def snapshot(row):
    return hashlib.sha256((str(row.full_profile_data) + str(row.analysis_result)).encode()).hexdigest()


def menu_text(meals):
    lines = []
    for meal in meals:
        lines.append(f"\n{meal.get('waktu', 'Menu')}" + (f" ({meal['jam']})" if meal.get('jam') else ""))
        total = dict(kalori=0.0, karbo=0.0, protein=0.0, lemak=0.0)
        for food in meal.get("items", []):
            portion = food.get("porsi") or (f"{food['gram_porsi']:g} g" if isinstance(food.get('gram_porsi'), (int, float)) else "porsi belum tersedia")
            kcal = food.get("kalori")
            calories = f"{float(kcal):g} kkal" if kcal is not None else "kalori belum tersedia"
            lines.append(f"- {food.get('slot_label') or food.get('slot_meal_plan') or 'Makanan'}: {food.get('nama')} — {portion}, {calories}.")
            for key in total:
                total[key] += float(food.get(key) or 0)
        if meal.get("items") and all(all(i.get(k) is not None for k in total) for i in meal['items']):
            lines.append(f"Total: {total['kalori']:g} kkal; karbohidrat {total['karbo']:g} g, protein {total['protein']:g} g, lemak {total['lemak']:g} g.")
    return "\n".join(lines)


class PersonalChatService:
    def __init__(self, db, *, program=None, foods=None):
        self.program = program or UserProgramActionService(db)
        self.foods = foods

    def profile_summary(self, user_id):
        _, profile, analysis = self.state(user_id)
        if not isinstance(profile, dict) or not isinstance(analysis, dict):
            raise UserActionError('Data profil tidak dapat dibaca. Silakan periksa halaman profil kesehatan.')

        def value(data, key, unit='', positive=False):
            raw = data.get(key)
            if raw is None or raw == '' or raw == []:
                return 'Belum diisi'
            if positive:
                try:
                    number = float(raw)
                    if not 0 < number < float('inf'):
                        return 'Belum diisi'
                    return f'{number:g}{unit}'
                except (TypeError, ValueError):
                    return 'Data tidak valid'
            if isinstance(raw, list):
                return escape(', '.join(str(item) for item in raw))
            return escape(str(raw)) + unit

        lines = ['Berikut profil kesehatan yang tersimpan pada akun Anda:', '', '**Data diri**']
        for key, label, unit, positive in [
            ('usia', 'Usia', ' tahun', True), ('jenis_kelamin', 'Jenis kelamin', '', False),
            ('berat_badan', 'Berat badan', ' kg', True), ('tinggi_badan', 'Tinggi badan', ' cm', True),
            ('lingkar_pinggang', 'Lingkar pinggang', ' cm', True),
        ]:
            lines.append(f'- {label}: {value(profile, key, unit, positive)}')
        lines.extend(['', '**Kesehatan dan pantangan**',
            '- Pantangan/alergi: ' + value(profile, 'pantangan_alergi'),
            '- Kondisi lain/obat rutin: ' + value(profile, 'penyakit_lain_obat'),
            '- Hasil lab yang Anda masukkan: ' + value(profile, 'hasil_lab'),
            '- Kategori risiko hasil assessment aplikasi: ' + value(analysis, 'kategori_risiko'),
            '', '**Target dan jadwal makan**'])
        for key, label, unit in [('target_kalori', 'Kalori', ' kkal/hari'), ('target_karbo', 'Karbohidrat', ' g/hari'),
                                 ('target_protein', 'Protein', ' g/hari'), ('target_lemak', 'Lemak', ' g/hari')]:
            lines.append(f'- {label}: {value(analysis, key, unit, True)}')
        diet = analysis.get('active_diet_label') or analysis.get('active_diet') or profile.get('active_diet')
        labels = {'mediterania': 'Mediterranean', 'rendah_karbo': 'Low Carbohydrate'}
        lines.append('- Diet aktif: ' + (escape(labels.get(diet, str(diet))) if diet else 'Belum memilih diet'))
        lines.append('- Waktu makan pilihan Anda: ' + value(profile, 'waktu_makan'))
        lines.extend(['', 'Kategori risiko di atas adalah hasil assessment aplikasi, bukan diagnosis baru dari chatbot.',
                      'Jika ada data yang perlu diperbarui, buka [Profil kesehatan](/questionnaire).'])
        return '\n'.join(lines)

    def state(self, user_id):
        row = self.program._row(user_id)
        profile, analysis = self.program._decode(row)
        return row, profile, analysis

    @staticmethod
    def ensure_allowed(meals, profile):
        for meal in meals:
            items = meal.get("items", [])
            if len(_filter_foods_for_pantangan(items, profile.get("pantangan_alergi"))) != len(items):
                raise UserActionError("Meal plan memuat makanan yang bertentangan dengan pantangan profil. Buat kandidat menu baru terlebih dahulu.")

    def recommend(self, user_id, scope=None):
        row, profile, analysis = self.state(user_id)
        meals = selected_meals(analysis.get("meal_plan") or [], scope)
        if not meals:
            raise UserActionError("Menu tersebut belum tersedia pada meal plan aktif. Periksa jadwal dan assessment pada profil Anda.")
        self.ensure_allowed(meals, profile)
        return {
            "type": "meal_plan_display", "scope": scope, "base_snapshot": snapshot(row),
            "seen": [signature(meals)], "title": "Meal plan aktif Anda",
            "message": "Berikut menu yang sudah tersimpan sesuai jadwal profil Anda." + menu_text(meals),
            "confirm_label": "Pakai menu ini",
        }

    def preview(self, user_id, scope=None, previous=None):
        row, profile, analysis = self.state(user_id)
        active = analysis.get("meal_plan") or []
        if not active or (scope and not selected_meals(active, scope)):
            raise UserActionError("Meal plan untuk jadwal tersebut belum tersedia. Lengkapi assessment terlebih dahulu.")
        seen = list(previous.get("seen", [])) if previous and previous.get("base_snapshot") == snapshot(row) else []
        seen.append(signature(selected_meals(active, scope)))
        for _ in range(6):
            generated = self.program.regenerate_meal_plan(user_id, preview=True)["meal_plan"]
            if scope:
                replacement = selected_meals(generated, scope)
                if len(replacement) != 1:
                    continue
                candidate = [deepcopy(replacement[0]) if m in selected_meals(active, scope) else deepcopy(m) for m in active]
            else:
                candidate = generated
            proposed = selected_meals(candidate, scope)
            if not proposed or any(not m.get("items") for m in candidate):
                continue
            self.ensure_allowed(candidate, profile)
            key = signature(proposed)
            if key in seen:
                continue
            validation = _evaluasi_kesesuaian_meal_plan(
                candidate, analysis.get("target_kalori", 0), analysis.get("target_karbo", 0),
                analysis.get("target_protein", 0), analysis.get("target_lemak", 0), analysis.get("kategori_risiko", ""),
            )
            if not validation.get("lolos_gula_tambahan") or not validation.get("lolos_sodium"):
                continue
            note = ""
            if not validation.get("lolos_toleransi"):
                note = "\nCatatan: kandidat belum memenuhi seluruh toleransi target kalori/makro. Periksa total menu sebelum memilih."
            return {
                "type": "replace_meal_plan", "scope": scope, "base_snapshot": snapshot(row),
                "candidate": deepcopy(candidate), "validation": validation,
                "seen": (seen + [key])[-40:], "title": "Kandidat menu baru",
                "message": "Menu aktif belum berubah. Sebagian makanan dapat tetap sama." + menu_text(proposed) + note,
                "confirm_label": "Pakai menu ini",
            }
        raise UserActionError("Belum menemukan kandidat berbeda yang memenuhi batas menu dalam pencarian ini. Menu aktif tetap tersimpan; Anda dapat mencoba lagi.")

    def apply(self, user_id, action):
        row, profile, analysis = self.state(user_id)
        if action.get("type") != "replace_meal_plan" or snapshot(row) != action.get("base_snapshot"):
            raise UserActionError("Profil atau menu sudah berubah, atau belum ada kandidat. Minta kandidat baru sebelum menyimpan.")
        candidate = action["candidate"]
        self.ensure_allowed(candidate, profile)
        analysis['meal_plan'] = deepcopy(candidate)
        analysis['meal_plan_date'] = today().isoformat()
        from app.user.assessment import _catatan_validasi_meal_plan
        notes = [n for n in analysis.get('catatan_pola_makan', []) if not str(n).startswith('Validasi meal plan:')]
        notes.append(_catatan_validasi_meal_plan(action['validation']))
        analysis['catatan_pola_makan'] = notes
        self.program._save(row, profile, analysis)
        self.program.db.flush()
        return {"message": "Menu pilihan Anda berhasil disimpan.", "meal_plan": candidate}

    def check(self, user_id, question):
        _, profile, analysis = self.state(user_id)
        q = normalize(question)
        match = re.search(r"\b(?:makan|makanan|minum|minuman)\s+(.+)", q)
        name = match[1] if match else q
        name = re.sub(r"^(?:(?:apakah|apa|saya|boleh|aman|sehat|baik|itu|makan|makanan|minum|minuman)\s+)+", "", name)
        name = re.sub(r"\s+(?:untuk saya|hari ini|itu|aman|sehat|boleh|baik|tidak|nggak|ngga|gak|ya|yah|dong)\b.*$", "", name).strip()
        foods = self.foods if self.foods is not None else load_nutrition_foods()
        exact = [food for food in foods if normalize(food.get('nama')) == name]
        if len(exact) != 1:
            candidates = similar_foods(name, foods)
            if not candidates:
                return f"Di dataset saya belum ada kecocokan pasti untuk '{name}', dan belum ditemukan nama yang cukup mirip. Saya tidak dapat memastikan kandungan atau angka nutrisinya. Gunakan nama lengkap yang ada pada dataset."
            lines = [f"Di dataset saya belum ada satu kecocokan pasti untuk '{name}'. Berikut nama yang mirip; setiap penilaian di bawah berlaku untuk nama kandidat tersebut, bukan otomatis untuk makanan yang Anda maksud:"]
            unsuitable = False
            for index, food in enumerate(candidates, 1):
                details, rejected = self.food_evaluation(food, profile)
                lines.append(f"\n{index}. " + '\n'.join(details))
                unsuitable = unsuitable or rejected
            lines.append("\nSebutkan nama lengkap salah satu kandidat di atas jika itu yang Anda maksud.")
        else:
            lines, unsuitable = self.food_evaluation(exact[0], profile)
        meals = selected_meals(analysis.get('meal_plan') or [], meal_scope(question))
        if meals and unsuitable:
            try:
                self.ensure_allowed(meals, profile)
                checked = exact if len(exact) == 1 else candidates
                slots = {normalize(f.get('slot_meal_plan', '')) for f in checked} - {'', 'no meal'}
                alternatives = []
                for meal in meals:
                    for item in meal.get('items', []):
                        if normalize(item.get('slot_meal_plan', '')) in slots:
                            portion = item.get('porsi') or f"{item.get('gram_porsi', 100):g} g"
                            suggestion = f"{item.get('nama')} ({portion}, menu {meal.get('waktu', '')})"
                            if suggestion not in alternatives:
                                alternatives.append(suggestion)
                if alternatives:
                    lines.append('Alternatif dari meal plan Anda: ' + '; '.join(alternatives[:2]) + '.')
                else:
                    lines.append('Untuk pilihan pengganti, Anda bisa meminta rekomendasi dari meal plan aktif.')
            except UserActionError:
                lines.append("Meal plan aktif perlu dibuat ulang agar sesuai pantangan profil.")
        return "\n".join(lines)

    @staticmethod
    def food_evaluation(food, profile):
        reasons = recommendation_reasons(food)
        blocked = not _filter_foods_for_pantangan([food], profile.get('pantangan_alergi'))
        lines = [f"{food['nama']}:"]
        if blocked:
            lines.append(f"Tidak sesuai pantangan yang Anda catat pada profil: {profile.get('pantangan_alergi')}.")
        if reasons:
            lines.append("Sebaiknya tidak dijadikan pilihan menu Anda karena " + ", ".join(reasons) + ".")
            if "natrium/sodium tinggi" in reasons:
                lines.append(f"Dataset mencatat natrium {food['natrium_mg']:g} mg per {food.get('gram_porsi', 100):g} g.")
            if "gula tinggi" in reasons:
                lines.append(f"Dataset mencatat gula {food['gula_g']:g} g per {food.get('gram_porsi', 100):g} g.")
        if not reasons and not blocked:
            lines.append("Makanan ini ada di dataset dan bisa dipertimbangkan: tidak ada kecocokan dengan pantangan profil atau alasan penolakan yang terdeteksi. Tetap sesuaikan porsinya dengan meal plan Anda.")
        if food.get('missing_nutrients'):
            labels = {'gula_g': 'gula', 'natrium_mg': 'natrium', 'lemak_g': 'lemak', 'protein_g': 'protein', 'karbohidrat_g': 'karbohidrat'}
            lines.append('Data belum lengkap untuk ' + ', '.join(labels.get(k, k) for k in food['missing_nutrients']) + '. Nilai kosong bukan berarti kandungannya nol.')
        return lines, bool(reasons or blocked)
