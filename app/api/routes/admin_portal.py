"""Portal admin terpadu untuk dataset referensi dan dokumen RAG."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.connection import get_db
from app.database.repositories.rag_job_repository import RagJobRepository
from app.services.dataset_service import DatasetService

router = APIRouter(tags=["Admin Portal"])
TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


@router.get("/admin", response_class=HTMLResponse)
def admin_portal(request: Request, db: Session = Depends(get_db)):
    settings = Settings()
    settings.ensure_runtime_directories()
    dataset_service = DatasetService.from_settings(settings)
    datasets = dataset_service.list_statuses()
    dataset_backups = {
        dataset.key: dataset_service.list_backups(dataset.key) for dataset in datasets
    }

    repository = RagJobRepository(db)
    jobs = repository.list_recent(limit=100)
    documents = repository.list_pdf_documents(limit=200)
    active_jobs = any(job.status in {"pending", "processing"} for job in jobs)
    food_reindex_jobs = repository.list_active("reference-food-master", source_type="csv")
    food_reindex_job = next(
        (job for job in food_reindex_jobs if job.status == "processing"),
        food_reindex_jobs[0] if food_reindex_jobs else None,
    )

    # Autentikasi V1 belum menjadi bagian fondasi V2. Nilai ini hanya untuk header
    # template dan nanti dapat diganti current_user tanpa mengubah desain halaman.
    user = SimpleNamespace(username="Admin")
    return templates.TemplateResponse(
        request=request,
        name="admin/index.html",
        context={
            "user": user,
            "datasets": datasets,
            "dataset_backups": dataset_backups,
            "documents": documents,
            "jobs": jobs,
            "active_jobs": active_jobs,
            "food_reindex_active": food_reindex_job is not None,
            "food_reindex_job": food_reindex_job,
            "food_reindex_active_count": len(food_reindex_jobs),
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        },
    )
