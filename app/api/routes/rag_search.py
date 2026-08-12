"""Endpoint diagnostik retrieval RAG untuk menguji index sebelum dihubungkan ke chatbot lama."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.bootstrap import build_retrievers

router = APIRouter(prefix="/api/rag", tags=["RAG Search"])


@router.get("/search")
def search(q: str = Query(min_length=2), source: str = Query(default="pdf")):
    try:
        pdf_retriever, food_retriever = build_retrievers()
        if source == "food":
            return {"source": source, "results": food_retriever.search(q)}
        if source == "pdf":
            return {"source": source, "results": pdf_retriever.search(q)}
        raise HTTPException(status_code=400, detail="source harus 'pdf' atau 'food'.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Retrieval belum tersedia: {exc}") from exc
