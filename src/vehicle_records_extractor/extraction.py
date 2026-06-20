"""Rule-based field extraction and reference matching."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .models import FIELD_LABELS_AR
from .normalization import (
    normalize_arabic_text, normalize_chassis, normalize_date, normalize_digits,
    normalize_phone, normalize_reference_key, normalize_vehicle_no,
)

EXTRACTABLE_FIELDS = [
    "driver_name", "mother_name", "wife_name", "birth_date", "birth_place", "province",
    "district_alley_house", "address_landmark", "ration_card_no", "national_id",
    "identity_issuer", "registry_page", "vehicle_no", "ownership", "vehicle_type",
    "vehicle_color", "vehicle_model", "annual_owner_name", "chassis_no", "annual_no",
    "annual_expiry_date", "phone", "residence_address", "residence_card_no",
    "residence_card_issuer",
]

ALIASES = {
    "driver_name": ["اسم السائق", "الاسم", "اسم المواطن"],
    "mother_name": ["اسم الام", "اسم الأم", "الام", "الأم"],
    "wife_name": ["اسم الزوجة", "الزوجة"],
    "birth_date": ["تاريخ الولادة", "المواليد"],
    "birth_place": ["مكان الولادة", "محل الولادة"],
    "province": ["المحافظة"],
    "district_alley_house": ["المحلة", "الزقاق", "الدار"],
    "address_landmark": ["اقرب نقطة دالة", "أقرب نقطة دالة"],
    "ration_card_no": ["رقم البطاقة التموينية", "البطاقة التموينية"],
    "national_id": ["الرقم الوطني", "رقم البطاقة الوطنية"],
    "identity_issuer": ["جهة الاصدار", "جهة إصدار الهوية"],
    "registry_page": ["السجل", "الصحيفة"],
    "vehicle_no": ["رقم المركبة", "رقم السيارة"],
    "ownership": ["محافظة الملكية", "محافظة العودة", "الملكية"],
    "vehicle_type": ["نوع المركبة", "نوع السيارة"],
    "vehicle_color": ["لون المركبة", "اللون"],
    "vehicle_model": ["موديل المركبة", "الموديل"],
    "annual_owner_name": ["اسم مالك السنوية", "مالك السنوية"],
    "chassis_no": ["رقم الشاصي", "الشاصي", "vin"],
    "annual_no": ["رقم السنوية", "السنوية"],
    "annual_expiry_date": ["تاريخ انتهاء السنوية", "نفاذ السنوية"],
    "phone": ["الهاتف", "الموبايل", "رقم الهاتف"],
    "residence_address": ["عنوان السكن"],
    "residence_card_no": ["رقم بطاقة السكن"],
    "residence_card_issuer": ["جهة إصدار بطاقة السكن", "جهة اصدار بطاقة السكن"],
}


def clean_field_value(field: str, value: Any) -> str:
    text = normalize_digits(value).strip(" :-ـ\t\n")
    if field == "phone": return normalize_phone(text)
    if field == "chassis_no": return normalize_chassis(text)
    if field in {"birth_date", "annual_expiry_date"}: return normalize_date(text)
    if field == "vehicle_no": return normalize_vehicle_no(text)
    if field in {"national_id", "annual_no", "ration_card_no", "residence_card_no"}: return re.sub(r"\D+", "", normalize_digits(text))
    return normalize_arabic_text(text)


def extract_field_suggestions(raw_text: str) -> list[dict[str, Any]]:
    text = normalize_digits(raw_text or "")
    suggestions: dict[str, dict[str, Any]] = {}
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for field, labels in ALIASES.items():
        for label in labels + [FIELD_LABELS_AR.get(field, "")]:
            if not label: continue
            pattern = rf"{re.escape(label)}\s*[:：\-]?\s*([^\n]+)"
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                raw = match.group(1).strip()
                suggestions[field] = {"field_name": field, "raw_value": raw, "clean_value": clean_field_value(field, raw), "confidence": 72.0, "source_type": "ocr"}
                break
    regexes = {
        "phone": r"(?:\+?964|0)?7\d{9}",
        "national_id": r"\b\d{12}\b",
        "chassis_no": r"\b[A-HJ-NPR-Z0-9]{11,17}\b",
        "annual_no": r"\b\d{5,12}\b",
        "birth_date": r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        "annual_expiry_date": r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    }
    for field, pattern in regexes.items():
        if field not in suggestions:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                raw = m.group(0)
                suggestions[field] = {"field_name": field, "raw_value": raw, "clean_value": clean_field_value(field, raw), "confidence": 58.0, "source_type": "ocr"}
    return [s for s in suggestions.values() if s.get("clean_value")]


def _score(keys: dict[str, str], row: dict[str, Any]) -> tuple[int, list[str]]:
    weights = {"vehicle_no": 45, "ownership": 20, "driver_name": 20, "mother_name": 20, "vehicle_type": 15}
    score = 0; matched = []
    for k, w in weights.items():
        a = normalize_vehicle_no(keys.get(k)) if k == "vehicle_no" else normalize_reference_key(keys.get(k))
        b = normalize_vehicle_no(row.get(k)) if k == "vehicle_no" else normalize_reference_key(row.get(k))
        if a and b and a == b:
            score += w; matched.append(k)
    return score, matched


def find_reference_matches(db: Any, source_code: str, keys: dict[str, str]) -> list[dict[str, Any]]:
    rows = db.conn.execute("SELECT * FROM reference_rows ORDER BY id").fetchall()
    candidates = []
    for row in rows:
        data = dict(row)
        score, matched = _score(keys, data)
        if score >= 40 and ("vehicle_no" not in matched or len(matched) > 1):
            candidates.append({"reference_row_id": data["id"], "match_score": score, "matched_by": "+".join(matched), "row": data})
    candidates.sort(key=lambda item: item["match_score"], reverse=True)
    return candidates[:10]


def reference_suggestions(match: dict[str, Any]) -> list[dict[str, Any]]:
    row = match.get("row", {})
    out = []
    for field in ("driver_name", "mother_name", "vehicle_no", "ownership", "vehicle_type"):
        value = row.get(field, "")
        if value:
            out.append({"field_name": field, "raw_value": value, "clean_value": clean_field_value(field, value), "confidence": float(match.get("match_score", 0)), "source_type": "reference_excel"})
    out.append({"field_name": "match_source", "raw_value": "reference_excel", "clean_value": "reference_excel", "confidence": float(match.get("match_score", 0)), "source_type": "reference_excel"})
    return out
