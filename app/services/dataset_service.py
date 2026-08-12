"""Pengelolaan dataset referensi aktif dan backup yang terisolasi.

Loader aplikasi selalu membaca path canonical pada ``DatasetDefinition``. File di
folder backup hanya dipakai ketika admin secara eksplisit melakukan pemulihan.
"""
from __future__ import annotations

import csv
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True, slots=True)
class DatasetDefinition:
    key: str
    label: str
    path: Path
    required_columns: tuple[str, ...]
    description: str = ""
    rag_enabled: bool = False


@dataclass(frozen=True, slots=True)
class DatasetStatus:
    key: str
    label: str
    description: str
    path: str
    exists: bool
    row_count: int
    column_count: int
    columns: tuple[str, ...]
    delimiter: str
    size_bytes: int
    modified_at: str | None
    rag_enabled: bool

    def to_dict(self) -> dict:
        data = asdict(self)
        data["columns"] = list(self.columns)
        return data


@dataclass(frozen=True, slots=True)
class DatasetBackup:
    key: str
    name: str
    path: str
    size_bytes: int
    modified_at: str

    def to_dict(self) -> dict:
        return asdict(self)


class DatasetService:
    def __init__(
        self,
        definitions: Mapping[str, DatasetDefinition],
        backup_dir: Path,
    ) -> None:
        self.definitions = dict(definitions)
        self.backup_dir = Path(backup_dir)

    @classmethod
    def from_settings(cls, settings) -> "DatasetService":
        return cls(
            {
                "food": DatasetDefinition(
                    key="food",
                    label="Master Makanan & Meal Plan",
                    path=settings.food_dataset_path,
                    required_columns=("nama_makanan", "kelompok_makanan", "gula_g"),
                    description=(
                        "Sumber utama data makanan, nilai gizi, kategori, dan flag meal plan. "
                        "PrediBeat V3 membacanya melalui structured SQLite retrieval; bukan RAG makanan."
                    ),
                    rag_enabled=False,
                ),
                "diets": DatasetDefinition(
                    key="diets",
                    label="Informasi Jenis Diet",
                    path=settings.diet_dataset_path,
                    required_columns=("nama_diet", "deskripsi", "target", "prinsip utama"),
                    description=(
                        "Referensi penjelasan diet untuk dashboard dan service rekomendasi diet. "
                        "Dataset ini dibaca langsung dan tidak masuk collection makanan Qdrant."
                    ),
                    rag_enabled=False,
                ),
            },
            backup_dir=settings.dataset_backup_dir,
        )

    def list_statuses(self) -> list[DatasetStatus]:
        return [self.get_status(key) for key in self.definitions]

    def get_definition(self, key: str) -> DatasetDefinition:
        try:
            return self.definitions[key]
        except KeyError as exc:
            raise KeyError(f"Dataset tidak dikenal: {key}") from exc

    def get_status(self, key: str) -> DatasetStatus:
        definition = self.get_definition(key)
        if not definition.path.exists():
            return DatasetStatus(
                key=key,
                label=definition.label,
                description=definition.description,
                path=str(definition.path),
                exists=False,
                row_count=0,
                column_count=0,
                columns=(),
                delimiter="",
                size_bytes=0,
                modified_at=None,
                rag_enabled=definition.rag_enabled,
            )

        delimiter, columns, row_count = self._inspect_csv(definition.path)
        stat = definition.path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        return DatasetStatus(
            key=key,
            label=definition.label,
            description=definition.description,
            path=str(definition.path),
            exists=True,
            row_count=row_count,
            column_count=len(columns),
            columns=tuple(columns),
            delimiter=delimiter,
            size_bytes=stat.st_size,
            modified_at=modified,
            rag_enabled=definition.rag_enabled,
        )

    def replace(self, key: str, incoming_path: Path) -> DatasetStatus:
        definition = self.get_definition(key)
        incoming_path = Path(incoming_path)
        self._validate_for_definition(definition, incoming_path)

        definition.path.parent.mkdir(parents=True, exist_ok=True)
        if definition.path.exists():
            self._backup_active(definition)
        self._atomic_copy(incoming_path, definition.path)
        return self.get_status(key)

    def list_backups(self, key: str) -> list[DatasetBackup]:
        self.get_definition(key)
        paths: list[Path] = []
        dataset_dir = self.backup_dir / key
        if dataset_dir.exists():
            paths.extend(path for path in dataset_dir.glob("*.csv") if path.is_file())

        # Kompatibilitas backup versi awal yang disimpan langsung di backup_dir.
        if self.backup_dir.exists():
            paths.extend(path for path in self.backup_dir.glob(f"{key}__*.csv") if path.is_file())

        unique = {path.resolve(strict=False): path for path in paths}
        ordered = sorted(unique.values(), key=lambda path: path.stat().st_mtime, reverse=True)
        return [
            DatasetBackup(
                key=key,
                name=path.name,
                path=str(path),
                size_bytes=path.stat().st_size,
                modified_at=datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            )
            for path in ordered
        ]

    def restore(self, key: str, backup_name: str) -> DatasetStatus:
        definition = self.get_definition(key)
        raw_name = str(backup_name or "")
        if not raw_name or Path(raw_name).name != raw_name:
            raise ValueError("Backup tidak ditemukan atau nama backup tidak valid.")

        available = {backup.name: Path(backup.path) for backup in self.list_backups(key)}
        backup_path = available.get(raw_name)
        if backup_path is None or not backup_path.exists():
            raise ValueError("Backup tidak ditemukan atau bukan milik dataset ini.")
        self._validate_for_definition(definition, backup_path)

        definition.path.parent.mkdir(parents=True, exist_ok=True)
        if definition.path.exists():
            self._backup_active(definition)
        self._atomic_copy(backup_path, definition.path)
        return self.get_status(key)

    def _backup_active(self, definition: DatasetDefinition) -> Path:
        dataset_dir = self.backup_dir / definition.key
        dataset_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = dataset_dir / f"{timestamp}__{definition.path.name}"
        shutil.copy2(definition.path, backup_path)
        return backup_path

    def _validate_for_definition(self, definition: DatasetDefinition, incoming_path: Path) -> None:
        incoming_path = Path(incoming_path)
        if incoming_path.suffix.lower() != ".csv":
            raise ValueError("Dataset harus berupa file CSV.")
        if not incoming_path.exists() or not incoming_path.is_file():
            raise ValueError("File dataset tidak ditemukan.")

        _delimiter, columns, _row_count = self._inspect_csv(incoming_path)
        normalized = {self._normalize_header(column) for column in columns}
        missing = [
            column
            for column in definition.required_columns
            if self._normalize_header(column) not in normalized
        ]
        if missing:
            raise ValueError("Kolom wajib tidak ditemukan: " + ", ".join(missing))

    @staticmethod
    def _atomic_copy(source: Path, destination: Path) -> None:
        temporary = destination.with_name(f".{destination.name}.tmp")
        try:
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _normalize_header(value: str) -> str:
        return str(value or "").replace("\ufeff", "").strip().lower()

    @classmethod
    def _inspect_csv(cls, path: Path) -> tuple[str, list[str], int]:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            sample = handle.read(16384)
            handle.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
                delimiter = dialect.delimiter
            except csv.Error:
                delimiter = ";" if sample.count(";") > sample.count(",") else ","

            reader = csv.reader(handle, delimiter=delimiter)
            try:
                raw_headers = next(reader)
            except StopIteration as exc:
                raise ValueError("CSV kosong dan tidak memiliki header.") from exc

            columns = [header.replace("\ufeff", "").strip() for header in raw_headers]
            if not any(columns):
                raise ValueError("Header CSV tidak valid.")

            row_count = 0
            for row in reader:
                if any(str(value).strip() for value in row):
                    row_count += 1
        return delimiter, columns, row_count
