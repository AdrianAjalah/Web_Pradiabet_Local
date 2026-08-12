from types import SimpleNamespace

from app.services.rag_job_processor import schedule_inline_jobs


class FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((fn, args, kwargs))


def test_worker_mode_does_not_schedule_web_background_tasks():
    background = FakeBackgroundTasks()

    schedule_inline_jobs(background, [SimpleNamespace(id=1)], SimpleNamespace(rag_process_mode="worker"))

    assert background.tasks == []
