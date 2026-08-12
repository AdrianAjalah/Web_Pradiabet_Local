"""Konfigurasi logging bersama untuk web dan RAG worker.

Tujuannya agar format log konsisten dan level log dapat diatur melalui
``LOG_LEVEL`` tanpa menulis ``logging.basicConfig`` di banyak file.
"""
from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> None:
    """Aktifkan format log standar PrediBeat.

    Fungsi ini aman dipanggil lebih dari sekali. ``force=True`` memastikan
    konfigurasi Uvicorn/worker tidak meninggalkan handler lama yang membuat log
    tercetak ganda saat development reload.
    """

    resolved_level = getattr(logging, (level or "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=resolved_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        force=True,
    )
