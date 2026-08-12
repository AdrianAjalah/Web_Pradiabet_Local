"""Pembuatan QA khusus chunk PDF melalui text-generation provider."""
from __future__ import annotations

import hashlib
import json
import re

from app.rag.domain.models import Chunk, QaPair


class PdfQaGenerator:
    def __init__(self, client, model: str = "llama3.1:8b", max_pairs_per_chunk: int = 2) -> None:
        self.client = client
        self.model = model
        self.max_pairs_per_chunk = max_pairs_per_chunk

    def generate_for_chunks(self, chunks: list[Chunk]) -> list[QaPair]:
        pairs: list[QaPair] = []
        candidates = [chunk for chunk in chunks if chunk.source_type == "pdf" and chunk.layer in {0, 1, 2}]
        for chunk in candidates:
            response = self.client.chat(
                self._prompt(chunk),
                model=self.model,
                system="Keluarkan JSON valid saja. Jangan mengarang fakta di luar konteks.",
            )
            for index, item in enumerate(self._parse_json(response)[: self.max_pairs_per_chunk]):
                question = str(item.get("question") or "").strip()
                answer = str(item.get("answer") or "").strip()
                if not question or not answer:
                    continue
                digest = hashlib.sha1(f"{chunk.chunk_id}|{question}".encode()).hexdigest()[:16]
                pairs.append(
                    QaPair(
                        qa_id=f"qa-{digest}",
                        source_id=chunk.source_id,
                        source_name=chunk.source_name,
                        source_chunk_id=chunk.chunk_id,
                        question=question,
                        answer=answer,
                        metadata={
                            "layer": chunk.layer,
                            "page_start": chunk.page_start,
                            "page_end": chunk.page_end,
                        },
                    )
                )
        return pairs

    def _prompt(self, chunk: Chunk) -> str:
        return (
            f"Buat maksimal {self.max_pairs_per_chunk} pasangan pertanyaan-jawaban dalam Bahasa Indonesia "
            "berdasarkan konteks berikut. Format harus berupa array JSON dengan key question dan answer.\n\n"
            f"KONTEKS:\n{chunk.content}"
        )

    @staticmethod
    def _parse_json(text: str) -> list[dict]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE | re.DOTALL)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
            if not match:
                return []
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                return []
        return data if isinstance(data, list) else []
