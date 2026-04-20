from __future__ import annotations

import csv
from io import BytesIO, StringIO

import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable
import zipfile
import xml.etree.ElementTree as ET

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from entity.models import EntityFinancialYear
from entity.models import EntityBankAccountV2
from posting.models import EntryStatus, JournalLine, TxnType

from .models import (
    BankReconciliationAuditLog,
    BankReconciliationExceptionItem,
    BankReconciliationMatchAllocation,
    BankReconciliationMatch,
    BankReconciliationRule,
    BankReconciliationSession,
    BankStatementImportProfile,
    BankStatementBatch,
    BankStatementLine,
    ZERO,
)


BANK_TXN_TYPES = (
    TxnType.JOURNAL,
    TxnType.JOURNAL_BANK,
    TxnType.JOURNAL_CASH,
    TxnType.RECEIPT,
    TxnType.PAYMENT,
    TxnType.SALES,
    TxnType.PURCHASE,
    TxnType.SALES_RETURN,
    TxnType.PURCHASE_RETURN,
    TxnType.PURCHASE_CREDIT_NOTE,
    TxnType.PURCHASE_DEBIT_NOTE,
)

CSV_DELIMITER_CANDIDATES = (",", ";", "\t", "|")


def _excel_column_index(cell_ref: str) -> int:
    value = 0
    for char in cell_ref:
        if not char.isalpha():
            break
        value = (value * 26) + (ord(char.upper()) - 64)
    return max(value - 1, 0)


def _parse_csv_rows(data: bytes, delimiter: str = ",") -> list[dict[str, object]]:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(StringIO(text), delimiter=delimiter or ",")
    return [dict(row) for row in reader]


def _count_columns_for_delimiter(text: str, delimiter: str) -> int:
    try:
        sample_reader = csv.reader(StringIO(text), delimiter=delimiter or ",")
        first_row = next(sample_reader, [])
        return len([cell for cell in first_row if cell is not None])
    except Exception:
        return 0


def _detect_csv_delimiter(data: bytes, preferred: str = ",") -> str:
    text = data.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    normalized_preferred = (preferred or ",").replace("tab", "\t")

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(CSV_DELIMITER_CANDIDATES))
        detected = getattr(dialect, "delimiter", "")
        if detected:
            return detected
    except Exception:
        pass

    best_delimiter = normalized_preferred if normalized_preferred in CSV_DELIMITER_CANDIDATES else ","
    best_score = -1
    for delimiter in CSV_DELIMITER_CANDIDATES:
        score = _count_columns_for_delimiter(sample, delimiter)
        if delimiter == normalized_preferred:
            score += 1
        if score > best_score:
            best_delimiter = delimiter
            best_score = score
    return best_delimiter


def _parse_xlsx_rows(data: bytes) -> list[dict[str, object]]:
    namespace_main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    namespace_rel = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    namespace_pkg = "{http://schemas.openxmlformats.org/package/2006/relationships}"

    def _load_shared_strings(zf: zipfile.ZipFile) -> list[str]:
        if "xl/sharedStrings.xml" not in zf.namelist():
            return []
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        values: list[str] = []
        for shared_string in root.findall(f"{namespace_main}si"):
            parts = [node.text or "" for node in shared_string.iter(f"{namespace_main}t")]
            values.append("".join(parts))
        return values

    def _resolve_sheet_path(zf: zipfile.ZipFile) -> str:
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rel_map = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels.findall(f"{namespace_pkg}Relationship")
        }
        first_sheet = workbook.find(f"{namespace_main}sheets/{namespace_main}sheet")
        if first_sheet is None:
            raise ValueError("Workbook does not contain a sheet.")
        rel_id = first_sheet.attrib.get(f"{namespace_rel}id")
        target = rel_map.get(rel_id)
        if not target:
            raise ValueError("Unable to resolve workbook sheet path.")
        return target if target.startswith("xl/") else f"xl/{target}"

    with zipfile.ZipFile(BytesIO(data)) as zf:
        shared_strings = _load_shared_strings(zf)
        sheet_path = _resolve_sheet_path(zf)
        root = ET.fromstring(zf.read(sheet_path))
        rows: list[dict[str, object]] = []
        headers: list[str] = []
        sheet_data = root.find(f"{namespace_main}sheetData")
        if sheet_data is None:
            return rows

        for row in sheet_data.findall(f"{namespace_main}row"):
            values: list[str] = []
            for cell in row.findall(f"{namespace_main}c"):
                ref = cell.attrib.get("r", "A1")
                idx = _excel_column_index(ref)
                while len(values) <= idx:
                    values.append("")
                cell_type = cell.attrib.get("t")
                value = ""
                if cell_type == "s":
                    shared_index = int(cell.findtext(f"{namespace_main}v") or 0)
                    value = shared_strings[shared_index] if shared_index < len(shared_strings) else ""
                elif cell_type == "inlineStr":
                    value = "".join(node.text or "" for node in cell.iter(f"{namespace_main}t"))
                else:
                    value = cell.findtext(f"{namespace_main}v") or ""
                values[idx] = value

            if not headers:
                headers = [str(value).strip() for value in values]
                continue
            row_payload = {headers[idx] or f"column_{idx + 1}": value for idx, value in enumerate(values) if idx < len(headers)}
            rows.append(row_payload)
        return rows


def parse_statement_file(data: bytes, source_format: str, delimiter: str = ",") -> list[dict[str, object]]:
    normalized_format = str(source_format or "").strip().lower()
    if normalized_format == "csv":
        resolved_delimiter = _detect_csv_delimiter(data, delimiter)
        return _parse_csv_rows(data, delimiter=resolved_delimiter)
    if normalized_format == "excel":
        return _parse_xlsx_rows(data)
    if normalized_format == "json":
        payload = json.loads(data.decode("utf-8-sig"))
        if not isinstance(payload, list):
            raise ValueError("JSON file must contain an array of rows.")
        return [dict(row) for row in payload]
    raise ValueError(f"Unsupported statement format: {source_format}")


