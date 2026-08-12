import pytest

from app.api.routes.admin_documents import safe_upload_name, validate_upload_extension


def test_safe_upload_name_removes_path_traversal():
    assert safe_upload_name("../../Panduan Gizi.pdf") == "Panduan_Gizi.pdf"


def test_upload_accepts_only_pdf_and_csv():
    assert validate_upload_extension("x.pdf") == "pdf"
    assert validate_upload_extension("x.csv") == "csv"
    with pytest.raises(ValueError):
        validate_upload_extension("malware.exe")
