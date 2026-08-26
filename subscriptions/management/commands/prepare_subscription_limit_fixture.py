from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from entity.models import Entity
from subscriptions.models import PlanLimit, UserEntityAccess
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


User = get_user_model()


class Command(BaseCommand):
    help = (
        "Audit or prepare a capped subscription-limit fixture for a tenant owner. "
        "Dry-run is the default. Use --apply to cap selected limits at current usage, "
        "and --restore to put back previously recorded values."
    )

    metadata_key = "signoff_fixture_previous_value"
    prepared_at_key = "signoff_fixture_prepared_at"

    def add_arguments(self, parser):
        parser.add_argument("--owner-email", required=True, help="Owner email for the tenant to inspect.")
        parser.add_argument(
            "--dimension",
            choices=["entities", "users", "both"],
            default="both",
            help="Which quota dimension to inspect or cap.",
        )
        parser.add_argument("--apply", action="store_true", help="Apply the capped fixture.")
        parser.add_argument("--restore", action="store_true", help="Restore limits from previously recorded fixture metadata.")

    def handle(self, *args, **options):
        owner_email = options["owner_email"].strip().lower()
        dimension = options["dimension"]
        apply_changes = bool(options["apply"])
        restore = bool(options["restore"])

        if apply_changes and restore:
            raise CommandError("Use either --apply or --restore, not both.")

        owner = User.objects.filter(email__iexact=owner_email).first()
        if owner is None:
            raise CommandError(f"No user found for owner email {owner_email}.")

        account = SubscriptionService.ensure_customer_account(user=owner)
        subscription = SubscriptionService.ensure_active_subscription(customer_account=account)
        plan = subscription.plan
        SubscriptionService.ensure_plan_limit_catalog(plan=plan)

        entities_used = Entity.objects.filter(
            customer_account=account,
            isactive=True,
        ).count()
        users_used = UserEntityAccess.objects.filter(
            customer_account=account,
            is_active=True,
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
        ).count()

        entity_limit_row = PlanLimit.objects.get(plan=plan, key=SubscriptionLimitCodes.MAX_ENTITIES)
        user_limit_row = PlanLimit.objects.get(plan=plan, key=SubscriptionLimitCodes.MAX_ENTITY_USERS)

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Tenant quota fixture audit for {owner_email} -> account {account.id} ({account.slug})"
        ))
        self.stdout.write(
            f"Plan: {plan.code} | "
            f"Entities used {entities_used}/{entity_limit_row.value if entity_limit_row.value is not None else '∞'} | "
            f"Users used {users_used}/{user_limit_row.value if user_limit_row.value is not None else '∞'}"
        )

        if restore:
            restored = 0
            restored += self._restore_limit(entity_limit_row, selected=dimension in {"entities", "both"})
            restored += self._restore_limit(user_limit_row, selected=dimension in {"users", "both"})
            if restored == 0:
                self.stdout.write(self.style.WARNING("No recorded fixture metadata found for the selected dimensions."))
                return
            self.stdout.write(self.style.SUCCESS(f"Restored {restored} limit row(s)."))
            return

        self._print_dimension_summary(
            label="Entities",
            selected=dimension in {"entities", "both"},
            used=entities_used,
            limit_row=entity_limit_row,
        )
        self._print_dimension_summary(
            label="Users",
            selected=dimension in {"users", "both"},
            used=users_used,
            limit_row=user_limit_row,
        )

        if not apply_changes:
            self.stdout.write(self.style.WARNING("Dry run only. Re-run with --apply to cap selected limits at current usage."))
            return

        updated = 0
        if dimension in {"entities", "both"}:
            updated += self._cap_limit_at_current_usage(entity_limit_row, entities_used)
        if dimension in {"users", "both"}:
            updated += self._cap_limit_at_current_usage(user_limit_row, users_used)

        self.stdout.write(self.style.SUCCESS(f"Prepared capped fixture for {updated} limit row(s)."))

    def _print_dimension_summary(self, *, label, selected, used, limit_row):
        if not selected:
            return
        current_limit = limit_row.value
        previous_value = (limit_row.metadata or {}).get(self.metadata_key)
        remaining = "unknown" if current_limit is None else max(int(current_limit) - int(used), 0)
        self.stdout.write(
            f"  - {label}: used={used}, limit={current_limit if current_limit is not None else '∞'}, "
            f"remaining={remaining}, recorded_previous={previous_value if previous_value is not None else '-'}"
        )

    def _cap_limit_at_current_usage(self, limit_row, used):
        current_limit = limit_row.value
        if current_limit is None:
            raise CommandError(
                f"Limit {limit_row.key} is currently unlimited. Set a concrete value before preparing a capped fixture."
            )

        metadata = dict(limit_row.metadata or {})
        if metadata.get(self.metadata_key) is None:
            metadata[self.metadata_key] = current_limit
        metadata[self.prepared_at_key] = timezone.now().isoformat()

        if int(current_limit) == int(used):
            limit_row.metadata = metadata
            limit_row.save(update_fields=["metadata", "updated_at"])
            self.stdout.write(f"  - {limit_row.key}: already capped at current usage {used}. Metadata refreshed.")
            return 1

        limit_row.int_value = int(used)
        limit_row.metadata = metadata
        limit_row.save(update_fields=["int_value", "metadata", "updated_at"])
        self.stdout.write(
            self.style.SUCCESS(
                f"  - {limit_row.key}: capped from {current_limit} to {used} for signoff fixture."
            )
        )
        return 1

    def _restore_limit(self, limit_row, *, selected):
        if not selected:
            return 0
        metadata = dict(limit_row.metadata or {})
        previous_value = metadata.get(self.metadata_key)
        if previous_value is None:
            return 0

        limit_row.int_value = int(previous_value)
        metadata.pop(self.metadata_key, None)
        metadata.pop(self.prepared_at_key, None)
        limit_row.metadata = metadata
        limit_row.save(update_fields=["int_value", "metadata", "updated_at"])
        self.stdout.write(
            self.style.SUCCESS(
                f"  - {limit_row.key}: restored to {previous_value}."
            )
        )
        return 1
