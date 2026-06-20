# Vehicle Records Extractor

A local offline desktop application for extracting, registering, reviewing, and exporting Arabic vehicle/person records from image and PDF sources into Excel.

## Features

- Desktop app named **Vehicle Records Extractor** built with PySide6.
- Local SQLite database stored at `~/.vehicle_records_extractor/records.sqlite3`.
- Imports folders containing images and PDFs without modifying originals.
- Registers every source with:
  - `source_code` such as `SRC-000001`
  - original filename, path, type, SHA256 hash, batch number, and status
- Imports reference Excel files with partial fields such as driver name, mother name, vehicle number, ownership/return province, and vehicle type.
- Arabic RTL-friendly review UI with source list, visible status indicator, editable form ordered like the Arabic document, and preview panel.
- Review actions: Save Draft, Approve, Needs Review, Bad Image, Duplicate, with Previous/Next navigation between sources.
- Validation and normalization:
  - highlights empty required fields
  - flags phone numbers that are non-numeric or shorter than 10 digits
  - strips spaces and uppercases chassis numbers
  - normalizes common date formats when possible
- Audit trail table records each record update.
- Excel export with sheets: `Final_Data`, `All_Records`, `Source_Index`, `Needs_Review`, `Drafts`, `Bad_Images`, `No_Match`, `Duplicates`, and `Processing_Report`.
- Tesseract OCR can be installed later via the optional `ocr` extra; the MVP prepares local processing without requiring cloud services.

## Requirements

- Python 3.11 or newer
- Linux, Windows, or macOS with Qt/PySide6 support

## Install

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e .
```

Optional PDF preview and OCR extras:

```bash
pip install -e '.[pdf,ocr]'
```

> OCR remains local. If using Tesseract, install the Tesseract binary and Arabic language data through your operating system package manager.

## Run

```bash
vehicle-records-extractor
```

Or run the module directly:

```bash
python -m vehicle_records_extractor.main
```

## Workflow

1. Open **استيراد المصادر** and choose a folder of images/PDFs. Files are hashed and registered in SQLite; originals are never edited.
2. Optionally open **استيراد Excel مرجعي** and import a spreadsheet with partial matching fields.
3. Open **مراجعة السجلات**, select a source, review the preview, edit Arabic fields in document order, and choose a review action.
4. Use **السابق** / **التالي** to move between sources while reviewing.
5. Use the preview tools to zoom in, zoom out, fit to width, fit to page, rotate left, or rotate right. Rotation changes only the on-screen preview and never modifies the original source file.
6. Watch the visible status indicator for the selected source: Draft, Approved, Needs Review, Bad Image, or Duplicate.
7. Empty required fields are highlighted: driver name, mother name, vehicle number, vehicle type, chassis number, annual number, and phone. Approving with missing required fields shows a confirmation warning and can proceed only if confirmed.
8. Open **تصدير Excel** and save a multi-sheet workbook for downstream review.

## Review shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+S` | Save Draft |
| `Ctrl+Enter` | Approve |
| `Ctrl+Right` | Next source |
| `Ctrl+Left` | Previous source |

## Development checks

```bash
python -m compileall src
```
