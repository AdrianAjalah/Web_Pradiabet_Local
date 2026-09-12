"""Live HTTP smoke/latency test using a temporary synthetic user (run in web container).

Creates only its own test user/profile, logs in normally, then removes them in finally.
Never uses existing accounts. Report contains synthetic questions and answers only.
"""
from __future__ import annotations

import json
from pathlib import Path
import secrets
import time
import requests

from app.core.config import Settings
from app.database.connection import SessionLocal
from app.database.models.user import UserDB, UserProfileDB
from app.user.security import hash_password


def main():
    settings = Settings()
    base = "http://127.0.0.1:8000"
    username = "latency-test-" + secrets.token_hex(8)
    password = secrets.token_urlsafe(24)
    report = {"model": settings.qa_model, "cases": [], "test_user_removed": False}
    with SessionLocal() as db:
        user = UserDB(username=username, username_normalized=username,
                      hashed_password=hash_password(password), role="user")
        db.add(user)
        db.flush()
        user_id = user.id
        db.add(UserProfileDB(user_id=user_id,
            full_profile_data=json.dumps({"usia": 35, "pantangan_alergi": "Tidak ada"}),
            analysis_result=json.dumps({"target_kalori": 1800, "meal_plan": []})))
        db.commit()
    session = requests.Session()
    try:
        report["loaded_models_before"] = requests.get(settings.ollama_base_url + "/api/ps", timeout=10).json()
        for name, question, stream in [
            ("greeting_first", "halo", True),
            ("greeting_warm", "halo", True),
            ("lookup_stream", "berapa kalori nasi goreng", True),
            ("complex_json", "Bandingkan kalori ABC, saus sambal dan ABC, kecap manis.", False),
        ]:
            session.get(base + "/logout", timeout=10)
            login = session.post(base + "/login", data={"username": username, "password": password},
                                 allow_redirects=False, timeout=10)
            assert login.status_code in (302, 303), login.status_code
            start = time.perf_counter()
            row = {"case": name, "question": question, "stream": stream}
            print(json.dumps({"starting": name}), flush=True)
            try:
                with session.post(base + "/tanya", json={"pertanyaan": question, "stream": stream},
                                  stream=stream, timeout=(10, 300)) as response:
                    row["http_status"] = response.status_code
                    response.raise_for_status()
                    if stream:
                        payload = None
                        deltas = 0
                        for line in response.iter_lines(chunk_size=1):
                            if not line:
                                continue
                            event = json.loads(line)
                            if event["type"] == "delta":
                                if not deltas:
                                    row["first_text_seconds"] = round(time.perf_counter() - start, 3)
                                    print(json.dumps({"case": name, "first_text_seconds": row["first_text_seconds"]}), flush=True)
                                deltas += 1
                            elif event["type"] == "done":
                                payload = event["data"]
                            elif event["type"] == "error":
                                raise RuntimeError(event["message"])
                        assert payload is not None, "Missing done event"
                        row["delta_count"] = deltas
                    else:
                        payload = response.json()
                    row["response"] = payload
                    row["success"] = payload.get("mode") == "ollama" and bool(payload.get("jawaban"))
            except Exception as exc:
                row.update(success=False, error=str(exc))
            row["total_seconds"] = round(time.perf_counter() - start, 3)
            report["cases"].append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        report["loaded_models_after"] = requests.get(settings.ollama_base_url + "/api/ps", timeout=10).json()
    finally:
        try:
            session.get(base + "/logout", timeout=10)
        finally:
            session.close()
            with SessionLocal() as db:
                user = db.get(UserDB, user_id)
                if user is not None and user.username == username:
                    db.delete(user)
                    db.commit()
                report["test_user_removed"] = db.get(UserDB, user_id) is None
            Path("/tmp/chatbot-runtime-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["cases"] and all(row["success"] for row in report["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
