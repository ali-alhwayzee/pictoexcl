"""Normalization helpers for OCR and reference matching."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

_DIGIT_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_ALEF_RE = re.compile("[إأآٱ]")


def normalize_digits(value: Any) -> str:
    return str(value or "").translate(_DIGIT_MAP)


def normalize_arabic_text(value: Any) -> str:
    text = normalize_digits(value)
    text = _ALEF_RE.sub("ا", text)
    text = text.replace("ى", "ي").replace("ة", "ه")
    text = re.sub(r"[\u064b-\u065f\u0670]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_phone(value: Any) -> str:
    digits = re.sub(r"\D+", "", normalize_digits(value))
    if digits.startswith("964") and len(digits) >= 13:
        digits = "0" + digits[3:]
    return digits


def normalize_chassis(value: Any) -> str:
    return re.sub(r"\s+", "", normalize_digits(value)).upper()


def normalize_date(value: Any) -> str:
    text = normalize_digits(value).strip()
    if not text:
        return ""
    text = re.sub(r"[.\\]", "/", text)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    match = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", text)
    if match:
        d, m, y = match.groups()
        if len(y) == 2:
            y = "20" + y if int(y) < 40 else "19" + y
        try:
            return datetime(int(y), int(m), int(d)).date().isoformat()
        except ValueError:
            return text
    return text


def normalize_vehicle_no(value: Any) -> str:
    return re.sub(r"\s+", "", normalize_arabic_text(value)).upper()


def normalize_reference_key(value: Any) -> str:
    return re.sub(r"[^\w\u0600-\u06ff]+", "", normalize_arabic_text(value).lower())
