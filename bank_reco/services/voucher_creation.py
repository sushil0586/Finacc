from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from financial.models import account
from posting.models import JournalLine, TxnType
from vouchers.models.voucher_core import VoucherHeader
from vouchers.services.voucher_service import VoucherService

from ..models import (
    ZERO,
    BankReconciliationAuditLog,
    BankReconciliationMatch,
    BankReconciliationRun,
    BankStatementLine,
)
from .matching import (
    _bank_direction,
    _statement_amount,
    confirm_manual_match,
    get_run_bank_lines,
    resolve_bank_book_binding,
)


VOUCHER_KIND_LABELS = {
    "bank_charges": "Bank charges",
    "interest_received": "Interest received",
    "direct_customer_receipt": "Direct customer receipt",
    "direct_vendor_payment": "Direct vendor payment",
    "bank_transfer": "Bank transfer",
    "loan_emi": "Loan EMI",
    "gst_payment": "GST payment",
    "tds_payment": "TDS payment",
    "tcs_payment": "TCS payment",
    "cheque_bounce": "Cheque bounce",
    "reversal_adjustment": "Reversal adjustment",
}


def _audit(*, run: BankReconciliationRun, bank_line: BankStatementLine, actor, old_status: str | None, new_status: str | None, action: str, metadata: dict):
    BankReconciliationAuditLog.objects.create(
        run=run,
        statement_import=run.statement_import,
        action=action,
        object_type="statement_line",
        object_id=str(bank_line.id),
        payload={
            "old_status": old_status,
            "new_status": new_status,
            **metadata,
        },
        actor=actor,
    )


def _resolve_cash_bank_account(*, run: BankReconciliationRun):
    binding = resolve_bank_book_binding(entity=run.entity, bank_account=run.bank_account, metadata=run.metadata)
    if not binding.account_ids:
        raise ValidationError(
            {
                "bank_account": (
                    "This reconciliation bank account does not resolve to a concrete book account that can be used "
                    "for bank vouchers. Add or correct the bank-to-book account mapping first."
                )
            }
        )
    account_id = sorted(binding.account_ids)[0]
    return account.objects.select_related("ledger").get(pk=account_id, entity=run.entity)


def _validate_counterpart_account(*, run: BankReconciliationRun, counterpart_account_id: int):
    row = account.objects.filter(id=counterpart_account_id, entity=run.entity, isactive=True).select_related("ledger").first()
    if row is None:
        raise ValidationError({"counterpart_account_id": "Counterpart account is not valid for this entity."})
    return row


def _build_voucher_lines(*, bank_line: BankStatementLine, allocations: list[dict], narration: str):
    amount = _statement_amount(bank_line)
    if amount <= ZERO:
        raise ValidationError({"bank_line_id": "Selected bank line does not have a valid debit or credit amount."})
    business_entry_type = "CR" if _bank_direction(bank_line) == "credit" else "DR"
    total_allocated = ZERO
    lines = []
    for allocation in allocations:
        line_amount = Decimal(str(allocation["amount"]))
        if line_amount <= ZERO:
            raise ValidationError({"allocations": "Each split allocation must have a positive amount."})
        total_allocated += line_amount
        lines.append(
            {
                "account": allocation["counterpart_account_id"],
                "entry_type": business_entry_type,
                "amount": line_amount,
                "narration": allocation.get("narration") or narration,
            }
        )
    if total_allocated != amount:
        raise ValidationError(
            {
                "allocations": (
                    f"Split allocation total {total_allocated} must match the bank-line amount {amount}."
                )
            }
        )
    return lines


def _normalize_allocations(
    *,
    run: BankReconciliationRun,
    counterpart_account_id: int,
    allocations: list[dict] | None,
    bank_line: BankStatementLine,
):
    if allocations:
        normalized = []
        for allocation in allocations:
            counterpart = _validate_counterpart_account(
                run=run,
                counterpart_account_id=allocation["counterpart_account_id"],
            )
            normalized.append(
                {
                    "counterpart_account_id": counterpart.id,
                    "amount": allocation["amount"],
                    "narration": (allocation.get("narration") or "").strip(),
                    "account": counterpart,
                }
            )
        return normalized

    counterpart = _validate_counterpart_account(run=run, counterpart_account_id=counterpart_account_id)
    return [
        {
            "counterpart_account_id": counterpart.id,
            "amount": _statement_amount(bank_line),
            "narration": "",
            "account": counterpart,
        }
    ]


def _ensure_posted_voucher(*, header: VoucherHeader, actor_id: int | None) -> VoucherHeader:
    current = header
    if int(current.status) == int(VoucherHeader.Status.DRAFT):
        current = VoucherService.confirm_voucher(current.id, confirmed_by_id=actor_id).header
    if int(current.status) == int(VoucherHeader.Status.CONFIRMED):
        current = VoucherService.post_voucher(current.id, posted_by_id=actor_id).header
    if int(current.status) != int(VoucherHeader.Status.POSTED):
        raise ValidationError(
            {
                "voucher": (
                    "Voucher was created but could not be posted through the configured voucher workflow. "
                    "Review voucher maker-checker and posting policies for this entity/subentity."
                )
            }
        )
    return current


def _find_posted_bank_journal_line(*, run: BankReconciliationRun, voucher: VoucherHeader, cash_bank_account_id: int, bank_line: BankStatementLine):
    queryset = JournalLine.objects.select_related("entry").filter(
        entity=run.entity,
        entityfin=run.entityfin,
        txn_type=TxnType.JOURNAL_BANK,
        txn_id=voucher.id,
        account_id=cash_bank_account_id,
    )
    expected_drcr = _bank_direction(bank_line) == "credit"
    expected_amount = _statement_amount(bank_line)
    line = queryset.filter(drcr=expected_drcr, amount=expected_amount).order_by("id").first()
    if line is None:
        line = queryset.order_by("id").first()
    if line is None:
        raise ValidationError(
            {
                "voucher": (
                    "The voucher was posted but the bank-side journal line could not be located for reconciliation. "
                    "Review voucher posting output for this voucher."
                )
            }
        )
    return line


