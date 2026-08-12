"""Layanan manajemen dokumen PDF RAG untuk portal admin."""
from __future__ import annotations

import math
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import Session

from app.core.security import safe_upload_name
from app.database.models.rag_job import RagJob
from app.database.repositories.rag_job_repository import RagJobRepository
from app.services.rag_artifact_service import RagArtifactWriter, render_markdown_safe

MAX_PDF_BYTES = 25 * 1024 * 1024
_COPY_BLOCK_SIZE = 1024 * 1024


class DocumentNotFoundError(LookupError):
    pass


class DocumentBusyError(RuntimeError):
    pass


class PdfBatchValidationError(ValueError):
    """Kesalahan validasi satu atau lebih file dalam batch PDF."""

    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(str(error) for error in errors)
        super().__init__("Upload dibatalkan: " + "; ".join(self.errors))


@dataclass(slots=True)
class _StagedPdf:
    source_name: str
    staged_path: Path
    size_bytes: int


class AdminDocumentService:
    def __init__(self, db: Session, settings, store=None) -> None:
        self.db = db
        self.settings = settings
        self.store = store
        self.repository = RagJobRepository(db)

    def upload_pdf_batch(self, files: list) -> list[RagJob]:
        """Validasi seluruh batch lebih dahulu, lalu buat semua job secara atomik."""

        if not files:
            raise PdfBatchValidationError(("Pilih minimal satu file PDF.",))

        self.settings.ensure_runtime_directories()
        staging_dir = self.settings.rag_inbox_dir / ".staging"
        staging_dir.mkdir(parents=True, exist_ok=True)
        staged: list[_StagedPdf] = []
        errors: list[str] = []
        normalized_names: set[str] = set()

        try:
            for upload in files:
                original_name = str(getattr(upload, "filename", "") or "").strip()
                safe_name = safe_upload_name(original_name)
                normalized = safe_name.casefold()

                if Path(original_name).suffix.lower() != ".pdf":
                    errors.append(f"{original_name or 'File tanpa nama'}: hanya PDF yang diperbolehkan.")
                    continue
                if normalized in normalized_names:
                    errors.append(f"{safe_name}: nama duplikat dalam pilihan upload.")
                    continue
                normalized_names.add(normalized)
                if self.repository.find_pdf_by_name(safe_name):
                    errors.append(f"{safe_name}: nama sudah terdaftar. Hapus dokumen lama terlebih dahulu.")
                    continue

                staged_path = staging_dir / f"{uuid.uuid4()}__{safe_name}.part"
                try:
                    size_bytes, header = self._copy_to_staging(upload, staged_path)
                except Exception:
                    staged_path.unlink(missing_ok=True)
                    raise

                if size_bytes == 0:
                    errors.append(f"{safe_name}: file kosong.")
                    staged_path.unlink(missing_ok=True)
                    continue
                if size_bytes > MAX_PDF_BYTES:
                    errors.append(f"{safe_name}: ukuran maksimal 25 MB per file.")
                    staged_path.unlink(missing_ok=True)
                    continue
                if not header.startswith(b"%PDF-"):
                    errors.append(f"{safe_name}: isi file bukan PDF yang valid.")
                    staged_path.unlink(missing_ok=True)
                    continue
                staged.append(_StagedPdf(safe_name, staged_path, size_bytes))

            if errors:
                raise PdfBatchValidationError(errors)

            final_paths: list[Path] = []
            job_rows: list[dict[str, str]] = []
            try:
                for item in staged:
                    source_id = str(uuid.uuid4())
                    destination = self.settings.rag_inbox_dir / f"{source_id}__{item.source_name}"
                    item.staged_path.replace(destination)
                    final_paths.append(destination)
                    job_rows.append(
                        {
                            "source_id": source_id,
                            "source_name": item.source_name,
                            "source_type": "pdf",
                            "source_path": str(destination),
                        }
                    )
                return self.repository.create_many(job_rows)
            except Exception:
                self.db.rollback()
                for path in final_paths:
                    path.unlink(missing_ok=True)
                raise
        finally:
            for item in staged:
                item.staged_path.unlink(missing_ok=True)
            try:
                staging_dir.rmdir()
            except OSError:
                pass

    def list_documents(self, limit: int = 200) -> list[dict]:
        return [job.to_dict() for job in self.repository.list_pdf_documents(limit=limit)]

    def get_document_detail(
        self,
        source_id: str,
        *,
        chunk_page: int = 1,
        qa_page: int = 1,
        page_size: int = 50,
    ) -> dict:
        jobs = self.repository.list_by_source_id(source_id)
        if not jobs or all(job.source_type != "pdf" for job in jobs):
            raise DocumentNotFoundError("Dokumen tidak ditemukan.")
        job = jobs[-1]
        chunks: list[dict] = []
        qa_data: list[dict] = []
        if job.status == "completed":
            self._require_store()
            chunks = self.store.list_source_payloads(source_id, target="pdf")
            qa_data = self.store.list_source_payloads(source_id, target="qa")
            chunks.sort(key=self._payload_sort_key)
            qa_data.sort(key=lambda item: self._natural_key(str(item.get("qa_id", ""))))

        page_size = min(max(int(page_size or 50), 1), 50)
        chunk_page_data, chunk_pagination = self._paginate(chunks, chunk_page, page_size)
        qa_page_data, qa_pagination = self._paginate(qa_data, qa_page, page_size)

        output_dir = Path(self.settings.rag_output_dir) / source_id
        if job.status == "completed":
            output_dir.mkdir(parents=True, exist_ok=True)
            artifact_writer = RagArtifactWriter()
            if not (output_dir / "chunks.md").is_file() or not (output_dir / "chunks.json").is_file():
                artifact_writer.write_chunk_payloads(output_dir, chunks)
            if not (output_dir / "qa.md").is_file() or not (output_dir / "qa.json").is_file():
                artifact_writer.write_qa_payloads(output_dir, qa_data)
            artifact_writer.ensure_extracted_markdown(output_dir, chunks)
        extracted_markdown = RagArtifactWriter.read_text(output_dir, "extracted.md")
        artifact_files = RagArtifactWriter.list_artifacts(output_dir)

        return {
            "source_id": source_id,
            "source_name": job.source_name,
            "status": job.status,
            "error_message": job.error_message,
            "chunk_count": len(chunks) if job.status == "completed" else job.chunk_count,
            "qa_count": len(qa_data) if job.status == "completed" else job.qa_count,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "extracted_markdown": extracted_markdown,
            "extracted_html": render_markdown_safe(extracted_markdown),
            "artifact_files": artifact_files,
            "chunks": chunk_page_data,
            "qa_data": qa_page_data,
            "chunks_pagination": chunk_pagination,
            "qa_pagination": qa_pagination,
        }

    @staticmethod
    def _paginate(items: list[dict], page: int, page_size: int) -> tuple[list[dict], dict]:
        page = max(int(page or 1), 1)
        total_items = len(items)
        total_pages = math.ceil(total_items / page_size) if total_items else 0
        start = (page - 1) * page_size
        end = start + page_size
        return items[start:end], {
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
            "has_previous": page > 1 and total_items > 0,
            "has_next": end < total_items,
        }

    @classmethod
    def _payload_sort_key(cls, item: dict):
        return (
            int(item.get("layer", 99) if item.get("layer") is not None else 99),
            int(item.get("page_start", 0) or 0),
            cls._natural_key(str(item.get("chunk_id", ""))),
        )

    @staticmethod
    def _natural_key(value: str):
        return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value))

    def get_artifact_path(self, source_id: str, filename: str) -> Path:
        jobs = self.repository.list_by_source_id(source_id)
        if not jobs or all(job.source_type != "pdf" for job in jobs):
            raise DocumentNotFoundError("Dokumen tidak ditemukan.")
        output_dir = Path(self.settings.rag_output_dir) / source_id
        return RagArtifactWriter.resolve_artifact(output_dir, filename)

    def delete_document(self, source_id: str) -> dict:
        jobs = self.repository.list_by_source_id(source_id, for_update=True)
        pdf_jobs = [job for job in jobs if job.source_type == "pdf"]
        if not pdf_jobs:
            self.db.rollback()
            raise DocumentNotFoundError("Dokumen tidak ditemukan.")
        if any(job.status == "processing" for job in pdf_jobs):
            self.db.rollback()
            raise DocumentBusyError("Dokumen sedang diproses dan belum dapat dihapus.")

        self._require_store()
        try:
            # Hapus vector lebih dahulu. Bila Qdrant gagal, file dan job tetap utuh.
            self.store.delete_source(source_id, targets=("pdf", "qa"))
            removed_paths = self._remove_runtime_artifacts(source_id, pdf_jobs)
            deleted_jobs = self.repository.delete_source_jobs(source_id, commit=False)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {
            "deleted": True,
            "source_id": source_id,
            "source_name": pdf_jobs[-1].source_name,
            "deleted_jobs": deleted_jobs,
            "removed_paths": removed_paths,
        }

    def _remove_runtime_artifacts(self, source_id: str, jobs: list[RagJob]) -> list[str]:
        removed: list[str] = []
        roots = (
            Path(self.settings.rag_inbox_dir),
            Path(self.settings.rag_processed_dir),
            Path(self.settings.rag_failed_dir),
        )
        candidates: set[Path] = set()
        for job in jobs:
            candidates.add(Path(job.source_path))
        for root in roots:
            root.mkdir(parents=True, exist_ok=True)
            candidates.update(root.glob(f"*{source_id}__*"))

        for candidate in candidates:
            if not any(self._is_within(candidate, root) for root in roots):
                continue
            if candidate.is_dir():
                shutil.rmtree(candidate)
            elif candidate.exists():
                candidate.unlink()
            else:
                continue
            removed.append(str(candidate))

        output_dir = Path(self.settings.rag_output_dir) / source_id
        if output_dir.exists() and self._is_within(output_dir, Path(self.settings.rag_output_dir)):
            shutil.rmtree(output_dir)
            removed.append(str(output_dir))
        return removed

    @staticmethod
    def _is_within(candidate: Path, root: Path) -> bool:
        try:
            candidate.resolve(strict=False).relative_to(root.resolve(strict=False))
            return True
        except ValueError:
            return False

    def _require_store(self) -> None:
        if self.store is None:
            raise RuntimeError("Koneksi Qdrant belum tersedia untuk operasi ini.")

    @staticmethod
    def _copy_to_staging(upload, destination: Path) -> tuple[int, bytes]:
        size_bytes = 0
        header = b""
        stream = upload.file
        try:
            stream.seek(0)
        except (AttributeError, OSError):
            pass
        with destination.open("wb") as handle:
            while True:
                block = stream.read(_COPY_BLOCK_SIZE)
                if not block:
                    break
                if not header:
                    header = bytes(block[:8])
                size_bytes += len(block)
                handle.write(block)
                if size_bytes > MAX_PDF_BYTES:
                    # Cukup membaca sampai terbukti melampaui batas.
                    break
        return size_bytes, header
