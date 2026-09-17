from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from numbering.seeding import NumberingSeedService
from financial.models import account
from payments.models import PaymentVoucherHeader
from payments.services.payment_voucher_service import PaymentVoucherService
from purchase.models.purchase_ap import VendorBillOpenItem, VendorSettlement
from purchase.services.purchase_ap_service import PurchaseApService
from vouchers.models import VoucherHeader
from vouchers.services.voucher_service import VoucherService
from vouchers.services.voucher_settings_service import VoucherSettingsService

from .models import (
    TreasuryChequeBook,
    TreasuryChequeLeaf,
    TreasuryCashMovement,
    TreasuryPaymentInstrument,
    TreasuryPaymentBatch,
    TreasuryPaymentBatchLine,
    TreasuryPaymentFileExport,
    TreasuryPaymentStatusLog,
)

ZERO2 = Decimal("0.00")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
ACTIVE_BATCH_STATUSES = (
    TreasuryPaymentBatch.Status.DRAFT,
    TreasuryPaymentBatch.Status.VALIDATED,
    TreasuryPaymentBatch.Status.APPROVED,
    TreasuryPaymentBatch.Status.EXPORTED,
)


@dataclass(frozen=True)
class TreasuryPaymentExportResult:
    batch: TreasuryPaymentBatch
    export_record: TreasuryPaymentFileExport
    file_name: str
    content_type: str
    file_content: str


