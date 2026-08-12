from pathlib import Path

import pytest

from app.rag.domain.models import DocumentElement
from app.rag.extractors.fallback_pdf_extractor import FallbackPdfExtractor
from app.rag.extractors.pypdf_extractor import PyPdfTextExtractor


class FailingPrimary:
    def __init__(self):
        self.calls = 0

    def extract(self, source_path, output_dir):
        self.calls += 1
        raise RuntimeError("MinerU gagal")


class WorkingFallback:
    def __init__(self):
        self.calls = 0

    def extract(self, source_path, output_dir):
        self.calls += 1
        return [DocumentElement("p1", "text", "Isi fallback", 1)]


class WorkingPrimary:
    def __init__(self):
        self.calls = 0

    def extract(self, source_path, output_dir):
        self.calls += 1
        return [DocumentElement("m1", "text", "Isi MinerU", 1)]


def test_fallback_extractor_uses_secondary_only_after_primary_failure(tmp_path: Path):
    primary = FailingPrimary()
    fallback = WorkingFallback()
    extractor = FallbackPdfExtractor(primary, fallback, enabled=True)

    result = extractor.extract(tmp_path / "doc.pdf", tmp_path / "out")

    assert result[0].content == "Isi fallback"
    assert primary.calls == 1
    assert fallback.calls == 1


def test_fallback_extractor_keeps_primary_result_when_mineru_succeeds(tmp_path: Path):
    primary = WorkingPrimary()
    fallback = WorkingFallback()
    extractor = FallbackPdfExtractor(primary, fallback, enabled=True)

    result = extractor.extract(tmp_path / "doc.pdf", tmp_path / "out")

    assert result[0].content == "Isi MinerU"
    assert fallback.calls == 0


def test_fallback_extractor_reraises_when_disabled(tmp_path: Path):
    extractor = FallbackPdfExtractor(FailingPrimary(), WorkingFallback(), enabled=False)

    with pytest.raises(RuntimeError, match="MinerU gagal"):
        extractor.extract(tmp_path / "doc.pdf", tmp_path / "out")


def test_pypdf_extractor_builds_one_element_per_nonempty_page(tmp_path: Path, monkeypatch):
    class FakePage:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class FakeReader:
        def __init__(self, path):
            self.pages = [FakePage("Halaman satu"), FakePage("  "), FakePage("Halaman tiga")]

    import sys
    from types import ModuleType

    fake_pypdf = ModuleType("pypdf")
    fake_pypdf.PdfReader = FakeReader
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-test")
    elements = PyPdfTextExtractor().extract(pdf, tmp_path / "out")

    assert [item.page for item in elements] == [1, 3]
    assert [item.content for item in elements] == ["Halaman satu", "Halaman tiga"]
    assert all(item.metadata["extractor"] == "pypdf" for item in elements)
