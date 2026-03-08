from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from numbering.services import ensure_document_type, ensure_series


DEFAULT_DOC_TYPES = {
    "SI": ("sales", "SALES_INVOICE", "Sales Invoice", "SI"),
    "SR": ("sales", "SALES_RETURN", "Sales Return", "SR"),
    "PI": ("purchase", "PURCHASE_INVOICE", "Purchase Invoice", "PI"),
    "PR": ("purchase", "PURCHASE_RETURN", "Purchase Return", "PR"),
    "RV": ("receipts", "RECEIPT_VOUCHER", "Receipt Voucher", "RV"),
    "PV": ("payments", "PAYMENT_VOUCHER", "Payment Voucher", "PPV"),
    "JV": ("vouchers", "JOURNAL_VOUCHER", "Journal Voucher", "JV"),
}


class Command(BaseCommand):
    help = "Seed generic document types and number series using the current numbering schema."

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, required=True, help="Entity ID")
        parser.add_argument("--entityfinid", type=int, required=True, help="Entity Financial Year ID")
        parser.add_argument("--subentity", type=int, default=None, help="Optional subentity ID")
        parser.add_argument("--doc-code", type=str, default=None, help="Limit to one default doc code, e.g. JV")
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

        if start < 1:
            raise CommandError("--start must be >= 1")
        if padding < 0:
            raise CommandError("--padding must be >= 0")

        items = DEFAULT_DOC_TYPES
        if target_code:
            if target_code not in items:
                raise CommandError(f"Unsupported --doc-code '{target_code}'.")
            items = {target_code: items[target_code]}

        output = []
        for code, (module, doc_key, name, default_code) in items.items():
            dt = ensure_document_type(module=module, doc_key=doc_key, name=name, default_code=default_code)
            series, created = ensure_series(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                doc_type_id=dt.id,
                doc_code=default_code,
                prefix=default_code,
                start=start,
                padding=padding,
                reset=reset,
            )
            output.append(f"{code}: dt={dt.id}, series={series.id}, created={created}")

        self.stdout.write(self.style.SUCCESS("Seeded document sequences -> " + "; ".join(output)))
