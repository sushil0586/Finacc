from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.exceptions import PermissionDenied

from Authentication.models import User
from Authentication.services import AuthOTPService
from entity.models import BankAccount, Entity, EntityConstitution, EntityDetail, EntityFinancialYear, SubEntity, UserRole
from financial.seeding import FinancialSeedService
from rbac.seeding import RBACSeedService
from rbac.models import UserRoleAssignment


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
        if not entity.entity_code:
            entity.entity_code = f"ENT{entity.id:05d}"
            entity.save(update_fields=["entity_code"])

        detail = None
        if detail_data:
            detail_defaults = {
                "gstno": entity.gstno,
                "gstintype": entity.gstintype,
            }
            # Legacy EntityDetail.email is capped at 24 chars, while Entity.email
            # supports real business email lengths. Do not implicitly mirror the
            # entity email into EntityDetail; only persist detail.email if the
            # caller explicitly sends one that fits the legacy column.
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
                if not subentity.subentity_code:
                    subentity.subentity_code = f"BR{entity.id:03d}{subentity.id:03d}"
                    subentity.save(update_fields=["subentity_code"])
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
                is_head_office=True,
                branch_type=SubEntity.BranchType.HEAD_OFFICE,
                isactive=True,
            )
            subentity.subentity_code = f"HO{entity.id:05d}"
            subentity.save(update_fields=["subentity_code"])
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

    @staticmethod
    def can_manage_entity(*, user, entity) -> bool:
        if not user or not user.is_authenticated:
            return False
        if entity.createdby_id == user.id:
            return True
        if UserRole.objects.filter(entity=entity, user=user).exists():
            return True
        return UserRoleAssignment.objects.filter(entity=entity, user=user, isactive=True).exists()

    @classmethod
    def _get_entity_detail(cls, entity):
        try:
            return entity.entitydetail
        except ObjectDoesNotExist:
            return None

    @classmethod
    def build_entity_payload(cls, *, entity):
        detail = cls._get_entity_detail(entity)
        return {
            "entity_id": entity.id,
            "entity": entity,
            "entity_detail": detail,
            "financial_years": entity.fy.all().order_by("finstartyear", "id"),
            "bank_accounts": entity.bank_accounts.all().order_by("id"),
            "subentities": entity.subentity.all().order_by("id"),
            "constitution_details": entity.constitution.all().order_by("id"),
        }

    @classmethod
    def _upsert_nested(cls, *, model, parent_instance, related_name, parent_field, items, actor=None):
        if items is None:
            return

        incoming = [dict(row) for row in items]
        existing_qs = getattr(parent_instance, related_name).all()
        existing_map = {obj.id: obj for obj in existing_qs}
        keep_ids = set()

        for row in incoming:
            row.pop(parent_field, None)
            row.pop(f"{parent_field}_id", None)
            obj_id = int(row.pop("id", 0) or 0)

            if obj_id and obj_id in existing_map:
                obj = existing_map[obj_id]
                for field, value in row.items():
                    setattr(obj, field, value)
                if hasattr(obj, "updatedby_id"):
                    obj.updatedby = actor
                obj.save()
                keep_ids.add(obj_id)
                continue

            create_kwargs = {parent_field: parent_instance}
            if actor is not None and hasattr(model, "createdby_id"):
                create_kwargs["createdby"] = actor
            obj = model.objects.create(**row, **create_kwargs)
            keep_ids.add(obj.id)

        for obj_id, obj in existing_map.items():
            if obj_id not in keep_ids:
                obj.delete()

    @classmethod
    @transaction.atomic
    def update_entity(cls, *, actor, entity, payload):
        if not cls.can_manage_entity(user=actor, entity=entity):
            raise PermissionDenied("You are not allowed to update this entity.")

        entity_data = payload.get("entity")
        if entity_data is not None:
            for field, value in dict(entity_data).items():
                setattr(entity, field, value)
            if hasattr(entity, "updatedby_id"):
                entity.updatedby = actor
            entity.save()

        detail_data = payload.get("entity_detail")
        if detail_data is not None:
            detail_defaults = dict(detail_data)
            detail_defaults.setdefault("gstno", entity.gstno)
            detail_defaults.setdefault("gstintype", entity.gstintype)
            EntityDetail.objects.update_or_create(entity=entity, defaults=detail_defaults)

        fy_rows = payload.get("financial_years")
        if fy_rows is not None:
            fy_rows = [dict(row) for row in fy_rows]
            if fy_rows and not any(row.get("isactive") for row in fy_rows):
                fy_rows[0]["isactive"] = True
            cls._upsert_nested(
                model=EntityFinancialYear,
                parent_instance=entity,
                related_name="fy",
                parent_field="entity",
                items=fy_rows,
                actor=actor,
            )

        cls._upsert_nested(
            model=BankAccount,
            parent_instance=entity,
            related_name="bank_accounts",
            parent_field="entity",
            items=payload.get("bank_accounts"),
            actor=actor,
        )
        cls._upsert_nested(
            model=SubEntity,
            parent_instance=entity,
            related_name="subentity",
            parent_field="entity",
            items=payload.get("subentities"),
            actor=actor,
        )
        cls._upsert_nested(
            model=EntityConstitution,
            parent_instance=entity,
            related_name="constitution",
            parent_field="entity",
            items=payload.get("constitution_details"),
            actor=actor,
        )

        entity.refresh_from_db()
        return cls.build_entity_payload(entity=entity)

    @classmethod
    @transaction.atomic
    def register_user_and_create_entity(cls, *, payload, user_agent="", ip_address=None):
        user_data = dict(payload["user"])
        onboarding_payload = dict(payload["onboarding"])

        email = user_data["email"].strip().lower()
        username = (user_data.get("username") or email).strip() or email
        password = user_data.pop("password")
        first_name = user_data.get("first_name", "")
        last_name = user_data.get("last_name", "")

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            email_verified=False,
        )

        onboarding_result = cls.create_entity(actor=user, payload=onboarding_payload)
        otp = AuthOTPService.create_otp(user=user, email=email, purpose="email_verification")

        return {
            "user": user,
            "onboarding": onboarding_result,
            "verification": {
                "email": user.email,
                "email_verified": user.email_verified,
                "otp_generated": bool(otp),
                "verification_required": True,
            },
        }
