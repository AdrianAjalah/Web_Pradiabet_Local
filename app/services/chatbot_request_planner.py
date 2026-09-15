"""Request-plan schema and deterministic Indonesian fallback parser."""
from __future__ import annotations

import re
from typing import Any


class DeterministicRequestPlanner:
    @staticmethod
    def _meal_total_plan(q: str) -> dict[str, Any] | None:
        """Parse explicit food-total questions without asking an LLM."""
        if "total" not in q or not re.search(r"\b(?:kalori|nutrisi)\b", q):
            return None

        body = ""
        prefix = re.match(
            r"^(?:berapa\s+)?total\s+(?:kalori|nutrisi)(?:nya)?\s+(?:dari\s+)?(.+)$",
            q,
        )
        action = re.match(
            r"^.*?\b(?:makan|konsumsi)\b\s+(.+?)\s+berapa\s+total\s+(?:kalori|nutrisi)\b.*$",
            q,
        )
        suffix = re.match(
            r"^(.+?)\s+(?:berapa\s+)?total\s+(?:kalori|nutrisi)(?:nya)?(?:\s+berapa)?$",
            q,
        )
        if prefix:
            body = prefix.group(1)
        elif action:
            body = action.group(1)
        elif suffix:
            body = suffix.group(1)
        else:
            return None

        body = re.sub(r"^(?:yang\s+)?(?:saya\s+)?(?:makan|konsumsi)\s+(?:dari\s+)?", "", body)
        body = re.sub(r"\s+yang\s+saya\s+(?:makan|konsumsi)\s*$", "", body)
        names = [
            part.strip(" ,.")
            for part in re.split(r"\s+(?:dan|serta|sama|dengan)\s+|\s*[,+]\s*", body)
            if part.strip(" ,.")
        ]
        if not names or any(name in {"saya", "hari ini", "saya hari ini"} for name in names):
            return None
        return {"intent": "meal_total", "items": [{"food_name": name, "quantity": 1} for name in names[:8]]}

    def fast_plan(self, question: str) -> dict[str, Any] | None:
        """Only bypass the model for explicit, self-contained requests."""
        q = self._clean(question)
        if q in self.GREETINGS:
            return {"intent": "greeting"}
        # Total makanan adalah operasi terstruktur. Parse di backend agar nama
        # makanan dan aritmetika tidak pernah bergantung pada model bahasa.
        total_plan = self._meal_total_plan(q)
        if total_plan:
            return total_plan
        if "bandingkan" in q or re.search(r"\blebih (?:baik|sehat)\b", q):
            comparison = self.plan(question)
            if comparison.get("intent") == "compare_foods" and len(comparison.get("food_names") or []) >= 2:
                return comparison
        # Pronouns, quantities and compound requests need contextual planning.
        if re.search(r"\b(itu|ini|tadi|tersebut|saya|dan|atau|serta|dengan|darah|normal|harian|kebutuhan|maksimal|minimal)\b|\d", q):
            return None
        if re.fullmatch(r"(?:berapa (?:kalori|protein|gula|serat|lemak|karbohidrat|natrium)|(?:cek|tampilkan|lihat) nutrisi) [a-z ]{2,60}", q):
            plan = self.plan(question)
            if plan.get("intent") == "food_lookup" and plan.get("food_name"):
                return plan
        return None

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
            names = [part.strip() for part in re.split(r"\s+(?:dan|atau|dengan|sama)\s+", body) if part.strip()]
            return {"intent": "compare_foods", "food_names": names[:3]}
        total_plan = self._meal_total_plan(q)
        if total_plan:
            return total_plan
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
