"""One-time migration of normal V1 users and health profiles into PrediBeat V2."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.database.connection import SessionLocal
from app.database.models.user import UserDB, UserProfileDB
from app.user.repository import UserRepository, normalize_email, normalize_username


@dataclass(slots=True)
class MigrationReport:
    migrated: int = 0
    skipped_admin: int = 0
    skipped_duplicate: int = 0
    failed: int = 0
    failures: list[str] = field(default_factory=list)


def _normalized_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def _read_source_users(source_engine: Engine):
    inspector = inspect(source_engine)
    if "users" not in inspector.get_table_names():
        raise RuntimeError("Tabel users tidak ditemukan pada database V1.")
    has_profiles = "profiles" in inspector.get_table_names()
    if has_profiles:
        query = text(
            """
            SELECT
                u.id,
                u.username,
                u.email,
                u.hashed_password,
                u.role,
                p.full_profile_data,
                p.analysis_result
            FROM users u
            LEFT JOIN profiles p ON p.user_id = u.id
            ORDER BY u.id
            """
        )
    else:
        query = text(
            """
            SELECT
                u.id,
                u.username,
                u.email,
                u.hashed_password,
                u.role,
                NULL AS full_profile_data,
                NULL AS analysis_result
            FROM users u
            ORDER BY u.id
            """
        )
    with source_engine.connect() as connection:
        return list(connection.execute(query).mappings())


def migrate_v1_users(
    source_engine: Engine,
    target_session_factory: sessionmaker = SessionLocal,
) -> MigrationReport:
    report = MigrationReport()
    rows = _read_source_users(source_engine)
    allowed_roles = {"user", "member", "pengguna"}

    for row in rows:
        role = str(row.get("role") or "user").strip().casefold()
        source_label = str(row.get("username") or f"id={row.get('id')}")
        if role not in allowed_roles:
            report.skipped_admin += 1
            continue

        db = target_session_factory()
        try:
            username = str(row.get("username") or "").strip()
            email = str(row.get("email") or "").strip() or None
            hashed_password = str(row.get("hashed_password") or "").strip()
            if not username or not hashed_password:
                raise ValueError("username atau hash password kosong")

            if UserRepository(db).find_duplicate(username, email):
                report.skipped_duplicate += 1
                db.rollback()
                continue

            profile_json = row.get("full_profile_data")
            analysis_json = row.get("analysis_result")
            parsed_profile = None
            parsed_analysis = None
            if profile_json is not None or analysis_json is not None:
                if profile_json is None or analysis_json is None:
                    raise ValueError("data profil V1 tidak lengkap")
                parsed_profile = json.loads(str(profile_json))
                parsed_analysis = json.loads(str(analysis_json))
                if not isinstance(parsed_profile, dict) or not isinstance(parsed_analysis, dict):
                    raise ValueError("format JSON profil V1 harus berupa object")

            user = UserDB(
                username=username,
                username_normalized=normalize_username(username),
                email=email,
                email_normalized=normalize_email(email),
                hashed_password=hashed_password,
                role="user",
            )
            db.add(user)
            db.flush()
            if parsed_profile is not None and parsed_analysis is not None:
                db.add(
                    UserProfileDB(
                        user_id=user.id,
                        full_profile_data=json.dumps(parsed_profile, ensure_ascii=False),
                        analysis_result=json.dumps(parsed_analysis, ensure_ascii=False),
                    )
                )
            db.commit()
            report.migrated += 1
        except Exception as exc:  # one source user must not abort the full migration
            db.rollback()
            report.failed += 1
            report.failures.append(f"{source_label}: {exc}")
        finally:
            db.close()
    return report


def main() -> int:
    v1_database_url = os.getenv("V1_DATABASE_URL", "").strip()
    if not v1_database_url:
        print("GAGAL: V1_DATABASE_URL belum diisi pada .env.")
        return 2

    source_engine = create_engine(
        _normalized_database_url(v1_database_url),
        pool_pre_ping=True,
    )
    try:
        report = migrate_v1_users(source_engine, SessionLocal)
    finally:
        source_engine.dispose()

    print("=== HASIL MIGRASI USER V1 → V2 ===")
    print(f"Berhasil dipindahkan : {report.migrated}")
    print(f"Admin/role lain dilewati : {report.skipped_admin}")
    print(f"Username/email duplikat : {report.skipped_duplicate}")
    print(f"Gagal : {report.failed}")
    for failure in report.failures:
        print(f"- {failure}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
