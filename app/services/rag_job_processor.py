"""Eksekusi satu job RAG, dapat dipakai worker terpisah atau inline di web."""
from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from app.bootstrap import build_pipelines
from app.database.connection import SessionLocal
from app.database.repositories.rag_job_repository import RagJobRepository

logger = logging.getLogger("predibeat.rag_job_processor")


def _move_file(source: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    if destination.exists():
        destination = destination_dir / f"{int(time.time())}_{source.name}"
    return Path(shutil.move(str(source), str(destination)))


def schedule_inline_jobs(background_tasks, jobs, settings) -> None:
    """Jadwalkan job di proses web hanya ketika RAG_PROCESS_MODE=inline."""

    if str(getattr(settings, "rag_process_mode", "worker") or "worker").casefold() != "inline":
        return
    for job in jobs:
        background_tasks.add_task(process_rag_job, int(job.id))


def process_rag_job(
    job_id: int,
    *,
    session_factory=SessionLocal,
    pipeline_factory=build_pipelines,
    repository_factory=RagJobRepository,
) -> None:
    """Proses satu job dan pastikan PDF hanya dihapus setelah indexing berhasil."""

    with session_factory() as db:
        repository = repository_factory(db)
        job = repository.get(job_id)
        if job is None:
            logger.warning("Job RAG %s tidak ditemukan.", job_id)
            return
        if job.status in {"completed", "cancelled"}:
            return
        if job.status == "pending":
            repository.start(job)

        source_path = Path(job.source_path)
        try:
            settings, pdf_pipeline, csv_pipeline = pipeline_factory()
            output_dir = Path(settings.rag_output_dir) / job.source_id
            if job.source_type == "pdf":
                result = pdf_pipeline.run(source_path, job.source_id, output_dir)
            elif job.source_type == "csv":
                result = csv_pipeline.run(source_path, job.source_id, output_dir)
            else:
                raise ValueError(f"Jenis sumber tidak didukung: {job.source_type}")

            repository.complete(job, result.chunk_count, result.qa_count)
            if source_path.exists():
                if bool(getattr(settings, "rag_delete_source_after_index", False)):
                    source_path.unlink()
                else:
                    _move_file(source_path, Path(settings.rag_processed_dir))
            logger.info(
                "Job %s selesai: %s chunks, %s QA",
                job.id,
                result.chunk_count,
                result.qa_count,
            )
        except Exception as exc:
            logger.exception("Job %s gagal", job.id)
            repository.fail(job, str(exc))
            try:
                settings
            except UnboundLocalError:
                # Pipeline factory gagal sebelum settings terbentuk; gunakan parent file sebagai fallback.
                settings = None
            if source_path.exists() and settings is not None:
                _move_file(source_path, Path(settings.rag_failed_dir))
