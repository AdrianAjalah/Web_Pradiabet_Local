"""CSV-backed food catalogue for the user menu page."""
from __future__ import annotations

import csv
import math
import os
from pathlib import Path
from typing import Any

HIGH_SODIUM_MG = 400.0
HIGH_SUGAR_G = 22.5
HIGH_GI_VALUE = 70.0
HIGH_FIBER_G = 6.0
HIGH_PROTEIN_G = 10.0
HIGH_CALORIE_KCAL = 300.0


def _clean(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"nan", "none", "null", "-"} else text


def _number(value: object, default: float = 0.0) -> float:
    text = _clean(value).replace(" ", "")
    if not text:
        return default
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return default


def _bool(value: object) -> bool:
    return _clean(value).lower() in {"1", "true", "ya", "yes", "y", "benar"}


def _fmt(value: float, decimals: int = 1) -> str:
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.{decimals}f}"


def _url(value: object) -> str:
    text = _clean(value)
    return text if text.startswith(("http://", "https://")) else ""


def _row_value(row: dict[str, str], *names: str, default: str = "") -> str:
    for name in names:
        value = row.get(name)
        if _clean(value):
            return _clean(value)
    return default


def _icon(category: str) -> str:
    key = category.lower()
    if "buah" in key:
        return "🍎"
    if "sayur" in key:
        return "🥦"
    if "minuman" in key:
        return "🥤"
    if "seafood" in key:
        return "🐟"
    if "dairy" in key:
        return "🥛"
    if "snack" in key or "dessert" in key:
        return "🍪"
    if "bumbu" in key:
        return "🧂"
    if "mentah" in key:
        return "🌾"
    if "lauk" in key:
        return "🍗"
    return "🍽️"


def _glycemic_label(gi: float) -> tuple[str, str, str]:
    if gi >= HIGH_GI_VALUE:
        return "high", "High", "bg-red-50 text-red-700 border-red-100"
    if 0 < gi <= 55:
        return "low", "Low", "bg-emerald-50 text-emerald-700 border-emerald-100"
    if gi > 0:
        return "moderate", "Medium", "bg-amber-50 text-amber-700 border-amber-100"
    return "", "-", "bg-slate-50 text-slate-500 border-slate-100"


