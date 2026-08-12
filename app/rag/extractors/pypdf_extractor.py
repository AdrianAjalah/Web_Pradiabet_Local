"""Fallback text extractor using pypdf, one element per non-empty page."""
from __future__ import annotations

import hashlib
from pathlib import Path

from app.rag.domain.models import DocumentElement


class PyPdfTextExtractor:
    def extract(self, source_path: Path, output_dir: Path) -> list[DocumentElement]:
        from pypdf import PdfReader

        source_path = Path(source_path)
        if source_path.suffix.lower() != ".pdf":
            raise ValueError("PyPDF extractor hanya menerima file PDF.")
        if not source_path.exists():
            raise FileNotFoundError(source_path)

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        reader = PdfReader(str(source_path))
        elements: list[DocumentElement] = []
        for index, page in enumerate(reader.pages, start=1):
            content = str(page.extract_text() or "").strip()
            if not content:
                continue
            digest = hashlib.sha1(f"{source_path.name}:{index}:{content}".encode("utf-8")).hexdigest()[:16]
            elements.append(
                DocumentElement(
                    element_id=f"pypdf-{digest}",
                    element_type="text",
                    content=content,
                    page=index,
                    metadata={"extractor": "pypdf"},
                )
            )
        if not elements:
            raise RuntimeError(
                "PDF tidak memiliki teks yang dapat diekstrak. Gunakan MinerU/OCR untuk PDF hasil scan."
            )
        return elements
