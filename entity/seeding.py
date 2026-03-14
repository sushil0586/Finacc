from django.db import transaction

from entity.models import Constitution, GstRegistrationType, OwnerShipTypes, UnitType
from entity.seed_catalogs import ENTITY_MASTER_CATALOG


class EntitySeedService:
    """
    Seed and normalize entity-domain master data.

    This is intentionally idempotent so it can be used safely in local setup,
    onboarding preparation, staging refreshes, or production repair runs.
    """

    @classmethod
    @transaction.atomic
    def seed_master_data(cls, *, actor=None, include_inactive=False):
        unit_types = cls._seed_unit_types(actor=actor)
        gst_types = cls._seed_gst_registration_types(actor=actor)
        constitutions = cls._seed_constitutions(actor=actor)
        ownership_types = cls._seed_ownership_types(actor=actor)

        if not include_inactive:
            cls._reactivate_seeded_rows(
                unit_types=unit_types,
                gst_types=gst_types,
                constitutions=constitutions,
                ownership_types=ownership_types,
            )

        return {
            "unit_type_count": len(unit_types),
            "gst_registration_type_count": len(gst_types),
            "constitution_count": len(constitutions),
            "ownership_type_count": len(ownership_types),
        }

    @staticmethod
    def _seed_unit_types(*, actor=None):
        rows = []
        for spec in ENTITY_MASTER_CATALOG["unit_types"]:
            obj, _ = UnitType.objects.get_or_create(
                UnitName=spec["name"],
                defaults={"UnitDesc": spec["description"]},
            )
            obj.UnitDesc = spec["description"]
            obj.save(update_fields=["UnitDesc"])
            rows.append(obj)
        return rows

    @staticmethod
    def _seed_gst_registration_types(*, actor=None):
        rows = []
        for spec in ENTITY_MASTER_CATALOG["gst_registration_types"]:
            obj, _ = GstRegistrationType.objects.get_or_create(
                Name=spec["name"],
                defaults={"Description": spec["description"]},
            )
            obj.Description = spec["description"]
            obj.save(update_fields=["Description"])
            rows.append(obj)
        return rows

    @staticmethod
    def _seed_constitutions(*, actor=None):
        rows = []
        for spec in ENTITY_MASTER_CATALOG["constitutions"]:
            obj, _ = Constitution.objects.get_or_create(
                constcode=spec["code"],
                defaults={
                    "constitutionname": spec["name"],
                    "constitutiondesc": spec["description"],
                    "createdby": actor,
                },
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
    def _seed_ownership_types(*, actor=None):
        rows = []
        for spec in ENTITY_MASTER_CATALOG["ownership_types"]:
            obj, _ = OwnerShipTypes.objects.get_or_create(
                Name=spec["name"],
                defaults={"Description": spec["description"]},
            )
            obj.Description = spec["description"]
            obj.save(update_fields=["Description"])
            rows.append(obj)
        return rows

    @staticmethod
    def _reactivate_seeded_rows(*, unit_types, gst_types, constitutions, ownership_types):
        for row in [*unit_types, *gst_types, *constitutions, *ownership_types]:
            if hasattr(row, "isactive") and not row.isactive:
                row.isactive = True
                row.save(update_fields=["isactive"])
