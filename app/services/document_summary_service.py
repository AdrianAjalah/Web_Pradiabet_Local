"""Ringkasan dokumen melalui text-generation provider yang dikonfigurasi."""
from __future__ import annotations


class DocumentSummaryService:
    def __init__(self, client, model: str = "llama3.1:8b", max_input_chars: int = 24000) -> None:
        self.client = client
        self.model = model
        self.max_input_chars = max_input_chars

    def summarize(self, text: str) -> str:
        if not text.strip():
            return ""
        prompt = (
            "Ringkas dokumen berikut dalam Bahasa Indonesia. Pertahankan fakta, istilah penting, "
            "angka, rekomendasi kesehatan, dan hubungan sebab-akibat. Jangan menambahkan informasi baru.\n\n"
            + text[: self.max_input_chars]
        )
        return self.client.chat(prompt, model=self.model)
