"""Import, validation, normalization, preview, and Excel services."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image, ImageOps
from PySide6.QtGui import QImage, QPixmap

from .db import Database
from .models import FINAL_FIELDS, REQUIRED_FIELDS, SUPPORTED_EXTENSIONS

REFERENCE_COLUMN_ALIASES = {
    "driver_name": ["driver name", "اسم السائق", "السائق", "name"],
    "mother_name": ["mother name", "اسم الام", "اسم الأم", "الام", "الأم"],
    "vehicle_no": ["vehicle number", "vehicle no", "رقم المركبة", "رقم السيارة"],
    "ownership": ["ownership", "return province", "محافظة الملكية", "محافظة العودة"],
    "vehicle_type": ["vehicle type", "نوع المركبة", "نوع السيارة"],
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def import_folder(db: Database, folder: Path, batch_no: str) -> int:
    count = 0
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            db.add_source(path.name, str(path.resolve()), path.suffix.lower().lstrip("."), sha256_file(path), batch_no)
            count += 1
    return count


def normalize_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def import_reference_excel(db: Database, path: Path) -> int:
    frame = pd.read_excel(path).fillna("")
    normalized_columns = {normalize_key(col): col for col in frame.columns}
    alias_to_column: dict[str, str] = {}
    for field, aliases in REFERENCE_COLUMN_ALIASES.items():
        for alias in aliases:
            if normalize_key(alias) in normalized_columns:
                alias_to_column[field] = normalized_columns[normalize_key(alias)]
                break
    count = 0
    for _, source_row in frame.iterrows():
        row = {field: str(source_row.get(column, "")).strip() for field, column in alias_to_column.items()}
        if any(row.values()):
            db.add_reference(row)
            count += 1
    return count


def normalize_date(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text


def normalize_record(data: dict[str, str]) -> dict[str, str]:
    normalized = {field: str(data.get(field, "") or "").strip() for field in FINAL_FIELDS}
    normalized["chassis_no"] = normalized["chassis_no"].replace(" ", "").upper()
    normalized["birth_date"] = normalize_date(normalized["birth_date"])
    normalized["annual_expiry_date"] = normalize_date(normalized["annual_expiry_date"])
    return normalized


def validate_record(data: dict[str, str]) -> dict[str, str]:
    issues: dict[str, str] = {}
    for field in REQUIRED_FIELDS:
        if not data.get(field, "").strip():
            issues[field] = "حقل مطلوب"
    phone = data.get("phone", "").strip()
    if phone and (not phone.isnumeric() or len(phone) < 7):
        issues["phone"] = "رقم الهاتف يجب أن يكون رقمياً وطوله مناسب"
    return issues


def load_preview(path: str, max_size: tuple[int, int] = (900, 900)) -> QPixmap | None:
    file_path = Path(path)
    if file_path.suffix.lower() == ".pdf":
        try:
            import fitz  # type: ignore
            doc = fitz.open(str(file_path))
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            return QPixmap.fromImage(image.copy())
        except Exception:
            return None
    try:
        image = Image.open(file_path)
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail(max_size)
        data = image.tobytes("raw", "RGB")
        qimage = QImage(data, image.width, image.height, image.width * 3, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(qimage.copy())
    except Exception:
        return None


def export_excel(db: Database, path: Path) -> None:
    sources = pd.read_sql_query("SELECT * FROM sources ORDER BY id", db.conn)
    records = pd.read_sql_query("SELECT {fields} FROM records ORDER BY id".format(fields=", ".join(FINAL_FIELDS)), db.conn)
    needs_review = records[records["review_status"].isin(["needs_review", "bad_image", "draft"])] if not records.empty else records
    no_match = records[records["match_source"].isin(["", "none", "no_match"])] if not records.empty else records
    duplicates = records[records["review_status"] == "duplicate"] if not records.empty else records
    report = pd.DataFrame([
        {"metric": "sources", "value": len(sources)},
        {"metric": "final_records", "value": len(records)},
        {"metric": "needs_review", "value": len(needs_review)},
        {"metric": "duplicates", "value": len(duplicates)},
    ])
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        records.to_excel(writer, sheet_name="Final_Data", index=False)
        sources.to_excel(writer, sheet_name="Source_Index", index=False)
        needs_review.to_excel(writer, sheet_name="Needs_Review", index=False)
        no_match.to_excel(writer, sheet_name="No_Match", index=False)
        duplicates.to_excel(writer, sheet_name="Duplicates", index=False)
        report.to_excel(writer, sheet_name="Processing_Report", index=False)
