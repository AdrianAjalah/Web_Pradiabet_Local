"""Operasi database untuk antrean RAG."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database.models.rag_job import RagJob


class RagJobRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, source_id: str, source_name: str, source_type: str, source_path: str) -> RagJob:
        job = self.add(
            source_id=source_id,
            source_name=source_name,
            source_type=source_type,
            source_path=source_path,
        )
        self.db.commit()
        self.db.refresh(job)
        return job

    def add(self, source_id: str, source_name: str, source_type: str, source_path: str) -> RagJob:
        """Tambahkan job ke session tanpa commit agar pemanggil dapat membuat batch atomik."""

        job = RagJob(
            source_id=source_id,
            source_name=source_name,
            source_type=source_type,
            source_path=source_path,
            status="pending",
        )
        self.db.add(job)
        return job

    def create_many(self, items: list[dict[str, str]]) -> list[RagJob]:
        jobs = [self.add(**item) for item in items]
        self.db.commit()
        for job in jobs:
            self.db.refresh(job)
        return jobs

    def get(self, job_id: int) -> RagJob | None:
        return self.db.get(RagJob, job_id)

    def find_pdf_by_name(self, source_name: str) -> RagJob | None:
        statement = (
            select(RagJob)
            .where(
                RagJob.source_type == "pdf",
                func.lower(RagJob.source_name) == source_name.casefold(),
            )
            .order_by(RagJob.created_at.desc())
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def list_by_source_id(self, source_id: str, *, for_update: bool = False) -> list[RagJob]:
        statement = (
            select(RagJob)
            .where(RagJob.source_id == source_id)
            .order_by(RagJob.created_at.asc())
        )
        if for_update:
            statement = statement.with_for_update()
        return list(self.db.execute(statement).scalars())

    def list_pdf_documents(self, limit: int = 200) -> list[RagJob]:
        statement = (
            select(RagJob)
            .where(RagJob.source_type == "pdf")
            .order_by(RagJob.created_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(statement).scalars())

    def delete_source_jobs(self, source_id: str, *, commit: bool = True) -> int:
        result = self.db.execute(delete(RagJob).where(RagJob.source_id == source_id))
        if commit:
            self.db.commit()
        return int(result.rowcount or 0)

    def find_active(self, source_id: str, source_type: str | None = None) -> RagJob | None:
        jobs = self.list_active(source_id, source_type=source_type)
        processing_job = next((job for job in jobs if job.status == "processing"), None)
        return processing_job or (jobs[0] if jobs else None)

    def list_active(self, source_id: str, source_type: str | None = None) -> list[RagJob]:
        statement = select(RagJob).where(
            RagJob.source_id == source_id,
            RagJob.status.in_(("pending", "processing")),
        )
        if source_type:
            statement = statement.where(RagJob.source_type == source_type)
        statement = statement.order_by(RagJob.created_at.asc())
        return list(self.db.execute(statement).scalars())

    def cancel(self, job: RagJob, message: str) -> None:
        job.status = "cancelled"
        job.error_message = message[:4000]
        job.finished_at = datetime.now(timezone.utc)
        self.db.commit()

    def list_recent(self, limit: int = 20) -> list[RagJob]:
        statement = select(RagJob).order_by(RagJob.created_at.desc()).limit(limit)
        return list(self.db.execute(statement).scalars())

    def claim_next(self) -> RagJob | None:
        statement = (
            select(RagJob)
            .where(RagJob.status == "pending")
            .order_by(RagJob.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = self.db.execute(statement).scalar_one_or_none()
        if job:
            job.status = "processing"
            job.started_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(job)
        return job

    def start(self, job: RagJob) -> None:
        job.status = "processing"
        job.started_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)

    def complete(self, job: RagJob, chunk_count: int, qa_count: int) -> None:
        job.status = "completed"
        job.chunk_count = chunk_count
        job.qa_count = qa_count
        job.finished_at = datetime.now(timezone.utc)
        self.db.commit()

    def fail(self, job: RagJob, message: str) -> None:
        job.status = "failed"
        job.error_message = message[:4000]
        job.finished_at = datetime.now(timezone.utc)
        self.db.commit()
