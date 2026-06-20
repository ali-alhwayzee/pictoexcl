"""Local/offline OCR utilities using Tesseract via pytesseract."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

from PIL import Image, ImageFilter, ImageOps

ARABIC_TESSERACT_ERROR = "محرك OCR غير مثبت. يرجى تثبيت Tesseract وإضافة اللغة العربية."


@dataclass
class OCRResult:
    raw_text: str = ""
    processed_image_path: str = ""
    confidence: float | None = None
    error_message: str = ""


def _load_first_page(path: Path) -> Image.Image:
    if path.suffix.lower() == ".pdf":
        try:
            import fitz  # type: ignore
        except Exception as exc:
            raise RuntimeError("PyMuPDF غير مثبت لدعم OCR لملفات PDF.") from exc
        doc = fitz.open(str(path))
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return Image.open(path)


def preprocess_image(path: str | Path) -> tuple[Image.Image, str]:
    image = ImageOps.exif_transpose(_load_first_page(Path(path))).convert("L")
    if min(image.size) < 1200:
        scale = max(2, int(1200 / max(1, min(image.size))))
        image = image.resize((image.width * scale, image.height * scale), Image.Resampling.LANCZOS)
    image = image.filter(ImageFilter.MedianFilter(size=3))
    image = image.point(lambda p: 255 if p > 165 else 0)
    tmp_dir = Path(tempfile.gettempdir()) / "vehicle_records_extractor_ocr"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out = tmp_dir / f"processed_{Path(path).stem}.png"
    image.save(out)
    return image, str(out)


def run_ocr(path: str | Path, lang: str = "ara+eng") -> OCRResult:
    try:
        import pytesseract  # type: ignore
        from pytesseract import TesseractNotFoundError  # type: ignore
    except Exception:
        return OCRResult(error_message=ARABIC_TESSERACT_ERROR)
    try:
        image, processed_path = preprocess_image(path)
        data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
        text = pytesseract.image_to_string(image, lang=lang)
        confs = [float(c) for c in data.get("conf", []) if str(c).replace(".", "", 1).lstrip("-").isdigit() and float(c) >= 0]
        confidence = sum(confs) / len(confs) if confs else None
        return OCRResult(raw_text=text, processed_image_path=processed_path, confidence=confidence)
    except TesseractNotFoundError:
        return OCRResult(error_message=ARABIC_TESSERACT_ERROR)
    except Exception as exc:
        return OCRResult(error_message=str(exc))
