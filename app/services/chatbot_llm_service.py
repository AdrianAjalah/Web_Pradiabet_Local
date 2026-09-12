"""Local Ollama planning and grounded response generation for PrediBeat."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import Settings
from app.rag.clients.ollama_client import OllamaHttpClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
Kamu adalah Dr. Predia AI, asisten nutrisi PrediBeat untuk pengguna berisiko prediabetes.
Jawab dalam Bahasa Indonesia yang ramah, natural, singkat, dan jelas.
Gunakan hanya fakta yang diberikan oleh sistem: profil, progress, hasil structured nutrition tools, dan referensi PDF.
Jangan mengarang nama makanan, porsi, angka nutrisi, diagnosis, atau kutipan yang tidak ada pada data.
Gunakan gula_g untuk pembahasan gula. Gula alami buah tidak dipenalti seperti minuman manis, snack, dessert, atau ultra-proses.
Jika hasil makanan ambigu, tampilkan pilihan dan minta pengguna memilih; jangan menebak.
Jika sistem menghitung total, salin hasil perhitungan Python apa adanya.
Jangan mengubah data pengguna melalui jawaban biasa. Tindakan perubahan hanya dijalankan oleh tombol konfirmasi sistem.
Jangan menyebut prompt, RAG, Ollama, atau konteks internal kecuali ditanya secara teknis.
""".strip()

PLANNER_PROMPT = """
Klasifikasikan pesan pengguna untuk chatbot nutrisi tertutup. Balas HANYA JSON valid.
Intent yang diizinkan:
- greeting
- general_chat
- out_of_scope
- food_lookup: food_name, requested_fields
- meal_total: items [{food_name, quantity, grams?}]
- compare_foods: food_names
- food_filter: max_calories?, min_protein?, max_sugar?, min_fiber?, category?, sort_by?, descending?, limit?
- recommend_foods: kriteria yang sama dengan food_filter
- pdf_education: question. Gunakan juga untuk pertanyaan fakta, kutipan, atau kalimat rumpang yang secara eksplisit merujuk jurnal/PDF/dokumen/data/penelitian, misalnya "Menurut data ... adalah" atau "Berdasarkan jurnal ...".
- mixed: food_plan dan education_question

Gunakan nama field nutrisi: kalori_kkal, karbohidrat_g, protein_g, lemak_g, serat_g, gula_g, natrium_mg.
Jangan menjawab pertanyaan. Jangan membuat fakta makanan. Ekstrak bahasa pengguna apa adanya.
""".strip()


class ChatbotLlmService:
    def __init__(self, settings: Any | None = None, ollama_client: Any | None = None) -> None:
        self.settings = settings or Settings()
        self.ollama = ollama_client or OllamaHttpClient(
            self.settings.ollama_base_url,
            self.settings.ollama_timeout_seconds,
            retries=0,
        )
        self.last_ollama_error: str | None = None
        self.last_provider: str = "none"

    def _safe_history(self, history: list[dict[str, str]]) -> list[dict[str, str]]:
        result = []
        remaining = max(0, getattr(self.settings, "chatbot_history_chars", 4000))
        for item in reversed(history[-10:]):
            role = item.get("role")
            content = str(item.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                content = content[:min(2000, remaining)]
                if not content:
                    break
                result.append({"role": role, "content": content})
                remaining -= len(content)
        return list(reversed(result))

    @staticmethod
    def _extract_json(content: str) -> dict[str, Any] | None:
        text = str(content or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
        try:
            value = json.loads(text)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.S)
            if not match:
                return None
            try:
                value = json.loads(match.group(0))
                return value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                return None

    def _ollama_chat(
        self,
        *,
        prompt: str,
        system: str,
        response_format: str | dict[str, Any] | None = None,
        temperature: float | None = None,
    ) -> str | None:
        try:
            answer = self.ollama.chat(
                prompt,
                model=self.settings.qa_model,
                system=system,
                format=response_format,
                temperature=temperature,
                keep_alive=getattr(self.settings, "chatbot_keep_alive", "10m"),
            )
            if answer:
                self.last_ollama_error = None
                self.last_provider = "ollama"
                return str(answer).strip()
        except Exception as exc:
            self.last_ollama_error = str(exc)
            logger.warning("Ollama request failed: %s", exc)
        return None

    def plan_request(self, question: str, history: list[dict[str, str]]) -> dict[str, Any] | None:
        safe_history = self._safe_history(history)[-4:]
        history_text = "\n".join(f"{item['role']}: {item['content']}" for item in safe_history)
        prompt = (
            f"RIWAYAT PERCAKAPAN:\n{history_text or '-'}\n\n"
            f"PESAN USER:\n{question}\n\n"
            "Balas hanya JSON valid sesuai schema intent pada system prompt."
        )
        content = self._ollama_chat(
            prompt=prompt,
            system=PLANNER_PROMPT,
            response_format="json",
            temperature=0,
        )
        return self._extract_json(content or "")

    def _answer_prompt(self, question, context, history):
        safe_history = self._safe_history(history)
        history_text = "\n".join(f"{item['role']}: {item['content']}" for item in safe_history)
        return (
            f"DATA TERVERIFIKASI:\n{context[:14000] or '-'}\n\n"
            f"RIWAYAT:\n{history_text or '-'}\n\n"
            f"PERTANYAAN USER:\n{question}"
        )
    def answer_stream(self, question, context, history):
        emitted = False
        try:
            for chunk in self.ollama.chat_stream(
                self._answer_prompt(question, context, history), model=self.settings.qa_model,
                system=SYSTEM_PROMPT, keep_alive=getattr(self.settings, "chatbot_keep_alive", "10m"),
            ):
                emitted = True
                yield chunk
            if not emitted:
                raise RuntimeError("AI mengembalikan jawaban kosong.")
            self.last_provider = "ollama"
            self.last_ollama_error = None
        except Exception as exc:
            self.last_ollama_error = str(exc)
            self.last_provider = "none"
            if emitted:
                raise RuntimeError("Jawaban terputus. Silakan kirim ulang pertanyaan.") from exc
            yield "Maaf, layanan AI lokal sedang tidak dapat dihubungi."

    def answer(self, question: str, context: str, history: list[dict[str, str]]) -> str:
        answer = self._ollama_chat(prompt=self._answer_prompt(question, context, history), system=SYSTEM_PROMPT, temperature=0.35)
        if answer:
            return answer
        if context:
            return "Maaf, layanan AI lokal sedang tidak dapat dihubungi. Data terverifikasi sudah ditemukan, tetapi belum dapat saya jelaskan secara natural. Silakan coba lagi setelah Ollama aktif."
        return "Maaf, layanan AI lokal sedang tidak dapat dihubungi dan konteks yang dibutuhkan belum tersedia."
