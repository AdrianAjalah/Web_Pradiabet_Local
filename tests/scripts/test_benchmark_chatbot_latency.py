from pathlib import Path
import statistics

from scripts import benchmark_chatbot_latency as benchmark


def test_benchmark_script_exists():
    assert Path("scripts/benchmark_chatbot_latency.py").is_file()


def test_summarize_results_reports_latency_statistics_for_all_ten_requests():
    summarize = getattr(benchmark, "summarize_results", None)
    assert callable(summarize)
    results = [
        {
            "latency_seconds": float(i),
            "success": i != 10,
            "http_status": 200 if i != 10 else 500,
        }
        for i in range(1, 11)
    ]

    summary = summarize(results)

    assert summary["request_count"] == 10
    assert summary["success_count"] == 9
    assert summary["failure_count"] == 1
    assert summary["mean_latency_seconds"] == 5.5
    assert summary["median_latency_seconds"] == 5.5
    assert summary["min_latency_seconds"] == 1.0
    assert summary["max_latency_seconds"] == 10.0
    assert summary["population_stddev_seconds"] == statistics.pstdev(range(1, 11))


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if url.endswith("/login"):
            return FakeResponse(303)
        if url.endswith("/tanya"):
            question = kwargs["json"]["pertanyaan"]
            return FakeResponse(
                200,
                {
                    "jawaban": f"jawaban untuk {question}",
                    "sumber": "Structured Nutrition Database",
                    "confidence": 100.0,
                    "mode": "ollama",
                },
            )
        raise AssertionError(url)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if url.endswith("/api/chatbot/status"):
            return FakeResponse(200, {"configured": True, "provider": "ollama", "model": "llama3.1:8b"})
        if url.endswith("/logout"):
            return FakeResponse(303)
        raise AssertionError(url)


def test_run_benchmark_measures_warmup_plus_exactly_ten_questions_and_resets_history():
    run = getattr(benchmark, "run_benchmark", None)
    assert callable(run)
    questions = [{"category": "food", "question": f"q{i}"} for i in range(1, 11)]

    # warm-up = 2 sec, then measured requests = 1..10 sec
    timer_values = iter(
        [100.0, 102.0]
        + [value for i in range(1, 11) for value in (200.0 + i * 20, 200.0 + i * 20 + i)]
    )

    result = run(
        session=FakeSession(),
        base_url="http://localhost:8000",
        username="tester",
        password="secret",
        questions=questions,
        timeout=30,
        reset_between_questions=True,
        timer=lambda: next(timer_values),
    )

    assert result["warmup_latency_seconds"] == 2.0
    assert len(result["results"]) == 10
    assert [row["latency_seconds"] for row in result["results"]] == [float(i) for i in range(1, 11)]
    assert result["summary"]["mean_latency_seconds"] == 5.5
    assert all(row["mode"] == "ollama" for row in result["results"])
    assert all("answer" in row for row in result["results"])
    assert result["results"][0]["answer"] == "jawaban untuk q1"
    assert sum(1 for method, url, _ in result["http_calls"] if method == "POST" and url.endswith("/tanya")) == 11
    assert sum(1 for method, url, _ in result["http_calls"] if method == "GET" and url.endswith("/logout")) == 10


def test_provider_preflight_requires_local_ollama():
    check = getattr(benchmark, "check_provider", None)
    assert callable(check)
    session = FakeSession()

    status = check(session, "http://localhost:8000", timeout=30, required_provider="ollama")

    assert status["provider"] == "ollama"
    assert status["model"] == "llama3.1:8b"


def test_provider_preflight_rejects_cloud_provider():
    check = getattr(benchmark, "check_provider", None)
    assert callable(check)

    class CloudSession(FakeSession):
        def get(self, url, **kwargs):
            if url.endswith("/api/chatbot/status"):
                return FakeResponse(200, {"configured": True, "provider": "remote", "model": "remote-model"})
            return super().get(url, **kwargs)

    import pytest
    with pytest.raises(RuntimeError, match="ollama"):
        check(CloudSession(), "http://localhost:8000", timeout=30, required_provider="ollama")
