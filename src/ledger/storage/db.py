from __future__ import annotations

import sqlite3
from pathlib import Path

BUSINESS_TABLES = ("entries", "match_records", "match_links")
LEGACY_TABLES = ("ledger_entries",)


def connect_database(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA synchronous=FULL")
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    _rebuild_business_tables_if_needed(connection)

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS entries (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            row_index         INTEGER NOT NULL,
            subject_code      TEXT NOT NULL DEFAULT '',
            subject_name      TEXT NOT NULL DEFAULT '',
            posted_date       TEXT,
            business_date     TEXT,
            voucher_no        TEXT NOT NULL DEFAULT '',
            summary           TEXT NOT NULL DEFAULT '',
            debit_amount      TEXT NOT NULL DEFAULT '0.00',
            credit_amount     TEXT NOT NULL DEFAULT '0.00',
            direction         TEXT NOT NULL DEFAULT '',
            balance           TEXT NOT NULL DEFAULT '0.00',
            row_type          TEXT NOT NULL DEFAULT 'entry',
            amount_side       TEXT NOT NULL DEFAULT '',
            original_amount   TEXT NOT NULL DEFAULT '0.00',
            remaining_amount  TEXT NOT NULL DEFAULT '0.00'
        );

        CREATE TABLE IF NOT EXISTS match_records (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            match_type      TEXT NOT NULL,
            match_mode      TEXT NOT NULL,
            matched_amount  TEXT NOT NULL DEFAULT '0.00',
            reason          TEXT NOT NULL DEFAULT '',
            created_by      TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS match_links (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            match_record_id  INTEGER NOT NULL,
            entry_id         INTEGER NOT NULL,
            role             TEXT NOT NULL,
            used_amount      TEXT NOT NULL DEFAULT '0.00',
            FOREIGN KEY(match_record_id) REFERENCES match_records(id) ON DELETE CASCADE,
            FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
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

        CREATE INDEX IF NOT EXISTS idx_entries_row_type ON entries(row_type);
        CREATE INDEX IF NOT EXISTS idx_entries_amount_side ON entries(amount_side);
        CREATE INDEX IF NOT EXISTS idx_entries_remaining_amount ON entries(remaining_amount);
        CREATE INDEX IF NOT EXISTS idx_match_links_match_record_id ON match_links(match_record_id);
        CREATE INDEX IF NOT EXISTS idx_match_links_entry_id ON match_links(entry_id);
        """
    )
    connection.commit()


def _rebuild_business_tables_if_needed(connection: sqlite3.Connection) -> None:
    table_names = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }

    if "entries" not in table_names and "ledger_entries" in table_names:
        _drop_tables(connection, LEGACY_TABLES)
        return

    if "entries" not in table_names:
        return

    expected_columns = {
        "id",
        "row_index",
        "subject_code",
        "subject_name",
        "posted_date",
        "business_date",
        "voucher_no",
        "summary",
        "debit_amount",
        "credit_amount",
        "direction",
        "balance",
        "row_type",
        "amount_side",
        "original_amount",
        "remaining_amount",
    }
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(entries)").fetchall()
    }
    if expected_columns.issubset(existing_columns):
        return

    _drop_tables(connection, BUSINESS_TABLES)


def _drop_tables(connection: sqlite3.Connection, table_names: tuple[str, ...]) -> None:
    for table_name in table_names:
        connection.execute(f"DROP TABLE IF EXISTS {table_name}")
    connection.commit()
