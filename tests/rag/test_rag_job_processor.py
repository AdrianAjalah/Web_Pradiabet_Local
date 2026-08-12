from pathlib import Path
from types import SimpleNamespace

from app.rag.domain.models import IngestionResult
from app.services.rag_job_processor import process_rag_job, schedule_inline_jobs


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRepository:
    def __init__(self, db, job):
        self.job = job
        self.completed = None
        self.failed = None
        self.started = False

    def get(self, job_id):
        return self.job if self.job.id == job_id else None

    def start(self, job):
        self.started = True
        job.status = "processing"

    def complete(self, job, chunk_count, qa_count):
        self.completed = (chunk_count, qa_count)
        job.status = "completed"

    def fail(self, job, message):
        self.failed = message
        job.status = "failed"


class FakePdfPipeline:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.calls = []

    def run(self, source_path, source_id, output_dir):
        self.calls.append((Path(source_path), source_id, Path(output_dir)))
        if self.should_fail:
            raise RuntimeError("embedding gagal")
        return IngestionResult(source_id, Path(source_path).name, 3, 2)


class FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, function, *args, **kwargs):
        self.tasks.append((function, args, kwargs))


def test_schedule_inline_jobs_only_when_inline_mode():
    background = FakeBackgroundTasks()
    jobs = [SimpleNamespace(id=11), SimpleNamespace(id=12)]

    schedule_inline_jobs(background, jobs, SimpleNamespace(rag_process_mode="inline"))

    assert [args for _fn, args, _kwargs in background.tasks] == [(11,), (12,)]


def test_process_rag_job_completes_and_deletes_pdf_after_success(tmp_path: Path):
    source = tmp_path / "inbox" / "doc.pdf"
    source.parent.mkdir()
    source.write_bytes(b"%PDF-test")
    job = SimpleNamespace(id=1, source_id="doc-1", source_name="doc.pdf", source_type="pdf", source_path=str(source), status="pending")
    settings = SimpleNamespace(
        rag_output_dir=tmp_path / "output",
        rag_processed_dir=tmp_path / "processed",
        rag_failed_dir=tmp_path / "failed",
        rag_delete_source_after_index=True,
    )
    repository = FakeRepository(FakeSession(), job)
    pipeline = FakePdfPipeline()

    process_rag_job(
        1,
        session_factory=FakeSession,
        pipeline_factory=lambda: (settings, pipeline, object()),
        repository_factory=lambda db: repository,
    )

    assert repository.started is True
    assert repository.completed == (3, 2)
    assert job.status == "completed"
    assert not source.exists()
    assert pipeline.calls[0][2] == settings.rag_output_dir / "doc-1"


def test_process_rag_job_marks_failed_and_keeps_pdf_in_failed_directory(tmp_path: Path):
    source = tmp_path / "inbox" / "doc.pdf"
    source.parent.mkdir()
    source.write_bytes(b"%PDF-test")
    job = SimpleNamespace(id=2, source_id="doc-2", source_name="doc.pdf", source_type="pdf", source_path=str(source), status="pending")
    settings = SimpleNamespace(
        rag_output_dir=tmp_path / "output",
        rag_processed_dir=tmp_path / "processed",
        rag_failed_dir=tmp_path / "failed",
        rag_delete_source_after_index=True,
    )
    repository = FakeRepository(FakeSession(), job)
    pipeline = FakePdfPipeline(should_fail=True)

    process_rag_job(
        2,
        session_factory=FakeSession,
        pipeline_factory=lambda: (settings, pipeline, object()),
        repository_factory=lambda db: repository,
    )

    assert job.status == "failed"
    assert "embedding gagal" in repository.failed
    assert not source.exists()
    assert list(settings.rag_failed_dir.glob("*.pdf"))
