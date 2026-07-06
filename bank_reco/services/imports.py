from __future__ import annotations

import csv
import hashlib
import json
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO, StringIO

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from entity.models import EntityBankAccountV2

from ..models import BankReconciliationAuditLog, BankReconciliationRun, BankStatementImport, BankStatementLine, ZERO


CSV_DELIMITER_CANDIDATES = (",", ";", "\t", "|")
CANONICAL_IMPORT_FIELDS = {
    "txn_date": ("txn_date", "transaction_date", "date", "txn date", "transaction date"),
    "value_date": ("value_date", "value dt", "value_dt", "value date"),
    "narration": ("narration", "description", "particulars", "remarks", "narrative"),
    "reference_no": ("reference_no", "reference", "reference_number", "utr", "txn_ref", "ref no", "utr number"),
    "cheque_no": ("cheque_no", "cheque", "chq_no", "cheque number", "instrument_no"),
    "debit_amount": ("debit_amount", "debit", "withdrawal", "dr", "debit amt", "debit amount"),
    "credit_amount": ("credit_amount", "credit", "deposit", "cr", "credit amt", "credit amount"),
    "balance": ("balance", "balance_amount", "closing_balance", "running balance"),
    "currency": ("currency", "ccy"),
}
DEBIT_HEADER_TOKENS = ("debit", "withdrawal", "dr")
CREDIT_HEADER_TOKENS = ("credit", "deposit", "cr")


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


def detect_csv_delimiter(data: bytes, preferred: str = ",") -> str:
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
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels.findall(f"{namespace_pkg}Relationship")}
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


def parse_statement_file(data: bytes, file_type: str, delimiter: str = ",") -> tuple[list[dict[str, object]], str]:
    normalized = str(file_type or "").strip().lower()
    if normalized == "csv":
        resolved_delimiter = detect_csv_delimiter(data, delimiter)
        return _parse_csv_rows(data, delimiter=resolved_delimiter), resolved_delimiter
    if normalized == "xlsx":
        return _parse_xlsx_rows(data), ""
    raise ValidationError({"file": f"Unsupported statement format: {file_type}"})


def _safe_decimal(value) -> Decimal:
    text = str(value or "").strip().replace(",", "")
    if text in {"", "-", "None", "null"}:
        return ZERO
    try:
        return Decimal(text)
    except Exception:
        return ZERO


def _safe_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _pick(row: dict[str, object], *candidates: str):
    normalized = {str(key).strip().lower(): value for key, value in row.items()}
    for candidate in candidates:
        key = candidate.strip().lower()
        if key in normalized and normalized[key] not in (None, ""):
            return normalized[key]
    return None


def _normalize_header(value: object) -> str:
    return str(value or "").strip().lower().replace("-", " ").replace("_", " ")


def _build_column_lookup(row: dict[str, object]) -> dict[str, str]:
    return {_normalize_header(key): key for key in row.keys()}


def _resolve_mapped_value(row: dict[str, object], lookup: dict[str, str], source_name: str | None):
    if not source_name:
        return None
    direct = row.get(source_name)
    if direct not in (None, ""):
        return direct
    resolved_key = lookup.get(_normalize_header(source_name))
    return row.get(resolved_key) if resolved_key else None


def _resolve_column_mapping(headers: list[str], column_map: dict[str, str] | None = None) -> tuple[dict[str, str | None], list[str], list[str]]:
    normalized_headers = {_normalize_header(header): header for header in headers if str(header or "").strip()}
    resolved: dict[str, str | None] = {}
    warnings: list[str] = []
    errors: list[str] = []
    requested_map = column_map or {}
    for field, aliases in CANONICAL_IMPORT_FIELDS.items():
        mapped_header = requested_map.get(field)
        if mapped_header:
            header_name = normalized_headers.get(_normalize_header(mapped_header))
            if not header_name:
                errors.append(f"Mapped column '{mapped_header}' for {field} was not found in the file headers.")
            resolved[field] = header_name
            continue
        resolved[field] = next((normalized_headers.get(_normalize_header(alias)) for alias in aliases if normalized_headers.get(_normalize_header(alias))), None)

    missing_amount_columns = not resolved.get("debit_amount") and not resolved.get("credit_amount")
    if not resolved.get("txn_date"):
        errors.append("Transaction date column is required before statement import can continue.")
    if missing_amount_columns:
        errors.append("At least one debit or credit amount column is required before statement import can continue.")

    debit_header = _normalize_header(resolved.get("debit_amount"))
    credit_header = _normalize_header(resolved.get("credit_amount"))
    if debit_header and any(token in debit_header for token in CREDIT_HEADER_TOKENS):
        warnings.append("The selected debit column looks like a credit/deposit column. Review the mapping before import.")
    if credit_header and any(token in credit_header for token in DEBIT_HEADER_TOKENS):
        warnings.append("The selected credit column looks like a debit/withdrawal column. Review the mapping before import.")
    return resolved, warnings, errors


