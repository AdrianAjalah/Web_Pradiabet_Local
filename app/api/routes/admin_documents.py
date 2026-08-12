"""Endpoint admin untuk upload, detail, dan penghapusan dokumen PDF RAG."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.bootstrap import build_runtime
from app.core.config import Settings
from app.core.security import safe_upload_name, validate_upload_extension  # compatibility exports
from app.database.connection import get_db
from app.database.repositories.rag_job_repository import RagJobRepository
from app.services.rag_job_processor import schedule_inline_jobs
from app.services.admin_document_service import (
    AdminDocumentService,
    DocumentBusyError,
    DocumentNotFoundError,
    PdfBatchValidationError,
)

router = APIRouter(prefix="/api/admin/documents", tags=["RAG Admin"])
admin_router = APIRouter(tags=["RAG Admin HTML"])


def _document_service(db: Session, with_store: bool = False) -> AdminDocumentService:
    settings = Settings()
    settings.ensure_runtime_directories()
    store = None
    if with_store:
        _settings, _ollama, _embedder, _qdrant, _collections, store = build_runtime()
    return AdminDocumentService(db=db, settings=settings, store=store)


def _combined_uploads(
    files: list[UploadFile] | None,
    file: UploadFile | None,
) -> list[UploadFile]:
    uploads = list(files or [])
    if file is not None:
        uploads.append(file)
    return uploads


def _job_payload(job) -> dict:
    return {
        "job_id": job.id,
        "source_id": job.source_id,
        "source_name": job.source_name,
        "status": job.status,
    }


@router.post("/upload", status_code=202)
def upload_document(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] | None = File(default=None),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    uploads = _combined_uploads(files, file)
    try:
        jobs = _document_service(db).upload_pdf_batch(uploads)
    except PdfBatchValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={"message": str(exc), "errors": list(exc.errors)},
        ) from exc
    schedule_inline_jobs(background_tasks, jobs, Settings())
    return {"count": len(jobs), "jobs": [_job_payload(job) for job in jobs]}


@admin_router.post("/admin/documents/upload")
def upload_documents_from_admin(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] | None = File(default=None),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    uploads = _combined_uploads(files, file)
    try:
        jobs = _document_service(db).upload_pdf_batch(uploads)
    except PdfBatchValidationError as exc:
        message = " | ".join(exc.errors)
        return RedirectResponse(url="/admin?error=" + quote(message), status_code=303)
    except Exception as exc:
        return RedirectResponse(
            url="/admin?error=" + quote(f"Upload gagal: {exc}"),
            status_code=303,
        )

    schedule_inline_jobs(background_tasks, jobs, Settings())
    message = f"{len(jobs)} PDF masuk antrean RAG. Pantau statusnya pada tabel dokumen."
    return RedirectResponse(url="/admin?message=" + quote(message), status_code=303)


@router.get("/jobs/{job_id}")
def job_status(job_id: int, db: Session = Depends(get_db)):
    job = RagJobRepository(db).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan.")
    return job.to_dict()


def _document_detail(
    source_id: str,
    db: Session,
    *,
    chunk_page: int = 1,
    qa_page: int = 1,
    page_size: int = 50,
):
    try:
        return _document_service(db, with_store=True).get_document_detail(
            source_id,
            chunk_page=chunk_page,
            qa_page=qa_page,
            page_size=page_size,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gagal membaca Qdrant/artefak: {exc}") from exc


@router.get("/{source_id}/details")
def document_detail(
    source_id: str,
    chunk_page: int = Query(1, ge=1),
    qa_page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return _document_detail(
        source_id,
        db,
        chunk_page=chunk_page,
        qa_page=qa_page,
        page_size=page_size,
    )


@admin_router.get("/admin/document/{source_id}/details")
def document_detail_admin_alias(
    source_id: str,
    chunk_page: int = Query(1, ge=1),
    qa_page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return _document_detail(
        source_id,
        db,
        chunk_page=chunk_page,
        qa_page=qa_page,
        page_size=page_size,
    )


def _delete_document(source_id: str, db: Session):
    try:
        return _document_service(db, with_store=True).delete_document(source_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DocumentBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Dokumen belum terhapus karena pembersihan Qdrant/file gagal: {exc}",
        ) from exc


@router.get("/{source_id}/artifacts/{filename}")
def download_document_artifact(
    source_id: str,
    filename: str,
    db: Session = Depends(get_db),
):
    try:
        path = _document_service(db).get_artifact_path(source_id, filename)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Artefak belum tersedia.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(path, filename=path.name)


@router.delete("/{source_id}")
def delete_document(source_id: str, db: Session = Depends(get_db)):
    return _delete_document(source_id, db)


@admin_router.delete("/admin/document/{source_id}")
def delete_document_admin_alias(source_id: str, db: Session = Depends(get_db)):
    return _delete_document(source_id, db)