class MenuDatasetService:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._signature: tuple[int, int] | None = None
        self._items: list[dict[str, Any]] = []

    @classmethod
    def from_environment(cls) -> "MenuDatasetService":
        return cls(os.getenv("FOOD_DATASET_PATH", "/app/data/reference/food/master_makanan_kategori_flag_mealplan.csv"))

    def _ensure_loaded(self) -> None:
        signature = None
        if self.path.is_file():
            stat = self.path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
        if signature == self._signature:
            return
        self._signature = signature
        self._items = self._load() if signature else []

    def _load(self) -> list[dict[str, Any]]:
        with self.path.open("r", encoding="utf-8-sig", newline="", errors="replace") as handle:
            sample = handle.read(4096)
            handle.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
            except csv.Error:
                dialect = csv.excel
            rows = list(csv.DictReader(handle, dialect=dialect))

        result: list[dict[str, Any]] = []
        for row in rows:
            name = _row_value(row, "nama_makanan", "nama")
            if not name:
                continue
            category = _row_value(row, "kelompok_makanan", "kategori_utama", "kategori", default="Lainnya")
            ingredient = _row_value(row, "jenis_bahan_utama")
            process = _row_value(row, "tingkat_proses")
            slot = _row_value(row, "slot_meal_plan", default="No Meal")
            calories = _number(_row_value(row, "kalori_kkal", "kalori_kal", "kalori"))
            carbs = _number(_row_value(row, "karbohidrat_g", "karbo", "karbo_g"))
            protein = _number(row.get("protein_g"))
            fat = _number(row.get("lemak_g"))
            fiber = _number(row.get("serat_g"))
            sugar = _number(row.get("gula_g"))
            sodium = _number(_row_value(row, "natrium_mg", "sodium_mg", "sodium"))
            gi_original = _number(row.get("indeks_glikemik"))
            gi_estimated = _number(row.get("indeks_glikemik_estimasi"))
            gi = gi_original if gi_original > 0 else gi_estimated
            gi_source = "GI asli" if gi_original > 0 else ("Estimasi GI" if gi_estimated > 0 else "-")
            gl = _number(row.get("beban_glikemik"))
            glycemic_risk, risk_label, risk_class = _glycemic_label(gi)
            is_fruit = category.casefold() == "buah" or slot.casefold() == "buah"
            high_sugar = sugar >= HIGH_SUGAR_G and not is_fruit
            natural_fruit_sugar = sugar >= HIGH_SUGAR_G and is_fruit
            high_sodium = sodium >= HIGH_SODIUM_MG
            high_gi = gi >= HIGH_GI_VALUE
            low_gi = 0 < gi <= 55
            ultra = process.casefold() == "ultraproses"
            fried = _bool(row.get("adalah_gorengan"))
            raw = process.casefold() == "mentah"
            beverage = category.casefold() == "minuman"
            pork = _bool(row.get("mengandung_babi"))
            alcohol = _bool(row.get("mengandung_alkohol"))
            high_fiber = fiber >= HIGH_FIBER_G
            high_protein = protein >= HIGH_PROTEIN_G
            recommended = not any((high_sodium, high_sugar, high_gi, ultra, fried, raw, pork, alcohol))

            flags: list[dict[str, str]] = []
            flag_defs = [
                (recommended, "recommended", "Lebih aman", "bg-emerald-50 text-emerald-700 border-emerald-100"),
                (high_sodium, "high_sodium", "High sodium", "bg-orange-50 text-orange-700 border-orange-100"),
                (high_sugar, "high_sugar", "High sugar", "bg-rose-50 text-rose-700 border-rose-100"),
                (natural_fruit_sugar, "fruit_sugar", "Gula alami buah", "bg-lime-50 text-lime-700 border-lime-100"),
                (high_gi, "high_glycemic", "High GI", "bg-red-50 text-red-700 border-red-100"),
                (ultra, "ultra_processed", "Ultra-proses", "bg-slate-100 text-slate-700 border-slate-200"),
                (fried, "fried", "Gorengan", "bg-amber-50 text-amber-700 border-amber-100"),
                (raw, "raw", "Bahan mentah", "bg-zinc-100 text-zinc-700 border-zinc-200"),
                (low_gi, "low_gi", "Low GI", "bg-teal-50 text-teal-700 border-teal-100"),
                (high_fiber, "high_fiber", "Tinggi serat", "bg-green-50 text-green-700 border-green-100"),
                (high_protein, "high_protein", "Tinggi protein", "bg-blue-50 text-blue-700 border-blue-100"),
            ]
            for condition, key, label, css in flag_defs:
                if condition:
                    flags.append({"key": key, "label": label, "class": css})

            result.append(
                {
                    "kode": _row_value(row, "kode"),
                    "nama": name,
                    "kategori_utama": category,
                    "kelompok_makanan": category,
                    "jenis_bahan_utama": ingredient,
                    "tingkat_proses": process,
                    "slot_meal_plan": slot,
                    "kategori_detail": " • ".join(part for part in (ingredient, process, slot) if part) or "Umum",
                    "sumber_file": _row_value(row, "file_sumber", "sumber_file"),
                    "hotlink": _url(_row_value(row, "gambar", "hotlink")),
                    "icon": _icon(category),
                    "porsi_g": _number(_row_value(row, "gram_porsi", "porsi_g"), 100.0),
                    "kalori_kal": calories,
                    "karbohidrat_g": carbs,
                    "protein_g": protein,
                    "lemak_g": fat,
                    "serat_g": fiber,
                    "gula_g": sugar,
                    "sodium_mg": sodium,
                    "glikemik_indeks": gi,
                    "gi_source": gi_source,
                    "glikemik_load": gl,
                    "glikemik_risk": glycemic_risk,
                    "glikemik_risk_label": risk_label,
                    "glikemik_risk_class": risk_class,
                    "net_karbo": max(0.0, carbs - fiber),
                    "lemak_jenuh_g": _number(row.get("lemak_jenuh_g")),
                    "lemak_trans_g": _number(row.get("lemak_trans_g")),
                    "kalori_fmt": _fmt(calories, 0),
                    "karbo_fmt": _fmt(carbs),
                    "protein_fmt": _fmt(protein),
                    "lemak_fmt": _fmt(fat),
                    "serat_fmt": _fmt(fiber),
                    "gula_fmt": _fmt(sugar),
                    "sodium_fmt": _fmt(sodium, 0),
                    "gi_fmt": _fmt(gi, 0) if gi else "-",
                    "gl_fmt": _fmt(gl) if gl else "-",
                    "is_high_sodium": high_sodium,
                    "is_high_sugar": high_sugar,
                    "is_natural_fruit_sugar": natural_fruit_sugar,
                    "is_high_glycemic": high_gi,
                    "is_low_glycemic": low_gi,
                    "is_high_glycemic_risk": glycemic_risk == "high",
                    "is_ultraproses": ultra,
                    "is_gorengan": fried,
                    "is_bahan_mentah": raw,
                    "is_minuman": beverage,
                    "is_high_fiber": high_fiber,
                    "is_high_protein": high_protein,
                    "is_high_calorie": calories >= HIGH_CALORIE_KCAL,
                    "is_recommended": recommended,
                    "mengandung_babi": pork,
                    "mengandung_alkohol": alcohol,
                    "flags": flags[:6],
                    "search_text": " ".join((name, _row_value(row, "kode"), category, ingredient, process, slot)).casefold(),
                }
            )
        return result

    def find_item(self, identifier: str) -> dict[str, Any] | None:
        """Find an exact food by code first, then by exact name."""
        self._ensure_loaded()
        key = (identifier or "").strip().casefold()
        if not key:
            return None
        for item in self._items:
            if str(item.get("kode") or "").strip().casefold() == key:
                return dict(item)
        for item in self._items:
            if str(item.get("nama") or "").strip().casefold() == key:
                return dict(item)
        return None

    def search_items(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return compact food matches for tracker autosuggest."""
        result = self.query(q=query, page=1, per_page=max(1, min(limit, 30)))
        return result["items"]

    @staticmethod
    def filter_options() -> list[dict[str, str]]:
        return [
            {"key": "all", "label": "Semua", "icon": "🍽️", "desc": "Seluruh data"},
            {"key": "recommended", "label": "Lebih aman", "icon": "✅", "desc": "Tanpa flag risiko utama"},
            {"key": "high_sodium", "label": "High sodium", "icon": "🧂", "desc": "Natrium tinggi"},
            {"key": "high_sugar", "label": "High sugar", "icon": "🍭", "desc": "Gula tinggi non-buah"},
            {"key": "high_glycemic", "label": "High GI", "icon": "📈", "desc": "GI tinggi"},
            {"key": "ultra_processed", "label": "Ultra-proses", "icon": "📦", "desc": "Tingkat proses tinggi"},
            {"key": "fried", "label": "Gorengan", "icon": "🍟", "desc": "Makanan digoreng"},
            {"key": "raw", "label": "Bahan mentah", "icon": "🌾", "desc": "Belum siap jadi meal plan"},
            {"key": "low_gi", "label": "Low GI", "icon": "🟢", "desc": "GI rendah"},
            {"key": "high_fiber", "label": "Tinggi serat", "icon": "🥬", "desc": "Serat tinggi"},
            {"key": "high_protein", "label": "Tinggi protein", "icon": "💪", "desc": "Protein tinggi"},
            {"key": "beverage", "label": "Minuman", "icon": "🥤", "desc": "Kategori minuman"},
        ]

    @staticmethod
    def _matches(item: dict[str, Any], key: str) -> bool:
        mapping = {
            "recommended": "is_recommended",
            "high_sodium": "is_high_sodium",
            "high_sugar": "is_high_sugar",
            "high_glycemic": "is_high_glycemic",
            "ultra_processed": "is_ultraproses",
            "fried": "is_gorengan",
            "raw": "is_bahan_mentah",
            "low_gi": "is_low_glycemic",
            "high_fiber": "is_high_fiber",
            "high_protein": "is_high_protein",
            "beverage": "is_minuman",
        }
        return True if key == "all" else bool(item.get(mapping.get(key, "")))

    def query(
        self,
        *,
        q: str = "",
        kategori: str = "",
        filter_key: str = "all",
        sort: str = "nama_asc",
        page: int = 1,
        per_page: int = 24,
    ) -> dict[str, Any]:
        self._ensure_loaded()
        items = list(self._items)
        terms = [term for term in q.casefold().split() if term]
        if terms:
            items = [item for item in items if all(term in item["search_text"] for term in terms)]
        if kategori:
            items = [item for item in items if item["kategori_utama"] == kategori]
        items = [item for item in items if self._matches(item, filter_key)]
        sorters = {
            "nama_asc": (lambda item: item["nama"].casefold(), False),
            "kalori_desc": (lambda item: item["kalori_kal"], True),
            "kalori_asc": (lambda item: item["kalori_kal"], False),
            "protein_desc": (lambda item: item["protein_g"], True),
            "gula_desc": (lambda item: item["gula_g"], True),
            "sodium_desc": (lambda item: item["sodium_mg"], True),
            "serat_desc": (lambda item: item["serat_g"], True),
            "gi_desc": (lambda item: item["glikemik_indeks"], True),
        }
        key_func, reverse = sorters.get(sort, sorters["nama_asc"])
        items.sort(key=key_func, reverse=reverse)
        total_filtered = len(items)
        per_page = max(1, min(int(per_page or 24), 60))
        total_pages = max(1, math.ceil(total_filtered / per_page))
        page = max(1, min(int(page or 1), total_pages))
        start = (page - 1) * per_page
        options = self.filter_options()
        return {
            "items": items[start : start + per_page],
            "total_items": len(self._items),
            "total_filtered": total_filtered,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "q": q,
            "kategori": kategori,
            "filter": filter_key,
            "sort": sort,
            "categories": sorted({item["kategori_utama"] for item in self._items if item["kategori_utama"]}),
            "filter_options": options,
            "counts_by_filter": {option["key"]: sum(1 for item in self._items if self._matches(item, option["key"])) for option in options},
            "active_filter_label": next((option["label"] for option in options if option["key"] == filter_key), "Semua"),
            "dataset_path": str(self.path) if self.path.is_file() else None,
            "thresholds": {"high_sodium": HIGH_SODIUM_MG, "high_sugar": HIGH_SUGAR_G, "high_gi": HIGH_GI_VALUE},
        }


_default_service: MenuDatasetService | None = None
_default_path: str | None = None


def get_menu_dataset_service() -> MenuDatasetService:
    global _default_service, _default_path
    path = os.getenv("FOOD_DATASET_PATH", "/app/data/reference/food/master_makanan_kategori_flag_mealplan.csv")
    if _default_service is None or _default_path != path:
        _default_service = MenuDatasetService(path)
        _default_path = path
    return _default_service
