"""MinerU-first extractor with an optional lightweight fallback."""
from __future__ import annotations

import logging

logger = logging.getLogger("predibeat.pdf_extractor")


class FallbackPdfExtractor:
    def __init__(self, primary, fallback, *, enabled: bool = True) -> None:
        self.primary = primary
        self.fallback = fallback
        self.enabled = bool(enabled)

    def extract(self, source_path, output_dir):
        try:
            return self.primary.extract(source_path, output_dir)
        except Exception as exc:
            if not self.enabled:
                raise
            logger.warning(
                "MinerU gagal untuk %s, memakai fallback pypdf: %s",
                getattr(source_path, "name", source_path),
                exc,
            )
            return self.fallback.extract(source_path, output_dir)
