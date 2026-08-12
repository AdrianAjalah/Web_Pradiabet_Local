"""In-memory structured nutrition database built from the local food CSV."""
from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any, Iterable

from app.services.food_service import load_tracker_foods

_NUMERIC_COLUMNS = (
    "gram_porsi", "kalori_kkal", "karbohidrat_g", "protein_g", "lemak_g",
    "serat_g", "gula_g", "natrium_mg", "indeks_glikemik", "indeks_glikemik_estimasi",
)


class NutritionDatabase:
    """Small SQLite index for deterministic food lookups and numeric filters."""

    def __init__(self, foods: Iterable[dict[str, Any]] | None = None) -> None:
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(":memory:", check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._create_schema()
        self.reload(list(foods) if foods is not None else load_tracker_foods())

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE foods (
                id TEXT PRIMARY KEY,
                kode TEXT,
                nama TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                kelompok_makanan TEXT,
                jenis_bahan_utama TEXT,
                tingkat_proses TEXT,
                slot_meal_plan TEXT,
                gram_porsi REAL,
                kalori_kkal REAL,
                karbohidrat_g REAL,
                protein_g REAL,
                lemak_g REAL,
                serat_g REAL,
                gula_g REAL,
                natrium_mg REAL,
                indeks_glikemik REAL,
                indeks_glikemik_estimasi REAL,
                is_recommended INTEGER NOT NULL DEFAULT 0,
                is_fruit INTEGER NOT NULL DEFAULT 0,
                not_recommended_reasons TEXT NOT NULL DEFAULT '[]',
                payload TEXT NOT NULL
            );
            CREATE INDEX foods_normalized_name_idx ON foods(normalized_name);
            CREATE INDEX foods_calories_idx ON foods(kalori_kkal);
            CREATE INDEX foods_protein_idx ON foods(protein_g);
            CREATE INDEX foods_sugar_idx ON foods(gula_g);
            CREATE INDEX foods_fiber_idx ON foods(serat_g);
            """
        )

    def reload(self, foods: Iterable[dict[str, Any]]) -> None:
        rows = []
        for index, food in enumerate(foods):
            payload = dict(food)
            food_id = str(food.get("id") or food.get("kode") or index)
            rows.append((
                food_id,
                str(food.get("kode") or ""),
                str(food.get("nama") or "").strip(),
                self.normalize(str(food.get("nama") or "")),
                str(food.get("kelompok_makanan") or ""),
                str(food.get("jenis_bahan_utama") or ""),
                str(food.get("tingkat_proses") or ""),
                str(food.get("slot_meal_plan") or ""),
                *[float(food.get(column) or 0) for column in _NUMERIC_COLUMNS],
                1 if food.get("is_recommended") else 0,
                1 if str(food.get("kelompok_makanan") or "").casefold() == "buah" else 0,
                json.dumps(food.get("not_recommended_reasons") or [], ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False),
            ))
        with self._lock:
            self._connection.execute("DELETE FROM foods")
            self._connection.executemany(
                """
                INSERT INTO foods (
                    id, kode, nama, normalized_name, kelompok_makanan, jenis_bahan_utama,
                    tingkat_proses, slot_meal_plan, gram_porsi, kalori_kkal,
                    karbohidrat_g, protein_g, lemak_g, serat_g, gula_g, natrium_mg,
                    indeks_glikemik, indeks_glikemik_estimasi, is_recommended, is_fruit,
                    not_recommended_reasons, payload
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                rows,
            )
            self._connection.commit()

    @staticmethod
    def normalize(value: str) -> str:
        import re
        text = str(value or "").casefold()
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def all_foods(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute("SELECT payload FROM foods").fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def query(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(sql, parameters).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            if "payload" in item:
                payload = json.loads(item.pop("payload"))
                payload.update(item)
                item = payload
            result.append(item)
        return result
