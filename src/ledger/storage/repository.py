from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from ledger.services.attribution import CorrectionRule
from ledger.services.importer import ImportedLedgerRow
from ledger.storage.db import connect_database, initialize_database


@dataclass(frozen=True)
class EntryRecord:
    id: int
    row_index: int
    subject_code: str
    subject_name: str
    posted_date: date | None
    business_date: date | None
    voucher_no: str
    summary: str
    debit_amount: Decimal
    credit_amount: Decimal
    direction: str
    balance: Decimal
    row_type: str
    amount_side: str
    original_amount: Decimal
    remaining_amount: Decimal

    @property
    def matched_amount(self) -> Decimal:
        return self.original_amount - self.remaining_amount

    @property
    def status(self) -> str:
        if self.row_type != "entry":
            return self.row_type
        if self.remaining_amount == self.original_amount:
            return "未匹配"
        if self.remaining_amount == Decimal("0.00"):
            return "已匹配"
        return "部分匹配"


@dataclass(frozen=True)
class EntryMatchInput:
    entry_id: int
    role: str
    used_amount: Decimal


@dataclass(frozen=True)
class MatchLinkRecord:
    id: int
    match_record_id: int
    entry_id: int
    role: str
    used_amount: Decimal


@dataclass(frozen=True)
class MatchRecord:
    id: int
    match_type: str
    match_mode: str
    matched_amount: Decimal
    reason: str
    created_by: str
    created_at: str
    links: list[MatchLinkRecord]


