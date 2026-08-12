"""FastAPI dependencies for authenticated user routes."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.connection import get_db
from app.database.models.user import UserDB
from app.user.repository import UserRepository
from app.user.security import InvalidSessionToken, decode_session_token


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> UserDB | None:
    settings = Settings()
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        return None
    try:
        payload = decode_session_token(token, secret=settings.auth_secret_key)
    except InvalidSessionToken:
        return None
    return UserRepository(db).get_by_id(int(payload["uid"]))


def require_current_user(
    user: UserDB | None = Depends(get_current_user_optional),
) -> UserDB:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Silakan masuk terlebih dahulu.",
        )
    return user