@transaction.atomic
def create_voucher_from_bank_line(
    *,
    run: BankReconciliationRun,
    bank_line_id: int,
    voucher_kind: str,
    counterpart_account_id: int,
    allocations: list[dict] | None = None,
    actor,
    voucher_date=None,
    reference_number: str = "",
    narration: str = "",
    instrument_no: str = "",
    instrument_date=None,
    audit_context: dict | None = None,
):
    bank_line = get_run_bank_lines(run=run, bank_line_ids=[bank_line_id])[0]
    if bank_line.reconciliation_status in {
        BankStatementLine.ReconciliationStatus.CONFIRMED,
        BankStatementLine.ReconciliationStatus.PARTIALLY_MATCHED,
    }:
        raise ValidationError({"bank_line_id": "A voucher cannot be created from a bank line that is already matched."})
    if bank_line.created_voucher_id:
        existing = bank_line.created_voucher
        if existing and int(existing.status) != int(VoucherHeader.Status.CANCELLED):
            raise ValidationError(
                {
                    "bank_line_id": (
                        f"A voucher ({existing.voucher_code or existing.id}) has already been created from this bank line. "
                        "Cancel that voucher before creating another one."
                    )
                }
            )

    cash_bank_account = _resolve_cash_bank_account(run=run)
    voucher_narration = (
        narration.strip()
        or f"{VOUCHER_KIND_LABELS.get(voucher_kind, voucher_kind.replace('_', ' ').title())} from bank statement line {bank_line.line_no}"
    )
    normalized_allocations = _normalize_allocations(
        run=run,
        counterpart_account_id=counterpart_account_id,
        allocations=allocations,
        bank_line=bank_line,
    )
    lines = _build_voucher_lines(bank_line=bank_line, allocations=normalized_allocations, narration=voucher_narration)
    payload = {
        "entity": run.entity,
        "entityfinid": run.entityfin,
        "subentity": run.subentity,
        "voucher_date": voucher_date or bank_line.value_date or bank_line.txn_date or run.as_of_date,
        "voucher_type": VoucherHeader.VoucherType.BANK,
        "doc_code": "",
        "cash_bank_account": cash_bank_account,
        "reference_number": (reference_number or bank_line.reference_no or bank_line.cheque_no or "").strip() or None,
        "narration": voucher_narration,
        "instrument_no": (instrument_no or bank_line.cheque_no or "").strip() or None,
        "instrument_date": instrument_date,
        "lines": lines,
    }
    try:
        voucher_result = VoucherService.create_voucher(data=payload, created_by_id=getattr(actor, "id", None))
        voucher_header = _ensure_posted_voucher(header=voucher_result.header, actor_id=getattr(actor, "id", None))
    except ValueError as exc:
        raise ValidationError({"voucher": str(exc)}) from exc

    journal_line = _find_posted_bank_journal_line(
        run=run,
        voucher=voucher_header,
        cash_bank_account_id=cash_bank_account.id,
        bank_line=bank_line,
    )
    old_status = bank_line.reconciliation_status
    bank_line.created_voucher = voucher_header
    bank_line.exception_status = BankStatementLine.ExceptionStatus.NONE
    bank_line.exception_reason = ""
    bank_line.metadata = {
        **(bank_line.metadata or {}),
        "voucher_kind": voucher_kind,
        "voucher_id": voucher_header.id,
        "voucher_code": voucher_header.voucher_code,
        "counterpart_account_id": normalized_allocations[0]["counterpart_account_id"],
        "allocations": [
            {
                "counterpart_account_id": allocation["counterpart_account_id"],
                "amount": str(allocation["amount"]),
                "narration": allocation.get("narration") or "",
            }
            for allocation in normalized_allocations
        ],
    }
    bank_line.save(update_fields=["created_voucher", "exception_status", "exception_reason", "metadata", "updated_at"])

    match = confirm_manual_match(
        run=run,
        bank_lines=[bank_line],
        journal_lines=[journal_line],
        actor=actor,
        notes=f"Auto-matched after voucher creation ({voucher_kind}).",
    )
    _audit(
        run=run,
        bank_line=bank_line,
        actor=actor,
        old_status=old_status,
        new_status=bank_line.reconciliation_status,
        action="voucher_created_from_bank_line",
        metadata={
            "voucher_kind": voucher_kind,
            "voucher_id": voucher_header.id,
            "voucher_code": voucher_header.voucher_code,
            "match_id": match.id,
            "counterpart_account_id": normalized_allocations[0]["counterpart_account_id"],
            "allocations": [
                {
                    "counterpart_account_id": allocation["counterpart_account_id"],
                    "amount": str(allocation["amount"]),
                    "narration": allocation.get("narration") or "",
                }
                for allocation in normalized_allocations
            ],
            "old_values": {
                "created_voucher_id": None,
                "exception_status": BankStatementLine.ExceptionStatus.NONE,
            },
            "new_values": {
                "created_voucher_id": voucher_header.id,
                "exception_status": bank_line.exception_status,
                "match_id": match.id,
            },
            "request_context": audit_context or {},
        },
    )
    return {
        "voucher_id": voucher_header.id,
        "voucher_code": voucher_header.voucher_code,
        "voucher_status": voucher_header.status,
        "match_id": match.id,
        "match_status": match.status,
    }
