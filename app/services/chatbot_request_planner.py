"""Request-plan schema and deterministic Indonesian fallback parser."""
from __future__ import annotations

import re
from typing import Any


class DeterministicRequestPlanner:
    GREETINGS = {"hai", "halo", "hello", "hi", "pagi", "siang", "sore", "malam", "assalamualaikum"}
    NUTRIENT_FIELDS = {
        "kalori": "kalori_kkal", "kalorinya": "kalori_kkal", "energi": "kalori_kkal",
        "protein": "protein_g", "gula": "gula_g", "serat": "serat_g",
        "lemak": "lemak_g", "karbo": "karbohidrat_g", "karbohidrat": "karbohidrat_g",
        "natrium": "natrium_mg", "sodium": "natrium_mg",
    }

    @staticmethod
    def _clean(text: str) -> str:
        text = str(text or "").casefold().replace("\\", " ")
        text = re.sub(r"[^a-z0-9, +.-]+", " ", text)
        return re.sub(r"\s+", " ", text).strip(" ,.?")

    def plan(self, question: str) -> dict[str, Any]:
        q = self._clean(question)
        if not q:
            return {"intent": "general_chat"}
        if q in self.GREETINGS or any(q.startswith(g + " ") for g in self.GREETINGS):
            return {"intent": "greeting"}
        if re.search(r"\b(siapa|presiden|ibukota|cuaca|sepak bola|politik)\b", q):
            return {"intent": "out_of_scope"}

        # Pertanyaan yang secara eksplisit merujuk jurnal, dokumen, penelitian,
        # laporan, atau data harus selalu masuk ke jalur PDF RAG. Ini mencakup
        # pertanyaan fakta/kalimat rumpang seperti "Menurut data ... adalah".
        document_reference = re.search(
            r"\b(?:menurut|berdasarkan)\s+(?:data|jurnal|dokumen|penelitian|laporan|artikel|referensi|sumber)\b"
            r"|\b(?:dalam|di)\s+(?:jurnal|dokumen|pdf|artikel|penelitian|laporan)\b",
            q,
        )
        education_question = (
            re.search(r"\b(kenapa|mengapa|jelaskan|apa fungsi|manfaat|pedoman|referensi)\b", q)
            and re.search(r"\b(prediabetes|gula darah|nutrisi|serat|protein|karbohidrat|makan|pangan|beras|kesehatan|gizi)\b", q)
        )
        if document_reference or education_question:
            return {"intent": "pdf_education", "question": question}
        if "bandingkan" in q or re.search(r"\blebih (baik|sehat)\b", q):
            body = re.sub(r".*?(?:bandingkan|lebih baik|lebih sehat)\s+", "", q)
            names = [part.strip() for part in re.split(r"\s+(?:dan|atau|dengan)\s+", body) if part.strip()]
            return {"intent": "compare_foods", "food_names": names[:3]}
        if "total" in q and ("makan" in q or "konsumsi" in q):
            body = re.sub(r"^.*?\b(?:makan|konsumsi)\b\s*", "", q)
            body = re.sub(r"\bberapa\b.*$", "", body)
            body = re.sub(r"\btotal\b.*$", "", body)
            names = [part.strip(" ,.") for part in re.split(r"\s+(?:dan|serta)\s+|\s*,\s*", body) if part.strip(" ,.")]
            return {"intent": "meal_total", "items": [{"food_name": name, "quantity": 1} for name in names[:8]]}
        if re.search(r"\b(cari|rekomendasi|rekomendasikan|pilihkan)\b", q):
            intent = "recommend_foods" if re.search(r"\b(rekomendasi|rekomendasikan|pilihkan)\b", q) else "food_filter"
            plan: dict[str, Any] = {"intent": intent, "limit": 5}
            patterns = {
                "max_calories": r"kalori\s+(?:maksimal|di bawah|kurang dari)\s*(\d+(?:\.\d+)?)",
                "min_protein": r"protein\s+(?:minimal|di atas|lebih dari)\s*(\d+(?:\.\d+)?)",
                "max_sugar": r"gula\s+(?:maksimal|di bawah|kurang dari)\s*(\d+(?:\.\d+)?)",
                "min_fiber": r"serat\s+(?:minimal|di atas|lebih dari)\s*(\d+(?:\.\d+)?)",
            }
            for key, pattern in patterns.items():
                match = re.search(pattern, q)
                if match:
                    plan[key] = float(match.group(1))
            if "protein tertinggi" in q or "tinggi protein" in q:
                plan.update(sort_by="protein_g", descending=True)
            elif "serat tertinggi" in q or "tinggi serat" in q:
                plan.update(sort_by="serat_g", descending=True)
            elif "gula terendah" in q or "rendah gula" in q:
                plan.update(sort_by="gula_g", descending=False)
            elif "kalori terendah" in q or "rendah kalori" in q:
                plan.update(sort_by="kalori_kkal", descending=False)
            return plan

        requested = []
        for token, field in self.NUTRIENT_FIELDS.items():
            if re.search(rf"\b{re.escape(token)}\b", q) and field not in requested:
                requested.append(field)
        food_name = q
        prefixes = [
            r"^saya (?:pengen|ingin|mau) makan\s+",
            r"^kira kira\s+", r"^berapa\s+(?:kalori|protein|gula|serat|lemak|karbohidrat|karbo|natrium|sodium)\s+(?:dari|pada)?\s*",
            r"^(?:berapa|cek|tampilkan|lihat)\s+(?:nutrisi|kandungan)\s+",
        ]
        for pattern in prefixes:
            food_name = re.sub(pattern, "", food_name)
        food_name = re.sub(r"\s+kira[- ]kira.*$", "", food_name)
        food_name = re.sub(r"\s+berapa\s+(?:ya|yah|kalorinya|proteinnya).*$", "", food_name)
        food_name = re.sub(r"\s+(?:berapa|apa saja)\s*$", "", food_name)
        for token in self.NUTRIENT_FIELDS:
            food_name = re.sub(rf"\b{re.escape(token)}(?:nya)?\b", "", food_name)
        food_name = re.sub(r"\b(dari|pada|nya|yah|ya|dong)\b", "", food_name)
        food_name = re.sub(r"\s+", " ", food_name).strip(" ,.")
        if food_name:
            return {"intent": "food_lookup", "food_name": food_name, "requested_fields": requested}
        return {"intent": "general_chat"}
