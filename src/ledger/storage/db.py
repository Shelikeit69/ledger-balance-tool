from __future__ import annotations

import sqlite3
from pathlib import Path


def connect_database(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA synchronous=FULL")
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS ledger_entries (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_code    TEXT NOT NULL DEFAULT '',
            subject_name    TEXT NOT NULL DEFAULT '',
            posted_date     TEXT,
            business_date   TEXT,
            voucher_no      TEXT NOT NULL DEFAULT '',
            summary         TEXT NOT NULL DEFAULT '',
            debit_amount    TEXT NOT NULL DEFAULT '0.00',
            credit_amount   TEXT NOT NULL DEFAULT '0.00',
            direction       TEXT NOT NULL DEFAULT '',
            balance         TEXT NOT NULL DEFAULT '0.00'
        );

        CREATE TABLE IF NOT EXISTS correction_rules (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            match_text   TEXT NOT NULL,
            project_name TEXT NOT NULL,
            UNIQUE(match_text, project_name)
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    connection.commit()
