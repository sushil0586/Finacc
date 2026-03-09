from django.db import transaction

from entity.models import BankAccount, Entity, EntityConstitution, EntityDetail, EntityFinancialYear, SubEntity
from financial.seeding import FinancialSeedService
from rbac.seeding import RBACSeedService


class EntityOnboardingService:
    """
    New entity onboarding flow.

    This is intentionally parallel to the legacy serializer-driven create path.
    It keeps the old endpoint untouched and moves the new onboarding transaction
    into explicit services so entity, financial, and RBAC defaults are seeded in
    a predictable and testable way.
    """

    @classmethod
    @transaction.atomic
    def create_entity(cls, *, actor, payload):
        entity_data = dict(payload["entity"])
        detail_data = dict(payload.get("entity_detail") or {})
        fy_rows = [dict(row) for row in payload.get("financial_years", [])]
        bank_rows = [dict(row) for row in payload.get("bank_accounts", [])]
        subentity_rows = [dict(row) for row in payload.get("subentities", [])]
        constitution_rows = [dict(row) for row in payload.get("constitution_details", [])]
        seed_options = dict(payload.get("seed_options") or {})

        entity = Entity.objects.create(createdby=actor, **entity_data)

        detail = None
        if detail_data:
            detail_defaults = {
                "email": entity.email,
                "gstno": entity.gstno,
                "gstintype": entity.gstintype,
            }
            detail_defaults.update(detail_data)
            detail = EntityDetail.objects.update_or_create(entity=entity, defaults=detail_defaults)[0]

        fy_ids = []
        active_rows = [row for row in fy_rows if row.get("isactive")]
        if not active_rows and fy_rows:
            fy_rows[0]["isactive"] = True

        for row in fy_rows:
            fy = EntityFinancialYear.objects.create(entity=entity, createdby=actor, **row)
            fy_ids.append(fy.id)

        bank_ids = []
        for row in bank_rows:
            bank = BankAccount.objects.create(entity=entity, **row)
            bank_ids.append(bank.id)

        subentity_ids = []
        if subentity_rows:
            for row in subentity_rows:
                subentity = SubEntity.objects.create(entity=entity, **row)
                subentity_ids.append(subentity.id)
        elif seed_options.get("seed_default_subentity", True):
            subentity = SubEntity.objects.create(
                entity=entity,
                subentityname="Main-Branch",
                address=entity.address,
                country=entity.country,
                state=entity.state,
                district=entity.district,
                city=entity.city,
                pincode=entity.pincode,
                phoneoffice=entity.phoneoffice,
                phoneresidence=entity.phoneresidence,
                email=entity.email,
                ismainentity=True,
                isactive=True,
            )
            subentity_ids.append(subentity.id)

        constitution_ids = []
        for row in constitution_rows:
            constitution = EntityConstitution.objects.create(entity=entity, createdby=actor, **row)
            constitution_ids.append(constitution.id)

        financial_summary = {}
        if seed_options.get("seed_financial", True):
            financial_summary = FinancialSeedService.seed_entity(
                entity=entity,
                actor=actor,
                template_code=seed_options.get("template_code"),
            )

        rbac_summary = {}
        if seed_options.get("seed_rbac", True):
            rbac_summary = RBACSeedService.seed_entity(
                entity=entity,
                actor=actor,
                seed_default_roles=seed_options.get("seed_default_roles", True),
            )

        return {
            "entity": entity,
            "entity_detail": detail,
            "financial_year_ids": fy_ids,
            "bank_account_ids": bank_ids,
            "subentity_ids": subentity_ids,
            "constitution_ids": constitution_ids,
            "financial": financial_summary,
            "rbac": rbac_summary,
        }
