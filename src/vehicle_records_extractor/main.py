"""PySide6 desktop UI for Vehicle Records Extractor."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut, QTransform
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSplitter,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget, QCheckBox, QProgressDialog,
)

from .db import Database
from .extraction import extract_field_suggestions, find_reference_matches, reference_suggestions
from .ocr import ARABIC_TESSERACT_ERROR, run_ocr
from .models import FIELD_LABELS_AR, FINAL_FIELDS, REQUIRED_FIELDS
from .services import export_excel, import_folder, import_reference_excel, load_preview, normalize_record, validate_record

APP_TITLE = "Vehicle Records Extractor"
STATUS_LABELS_AR = {
    "draft": "مسودة",
    "approved": "معتمد",
    "needs_review": "يحتاج مراجعة",
    "bad_image": "صورة رديئة",
    "duplicate": "مكرر",
}
STATUS_STYLES = {
    "draft": "background:#fff3cd;color:#664d03;border:1px solid #ffecb5;",
    "approved": "background:#d1e7dd;color:#0f5132;border:1px solid #badbcc;",
    "needs_review": "background:#cff4fc;color:#055160;border:1px solid #b6effb;",
    "bad_image": "background:#f8d7da;color:#842029;border:1px solid #f5c2c7;",
    "duplicate": "background:#e2e3e5;color:#41464b;border:1px solid #d3d6d8;",
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1300, 850)
        self.db = Database(Path.home() / ".vehicle_records_extractor" / "records.sqlite3")
        self.inputs: dict[str, QLineEdit] = {}
        self.field_info: dict[str, QLabel] = {}
        self.source_list = QListWidget()
        self.status_indicator = QLabel("مسودة")
        self.status_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_indicator.setMinimumHeight(34)
        self.status_indicator.setStyleSheet("border-radius:8px;padding:6px 12px;font-weight:bold;")
        self.preview = QLabel("معاينة الملف")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumWidth(520)
        self.preview.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_scroll.setWidget(self.preview)
        self.original_preview: QPixmap | None = None
        self.zoom_factor = 1.0
        self.rotation_degrees = 0
        self.fit_mode = "page"
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setCentralWidget(self.build_tabs())
        self.install_shortcuts()
        self.refresh_sources()

    def build_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.addTab(self.build_import_tab(), "استيراد المصادر")
        tabs.addTab(self.build_reference_tab(), "استيراد Excel مرجعي")
        tabs.addTab(self.build_review_tab(), "مراجعة السجلات")
        tabs.addTab(self.build_export_tab(), "تصدير Excel")
        return tabs

    def build_import_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel("استيراد مجلد يحتوي على صور وملفات PDF. لا يتم تعديل الملفات الأصلية.")
        batch = QLineEdit()
        batch.setPlaceholderText("رقم الدفعة مثل BATCH-001")
        button = QPushButton("اختيار مجلد واستيراد")
        button.clicked.connect(lambda: self.choose_folder(batch.text().strip() or "BATCH-001"))
        layout.addWidget(label)
        layout.addWidget(batch)
        layout.addWidget(button)
        layout.addStretch()
        return page

    def build_reference_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("استيراد ملف Excel مرجعي يحتوي حقولاً جزئية للمطابقة اليدوية."))
        button = QPushButton("اختيار ملف Excel")
        button.clicked.connect(self.choose_reference)
        layout.addWidget(button)
        layout.addStretch()
        return page

    def build_review_tab(self) -> QWidget:
        page = QWidget()
        root = QHBoxLayout(page)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        header = QHBoxLayout()
        header.addWidget(QLabel("المصادر المستوردة"))
        header.addWidget(self.status_indicator)
        left_layout.addLayout(header)
        self.source_list.currentTextChanged.connect(self.load_selected_source)
        left_layout.addWidget(self.source_list)
        nav_buttons = QHBoxLayout()
        prev_btn = QPushButton("السابق")
        prev_btn.clicked.connect(self.previous_source)
        next_btn = QPushButton("التالي")
        next_btn.clicked.connect(self.next_source)
        nav_buttons.addWidget(prev_btn)
        nav_buttons.addWidget(next_btn)
        left_layout.addLayout(nav_buttons)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        for field in FINAL_FIELDS:
            edit = QLineEdit()
            edit.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            edit.textChanged.connect(self.update_required_highlights)
            if field == "source_code":
                edit.setReadOnly(True)
                edit.setStyleSheet("background:#f3f4f6;color:#555;")
            self.inputs[field] = edit
            label_text = FIELD_LABELS_AR[field] + (" *" if field in REQUIRED_FIELDS else "")
            box = QWidget(); box_layout = QVBoxLayout(box); box_layout.setContentsMargins(0, 0, 0, 0)
            info = QLabel(""); info.setStyleSheet("color:#6b7280;font-size:10px;")
            self.field_info[field] = info
            box_layout.addWidget(edit); box_layout.addWidget(info)
            form.addRow(QLabel(label_text), box)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_widget)
        buttons = QHBoxLayout()
        self.save_draft_button = QPushButton("حفظ مسودة")
        self.save_draft_button.clicked.connect(lambda: self.save_record("draft"))
        self.approve_button = QPushButton("اعتماد")
        self.approve_button.clicked.connect(lambda: self.save_record("approved"))
        buttons.addWidget(self.save_draft_button)
        buttons.addWidget(self.approve_button)
        for text, status in [("يحتاج مراجعة", "needs_review"), ("صورة رديئة", "bad_image"), ("مكرر", "duplicate")]:
            btn = QPushButton(text)
            btn.clicked.connect(lambda _, s=status: self.save_record(s))
            buttons.addWidget(btn)
        ocr_buttons = QHBoxLayout()
        for text, handler in [("Run OCR for current source", self.run_ocr_current), ("Apply OCR suggestions", lambda: self.apply_suggestions("ocr")), ("Show raw OCR text", self.show_raw_ocr_text), ("Clear OCR suggestions for current source", self.clear_ocr_suggestions)]:
            btn = QPushButton(text); btn.clicked.connect(handler); ocr_buttons.addWidget(btn)
        ref_buttons = QHBoxLayout()
        for text, handler in [("Match with Reference Excel", self.match_reference_current), ("Apply Reference Match", lambda: self.apply_suggestions("reference_excel")), ("Show Reference Match Details", self.show_reference_details)]:
            btn = QPushButton(text); btn.clicked.connect(handler); ref_buttons.addWidget(btn)
        batch_buttons = QHBoxLayout()
        self.skip_approved = QCheckBox("Skip approved records"); self.skip_approved.setChecked(True)
        batch_btn = QPushButton("Process OCR for current batch"); batch_btn.clicked.connect(self.run_ocr_batch)
        one_btn = QPushButton("Process OCR for current source"); one_btn.clicked.connect(self.run_ocr_current)
        batch_buttons.addWidget(one_btn); batch_buttons.addWidget(batch_btn); batch_buttons.addWidget(self.skip_approved)
        left_layout.addWidget(scroll)
        left_layout.addLayout(ocr_buttons)
        left_layout.addLayout(ref_buttons)
        left_layout.addLayout(batch_buttons)
        left_layout.addLayout(buttons)
        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        tools = QHBoxLayout()
        for text, handler in [
            ("تكبير +", self.zoom_in), ("تصغير -", self.zoom_out), ("ملاءمة العرض", self.fit_to_width),
            ("ملاءمة الصفحة", self.fit_to_page), ("تدوير يسار", self.rotate_left), ("تدوير يمين", self.rotate_right),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(handler)
            tools.addWidget(btn)
        preview_layout.addLayout(tools)
        preview_layout.addWidget(self.preview_scroll)
        splitter.addWidget(left)
        splitter.addWidget(preview_panel)
        splitter.setSizes([720, 580])
        root.addWidget(splitter)
        return page

    def build_export_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("تصدير قاعدة البيانات المحلية إلى ملف Excel متعدد الأوراق."))
        button = QPushButton("تصدير إلى Excel")
        button.clicked.connect(self.choose_export)
        layout.addWidget(button)
        layout.addStretch()
        return page

    def install_shortcuts(self) -> None:
        QShortcut(QKeySequence.StandardKey.Save, self, activated=lambda: self.save_record("draft"))
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=lambda: self.save_record("approved"))
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=lambda: self.save_record("approved"))
        QShortcut(QKeySequence("Ctrl+Right"), self, activated=self.next_source)
        QShortcut(QKeySequence("Ctrl+Left"), self, activated=self.previous_source)

    def choose_folder(self, batch_no: str) -> None:
        folder = QFileDialog.getExistingDirectory(self, "اختيار مجلد")
        if folder:
            count = import_folder(self.db, Path(folder), batch_no)
            self.refresh_sources()
            QMessageBox.information(self, APP_TITLE, f"تم تسجيل {count} ملف/ملفات.")

    def choose_reference(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "اختيار Excel", filter="Excel (*.xlsx *.xls)")
        if path:
            count = import_reference_excel(self.db, Path(path))
            QMessageBox.information(self, APP_TITLE, f"تم استيراد {count} صف مرجعي.")

    def choose_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "حفظ Excel", "vehicle_records.xlsx", "Excel (*.xlsx)")
        if path:
            export_excel(self.db, Path(path))
            QMessageBox.information(self, APP_TITLE, "تم التصدير بنجاح.")

    def refresh_sources(self) -> None:
        current = self.source_list.currentItem().text() if self.source_list.currentItem() else ""
        self.source_list.clear()
        for row in self.db.list_sources():
            self.source_list.addItem(row["source_code"])
        matches = self.source_list.findItems(current, Qt.MatchFlag.MatchExactly) if current else []
        if matches:
            self.source_list.setCurrentItem(matches[0])
        elif self.source_list.count() and self.source_list.currentRow() < 0:
            self.source_list.setCurrentRow(0)

    def load_selected_source(self, source_code: str) -> None:
        if not source_code:
            return
        record = self.db.get_record(source_code)
        for field in FINAL_FIELDS:
            self.inputs[field].setText(str(record[field] if record and record[field] is not None else ""))
            self.inputs[field].setStyleSheet(self.field_style(field, False))
        self.update_status_indicator(self.inputs["review_status"].text() or "draft")
        source = next((row for row in self.db.list_sources() if row["source_code"] == source_code), None)
        if source:
            self.original_preview = load_preview(source["file_path"])
            self.zoom_factor = 1.0
            self.rotation_degrees = 0
            self.fit_mode = "page"
            if self.original_preview:
                self.update_preview()
            else:
                self.preview.clear()
                self.preview.setText("تعذر عرض المعاينة. ثبّت PyMuPDF لمعاينة PDF.")
        self.refresh_field_indicators()
        self.update_required_highlights()

    def current_source_code(self) -> str:
        return self.inputs.get("source_code", QLineEdit()).text().strip()

    def run_ocr_current(self) -> None:
        code = self.current_source_code()
        source = self.db.get_source(code) if code else None
        if not source: return
        result = run_ocr(source["file_path"])
        status = "failed" if result.error_message else "success"
        self.db.add_extraction_run(code, "tesseract ara+eng", result.raw_text, status, result.error_message, result.processed_image_path, result.confidence)
        if result.error_message:
            QMessageBox.warning(self, APP_TITLE, result.error_message or ARABIC_TESSERACT_ERROR)
            return
        suggestions = extract_field_suggestions(result.raw_text)
        self.db.replace_field_suggestions(code, suggestions, "ocr")
        self.refresh_field_indicators()
        QMessageBox.information(self, APP_TITLE, f"تم تشغيل OCR وحفظ {len(suggestions)} اقتراح/اقتراحات.")

    def run_ocr_batch(self) -> None:
        sources = self.db.list_sources(); total = len(sources)
        progress = QProgressDialog("Processing OCR...", "Cancel", 0, total, self); progress.setWindowModality(Qt.WindowModality.WindowModal)
        for i, source in enumerate(sources, 1):
            progress.setValue(i - 1); progress.setLabelText(f"{i}/{total}: {source['source_code']}"); QApplication.processEvents()
            if progress.wasCanceled(): break
            record = self.db.get_record(source["source_code"])
            if self.skip_approved.isChecked() and record and record["review_status"] == "approved": continue
            result = run_ocr(source["file_path"]); status = "failed" if result.error_message else "success"
            self.db.add_extraction_run(source["source_code"], "tesseract ara+eng", result.raw_text, status, result.error_message, result.processed_image_path, result.confidence)
            if not result.error_message:
                self.db.replace_field_suggestions(source["source_code"], extract_field_suggestions(result.raw_text), "ocr")
        progress.setValue(total); self.refresh_field_indicators(); QMessageBox.information(self, APP_TITLE, "اكتملت معالجة الدفعة وحُفظ التقدم بعد كل مصدر.")

    def show_raw_ocr_text(self) -> None:
        code = self.current_source_code()
        row = self.db.conn.execute("SELECT raw_text, error_message FROM extraction_runs WHERE source_code = ? ORDER BY id DESC LIMIT 1", (code,)).fetchone()
        dlg = QMessageBox(self); dlg.setWindowTitle("Raw OCR Text"); dlg.setText((row["raw_text"] or row["error_message"] or "لا يوجد نص OCR محفوظ.") if row else "لا يوجد نص OCR محفوظ."); dlg.exec()

    def clear_ocr_suggestions(self) -> None:
        code = self.current_source_code(); self.db.clear_field_suggestions(code, "ocr"); self.refresh_field_indicators(); QMessageBox.information(self, APP_TITLE, "تم حذف اقتراحات OCR للمصدر الحالي.")

    def match_reference_current(self) -> None:
        code = self.current_source_code(); keys = {f: self.inputs[f].text() for f in self.inputs}
        for sug in self.db.get_field_suggestions(code, "ocr"):
            keys.setdefault(sug["field_name"], sug["clean_value"] or "")
            if not keys.get(sug["field_name"]): keys[sug["field_name"]] = sug["clean_value"] or ""
        matches = find_reference_matches(self.db, code, keys)
        status = "multiple_reference_matches" if len(matches) > 1 else ("matched" if len(matches) == 1 else "no_match")
        self.db.replace_reference_matches(code, matches, status)
        if len(matches) == 1:
            self.db.replace_field_suggestions(code, reference_suggestions(matches[0]), "reference_excel")
        self.refresh_field_indicators(); QMessageBox.information(self, APP_TITLE, f"نتيجة المطابقة: {status} ({len(matches)} candidates)")

    def show_reference_details(self) -> None:
        code = self.current_source_code()
        rows = self.db.conn.execute("SELECT rm.*, rr.raw_json FROM reference_matches rm LEFT JOIN reference_rows rr ON rr.id = rm.reference_row_id WHERE rm.source_code = ? ORDER BY rm.match_score DESC", (code,)).fetchall()
        text = "\n\n".join(f"#{r['reference_row_id']} score={r['match_score']} by={r['matched_by']} status={r['status']}\n{r['raw_json'] or ''}" for r in rows) or "لا توجد مطابقات مرجعية."
        dlg = QMessageBox(self); dlg.setWindowTitle("Reference Match Details"); dlg.setText(text); dlg.exec()

    def apply_suggestions(self, source_type: str) -> None:
        code = self.current_source_code(); record_status = self.inputs.get("review_status", QLineEdit()).text()
        if record_status == "approved":
            ans = QMessageBox.question(self, APP_TITLE, "السجل معتمد. هل تريد تطبيق الاقتراحات؟", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ans != QMessageBox.StandardButton.Yes: return
        changed = 0
        for sug in self.db.get_field_suggestions(code, source_type):
            field = sug["field_name"]
            if field not in self.inputs: continue
            current = self.inputs[field].text().strip(); value = sug["clean_value"] or ""
            if current and current != value:
                ans = QMessageBox.question(self, APP_TITLE, f"{FIELD_LABELS_AR.get(field, field)} يحتوي قيمة. هل تريد الاستبدال؟", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if ans != QMessageBox.StandardButton.Yes: continue
            if value and (not current or current != value): self.inputs[field].setText(value); changed += 1
        self.refresh_field_indicators(); QMessageBox.information(self, APP_TITLE, f"تم تطبيق {changed} قيمة.")

    def refresh_field_indicators(self) -> None:
        code = self.current_source_code()
        by_field = {}
        for row in self.db.get_field_suggestions(code) if code else []:
            by_field.setdefault(row["field_name"], []).append(row)
        for field, label in self.field_info.items():
            rows = by_field.get(field, [])
            if rows:
                r = rows[-1]; conf = r["confidence"]
                label.setText(f"{r['source_type']}" + (f" • {conf:.0f}%" if conf is not None else ""))
                label.setStyleSheet("color:#dc2626;font-size:10px;" if conf is not None and conf < 60 else "color:#2563eb;font-size:10px;")
            elif self.inputs.get(field) and self.inputs[field].text().strip():
                label.setText("manual"); label.setStyleSheet("color:#6b7280;font-size:10px;")
            else:
                label.setText("")

    def update_status_indicator(self, status: str) -> None:
        display = STATUS_LABELS_AR.get(status, STATUS_LABELS_AR["draft"])
        self.status_indicator.setText(display)
        self.status_indicator.setStyleSheet(f"border-radius:8px;padding:6px 12px;font-weight:bold;{STATUS_STYLES.get(status, STATUS_STYLES['draft'])}")

    def field_style(self, field: str, has_issue: bool) -> str:
        if field == "source_code":
            return "background:#f3f4f6;color:#555;"
        return "background:#ffe0e0;" if has_issue else ""

    def collect_normalized_data(self, status: str) -> tuple[dict[str, str], dict[str, str]]:
        data = {field: self.inputs[field].text() for field in FINAL_FIELDS}
        data["review_status"] = status
        normalized = normalize_record(data)
        issues = validate_record(normalized, require_approval_fields=(status == "approved"))
        return normalized, issues

    def update_required_highlights(self) -> None:
        status = self.inputs.get("review_status").text() if "review_status" in self.inputs else "draft"
        normalized, issues = self.collect_normalized_data(status or "draft") if self.inputs else ({}, {})
        for field, edit in self.inputs.items():
            has_issue = field in REQUIRED_FIELDS and not normalized.get(field, "").strip()
            if field in issues and field not in REQUIRED_FIELDS:
                has_issue = True
            edit.setStyleSheet(self.field_style(field, has_issue))

    def save_record(self, status: str) -> None:
        if not self.inputs or not self.inputs.get("source_code", QLineEdit()).text():
            return
        normalized, issues = self.collect_normalized_data(status)
        missing_required = [field for field in REQUIRED_FIELDS if not normalized.get(field, "").strip()]
        if status == "approved" and missing_required:
            labels = "\n".join(f"- {FIELD_LABELS_AR[field]}" for field in missing_required)
            answer = QMessageBox.warning(
                self,
                APP_TITLE,
                "توجد حقول مطلوبة فارغة:\n" + labels + "\n\nهل تريد الاعتماد رغم ذلك؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.apply_normalized_values(normalized, issues)
                return
        self.apply_normalized_values(normalized, issues)
        self.db.upsert_record(normalized, status)
        self.update_status_indicator(status)
        QMessageBox.information(self, APP_TITLE, "تم حفظ السجل محلياً.")
        self.refresh_sources()

    def apply_normalized_values(self, normalized: dict[str, str], issues: dict[str, str]) -> None:
        for field, edit in self.inputs.items():
            edit.blockSignals(True)
            edit.setText(normalized.get(field, ""))
            edit.setStyleSheet(self.field_style(field, field in issues))
            edit.blockSignals(False)

    def previous_source(self) -> None:
        row = self.source_list.currentRow()
        if row > 0:
            self.source_list.setCurrentRow(row - 1)

    def next_source(self) -> None:
        row = self.source_list.currentRow()
        if 0 <= row < self.source_list.count() - 1:
            self.source_list.setCurrentRow(row + 1)

    def transformed_preview(self) -> QPixmap | None:
        if not self.original_preview:
            return None
        transform = QTransform().rotate(self.rotation_degrees)
        return self.original_preview.transformed(transform, Qt.TransformationMode.SmoothTransformation)

    def update_preview(self) -> None:
        pixmap = self.transformed_preview()
        if not pixmap:
            return
        viewport_size = self.preview_scroll.viewport().size()
        if self.fit_mode == "width" and pixmap.width():
            width = max(1, viewport_size.width() - 24)
            pixmap = pixmap.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
        elif self.fit_mode == "page":
            pixmap = pixmap.scaled(max(1, viewport_size.width() - 24), max(1, viewport_size.height() - 24), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        else:
            pixmap = pixmap.scaled(max(1, int(pixmap.width() * self.zoom_factor)), max(1, int(pixmap.height() * self.zoom_factor)), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.preview.setPixmap(pixmap)
        self.preview.resize(pixmap.size())

    def zoom_in(self) -> None:
        self.fit_mode = "manual"
        self.zoom_factor = min(self.zoom_factor * 1.25, 6.0)
        self.update_preview()

    def zoom_out(self) -> None:
        self.fit_mode = "manual"
        self.zoom_factor = max(self.zoom_factor / 1.25, 0.15)
        self.update_preview()

    def fit_to_width(self) -> None:
        self.fit_mode = "width"
        self.update_preview()

    def fit_to_page(self) -> None:
        self.fit_mode = "page"
        self.update_preview()

    def rotate_left(self) -> None:
        self.rotation_degrees = (self.rotation_degrees - 90) % 360
        self.update_preview()

    def rotate_right(self) -> None:
        self.rotation_degrees = (self.rotation_degrees + 90) % 360
        self.update_preview()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        if self.fit_mode in {"width", "page"}:
            self.update_preview()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
