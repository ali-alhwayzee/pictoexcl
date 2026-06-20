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

## Phase 2: Local OCR, Extraction Suggestions, and Reference Matching

Phase 2 remains fully local/offline:

- OCR uses local Tesseract through `pytesseract` with language `ara+eng`.
- Images/PDFs are read from disk only; no cloud APIs are used and no data is uploaded.
- Original image/PDF files are never modified. OCR preprocessing writes temporary processed copies under the operating system temp directory.
- OCR and reference suggestions are stored separately from reviewed records and do **not** overwrite approved or manually entered values automatically.

### Install Tesseract on Windows

1. Install the Python OCR extras:

   ```powershell
   pip install -e ".[ocr,pdf]"
   ```

2. Install Tesseract for Windows, for example from the UB Mannheim Windows builds.
3. During setup, select the Arabic language data if offered.
4. Add the Tesseract install directory to `PATH`, commonly:

   ```text
   C:\Program Files\Tesseract-OCR
   ```

5. Open a new terminal and verify:

   ```powershell
   tesseract --version
   tesseract --list-langs
   ```

### Install Arabic language data

If Arabic is not listed by `tesseract --list-langs`, install `ara.traineddata` into Tesseract's `tessdata` directory. On Windows this is commonly:

```text
C:\Program Files\Tesseract-OCR\tessdata\ara.traineddata
```

The app will show this Arabic error if Tesseract or Arabic OCR support is unavailable:

```text
محرك OCR غير مثبت. يرجى تثبيت Tesseract وإضافة اللغة العربية.
```

### Test OCR on 10 images

1. Import a folder containing 10 sample images or PDFs.
2. Open **مراجعة السجلات**.
3. Select the first source and click **Run OCR for current source**.
4. Click **Show raw OCR text** and confirm text was saved.
5. Click **Apply OCR suggestions** and review the filled empty fields.
6. Use **Process OCR for current batch** with **Skip approved records** checked to process the remaining imported sources.
7. Watch the progress dialog; if OCR fails for one source, processing continues and the failure is saved in the OCR run history.

### Recommended Phase 2 workflow

1. Import 10 images.
2. Run OCR for one source.
3. Check raw OCR text.
4. Apply suggestions.
5. Import reference Excel.
6. Run reference matching.
7. Review manually.
8. Approve.
9. Export Excel.

### Phase 2 export sheets

The Excel export keeps the original sheets and adds:

- `OCR_Raw_Text`
- `Extracted_Values`
- `Reference_Matches`
- `Audit_Trail`

`Processing_Report` now also includes OCR success/failure counts and reference matching counts.
