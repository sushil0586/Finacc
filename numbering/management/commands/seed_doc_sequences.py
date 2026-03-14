from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from numbering.seeding import NumberingSeedService, NumberingSeedSpec


DEFAULT_DOC_TYPES = {
    "SINV": ("sales", "sales_invoice", "Sales Invoice", "SINV"),
    "SCN": ("sales", "sales_credit_note", "Sales Credit Note", "SCN"),
    "SDN": ("sales", "sales_debit_note", "Sales Debit Note", "SDN"),
    "PINV": ("purchase", "PURCHASE_TAX_INVOICE", "Purchase Invoice", "PINV"),
    "PCN": ("purchase", "PURCHASE_CREDIT_NOTE", "Purchase Credit Note", "PCN"),
    "PDN": ("purchase", "PURCHASE_DEBIT_NOTE", "Purchase Debit Note", "PDN"),
    "RV": ("receipts", "RECEIPT_VOUCHER", "Receipt Voucher", "RV"),
    "PV": ("payments", "PAYMENT_VOUCHER", "Payment Voucher", "PPV"),
    "CV": ("vouchers", "cash_voucher", "Cash Voucher", "CV"),
    "BV": ("vouchers", "bank_voucher", "Bank Voucher", "BV"),
    "JV": ("vouchers", "JOURNAL_VOUCHER", "Journal Voucher", "JV"),
    "FA": ("assets", "asset_capitalization", "Asset Capitalization", "FA"),
    "FAD": ("assets", "asset_disposal", "Asset Disposal", "FAD"),
}


class Command(BaseCommand):
    help = "Seed document type + numbering series together using the current numbering schema."

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, required=True, help="Entity ID")
        parser.add_argument("--entityfinid", type=int, required=True, help="Entity Financial Year ID")
        parser.add_argument("--subentity", type=int, default=None, help="Optional subentity ID")
        parser.add_argument("--doc-code", type=str, default=None, help="Limit to one default doc code, e.g. JV")
        parser.add_argument("--module", type=str, default=None, help="Custom module for one-off seed")
        parser.add_argument("--doc-key", type=str, default=None, help="Custom document key for one-off seed")
        parser.add_argument("--name", type=str, default=None, help="Custom document name for one-off seed")
        parser.add_argument("--default-code", type=str, default=None, help="Custom default code for one-off seed")
        parser.add_argument("--prefix", type=str, default=None, help="Custom visible prefix. Defaults to default-code.")
        parser.add_argument("--start", type=int, default=1, help="Starting/current number")
        parser.add_argument("--padding", type=int, default=5, help="Number padding")
        parser.add_argument("--reset", type=str, default="yearly", choices=["none", "monthly", "yearly"])

    @transaction.atomic
    def handle(self, *args, **opts):
        entity_id = int(opts["entity"])
        entityfinid_id = int(opts["entityfinid"])
        subentity_id = opts.get("subentity")
        start = int(opts["start"])
        padding = int(opts["padding"])
        reset = opts["reset"]
        target_code = (opts.get("doc_code") or "").strip().upper() or None
        custom_module = (opts.get("module") or "").strip().lower() or None
        custom_doc_key = (opts.get("doc_key") or "").strip().upper() or None
        custom_name = (opts.get("name") or "").strip() or None
        custom_default_code = (opts.get("default_code") or "").strip().upper() or None
        custom_prefix = (opts.get("prefix") or "").strip().upper() or None

        if start < 1:
            raise CommandError("--start must be >= 1")
        if padding < 0:
            raise CommandError("--padding must be >= 0")

        if any([custom_module, custom_doc_key, custom_name, custom_default_code]):
            if not all([custom_module, custom_doc_key, custom_name, custom_default_code]):
                raise CommandError("Custom seeding requires --module, --doc-key, --name, and --default-code together.")
            specs = [
                NumberingSeedSpec(
                    module=custom_module,
                    doc_key=custom_doc_key,
                    name=custom_name,
                    default_code=custom_default_code,
                    prefix=custom_prefix or custom_default_code,
                    start=start,
                    padding=padding,
                    reset=reset,
                )
            ]
        else:
            items = DEFAULT_DOC_TYPES
            if target_code:
                if target_code not in items:
                    raise CommandError(f"Unsupported --doc-code '{target_code}'.")
                items = {target_code: items[target_code]}
            specs = [
                NumberingSeedSpec(
                    module=module,
                    doc_key=doc_key,
                    name=name,
                    default_code=default_code,
                    prefix=default_code,
                    start=start,
                    padding=padding,
                    reset=reset,
                )
                for _, (module, doc_key, name, default_code) in items.items()
            ]

        output = []
        for row in NumberingSeedService.seed_documents(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
            specs=specs,
        ):
            output.append(
                f"{row['module']}/{row['doc_key']}: dt={row['doc_type_id']}, series={row['series_id']}, created={row['series_created']}"
            )

        self.stdout.write(self.style.SUCCESS("Seeded document sequences -> " + "; ".join(output)))
