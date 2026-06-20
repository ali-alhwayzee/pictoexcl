"""PySide6 desktop UI for Vehicle Records Extractor."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut, QTransform
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSplitter,
    QTabWidget, QVBoxLayout, QWidget,
)

from .db import Database
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
            form.addRow(QLabel(label_text), edit)
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
        left_layout.addWidget(scroll)
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
        self.update_required_highlights()

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