class TreasuryPaymentBatchService:
    INSTRUMENT_TRANSITIONS = {
        "sent-to-bank": {
            "target": TreasuryPaymentInstrument.Status.SENT_TO_BANK,
            "allowed": {
                TreasuryPaymentInstrument.Status.PREPARED,
                TreasuryPaymentInstrument.Status.EXPORTED,
                TreasuryPaymentInstrument.Status.FAILED,
                TreasuryPaymentInstrument.Status.BOUNCED,
            },
            "default_reason": "Instrument sent to bank.",
        },
        "cleared": {
            "target": TreasuryPaymentInstrument.Status.CLEARED,
            "allowed": {
                TreasuryPaymentInstrument.Status.PREPARED,
                TreasuryPaymentInstrument.Status.EXPORTED,
                TreasuryPaymentInstrument.Status.SENT_TO_BANK,
            },
            "default_reason": "Instrument cleared by bank.",
        },
        "failed": {
            "target": TreasuryPaymentInstrument.Status.FAILED,
            "allowed": {
                TreasuryPaymentInstrument.Status.PREPARED,
                TreasuryPaymentInstrument.Status.EXPORTED,
                TreasuryPaymentInstrument.Status.SENT_TO_BANK,
            },
            "default_reason": "Instrument failed.",
        },
        "bounced": {
            "target": TreasuryPaymentInstrument.Status.BOUNCED,
            "allowed": {
                TreasuryPaymentInstrument.Status.SENT_TO_BANK,
                TreasuryPaymentInstrument.Status.CLEARED,
            },
            "default_reason": "Instrument bounced.",
        },
        "stale": {
            "target": TreasuryPaymentInstrument.Status.STALE,
            "allowed": {
                TreasuryPaymentInstrument.Status.PREPARED,
                TreasuryPaymentInstrument.Status.EXPORTED,
                TreasuryPaymentInstrument.Status.SENT_TO_BANK,
            },
            "default_reason": "Instrument marked stale.",
        },
        "cancel": {
            "target": TreasuryPaymentInstrument.Status.CANCELLED,
            "allowed": {
                TreasuryPaymentInstrument.Status.PREPARED,
                TreasuryPaymentInstrument.Status.EXPORTED,
                TreasuryPaymentInstrument.Status.SENT_TO_BANK,
                TreasuryPaymentInstrument.Status.FAILED,
                TreasuryPaymentInstrument.Status.BOUNCED,
                TreasuryPaymentInstrument.Status.STALE,
            },
            "default_reason": "Instrument cancelled.",
        },
        "reverse": {
            "target": TreasuryPaymentInstrument.Status.REVERSED,
            "allowed": {
                TreasuryPaymentInstrument.Status.CLEARED,
                TreasuryPaymentInstrument.Status.BOUNCED,
                TreasuryPaymentInstrument.Status.FAILED,
            },
            "default_reason": "Instrument reversed.",
        },
        "retry": {
            "target": TreasuryPaymentInstrument.Status.PREPARED,
            "allowed": {
                TreasuryPaymentInstrument.Status.FAILED,
                TreasuryPaymentInstrument.Status.BOUNCED,
                TreasuryPaymentInstrument.Status.STALE,
                TreasuryPaymentInstrument.Status.CANCELLED,
            },
            "default_reason": "Instrument queued for retry.",
        },
        "reissue": {
            "target": TreasuryPaymentInstrument.Status.PREPARED,
            "allowed": {
                TreasuryPaymentInstrument.Status.FAILED,
                TreasuryPaymentInstrument.Status.BOUNCED,
                TreasuryPaymentInstrument.Status.STALE,
                TreasuryPaymentInstrument.Status.CANCELLED,
            },
            "default_reason": "Instrument reissued.",
        },
    }

    @classmethod
    def _generate_leaf_numbers(cls, *, start_leaf: str, end_leaf: str) -> list[str]:
        start = cls._normalize_text(start_leaf)
        end = cls._normalize_text(end_leaf)
        if not start or not end:
            raise ValueError("Start and end cheque leaf numbers are required.")
        if not start.isdigit() or not end.isdigit():
            raise ValueError("Cheque leaf range must be numeric.")
        start_number = int(start)
        end_number = int(end)
        if start_number > end_number:
            raise ValueError("Start cheque leaf cannot be greater than end cheque leaf.")
        if end_number - start_number > 999:
            raise ValueError("A cheque book can contain at most 1000 leaves.")
        width = max(len(start), len(end))
        return [str(number).zfill(width) for number in range(start_number, end_number + 1)]

    @classmethod
    @transaction.atomic
    def create_cheque_book(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int | None = None,
        subentity_id: int | None = None,
        bank_account_id: int,
        book_number: str,
        start_leaf: str,
        end_leaf: str,
        issued_on=None,
        remarks: str = "",
        user_id: int | None = None,
    ) -> TreasuryChequeBook:
        leaf_numbers = cls._generate_leaf_numbers(start_leaf=start_leaf, end_leaf=end_leaf)
        normalized_book = cls._normalize_text(book_number)
        if not normalized_book:
            raise ValueError("Cheque book number is required.")

        duplicates = list(
            TreasuryChequeLeaf.objects.filter(
                entity_id=entity_id,
                bank_account_id=bank_account_id,
                leaf_no__in=leaf_numbers,
            ).values_list("leaf_no", flat=True)[:10]
        )
        if duplicates:
            raise ValueError("Cheque leaf numbers already exist for this bank account: " + ", ".join(duplicates) + ".")

        book = TreasuryChequeBook.objects.create(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            bank_account_id=bank_account_id,
            book_number=normalized_book[:60],
            start_leaf=leaf_numbers[0],
            end_leaf=leaf_numbers[-1],
            total_leaves=len(leaf_numbers),
            issued_on=issued_on,
            remarks=cls._normalize_text(remarks)[:255],
        )
        TreasuryChequeLeaf.objects.bulk_create(
            [
                TreasuryChequeLeaf(
                    cheque_book=book,
                    entity_id=entity_id,
                    bank_account_id=bank_account_id,
                    leaf_no=leaf_no,
                )
                for leaf_no in leaf_numbers
            ]
        )
        return book

    @classmethod
    def _lock_cheque_leaf_for_instrument(
        cls,
        *,
        instrument: TreasuryPaymentInstrument,
        cheque_leaf_id=None,
        instrument_no: str = "",
    ) -> TreasuryChequeLeaf | None:
        if instrument.instrument_type != TreasuryPaymentInstrument.InstrumentType.CHEQUE:
            return None
        leaf = None
        if cheque_leaf_id:
            leaf = TreasuryChequeLeaf.objects.select_for_update().select_related("cheque_book").filter(pk=cheque_leaf_id).first()
            if leaf is None:
                raise ValueError("Selected cheque leaf was not found.")
        else:
            leaf_no = cls._normalize_text(instrument_no or instrument.instrument_no)
            if leaf_no and instrument.source_account_id:
                leaf = (
                    TreasuryChequeLeaf.objects.select_for_update()
                    .select_related("cheque_book")
                    .filter(
                        entity_id=instrument.batch.entity_id,
                        bank_account_id=instrument.source_account_id,
                        leaf_no=leaf_no,
                    )
                    .first()
                )
        if leaf is None:
            return None

        if leaf.entity_id != instrument.batch.entity_id:
            raise ValueError("Cheque leaf belongs to a different entity.")
        if instrument.source_account_id and leaf.bank_account_id != instrument.source_account_id:
            raise ValueError("Cheque leaf belongs to a different bank account.")
        if leaf.status not in {
            TreasuryChequeLeaf.Status.AVAILABLE,
            TreasuryChequeLeaf.Status.RESERVED,
            TreasuryChequeLeaf.Status.ISSUED,
        }:
            raise ValueError(f"Cheque leaf {leaf.leaf_no} is already {leaf.get_status_display()}.")

        existing_instrument_id = (
            TreasuryPaymentInstrument.objects.filter(cheque_leaf=leaf)
            .exclude(pk=instrument.pk)
            .values_list("id", flat=True)
            .first()
        )
        if existing_instrument_id:
            raise ValueError(f"Cheque leaf {leaf.leaf_no} is already linked to another payment instrument.")
        return leaf

    @classmethod
    def _sync_cheque_leaf_status(
        cls,
        *,
        instrument: TreasuryPaymentInstrument,
        target_status: str,
        action: str,
        cheque_leaf: TreasuryChequeLeaf | None = None,
        user_id: int | None = None,
        reason: str = "",
    ) -> TreasuryChequeLeaf | None:
        leaf = cheque_leaf or getattr(instrument, "cheque_leaf", None)
        if leaf is None:
            return None
        now = timezone.now()
        status_map = {
            TreasuryPaymentInstrument.Status.PREPARED: TreasuryChequeLeaf.Status.RESERVED,
            TreasuryPaymentInstrument.Status.EXPORTED: TreasuryChequeLeaf.Status.ISSUED,
            TreasuryPaymentInstrument.Status.SENT_TO_BANK: TreasuryChequeLeaf.Status.ISSUED,
            TreasuryPaymentInstrument.Status.CLEARED: TreasuryChequeLeaf.Status.CLEARED,
            TreasuryPaymentInstrument.Status.BOUNCED: TreasuryChequeLeaf.Status.BOUNCED,
            TreasuryPaymentInstrument.Status.CANCELLED: TreasuryChequeLeaf.Status.CANCELLED,
            TreasuryPaymentInstrument.Status.STALE: TreasuryChequeLeaf.Status.STALE,
            TreasuryPaymentInstrument.Status.REVERSED: TreasuryChequeLeaf.Status.CANCELLED,
        }
        leaf.status = status_map.get(target_status, leaf.status)
        if leaf.status == TreasuryChequeLeaf.Status.RESERVED and not leaf.reserved_at:
            leaf.reserved_at = now
        if leaf.status in {TreasuryChequeLeaf.Status.ISSUED, TreasuryChequeLeaf.Status.CLEARED}:
            leaf.used_at = leaf.used_at or now
        if leaf.status in {TreasuryChequeLeaf.Status.CANCELLED, TreasuryChequeLeaf.Status.STALE, TreasuryChequeLeaf.Status.BOUNCED}:
            leaf.cancelled_at = leaf.cancelled_at or now
        leaf.remarks = cls._normalize_text(reason or f"Treasury instrument {action}")[:255]
        leaf.save(update_fields=["status", "reserved_at", "used_at", "cancelled_at", "remarks", "updated_at"])
        return leaf

    @staticmethod
    def _next_batch_number(*, entity_id: int) -> str:
        stamp = timezone.now().strftime("%Y%m%d%H%M%S")
        return f"TPB-{entity_id}-{stamp}-{uuid.uuid4().hex[:6].upper()}"

    @staticmethod
    def _next_cash_movement_number(*, entity_id: int) -> str:
        stamp = timezone.now().strftime("%Y%m%d%H%M%S")
        return f"TCM-{entity_id}-{stamp}-{uuid.uuid4().hex[:6].upper()}"

    @staticmethod
    def _q2(value) -> Decimal:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))

    @staticmethod
    def _normalize_text(value) -> str:
        return str(value or "").strip()

    @classmethod
    def _normalize_ifsc(cls, value) -> str:
        return cls._normalize_text(value).upper()

    @classmethod
    def _lock_batch(cls, batch: TreasuryPaymentBatch) -> TreasuryPaymentBatch:
        return TreasuryPaymentBatch.objects.select_for_update().get(pk=batch.pk)

    @classmethod
    def _resolve_account(cls, *, account_id: int, entity_id: int, label: str):
        try:
            row = account.objects.select_related("ledger").get(pk=account_id, entity_id=entity_id)
        except account.DoesNotExist:
            raise ValueError(f"{label} account is not available in this entity.")
        if not getattr(row, "ledger_id", None):
            raise ValueError(f"{label} account must be linked to a ledger before Treasury can post a movement.")
        return row

    @classmethod
    def _voucher_plan_for_cash_movement(
        cls,
        *,
        movement_type: str,
        source_account,
        destination_account,
        amount: Decimal,
        narration: str,
    ) -> tuple[str, object, list[dict]]:
        if int(source_account.id) == int(destination_account.id):
            raise ValueError("Source and destination accounts must be different.")
        movement_type = str(movement_type or "").upper().strip()
        amount = cls._q2(amount)
        if amount <= ZERO2:
            raise ValueError("Movement amount must be greater than zero.")

        if movement_type in {TreasuryCashMovement.MovementType.CASH_DEPOSIT, TreasuryCashMovement.MovementType.CASH_TO_BANK}:
            return (
                VoucherHeader.VoucherType.BANK,
                destination_account,
                [{"account": source_account.id, "entry_type": "CR", "amount": amount, "narration": narration or "Cash deposited into bank"}],
            )
        if movement_type in {TreasuryCashMovement.MovementType.CASH_WITHDRAWAL, TreasuryCashMovement.MovementType.BANK_TO_CASH}:
            return (
                VoucherHeader.VoucherType.BANK,
                source_account,
                [{"account": destination_account.id, "entry_type": "DR", "amount": amount, "narration": narration or "Cash withdrawn from bank"}],
            )
        if movement_type == TreasuryCashMovement.MovementType.BANK_TO_BANK:
            return (
                VoucherHeader.VoucherType.BANK,
                source_account,
                [{"account": destination_account.id, "entry_type": "DR", "amount": amount, "narration": narration or "Bank-to-bank transfer"}],
            )
        raise ValueError("Unsupported treasury cash movement type.")

    @classmethod
    def _ensure_voucher_numbering(cls, *, entity_id: int, entityfinid_id: int, subentity_id: int | None, voucher_type: str) -> str:
        settings = VoucherSettingsService.get_settings(entity_id, subentity_id)
        doc_code = VoucherSettingsService.default_doc_code_for_type(settings, voucher_type)
        VoucherSettingsService.ensure_numbering_scope_for_type(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            voucher_type=voucher_type,
            doc_code=doc_code,
        )
        return doc_code

    @classmethod
    def _post_cash_movement_voucher(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: int | None,
        movement_type: str,
        movement_date,
        source_account,
        destination_account,
        payment_mode_id: int | None,
        amount: Decimal,
        reference_no: str,
        instrument_no: str,
        instrument_date,
        bank_name: str,
        narration: str,
        user_id: int | None,
    ) -> VoucherHeader:
        voucher_type, cash_bank_account, lines = cls._voucher_plan_for_cash_movement(
            movement_type=movement_type,
            source_account=source_account,
            destination_account=destination_account,
            amount=amount,
            narration=narration,
        )
        doc_code = cls._ensure_voucher_numbering(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            voucher_type=voucher_type,
        )
        result = VoucherService.create_voucher(
            data={
                "entity_id": entity_id,
                "entityfinid_id": entityfinid_id,
                "subentity_id": subentity_id,
                "voucher_date": movement_date or timezone.localdate(),
                "voucher_type": voucher_type,
                "doc_code": doc_code,
                "cash_bank_account": cash_bank_account,
                "reference_number": reference_no[:100],
                "narration": narration or TreasuryCashMovement.MovementType(movement_type).label,
                "instrument_bank_name": bank_name[:100],
                "instrument_no": instrument_no[:50] or reference_no[:50],
                "instrument_date": instrument_date or movement_date,
                "workflow_payload": {
                    "source": "treasury_cash_movement",
                    "movement_type": movement_type,
                    "source_account_id": source_account.id,
                    "destination_account_id": destination_account.id,
                    "payment_mode_id": payment_mode_id,
                },
                "lines": lines,
            },
            created_by_id=user_id,
        )
        header = result.header
        header.refresh_from_db()
        if int(header.status) == int(VoucherHeader.Status.DRAFT):
            try:
                VoucherService.submit_voucher(header.id, submitted_by_id=user_id or 0, remarks="Submitted from Treasury movement.")
            except Exception:
                pass
            try:
                VoucherService.approve_voucher(header.id, approved_by_id=user_id or 0, remarks="Approved from Treasury movement.")
            except Exception:
                pass
            header = VoucherService.confirm_voucher(header.id, confirmed_by_id=user_id).header
        if int(header.status) == int(VoucherHeader.Status.CONFIRMED):
            try:
                VoucherService.approve_voucher(header.id, approved_by_id=user_id or 0, remarks="Approved from Treasury movement.")
            except Exception:
                pass
        header.refresh_from_db()
        if int(header.status) != int(VoucherHeader.Status.POSTED):
            header = VoucherService.post_voucher(header.id, posted_by_id=user_id).header
        header.refresh_from_db()
        return header

    @classmethod
    @transaction.atomic
    def create_cash_movement(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: int | None,
        movement_type: str,
        movement_date=None,
        source_account_id: int,
        destination_account_id: int,
        payment_mode_id: int | None = None,
        amount=ZERO2,
        reference_no: str = "",
        instrument_no: str = "",
        instrument_date=None,
        bank_name: str = "",
        narration: str = "",
        user_id: int | None = None,
    ) -> TreasuryCashMovement:
        source_account = cls._resolve_account(account_id=source_account_id, entity_id=entity_id, label="Source")
        destination_account = cls._resolve_account(account_id=destination_account_id, entity_id=entity_id, label="Destination")
        amount = cls._q2(amount)
        movement_type = str(movement_type or "").upper().strip()
        movement_date = movement_date or timezone.localdate()
        reference_no = cls._normalize_text(reference_no)
        instrument_no = cls._normalize_text(instrument_no)
        bank_name = cls._normalize_text(bank_name)
        narration = cls._normalize_text(narration) or TreasuryCashMovement.MovementType(movement_type).label
        voucher = cls._post_cash_movement_voucher(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            movement_type=movement_type,
            movement_date=movement_date,
            source_account=source_account,
            destination_account=destination_account,
            payment_mode_id=payment_mode_id,
            amount=amount,
            reference_no=reference_no,
            instrument_no=instrument_no,
            instrument_date=instrument_date,
            bank_name=bank_name,
            narration=narration,
            user_id=user_id,
        )
        return TreasuryCashMovement.objects.create(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            movement_number=cls._next_cash_movement_number(entity_id=entity_id),
            movement_type=movement_type,
            movement_date=movement_date,
            source_account=source_account,
            destination_account=destination_account,
            payment_mode_id=payment_mode_id,
            amount=amount,
            reference_no=reference_no[:120],
            instrument_no=instrument_no[:50],
            instrument_date=instrument_date,
            bank_name=bank_name[:100],
            narration=narration[:255],
            voucher=voucher,
            status=TreasuryCashMovement.Status.POSTED,
            posted_by_id=user_id,
            posted_at=timezone.now(),
            metadata_json={
                "voucher_id": voucher.id,
                "voucher_code": voucher.voucher_code,
                "voucher_type": voucher.voucher_type,
                "source_account_name": source_account.accountname,
                "destination_account_name": destination_account.accountname,
            },
        )

    @classmethod
    @transaction.atomic
    def cancel_cash_movement(
        cls,
        *,
        movement: TreasuryCashMovement,
        user_id: int | None = None,
        reason: str = "",
    ) -> TreasuryCashMovement:
        movement = TreasuryCashMovement.objects.select_for_update().get(pk=movement.pk)
        if movement.status == TreasuryCashMovement.Status.CANCELLED:
            return movement
        if movement.voucher_id:
            voucher = VoucherHeader.objects.get(pk=movement.voucher_id)
            if int(voucher.status) == int(VoucherHeader.Status.POSTED):
                VoucherService.unpost_voucher(voucher.id, unposted_by_id=user_id)
                voucher.refresh_from_db()
            if int(voucher.status) != int(VoucherHeader.Status.CANCELLED):
                VoucherService.cancel_voucher(voucher.id, cancelled_by_id=user_id, reason=reason or "Cancelled from Treasury movement.")
        movement.status = TreasuryCashMovement.Status.CANCELLED
        movement.cancelled_by_id = user_id
        movement.cancelled_at = timezone.now()
        movement.cancellation_reason = cls._normalize_text(reason)[:255]
        metadata = dict(movement.metadata_json or {})
        metadata["cancelled_from_treasury"] = True
        metadata["cancelled_at"] = movement.cancelled_at.isoformat()
        metadata["cancelled_by"] = user_id
        movement.metadata_json = metadata
        movement.save(update_fields=["status", "cancelled_by", "cancelled_at", "cancellation_reason", "metadata_json", "updated_at"])
        return movement

    @classmethod
    def _resolve_primary_bank_detail(cls, party_account):
        if party_account is None:
            return None
        return (
            party_account.bank_details.filter(isprimary=True, isactive=True)
            .only("bankname", "banKAcno", "ifsc", "branch")
            .first()
            or party_account.bank_details.filter(isactive=True).only("bankname", "banKAcno", "ifsc", "branch").first()
        )

    @classmethod
    def _line_from_vendor_open_item(cls, *, batch: TreasuryPaymentBatch, item: VendorBillOpenItem, sequence: int):
        vendor = item.vendor
        bank = cls._resolve_primary_bank_detail(vendor)
        amount = cls._q2(item.outstanding_amount)
        doc_number = item.purchase_number or item.supplier_invoice_number or f"AP-{item.id}"
        return TreasuryPaymentBatchLine(
            batch=batch,
            vendor_open_item=item,
            sequence=sequence,
            party_account=vendor,
            party_name=cls._normalize_text(getattr(vendor, "effective_accounting_name", "") or getattr(vendor, "accountname", "")),
            party_code=cls._normalize_text(getattr(vendor, "effective_accounting_code", "") or ""),
            source_doc_type=cls._normalize_text(getattr(item.header, "get_doc_type_display", lambda: "")()),
            source_doc_number=doc_number,
            source_date=item.bill_date,
            due_date=item.due_date,
            account_holder_name=cls._normalize_text(getattr(vendor, "effective_accounting_name", "") or getattr(vendor, "accountname", "")),
            bank_name=cls._normalize_text(getattr(bank, "bankname", "")),
            branch_name=cls._normalize_text(getattr(bank, "branch", "")),
            account_number=cls._normalize_text(getattr(bank, "banKAcno", "")),
            ifsc_code=cls._normalize_ifsc(getattr(bank, "ifsc", "")),
            amount=amount,
            narration=f"Vendor payment {doc_number}",
            source_snapshot_json={
                "vendor_open_item_id": item.id,
                "header_id": item.header_id,
                "purchase_number": item.purchase_number,
                "supplier_invoice_number": item.supplier_invoice_number,
                "original_amount": f"{cls._q2(item.original_amount):.2f}",
                "settled_amount": f"{cls._q2(item.settled_amount):.2f}",
                "outstanding_amount": f"{amount:.2f}",
                "vendor_id": item.vendor_id,
                "vendor_name": cls._normalize_text(getattr(vendor, "effective_accounting_name", "") or getattr(vendor, "accountname", "")),
            },
        )

    @classmethod
    @transaction.atomic
    def create_from_vendor_open_items(
        cls,
        *,
        entity_id: int,
        entityfinid_id: int,
        subentity_id: int | None,
        open_item_ids: list[int],
        batch_name: str = "",
        payout_date=None,
        paid_from_id: int | None = None,
        payment_mode_id: int | None = None,
        instrument_bank_name: str = "",
        instrument_no: str = "",
        instrument_date=None,
        export_format: str = TreasuryPaymentBatch.ExportFormat.GENERIC_CSV,
        user_id: int | None = None,
    ) -> TreasuryPaymentBatch:
        unique_ids = list(dict.fromkeys(int(x) for x in open_item_ids))
        if not unique_ids:
            raise ValueError("Select at least one payable item for the payment batch.")

        items = list(
            VendorBillOpenItem.objects.select_for_update()
            .select_related("header", "vendor")
            .filter(pk__in=unique_ids)
            .order_by("due_date", "bill_date", "id")
        )
        found_ids = {x.id for x in items}
        missing_ids = [x for x in unique_ids if x not in found_ids]
        if missing_ids:
            raise ValueError(f"Some payable items were not found: {', '.join(str(x) for x in missing_ids)}.")

        duplicate_item_ids = set(
            TreasuryPaymentBatchLine.objects.filter(
                vendor_open_item_id__in=unique_ids,
                batch__status__in=ACTIVE_BATCH_STATUSES,
            ).values_list("vendor_open_item_id", flat=True)
        )
        if duplicate_item_ids:
            raise ValueError(
                "Some payable items are already part of an active treasury batch: "
                + ", ".join(str(x) for x in sorted(duplicate_item_ids))
                + "."
            )

        for item in items:
            if item.entity_id != entity_id or item.entityfinid_id != entityfinid_id:
                raise ValueError("All payable items must belong to the selected entity and financial year.")
            if subentity_id and item.subentity_id != subentity_id:
                raise ValueError("All payable items must belong to the selected branch/subentity.")
            if not item.is_open or cls._q2(item.outstanding_amount) <= ZERO2:
                raise ValueError("Only open payable items with positive outstanding amounts can be batched.")

        batch = TreasuryPaymentBatch.objects.create(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            source_type=TreasuryPaymentBatch.SourceType.VENDOR_PAYABLES,
            batch_number=cls._next_batch_number(entity_id=entity_id),
            batch_name=cls._normalize_text(batch_name),
            payout_date=payout_date,
            paid_from_id=paid_from_id,
            payment_mode_id=payment_mode_id,
            instrument_bank_name=cls._normalize_text(instrument_bank_name),
            instrument_no=cls._normalize_text(instrument_no),
            instrument_date=instrument_date,
            export_format=export_format,
            requested_by_id=user_id,
        )
        TreasuryPaymentBatchLine.objects.bulk_create(
            [cls._line_from_vendor_open_item(batch=batch, item=item, sequence=(index + 1) * 100) for index, item in enumerate(items)]
        )
        cls._refresh_batch_totals(batch=batch)
        cls._sync_batch_instrument(
            batch=batch,
            status=TreasuryPaymentInstrument.Status.PREPARED,
            reference=batch.instrument_no or batch.batch_number,
            reason="Payment batch prepared.",
        )
        cls._log_status(batch=batch, old_status="", new_status=batch.status, user_id=user_id, comment="Payment batch created.")
        return cls.validate_batch(batch=batch, user_id=user_id, comment="Initial validation.")

    @classmethod
    def _validate_line(cls, *, line: TreasuryPaymentBatchLine, duplicate_keys: set[str]) -> tuple[list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        if cls._q2(line.amount) <= ZERO2:
            errors.append("Payment amount must be greater than zero.")
        if not line.account_holder_name:
            errors.append("Beneficiary/account holder name is missing.")
        if not line.account_number:
            errors.append("Beneficiary bank account number is missing.")
        if not line.ifsc_code:
            errors.append("Beneficiary IFSC code is missing.")
        elif not IFSC_RE.match(line.ifsc_code):
            errors.append("Beneficiary IFSC code is not valid.")
        key = f"{line.account_number}|{line.ifsc_code}" if line.account_number and line.ifsc_code else ""
        if key and key in duplicate_keys:
            warnings.append("Another line in this batch uses the same bank account and IFSC.")
        return errors, warnings

    @classmethod
    def _batch_duplicate_keys(cls, *, batch: TreasuryPaymentBatch) -> set[str]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for line in batch.lines.all():
            key = f"{line.account_number}|{line.ifsc_code}" if line.account_number and line.ifsc_code else ""
            if not key:
                continue
            if key in seen:
                duplicates.add(key)
            seen.add(key)
        return duplicates

    @classmethod
    def _refresh_batch_totals(cls, *, batch: TreasuryPaymentBatch) -> TreasuryPaymentBatch:
        totals = batch.lines.aggregate(
            total_lines=Count("id"),
            payable_line_count=Count("id", filter=Q(line_status=TreasuryPaymentBatchLine.LineStatus.VALID)),
            invalid_line_count=Count("id", filter=Q(line_status=TreasuryPaymentBatchLine.LineStatus.INVALID)),
            total_amount=Sum("amount", filter=~Q(line_status=TreasuryPaymentBatchLine.LineStatus.INVALID)),
        )
        batch.total_lines = totals["total_lines"] or 0
        batch.payable_line_count = totals["payable_line_count"] or 0
        batch.invalid_line_count = totals["invalid_line_count"] or 0
        batch.warning_line_count = sum(1 for line in batch.lines.only("validation_warnings_json") if line.validation_warnings_json)
        batch.total_amount = cls._q2(totals["total_amount"] or ZERO2)
        batch.validation_summary_json = {
            "total_lines": batch.total_lines,
            "payable_line_count": batch.payable_line_count,
            "invalid_line_count": batch.invalid_line_count,
            "warning_line_count": batch.warning_line_count,
            "total_amount": f"{batch.total_amount:.2f}",
        }
        batch.save(
            update_fields=[
                "total_lines",
                "payable_line_count",
                "invalid_line_count",
                "warning_line_count",
                "total_amount",
                "validation_summary_json",
                "updated_at",
            ]
        )
        return batch

    @classmethod
    @transaction.atomic
    def validate_batch(cls, *, batch: TreasuryPaymentBatch, user_id: int | None = None, comment: str = "") -> TreasuryPaymentBatch:
        batch = cls._lock_batch(batch)
        if batch.status in {TreasuryPaymentBatch.Status.PAID, TreasuryPaymentBatch.Status.CANCELLED}:
            raise ValueError("Paid or cancelled payment batches cannot be revalidated.")
        duplicate_keys = cls._batch_duplicate_keys(batch=batch)
        for line in batch.lines.select_for_update().order_by("sequence", "id"):
            errors, warnings = cls._validate_line(line=line, duplicate_keys=duplicate_keys)
            line.line_status = TreasuryPaymentBatchLine.LineStatus.INVALID if errors else TreasuryPaymentBatchLine.LineStatus.VALID
            line.has_duplicate_account_warning = bool(warnings)
            line.validation_errors_json = errors
            line.validation_warnings_json = warnings
            line.save(
                update_fields=[
                    "line_status",
                    "has_duplicate_account_warning",
                    "validation_errors_json",
                    "validation_warnings_json",
                    "updated_at",
                ]
            )
        old_status = batch.status
        batch.status = TreasuryPaymentBatch.Status.VALIDATED
        batch.save(update_fields=["status", "updated_at"])
        cls._refresh_batch_totals(batch=batch)
        cls._log_status(batch=batch, old_status=old_status, new_status=batch.status, user_id=user_id, comment=comment)
        return batch

    @classmethod
    @transaction.atomic
    def approve_batch(cls, *, batch: TreasuryPaymentBatch, user_id: int | None = None, comment: str = "") -> TreasuryPaymentBatch:
        batch = cls._lock_batch(batch)
        if batch.status != TreasuryPaymentBatch.Status.VALIDATED:
            raise ValueError("Only validated payment batches can be approved.")
        cls._refresh_batch_totals(batch=batch)
        if batch.invalid_line_count:
            raise ValueError("Resolve invalid payment lines before approval.")
        old_status = batch.status
        batch.status = TreasuryPaymentBatch.Status.APPROVED
        batch.approval_status = TreasuryPaymentBatch.ApprovalStatus.APPROVED
        batch.approved_by_id = user_id
        batch.approved_at = timezone.now()
        batch.save(update_fields=["status", "approval_status", "approved_by", "approved_at", "updated_at"])
        cls._log_status(batch=batch, old_status=old_status, new_status=batch.status, user_id=user_id, comment=comment)
        return batch

    @classmethod
    def _export_rows(cls, *, batch: TreasuryPaymentBatch) -> list[dict]:
        rows: list[dict] = []
        for line in batch.lines.exclude(line_status=TreasuryPaymentBatchLine.LineStatus.INVALID).order_by("sequence", "id"):
            rows.append(
                {
                    "beneficiary_name": line.account_holder_name,
                    "beneficiary_account_number": line.account_number,
                    "ifsc_code": line.ifsc_code,
                    "amount": f"{line.amount:.2f}",
                    "narration": line.narration,
                    "source_doc_number": line.source_doc_number,
                    "party_code": line.party_code,
                    "bank_name": line.bank_name,
                    "branch_name": line.branch_name,
                }
            )
        return rows

    @classmethod
    def _render_csv(cls, *, rows: list[dict]) -> str:
        buffer = io.StringIO()
        fieldnames = [
            "beneficiary_name",
            "beneficiary_account_number",
            "ifsc_code",
            "amount",
            "narration",
            "source_doc_number",
            "party_code",
            "bank_name",
            "branch_name",
        ]
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return buffer.getvalue()

    @classmethod
    @transaction.atomic
    def export_batch(
        cls,
        *,
        batch: TreasuryPaymentBatch,
        user_id: int | None = None,
        export_format: str | None = None,
        comment: str = "",
    ) -> TreasuryPaymentExportResult:
        batch = cls._lock_batch(batch)
        if batch.status not in {TreasuryPaymentBatch.Status.APPROVED, TreasuryPaymentBatch.Status.EXPORTED}:
            raise ValueError("Only approved payment batches can be exported.")
        if batch.approval_status not in {TreasuryPaymentBatch.ApprovalStatus.APPROVED, TreasuryPaymentBatch.ApprovalStatus.LOCKED}:
            raise ValueError("Payment batch must be approval-cleared before export.")
        rows = cls._export_rows(batch=batch)
        export_format = export_format or batch.export_format or TreasuryPaymentBatch.ExportFormat.GENERIC_CSV
        file_content = cls._render_csv(rows=rows)
        total_amount = sum((Decimal(str(row["amount"])) for row in rows), ZERO2)
        file_name = f"{batch.batch_number.lower()}-{export_format.lower()}.csv"
        export_record = TreasuryPaymentFileExport.objects.create(
            batch=batch,
            export_format=export_format,
            file_name=file_name,
            row_count=len(rows),
            total_amount=cls._q2(total_amount),
            file_content=file_content,
            export_metadata_json={
                "exported_at": timezone.now().isoformat(),
                "row_count": len(rows),
                "export_total_amount": f"{cls._q2(total_amount):.2f}",
                "batch_total_amount": f"{batch.total_amount:.2f}",
                "is_reconciled": cls._q2(total_amount) == cls._q2(batch.total_amount),
            },
            exported_by_id=user_id,
        )
        old_status = batch.status
        batch.status = TreasuryPaymentBatch.Status.EXPORTED
        batch.export_format = export_format
        batch.exported_by_id = user_id
        batch.exported_at = timezone.now()
        batch.export_reference = file_name
        batch.save(update_fields=["status", "export_format", "exported_by", "exported_at", "export_reference", "updated_at"])
        cls._log_status(
            batch=batch,
            old_status=old_status,
            new_status=batch.status,
            user_id=user_id,
            comment=comment,
            payload={"export_file_name": file_name, "export_format": export_format},
        )
        cls._sync_batch_instrument(
            batch=batch,
            status=TreasuryPaymentInstrument.Status.EXPORTED,
            reference=batch.export_reference or batch.instrument_no or batch.batch_number,
            reason=comment or "Payment file exported.",
            metadata={"export_file_name": file_name, "export_format": export_format},
        )
        return TreasuryPaymentExportResult(
            batch=batch,
            export_record=export_record,
            file_name=file_name,
            content_type=export_record.content_type,
            file_content=file_content,
        )

    @classmethod
    @transaction.atomic
    def mark_paid(
        cls,
        *,
        batch: TreasuryPaymentBatch,
        user_id: int | None = None,
        payment_reference: str = "",
        comment: str = "",
        paid_from_id: int | None = None,
        payment_mode_id: int | None = None,
        instrument_bank_name: str = "",
        instrument_no: str = "",
        instrument_date=None,
    ) -> TreasuryPaymentBatch:
        batch = cls._lock_batch(batch)
        if batch.status not in {TreasuryPaymentBatch.Status.APPROVED, TreasuryPaymentBatch.Status.EXPORTED, TreasuryPaymentBatch.Status.FAILED}:
            raise ValueError("Only approved, exported, or failed payment batches can be marked paid.")
        update_fields = []
        if paid_from_id:
            batch.paid_from_id = paid_from_id
            update_fields.append("paid_from")
        if payment_mode_id:
            batch.payment_mode_id = payment_mode_id
            update_fields.append("payment_mode")
        if instrument_bank_name:
            batch.instrument_bank_name = cls._normalize_text(instrument_bank_name)
            update_fields.append("instrument_bank_name")
        if instrument_no:
            batch.instrument_no = cls._normalize_text(instrument_no)
            update_fields.append("instrument_no")
        if instrument_date is not None:
            batch.instrument_date = instrument_date
            update_fields.append("instrument_date")
        if update_fields:
            batch.save(update_fields=[*update_fields, "updated_at"])
        ap_handoff = cls._post_vendor_payable_handoff(batch=batch, user_id=user_id, payment_reference=payment_reference)
        old_status = batch.status
        batch.status = TreasuryPaymentBatch.Status.PAID
        batch.paid_by_id = user_id
        batch.paid_at = timezone.now()
        batch.payment_reference = cls._normalize_text(payment_reference)
        config = dict(batch.config_json or {})
        if ap_handoff:
            if ap_handoff.get("mode") == "vendor_payables_payment_voucher":
                config["payment_voucher_handoff"] = ap_handoff
                config["ap_handoff"] = {
                    "source": ap_handoff.get("source"),
                    "mode": "vendor_payables_ap_settlement",
                    "settlement_ids": ap_handoff.get("settlement_ids", []),
                    "settlement_count": ap_handoff.get("settlement_count", 0),
                    "settlement_total": ap_handoff.get("settlement_total", "0.00"),
                    "payment_reference": ap_handoff.get("payment_reference", ""),
                    "settlement_date": ap_handoff.get("settlement_date", ""),
                    "via_payment_voucher": True,
                }
            else:
                config["ap_handoff"] = ap_handoff
        batch.config_json = config
        batch.save(update_fields=["status", "paid_by", "paid_at", "payment_reference", "config_json", "updated_at"])
        batch.lines.update(line_status=TreasuryPaymentBatchLine.LineStatus.PAID)
        cls._sync_batch_instrument(
            batch=batch,
            status=TreasuryPaymentInstrument.Status.CLEARED,
            reference=batch.payment_reference or batch.instrument_no or batch.batch_number,
            reason=comment or "Payment cleared/marked paid.",
            metadata={"ap_handoff": ap_handoff},
        )
        cls._log_status(
            batch=batch,
            old_status=old_status,
            new_status=batch.status,
            user_id=user_id,
            comment=comment,
            payload={"payment_reference": payment_reference, "ap_handoff": ap_handoff},
        )
        return batch

    @classmethod
    def _post_vendor_payable_handoff(
        cls,
        *,
        batch: TreasuryPaymentBatch,
        user_id: int | None = None,
        payment_reference: str = "",
    ) -> dict:
        if batch.source_type != TreasuryPaymentBatch.SourceType.VENDOR_PAYABLES:
            return {}

        existing = (batch.config_json or {}).get("payment_voucher_handoff") or (batch.config_json or {}).get("ap_handoff") or {}
        existing_ids = existing.get("settlement_ids") or []
        if existing_ids:
            return existing

        if batch.paid_from_id and batch.payment_mode_id:
            return cls._post_vendor_payable_payment_voucher_handoff(
                batch=batch,
                user_id=user_id,
                payment_reference=payment_reference,
            )

        lines = list(
            batch.lines.select_related("vendor_open_item", "vendor_open_item__vendor")
            .exclude(line_status=TreasuryPaymentBatchLine.LineStatus.INVALID)
            .order_by("party_account_id", "sequence", "id")
        )
        if not lines:
            raise ValueError("Payment batch has no valid payable lines to settle.")

        grouped: dict[int, list[TreasuryPaymentBatchLine]] = {}
        for line in lines:
            if not line.vendor_open_item_id:
                raise ValueError("Vendor payable batches require every payment line to reference an AP open item.")
            item = line.vendor_open_item
            if item.entity_id != batch.entity_id or item.entityfinid_id != batch.entityfinid_id:
                raise ValueError("Payment line AP open item is outside the batch entity or financial year.")
            if batch.subentity_id and item.subentity_id != batch.subentity_id:
                raise ValueError("Payment line AP open item is outside the batch branch/subentity.")
            if not item.is_open or cls._q2(item.outstanding_amount) <= ZERO2:
                raise ValueError(f"AP open item {item.id} is already settled or has no payable balance.")
            amount = cls._q2(line.amount)
            if amount <= ZERO2:
                raise ValueError("Payment line amount must be greater than zero before AP handoff.")
            if amount > cls._q2(item.outstanding_amount):
                raise ValueError(f"Payment line amount exceeds AP open item {item.id} outstanding balance.")
            grouped.setdefault(int(item.vendor_id), []).append(line)

        settlement_ids: list[int] = []
        settlement_total = ZERO2
        reference = cls._normalize_text(payment_reference) or batch.batch_number
        settlement_date = batch.payout_date or timezone.localdate()
        for vendor_id, vendor_lines in grouped.items():
            result = PurchaseApService.create_settlement(
                entity_id=batch.entity_id,
                entityfinid_id=batch.entityfinid_id,
                subentity_id=batch.subentity_id,
                vendor_id=vendor_id,
                settlement_type=VendorSettlement.SettlementType.PAYMENT,
                settlement_date=settlement_date,
                reference_no=reference[:50],
                external_voucher_no=batch.batch_number[:50],
                remarks=f"Treasury payment batch {batch.batch_number}",
                lines=[
                    {
                        "open_item_id": int(line.vendor_open_item_id),
                        "amount": cls._q2(line.amount),
                        "note": line.source_doc_number or line.narration,
                    }
                    for line in vendor_lines
                ],
            )
            posted = PurchaseApService.post_settlement(settlement_id=result.settlement.id, posted_by_id=user_id)
            settlement_ids.append(int(posted.settlement.id))
            settlement_total = cls._q2(settlement_total + posted.applied_total)

        if settlement_total != cls._q2(batch.total_amount):
            raise ValueError("AP handoff total does not match the treasury batch total.")

        return {
            "source": "treasury_payment_batch",
            "mode": "vendor_payables_ap_settlement",
            "settlement_ids": settlement_ids,
            "settlement_count": len(settlement_ids),
            "settlement_total": f"{settlement_total:.2f}",
            "payment_reference": reference,
            "settlement_date": settlement_date.isoformat(),
        }

    @classmethod
    def _seed_payment_voucher_numbering(cls, *, batch: TreasuryPaymentBatch) -> None:
        NumberingSeedService.seed_document(
            entity_id=batch.entity_id,
            entityfinid_id=batch.entityfinid_id,
            subentity_id=batch.subentity_id,
            module="payments",
            doc_key="PAYMENT_VOUCHER",
            name="Payment Voucher",
            default_code="PPV",
            prefix="PPV",
        )

    @classmethod
    def _post_vendor_payable_payment_voucher_handoff(
        cls,
        *,
        batch: TreasuryPaymentBatch,
        user_id: int | None = None,
        payment_reference: str = "",
    ) -> dict:
        lines = list(
            batch.lines.select_related("vendor_open_item", "vendor_open_item__vendor", "party_account")
            .exclude(line_status=TreasuryPaymentBatchLine.LineStatus.INVALID)
            .order_by("party_account_id", "sequence", "id")
        )
        if not lines:
            raise ValueError("Payment batch has no valid payable lines to settle.")
        if not batch.paid_from_id:
            raise ValueError("Source cash/bank account is required to create payment vouchers from a treasury batch.")
        if not batch.payment_mode_id:
            raise ValueError("Payment mode is required to create payment vouchers from a treasury batch.")
        if not getattr(batch.paid_from, "ledger_id", None):
            raise ValueError("Source cash/bank account must be linked to a ledger before Treasury can create payment vouchers.")

        cls._seed_payment_voucher_numbering(batch=batch)
        grouped: dict[int, list[TreasuryPaymentBatchLine]] = {}
        for line in lines:
            if not line.vendor_open_item_id:
                raise ValueError("Vendor payable batches require every payment line to reference an AP open item.")
            item = line.vendor_open_item
            if not getattr(item.vendor, "ledger_id", None):
                raise ValueError(f"Vendor account {item.vendor_id} must be linked to a ledger before Treasury can create payment vouchers.")
            if item.entity_id != batch.entity_id or item.entityfinid_id != batch.entityfinid_id:
                raise ValueError("Payment line AP open item is outside the batch entity or financial year.")
            if batch.subentity_id and item.subentity_id != batch.subentity_id:
                raise ValueError("Payment line AP open item is outside the batch branch/subentity.")
            if not item.is_open or cls._q2(item.outstanding_amount) <= ZERO2:
                raise ValueError(f"AP open item {item.id} is already settled or has no payable balance.")
            amount = cls._q2(line.amount)
            if amount <= ZERO2:
                raise ValueError("Payment line amount must be greater than zero before payment voucher handoff.")
            if amount > cls._q2(item.outstanding_amount):
                raise ValueError(f"Payment line amount exceeds AP open item {item.id} outstanding balance.")
            grouped.setdefault(int(item.vendor_id), []).append(line)

        reference = cls._normalize_text(payment_reference) or batch.batch_number
        voucher_date = batch.payout_date or timezone.localdate()
        voucher_ids: list[int] = []
        voucher_codes: list[str] = []
        settlement_ids: list[int] = []
        handoff_total = ZERO2

        for vendor_id, vendor_lines in grouped.items():
            vendor_total = sum((cls._q2(line.amount) for line in vendor_lines), ZERO2)
            vendor_total = cls._q2(vendor_total)
            first_line = vendor_lines[0]
            voucher = PaymentVoucherService.create_voucher({
                "entity": batch.entity,
                "entityfinid": batch.entityfinid,
                "subentity": batch.subentity,
                "voucher_date": voucher_date,
                "doc_code": "PPV",
                "payment_type": PaymentVoucherHeader.PaymentType.AGAINST_BILL,
                "supply_type": PaymentVoucherHeader.SupplyType.MIXED,
                "paid_from": batch.paid_from,
                "paid_to": first_line.vendor_open_item.vendor,
                "payment_mode": batch.payment_mode,
                "cash_paid_amount": vendor_total,
                "reference_number": reference[:100],
                "narration": f"Treasury payment batch {batch.batch_number}",
                "instrument_bank_name": batch.instrument_bank_name or first_line.bank_name,
                "instrument_no": batch.instrument_no or reference[:50],
                "instrument_date": batch.instrument_date or voucher_date,
                "created_by_id": user_id,
                "allocations": [
                    {
                        "open_item": int(line.vendor_open_item_id),
                        "settled_amount": cls._q2(line.amount),
                        "is_full_settlement": cls._q2(line.amount) == cls._q2(line.vendor_open_item.outstanding_amount),
                    }
                    for line in vendor_lines
                ],
                "adjustments": [],
            })
            PaymentVoucherService.confirm_voucher(voucher.id, confirmed_by_id=user_id)
            PaymentVoucherService.approve_voucher(voucher.id, approved_by_id=user_id, remarks="Approved from treasury payment batch.")
            posted = PaymentVoucherService.post_voucher(voucher.id, posted_by_id=user_id)
            posted.header.refresh_from_db()
            voucher_ids.append(int(posted.header.id))
            voucher_codes.append(posted.header.voucher_code or str(posted.header.id))
            if posted.header.ap_settlement_id:
                settlement_ids.append(int(posted.header.ap_settlement_id))
            handoff_total = cls._q2(handoff_total + vendor_total)

        if handoff_total != cls._q2(batch.total_amount):
            raise ValueError("Payment voucher handoff total does not match the treasury batch total.")

        return {
            "source": "treasury_payment_batch",
            "mode": "vendor_payables_payment_voucher",
            "payment_voucher_ids": voucher_ids,
            "payment_voucher_codes": voucher_codes,
            "voucher_count": len(voucher_ids),
            "settlement_ids": settlement_ids,
            "settlement_count": len(settlement_ids),
            "settlement_total": f"{handoff_total:.2f}",
            "payment_reference": reference,
            "settlement_date": voucher_date.isoformat(),
            "paid_from_id": batch.paid_from_id,
            "payment_mode_id": batch.payment_mode_id,
        }

    @classmethod
    @transaction.atomic
    def mark_failed(cls, *, batch: TreasuryPaymentBatch, user_id: int | None = None, failure_reason: str = "", comment: str = "") -> TreasuryPaymentBatch:
        batch = cls._lock_batch(batch)
        if batch.status not in {TreasuryPaymentBatch.Status.APPROVED, TreasuryPaymentBatch.Status.EXPORTED, TreasuryPaymentBatch.Status.FAILED}:
            raise ValueError("Only approved, exported, or failed payment batches can be marked failed.")
        old_status = batch.status
        batch.status = TreasuryPaymentBatch.Status.FAILED
        batch.failed_by_id = user_id
        batch.failed_at = timezone.now()
        batch.failure_reason = cls._normalize_text(failure_reason)
        batch.save(update_fields=["status", "failed_by", "failed_at", "failure_reason", "updated_at"])
        batch.lines.update(line_status=TreasuryPaymentBatchLine.LineStatus.FAILED)
        cls._sync_batch_instrument(
            batch=batch,
            status=TreasuryPaymentInstrument.Status.FAILED,
            reference=batch.payment_reference or batch.instrument_no or batch.export_reference or batch.batch_number,
            reason=batch.failure_reason or comment or "Payment failed.",
        )
        cls._log_status(batch=batch, old_status=old_status, new_status=batch.status, user_id=user_id, comment=comment, payload={"failure_reason": failure_reason})
        return batch

    @classmethod
    @transaction.atomic
    def cancel_batch(cls, *, batch: TreasuryPaymentBatch, user_id: int | None = None, cancellation_reason: str = "", comment: str = "") -> TreasuryPaymentBatch:
        batch = cls._lock_batch(batch)
        if batch.status not in {TreasuryPaymentBatch.Status.DRAFT, TreasuryPaymentBatch.Status.VALIDATED, TreasuryPaymentBatch.Status.APPROVED}:
            raise ValueError("Only draft, validated, or approved payment batches can be cancelled.")
        old_status = batch.status
        batch.status = TreasuryPaymentBatch.Status.CANCELLED
        batch.approval_status = TreasuryPaymentBatch.ApprovalStatus.CANCELLED
        batch.cancelled_by_id = user_id
        batch.cancelled_at = timezone.now()
        batch.cancellation_reason = cls._normalize_text(cancellation_reason)
        batch.save(update_fields=["status", "approval_status", "cancelled_by", "cancelled_at", "cancellation_reason", "updated_at"])
        batch.lines.update(line_status=TreasuryPaymentBatchLine.LineStatus.CANCELLED)
        cls._sync_batch_instrument(
            batch=batch,
            status=TreasuryPaymentInstrument.Status.CANCELLED,
            reference=batch.payment_reference or batch.instrument_no or batch.export_reference or batch.batch_number,
            reason=batch.cancellation_reason or comment or "Payment cancelled.",
        )
        cls._log_status(batch=batch, old_status=old_status, new_status=batch.status, user_id=user_id, comment=comment, payload={"cancellation_reason": cancellation_reason})
        return batch

    @classmethod
    def _instrument_type_for_batch(cls, *, batch: TreasuryPaymentBatch) -> str:
        label = cls._normalize_text(
            getattr(batch.payment_mode, "paymentmode", "")
            or getattr(batch.payment_mode, "paymentmodename", "")
            or getattr(batch.payment_mode, "paymentmodecode", "")
        ).upper()
        if "CHEQUE" in label or "CHECK" in label:
            return TreasuryPaymentInstrument.InstrumentType.CHEQUE
        if "UPI" in label:
            return TreasuryPaymentInstrument.InstrumentType.UPI
        if "NEFT" in label:
            return TreasuryPaymentInstrument.InstrumentType.NEFT
        if "RTGS" in label:
            return TreasuryPaymentInstrument.InstrumentType.RTGS
        if "IMPS" in label:
            return TreasuryPaymentInstrument.InstrumentType.IMPS
        if "CASH" in label:
            return TreasuryPaymentInstrument.InstrumentType.CASH
        if "CARD" in label:
            return TreasuryPaymentInstrument.InstrumentType.CARD
        if "GATEWAY" in label:
            return TreasuryPaymentInstrument.InstrumentType.GATEWAY
        if "BANK" in label or "TRANSFER" in label:
            return TreasuryPaymentInstrument.InstrumentType.BANK_TRANSFER
        return TreasuryPaymentInstrument.InstrumentType.OTHER

    @classmethod
    def _sync_batch_instrument(
        cls,
        *,
        batch: TreasuryPaymentBatch,
        status: str,
        reference: str = "",
        reason: str = "",
        metadata: dict | None = None,
    ) -> TreasuryPaymentInstrument:
        now = timezone.now()
        timestamp_fields = {
            "cleared_at": now if status == TreasuryPaymentInstrument.Status.CLEARED else None,
            "failed_at": now if status == TreasuryPaymentInstrument.Status.FAILED else None,
            "cancelled_at": now if status == TreasuryPaymentInstrument.Status.CANCELLED else None,
        }
        existing = batch.instruments.order_by("created_at", "id").first()
        existing_metadata = dict(getattr(existing, "metadata_json", None) or {})
        if metadata:
            existing_metadata.update(metadata)
        existing_metadata.update(
            {
                "batch_number": batch.batch_number,
                "batch_status": batch.status,
                "source_type": batch.source_type,
                "status_synced_at": now.isoformat(),
            }
        )
        defaults = {
            "source_account_id": batch.paid_from_id,
            "payment_mode_id": batch.payment_mode_id,
            "instrument_type": cls._instrument_type_for_batch(batch=batch),
            "status": status,
            "reference_no": cls._normalize_text(reference)[:120],
            "instrument_no": cls._normalize_text(batch.instrument_no or reference)[:50],
            "instrument_date": batch.instrument_date or batch.payout_date,
            "bank_name": cls._normalize_text(batch.instrument_bank_name)[:100],
            "amount": cls._q2(batch.total_amount),
            "status_reason": cls._normalize_text(reason)[:255],
            "metadata_json": existing_metadata,
            **timestamp_fields,
        }
        if existing:
            for field, value in defaults.items():
                setattr(existing, field, value)
            existing.save(update_fields=[*defaults.keys(), "updated_at"])
            return existing
        return TreasuryPaymentInstrument.objects.create(batch=batch, **defaults)

    @classmethod
    @transaction.atomic
    def transition_instrument(
        cls,
        *,
        instrument: TreasuryPaymentInstrument,
        action: str,
        user_id: int | None = None,
        reference_no: str = "",
        instrument_no: str = "",
        instrument_date=None,
        bank_name: str = "",
        cheque_leaf_id=None,
        reason: str = "",
        comment: str = "",
    ) -> TreasuryPaymentInstrument:
        action = cls._normalize_text(action).lower()
        rule = cls.INSTRUMENT_TRANSITIONS.get(action)
        if not rule:
            raise ValueError("Unsupported treasury instrument action.")
        instrument = (
            TreasuryPaymentInstrument.objects
            .select_for_update()
            .select_related("batch")
            .get(pk=instrument.pk)
        )
        old_status = instrument.status
        if old_status == rule["target"] and action not in {"retry", "reissue"}:
            raise ValueError(f"Instrument is already {instrument.get_status_display()}.")
        if old_status not in rule["allowed"]:
            target_label = dict(TreasuryPaymentInstrument.Status.choices).get(rule["target"], rule["target"])
            raise ValueError(f"Cannot move instrument from {instrument.get_status_display()} to {target_label}.")

        now = timezone.now()
        target = rule["target"]
        cheque_leaf = cls._lock_cheque_leaf_for_instrument(
            instrument=instrument,
            cheque_leaf_id=cheque_leaf_id,
            instrument_no=instrument_no,
        )
        metadata = dict(instrument.metadata_json or {})
        history = list(metadata.get("lifecycle_history") or [])
        normalized_reason = cls._normalize_text(reason or comment or rule["default_reason"])
        history.append(
            {
                "action": action,
                "old_status": old_status,
                "new_status": target,
                "acted_by": user_id,
                "acted_at": now.isoformat(),
                "reason": normalized_reason,
            }
        )
        metadata["lifecycle_history"] = history[-25:]
        metadata["last_lifecycle_action"] = action
        metadata["last_lifecycle_at"] = now.isoformat()

        instrument.status = target
        instrument.status_reason = normalized_reason[:255]
        if reference_no:
            instrument.reference_no = cls._normalize_text(reference_no)[:120]
        if instrument_no:
            instrument.instrument_no = cls._normalize_text(instrument_no)[:50]
        if instrument_date is not None:
            instrument.instrument_date = instrument_date
        if bank_name:
            instrument.bank_name = cls._normalize_text(bank_name)[:100]
        if cheque_leaf:
            instrument.cheque_leaf = cheque_leaf
            instrument.instrument_no = cheque_leaf.leaf_no

        if target == TreasuryPaymentInstrument.Status.CLEARED:
            instrument.cleared_at = now
            instrument.failed_at = None
            instrument.cancelled_at = None
        elif target in {TreasuryPaymentInstrument.Status.FAILED, TreasuryPaymentInstrument.Status.BOUNCED}:
            instrument.failed_at = now
            instrument.cleared_at = None
            instrument.cancelled_at = None
        elif target in {TreasuryPaymentInstrument.Status.CANCELLED, TreasuryPaymentInstrument.Status.STALE, TreasuryPaymentInstrument.Status.REVERSED}:
            instrument.cancelled_at = now
            if target != TreasuryPaymentInstrument.Status.REVERSED:
                instrument.cleared_at = None
            if target != TreasuryPaymentInstrument.Status.STALE:
                instrument.failed_at = None
        elif target in {TreasuryPaymentInstrument.Status.PREPARED, TreasuryPaymentInstrument.Status.SENT_TO_BANK, TreasuryPaymentInstrument.Status.EXPORTED}:
            instrument.cleared_at = None
            instrument.failed_at = None
            instrument.cancelled_at = None

        instrument.metadata_json = metadata
        cls._sync_cheque_leaf_status(
            instrument=instrument,
            target_status=target,
            action=action,
            cheque_leaf=cheque_leaf,
            user_id=user_id,
            reason=normalized_reason,
        )
        instrument.save(
            update_fields=[
                "status",
                "reference_no",
                "instrument_no",
                "instrument_date",
                "bank_name",
                "cheque_leaf",
                "status_reason",
                "cleared_at",
                "failed_at",
                "cancelled_at",
                "metadata_json",
                "updated_at",
            ]
        )
        cls._log_status(
            batch=instrument.batch,
            old_status=old_status,
            new_status=target,
            user_id=user_id,
            comment=comment or normalized_reason,
            payload={
                "scope": "instrument",
                "instrument_id": str(instrument.id),
                "action": action,
                "reference_no": instrument.reference_no,
                "instrument_no": instrument.instrument_no,
                "cheque_leaf_id": str(instrument.cheque_leaf_id) if instrument.cheque_leaf_id else "",
                "reason": normalized_reason,
            },
        )
        return instrument

    @staticmethod
    def _log_status(
        *,
        batch: TreasuryPaymentBatch,
        old_status: str,
        new_status: str,
        user_id: int | None = None,
        comment: str = "",
        payload: dict | None = None,
    ) -> None:
        TreasuryPaymentStatusLog.objects.create(
            batch=batch,
            old_status=old_status or "",
            new_status=new_status,
            acted_by_id=user_id,
            comment=comment or "",
            payload=payload or {},
        )

    @classmethod
    def list_vendor_payable_candidates(cls, *, entity_id: int, entityfinid_id: int, subentity_id: int | None = None):
        qs = VendorBillOpenItem.objects.select_related("header", "vendor").filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            is_open=True,
            outstanding_amount__gt=ZERO2,
        )
        if subentity_id:
            qs = qs.filter(subentity_id=subentity_id)
        active_ids = TreasuryPaymentBatchLine.objects.filter(
            batch__status__in=ACTIVE_BATCH_STATUSES,
            vendor_open_item_id__isnull=False,
        ).values_list("vendor_open_item_id", flat=True)
        return qs.exclude(pk__in=active_ids).order_by("due_date", "bill_date", "id")
