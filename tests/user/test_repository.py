from __future__ import annotations

from app.database.models.user import UserDB, UserProfileDB
from app.user.repository import UserRepository
from app.user.security import hash_password


def test_repository_login_lookup_and_duplicates_are_case_insensitive(db_session_factory):
    with db_session_factory() as db:
        user = UserDB(
            username="Daniel",
            username_normalized="daniel",
            email="Daniel@Example.com",
            email_normalized="daniel@example.com",
            hashed_password=hash_password("password123"),
            role="user",
        )
        db.add(user)
        db.commit()

        repo = UserRepository(db)
        assert repo.find_by_login("DANIEL").id == user.id
        assert repo.find_by_login("daniel@example.COM").id == user.id
        assert repo.find_duplicate("daniel", "new@example.com") == "username"
        assert repo.find_duplicate("new-user", "DANIEL@example.com") == "email"


def test_repository_detects_completed_profile(db_session_factory):
    with db_session_factory() as db:
        user = UserDB(
            username="member",
            username_normalized="member",
            email="member@example.com",
            email_normalized="member@example.com",
            hashed_password=hash_password("password123"),
            role="user",
        )
        db.add(user)
        db.commit()
        repo = UserRepository(db)
        assert repo.has_completed_profile(user.id) is False

        db.add(
            UserProfileDB(
                user_id=user.id,
                full_profile_data='{"usia": 30}',
                analysis_result='{"skor_risiko": 2}',
            )
        )
        db.commit()
        assert repo.has_completed_profile(user.id) is True
