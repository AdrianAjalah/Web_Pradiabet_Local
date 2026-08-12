from pathlib import Path

import pytest

from app.services.dataset_service import DatasetDefinition, DatasetService


def test_reads_semicolon_food_dataset_and_counts_rows(tmp_path: Path):
    path = tmp_path / "food.csv"
    path.write_text(
        "nama_makanan;kelompok_makanan;gula_g\nApel;Buah;10,2\nTempe;Lauk Nabati;0\n",
        encoding="utf-8-sig",
    )
    service = DatasetService(
        {
            "food": DatasetDefinition(
                key="food",
                label="Dataset Makanan",
                path=path,
                required_columns=("nama_makanan", "kelompok_makanan", "gula_g"),
            )
        },
        backup_dir=tmp_path / "backups",
    )

    status = service.get_status("food")

    assert status.exists is True
    assert status.row_count == 2
    assert status.column_count == 3
    assert status.delimiter == ";"


def test_replace_dataset_creates_backup_and_validates_columns(tmp_path: Path):
    current = tmp_path / "food.csv"
    current.write_text(
        "nama_makanan;kelompok_makanan;gula_g\nApel;Buah;10\n",
        encoding="utf-8-sig",
    )
    incoming = tmp_path / "incoming.csv"
    incoming.write_text(
        "nama_makanan;kelompok_makanan;gula_g\nPir;Buah;8\n",
        encoding="utf-8-sig",
    )
    service = DatasetService(
        {
            "food": DatasetDefinition(
                key="food",
                label="Dataset Makanan",
                path=current,
                required_columns=("nama_makanan", "kelompok_makanan", "gula_g"),
            )
        },
        backup_dir=tmp_path / "backups",
    )

    result = service.replace("food", incoming)

    assert result.row_count == 1
    assert "Pir" in current.read_text(encoding="utf-8-sig")
    assert len(list((tmp_path / "backups" / "food").glob("*.csv"))) == 1


def test_replace_rejects_missing_required_columns(tmp_path: Path):
    current = tmp_path / "food.csv"
    current.write_text(
        "nama_makanan;kelompok_makanan;gula_g\nApel;Buah;10\n",
        encoding="utf-8-sig",
    )
    incoming = tmp_path / "invalid.csv"
    incoming.write_text("nama;kalori\nApel;52\n", encoding="utf-8")
    service = DatasetService(
        {
            "food": DatasetDefinition(
                key="food",
                label="Dataset Makanan",
                path=current,
                required_columns=("nama_makanan", "kelompok_makanan", "gula_g"),
            )
        },
        backup_dir=tmp_path / "backups",
    )

    with pytest.raises(ValueError, match="Kolom wajib"):
        service.replace("food", incoming)
