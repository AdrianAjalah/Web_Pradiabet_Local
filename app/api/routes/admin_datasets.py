"""Dashboard admin untuk mengelola dataset referensi tetap."""
from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.bootstrap import build_runtime
from app.core.config import Settings
from app.database.connection import get_db
from app.database.repositories.rag_job_repository import RagJobRepository
from app.services.admin_dataset_chunk_service import AdminDatasetChunkService
from app.services.dataset_service import DatasetService
from app.services.rag_artifact_service import RagArtifactWriter

router = APIRouter(tags=["Admin Dataset"])
TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
_ALLOWED_RETURN_PATHS = {"/admin", "/admin/datasets"}


def _service() -> DatasetService:
    settings = Settings()
    settings.ensure_runtime_directories()
    return DatasetService.from_settings(settings)




def _food_chunk_service() -> AdminDatasetChunkService:
    settings, _ollama, _embedder, _qdrant, _collections, store = build_runtime()
    settings.ensure_runtime_directories()
    return AdminDatasetChunkService(settings=settings, store=store)


def _refresh_structured_food_runtime() -> None:
    """Reload the CSV cache and rebuild the structured DB on the next chat request."""
    from app.api.routes import chatbot as chatbot_route
    from app.services.food_service import load_nutrition_foods, load_tracker_foods

    load_tracker_foods(force_reload=True)
    load_nutrition_foods(force_reload=True)
    chatbot_route._chatbot_orchestrator = None

def _safe_return_path(return_to: str) -> str:
    return return_to if return_to in _ALLOWED_RETURN_PATHS else "/admin/datasets"



def _enqueue_food_reindex(db: Session, service: DatasetService | None = None):
    settings = Settings()
    settings.ensure_runtime_directories()
    service = service or DatasetService.from_settings(settings)
    definition = service.get_definition("food")
    if not definition.path.exists():
        raise HTTPException(status_code=404, detail="Dataset makanan belum tersedia.")

    repository = RagJobRepository(db)
    active_job = repository.find_active("reference-food-master", source_type="csv")
    if active_job:
        return {
            "job_id": active_job.id,
            "source_id": active_job.source_id,
            "status": active_job.status,
            "already_active": True,
        }

    timestamp = int(time.time() * 1000)
    job_copy = settings.rag_inbox_dir / f"reference-food-master__{timestamp}__{definition.path.name}"
    shutil.copy2(definition.path, job_copy)
    job = repository.create(
        source_id="reference-food-master",
        source_name=definition.path.name,
        source_type="csv",
        source_path=str(job_copy),
    )
    return {
        "job_id": job.id,
        "source_id": job.source_id,
        "status": job.status,
        "already_active": False,
    }


