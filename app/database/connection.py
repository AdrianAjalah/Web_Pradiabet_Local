"""Koneksi SQLAlchemy dan dependency FastAPI."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import Settings


class Base(DeclarativeBase):
    pass


def normalize_database_url(url: str) -> str:
    """Gunakan driver psycopg 3 untuk URL PostgreSQL."""

    value = str(url or "").strip()
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


_settings = Settings()
_database_url = normalize_database_url(_settings.database_url)
_engine_options = {"pool_pre_ping": True}
if _database_url.startswith("sqlite"):
    _engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(_database_url, **_engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
