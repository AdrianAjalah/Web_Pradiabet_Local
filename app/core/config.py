"""Konfigurasi terpusat PrediBeat untuk runtime lokal dan Docker."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class Settings:
    app_name: str = field(default_factory=lambda: _env("APP_NAME", "PrediBeat V3 Structured Chatbot"))
    app_env: str = field(default_factory=lambda: _env("APP_ENV", "development"))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
    app_timezone: str = field(default_factory=lambda: _env("APP_TIMEZONE", "Asia/Jakarta"))

    auth_secret_key: str = field(
        default_factory=lambda: _env(
            "AUTH_SECRET_KEY",
            "development-only-change-this-secret-before-production",
        )
    )
    auth_cookie_name: str = field(default_factory=lambda: _env("AUTH_COOKIE_NAME", "predibeat_session"))
    auth_session_minutes: int = field(default_factory=lambda: _env_int("AUTH_SESSION_MINUTES", 720))
    auth_cookie_secure: bool = field(
        default_factory=lambda: _env("AUTH_COOKIE_SECURE", "false").lower() in {"1", "true", "yes", "on"}
    )

    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "sqlite:///./predibeat.db"))

    # Local Ollama models.
    ollama_base_url: str = field(
        default_factory=lambda: _env("OLLAMA_BASE_URL", "http://host.docker.internal:11435")
    )
    ollama_timeout_seconds: int = field(default_factory=lambda: _env_int("OLLAMA_TIMEOUT_SECONDS", 180))
    embedding_model: str = field(default_factory=lambda: _env("EMBEDDING_MODEL", "bge-m3"))
    qa_model: str = field(default_factory=lambda: _env("QA_MODEL", "llama3.1:8b"))
    chatbot_history_chars: int = field(default_factory=lambda: _env_int("CHATBOT_HISTORY_CHARS", 4000))
    chatbot_keep_alive: str = field(default_factory=lambda: _env("CHATBOT_KEEP_ALIVE", "10m"))
    vision_model: str = field(default_factory=lambda: _env("VISION_MODEL", "llava"))

    # Qdrant may run locally or on a separate server. API key is optional.
    qdrant_url: str = field(default_factory=lambda: _env("QDRANT_URL", "http://qdrant:6333"))
    qdrant_api_key: str = field(default_factory=lambda: _env("QDRANT_API_KEY", ""))
    vector_size: int = field(default_factory=lambda: _env_int("VECTOR_SIZE", 1024))
    pdf_chunks_collection: str = field(
        default_factory=lambda: _env("QDRANT_PDF_CHUNKS_COLLECTION", "predibeat_pdf_chunks")
    )
    pdf_qa_collection: str = field(
        default_factory=lambda: _env("QDRANT_PDF_QA_COLLECTION", "predibeat_pdf_qa")
    )
    food_chunks_collection: str = field(
        default_factory=lambda: _env("QDRANT_FOOD_COLLECTION", "predibeat_food_chunks")
    )

    rag_inbox_dir: Path = field(default_factory=lambda: Path(_env("RAG_INBOX_DIR", "/app/data/rag/inbox")))
    rag_output_dir: Path = field(default_factory=lambda: Path(_env("RAG_OUTPUT_DIR", "/app/data/rag/output")))
    rag_processed_dir: Path = field(default_factory=lambda: Path(_env("RAG_PROCESSED_DIR", "/app/data/rag/processed")))
    rag_failed_dir: Path = field(default_factory=lambda: Path(_env("RAG_FAILED_DIR", "/app/data/rag/failed")))

    food_dataset_path: Path = field(
        default_factory=lambda: Path(
            _env("FOOD_DATASET_PATH", "/app/data/reference/food/master_makanan_kategori_flag_mealplan.csv")
        )
    )
    activity_dataset_path: Path = field(
        default_factory=lambda: Path(_env("ACTIVITY_DATASET_PATH", "/app/data/reference/activities.csv"))
    )
    diet_dataset_path: Path = field(
        default_factory=lambda: Path(
            _env("DIET_DATASET_PATH", "/app/data/reference/diets/NutrinusaDatabase_InformationDiet.csv")
        )
    )
    dataset_backup_dir: Path = field(
        default_factory=lambda: Path(_env("DATASET_BACKUP_DIR", "/app/data/reference/backups"))
    )

    worker_poll_seconds: int = field(default_factory=lambda: _env_int("WORKER_POLL_SECONDS", 5))
    rag_process_mode: str = field(default_factory=lambda: _env("RAG_PROCESS_MODE", "worker"))
    rag_delete_source_after_index: bool = field(
        default_factory=lambda: _env("RAG_DELETE_SOURCE_AFTER_INDEX", "false").lower() in {"1", "true", "yes", "on"}
    )

    mineru_backend: str = field(default_factory=lambda: _env("MINERU_BACKEND", "pipeline"))
    mineru_method: str = field(default_factory=lambda: _env("MINERU_METHOD", "auto"))
    mineru_command: str = field(default_factory=lambda: _env("MINERU_COMMAND", "mineru"))
    mineru_fallback_pypdf: bool = field(
        default_factory=lambda: _env("MINERU_FALLBACK_PYPDF", "true").lower() in {"1", "true", "yes", "on"}
    )

    pdf_chunk_max_tokens: int = field(default_factory=lambda: _env_int("PDF_CHUNK_MAX_TOKENS", 900))
    pdf_chunk_overlap_tokens: int = field(default_factory=lambda: _env_int("PDF_CHUNK_OVERLAP_TOKENS", 100))

    def ensure_runtime_directories(self) -> None:
        for path in (
            self.rag_inbox_dir,
            self.rag_output_dir,
            self.rag_processed_dir,
            self.rag_failed_dir,
            self.food_dataset_path.parent,
            self.diet_dataset_path.parent,
            self.activity_dataset_path.parent,
            self.dataset_backup_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
