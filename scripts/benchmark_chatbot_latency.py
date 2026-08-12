"""Benchmark end-to-end latency for the PrediBeat chatbot HTTP endpoint."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import statistics
import time
from typing import Any, Callable

import requests


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [float(row["latency_seconds"]) for row in results]
    if not latencies:
        raise ValueError("Tidak ada hasil benchmark untuk diringkas.")
    success_count = sum(1 for row in results if bool(row.get("success")))
    return {
        "request_count": len(results),
        "success_count": success_count,
        "failure_count": len(results) - success_count,
        "mean_latency_seconds": statistics.fmean(latencies),
        "median_latency_seconds": statistics.median(latencies),
        "min_latency_seconds": min(latencies),
        "max_latency_seconds": max(latencies),
        "population_stddev_seconds": statistics.pstdev(latencies),
    }



def check_provider(
    session: Any,
    base_url: str,
    *,
    timeout: float,
    required_provider: str = "ollama",
) -> dict[str, Any]:
    response = session.get(
        base_url.rstrip("/") + "/api/chatbot/status",
        timeout=timeout,
    )
    if int(response.status_code) != 200:
        raise RuntimeError(f"Gagal membaca status chatbot: HTTP {response.status_code}")
    payload = response.json()
    provider = str(payload.get("provider") or "").casefold()
    if provider != required_provider.casefold():
        raise RuntimeError(
            f"Benchmark mensyaratkan provider {required_provider}, tetapi server melaporkan {provider or 'unknown'}."
        )
    if not bool(payload.get("configured")):
        raise RuntimeError(f"Provider {provider} belum dikonfigurasi dengan benar.")
    return payload

def _validate_questions(questions: list[dict[str, str]]) -> None:
    if len(questions) != 10:
        raise ValueError(f"Benchmark membutuhkan tepat 10 pertanyaan; ditemukan {len(questions)}.")
    for index, item in enumerate(questions, start=1):
        if not str(item.get("question") or "").strip():
            raise ValueError(f"Pertanyaan ke-{index} kosong.")


def _login(session: Any, base_url: str, username: str, password: str, timeout: float) -> None:
    response = session.post(
        base_url.rstrip("/") + "/login",
        data={"username": username, "password": password},
        allow_redirects=False,
        timeout=timeout,
    )
    if int(response.status_code) not in {200, 302, 303}:
        raise RuntimeError(f"Login benchmark gagal: HTTP {response.status_code} {getattr(response, 'text', '')[:300]}")


def _reset_chat_state(session: Any, base_url: str, username: str, password: str, timeout: float) -> None:
    session.get(base_url.rstrip("/") + "/logout", allow_redirects=False, timeout=timeout)
    _login(session, base_url, username, password, timeout)


def _timed_question(
    *,
    session: Any,
    base_url: str,
    question: str,
    category: str,
    timeout: float,
    timer: Callable[[], float],
    sequence: int,
) -> dict[str, Any]:
    started = timer()
    try:
        response = session.post(
            base_url.rstrip("/") + "/tanya",
            json={"pertanyaan": question},
            timeout=timeout,
        )
        payload = response.json()
        latency = timer() - started
        status_code = int(response.status_code)
        success = 200 <= status_code < 300 and isinstance(payload, dict) and bool(payload.get("jawaban"))
        return {
            "no": sequence,
            "category": category,
            "question": question,
            "latency_seconds": float(latency),
            "success": success,
            "http_status": status_code,
            "mode": str(payload.get("mode") or "unknown") if isinstance(payload, dict) else "unknown",
            "source": str(payload.get("sumber") or "") if isinstance(payload, dict) else "",
            "confidence": payload.get("confidence") if isinstance(payload, dict) else None,
            "answer": str(payload.get("jawaban") or "") if isinstance(payload, dict) else "",
            "answer_length_chars": len(str(payload.get("jawaban") or "")) if isinstance(payload, dict) else 0,
            "error": "" if success else str(payload if isinstance(payload, dict) else getattr(response, "text", ""))[:500],
        }
    except Exception as exc:
        latency = timer() - started
        return {
            "no": sequence,
            "category": category,
            "question": question,
            "latency_seconds": float(latency),
            "success": False,
            "http_status": 0,
            "mode": "error",
            "source": "",
            "confidence": None,
            "answer": "",
            "answer_length_chars": 0,
            "error": str(exc)[:500],
        }


def run_benchmark(
    *,
    session: Any,
    base_url: str,
    username: str,
    password: str,
    questions: list[dict[str, str]],
    timeout: float = 300.0,
    reset_between_questions: bool = True,
    timer: Callable[[], float] = time.perf_counter,
) -> dict[str, Any]:
    _validate_questions(questions)
    _login(session, base_url, username, password, timeout)
    provider_status = check_provider(session, base_url, timeout=timeout, required_provider="ollama")

    warmup_item = questions[0]
    warmup = _timed_question(
        session=session,
        base_url=base_url,
        question=str(warmup_item["question"]),
        category="warmup",
        timeout=timeout,
        timer=timer,
        sequence=0,
    )

    results: list[dict[str, Any]] = []
    for index, item in enumerate(questions, start=1):
        if reset_between_questions:
            _reset_chat_state(session, base_url, username, password, timeout)
        results.append(
            _timed_question(
                session=session,
                base_url=base_url,
                question=str(item["question"]),
                category=str(item.get("category") or "unspecified"),
                timeout=timeout,
                timer=timer,
                sequence=index,
            )
        )

    return {
        "warmup_latency_seconds": float(warmup["latency_seconds"]),
        "warmup_success": bool(warmup["success"]),
        "results": results,
        "summary": summarize_results(results),
        "provider_status": provider_status,
        "http_calls": getattr(session, "calls", []),
    }


def _load_questions(path: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("File pertanyaan harus berupa JSON array.")
    questions = [dict(item) for item in data if isinstance(item, dict)]
    _validate_questions(questions)
    return questions


def _write_outputs(result: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"chatbot_latency_{stamp}.csv"
    json_path = output_dir / f"chatbot_latency_{stamp}_summary.json"

    rows = result["results"]
    fieldnames = [
        "no", "category", "question", "latency_seconds", "success", "http_status",
        "mode", "source", "confidence", "answer", "answer_length_chars", "error",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            serializable = {key: row.get(key) for key in fieldnames}
            serializable["latency_seconds"] = f"{float(row['latency_seconds']):.6f}"
            writer.writerow(serializable)

    summary_payload = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "warmup_latency_seconds": result["warmup_latency_seconds"],
        "warmup_success": result["warmup_success"],
        "provider": result.get("provider_status", {}).get("provider"),
        "model": result.get("provider_status", {}).get("model"),
        **result["summary"],
    }
    json_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, json_path


def _print_summary(result: dict[str, Any], csv_path: Path, json_path: Path) -> None:
    print("\n=== PrediBeat End-to-End Latency Benchmark ===")
    status = result.get("provider_status", {})
    print(f"Provider: {status.get('provider', 'unknown')} | Model: {status.get('model', 'unknown')}")
    print(f"Warm-up (tidak dihitung): {result['warmup_latency_seconds']:.3f} detik")
    print("\nNo  Kategori                 Latency(s)  Status  Mode")
    print("--  -----------------------  ----------  ------  --------")
    for row in result["results"]:
        print(
            f"{row['no']:>2}  {row['category'][:23]:<23}  {row['latency_seconds']:>10.3f}  "
            f"{'OK' if row['success'] else 'FAIL':<6}  {row['mode']}"
        )
    summary = result["summary"]
    print("\nRingkasan 10 pertanyaan:")
    print(f"  Mean     : {summary['mean_latency_seconds']:.3f} detik")
    print(f"  Median   : {summary['median_latency_seconds']:.3f} detik")
    print(f"  Minimum  : {summary['min_latency_seconds']:.3f} detik")
    print(f"  Maximum  : {summary['max_latency_seconds']:.3f} detik")
    print(f"  Std. dev : {summary['population_stddev_seconds']:.3f} detik")
    print(f"  Berhasil : {summary['success_count']}/{summary['request_count']}")
    print(f"\nCSV  : {csv_path}")
    print(f"JSON : {json_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument(
        "--questions",
        type=Path,
        default=Path(__file__).with_name("benchmark_questions.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("benchmark_results"))
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--no-reset-between-questions", action="store_true")
    args = parser.parse_args()

    questions = _load_questions(args.questions)
    with requests.Session() as session:
        result = run_benchmark(
            session=session,
            base_url=args.base_url,
            username=args.username,
            password=args.password,
            questions=questions,
            timeout=args.timeout,
            reset_between_questions=not args.no_reset_between_questions,
        )
    csv_path, json_path = _write_outputs(result, args.output_dir)
    _print_summary(result, csv_path, json_path)
    return 0 if result["summary"]["failure_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
