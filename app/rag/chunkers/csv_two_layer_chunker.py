"""Chunking khusus dataset makanan CSV tanpa ekstraksi MinerU dan tanpa QA."""
from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping

from app.rag.domain.models import Chunk


BOOL_FIELDS = (
    "mengandung_susu",
    "mengandung_telur",
    "mengandung_seafood",
    "mengandung_kacang",
    "mengandung_babi",
    "mengandung_santan",
    "mengandung_alkohol",
    "mengandung_sayur",
    "adalah_gorengan",
    "sumber_karbohidrat",
    "karbohidrat_kompleks",
    "karbohidrat_olahan",
)

FLAG_LABELS = {
    "mengandung_susu": "Mengandung Susu",
    "mengandung_telur": "Mengandung Telur",
    "mengandung_seafood": "Mengandung Seafood",
    "mengandung_kacang": "Mengandung Kacang",
    "mengandung_babi": "Mengandung Babi",
    "mengandung_santan": "Mengandung Santan",
    "mengandung_alkohol": "Mengandung Alkohol",
    "mengandung_sayur": "Mengandung Sayur",
    "adalah_gorengan": "Adalah Gorengan",
    "sumber_karbohidrat": "Sumber Karbohidrat",
    "karbohidrat_kompleks": "Karbohidrat Kompleks",
    "karbohidrat_olahan": "Karbohidrat Olahan",
}


def _clean(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"nan", "none", "null", "-"} else text


def _chunk_id(*parts: object) -> str:
    return "food-" + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:16]


def _number(value: object) -> float:
    """Parse angka CSV Indonesia maupun internasional menjadi float."""

    text = _clean(value).replace(" ", "")
    if not text:
        return 0.0
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _boolean(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return _clean(value).lower() in {"1", "true", "ya", "yes", "y", "benar"}


class CsvTwoLayerChunker:
    def chunk_file(self, source_path: Path, source_id: str, source_name: str | None = None) -> list[Chunk]:
        source_path = Path(source_path)
        with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
            sample = handle.read(4096)
            handle.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
            except csv.Error:
                dialect = csv.excel
            rows = list(csv.DictReader(handle, dialect=dialect))
        return self.chunk_rows(rows, source_id=source_id, source_name=source_name or source_path.name)

    def chunk_rows(
        self,
        rows: Iterable[Mapping[str, object]],
        source_id: str,
        source_name: str,
    ) -> list[Chunk]:
        chunks: list[Chunk] = []
        groups: dict[str, list[str]] = defaultdict(list)
        group_flag_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for row_number, row in enumerate(rows, start=1):
            name = _clean(row.get("nama_makanan") or row.get("nama"))
            if not name:
                continue
            code = _clean(row.get("kode")) or str(row_number)
            category = _clean(row.get("kelompok_makanan") or row.get("kategori")) or "Tanpa Kategori"
            flags = {field: _boolean(row.get(field)) for field in BOOL_FIELDS}
            content = self._build_food_content(row, name=name, category=category, flags=flags)
            groups[category].append(name)
            for field, enabled in flags.items():
                if enabled:
                    group_flag_counts[category][field] += 1
            chunks.append(
                Chunk(
                    chunk_id=_chunk_id(source_id, "row", code, name.lower()),
                    source_id=source_id,
                    source_name=source_name,
                    source_type="csv",
                    layer=0,
                    chunk_type="food_row",
                    content=content,
                    metadata={
                        "food_name": name.lower(),
                        "food_name_display": name,
                        "food_code": code,
                        "food_category": category,
                        "slot_meal_plan": _clean(row.get("slot_meal_plan")),
                        "kalori_kkal": _number(row.get("kalori_kkal")),
                        "karbohidrat_g": _number(row.get("karbohidrat_g")),
                        "protein_g": _number(row.get("protein_g")),
                        "lemak_g": _number(row.get("lemak_g")),
                        "serat_g": _number(row.get("serat_g")),
                        "gula_g": _number(row.get("gula_g")),
                        "natrium_mg": _number(row.get("natrium_mg")),
                        "indeks_glikemik": _number(row.get("indeks_glikemik")),
                        "beban_glikemik": _number(row.get("beban_glikemik")),
                        "is_fruit": "buah" in category.lower(),
                        "sugar_interpretation": (
                            "natural_fruit_sugar"
                            if "buah" in category.lower()
                            else "standard_sugar"
                        ),
                        "tingkat_proses": _clean(row.get("tingkat_proses")),
                        **flags,
                    },
                )
            )

        for category, names in sorted(groups.items()):
            content = (
                f"Kelompok makanan: {category}. Total item: {len(names)}. "
                f"Daftar contoh makanan: {', '.join(names[:50])}."
            )
            chunks.append(
                Chunk(
                    chunk_id=_chunk_id(source_id, "group", category.lower()),
                    source_id=source_id,
                    source_name=source_name,
                    source_type="csv",
                    layer=1,
                    chunk_type="food_group",
                    content=content,
                    metadata={
                        "food_category": category,
                        "food_count": len(names),
                        "flag_counts": {field: int(group_flag_counts[category].get(field, 0)) for field in BOOL_FIELDS},
                    },
                )
            )
        return chunks

    @staticmethod
    def _build_food_content(
        row: Mapping[str, object],
        name: str,
        category: str,
        flags: Mapping[str, bool] | None = None,
    ) -> str:
        labels = {
            "kode": "Kode",
            "kelompok_makanan": "Kelompok Makanan",
            "jenis_bahan_utama": "Jenis Bahan Utama",
            "tingkat_proses": "Tingkat Proses",
            "slot_meal_plan": "Slot Meal Plan",
            "gram_porsi": "Porsi (g)",
            "kalori_kkal": "Kalori (kkal)",
            "karbohidrat_g": "Karbohidrat (g)",
            "protein_g": "Protein (g)",
            "lemak_g": "Lemak (g)",
            "serat_g": "Serat (g)",
            "gula_g": "Gula (g)",
            "natrium_mg": "Natrium (mg)",
            "indeks_glikemik": "Indeks Glikemik",
            "beban_glikemik": "Beban Glikemik",
        }
        parts = [f"Nama Makanan: {name}", f"Kategori: {category}"]
        for key, label in labels.items():
            value = _clean(row.get(key))
            if value:
                parts.append(f"{label}: {value}")

        sugar_text = _clean(row.get("gula_g"))
        try:
            sugar = _number(sugar_text)
        except ValueError:
            sugar = 0.0
        is_fruit = "buah" in category.lower()
        if sugar >= 10 and is_fruit:
            parts.append(
                "Interpretasi gula: gula pada kategori Buah diperlakukan sebagai gula alami buah, "
                "bukan seperti gula pada minuman manis, dessert, snack, atau makanan ultra-proses; porsi tetap dijaga."
            )
        elif sugar >= 10:
            parts.append("Interpretasi gula: kandungan gula cukup tinggi sehingga perlu dibatasi untuk prediabetes.")

        process = _clean(row.get("tingkat_proses")).lower()
        if "ultra" in process:
            parts.append("Interpretasi proses: makanan ultra-proses sebaiknya dibatasi.")
        return "\n".join(parts)
