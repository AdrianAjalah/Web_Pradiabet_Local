"""Deterministic intent extraction for safe chatbot actions."""
from __future__ import annotations

import re
from typing import Any

from app.user.diet_service import normalize_diet_id

_NUMBER_WORDS = {
    "satu": 1,
    "sebuah": 1,
    "dua": 2,
    "tiga": 3,
    "empat": 4,
    "lima": 5,
    "enam": 6,
    "tujuh": 7,
    "delapan": 8,
    "sembilan": 9,
    "sepuluh": 10,
}


def _clean(text: str) -> str:
    text = str(text or "").lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _quantity(value: str | None) -> int:
    if not value:
        return 1
    value = value.strip().lower()
    if value.isdigit():
        return max(1, min(int(value), 20))
    return _NUMBER_WORDS.get(value, 1)


def _strip_food_command(text: str) -> str:
    text = re.sub(
        r"\b(?:tolong\s+)?(?:catat(?:kan|\s+kan)?|tambah(?:kan|\s+kan)?|masuk(?:kan|\s+kan)|masukin)\b",
        "",
        text,
        count=1,
    )
    text = re.sub(
        r"\b(?:ke|di|pada)\s+(?:progress\s+)?(?:tracker|tracking)(?:\s+saya)?(?:\s+hari\s+ini)?\b",
        "",
        text,
    )
    text = re.sub(r"\buntuk\s+hari\s+ini\b", "", text)
    text = re.sub(r"\bhari\s+ini\b", "", text)
    return re.sub(r"\s+", " ", text).strip(" ,.+")


def _parse_food_part(part: str) -> dict[str, Any] | None:
    part = part.strip(" ,.+")
    if not part:
        return None
    number_pattern = r"(?:\d+|" + "|".join(_NUMBER_WORDS) + r")"

    prefix = re.match(
        rf"^(?P<qty>{number_pattern})\s*(?:x|kali|porsi)?\s+(?P<name>.+)$",
        part,
    )
    if prefix and ("porsi" in part or "kali" in part or re.match(r"^\d+\s+", part)):
        name = prefix.group("name").strip()
        qty = _quantity(prefix.group("qty"))
    else:
        suffix = re.match(
            rf"^(?P<name>.+?)\s+(?P<qty>{number_pattern})\s*(?:x|kali|porsi)?$",
            part,
        )
        if suffix:
            name = suffix.group("name").strip()
            qty = _quantity(suffix.group("qty"))
        else:
            name = part
            qty = 1

    name = re.sub(r"\b(?:sebanyak|masing masing)\b", "", name).strip()
    if not name:
        return None
    return {"query": name, "quantity": qty}


def _parse_food_items(text: str) -> list[dict[str, Any]]:
    body = _strip_food_command(text)
    parts = re.split(r"\s*(?:,|\+|\bdan\b|\bserta\b)\s*", body)
    result: list[dict[str, Any]] = []
    for part in parts:
        item = _parse_food_part(part)
        if item:
            result.append(item)
    return result


def plan_chat_action(question: str) -> dict[str, Any] | None:
    q = _clean(question)
    if not q:
        return None

    if re.search(r"\b(?:nonaktifkan|matikan|berhenti(?:kan)?|hapus)\b.*\bdiet\b", q):
        return {"type": "deactivate_diet"}

    if re.search(r"\b(?:ganti|ubah|aktifkan|pakai)\b.*\bdiet\b", q):
        target = None
        aliases = [
            "low carbohydrate",
            "low carb",
            "rendah karbohidrat",
            "rendah karbo",
            "mediterranean",
            "mediterania",
        ]
        for alias in aliases:
            if alias in q:
                target = "rendah_karbo" if alias in {"low carbohydrate", "low carb", "rendah karbohidrat", "rendah karbo"} else "mediterania"
                break
        if target:
            return {"type": "change_diet", "diet_id": target}

    if (
        (
            re.search(r"\b(?:generate|buat|acak|ganti|perbarui)\s+ulang\b", q)
            and re.search(r"\b(?:meal\s*plan|menu|rencana makan)\b", q)
        )
        or re.search(r"\bregenerate\b.*\b(?:meal\s*plan|menu)\b", q)
        or (
            re.search(r"\b(?:ganti|ubah|perbarui|acak)\b", q)
            and re.search(r"\b(?:meal\s*plan|menu|rencana\s+makan)\b", q)
        )
    ):
        return {"type": "regenerate_meal_plan"}

    has_food_command = re.search(
        r"\b(?:catat(?:kan)?|tambahkan|tambah|masukkan|masukin)\b", q
    )
    if has_food_command:
        items = _parse_food_items(q)
        if items:
            return {"type": "add_food", "items": items}

    return None
