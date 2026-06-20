"""PySide6 desktop UI for Vehicle Records Extractor."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSplitter,
    QTabWidget, QVBoxLayout, QWidget,
)

from .db import Database
from .models import FIELD_LABELS_AR, FINAL_FIELDS
from .services import export_excel, import_folder, import_reference_excel, load_preview, normalize_record, validate_record

APP_TITLE = "Vehicle Records Extractor"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1300, 850)
        self.db = Database(Path.home() / ".vehicle_records_extractor" / "records.sqlite3")
        self.inputs: dict[str, QLineEdit] = {}
        self.source_list = QListWidget()
        self.preview = QLabel("معاينة الملف")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumWidth(520)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setCentralWidget(self.build_tabs())
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
        left_layout.addWidget(QLabel("المصادر المستوردة"))
        self.source_list.currentTextChanged.connect(self.load_selected_source)
        left_layout.addWidget(self.source_list)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        for field in FINAL_FIELDS:
            edit = QLineEdit()
            edit.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            if field == "source_code":
                edit.setReadOnly(True)
            self.inputs[field] = edit
            form.addRow(QLabel(FIELD_LABELS_AR[field]), edit)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_widget)
        buttons = QHBoxLayout()
        for text, status in [
            ("حفظ مسودة", "draft"), ("اعتماد", "approved"), ("يحتاج مراجعة", "needs_review"),
            ("صورة رديئة", "bad_image"), ("مكرر", "duplicate"),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(lambda _, s=status: self.save_record(s))
            buttons.addWidget(btn)
        left_layout.addWidget(scroll)
        left_layout.addLayout(buttons)
        splitter.addWidget(left)
        splitter.addWidget(self.preview)
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
        self.source_list.clear()
        for row in self.db.list_sources():
            self.source_list.addItem(row["source_code"])

    def load_selected_source(self, source_code: str) -> None:
        if not source_code:
            return
        record = self.db.get_record(source_code)
        for field in FINAL_FIELDS:
            self.inputs[field].setText(str(record[field] if record and record[field] is not None else ""))
            self.inputs[field].setStyleSheet("")
        source = next((row for row in self.db.list_sources() if row["source_code"] == source_code), None)
        if source:
            pixmap = load_preview(source["file_path"])
            self.preview.setPixmap(pixmap if pixmap else self.preview.pixmap())
            if not pixmap:
                self.preview.setText("تعذر عرض المعاينة. ثبّت PyMuPDF لمعاينة PDF.")

    def save_record(self, status: str) -> None:
        data = {field: self.inputs[field].text() for field in FINAL_FIELDS}
        data["review_status"] = status
        normalized = normalize_record(data)
        issues = validate_record(normalized)
        for field, edit in self.inputs.items():
            edit.setText(normalized.get(field, ""))
            edit.setStyleSheet("background:#ffe0e0;" if field in issues else "")
        if issues and status == "approved":
            QMessageBox.warning(self, APP_TITLE, "لا يمكن الاعتماد قبل تصحيح الحقول المطلوبة والمميزة.")
            return
        self.db.upsert_record(normalized, status)
        QMessageBox.information(self, APP_TITLE, "تم حفظ السجل محلياً.")
        self.refresh_sources()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
