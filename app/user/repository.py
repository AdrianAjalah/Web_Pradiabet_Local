"""Database queries for user-facing flows."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database.models.user import UserDB, UserProfileDB


def normalize_username(value: str) -> str:
    return (value or "").strip().casefold()


def normalize_email(value: str | None) -> str | None:
    normalized = (value or "").strip().casefold()
    return normalized or None


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_login(self, login: str) -> UserDB | None:
        normalized = (login or "").strip().casefold()
        if not normalized:
            return None
        return self.db.scalar(
            select(UserDB).where(
                or_(
                    UserDB.username_normalized == normalized,
                    UserDB.email_normalized == normalized,
                )
            )
        )

    def find_duplicate(self, username: str, email: str | None) -> str | None:
        username_normalized = normalize_username(username)
        email_normalized = normalize_email(email)
        if self.db.scalar(select(UserDB.id).where(UserDB.username_normalized == username_normalized)):
            return "username"
        if email_normalized and self.db.scalar(
            select(UserDB.id).where(UserDB.email_normalized == email_normalized)
        ):
            return "email"
        return None

    def get_by_id(self, user_id: int) -> UserDB | None:
        return self.db.get(UserDB, user_id)

    def has_completed_profile(self, user_id: int) -> bool:
        return self.db.scalar(select(UserProfileDB.id).where(UserProfileDB.user_id == user_id)) is not None
