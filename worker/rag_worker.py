"""Worker terpisah untuk mengambil dan memproses job RAG dari PostgreSQL."""
from __future__ import annotations

import logging
import time

from app.core.config import Settings
from app.core.logging import configure_logging
from app.database.connection import Base, SessionLocal, engine
from app.database.repositories.rag_job_repository import RagJobRepository
from app.services.rag_job_processor import process_rag_job
import app.database.models.rag_job  # noqa: F401

configure_logging(Settings().log_level)
logger = logging.getLogger("predibeat.rag_worker")


def run_forever() -> None:
    Base.metadata.create_all(bind=engine)
    settings = Settings()
    settings.ensure_runtime_directories()
    logger.info(
        "RAG worker aktif. embedding=%s Qdrant=%s",
        settings.embedding_model,
        settings.qdrant_url,
    )

    while True:
        with SessionLocal() as db:
            job = RagJobRepository(db).claim_next()
        if not job:
            time.sleep(settings.worker_poll_seconds)
            continue
        process_rag_job(job.id)


if __name__ == "__main__":
    run_forever()
