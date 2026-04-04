from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from ledger.storage.db import connect_database, initialize_database
from ledger.services.attribution import CorrectionRule
from ledger.services.importer import NormalizedLedgerRow


class LedgerRepository:
    def __init__(self, db_path: Path) -> None:
        self.connection = connect_database(db_path)
        initialize_database(self.connection)

    # ── 账目 ──────────────────────────────────────────

    def clear_rows(self) -> None:
        """导入新文件前清空旧数据。"""
        self.connection.execute("DELETE FROM ledger_entries")
        self.connection.commit()

    def save_rows(self, rows: list[NormalizedLedgerRow]) -> None:
        self.connection.executemany(
            """
            INSERT INTO ledger_entries (
                subject_code, subject_name, posted_date, business_date,
                voucher_no, summary, debit_amount, credit_amount,
                direction, balance
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.subject_code,
                    row.subject_name,
                    row.posted_date.isoformat() if row.posted_date else None,
                    row.business_date.isoformat() if row.business_date else None,
                    row.voucher_no,
                    row.summary,
                    str(row.debit_amount),
                    str(row.credit_amount),
                    row.direction,
                    str(row.balance),
                )
                for row in rows
            ],
        )
        self.connection.commit()

    def load_rows(self) -> list[NormalizedLedgerRow]:
        cursor = self.connection.execute(
            """
            SELECT subject_code, subject_name, posted_date, business_date,
                   voucher_no, summary, debit_amount, credit_amount,
                   direction, balance
            FROM ledger_entries
            ORDER BY COALESCE(posted_date, ''), COALESCE(business_date, ''),
                     voucher_no, summary
            """
        )
        return [
            NormalizedLedgerRow(
                subject_code=row["subject_code"],
                subject_name=row["subject_name"],
                posted_date=date.fromisoformat(row["posted_date"][:10]) if row["posted_date"] else None,
                business_date=date.fromisoformat(row["business_date"][:10]) if row["business_date"] else None,
                voucher_no=row["voucher_no"],
                summary=row["summary"],
                debit_amount=Decimal(row["debit_amount"]),
                credit_amount=Decimal(row["credit_amount"]),
                direction=row["direction"],
                balance=Decimal(row["balance"]),
            )
            for row in cursor.fetchall()
        ]

    def count_rows(self) -> int:
        cursor = self.connection.execute("SELECT COUNT(*) FROM ledger_entries")
        return int(cursor.fetchone()[0])

    # ── 规则 ──────────────────────────────────────────

    def save_rule(self, rule: CorrectionRule) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO correction_rules (match_text, project_name) VALUES (?, ?)",
            (rule.match_text, rule.project_name),
        )
        self.connection.commit()

    def load_rules(self) -> list[CorrectionRule]:
        cursor = self.connection.execute(
            "SELECT match_text, project_name FROM correction_rules ORDER BY id DESC"
        )
        return [
            CorrectionRule(match_text=row["match_text"], project_name=row["project_name"])
            for row in cursor.fetchall()
        ]

    def delete_rule(self, match_text: str, project_name: str) -> None:
        self.connection.execute(
            "DELETE FROM correction_rules WHERE match_text = ? AND project_name = ?",
            (match_text, project_name),
        )
        self.connection.commit()

    # ── 设置 ──────────────────────────────────────────

    def save_setting(self, key: str, value: str) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.connection.commit()

    def load_setting(self, key: str, default: str = "") -> str:
        cursor = self.connection.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        return row["value"] if row else default