@router.get("/admin/datasets", response_class=HTMLResponse)
def dataset_dashboard(request: Request, db: Session = Depends(get_db)):
    service = _service()
    statuses = service.list_statuses()
    active_job = RagJobRepository(db).find_active("reference-food-master", source_type="csv")
    return templates.TemplateResponse(
        request=request,
        name="admin/datasets.html",
        context={
            "datasets": statuses,
            "dataset_backups": {status.key: service.list_backups(status.key) for status in statuses},
            "food_reindex_active": active_job is not None,
            "food_reindex_job": active_job,
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/api/admin/datasets")
def list_datasets():
    service = _service()
    return {
        "datasets": [status.to_dict() for status in service.list_statuses()],
        "backups": {
            key: [backup.to_dict() for backup in service.list_backups(key)]
            for key in service.definitions
        },
    }




@router.get("/api/admin/datasets/{dataset_key}/chunks")
def list_dataset_chunks(
    dataset_key: str,
    query: str = Query("", max_length=200),
    layer: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=50),
):
    if dataset_key != "food":
        raise HTTPException(status_code=404, detail="Chunk hanya tersedia untuk dataset makanan.")
    if layer not in {None, 0, 1}:
        raise HTTPException(status_code=400, detail="Layer harus 0, 1, atau dikosongkan.")
    try:
        return _food_chunk_service().list_food_chunks(
            query=query,
            layer=layer,
            page=page,
            page_size=page_size,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gagal membaca chunk makanan dari Qdrant: {exc}") from exc


@router.get("/api/admin/datasets/{dataset_key}/artifacts/{filename}")
def download_dataset_artifact(dataset_key: str, filename: str):
    if dataset_key != "food":
        raise HTTPException(status_code=404, detail="Artefak chunk hanya tersedia untuk dataset makanan.")
    try:
        settings = Settings()
        path = RagArtifactWriter.resolve_artifact(
            Path(settings.rag_output_dir) / AdminDatasetChunkService.SOURCE_ID,
            filename,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Artefak belum tersedia.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(path, filename=path.name)


@router.get("/api/admin/datasets/{dataset_key}/backups")
def list_dataset_backups(dataset_key: str):
    service = _service()
    try:
        backups = service.list_backups(dataset_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"dataset_key": dataset_key, "backups": [backup.to_dict() for backup in backups]}


@router.post("/api/admin/datasets/{dataset_key}/upload")
def replace_dataset(
    dataset_key: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File dataset harus berformat CSV.")

    service = _service()
    try:
        service.get_definition(dataset_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temporary:
            shutil.copyfileobj(file.file, temporary)
            temporary_path = Path(temporary.name)
        status = service.replace(dataset_key, temporary_path)
        if dataset_key == "food":
            _refresh_structured_food_runtime()
        return {"dataset": status.to_dict(), "reindex": None}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


@router.post("/admin/datasets/{dataset_key}/upload")
def replace_dataset_from_dashboard(
    dataset_key: str,
    file: UploadFile = File(...),
    return_to: str = Form("/admin/datasets"),
    db: Session = Depends(get_db),
):
    target = _safe_return_path(return_to)
    try:
        result = replace_dataset(dataset_key, file, db)
    except HTTPException as exc:
        return RedirectResponse(url=f"{target}?error={quote(str(exc.detail))}", status_code=303)

    dataset = result["dataset"]
    message = f"Dataset {dataset.get('label', dataset_key)} berhasil diperbarui."
    if result["reindex"]:
        job = result["reindex"]
        if job["already_active"]:
            message += f" Reindex aktif tetap menggunakan job #{job['job_id']}."
        else:
            message += f" Reindex otomatis dibuat sebagai job #{job['job_id']}."
    return RedirectResponse(url=f"{target}?message={quote(message)}", status_code=303)


@router.post("/api/admin/datasets/{dataset_key}/restore")
def restore_dataset(
    dataset_key: str,
    backup_name: str = Form(...),
    db: Session = Depends(get_db),
):
    service = _service()
    try:
        status = service.restore(dataset_key, backup_name)
        if dataset_key == "food":
            _refresh_structured_food_runtime()
        return {"dataset": status.to_dict(), "reindex": None}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/admin/datasets/{dataset_key}/restore")
def restore_dataset_from_dashboard(
    dataset_key: str,
    backup_name: str = Form(...),
    return_to: str = Form("/admin/datasets"),
    db: Session = Depends(get_db),
):
    target = _safe_return_path(return_to)
    try:
        result = restore_dataset(dataset_key, backup_name, db)
    except HTTPException as exc:
        return RedirectResponse(url=f"{target}?error={quote(str(exc.detail))}", status_code=303)
    dataset = result["dataset"]
    message = f"Backup berhasil dipulihkan menjadi dataset aktif {dataset.get('label', dataset_key)}."
    if result["reindex"]:
        message += f" Reindex menggunakan job #{result['reindex']['job_id']}."
    return RedirectResponse(url=f"{target}?message={quote(message)}", status_code=303)


@router.post("/api/admin/datasets/food/reindex", status_code=202)
def reindex_food_dataset(db: Session = Depends(get_db)):
    return _enqueue_food_reindex(db)


def cancel_duplicate_food_jobs(db: Session = Depends(get_db)):
    repository = RagJobRepository(db)
    active_jobs = repository.list_active("reference-food-master", source_type="csv")
    if not active_jobs:
        return {"kept_job_id": None, "cancelled_count": 0}

    processing_jobs = [job for job in active_jobs if job.status == "processing"]
    keep_job = processing_jobs[0] if processing_jobs else active_jobs[0]
    cancelled_count = 0
    for job in active_jobs:
        if job.id == keep_job.id:
            continue
        repository.cancel(job, "Dibatalkan otomatis karena merupakan antrean reindex duplikat.")
        Path(job.source_path).unlink(missing_ok=True)
        cancelled_count += 1

    return {"kept_job_id": keep_job.id, "cancelled_count": cancelled_count}


@router.post("/admin/datasets/food/cancel-duplicates")
def cancel_duplicate_food_jobs_from_dashboard(
    return_to: str = Form("/admin"),
    db: Session = Depends(get_db),
):
    target = _safe_return_path(return_to)
    result = cancel_duplicate_food_jobs(db)
    if result["cancelled_count"]:
        message = (
            f"{result['cancelled_count']} antrean duplikat dibatalkan. "
            f"Job #{result['kept_job_id']} tetap dilanjutkan."
        )
    else:
        message = "Tidak ada antrean reindex duplikat yang perlu dibatalkan."
    return RedirectResponse(url=f"{target}?message={quote(message)}", status_code=303)


@router.post("/admin/datasets/food/reindex")
def reindex_food_from_dashboard(
    return_to: str = Form("/admin/datasets"),
    db: Session = Depends(get_db),
):
    target = _safe_return_path(return_to)
    try:
        result = reindex_food_dataset(db)
    except HTTPException as exc:
        return RedirectResponse(url=f"{target}?error={quote(str(exc.detail))}", status_code=303)

    if result["already_active"]:
        message = (
            f"Reindex sudah berjalan pada job #{result['job_id']} "
            f"({result['status']}). Job baru tidak dibuat."
        )
    else:
        message = f"Reindex dimasukkan ke antrean sebagai job #{result['job_id']}."
    return RedirectResponse(url=f"{target}?message={quote(message)}", status_code=303)
