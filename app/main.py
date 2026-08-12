"""Entry point web PrediBeat V2.

File ini sengaja kecil. Seluruh route dan logika bisnis ditempatkan pada modul yang
sesuai agar perubahan RAG tidak mengganggu fitur web lain.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.routes.admin_documents import admin_router as admin_documents_html_router
from app.api.routes.admin_documents import router as admin_documents_router
from app.api.routes.admin_datasets import router as admin_datasets_router
from app.api.routes.admin_portal import router as admin_portal_router
from app.api.routes.rag_search import router as rag_search_router
from app.api.routes.user_portal import router as user_portal_router
from app.api.routes.progress_tracker import router as progress_tracker_router
from app.api.routes.chatbot import router as chatbot_router
from app.core.config import Settings
from app.core.logging import configure_logging
from app.database.connection import Base, engine
import app.database.models.rag_job  # noqa: F401
import app.database.models.user  # noqa: F401
import app.database.models.progress  # noqa: F401


def create_app() -> FastAPI:
    settings = Settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        settings.ensure_runtime_directories()
        Base.metadata.create_all(bind=engine)
        yield

    app = FastAPI(title=settings.app_name, version="2.0.0", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parents[1] / "static")), name="static")
    app.include_router(user_portal_router)
    app.include_router(progress_tracker_router)
    app.include_router(chatbot_router)
    app.include_router(admin_portal_router)
    app.include_router(admin_datasets_router)
    app.include_router(admin_documents_router)
    app.include_router(admin_documents_html_router)
    app.include_router(rag_search_router)

    @app.get("/health", tags=["System"])
    def health() -> dict:
        return {
            "status": "ok",
            "app": settings.app_name,
            "structured_nutrition": True,
            "pdf_rag": True,
            "embedding_provider": "ollama",
            "embedding_model": settings.embedding_model,
            "rag_process_mode": settings.rag_process_mode,
            "pdf_collections": {
                "chunks": settings.pdf_chunks_collection,
                "qa": settings.pdf_qa_collection,
            },
        }

    return app


app = create_app()
