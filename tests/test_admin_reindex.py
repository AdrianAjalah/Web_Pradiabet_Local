from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.responses import RedirectResponse

from app.api.routes import admin_datasets


class _FakeDefinition:
    def __init__(self, path: Path):
        self.path = path


class _FakeDatasetService:
    def __init__(self, path: Path):
        self._path = path

    def get_definition(self, key: str):
        assert key == "food"
        return _FakeDefinition(self._path)


class _FakeSettings:
    def __init__(self, inbox: Path):
        self.rag_inbox_dir = inbox

    def ensure_runtime_directories(self):
        self.rag_inbox_dir.mkdir(parents=True, exist_ok=True)


def test_reindex_reuses_active_food_job_instead_of_creating_duplicate(tmp_path, monkeypatch):
    dataset_path = tmp_path / "master.csv"
    dataset_path.write_text("nama,kalori\nNasi,100\n", encoding="utf-8")
    active_job = SimpleNamespace(
        id=7,
        source_id="reference-food-master",
        status="processing",
    )

    class FakeRepo:
        def __init__(self, db):
            self.db = db

        def find_active(self, source_id: str, source_type: str | None = None):
            assert source_id == "reference-food-master"
            assert source_type == "csv"
            return active_job

        def create(self, **kwargs):
            pytest.fail("Tidak boleh membuat job duplikat saat reindex masih aktif")

    monkeypatch.setattr(admin_datasets, "Settings", lambda: _FakeSettings(tmp_path / "inbox"))
    monkeypatch.setattr(
        admin_datasets.DatasetService,
        "from_settings",
        lambda settings: _FakeDatasetService(dataset_path),
    )
    monkeypatch.setattr(admin_datasets, "RagJobRepository", FakeRepo)
    monkeypatch.setattr(
        admin_datasets.shutil,
        "copy2",
        lambda *_args, **_kwargs: pytest.fail("Dataset tidak perlu disalin untuk job duplikat"),
    )

    result = admin_datasets.reindex_food_dataset(db=object())

    assert result == {
        "job_id": 7,
        "source_id": "reference-food-master",
        "status": "processing",
        "already_active": True,
    }


def test_admin_reindex_redirects_back_to_combined_admin(monkeypatch):
    monkeypatch.setattr(
        admin_datasets,
        "reindex_food_dataset",
        lambda db: {
            "job_id": 8,
            "source_id": "reference-food-master",
            "status": "pending",
            "already_active": False,
        },
    )

    response = admin_datasets.reindex_food_from_dashboard(
        return_to="/admin",
        db=object(),
    )

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/admin?")


def test_admin_reindex_rejects_external_redirect_target(monkeypatch):
    monkeypatch.setattr(
        admin_datasets,
        "reindex_food_dataset",
        lambda db: {
            "job_id": 8,
            "source_id": "reference-food-master",
            "status": "pending",
            "already_active": False,
        },
    )

    response = admin_datasets.reindex_food_from_dashboard(
        return_to="https://example.com/steal",
        db=object(),
    )

    assert response.headers["location"].startswith("/admin/datasets?")


def test_cancel_duplicate_food_jobs_keeps_one_and_cancels_the_rest(tmp_path, monkeypatch):
    keep_path = tmp_path / "keep.csv"
    duplicate_path = tmp_path / "duplicate.csv"
    keep_path.write_text("keep", encoding="utf-8")
    duplicate_path.write_text("duplicate", encoding="utf-8")
    keep = SimpleNamespace(id=3, status="processing", source_path=str(keep_path))
    duplicate = SimpleNamespace(id=4, status="pending", source_path=str(duplicate_path))

    class FakeRepo:
        def __init__(self, db):
            self.cancelled = []

        def list_active(self, source_id: str, source_type: str | None = None):
            assert source_id == "reference-food-master"
            assert source_type == "csv"
            return [keep, duplicate]

        def cancel(self, job, message: str):
            job.status = "cancelled"
            self.cancelled.append((job.id, message))

    monkeypatch.setattr(admin_datasets, "RagJobRepository", FakeRepo)

    result = admin_datasets.cancel_duplicate_food_jobs(db=object())

    assert result == {"kept_job_id": 3, "cancelled_count": 1}
    assert keep_path.exists()
    assert not duplicate_path.exists()
    assert duplicate.status == "cancelled"
