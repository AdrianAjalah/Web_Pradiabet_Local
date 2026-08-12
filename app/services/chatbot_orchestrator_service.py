"""Coordinate local conversation, structured food tools, and PDF Hybrid RAG."""
from __future__ import annotations

import json
from typing import Any, Callable

from app.services.chatbot_context_service import build_profile_progress_context, build_rag_context
from app.services.chatbot_llm_service import ChatbotLlmService
from app.services.chatbot_request_planner import DeterministicRequestPlanner
from app.services.chatbot_tool_service import ChatbotToolService


class ChatbotOrchestratorService:
    def __init__(
        self,
        *,
        llm: ChatbotLlmService | Any | None = None,
        planner: DeterministicRequestPlanner | None = None,
        tool_service: ChatbotToolService | None = None,
        profile_context_builder: Callable[[Any, int], str] = build_profile_progress_context,
        rag_context_builder: Callable[[str], tuple[str, str, float]] = build_rag_context,
    ) -> None:
        self.llm = llm or ChatbotLlmService()
        self.planner = planner or DeterministicRequestPlanner()
        self.tools = tool_service or ChatbotToolService()
        self.profile_context_builder = profile_context_builder
        self.rag_context_builder = rag_context_builder

    def respond(self, db: Any, user_id: int, question: str, history: list[dict[str, str]]) -> dict[str, Any]:
        plan = self.llm.plan_request(question, history) or self.planner.plan(question)
        plan = self._sanitize_plan(plan, question)
        intent = plan["intent"]

        profile_context = self.profile_context_builder(db, user_id)
        tool_result: dict[str, Any] | None = None
        pdf_context = ""
        source = "Percakapan Dr. Predia"
        confidence = 1.0

        if intent == "mixed":
            food_plan = plan.get("food_plan") if isinstance(plan.get("food_plan"), dict) else {}
            tool_result = self.tools.execute(food_plan)
            pdf_context, pdf_source, pdf_confidence = self.rag_context_builder(
                str(plan.get("education_question") or question)
            )
            source = f"Structured Nutrition Database + {pdf_source}"
            confidence = pdf_confidence
        elif intent in {"food_lookup", "meal_total", "compare_foods", "food_filter", "recommend_foods"}:
            tool_result = self.tools.execute(plan)
            source = "Structured Nutrition Database"
            confidence = 1.0
        elif intent == "pdf_education":
            pdf_context, source, confidence = self.rag_context_builder(str(plan.get("question") or question))
        elif intent == "out_of_scope":
            source = "Batas Domain PrediBeat"
        elif intent in {"greeting", "general_chat"}:
            source = "Percakapan Dr. Predia"

        verified_context = self._build_verified_context(profile_context, plan, tool_result, pdf_context)
        answer = self.llm.answer(question, verified_context, history)
        if answer.startswith("Maaf, layanan AI sedang tidak dapat dihubungi"):
            answer = self._fallback_answer(plan, tool_result, pdf_context)
            mode = "deterministic"
        else:
            mode = str(getattr(self.llm, "last_provider", "ollama"))
        return {
            "answer": answer,
            "source": source,
            "confidence": float(confidence or 0),
            "plan": plan,
            "tool_result": tool_result,
            "mode": mode,
        }

    @staticmethod
    def _sanitize_plan(plan: dict[str, Any], question: str) -> dict[str, Any]:
        allowed = {
            "greeting", "general_chat", "out_of_scope", "food_lookup", "meal_total",
            "compare_foods", "food_filter", "recommend_foods", "pdf_education", "mixed",
        }
        result = dict(plan or {})
        intent = str(result.get("intent") or "general_chat")
        if intent not in allowed:
            intent = "general_chat"
        result["intent"] = intent
        fallback = DeterministicRequestPlanner().plan(question)

        # Model dapat menganggap pertanyaan fakta dari jurnal sebagai general_chat
        # atau food_lookup. Untuk pola referensi dokumen yang eksplisit, parser
        # deterministik menjadi pengaman agar pencarian PDF benar-benar dijalankan.
        if fallback.get("intent") == "pdf_education" and intent in {
            "general_chat", "out_of_scope", "food_lookup"
        }:
            return fallback

        if intent == "food_lookup" and not str(result.get("food_name") or "").strip():
            return fallback
        if intent == "meal_total" and not isinstance(result.get("items"), list):
            return fallback
        if intent == "compare_foods" and not isinstance(result.get("food_names"), list):
            return fallback
        if intent == "mixed" and not isinstance(result.get("food_plan"), dict):
            return fallback
        if intent == "pdf_education" and not result.get("question"):
            result["question"] = question
        return result

    @staticmethod
    def _build_verified_context(
        profile_context: str,
        plan: dict[str, Any],
        tool_result: dict[str, Any] | None,
        pdf_context: str,
    ) -> str:
        parts = [profile_context, "RENCANA PERMINTAAN:\n" + json.dumps(plan, ensure_ascii=False)]
        if tool_result is not None:
            parts.append(
                "HASIL STRUCTURED NUTRITION TOOL (salin angka apa adanya):\n"
                + json.dumps(tool_result, ensure_ascii=False, default=str)
            )
        if pdf_context:
            parts.append("REFERENSI HYBRID RAG PDF:\n" + pdf_context)
        return "\n\n".join(part for part in parts if part)

    @staticmethod
    def _fmt(value: Any) -> str:
        number = float(value or 0)
        return str(int(number)) if number.is_integer() else f"{number:.2f}".rstrip("0").rstrip(".")

    def _fallback_answer(self, plan: dict[str, Any], tool_result: dict[str, Any] | None, pdf_context: str) -> str:
        intent = plan.get("intent")
        if intent == "greeting":
            return "Halo! Saya Dr. Predia. Mau mengecek nutrisi makanan, menghitung total makanan yang sudah dikonsumsi, atau mencari rekomendasi menu?"
        if intent == "out_of_scope":
            return "Saya difokuskan untuk membantu nutrisi, pola makan, progress kesehatan, dan rekomendasi makanan di PrediBeat. Silakan tanyakan makanan atau kebutuhan nutrisi Anda."
        if intent == "pdf_education":
            if pdf_context:
                return "Referensi PDF sudah ditemukan, tetapi layanan AI untuk merangkum sedang tidak tersedia. Silakan coba lagi setelah koneksi AI aktif."
            return "Saya belum menemukan referensi PDF yang sesuai untuk pertanyaan tersebut."
        if not tool_result:
            return "Silakan tanyakan nama makanan, nilai nutrisi, perbandingan makanan, atau rekomendasi berdasarkan kebutuhan Anda."

        status = tool_result.get("status")
        if status == "not_found":
            return "Makanan tersebut belum ditemukan dalam dataset PrediBeat. Coba gunakan nama yang lebih singkat atau lebih spesifik."
        if status in {"ambiguous", "needs_clarification"}:
            candidates = tool_result.get("candidates") or []
            if not candidates:
                for item in tool_result.get("unresolved") or tool_result.get("items") or []:
                    candidates.extend(item.get("candidates") or [])
            names = []
            for item in candidates:
                name = item.get("nama")
                if name and name not in names:
                    names.append(name)
            if names:
                choices = "\n".join(f"{idx}. {name}" for idx, name in enumerate(names[:5], 1))
                return f"Saya menemukan beberapa kemungkinan:\n{choices}\n\nYang mana yang Anda maksud?"
            return "Saya membutuhkan nama makanan atau ukuran porsi yang lebih spesifik agar perhitungannya tepat."
        if status == "found" and tool_result.get("food"):
            food = tool_result["food"]
            fields = tool_result.get("requested_fields") or ["kalori_kkal", "karbohidrat_g", "protein_g", "lemak_g", "serat_g", "gula_g", "natrium_mg"]
            labels = {
                "kalori_kkal": ("kalori", "kkal"), "karbohidrat_g": ("karbohidrat", "g"),
                "protein_g": ("protein", "g"), "lemak_g": ("lemak", "g"),
                "serat_g": ("serat", "g"), "gula_g": ("gula", "g"), "natrium_mg": ("natrium", "mg"),
            }
            values = []
            for field in fields:
                if field in labels:
                    label, unit = labels[field]
                    values.append(f"{label} {self._fmt(food.get(field))} {unit}")
            return f"Berdasarkan dataset, {food.get('nama')} per {self._fmt(food.get('gram_porsi') or 100)} gram mengandung " + ", ".join(values) + "."
        if status == "calculated" and tool_result.get("intent") == "compare_foods":
            lines = []
            for item in tool_result.get("items") or []:
                food = item["food"]
                lines.append(
                    f"- {food.get('nama')}: {self._fmt(food.get('kalori_kkal'))} kkal, "
                    f"protein {self._fmt(food.get('protein_g'))} g, serat {self._fmt(food.get('serat_g'))} g, "
                    f"gula {self._fmt(food.get('gula_g'))} g per {self._fmt(food.get('gram_porsi') or 100)} g"
                )
            return "Berikut perbandingannya berdasarkan dataset:\n" + "\n".join(lines)
        if status == "calculated" and tool_result.get("totals"):
            lines = []
            for item in tool_result.get("items") or []:
                lines.append(f"- {item['food'].get('nama')}: {self._fmt(item['scaled'].get('kalori_kkal'))} kkal")
            return "Jika porsinya sesuai dataset:\n" + "\n".join(lines) + f"\n\nTotalnya sekitar **{self._fmt(tool_result['totals'].get('kalori_kkal'))} kkal**."
        if status == "found" and tool_result.get("foods"):
            lines = [f"{i}. {food.get('nama')} — {self._fmt(food.get('kalori_kkal'))} kkal, protein {self._fmt(food.get('protein_g'))} g, serat {self._fmt(food.get('serat_g'))} g, gula {self._fmt(food.get('gula_g'))} g" for i, food in enumerate(tool_result["foods"], 1)]
            return "Berikut hasil dari dataset PrediBeat:\n" + "\n".join(lines)
        return "Permintaan sudah diproses, tetapi hasilnya perlu diperjelas. Coba sebutkan nama makanan dan porsinya."
