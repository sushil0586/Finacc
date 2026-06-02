from django.core.management.base import BaseCommand, CommandError

from Authentication.models import User
from entity.models import Entity
from entity.seeding import EntitySeedService


class Command(BaseCommand):
    help = (
        "Repair/bootstrap legacy entities so they receive the current onboarding baseline "
        "(policy, financial, RBAC, numbering, catalog, assets, and choice overrides)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, default=None, help="Repair one entity by id.")
        parser.add_argument("--all-entities", action="store_true", help="Repair every entity.")
        parser.add_argument("--actor-id", type=int, default=None, help="Optional actor for RBAC/policy ownership.")
        parser.add_argument("--include-inactive-scopes", action="store_true", help="Also seed inactive FY/subentity numbering scopes.")
        parser.add_argument("--skip-policy", action="store_true")
        parser.add_argument("--skip-static-account-master", action="store_true")
        parser.add_argument("--skip-financial", action="store_true")
        parser.add_argument("--skip-financial-resync", action="store_true")
        parser.add_argument("--skip-rbac", action="store_true")
        parser.add_argument("--skip-numbering", action="store_true")
        parser.add_argument("--skip-catalog", action="store_true")
        parser.add_argument("--skip-assets", action="store_true")
        parser.add_argument("--skip-purchase-choices", action="store_true")
        parser.add_argument("--skip-sales-choices", action="store_true")

    def handle(self, *args, **options):
        entity_id = options["entity_id"]
        all_entities = bool(options["all_entities"])
        actor_id = options["actor_id"]

        if bool(entity_id) == bool(all_entities):
            raise CommandError("Provide exactly one of --entity-id or --all-entities.")

        actor = None
        if actor_id is not None:
            actor = User.objects.filter(pk=actor_id).first()
            if actor is None:
                raise CommandError(f"Actor {actor_id} does not exist.")

        if entity_id is not None:
            entities = list(Entity.objects.filter(pk=entity_id).order_by("id"))
            if not entities:
                raise CommandError(f"Entity {entity_id} does not exist.")
        else:
            entities = list(Entity.objects.order_by("id"))
            if not entities:
                raise CommandError("No entities found.")

        failures = []
        for entity in entities:
            effective_actor = actor or getattr(entity, "createdby", None)
            self.stdout.write(self.style.MIGRATE_HEADING(f"Repairing entity {entity.id} - {entity}"))
            try:
                summary = EntitySeedService.repair_entity_bootstrap(
                    entity=entity,
                    actor=effective_actor,
                    include_policy=not options["skip_policy"],
                    include_static_account_master=not options["skip_static_account_master"],
                    include_financial=not options["skip_financial"],
                    include_financial_resync=not options["skip_financial_resync"],
                    include_rbac=not options["skip_rbac"],
                    include_numbering=not options["skip_numbering"],
                    include_catalog=not options["skip_catalog"],
                    include_assets=not options["skip_assets"],
                    include_purchase_choices=not options["skip_purchase_choices"],
                    include_sales_choices=not options["skip_sales_choices"],
                    include_inactive_scopes=bool(options["include_inactive_scopes"]),
                )
            except Exception as exc:  # noqa: BLE001
                failures.append((entity.id, str(exc)))
                self.stdout.write(self.style.ERROR(f"Failed entity {entity.id}: {exc}"))
                continue

            self.stdout.write(self.style.SUCCESS(f"Repair complete for entity {entity.id}."))
            self._print_summary(summary)

        if failures:
            self.stdout.write(self.style.ERROR("Some entities failed during repair:"))
            for failed_entity_id, message in failures:
                self.stdout.write(f"  - entity {failed_entity_id}: {message}")
            raise CommandError(f"Repair finished with {len(failures)} failure(s).")

        self.stdout.write(self.style.SUCCESS(f"Repair completed successfully for {len(entities)} entit(y/ies)."))

    def _print_summary(self, summary):
        financial = summary.get("financial") or {}
        if financial:
            self.stdout.write(
                "  financial: "
                f"settings={financial.get('financial_settings_id')} "
                f"default_accounts={financial.get('default_account_count')} "
                f"corrected_default_ledgers={financial.get('corrected_default_ledgers')} "
                f"corrected_party_ledgers={financial.get('corrected_party_ledgers')}"
            )

        financial_resync = summary.get("financial_resync") or {}
        if financial_resync:
            self.stdout.write(f"  financial_resync: ledgers_synced={financial_resync.get('ledgers_synced')}")

        policy = summary.get("policy") or {}
        if policy:
            self.stdout.write(f"  policy: policy_id={policy.get('policy_id')}")

        posting = summary.get("posting_static_accounts") or {}
        if posting:
            self.stdout.write(
                "  posting_static_accounts: "
                f"created={posting.get('created')} updated={posting.get('updated')}"
            )

        rbac = summary.get("rbac") or {}
        if rbac:
            if rbac.get("skipped"):
                self.stdout.write(f"  rbac: skipped ({rbac.get('reason')})")
            else:
                self.stdout.write(
                    "  rbac: "
                    f"admin_role={rbac.get('rbac_admin_role_id')} "
                    f"shell_roles={len(rbac.get('shell_role_ids') or [])}"
                )

        numbering = summary.get("numbering") or {}
        if numbering:
            self.stdout.write(
                "  numbering: "
                f"financial_years={numbering.get('financial_year_count')} "
                f"scopes={numbering.get('subentity_scope_count')} "
                f"series_touched={numbering.get('series_touched')}"
            )

        catalog = summary.get("catalog") or {}
        if catalog:
            self.stdout.write(
                "  catalog: "
                f"categories={catalog.get('categories_created', 0) + catalog.get('categories_updated', 0)} "
                f"uoms={catalog.get('uoms_created', 0) + catalog.get('uoms_updated', 0)} "
                f"hsn={catalog.get('hsn_created', 0) + catalog.get('hsn_updated', 0)}"
            )

        assets = summary.get("assets") or {}
        if assets:
            self.stdout.write(
                "  assets: "
                f"categories_created={assets.get('categories_created')} "
                f"categories_backfilled={assets.get('categories_backfilled')} "
                f"ledgers_created={assets.get('ledgers_created')} "
                f"ledgers_backfilled={assets.get('ledgers_backfilled')}"
            )

        purchase = summary.get("purchase_choice_overrides") or {}
        if purchase:
            self.stdout.write(
                "  purchase_choice_overrides: "
                f"created={purchase.get('created')} updated={purchase.get('updated')}"
            )

        sales = summary.get("sales_choice_overrides") or {}
        if sales:
            self.stdout.write(
                "  sales_choice_overrides: "
                f"created={sales.get('created')} updated={sales.get('updated')}"
            )