def preview_statement_file(*, data: bytes, file_type: str, delimiter: str = ",", column_map: dict[str, str] | None = None) -> dict[str, object]:
    rows, resolved_delimiter = parse_statement_file(data, file_type=file_type, delimiter=delimiter)
    headers = list(rows[0].keys()) if rows else []
    resolved_map, mapping_warnings, mapping_errors = _resolve_column_mapping(headers, column_map)
    sample_rows = rows[:10]
    preview_rows = []
    if not mapping_errors:
        preview_rows = [_normalize_row(row, column_map=resolved_map) for row in sample_rows]
    return {
        "headers": headers,
        "resolved_delimiter": resolved_delimiter,
        "suggested_column_map": {key: value for key, value in resolved_map.items() if value},
        "mapping_warnings": mapping_warnings,
        "mapping_errors": mapping_errors,
        "sample_rows": sample_rows,
        "normalized_preview_rows": preview_rows,
        "detected_file_type": str(file_type or "").lower(),
    }


def _normalize_row(row: dict[str, object], *, column_map: dict[str, str] | None = None) -> dict[str, object]:
    lookup = _build_column_lookup(row)
    column_map = column_map or {}

    def pick_field(field: str, *fallbacks: str):
        mapped = _resolve_mapped_value(row, lookup, column_map.get(field))
        if mapped not in (None, ""):
            return mapped
        return _pick(row, *fallbacks)

    debit = _safe_decimal(pick_field("debit_amount", "debit_amount", "debit", "withdrawal", "dr"))
    credit = _safe_decimal(pick_field("credit_amount", "credit_amount", "credit", "deposit", "cr"))
    balance_value = pick_field("balance", "balance", "balance_amount", "closing_balance")
    normalized = {
        "txn_date": _safe_date(pick_field("txn_date", "txn_date", "transaction_date", "date")),
        "value_date": _safe_date(pick_field("value_date", "value_date", "value dt", "value_dt")),
        "narration": str(pick_field("narration", "narration", "description", "particulars", "remarks") or "").strip(),
        "reference_no": str(pick_field("reference_no", "reference_no", "reference", "reference_number", "utr", "txn_ref") or "").strip(),
        "cheque_no": str(pick_field("cheque_no", "cheque_no", "cheque", "chq_no") or "").strip(),
        "debit_amount": debit,
        "credit_amount": credit,
        "balance": _safe_decimal(balance_value) if balance_value not in (None, "") else None,
        "currency": str(pick_field("currency", "currency", "ccy") or "INR").strip().upper() or "INR",
        "raw_data": row,
    }
    normalized["normalized_hash"] = hashlib.sha256(
        json.dumps(
            {
                "txn_date": str(normalized["txn_date"] or ""),
                "value_date": str(normalized["value_date"] or ""),
                "narration": normalized["narration"],
                "reference_no": normalized["reference_no"],
                "cheque_no": normalized["cheque_no"],
                "debit_amount": str(normalized["debit_amount"]),
                "credit_amount": str(normalized["credit_amount"]),
                "balance": str(normalized["balance"]) if normalized["balance"] is not None else "",
                "currency": normalized["currency"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return normalized


def _validate_normalized_row_lengths(normalized: dict[str, object], *, line_no: int) -> None:
    field_limits = {
        "narration": 500,
        "reference_no": 120,
        "cheque_no": 80,
        "currency": 10,
    }
    errors: list[str] = []
    for field, limit in field_limits.items():
        value = str(normalized.get(field) or "").strip()
        if len(value) > limit:
            errors.append(f"Line {line_no}: {field} may not exceed {limit} characters.")
    if errors:
        raise ValidationError({"rows": errors})


def _statement_opening_from_line(line: BankStatementLine) -> Decimal | None:
    if line.balance is None:
        return None
    return line.balance - (line.credit_amount or ZERO) + (line.debit_amount or ZERO)


def _account_suffix(value: str | None) -> str:
    text = str(value or "").strip()
    return text[-4:] if len(text) >= 4 else text


def _money_text(value: Decimal | None) -> str:
    return str(value if value is not None else ZERO)


@transaction.atomic
def import_statement_upload(
    *,
    entity,
    entityfin,
    subentity,
    bank_account: EntityBankAccountV2,
    uploaded_file,
    file_type: str,
    uploaded_by,
    parser_key: str = "",
    delimiter: str = ",",
    statement_from=None,
    statement_to=None,
    opening_balance: Decimal = ZERO,
    closing_balance: Decimal = ZERO,
    metadata: dict | None = None,
    column_map: dict[str, str] | None = None,
):
    blob = uploaded_file.read()
    source_hash = hashlib.sha256(blob).hexdigest()
    if BankStatementImport.objects.filter(entity=entity, bank_account=bank_account, source_file_sha256=source_hash).exists():
        raise ValidationError({"file": "This bank statement file has already been imported for the selected bank account."})
    if statement_from and statement_to and BankStatementImport.objects.filter(
        entity=entity,
        bank_account=bank_account,
        statement_from=statement_from,
        statement_to=statement_to,
    ).exclude(status=BankStatementImport.Status.ARCHIVED).exists():
        raise ValidationError({"statement_period": "A statement import already exists for the same statement period and bank account."})

    preview = preview_statement_file(data=blob, file_type=file_type, delimiter=delimiter, column_map=column_map)
    if preview["mapping_errors"]:
        raise ValidationError({"column_map": preview["mapping_errors"]})
    rows, resolved_delimiter = parse_statement_file(blob, file_type=file_type, delimiter=delimiter)
    statement_import = BankStatementImport.objects.create(
        entity=entity,
        entityfin=entityfin,
        subentity=subentity,
        bank_account=bank_account,
        source_file_name=getattr(uploaded_file, "name", "") or "",
        source_file_type=file_type,
        source_file_sha256=source_hash,
        parser_key=parser_key or file_type,
        statement_from=statement_from,
        statement_to=statement_to,
        opening_balance=opening_balance or ZERO,
        closing_balance=closing_balance or ZERO,
        imported_line_count=len(rows),
        metadata={
            **(metadata or {}),
            "resolved_delimiter": resolved_delimiter,
            "column_map": preview["suggested_column_map"],
            "mapping_warnings": preview["mapping_warnings"],
        },
        uploaded_by=uploaded_by,
    )

    normalized_lines: list[BankStatementLine] = []
    for index, row in enumerate(rows, start=1):
        normalized_row = _normalize_row(row, column_map=preview["suggested_column_map"])
        _validate_normalized_row_lengths(normalized_row, line_no=index)
        normalized_lines.append(
            BankStatementLine(
                statement_import=statement_import,
                line_no=index,
                **normalized_row,
            )
        )

    BankStatementLine.objects.bulk_create(normalized_lines)

    BankReconciliationAuditLog.objects.create(
        run=None,
        statement_import=statement_import,
        action="import_created",
        object_type="statement_import",
        object_id=str(statement_import.id),
        payload={
            "line_count": len(rows),
            "source_file_name": statement_import.source_file_name,
            "statement_from": str(statement_import.statement_from or ""),
            "statement_to": str(statement_import.statement_to or ""),
            "column_map": preview["suggested_column_map"],
            "mapping_warnings": preview["mapping_warnings"],
        },
        actor=uploaded_by,
    )
    return statement_import


@transaction.atomic
def validate_statement_import(*, statement_import: BankStatementImport, actor=None, audit_context: dict | None = None) -> BankStatementImport:
    lines = list(statement_import.lines.order_by("line_no"))
    duplicates_in_file = Counter(line.normalized_hash for line in lines if line.normalized_hash)
    import_errors: list[str] = []
    import_warnings: list[str] = []

    overlap_exists = False
    if statement_import.statement_from and statement_import.statement_to:
        overlap_exists = BankStatementImport.objects.filter(
            entity=statement_import.entity,
            bank_account=statement_import.bank_account,
        ).exclude(pk=statement_import.pk).filter(
            statement_from__lte=statement_import.statement_to,
            statement_to__gte=statement_import.statement_from,
        ).exists()
        if overlap_exists:
            import_warnings.append("Statement period overlaps with an existing import for this bank account.")

    declared_account_number = str((statement_import.metadata or {}).get("statement_account_number") or "").strip()
    if declared_account_number and _account_suffix(declared_account_number) != _account_suffix(statement_import.bank_account.account_number):
        import_errors.append("Statement account number does not match the selected bank account.")

    if lines:
        first_line = next((line for line in lines if line.balance is not None), None)
        last_line = next((line for line in reversed(lines) if line.balance is not None), None)
        expected_opening = _statement_opening_from_line(first_line) if first_line else None
        if expected_opening is not None and statement_import.opening_balance is not None and expected_opening != statement_import.opening_balance:
            import_errors.append(
                "Opening balance mismatch: you entered "
                f"{_money_text(statement_import.opening_balance)}, but the first statement line implies "
                f"{_money_text(expected_opening)} (line {first_line.line_no} balance "
                f"{_money_text(first_line.balance)} with debit {_money_text(first_line.debit_amount)} "
                f"and credit {_money_text(first_line.credit_amount)})."
            )
        if last_line and last_line.balance is not None and statement_import.closing_balance is not None and last_line.balance != statement_import.closing_balance:
            import_errors.append(
                "Closing balance mismatch: you entered "
                f"{_money_text(statement_import.closing_balance)}, but the last statement line ends at "
                f"{_money_text(last_line.balance)} (line {last_line.line_no})."
            )

    existing_hashes = set(
        BankStatementLine.objects.filter(
            statement_import__entity=statement_import.entity,
            statement_import__bank_account=statement_import.bank_account,
            normalized_hash__in=[line.normalized_hash for line in lines if line.normalized_hash],
        )
        .exclude(statement_import=statement_import)
        .values_list("normalized_hash", flat=True)
    )

    invalid_count = 0
    warning_count = 0
    duplicate_count = 0

    for line in lines:
        errors: list[str] = []
        warnings: list[str] = []
        debit_amount = line.debit_amount or ZERO
        credit_amount = line.credit_amount or ZERO

        if debit_amount > ZERO and credit_amount > ZERO:
            errors.append("Both debit and credit amounts are populated on the same line.")
        if debit_amount <= ZERO and credit_amount <= ZERO:
            errors.append("Either debit amount or credit amount is required on the line.")
        if debit_amount < ZERO or credit_amount < ZERO:
            errors.append("Negative debit/credit amounts are not allowed in normalized statement lines.")
        if duplicates_in_file.get(line.normalized_hash, 0) > 1:
            duplicate_count += 1
            warnings.append("This statement line appears more than once in the imported file.")
        if line.normalized_hash in existing_hashes:
            warnings.append("A similar statement line already exists in another import for this bank account.")
        if statement_import.statement_from and line.txn_date and line.txn_date < statement_import.statement_from:
            warnings.append("Transaction date is earlier than the declared statement period.")
        if statement_import.statement_to and line.txn_date and line.txn_date > statement_import.statement_to:
            warnings.append("Transaction date is later than the declared statement period.")

        if errors:
            line.validation_status = BankStatementLine.ValidationStatus.INVALID
            invalid_count += 1
        elif warnings:
            line.validation_status = BankStatementLine.ValidationStatus.WARNING
            warning_count += 1
        else:
            line.validation_status = BankStatementLine.ValidationStatus.VALID
        line.validation_errors = errors
        line.validation_warnings = warnings
        line.save(update_fields=["validation_status", "validation_errors", "validation_warnings", "updated_at"])

    statement_import.duplicate_line_count = duplicate_count
    statement_import.invalid_line_count = invalid_count
    statement_import.warning_count = warning_count + len(import_warnings)
    statement_import.validation_summary = {
        "import_errors": import_errors,
        "import_warnings": import_warnings,
        "line_summary": {
            "total": len(lines),
            "valid": sum(1 for line in lines if line.validation_status == BankStatementLine.ValidationStatus.VALID),
            "warning": sum(1 for line in lines if line.validation_status == BankStatementLine.ValidationStatus.WARNING),
            "invalid": sum(1 for line in lines if line.validation_status == BankStatementLine.ValidationStatus.INVALID),
        },
        "overlap_detected": overlap_exists,
        "existing_duplicate_hash_count": len(existing_hashes),
    }
    statement_import.status = (
        BankStatementImport.Status.REJECTED
        if import_errors or invalid_count
        else BankStatementImport.Status.VALIDATED
    )
    statement_import.validated_by = actor
    statement_import.validated_at = timezone.now()
    statement_import.save(
        update_fields=[
            "duplicate_line_count",
            "invalid_line_count",
            "warning_count",
            "validation_summary",
            "status",
            "validated_by",
            "validated_at",
            "updated_at",
        ]
    )

    BankReconciliationAuditLog.objects.create(
        run=None,
        statement_import=statement_import,
        action="import_validated",
        object_type="statement_import",
        object_id=str(statement_import.id),
        payload={
            **(statement_import.validation_summary or {}),
            "request_context": audit_context or {},
        },
        actor=actor,
    )
    return statement_import


@transaction.atomic
def revise_statement_import(
    *,
    statement_import: BankStatementImport,
    actor=None,
    audit_context: dict | None = None,
    statement_from=None,
    statement_to=None,
    opening_balance: Decimal | None = None,
    closing_balance: Decimal | None = None,
    declared_account_number: str | None = None,
) -> BankStatementImport:
    if statement_import.status == BankStatementImport.Status.ARCHIVED:
        raise ValidationError({"import": "Archived imports cannot be revised."})
    if statement_import.reconciliation_runs.exists():
        raise ValidationError({"import": "This import already has reconciliation runs and can no longer be revised directly."})

    metadata = dict(statement_import.metadata or {})
    if declared_account_number is not None:
        metadata["statement_account_number"] = str(declared_account_number or "").strip()

    statement_import.statement_from = statement_from
    statement_import.statement_to = statement_to
    if opening_balance is not None:
        statement_import.opening_balance = opening_balance
    if closing_balance is not None:
        statement_import.closing_balance = closing_balance
    statement_import.metadata = metadata
    statement_import.status = BankStatementImport.Status.UPLOADED
    statement_import.validation_summary = {}
    statement_import.duplicate_line_count = 0
    statement_import.invalid_line_count = 0
    statement_import.warning_count = 0
    statement_import.validated_by = None
    statement_import.validated_at = None
    statement_import.save(
        update_fields=[
            "statement_from",
            "statement_to",
            "opening_balance",
            "closing_balance",
            "metadata",
            "status",
            "validation_summary",
            "duplicate_line_count",
            "invalid_line_count",
            "warning_count",
            "validated_by",
            "validated_at",
            "updated_at",
        ]
    )

    BankReconciliationAuditLog.objects.create(
        run=None,
        statement_import=statement_import,
        action="import_revised",
        object_type="statement_import",
        object_id=str(statement_import.id),
        payload={
            "statement_from": str(statement_import.statement_from or ""),
            "statement_to": str(statement_import.statement_to or ""),
            "opening_balance": str(statement_import.opening_balance),
            "closing_balance": str(statement_import.closing_balance),
            "declared_account_number": metadata.get("statement_account_number") or "",
            "request_context": audit_context or {},
        },
        actor=actor,
    )
    return statement_import


@transaction.atomic
def archive_statement_import(*, statement_import: BankStatementImport, actor=None, audit_context: dict | None = None, reason: str = "") -> BankStatementImport:
    if statement_import.status == BankStatementImport.Status.ARCHIVED:
        return statement_import
    if statement_import.reconciliation_runs.exists():
        raise ValidationError({"import": "This import already has reconciliation runs and cannot be archived."})

    statement_import.status = BankStatementImport.Status.ARCHIVED
    statement_import.save(update_fields=["status", "updated_at"])

    BankReconciliationAuditLog.objects.create(
        run=None,
        statement_import=statement_import,
        action="import_archived",
        object_type="statement_import",
        object_id=str(statement_import.id),
        payload={
            "reason": str(reason or "").strip(),
            "request_context": audit_context or {},
        },
        actor=actor,
    )
    return statement_import


def build_workspace_summary(*, entity, entityfin=None, subentity=None, bank_account=None) -> dict[str, object]:
    imports = BankStatementImport.objects.filter(entity=entity).select_related("bank_account", "entityfin", "subentity")
    if entityfin is not None:
        imports = imports.filter(entityfin=entityfin)
    if subentity is not None:
        imports = imports.filter(subentity=subentity)
    if bank_account is not None:
        imports = imports.filter(bank_account=bank_account)

    recent_import_objects = list(imports.order_by("-created_at", "-id")[:10])
    recent_imports = []
    for item in recent_import_objects:
        recent_imports.append(
            {
                "id": item.id,
                "import_code": item.import_code,
                "status": item.status,
                "source_file_name": item.source_file_name,
                "statement_from": item.statement_from,
                "statement_to": item.statement_to,
                "opening_balance": item.opening_balance,
                "closing_balance": item.closing_balance,
                "imported_line_count": item.imported_line_count,
                "duplicate_line_count": item.duplicate_line_count,
                "invalid_line_count": item.invalid_line_count,
                "warning_count": item.warning_count,
                "bank_account": {
                    "id": item.bank_account_id,
                    "bank_name": item.bank_account.bank_name,
                    "account_number_masked": f"***{item.bank_account.account_number[-4:]}",
                },
            }
        )

    current_workspace = None
    latest_import = recent_import_objects[0] if recent_import_objects else None
    if latest_import is not None:
        from .matching import build_workspace_payload

        latest_run = (
            BankReconciliationRun.objects.filter(statement_import=latest_import)
            .order_by("-created_at", "-id")
            .first()
        )
        current_workspace = build_workspace_payload(
            statement_import=latest_import,
            run=latest_run,
            summary_only=True,
            include_queues=False,
            include_matches=False,
        )

    import_counts = imports.aggregate(
        total=Count("id"),
        uploaded=Count("id", filter=Q(status=BankStatementImport.Status.UPLOADED)),
        validated=Count("id", filter=Q(status=BankStatementImport.Status.VALIDATED)),
        ready=Count("id", filter=Q(status=BankStatementImport.Status.READY)),
        rejected=Count("id", filter=Q(status=BankStatementImport.Status.REJECTED)),
        archived=Count("id", filter=Q(status=BankStatementImport.Status.ARCHIVED)),
    )
    status_counts = {
        BankStatementImport.Status.UPLOADED: import_counts["uploaded"] or 0,
        BankStatementImport.Status.VALIDATED: import_counts["validated"] or 0,
        BankStatementImport.Status.READY: import_counts["ready"] or 0,
        BankStatementImport.Status.REJECTED: import_counts["rejected"] or 0,
        BankStatementImport.Status.ARCHIVED: import_counts["archived"] or 0,
    }
    activity_scope = Q(statement_import__entity=entity) | Q(run__entity=entity)
    if entityfin is not None:
        activity_scope &= Q(statement_import__entityfin=entityfin) | Q(run__entityfin=entityfin)
    if subentity is not None:
        activity_scope &= Q(statement_import__subentity=subentity) | Q(run__subentity=subentity)
    if bank_account is not None:
        activity_scope &= Q(statement_import__bank_account=bank_account) | Q(run__bank_account=bank_account)

    recent_activity = []
    activity_queryset = (
        BankReconciliationAuditLog.objects.filter(activity_scope)
        .select_related("actor", "run__bank_account", "statement_import__bank_account")
        .order_by("-created_at", "-id")
    )
    for item in activity_queryset[:10]:
        source_bank_account = (
            getattr(item.run, "bank_account", None)
            or getattr(item.statement_import, "bank_account", None)
        )
        recent_activity.append(
            {
                "id": item.id,
                "created_at": item.created_at,
                "action": item.action,
                "object_type": item.object_type,
                "object_id": item.object_id,
                "actor": getattr(item.actor, "username", "") or getattr(item.actor, "email", "") or "",
                "run_id": item.run_id,
                "statement_import_id": item.statement_import_id,
                "bank_account": (
                    {
                        "id": source_bank_account.id,
                        "bank_name": source_bank_account.bank_name,
                        "account_number_masked": f"***{source_bank_account.account_number[-4:]}",
                    }
                    if source_bank_account is not None
                    else None
                ),
            }
        )

    return {
        "module": "bank_reco",
        "imports_count": import_counts["total"] or 0,
        "status_counts": status_counts,
        "recent_imports": recent_imports,
        "recent_activity": recent_activity,
        "current_workspace": current_workspace,
        "selected_bank_account": (
            {
                "id": bank_account.id,
                "bank_name": bank_account.bank_name,
                "account_number_masked": f"***{bank_account.account_number[-4:]}",
            }
            if bank_account is not None
            else None
        ),
    }
