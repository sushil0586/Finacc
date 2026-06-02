from django.db import transaction

from assets.seeding import AssetSeedService
from catalog.seeding import CatalogSeedService
from entity.models import Constitution, GstRegistrationType
from entity.policy import EntityPolicyService
from entity.seed_catalogs import ENTITY_MASTER_CATALOG
from financial.seeding import FinancialSeedService
from financial.services import get_or_create_financial_settings, resync_ledgers
from numbering.seeding import NumberingSeedService
from posting.services.static_accounts import StaticAccountService
from purchase.seeding import PurchaseSeedService
from rbac.seeding import RBACSeedService
from sales.seeding import SalesSeedService


class EntitySeedService:
    """
    Seed and normalize entity-domain master data.

    This is intentionally idempotent so it can be used safely in local setup,
    onboarding preparation, staging refreshes, or production repair runs.
    """

    @classmethod
    @transaction.atomic
    def seed_master_data(cls, *, actor=None, include_inactive=False):
        gst_types = cls._seed_gst_registration_types(actor=actor)
        constitutions = cls._seed_constitutions(actor=actor)
        if not include_inactive:
            cls._reactivate_seeded_rows(
                gst_types=gst_types,
                constitutions=constitutions,
            )

        return {
            "gst_registration_type_count": len(gst_types),
            "constitution_count": len(constitutions),
        }

    @classmethod
    @transaction.atomic
    def repair_entity_bootstrap(
        cls,
        *,
        entity,
        actor=None,
        include_policy=True,
        include_static_account_master=True,
        include_financial=True,
        include_financial_resync=True,
        include_rbac=True,
        include_numbering=True,
        include_catalog=True,
        include_assets=True,
        include_purchase_choices=True,
        include_sales_choices=True,
        include_inactive_scopes=False,
    ):
        """
        Bring a legacy entity up to the current onboarding baseline.
        """
        from entity.models import EntityFinancialYear, SubEntity
        from entity.onboarding_services import DEFAULT_NUMBERING_SPECS

        actor = actor or getattr(entity, "createdby", None)
        summary = {
            "entity_id": entity.id,
            "entity_name": str(entity),
        }

        if include_policy:
            policy = EntityPolicyService.ensure_policy(entity=entity, actor=actor)
            summary["policy"] = {
                "policy_id": policy.id,
                "createdby_id": policy.createdby_id,
            }

        if include_static_account_master:
            summary["posting_static_accounts"] = StaticAccountService.seed_static_account_master()

        if include_financial:
            settings_obj, settings_created = get_or_create_financial_settings(entity, createdby=actor)
            financial_summary = FinancialSeedService.reconcile_entity(
                entity=entity,
                actor=actor,
                template_code=FinancialSeedService.DEFAULT_TEMPLATE,
            )
            financial_summary["financial_settings_id"] = settings_obj.id
            financial_summary["financial_settings_created"] = settings_created
            summary["financial"] = financial_summary

        if include_financial_resync:
            summary["financial_resync"] = {
                "ledgers_synced": resync_ledgers(entity_id=entity.id),
            }

        if include_rbac:
            if actor is None:
                summary["rbac"] = {
                    "skipped": True,
                    "reason": "no_actor_available",
                }
            else:
                summary["rbac"] = RBACSeedService.seed_entity(
                    entity=entity,
                    actor=actor,
                    seed_default_roles=True,
                )

        if include_numbering:
            fy_qs = EntityFinancialYear.objects.filter(entity=entity)
            sub_qs = SubEntity.objects.filter(entity=entity)
            if not include_inactive_scopes:
                fy_qs = fy_qs.filter(isactive=True)
                sub_qs = sub_qs.filter(isactive=True)

            fy_ids = list(fy_qs.order_by("id").values_list("id", flat=True))
            subentity_ids = list(sub_qs.order_by("id").values_list("id", flat=True))
            numbering_rows = []
            for fy_id in fy_ids:
                for subentity_id in [None, *subentity_ids]:
                    numbering_rows.extend(
                        NumberingSeedService.seed_documents(
                            entity_id=entity.id,
                            entityfinid_id=fy_id,
                            subentity_id=subentity_id,
                            specs=DEFAULT_NUMBERING_SPECS,
                        )
                    )

            summary["numbering"] = {
                "financial_year_count": len(fy_ids),
                "subentity_scope_count": len([None, *subentity_ids]),
                "series_touched": len(numbering_rows),
            }

        if include_catalog:
            summary["catalog"] = CatalogSeedService.seed_entity(entity=entity)

        if include_assets:
            summary["assets"] = AssetSeedService.seed_entity(entity=entity, actor=actor)

        if include_purchase_choices:
            summary["purchase_choice_overrides"] = PurchaseSeedService.seed_choice_overrides(
                entity=entity,
                subentity=None,
            )

        if include_sales_choices:
            summary["sales_choice_overrides"] = SalesSeedService.seed_choice_overrides(
                entity=entity,
                subentity=None,
            )

        return summary

    @staticmethod
    def _seed_gst_registration_types(*, actor=None):
        rows = []
        for spec in ENTITY_MASTER_CATALOG["gst_registration_types"]:
            obj = GstRegistrationType.objects.filter(Name=spec["name"]).order_by("id").first()
            if obj is None:
                obj = GstRegistrationType.objects.create(
                    Name=spec["name"],
                    Description=spec["description"],
                )
            obj.Description = spec["description"]
            obj.save(update_fields=["Description"])
            rows.append(obj)
        return rows

    @staticmethod
    def _seed_constitutions(*, actor=None):
        rows = []
        for spec in ENTITY_MASTER_CATALOG["constitutions"]:
            obj = Constitution.objects.filter(constcode=spec["code"]).order_by("id").first()
            if obj is None:
                obj = Constitution.objects.create(
                    constcode=spec["code"],
                    constitutionname=spec["name"],
                    constitutiondesc=spec["description"],
                    createdby=actor,
                )
            obj.constitutionname = spec["name"]
            obj.constitutiondesc = spec["description"]
            if actor and not obj.createdby_id:
                obj.createdby = actor
                obj.save(update_fields=["constitutionname", "constitutiondesc", "createdby"])
            else:
                obj.save(update_fields=["constitutionname", "constitutiondesc"])
            rows.append(obj)
        return rows

    @staticmethod
    def _reactivate_seeded_rows(*, gst_types, constitutions):
        for row in [*gst_types, *constitutions]:
            if hasattr(row, "isactive") and not row.isactive:
                row.isactive = True
                row.save(update_fields=["isactive"])
