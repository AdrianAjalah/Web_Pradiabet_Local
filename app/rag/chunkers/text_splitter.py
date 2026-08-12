"""Pemecah teks ringan berbasis kata dengan overlap yang deterministik."""
from __future__ import annotations


def split_text(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    words = str(text or "").split()
    if not words:
        return []
    if max_tokens <= 0:
        raise ValueError("max_tokens harus lebih dari 0")
    if overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens harus >= 0 dan lebih kecil dari max_tokens")

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + max_tokens, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = end - overlap_tokens
    return chunks
