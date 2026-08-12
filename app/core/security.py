"""Helper keamanan umum yang tidak bergantung pada route tertentu."""
from __future__ import annotations

import re
from pathlib import Path

_ALLOWED_UPLOAD_SUFFIXES = {".pdf": "pdf", ".csv": "csv"}


def safe_upload_name(filename: str) -> str:
    """Buang path traversal dan karakter berbahaya dari nama upload."""

    name = Path(filename or "upload").name
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return clean or "upload"


def validate_upload_extension(filename: str) -> str:
    """Kembalikan ``pdf``/``csv`` atau tolak ekstensi selain keduanya."""

    suffix = Path(filename).suffix.lower()
    try:
        return _ALLOWED_UPLOAD_SUFFIXES[suffix]
    except KeyError as exc:
        raise ValueError("Hanya file PDF dan CSV yang didukung.") from exc