class LedgerRepository:
    def __init__(self, db_path: Path) -> None:
        self.connection = connect_database(db_path)
        initialize_database(self.connection)

    def clear_entries(self) -> None:
        self.connection.execute("DELETE FROM match_links")
        self.connection.execute("DELETE FROM match_records")
        self.connection.execute("DELETE FROM entries")
        self.connection.commit()

    def replace_entries(self, rows: list[ImportedLedgerRow]) -> None:
        self.clear_entries()
        self.save_entries(rows)

    def save_entries(self, rows: list[ImportedLedgerRow]) -> None:
        self.connection.executemany(
            """
            INSERT INTO entries (
                row_index, subject_code, subject_name, posted_date, business_date,
                voucher_no, summary, debit_amount, credit_amount, direction, balance,
                row_type, amount_side, original_amount, remaining_amount
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.row_index,
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
                    row.row_type,
                    row.amount_side,
                    str(row.original_amount),
                    str(row.remaining_amount),
                )
                for row in rows
            ],
        )
        self.connection.commit()

    def list_entries(
        self,
        *,
        row_type: str | None = None,
        only_unmatched: bool = False,
        sort_by_remaining_desc: bool = False,
    ) -> list[EntryRecord]:
        clauses: list[str] = []
        params: list[object] = []
        if row_type is not None:
            clauses.append("row_type = ?")
            params.append(row_type)
        if only_unmatched:
            clauses.append("CAST(remaining_amount AS REAL) > 0")
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order_sql = (
            "ORDER BY CAST(remaining_amount AS REAL) DESC, row_index ASC, id ASC"
            if sort_by_remaining_desc
            else "ORDER BY row_index ASC, id ASC"
        )
        cursor = self.connection.execute(
            f"""
            SELECT id, row_index, subject_code, subject_name, posted_date, business_date,
                   voucher_no, summary, debit_amount, credit_amount, direction, balance,
                   row_type, amount_side, original_amount, remaining_amount
            FROM entries
            {where_sql}
            {order_sql}
            """,
            params,
        )
        return [self._entry_from_row(row) for row in cursor.fetchall()]

    def get_entry(self, entry_id: int) -> EntryRecord | None:
        row = self.connection.execute(
            """
            SELECT id, row_index, subject_code, subject_name, posted_date, business_date,
                   voucher_no, summary, debit_amount, credit_amount, direction, balance,
                   row_type, amount_side, original_amount, remaining_amount
            FROM entries
            WHERE id = ?
            """,
            (entry_id,),
        ).fetchone()
        return self._entry_from_row(row) if row else None

    def get_entries(self, entry_ids: list[int]) -> list[EntryRecord]:
        if not entry_ids:
            return []
        placeholders = ", ".join("?" for _ in entry_ids)
        rows = self.connection.execute(
            f"""
            SELECT id, row_index, subject_code, subject_name, posted_date, business_date,
                   voucher_no, summary, debit_amount, credit_amount, direction, balance,
                   row_type, amount_side, original_amount, remaining_amount
            FROM entries
            WHERE id IN ({placeholders})
            ORDER BY row_index ASC, id ASC
            """,
            entry_ids,
        ).fetchall()
        return [self._entry_from_row(row) for row in rows]

    def count_entries(self, *, row_type: str | None = None) -> int:
        if row_type is None:
            cursor = self.connection.execute("SELECT COUNT(*) FROM entries")
        else:
            cursor = self.connection.execute(
                "SELECT COUNT(*) FROM entries WHERE row_type = ?",
                (row_type,),
            )
        return int(cursor.fetchone()[0])

    def create_match_record(
        self,
        *,
        match_type: str,
        match_mode: str,
        matched_amount: Decimal,
        reason: str,
        created_by: str,
        links: list[EntryMatchInput],
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO match_records (match_type, match_mode, matched_amount, reason, created_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (match_type, match_mode, str(matched_amount), reason, created_by),
        )
        match_record_id = int(cursor.lastrowid)
        self.connection.executemany(
            """
            INSERT INTO match_links (match_record_id, entry_id, role, used_amount)
            VALUES (?, ?, ?, ?)
            """,
            [
                (match_record_id, link.entry_id, link.role, str(link.used_amount))
                for link in links
            ],
        )
        self.connection.commit()
        self.recalculate_remaining_amounts()
        return match_record_id

    def list_match_records(self) -> list[MatchRecord]:
        rows = self.connection.execute(
            """
            SELECT id, match_type, match_mode, matched_amount, reason, created_by, created_at
            FROM match_records
            ORDER BY id DESC
            """
        ).fetchall()
        return [self._match_record_from_row(row) for row in rows]

    def delete_match_record(self, match_record_id: int) -> None:
        self.connection.execute(
            "DELETE FROM match_records WHERE id = ?",
            (match_record_id,),
        )
        self.connection.commit()
        self.recalculate_remaining_amounts()

    def recalculate_remaining_amounts(self) -> None:
        self.connection.execute(
            """
            UPDATE entries
            SET remaining_amount = CASE
                WHEN row_type = 'entry' THEN original_amount
                ELSE '0.00'
            END
            """
        )
        used_rows = self.connection.execute(
            """
            SELECT entry_id, used_amount
            FROM match_links
            """
        ).fetchall()
        used_amounts: dict[int, Decimal] = {}
        for row in used_rows:
            entry_id = int(row["entry_id"])
            used_amounts[entry_id] = used_amounts.get(entry_id, Decimal("0.00")) + Decimal(row["used_amount"])
        for entry_id, total_used in used_amounts.items():
            entry = self.get_entry(entry_id)
            if not entry:
                continue
            remaining = entry.original_amount - total_used
            if remaining < Decimal("0.00"):
                remaining = Decimal("0.00")
            self.connection.execute(
                "UPDATE entries SET remaining_amount = ? WHERE id = ?",
                (str(remaining), entry.id),
            )
        self.connection.commit()

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

    def save_setting(self, key: str, value: str) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.connection.commit()

    def load_setting(self, key: str, default: str = "") -> str:
        cursor = self.connection.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            (key,),
        )
        row = cursor.fetchone()
        return row["value"] if row else default

    def _entry_from_row(self, row) -> EntryRecord:
        return EntryRecord(
            id=int(row["id"]),
            row_index=int(row["row_index"]),
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
            row_type=row["row_type"],
            amount_side=row["amount_side"],
            original_amount=Decimal(row["original_amount"]),
            remaining_amount=Decimal(row["remaining_amount"]),
        )

    def _match_record_from_row(self, row) -> MatchRecord:
        links = self.connection.execute(
            """
            SELECT id, match_record_id, entry_id, role, used_amount
            FROM match_links
            WHERE match_record_id = ?
            ORDER BY id ASC
            """,
            (row["id"],),
        ).fetchall()
        return MatchRecord(
            id=int(row["id"]),
            match_type=row["match_type"],
            match_mode=row["match_mode"],
            matched_amount=Decimal(row["matched_amount"]),
            reason=row["reason"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            links=[
                MatchLinkRecord(
                    id=int(link["id"]),
                    match_record_id=int(link["match_record_id"]),
                    entry_id=int(link["entry_id"]),
                    role=link["role"],
                    used_amount=Decimal(link["used_amount"]),
                )
                for link in links
            ],
        )
