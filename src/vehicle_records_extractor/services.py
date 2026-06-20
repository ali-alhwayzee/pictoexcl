"""Import, validation, normalization, preview, and Excel services."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
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


def _records_export_columns(db: Database) -> list[str]:
    """Return stable record export columns, including optional schema additions."""
    record_columns = {
        row["name"] for row in db.conn.execute("PRAGMA table_info(records)")
    }
    columns = [field for field in FINAL_FIELDS if field in record_columns]
    if "match_status" in record_columns and "match_status" not in columns:
        columns.append("match_status")
    return columns


def _records_with_status(records: pd.DataFrame, status: str) -> pd.DataFrame:
    if records.empty:
        return records.copy()
    return records[records["review_status"] == status].copy()


def _no_match_records(records: pd.DataFrame) -> pd.DataFrame:
    if records.empty:
        return records.copy()
    review_no_match = records["review_status"] == "no_match"
    if "match_status" in records.columns:
        match_no_match = records["match_status"] == "no_match"
        return records[review_no_match | match_no_match].copy()
    return records[review_no_match].copy()


def export_excel(db: Database, path: Path) -> None:
    sources = pd.read_sql_query("SELECT * FROM sources ORDER BY id", db.conn)
    record_columns = _records_export_columns(db)
    records = pd.read_sql_query(
        "SELECT {fields} FROM records ORDER BY id".format(fields=", ".join(record_columns)), db.conn
    )
    approved = _records_with_status(records, "approved")
    needs_review = _records_with_status(records, "needs_review")
    drafts = _records_with_status(records, "draft")
    bad_images = _records_with_status(records, "bad_image")
    duplicates = _records_with_status(records, "duplicate")
    no_match = _no_match_records(records)
    report = pd.DataFrame([
        {"metric": "total_sources", "value": len(sources)},
        {"metric": "total_records", "value": len(records)},
        {"metric": "approved", "value": len(approved)},
        {"metric": "draft", "value": len(drafts)},
        {"metric": "needs_review", "value": len(needs_review)},
        {"metric": "bad_image", "value": len(bad_images)},
        {"metric": "duplicate", "value": len(duplicates)},
        {"metric": "no_match", "value": len(no_match)},
        {"metric": "exported_at", "value": datetime.now(timezone.utc).isoformat(timespec="seconds")},
    ])
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        approved.to_excel(writer, sheet_name="Final_Data", index=False)
        records.to_excel(writer, sheet_name="All_Records", index=False)
        sources.to_excel(writer, sheet_name="Source_Index", index=False)
        needs_review.to_excel(writer, sheet_name="Needs_Review", index=False)
        drafts.to_excel(writer, sheet_name="Drafts", index=False)
        bad_images.to_excel(writer, sheet_name="Bad_Images", index=False)
        no_match.to_excel(writer, sheet_name="No_Match", index=False)
        duplicates.to_excel(writer, sheet_name="Duplicates", index=False)
        report.to_excel(writer, sheet_name="Processing_Report", index=False)
