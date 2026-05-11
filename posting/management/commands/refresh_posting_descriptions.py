from __future__ import annotations

import re

from django.core.management.base import BaseCommand

from catalog.models import Product
from catalog.services.opening_stock_posting import catalog_opening_stock_txn_id
from entity.models import SubEntity
from payroll.models import PayrollRun
from payments.models.payment_core import PaymentVoucherHeader
from posting.common.journal_descriptions import (
    opening_stock_prefix,
    payment_document_prefix,
    payroll_prefix,
    purchase_charge_description,
    purchase_document_prefix,
    purchase_line_description,
    receipt_document_prefix,
    sales_charge_description,
    sales_document_prefix,
    sales_line_description,
    voucher_document_prefix,
)
from posting.models import JournalLine, TxnType
from purchase.models.purchase_addons import PurchaseChargeLine
from purchase.models.purchase_core import PurchaseInvoiceHeader, PurchaseInvoiceLine
from receipts.models.receipt_core import ReceiptVoucherHeader
from sales.models.sales_addons import SalesChargeLine
from sales.models.sales_core import SalesInvoiceHeader, SalesInvoiceLine
from vouchers.models.voucher_core import VoucherHeader, VoucherLine


TRAILING_SUFFIX_RE = re.compile(r"(\([^)]+\))\s*$")


def _normalize_reversal(text: str) -> tuple[bool, str]:
    raw = (text or "").strip()
    lower = raw.lower()
    if lower.startswith("reversal:"):
        return True, raw.split(":", 1)[1].strip()
    if lower.startswith("reversal |"):
        return True, raw.split("|", 1)[1].strip()
    return False, raw


def _merge_with_old_suffix(prefix: str, old_text: str) -> str:
    _, core = _normalize_reversal(old_text)
    match = TRAILING_SUFFIX_RE.search(core or "")
    if match:
        return f"{prefix} {match.group(1)}".strip()
    return prefix.strip()


