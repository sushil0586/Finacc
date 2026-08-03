from __future__ import annotations

from django.core.management.base import BaseCommand

from payments.services.payment_voucher_repair import audit_posted_payment_voucher_settlement_mismatches


class Command(BaseCommand):
    help = (
        "Audit posted payment vouchers for mismatches between header settlement support, "
        "saved allocations, and linked AP settlement totals. Dry-run by default."
    )

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, dest="entity_id")
        parser.add_argument("--subentity-id", type=int, dest="subentity_id")
        parser.add_argument("--voucher-id", type=int, dest="voucher_id")
        parser.add_argument("--voucher-code", dest="voucher_code")
        parser.add_argument("--apply", action="store_true", dest="apply")

    def handle(self, *args, **options):
        apply = bool(options.get("apply"))
        summary = audit_posted_payment_voucher_settlement_mismatches(
            entity_id=options.get("entity_id"),
            subentity_id=options.get("subentity_id"),
            voucher_id=options.get("voucher_id"),
            voucher_code=options.get("voucher_code"),
            apply=apply,
        )

        mode = "APPLY" if apply else "DRY RUN"
        self.stdout.write(self.style.SUCCESS(f"Payment voucher settlement audit ({mode})"))
        self.stdout.write(f"  scanned_vouchers: {summary['scanned_vouchers']}")
        self.stdout.write(f"  flagged_vouchers: {summary['flagged_vouchers']}")
        self.stdout.write(f"  repaired_vouchers: {summary['repaired_vouchers']}")
        self.stdout.write(f"  allocation_repairs: {summary['allocation_repairs']}")

        for row in summary["rows"]:
            if row["mismatch_kind"] == "ok":
                continue
            self.stdout.write(
                "  row:"
                f" voucher_id={row['voucher_id']}"
                f" voucher={row['voucher_code'] or '-'}"
                f" vendor={row['vendor_id']}"
                f" payment_type={row['payment_type']}"
                f" support={row['support_total']}"
                f" alloc={row['allocation_total']}"
                f" settlement={row['settlement_total']}"
                f" kind={row['mismatch_kind']}"
                f" repairable={row['repairable']}"
                f" action={row['repair_action'] or '-'}"
                f" note={row['note'] or '-'}"
            )
