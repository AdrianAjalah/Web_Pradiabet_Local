from __future__ import annotations

import json

from sqlalchemy import create_engine, text, select

from app.database.models.user import UserDB, UserProfileDB
from app.scripts.migrate_v1_users import migrate_v1_users
from app.user.security import hash_password


def build_v1_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'v1.sqlite3'}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR NOT NULL,
                    email VARCHAR,
                    hashed_password VARCHAR NOT NULL,
                    role VARCHAR NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE profiles (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    full_profile_data TEXT NOT NULL,
                    analysis_result TEXT NOT NULL
                )
                """
            )
        )
    return engine


def test_migration_preserves_user_hash_and_profile_and_skips_admin(tmp_path, db_session_factory):
    source = build_v1_engine(tmp_path)
    legacy_hash = hash_password("password123")
    with source.begin() as conn:
        conn.execute(
            text("INSERT INTO users VALUES (1, 'Daniel', 'daniel@example.com', :h, 'user')"),
            {"h": legacy_hash},
        )
        conn.execute(
            text("INSERT INTO users VALUES (2, 'admin-lama', 'admin@example.com', :h, 'admin')"),
            {"h": legacy_hash},
        )
        conn.execute(
            text("INSERT INTO profiles VALUES (1, 1, :p, :a)"),
            {"p": json.dumps({"usia": 35}), "a": json.dumps({"skor_risiko": 3})},
        )

    report = migrate_v1_users(source, db_session_factory)

    assert report.migrated == 1
    assert report.skipped_admin == 1
    with db_session_factory() as db:
        user = db.scalar(select(UserDB).where(UserDB.username_normalized == "daniel"))
        assert user.hashed_password == legacy_hash
        profile = db.scalar(select(UserProfileDB).where(UserProfileDB.user_id == user.id))
        assert json.loads(profile.full_profile_data)["usia"] == 35


def test_migration_skips_existing_username_or_email_without_overwrite(tmp_path, db_session_factory):
    source = build_v1_engine(tmp_path)
    with source.begin() as conn:
        conn.execute(
            text("INSERT INTO users VALUES (1, 'Existing', 'other@example.com', 'hash-v1', 'user')")
        )
        conn.execute(
            text("INSERT INTO users VALUES (2, 'NewName', 'existing@example.com', 'hash-v1', 'member')")
        )

    with db_session_factory() as db:
        db.add(
            UserDB(
                username="Existing",
                username_normalized="existing",
                email="existing@example.com",
                email_normalized="existing@example.com",
                hashed_password="hash-v2",
                role="user",
            )
        )
        db.commit()

    report = migrate_v1_users(source, db_session_factory)
    assert report.migrated == 0
    assert report.skipped_duplicate == 2
    with db_session_factory() as db:
        assert db.scalar(select(UserDB)).hashed_password == "hash-v2"


def test_malformed_profile_json_rolls_back_that_user(tmp_path, db_session_factory):
    source = build_v1_engine(tmp_path)
    with source.begin() as conn:
        conn.execute(text("INSERT INTO users VALUES (1, 'Broken', 'broken@example.com', 'hash', 'user')"))
        conn.execute(text("INSERT INTO profiles VALUES (1, 1, '{not-json}', '{}')"))

    report = migrate_v1_users(source, db_session_factory)
    assert report.failed == 1
    with db_session_factory() as db:
        assert db.scalar(select(UserDB)) is None