def preview_statement_file(data: bytes, source_format: str, delimiter: str = ",", limit: int = 5) -> dict[str, object]:
    resolved_delimiter = delimiter
    if str(source_format or "").strip().lower() == "csv":
        resolved_delimiter = _detect_csv_delimiter(data, delimiter)
    rows = parse_statement_file(data, source_format, delimiter=resolved_delimiter)
    headers = list(rows[0].keys()) if rows else []
    return {
        "headers": headers,
        "sample_rows": rows[:limit],
        "row_count": len(rows),
        "delimiter": resolved_delimiter,
    }


def _safe_decimal(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return ZERO


def _safe_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return None


def _row_hash(payload: dict[str, object]) -> str:
    stable = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha1(stable.encode("utf-8")).hexdigest()


def _mask_account_number(account_number: str | None) -> str:
    text = str(account_number or "").strip()
    if len(text) <= 4:
        return text
    return f"{'*' * max(len(text) - 4, 0)}{text[-4:]}"


def _statement_amount(line: BankStatementLine) -> Decimal:
    return (line.credit_amount or ZERO) if (line.credit_amount or ZERO) > ZERO else (line.debit_amount or ZERO)


def _statement_direction(line: BankStatementLine) -> str:
    if (line.credit_amount or ZERO) > ZERO and (line.debit_amount or ZERO) <= ZERO:
        return "credit"
    if (line.debit_amount or ZERO) > ZERO and (line.credit_amount or ZERO) <= ZERO:
        return "debit"
    return "credit" if (line.credit_amount or ZERO) >= (line.debit_amount or ZERO) else "debit"


def _bank_to_book_drcr(direction: str) -> bool:
    return direction == "credit"


def _mapping_value(row: dict[str, object], key: str | None, default_keys: tuple[str, ...] = ()) -> object:
    candidates: list[str] = []
    if key:
        candidates.append(key)
    candidates.extend(default_keys)
    for candidate in candidates:
        if candidate in row and row.get(candidate) not in (None, ""):
            return row.get(candidate)
    return None


def _iso_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _journal_line_descriptor(line: JournalLine) -> str:
    parts = [
        str(line.voucher_no or "").strip(),
        str(getattr(line.entry, "voucher_no", "") or "").strip(),
        str(line.description or "").strip(),
        str(getattr(line.entry, "narration", "") or "").strip(),
    ]
    return " ".join(part for part in parts if part).strip().lower()


def _score_candidate(line: BankStatementLine, journal_line: JournalLine) -> tuple[Decimal, str]:
    score = Decimal("0.00")
    reasons: list[str] = []
    statement_amount = _statement_amount(line)

    if statement_amount and journal_line.amount == statement_amount:
        score += Decimal("55.00")
        reasons.append("amount")

    if line.reference_number:
        ref = line.reference_number.lower()
        descriptor = _journal_line_descriptor(journal_line)
        if ref in descriptor or str(journal_line.voucher_no or "").lower() == ref:
            score += Decimal("25.00")
            reasons.append("reference")

    if line.transaction_date and journal_line.posting_date:
        gap = abs((journal_line.posting_date - line.transaction_date).days)
        if gap == 0:
            score += Decimal("20.00")
            reasons.append("date")
        elif gap <= 2:
            score += Decimal("12.00")
            reasons.append("near_date")
        elif gap <= 5:
            score += Decimal("6.00")
            reasons.append("window")

    descriptor = _journal_line_descriptor(journal_line)
    if line.description and line.description.lower() in descriptor:
        score += Decimal("10.00")
        reasons.append("description")
    if line.counterparty and line.counterparty.lower() in descriptor:
        score += Decimal("8.00")
        reasons.append("counterparty")

    if journal_line.entry_id and journal_line.entry.status == EntryStatus.POSTED:
        score += Decimal("5.00")
        reasons.append("posted")

    return min(score, Decimal("100.00")), ",".join(reasons) or "amount"


def candidate_journal_lines(session: BankReconciliationSession, statement_line: BankStatementLine) -> list[dict[str, object]]:
    direction = _statement_direction(statement_line)
    expected_drcr = _bank_to_book_drcr(direction)
    amount = _statement_amount(statement_line)
    if amount <= ZERO:
        return []

    candidates = (
        JournalLine.objects.select_related("entry")
        .filter(
            entity=session.entity,
            entry__status=EntryStatus.POSTED,
            drcr=expected_drcr,
            amount=amount,
            txn_type__in=BANK_TXN_TYPES,
        )
    )
    if session.entityfin_id:
        candidates = candidates.filter(entityfin_id=session.entityfin_id)
    if session.subentity_id:
        candidates = candidates.filter(subentity_id=session.subentity_id)
    if statement_line.transaction_date:
        candidates = candidates.filter(
            posting_date__gte=statement_line.transaction_date - timedelta(days=5),
            posting_date__lte=statement_line.transaction_date + timedelta(days=5),
        )

    ranked: list[dict[str, object]] = []
    for journal_line in candidates.order_by("posting_date", "id")[:25]:
        score, reason = _score_candidate(statement_line, journal_line)
        ranked.append(
            {
                "journal_line_id": journal_line.id,
                "entry_id": journal_line.entry_id,
                "txn_type": journal_line.txn_type,
                "txn_id": journal_line.txn_id,
                "voucher_no": journal_line.voucher_no,
                "posting_date": journal_line.posting_date,
                "amount": f"{journal_line.amount:.2f}",
                "drcr": "debit" if journal_line.drcr else "credit",
                "description": journal_line.description or "",
                "score": score,
                "reason": reason,
            }
        )

    ranked.sort(key=lambda item: (item["score"], item["posting_date"] or "", item["journal_line_id"]), reverse=True)
    return ranked[:10]


def _apply_match(
    *,
    session: BankReconciliationSession,
    statement_line: BankStatementLine,
    journal_line: JournalLine,
    created_by=None,
    match_kind: str = BankReconciliationMatch.MatchKind.MANUAL,
    confidence: Decimal | None = None,
    notes: str = "",
    metadata: dict[str, object] | None = None,
) -> BankReconciliationMatch:
    score, reason = _score_candidate(statement_line, journal_line)
    match, _ = BankReconciliationMatch.objects.update_or_create(
        statement_line=statement_line,
        defaults={
            "session": session,
            "entry": journal_line.entry,
            "journal_line": journal_line,
            "match_kind": match_kind,
            "matched_amount": journal_line.amount,
            "difference_amount": _statement_amount(statement_line) - journal_line.amount,
            "confidence": confidence if confidence is not None else score,
            "notes": notes or reason,
            "matchedby": created_by,
            "matched_at": timezone.now(),
            "metadata": metadata or {"auto_reason": reason},
            },
    )
    match.allocations.all().delete()
    statement_line.match_status = BankStatementLine.MatchStatus.MATCHED
    statement_line.suggested_match_score = confidence if confidence is not None else score
    statement_line.metadata = {**(statement_line.metadata or {}), "matched_journal_line_id": journal_line.id}
    statement_line.save(update_fields=["match_status", "suggested_match_score", "metadata", "updated_at"])
    BankReconciliationAuditLog.objects.create(
        session=session,
        action="line_matched",
        actor=created_by,
        payload={
            "statement_line_id": statement_line.id,
            "journal_line_id": journal_line.id,
            "entry_id": journal_line.entry_id,
            "match_kind": match_kind,
            "reason": reason,
        },
    )
    return match


def serialize_bank_account(bank_account: EntityBankAccountV2) -> dict[str, object]:
    return {
        "id": bank_account.id,
        "bank_name": bank_account.bank_name,
        "branch": bank_account.branch,
        "account_number": _mask_account_number(bank_account.account_number),
        "ifsc_code": bank_account.ifsc_code,
        "account_type": bank_account.account_type,
        "is_primary": bank_account.is_primary,
        "effective_from": _iso_date(bank_account.effective_from),
        "effective_to": _iso_date(bank_account.effective_to),
    }


def normalize_statement_row(
    row: dict[str, object],
    line_no: int,
    *,
    mapping: dict[str, str] | None = None,
) -> dict[str, object]:
    mapping = mapping or {}
    transaction_date = _safe_date(_mapping_value(row, mapping.get("transaction_date"), ("transaction_date", "date", "txn_date")))
    value_date = _safe_date(_mapping_value(row, mapping.get("value_date"), ("value_date", "valueDate")))
    debit_amount = _safe_decimal(_mapping_value(row, mapping.get("debit_amount"), ("debit_amount", "debit")) or 0)
    credit_amount = _safe_decimal(_mapping_value(row, mapping.get("credit_amount"), ("credit_amount", "credit")) or 0)

    amount = _safe_decimal(_mapping_value(row, mapping.get("amount"), ("amount",)))
    direction = str(_mapping_value(row, mapping.get("direction"), ("direction", "drcr")) or "").strip().lower()
    if debit_amount == ZERO and credit_amount == ZERO and amount:
        if direction in {"credit", "cr", "c", "in", "receipt"}:
            credit_amount = amount
        elif direction in {"debit", "dr", "d", "out", "payment"}:
            debit_amount = amount
        else:
            credit_amount = amount if amount < ZERO else ZERO
            debit_amount = amount if amount > ZERO else ZERO

    payload = {
        "line_no": line_no,
        "transaction_date": transaction_date,
        "value_date": value_date,
        "description": str(_mapping_value(row, mapping.get("description"), ("description", "narration")) or "").strip(),
        "reference_number": str(_mapping_value(row, mapping.get("reference_number"), ("reference_number", "reference", "cheque_no")) or "").strip(),
        "counterparty": str(_mapping_value(row, mapping.get("counterparty"), ("counterparty", "party_name")) or "").strip(),
        "debit_amount": str(debit_amount),
        "credit_amount": str(credit_amount),
        "balance_amount": str(_safe_decimal(_mapping_value(row, mapping.get("balance_amount"), ("balance_amount", "balance")))) if _mapping_value(row, mapping.get("balance_amount"), ("balance_amount", "balance")) is not None else None,
        "currency": str(_mapping_value(row, mapping.get("currency"), ("currency",)) or "INR").strip().upper() or "INR",
        "external_id": str(_mapping_value(row, mapping.get("external_id"), ("external_id", "id")) or "").strip(),
    }
    payload["row_hash"] = _row_hash(payload)
    payload["match_status"] = str(row.get("match_status") or "unmatched").strip().lower() or "unmatched"
    payload["suggested_match_score"] = _safe_decimal(row.get("suggested_match_score") or 0)
    payload["metadata"] = dict(row.get("metadata") or {})
    return payload


def recalculate_session_metrics(session: BankReconciliationSession) -> BankReconciliationSession:
    lines = BankStatementLine.objects.filter(batch__session=session)
    matches = BankReconciliationMatch.objects.filter(session=session)
    exceptions = BankReconciliationExceptionItem.objects.filter(session=session)

    imported_row_count = lines.count()
    matched_row_count = lines.filter(match_status=BankStatementLine.MatchStatus.MATCHED).count()
    reviewed_row_count = lines.filter(
        match_status__in=[
            BankStatementLine.MatchStatus.SUGGESTED,
            BankStatementLine.MatchStatus.MATCHED,
            BankStatementLine.MatchStatus.EXCEPTION,
            BankStatementLine.MatchStatus.IGNORED,
        ]
    ).count()
    exception_row_count = max(lines.filter(match_status=BankStatementLine.MatchStatus.EXCEPTION).count(), exceptions.count())

    statement_debits = lines.aggregate(total=Sum("debit_amount"))["total"] or ZERO
    statement_credits = lines.aggregate(total=Sum("credit_amount"))["total"] or ZERO
    statement_delta = statement_credits - statement_debits
    matched_amount = matches.aggregate(total=Sum("matched_amount"))["total"] or ZERO

    session.imported_row_count = imported_row_count
    session.matched_row_count = matched_row_count
    session.reviewed_row_count = reviewed_row_count
    session.exception_row_count = exception_row_count
    session.matched_amount = matched_amount
    session.difference_amount = (statement_delta - session.book_closing_balance) if session.book_closing_balance else statement_delta
    session.unmatched_amount = statement_debits - statement_credits
    if matches.exists() and imported_row_count and matched_row_count == imported_row_count and exception_row_count == 0:
        session.status = BankReconciliationSession.Status.RECONCILED
    elif imported_row_count:
        session.status = BankReconciliationSession.Status.NEEDS_REVIEW if exception_row_count or matched_row_count != imported_row_count else BankReconciliationSession.Status.IMPORTED
    session.save(
        update_fields=[
            "imported_row_count",
            "matched_row_count",
            "reviewed_row_count",
        "exception_row_count",
        "matched_amount",
        "difference_amount",
        "unmatched_amount",
        "status",
        "updated_at",
    ]
    )
    return session


def build_reconciliation_summary(session: BankReconciliationSession) -> dict[str, object]:
    lines = BankStatementLine.objects.filter(batch__session=session)
    exceptions = BankReconciliationExceptionItem.objects.filter(session=session)
    unresolved_lines = lines.filter(match_status__in=[BankStatementLine.MatchStatus.UNMATCHED, BankStatementLine.MatchStatus.SUGGESTED]).count()
    open_exceptions = exceptions.filter(status=BankReconciliationExceptionItem.Status.OPEN).count()
    return {
        "imported_row_count": lines.count(),
        "matched_row_count": lines.filter(match_status=BankStatementLine.MatchStatus.MATCHED).count(),
        "reviewed_row_count": lines.filter(
            match_status__in=[
                BankStatementLine.MatchStatus.SUGGESTED,
                BankStatementLine.MatchStatus.MATCHED,
                BankStatementLine.MatchStatus.EXCEPTION,
                BankStatementLine.MatchStatus.IGNORED,
            ]
        ).count(),
        "exception_row_count": max(lines.filter(match_status=BankStatementLine.MatchStatus.EXCEPTION).count(), exceptions.count()),
        "open_exception_count": open_exceptions,
        "unresolved_line_count": unresolved_lines,
        "matched_amount": f"{session.matched_amount:.2f}",
        "unmatched_amount": f"{session.unmatched_amount:.2f}",
        "difference_amount": f"{session.difference_amount:.2f}",
        "status": session.status,
        "can_lock": session.status != BankReconciliationSession.Status.LOCKED,
    }


def build_session_payload(session: BankReconciliationSession) -> dict[str, object]:
    batches = []
    for batch in session.batches.all().order_by("-created_at", "-id"):
        batches.append(
            {
                "id": batch.id,
                "batch_code": batch.batch_code,
                "source_name": batch.source_name,
                "source_format": batch.source_format,
                "imported_row_count": batch.imported_row_count,
                "duplicate_row_count": batch.duplicate_row_count,
                "created_at": _iso_date(batch.created_at),
                "lines": [
                    {
                        "id": line.id,
                        "line_no": line.line_no,
                        "transaction_date": line.transaction_date,
                        "value_date": line.value_date,
                        "description": line.description,
                        "reference_number": line.reference_number,
                        "counterparty": line.counterparty,
                        "debit_amount": f"{line.debit_amount:.2f}",
                        "credit_amount": f"{line.credit_amount:.2f}",
                        "balance_amount": f"{line.balance_amount:.2f}" if line.balance_amount is not None else None,
                        "currency": line.currency,
                        "match_status": line.match_status,
                        "suggested_match_score": f"{line.suggested_match_score:.2f}",
                    }
                    for line in batch.lines.all().order_by("line_no", "id")
                ],
            }
        )

    return {
        "id": session.id,
        "session_code": session.session_code,
        "entity_id": session.entity_id,
        "entity_name": session.entity.entityname if session.entity_id else "",
        "entityfin_id": session.entityfin_id,
        "subentity_id": session.subentity_id,
        "bank_account": serialize_bank_account(session.bank_account),
        "status": session.status,
        "statement_label": session.statement_label,
        "source_name": session.source_name,
        "source_format": session.source_format,
        "date_from": _iso_date(session.date_from),
        "date_to": _iso_date(session.date_to),
        "statement_opening_balance": f"{session.statement_opening_balance:.2f}",
        "statement_closing_balance": f"{session.statement_closing_balance:.2f}",
        "book_opening_balance": f"{session.book_opening_balance:.2f}",
        "book_closing_balance": f"{session.book_closing_balance:.2f}",
        "matched_amount": f"{session.matched_amount:.2f}",
        "unmatched_amount": f"{session.unmatched_amount:.2f}",
        "difference_amount": f"{session.difference_amount:.2f}",
        "imported_row_count": session.imported_row_count,
        "matched_row_count": session.matched_row_count,
        "reviewed_row_count": session.reviewed_row_count,
        "exception_row_count": session.exception_row_count,
        "notes": session.notes,
        "metadata": session.metadata,
        "batches": batches,
        "recent_matches": [
            {
                "id": match.id,
                "match_kind": match.match_kind,
                "matched_amount": f"{match.matched_amount:.2f}",
                "difference_amount": f"{match.difference_amount:.2f}",
                "confidence": f"{match.confidence:.2f}",
                "statement_line_id": match.statement_line_id,
                "entry_id": match.entry_id,
                "journal_line_id": match.journal_line_id,
                "notes": match.notes,
                "allocations": [
                    {
                        "id": allocation.id,
                        "journal_line_id": allocation.journal_line_id,
                        "allocated_amount": f"{allocation.allocated_amount:.2f}",
                        "allocation_order": allocation.allocation_order,
                        "notes": allocation.notes,
                    }
                    for allocation in match.allocations.all().order_by("allocation_order", "id")
                ],
            }
            for match in session.matches.all().order_by("-matched_at", "-id")[:20]
        ],
        "recent_exceptions": [
            {
                "id": exception.id,
                "statement_line_id": exception.statement_line_id,
                "exception_type": exception.exception_type,
                "status": exception.status,
                "amount": f"{exception.amount:.2f}",
                "notes": exception.notes,
                "metadata": exception.metadata,
            }
            for exception in session.exceptions.all().order_by("-created_at", "-id")[:20]
        ],
        "audit_logs": [
            {
                "id": log.id,
                "action": log.action,
                "actor_id": log.actor_id,
                "payload": log.payload,
                "created_at": _iso_date(log.created_at),
            }
            for log in session.audit_logs.all().order_by("-created_at", "-id")[:20]
        ],
        "summary": build_reconciliation_summary(session),
    }


def build_hub_payload(*, entity, entityfin_id=None, subentity_id=None) -> dict[str, object]:
    sessions = BankReconciliationSession.objects.filter(entity=entity)
    if entityfin_id:
        sessions = sessions.filter(entityfin_id=entityfin_id)
    if subentity_id:
        sessions = sessions.filter(subentity_id=subentity_id)

    bank_accounts = EntityBankAccountV2.objects.filter(entity=entity, isactive=True).order_by("-is_primary", "bank_name", "id")
    financial_years = EntityFinancialYear.objects.filter(entity=entity, isactive=True).order_by("-finstartyear", "id")

    status_counts = {
        row["status"]: row["total"]
        for row in sessions.values("status").annotate(total=Count("id"))
    }

    recent_sessions = [
        {
            "id": session.id,
            "session_code": session.session_code,
            "status": session.status,
            "statement_label": session.statement_label,
            "source_name": session.source_name,
            "bank_account": serialize_bank_account(session.bank_account),
            "date_from": _iso_date(session.date_from),
            "date_to": _iso_date(session.date_to),
            "imported_row_count": session.imported_row_count,
            "matched_row_count": session.matched_row_count,
            "difference_amount": f"{session.difference_amount:.2f}",
            "created_at": _iso_date(session.created_at),
        }
        for session in sessions.select_related("bank_account").order_by("-created_at", "-id")[:8]
    ]

    return {
        "report_code": "bank_reconciliation_hub",
        "report_name": "Bank Reconciliation",
        "report_eyebrow": "Financial Controls",
        "entity_id": entity.id,
        "entity_name": entity.entityname,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "generated_at": timezone.now().isoformat(),
        "summary_cards": [
            {"label": "Bank accounts", "value": bank_accounts.count(), "note": "Active bank accounts available for reconciliation", "tone": "neutral"},
            {"label": "Sessions", "value": sessions.count(), "note": "Reconciliation workspaces started for the selected scope", "tone": "accent"},
            {"label": "Imported rows", "value": sessions.aggregate(total=Sum("imported_row_count"))["total"] or 0, "note": "Rows loaded into statement batches", "tone": "neutral"},
            {
                "label": "Open difference",
                "value": f"{(sessions.aggregate(total=Sum('difference_amount'))['total'] or ZERO):.2f}",
                "note": "Combined unreconciled delta for the scope",
                "tone": "warning",
            },
        ],
        "status_counts": status_counts,
        "financial_years": [
            {
                "id": fy.id,
                "desc": fy.desc,
                "year_code": fy.year_code,
                "period_status": getattr(fy, "period_status", None),
                "is_year_closed": bool(getattr(fy, "is_year_closed", False)),
            }
            for fy in financial_years
        ],
        "bank_accounts": [serialize_bank_account(bank_account) for bank_account in bank_accounts],
        "recent_sessions": recent_sessions,
        "next_steps": [
            "Create a reconciliation session for a bank account",
            "Import a statement batch as JSON, CSV, or Excel-normalized rows",
            "Add matching rules in the next phase",
        ],
        "actions": {
            "can_create_session": True,
            "can_import_statement": True,
            "can_manage_rules": True,
        },
    }


@transaction.atomic
def auto_match_session(*, session: BankReconciliationSession, created_by=None, threshold: Decimal = Decimal("70.00")) -> dict[str, object]:
    total_lines = 0
    candidates_considered = 0
    matches: list[dict[str, object]] = []

    unmatched_lines = (
        BankStatementLine.objects.filter(
            batch__session=session,
            match_status__in=[BankStatementLine.MatchStatus.UNMATCHED, BankStatementLine.MatchStatus.SUGGESTED],
        )
        .select_related("batch")
        .order_by("line_no", "id")
    )

    for statement_line in unmatched_lines:
        total_lines += 1
        candidates = candidate_journal_lines(session, statement_line)
        candidates_considered += len(candidates)
        if not candidates:
            continue

        best = candidates[0]
        if best["score"] < threshold:
            statement_line.match_status = BankStatementLine.MatchStatus.SUGGESTED
            statement_line.suggested_match_score = best["score"]
            statement_line.save(update_fields=["match_status", "suggested_match_score", "updated_at"])
            continue

        journal_line = (
            JournalLine.objects.select_related("entry")
            .filter(id=best["journal_line_id"])
            .first()
        )
        if journal_line is None:
            continue

        match = _apply_match(
            session=session,
            statement_line=statement_line,
            journal_line=journal_line,
            created_by=created_by,
            match_kind=BankReconciliationMatch.MatchKind.EXACT,
            confidence=best["score"],
            notes=best["reason"],
            metadata={"auto": True, "reasons": best["reason"]},
        )
        matches.append(
            {
                "statement_line_id": statement_line.id,
                "journal_line_id": journal_line.id,
                "confidence": f"{match.confidence:.2f}",
                "matched_amount": f"{match.matched_amount:.2f}",
            }
        )

    recalculate_session_metrics(session)
    session.status = (
        BankReconciliationSession.Status.RECONCILED
        if session.imported_row_count and session.matched_row_count == session.imported_row_count and session.exception_row_count == 0
        else BankReconciliationSession.Status.NEEDS_REVIEW
    )
    session.save(update_fields=["status", "updated_at"])
    BankReconciliationAuditLog.objects.create(
        session=session,
        action="auto_match_completed",
        actor=created_by,
        payload={
            "matched_count": len(matches),
            "candidates_considered": candidates_considered,
            "total_lines": total_lines,
            "threshold": str(threshold),
        },
    )
    return {
        "matched_count": len(matches),
        "reviewed_count": session.reviewed_row_count,
        "unmatched_count": max(total_lines - len(matches), 0),
        "total_lines": total_lines,
        "candidates_considered": candidates_considered,
        "matches": matches,
    }


@transaction.atomic
def manual_match_line(
    *,
    session: BankReconciliationSession,
    statement_line: BankStatementLine,
    journal_line: JournalLine,
    created_by=None,
    match_kind: str = BankReconciliationMatch.MatchKind.MANUAL,
    notes: str = "",
    confidence: Decimal | None = None,
    metadata: dict[str, object] | None = None,
) -> BankReconciliationMatch:
    return _apply_match(
        session=session,
        statement_line=statement_line,
        journal_line=journal_line,
        created_by=created_by,
        match_kind=match_kind,
        confidence=confidence,
        notes=notes,
        metadata=metadata,
    )


def _clear_statement_line_match(statement_line: BankStatementLine) -> None:
    BankReconciliationMatch.objects.filter(statement_line=statement_line).delete()
    statement_line.match_status = BankStatementLine.MatchStatus.UNMATCHED
    statement_line.suggested_match_score = ZERO
    statement_line.metadata = {k: v for k, v in (statement_line.metadata or {}).items() if k != "matched_journal_line_id"}
    statement_line.save(update_fields=["match_status", "suggested_match_score", "metadata", "updated_at"])


@transaction.atomic
def unmatch_statement_line(*, session: BankReconciliationSession, statement_line: BankStatementLine, created_by=None) -> None:
    BankReconciliationMatch.objects.filter(session=session, statement_line=statement_line).delete()
    _clear_statement_line_match(statement_line)
    BankReconciliationAuditLog.objects.create(
        session=session,
        action="line_unmatched",
        actor=created_by,
        payload={"statement_line_id": statement_line.id},
    )


@transaction.atomic
def resolve_exception_item(
    *,
    session: BankReconciliationSession,
    exception_item: BankReconciliationExceptionItem,
    created_by=None,
    status: str = BankReconciliationExceptionItem.Status.RESOLVED,
) -> BankReconciliationExceptionItem:
    normalized_status = str(status or BankReconciliationExceptionItem.Status.RESOLVED).strip().lower()
    if normalized_status not in {
        BankReconciliationExceptionItem.Status.RESOLVED,
        BankReconciliationExceptionItem.Status.IGNORED,
    }:
        raise ValueError("Unsupported exception resolution status.")

    if normalized_status == BankReconciliationExceptionItem.Status.IGNORED:
        exception_item.status = BankReconciliationExceptionItem.Status.IGNORED
        exception_item.resolvedby = created_by
        exception_item.resolved_at = timezone.now()
        exception_item.save(update_fields=["status", "resolvedby", "resolved_at", "updated_at"])
        exception_item.statement_line.match_status = BankStatementLine.MatchStatus.IGNORED
        exception_item.statement_line.suggested_match_score = ZERO
        statement_metadata = dict(exception_item.statement_line.metadata or {})
        statement_metadata.pop("exception_type", None)
        statement_metadata["exception_status"] = "ignored"
        exception_item.statement_line.metadata = statement_metadata
        exception_item.statement_line.save(update_fields=["match_status", "suggested_match_score", "metadata", "updated_at"])
    else:
        exception_item.status = BankReconciliationExceptionItem.Status.RESOLVED
        exception_item.resolvedby = created_by
        exception_item.resolved_at = timezone.now()
        exception_item.save(update_fields=["status", "resolvedby", "resolved_at", "updated_at"])
        statement_line = exception_item.statement_line
        statement_line.match_status = BankStatementLine.MatchStatus.UNMATCHED
        statement_line.suggested_match_score = ZERO
        statement_metadata = dict(statement_line.metadata or {})
        statement_metadata.pop("exception_type", None)
        statement_metadata["exception_status"] = "resolved"
        statement_line.metadata = statement_metadata
        statement_line.save(update_fields=["match_status", "suggested_match_score", "metadata", "updated_at"])

    BankReconciliationAuditLog.objects.create(
        session=session,
        action="exception_resolved",
        actor=created_by,
        payload={
            "exception_id": exception_item.id,
            "statement_line_id": exception_item.statement_line_id,
            "status": exception_item.status,
        },
    )
    return exception_item


@transaction.atomic
def split_match_line(
    *,
    session: BankReconciliationSession,
    statement_line: BankStatementLine,
    allocations: list[dict[str, object]],
    created_by=None,
    notes: str = "",
    confidence: Decimal | None = None,
    metadata: dict[str, object] | None = None,
) -> BankReconciliationMatch:
    if not allocations:
        raise ValueError("At least one allocation is required for a split match.")

    journal_rows: list[tuple[JournalLine, Decimal, str]] = []
    total = ZERO
    for allocation in allocations:
        journal_line = JournalLine.objects.select_related("entry").filter(
            id=allocation["journal_line_id"],
            entity=session.entity,
        ).first()
        if journal_line is None:
            raise ValueError(f"Journal line {allocation['journal_line_id']} not found.")
        amount = _safe_decimal(allocation["amount"])
        if amount <= ZERO:
            raise ValueError("Allocation amounts must be greater than zero.")
        journal_rows.append((journal_line, amount, str(allocation.get("notes") or "").strip()))
        total += amount

    statement_amount = _statement_amount(statement_line)
    match = BankReconciliationMatch.objects.update_or_create(
        statement_line=statement_line,
        defaults={
            "session": session,
            "entry": journal_rows[0][0].entry,
            "journal_line": journal_rows[0][0],
            "match_kind": BankReconciliationMatch.MatchKind.SPLIT,
            "matched_amount": total,
            "difference_amount": statement_amount - total,
            "confidence": confidence if confidence is not None else Decimal("75.00"),
            "notes": notes or "split",
            "matchedby": created_by,
            "matched_at": timezone.now(),
            "metadata": metadata or {"split": True},
        },
    )[0]

    statement_line.match_status = BankStatementLine.MatchStatus.MATCHED
    statement_line.suggested_match_score = confidence if confidence is not None else Decimal("75.00")
    statement_line.metadata = {**(statement_line.metadata or {}), "split_match": True}
    statement_line.save(update_fields=["match_status", "suggested_match_score", "metadata", "updated_at"])

    match.allocations.all().delete()
    for order, (journal_line, amount, allocation_notes) in enumerate(journal_rows, start=1):
        BankReconciliationMatchAllocation.objects.create(
            match=match,
            journal_line=journal_line,
            allocated_amount=amount,
            allocation_order=order,
            notes=allocation_notes,
            metadata={"split_allocation": True},
            createdby=created_by,
        )
    BankReconciliationAuditLog.objects.create(
        session=session,
        action="line_split_matched",
        actor=created_by,
        payload={
            "statement_line_id": statement_line.id,
            "allocation_count": len(journal_rows),
            "match_kind": BankReconciliationMatch.MatchKind.SPLIT,
        },
    )
    return match


@transaction.atomic
def record_exception(
    *,
    session: BankReconciliationSession,
    statement_line: BankStatementLine,
    exception_type: str,
    amount: Decimal | None = None,
    created_by=None,
    notes: str = "",
    metadata: dict[str, object] | None = None,
) -> BankReconciliationExceptionItem:
    if amount is None:
        amount = _statement_amount(statement_line)
    statement_line.match_status = BankStatementLine.MatchStatus.EXCEPTION
    statement_line.suggested_match_score = ZERO
    statement_line.metadata = {**(statement_line.metadata or {}), "exception_type": exception_type}
    statement_line.save(update_fields=["match_status", "suggested_match_score", "metadata", "updated_at"])

    exception_item, _ = BankReconciliationExceptionItem.objects.update_or_create(
        statement_line=statement_line,
        defaults={
            "session": session,
            "exception_type": exception_type,
            "status": BankReconciliationExceptionItem.Status.OPEN,
            "amount": _safe_decimal(amount),
            "notes": notes or exception_type.replace("_", " "),
            "metadata": metadata or {},
            "createdby": created_by,
            "resolvedby": None,
            "resolved_at": None,
        },
    )
    BankReconciliationAuditLog.objects.create(
        session=session,
        action="exception_recorded",
        actor=created_by,
        payload={
            "statement_line_id": statement_line.id,
            "exception_type": exception_type,
            "amount": f"{exception_item.amount:.2f}",
        },
    )
    return exception_item


@transaction.atomic
def lock_session(*, session: BankReconciliationSession, created_by=None, force: bool = False) -> BankReconciliationSession:
    summary = build_reconciliation_summary(session)
    if not force and summary["unresolved_line_count"]:
        raise ValueError("Cannot lock session while unresolved rows remain. Use force to override.")
    session.status = BankReconciliationSession.Status.LOCKED
    session.save(update_fields=["status", "updated_at"])
    BankReconciliationAuditLog.objects.create(
        session=session,
        action="session_locked",
        actor=created_by,
        payload={"force": force, "summary": summary},
    )
    return session


@transaction.atomic
def create_session(*, entity, payload: dict[str, object], created_by=None) -> BankReconciliationSession:
    session = BankReconciliationSession.objects.create(
        entity=entity,
        entityfin_id=payload.get("entityfinid") or None,
        subentity_id=payload.get("subentity") or None,
        bank_account_id=payload["bank_account"],
        statement_label=payload.get("statement_label") or "",
        source_name=payload.get("source_name") or "",
        source_format=payload.get("source_format") or "manual",
        date_from=payload.get("date_from"),
        date_to=payload.get("date_to"),
        statement_opening_balance=payload.get("statement_opening_balance") or ZERO,
        statement_closing_balance=payload.get("statement_closing_balance") or ZERO,
        book_opening_balance=payload.get("book_opening_balance") or ZERO,
        book_closing_balance=payload.get("book_closing_balance") or ZERO,
        notes=payload.get("notes") or "",
        metadata=payload.get("metadata") or {},
        createdby=created_by,
    )
    BankReconciliationAuditLog.objects.create(
        session=session,
        action="session_created",
        actor=created_by,
        payload={"entity_id": entity.id, "bank_account_id": session.bank_account_id},
    )
    return session


@transaction.atomic
def import_statement_rows(*, session: BankReconciliationSession, rows: list[dict[str, object]], created_by=None, source_name: str = "", source_format: str = "json") -> BankStatementBatch:
    return import_statement_rows_with_mapping(
        session=session,
        rows=rows,
        created_by=created_by,
        source_name=source_name,
        source_format=source_format,
        column_mapping=None,
    )


@transaction.atomic
def import_statement_rows_with_mapping(
    *,
    session: BankReconciliationSession,
    rows: list[dict[str, object]],
    created_by=None,
    source_name: str = "",
    source_format: str = "json",
    column_mapping: dict[str, str] | None = None,
) -> BankStatementBatch:
    batch = BankStatementBatch.objects.create(
        session=session,
        source_name=source_name or session.source_name or "Statement Import",
        source_format=source_format or "json",
        raw_payload=rows,
        imported_row_count=len(rows),
        importedby=created_by,
    )

    seen_hashes: set[str] = set()
    duplicates = 0
    for idx, row in enumerate(rows, start=1):
        normalized = normalize_statement_row(row, idx, mapping=column_mapping)
        row_hash = normalized["row_hash"]
        if row_hash in seen_hashes:
            duplicates += 1
            continue
        seen_hashes.add(row_hash)
        BankStatementLine.objects.create(
            batch=batch,
            line_no=idx,
            transaction_date=normalized["transaction_date"],
            value_date=normalized["value_date"],
            description=normalized["description"],
            reference_number=normalized["reference_number"],
            counterparty=normalized["counterparty"],
            debit_amount=normalized["debit_amount"],
            credit_amount=normalized["credit_amount"],
            balance_amount=normalized["balance_amount"],
            currency=normalized["currency"],
            external_id=normalized["external_id"],
            row_hash=row_hash,
            match_status=normalized["match_status"],
            suggested_match_score=normalized["suggested_match_score"],
            metadata=normalized["metadata"],
        )

    batch.duplicate_row_count = duplicates
    batch.save(update_fields=["duplicate_row_count", "updated_at"])
    session.source_name = batch.source_name
    session.source_format = batch.source_format
    session.status = BankReconciliationSession.Status.IMPORTED if batch.imported_row_count else BankReconciliationSession.Status.DRAFT
    session.save(update_fields=["source_name", "source_format", "status", "updated_at"])
    BankReconciliationAuditLog.objects.create(
        session=session,
        action="statement_imported",
        actor=created_by,
        payload={"batch_id": batch.id, "row_count": batch.imported_row_count, "duplicate_row_count": duplicates},
    )
    recalculate_session_metrics(session)
    return batch


@transaction.atomic
def import_statement_file(
    *,
    session: BankReconciliationSession,
    file_data: bytes,
    source_format: str,
    created_by=None,
    source_name: str = "",
    notes: str = "",
    metadata: dict[str, object] | None = None,
    column_mapping: dict[str, str] | None = None,
    delimiter: str = ",",
    statement_opening_balance=None,
    statement_closing_balance=None,
    book_opening_balance=None,
    book_closing_balance=None,
) -> BankStatementBatch:
    rows = parse_statement_file(file_data, source_format, delimiter=delimiter)
    batch = import_statement_rows_with_mapping(
        session=session,
        rows=rows,
        created_by=created_by,
        source_name=source_name or session.source_name,
        source_format=source_format,
        column_mapping=column_mapping,
    )
    if statement_opening_balance is not None:
        session.statement_opening_balance = statement_opening_balance
    if statement_closing_balance is not None:
        session.statement_closing_balance = statement_closing_balance
    if book_opening_balance is not None:
        session.book_opening_balance = book_opening_balance
    if book_closing_balance is not None:
        session.book_closing_balance = book_closing_balance
    if notes:
        session.notes = notes
    session.metadata = {**(session.metadata or {}), **(metadata or {}), "last_upload_batch_id": batch.id}
    session.save(
        update_fields=[
            "statement_opening_balance",
            "statement_closing_balance",
            "book_opening_balance",
            "book_closing_balance",
            "notes",
            "metadata",
            "updated_at",
        ]
    )
    recalculate_session_metrics(session)
    return batch


def list_import_profiles(*, entity, bank_account=None, source_format: str | None = None):
    profiles = BankStatementImportProfile.objects.filter(entity=entity, is_active=True)
    if bank_account:
        profiles = profiles.filter(Q(bank_account=bank_account) | Q(bank_account__isnull=True))
    if source_format:
        profiles = profiles.filter(source_format=source_format)
    return profiles.order_by("name", "id")


@transaction.atomic
def save_import_profile(*, entity, payload: dict[str, object], created_by=None) -> BankStatementImportProfile:
    profile = BankStatementImportProfile.objects.create(
        entity=entity,
        bank_account_id=payload.get("bank_account") or None,
        name=payload["name"],
        source_format=payload.get("source_format") or BankStatementImportProfile.SourceFormat.CSV,
        delimiter=payload.get("delimiter") or ",",
        date_format=payload.get("date_format") or "",
        column_mapping=payload.get("column_mapping") or {},
        is_active=payload.get("is_active", True),
        createdby=created_by,
    )
    return profile


def serialize_import_profile(profile: BankStatementImportProfile) -> dict[str, object]:
    return {
        "id": profile.id,
        "name": profile.name,
        "entity_id": profile.entity_id,
        "bank_account_id": profile.bank_account_id,
        "source_format": profile.source_format,
        "delimiter": profile.delimiter,
        "date_format": profile.date_format,
        "column_mapping": profile.column_mapping,
        "is_active": profile.is_active,
        "created_at": _iso_date(profile.created_at),
    }
