from __future__ import annotations

from datetime import date
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from receipts.models.receipt_core import ReceiptVoucherAdvanceAdjustment, ReceiptVoucherHeader
from receipts.services.receipt_voucher_service import ReceiptVoucherService


class Command(BaseCommand):
    help = "Rebuild GSTR-1 Table 11 rows from posted receipt vouchers."

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, required=True, help="Entity ID")
        parser.add_argument("--entityfinid", type=int, required=True, help="Entity Financial Year ID")
        parser.add_argument("--subentity", type=int, default=None, help="Optional subentity ID")
        parser.add_argument("--from-date", type=str, default=None, help="Optional from date (YYYY-MM-DD)")
        parser.add_argument("--to-date", type=str, default=None, help="Optional to date (YYYY-MM-DD)")
        parser.add_argument(
            "--track-amendments",
            action="store_true",
            help="When set, snapshot amendment rows are created for changed/removed rows.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show affected voucher count only, without writing changes.",
        )

    @staticmethod
    def _parse_date(value: Optional[str], label: str) -> Optional[date]:
        if not value:
            return None
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            raise CommandError(f"{label} must be YYYY-MM-DD.") from exc

    def handle(self, *args, **options):
        entity_id = int(options["entity"])
        entityfinid_id = int(options["entityfinid"])
        subentity_id = options.get("subentity")
        from_date = self._parse_date(options.get("from_date"), "--from-date")
        to_date = self._parse_date(options.get("to_date"), "--to-date")
        track_amendments = bool(options.get("track_amendments"))
        dry_run = bool(options.get("dry_run"))

        if from_date and to_date and from_date > to_date:
            raise CommandError("--from-date cannot be greater than --to-date.")

        qs = ReceiptVoucherHeader.objects.filter(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            status=ReceiptVoucherHeader.Status.POSTED,
        ).only("id", "entity_id", "entityfinid_id", "subentity_id", "voucher_date")

        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        if from_date:
            qs = qs.filter(voucher_date__gte=from_date)
        if to_date:
            qs = qs.filter(voucher_date__lte=to_date)

        voucher_ids = list(qs.values_list("id", flat=True))
        total = len(voucher_ids)
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY RUN] Eligible posted vouchers for Table 11 rebuild: {total}"
                )
            )
            return

        updated = 0
        failed = 0
        for voucher_id in voucher_ids:
            try:
                with transaction.atomic():
                    header = ReceiptVoucherHeader.objects.get(pk=voucher_id)
                    live_rows = list(
                        ReceiptVoucherAdvanceAdjustment.objects.filter(receipt_voucher_id=voucher_id)
                        .select_related("open_item", "advance_balance__receipt_voucher")
                        .order_by("id")
                    )
                    ReceiptVoucherService._sync_gstr1_table11_rows(
                        header=header,
                        live_advance_rows=live_rows,
                        track_amendments=track_amendments,
                    )
                updated += 1
            except Exception as exc:  # noqa: BLE001 - command should continue and report all failures
                failed += 1
                self.stderr.write(
                    self.style.ERROR(f"Voucher {voucher_id}: failed ({exc})")
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Table 11 rebuild completed. Processed={total}, Updated={updated}, Failed={failed}, "
                f"TrackAmendments={'on' if track_amendments else 'off'}"
            )
        )