class Command(BaseCommand):
    help = "Refresh JournalLine.description with clearer business context from source documents."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int)
        parser.add_argument("--txn-type", action="append")
        parser.add_argument("--limit", type=int)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        qs = JournalLine.objects.select_related("entry").order_by("id")
        if options.get("entity_id"):
            qs = qs.filter(entity_id=options["entity_id"])
        txn_types = [str(x).strip() for x in (options.get("txn_type") or []) if str(x).strip()]
        if txn_types:
            qs = qs.filter(txn_type__in=txn_types)
        if options.get("limit"):
            qs = qs[: max(int(options["limit"]), 0)]

        lines = list(qs)
        if not lines:
            self.stdout.write("No journal lines matched.")
            return

        purchase_ids = {line.txn_id for line in lines if line.txn_type in {TxnType.PURCHASE, TxnType.PURCHASE_CREDIT_NOTE, TxnType.PURCHASE_DEBIT_NOTE}}
        sales_ids = {line.txn_id for line in lines if line.txn_type in {TxnType.SALES, TxnType.SALES_CREDIT_NOTE, TxnType.SALES_DEBIT_NOTE, TxnType.SALES_RETURN}}
        payment_ids = {line.txn_id for line in lines if line.txn_type == TxnType.PAYMENT}
        receipt_ids = {line.txn_id for line in lines if line.txn_type == TxnType.RECEIPT}
        voucher_ids = {line.txn_id for line in lines if line.txn_type in {TxnType.JOURNAL, TxnType.JOURNAL_CASH, TxnType.JOURNAL_BANK}}
        payroll_ids = {line.txn_id for line in lines if line.txn_type == TxnType.PAYROLL}

        purchase_headers = {
            obj.id: obj
            for obj in PurchaseInvoiceHeader.objects.filter(id__in=purchase_ids).select_related("vendor")
        }
        sales_headers = {
            obj.id: obj
            for obj in SalesInvoiceHeader.objects.filter(id__in=sales_ids).select_related("customer")
        }
        payment_headers = {
            obj.id: obj
            for obj in PaymentVoucherHeader.objects.filter(id__in=payment_ids).select_related("paid_to", "paid_from")
        }
        receipt_headers = {
            obj.id: obj
            for obj in ReceiptVoucherHeader.objects.filter(id__in=receipt_ids).select_related("received_from", "received_in")
        }
        voucher_headers = {
            obj.id: obj
            for obj in VoucherHeader.objects.filter(id__in=voucher_ids)
        }
        payroll_runs = {
            obj.id: obj
            for obj in PayrollRun.objects.filter(id__in=payroll_ids).select_related("payroll_period")
        }

        purchase_line_map = {obj.id: obj for obj in PurchaseInvoiceLine.objects.filter(header_id__in=purchase_ids).select_related("product")}
        purchase_charge_map = {obj.id: obj for obj in PurchaseChargeLine.objects.filter(header_id__in=purchase_ids)}
        sales_line_map = {obj.id: obj for obj in SalesInvoiceLine.objects.filter(header_id__in=sales_ids).select_related("product")}
        sales_charge_map = {obj.id: obj for obj in SalesChargeLine.objects.filter(header_id__in=sales_ids)}
        voucher_line_map = {obj.id: obj for obj in VoucherLine.objects.filter(header_id__in=voucher_ids)}

        branch_cache: dict[int, str] = {
            row.id: row.subentityname
            for row in SubEntity.objects.filter(id__in={line.subentity_id for line in lines if line.subentity_id}).only("id", "subentityname")
        }
        product_cache: dict[int, Product] = {}

        updated = 0
        for line in lines:
            old_description = line.description or ""
            is_reversal, _ = _normalize_reversal(old_description)
            new_description = None

            if line.txn_type in {TxnType.PURCHASE, TxnType.PURCHASE_CREDIT_NOTE, TxnType.PURCHASE_DEBIT_NOTE}:
                header = purchase_headers.get(line.txn_id)
                if header:
                    if line.detail_id and line.detail_id in purchase_line_map:
                        new_description = purchase_line_description(header, purchase_line_map[line.detail_id])
                    elif line.detail_id and line.detail_id in purchase_charge_map:
                        new_description = purchase_charge_description(header, purchase_charge_map[line.detail_id])
                    else:
                        new_description = _merge_with_old_suffix(purchase_document_prefix(header), old_description)
            elif line.txn_type in {TxnType.SALES, TxnType.SALES_CREDIT_NOTE, TxnType.SALES_DEBIT_NOTE, TxnType.SALES_RETURN}:
                header = sales_headers.get(line.txn_id)
                if header:
                    if line.detail_id and line.detail_id in sales_line_map:
                        new_description = sales_line_description(header, sales_line_map[line.detail_id])
                    elif line.detail_id and line.detail_id in sales_charge_map:
                        new_description = sales_charge_description(header, sales_charge_map[line.detail_id])
                    else:
                        new_description = _merge_with_old_suffix(sales_document_prefix(header), old_description)
            elif line.txn_type == TxnType.PAYMENT:
                header = payment_headers.get(line.txn_id)
                if header:
                    new_description = _merge_with_old_suffix(payment_document_prefix(header), old_description)
            elif line.txn_type == TxnType.RECEIPT:
                header = receipt_headers.get(line.txn_id)
                if header:
                    new_description = _merge_with_old_suffix(receipt_document_prefix(header), old_description)
            elif line.txn_type in {TxnType.JOURNAL, TxnType.JOURNAL_CASH, TxnType.JOURNAL_BANK}:
                header = voucher_headers.get(line.txn_id)
                if header:
                    prefix = voucher_document_prefix(header)
                    voucher_line = voucher_line_map.get(line.detail_id) if line.detail_id else None
                    if voucher_line and (voucher_line.narration or "").strip():
                        new_description = f"{prefix} | {voucher_line.narration.strip()}"
                    else:
                        new_description = _merge_with_old_suffix(prefix, old_description)
            elif line.txn_type == TxnType.PAYROLL:
                run = payroll_runs.get(line.txn_id)
                if run:
                    new_description = payroll_prefix(run)
            elif line.txn_type == TxnType.OPENING_BALANCE and line.voucher_no and line.voucher_no.startswith("CAT-OPEN-"):
                entry = line.entry
                product_id = None
                try:
                    _, _, raw_product_id, raw_row_id = line.voucher_no.split("-", 3)
                    product_id = int(raw_product_id)
                    row_id = int(raw_row_id)
                except Exception:
                    row_id = None
                if product_id and row_id:
                    product = product_cache.get(product_id)
                    if product is None:
                        product = Product.objects.filter(id=product_id).only("id", "productname", "sku").first()
                        product_cache[product_id] = product
                    branch_name = branch_cache.get(entry.subentity_id or 0, "")
                    new_description = opening_stock_prefix(
                        product=product,
                        branch_name=branch_name,
                        location_name="",
                        voucher_no=line.voucher_no,
                    )
                    new_description = _merge_with_old_suffix(new_description, old_description)

            if not new_description:
                continue
            if is_reversal:
                new_description = f"Reversal | {new_description}"
            if new_description == old_description:
                continue

            if options["dry_run"]:
                self.stdout.write(f"[DRY-RUN] {line.id}: {old_description!r} -> {new_description!r}")
            else:
                JournalLine.objects.filter(pk=line.id).update(description=new_description)
            updated += 1

        self.stdout.write(f"{'Would update' if options['dry_run'] else 'Updated'} {updated} journal line description(s).")
