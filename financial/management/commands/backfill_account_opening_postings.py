from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Q

from financial.models import account
from financial.services_opening_balance import sync_account_opening_posting


class Command(BaseCommand):
    help = "Backfill posted opening balance journal entries for accounts that still only have legacy ledger master openings."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, dest="entity_id")
        parser.add_argument("--account-id", type=int, dest="account_id")
        parser.add_argument("--dry-run", action="store_true", dest="dry_run")

    def handle(self, *args, **options):
        entity_id = options.get("entity_id")
        account_id = options.get("account_id")
        dry_run = bool(options.get("dry_run"))

        queryset = (
            account.objects.select_related("ledger")
            .filter(ledger__isnull=False)
            .filter(
                Q(ledger__openingbdr__gt=Decimal("0.00"))
                | Q(ledger__openingbcr__gt=Decimal("0.00"))
            )
            .order_by("entity_id", "id")
        )
        if entity_id:
            queryset = queryset.filter(entity_id=entity_id)
        if account_id:
            queryset = queryset.filter(id=account_id)

        total = queryset.count()
        success = 0
        failures = 0

        for acc in queryset.iterator():
            opening_dr = getattr(acc.ledger, "openingbdr", None)
            opening_cr = getattr(acc.ledger, "openingbcr", None)
            label = f"Account #{acc.id} {getattr(acc, 'accountname', '')}".strip()

            if dry_run:
                self.stdout.write(
                    f"DRY RUN {label} | entity={acc.entity_id} | opening_dr={opening_dr or 0} | opening_cr={opening_cr or 0}"
                )
                continue

            try:
                sync_account_opening_posting(acc)
            except Exception as exc:
                failures += 1
                self.stderr.write(f"FAILED {label}: {exc}")
            else:
                success += 1
                self.stdout.write(self.style.SUCCESS(f"POSTED {label}"))

        if dry_run:
            self.stdout.write(self.style.WARNING(f"Dry run complete. {total} account(s) scanned."))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete. scanned={total} posted={success} failed={failures}"
            )
        )
