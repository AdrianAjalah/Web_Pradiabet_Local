"""Diet/program catalog for user-facing pages.

All rows from the active diet CSV are visible, but only Mediterania,
Rendah Karbo, and Intermittent Fasting are currently supported. IF is a
separate time pattern and does not replace the active food-pattern diet.
"""
from __future__ import annotations

import csv
import html
import json
import os
import re
from pathlib import Path
from typing import Any


SUPPORTED_DIET_IDS = frozenset({"mediterania", "rendah_karbo"})
SUPPORTED_TIME_PATTERN_IDS = frozenset({"intermittent_fasting"})
SUPPORTED_PROGRAM_IDS = SUPPORTED_DIET_IDS | SUPPORTED_TIME_PATTERN_IDS

_CANONICAL_ALIASES = {
    "dash": "dash",
    "diet dash": "dash",
    "defisit kalori": "defisit_kalori",
    "diet defisit kalori": "defisit_kalori",
    "mediterania": "mediterania",
    "diet mediterania": "mediterania",
    "mediterranean": "mediterania",
    "rendah lemak": "rendah_lemak",
    "diet rendah lemak": "rendah_lemak",
    "tinggi serat": "tinggi_serat",
    "diet tinggi serat": "tinggi_serat",
    "tinggi protein": "tinggi_protein",
    "diet tinggi protein": "tinggi_protein",
    "intermittent fasting": "intermittent_fasting",
    "diet intermittent fasting": "intermittent_fasting",
    "if": "intermittent_fasting",
    "keto": "keto",
    "ketogenik": "keto",
    "diet keto": "keto",
    "diet keto ketogenik": "keto",
    "rendah karbo": "rendah_karbo",
    "rendah karbohidrat": "rendah_karbo",
    "diet rendah karbo": "rendah_karbo",
    "diet rendah karbohidrat": "rendah_karbo",
    "low carb": "rendah_karbo",
    "rendah purin": "rendah_purin",
    "diet rendah purin": "rendah_purin",
    "vegan": "vegan",
    "diet vegan": "vegan",
}

_DIET_IMAGES = {
    "dash": "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?auto=format&fit=crop&w=1200&q=80",
    "defisit_kalori": "https://images.unsplash.com/photo-1490645935967-10de6ba17061?auto=format&fit=crop&w=1200&q=80",
    "mediterania": "https://images.unsplash.com/photo-1498837167922-ddd27525d352?auto=format&fit=crop&w=1200&q=80",
    "rendah_lemak": "https://images.unsplash.com/photo-1547592180-85f173990554?auto=format&fit=crop&w=1200&q=80",
    "tinggi_serat": "https://images.unsplash.com/photo-1540420773420-3366772f4999?auto=format&fit=crop&w=1200&q=80",
    "tinggi_protein": "https://images.unsplash.com/photo-1532550907401-a500c9a57435?auto=format&fit=crop&w=1200&q=80",
    "intermittent_fasting": "https://images.unsplash.com/photo-1493770348161-369560ae357d?auto=format&fit=crop&w=1200&q=80",
    "keto": "https://images.unsplash.com/photo-1543352634-a1c51d9f1fa7?auto=format&fit=crop&w=1200&q=80",
    "rendah_karbo": "https://images.unsplash.com/photo-1543362906-acfc16c67564?auto=format&fit=crop&w=1200&q=80",
    "rendah_purin": "https://images.unsplash.com/photo-1466637574441-749b8f19452f?auto=format&fit=crop&w=1200&q=80",
    "vegan": "https://images.unsplash.com/photo-1511690743698-d9d85f2fbf38?auto=format&fit=crop&w=1200&q=80",
}

_EFFECT_TEXT = {
    "mediterania": (
        "Target kalori dan makro tetap mengikuti profil; meal plan lebih memprioritaskan "
        "sayur, buah utuh, ikan, legum, kacang/biji, karbo kompleks, dan makanan tinggi serat."
    ),
    "rendah_karbo": (
        "Target kalori tetap; target karbo diturunkan, protein sekitar 30% energi, dan lemak "
        "mengisi sisa energi. Ini bukan keto ekstrem."
    ),
    "intermittent_fasting": (
        "Tidak mengubah target kalori atau jenis diet. Sistem hanya menempatkan slot makan "
        "di dalam jendela waktu makan yang dipilih."
    ),
}


