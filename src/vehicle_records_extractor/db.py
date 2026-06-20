"""SQLite persistence layer for the local offline application."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import FINAL_FIELDS


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.migrate()

    def migrate(self) -> None:
        field_columns = ",\n".join(
            f"{field} TEXT" for field in FINAL_FIELDS if field != "source_code"
        )
        self.conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_code TEXT UNIQUE NOT NULL,
                original_filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                batch_no TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'imported',
                imported_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sources_hash ON sources(file_hash);
            CREATE INDEX IF NOT EXISTS idx_sources_status ON sources(status);

            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_code TEXT UNIQUE NOT NULL REFERENCES sources(source_code) ON DELETE CASCADE,
                {field_columns},
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reference_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                driver_name TEXT,
                mother_name TEXT,
                vehicle_no TEXT,
                ownership TEXT,
                vehicle_type TEXT,
                raw_json TEXT NOT NULL,
                imported_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_trail (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id INTEGER REFERENCES records(id) ON DELETE SET NULL,
                source_code TEXT NOT NULL,
                action TEXT NOT NULL,
                changed_fields TEXT NOT NULL,
                old_values TEXT,
                new_values TEXT,
                changed_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def next_source_code(self) -> str:
        row = self.conn.execute(
            "SELECT source_code FROM sources ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return "SRC-000001"
        return f"SRC-{int(row['source_code'].split('-')[-1]) + 1:06d}"

    def add_source(self, original_filename: str, file_path: str, file_type: str,
                   file_hash: str, batch_no: str, status: str = "imported") -> str:
        existing = self.conn.execute(
            "SELECT source_code FROM sources WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        if existing:
            return existing["source_code"]
        code = self.next_source_code()
        now = utc_now()
        self.conn.execute(
            """INSERT INTO sources
            (source_code, original_filename, file_path, file_type, file_hash, batch_no, status, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, original_filename, file_path, file_type, file_hash, batch_no, status, now),
        )
        self.upsert_record({"source_code": code, "review_status": "draft", "match_source": "none"}, "create")
        self.conn.commit()
        return code

    def upsert_record(self, data: dict[str, Any], action: str = "save") -> None:
        code = str(data["source_code"])
        existing = self.conn.execute("SELECT * FROM records WHERE source_code = ?", (code,)).fetchone()
        now = utc_now()
        payload = {field: str(data.get(field, "") or "") for field in FINAL_FIELDS}
        if existing:
            old = {field: existing[field] or "" for field in FINAL_FIELDS if field != "source_code"}
            changed = {k: v for k, v in payload.items() if k != "source_code" and old.get(k, "") != v}
            if changed:
                assignments = ", ".join(f"{k} = ?" for k in changed) + ", updated_at = ?"
                self.conn.execute(
                    f"UPDATE records SET {assignments} WHERE source_code = ?",
                    (*changed.values(), now, code),
                )
                record_id = existing["id"]
                self.add_audit(record_id, code, action, changed, old, payload)
        else:
            columns = ", ".join(FINAL_FIELDS + ["created_at", "updated_at"])
            placeholders = ", ".join("?" for _ in FINAL_FIELDS + ["created_at", "updated_at"])
            self.conn.execute(
                f"INSERT INTO records ({columns}) VALUES ({placeholders})",
                (*[payload[f] for f in FINAL_FIELDS], now, now),
            )
            record_id = self.conn.execute("SELECT id FROM records WHERE source_code = ?", (code,)).fetchone()["id"]
            self.add_audit(record_id, code, action, payload, {}, payload)
        if payload.get("review_status"):
            self.conn.execute("UPDATE sources SET status = ? WHERE source_code = ?", (payload["review_status"], code))
        self.conn.commit()

    def add_audit(self, record_id: int, code: str, action: str, changed: dict[str, Any],
                  old: dict[str, Any], new: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT INTO audit_trail
            (record_id, source_code, action, changed_fields, old_values, new_values, changed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (record_id, code, action, json.dumps(list(changed), ensure_ascii=False),
             json.dumps(old, ensure_ascii=False), json.dumps(new, ensure_ascii=False), utc_now()),
        )

    def list_sources(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM sources ORDER BY id"))

    def get_record(self, source_code: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM records WHERE source_code = ?", (source_code,)).fetchone()

    def add_reference(self, row: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT INTO reference_rows
            (driver_name, mother_name, vehicle_no, ownership, vehicle_type, raw_json, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (row.get("driver_name", ""), row.get("mother_name", ""), row.get("vehicle_no", ""),
             row.get("ownership", ""), row.get("vehicle_type", ""), json.dumps(row, ensure_ascii=False), utc_now()),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