def _key(value: object) -> str:
    text = html.unescape(str(value or "")).strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_diet_id(value: object) -> str | None:
    key = _key(value)
    if not key or key in {"none", "null", "tidak ada", "-"}:
        return None
    if key in _CANONICAL_ALIASES:
        return _CANONICAL_ALIASES[key]
    if key.startswith("diet ") and key[5:] in _CANONICAL_ALIASES:
        return _CANONICAL_ALIASES[key[5:]]
    return key.replace(" ", "_")



def is_supported_diet(value: object) -> bool:
    return (normalize_diet_id(value) or "") in SUPPORTED_DIET_IDS



def _json_value(value: object, default: Any) -> Any:
    text = html.unescape(str(value or "")).strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


class DietCatalogService:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._signature: tuple[int, int] | None = None
        self._items: list[dict[str, Any]] = []

    @classmethod
    def from_environment(cls) -> "DietCatalogService":
        return cls(
            os.getenv(
                "DIET_DATASET_PATH",
                "/app/data/reference/diets/NutrinusaDatabase_InformationDiet.csv",
            )
        )

    def _current_signature(self) -> tuple[int, int] | None:
        if not self.path.is_file():
            return None
        stat = self.path.stat()
        return stat.st_mtime_ns, stat.st_size

    def _ensure_loaded(self) -> None:
        signature = self._current_signature()
        if signature == self._signature:
            return
        self._signature = signature
        self._items = self._load() if signature else []

    def _load(self) -> list[dict[str, Any]]:
        with self.path.open("r", encoding="utf-8-sig", newline="", errors="replace") as handle:
            sample = handle.read(4096)
            handle.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            rows = list(csv.DictReader(handle, dialect=dialect))

        items: list[dict[str, Any]] = []
        for row in rows:
            name = html.unescape(str(row.get("nama_diet") or "")).strip()
            diet_id = normalize_diet_id(name)
            if not name or not diet_id:
                continue
            description = html.unescape(str(row.get("deskripsi") or "")).strip()
            target = _json_value(row.get("target"), {})
            principles = _json_value(row.get("prinsip utama"), [])
            recommended = _json_value(row.get("boleh_dikonsumsi"), [])
            limited = _json_value(row.get("batasi_hindari"), [])
            benefits = _json_value(row.get("kelebihan_manfaat"), [])
            risks = _json_value(row.get("kekurangan_risiko"), [])
            note_parts: list[str] = []
            if benefits:
                note_parts.append("Manfaat: " + "; ".join(map(str, benefits)))
            if risks:
                note_parts.append("Perhatian: " + "; ".join(map(str, risks)))

            supported = diet_id in SUPPORTED_PROGRAM_IDS
            program_type = "time_pattern" if diet_id in SUPPORTED_TIME_PATTERN_IDS else "diet"
            items.append(
                {
                    "id": diet_id,
                    "slug": diet_id.replace("_", "-"),
                    "nama": name,
                    "gambar": _DIET_IMAGES.get(diet_id, _DIET_IMAGES["mediterania"]),
                    "ringkas": description,
                    "untuk_apa": description,
                    "efek_makro": _EFFECT_TEXT.get(
                        diet_id,
                        "Logika khusus program ini belum diaktifkan pada tahap sekarang.",
                    ),
                    "komposisi": principles if isinstance(principles, list) else [],
                    "dianjurkan": recommended if isinstance(recommended, list) else [],
                    "dibatasi": limited if isinstance(limited, list) else [],
                    "catatan": " ".join(note_parts)
                    or (
                        "Program ini sudah dapat digunakan."
                        if supported
                        else "Program ini masih Coming Soon dan belum memengaruhi meal plan."
                    ),
                    "target": target if isinstance(target, dict) else {},
                    "supported": supported,
                    "coming_soon": not supported,
                    "program_type": program_type,
                }
            )
        return items

    def list_diets(self) -> list[dict[str, Any]]:
        self._ensure_loaded()
        return [dict(item) for item in self._items]

    def get_diet(self, value: object) -> dict[str, Any] | None:
        diet_id = normalize_diet_id(value)
        if not diet_id:
            return None
        self._ensure_loaded()
        for item in self._items:
            if item["id"] == diet_id:
                return dict(item)
        return None


_default_service: DietCatalogService | None = None
_default_path: str | None = None


def get_diet_catalog_service() -> DietCatalogService:
    global _default_service, _default_path
    path = os.getenv(
        "DIET_DATASET_PATH",
        "/app/data/reference/diets/NutrinusaDatabase_InformationDiet.csv",
    )
    if _default_service is None or _default_path != path:
        _default_service = DietCatalogService(path)
        _default_path = path
    return _default_service
