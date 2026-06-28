from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from Authentication.models import User
from Authentication.services import AuthOTPService
from entity.models import (
    Entity,
    EntityAddress,
    EntityBankAccountV2,
    EntityComplianceProfile,
    EntityConstitutionV2,
    EntityContact,
    EntityFinancialYear,
    EntityGstRegistration,
    EntityOwnershipV2,
    EntityTaxProfile,
    SubEntity,
    SubEntityAddress,
    SubEntityCapability,
    SubEntityContact,
    SubEntityGstRegistration,
    _relaxed_gstin_enabled,
)
from entity.policy import EntityPolicyService

from assets.seeding import AssetSeedService
from catalog.seeding import CatalogSeedService
from financial.seeding import FinancialSeedService
from numbering.seeding import NumberingSeedService, NumberingSeedSpec
from posting.services.static_accounts import StaticAccountService
from purchase.seeding import PurchaseSeedService
from rbac.models import UserRoleAssignment
from rbac.seeding import RBACSeedService
from sales.seeding import SalesSeedService
from subscriptions.services import SubscriptionService

# Default numbering specs mirrored from numbering.management.commands.seed_doc_sequences
DEFAULT_NUMBERING_SPECS = [
    NumberingSeedSpec("sales", "sales_invoice", "Sales Invoice", "SINV"),
    NumberingSeedSpec("sales", "sales_credit_note", "Sales Credit Note", "SCN"),
    NumberingSeedSpec("sales", "sales_debit_note", "Sales Debit Note", "SDN"),
    NumberingSeedSpec("purchase", "PURCHASE_TAX_INVOICE", "Purchase Invoice", "PINV"),
    NumberingSeedSpec("purchase", "PURCHASE_CREDIT_NOTE", "Purchase Credit Note", "PCN"),
    NumberingSeedSpec("purchase", "PURCHASE_DEBIT_NOTE", "Purchase Debit Note", "PDN"),
    NumberingSeedSpec("receipts", "RECEIPT_VOUCHER", "Receipt Voucher", "RV"),
    NumberingSeedSpec("payments", "PAYMENT_VOUCHER", "Payment Voucher", "PPV"),
    NumberingSeedSpec("vouchers", "CASH_VOUCHER", "Cash Voucher", "CV"),
    NumberingSeedSpec("vouchers", "BANK_VOUCHER", "Bank Voucher", "BV"),
    NumberingSeedSpec("vouchers", "JOURNAL_VOUCHER", "Journal Voucher", "JV"),
    NumberingSeedSpec("assets", "asset_capitalization", "Asset Capitalization", "FA"),
    NumberingSeedSpec("assets", "asset_disposal", "Asset Disposal", "FAD"),
]


class EntityOnboardingService:
    """
    New entity onboarding flow.

    This is intentionally parallel to the legacy serializer-driven create path.
    It keeps the old endpoint untouched and moves the new onboarding transaction
    into explicit services so entity, financial, and RBAC defaults are seeded in
    a predictable and testable way.
    """

    @classmethod
    def _extract_entity_profile_data(cls, entity_data):
        legacy_keys = {
            "address", "address2", "addressfloorno", "addressstreet",
            "country", "state", "district", "city", "pincode", "registered_address_same_as_principal",
            "ownername", "contact_person_name", "contact_person_designation",
            "phoneoffice", "phoneresidence", "mobile_primary", "mobile_secondary",
            "email", "email_primary", "email_secondary", "support_email", "accounts_email",
            "gstno", "gstintype", "gst_effective_from", "gst_cancelled_from", "nature_of_business",
            "GstRegitrationType",
            "panno", "tds", "tan_no", "tdscircle", "cin_no", "llpin_no", "udyam_no", "iec_code",
            "incorporation_date", "business_commencement_date",
            "is_tds_applicable", "is_tcs_applicable", "is_einvoice_applicable", "is_ewaybill_applicable",
            "is_msme_registered", "msme_category",
            "bank", "bankacno", "ifsccode", "blockstatus", "dateofreg", "dateofdreg",
            "const", "tcs206c1honsale",
        }
        profile = {}
        for key in list(entity_data.keys()):
            if key in legacy_keys:
                profile[key] = entity_data.pop(key)
        return profile

    @classmethod
    def _extract_subentity_profile_data(cls, subentity_data):
        legacy_keys = {
            "address", "address2", "addressfloorno", "addressstreet",
            "country", "state", "district", "city", "pincode",
            "phoneoffice", "phoneresidence",
            "email", "email_primary", "mobile_primary", "mobile_secondary",
            "contact_person_name", "contact_person_designation",
            "gstno", "GstRegitrationType", "ismainentity",
            "can_sell", "can_purchase", "can_stock", "can_bank",
        }
        profile = {}
        for key in list(subentity_data.keys()):
            if key in legacy_keys:
                profile[key] = subentity_data.pop(key)
        return profile

    @classmethod
    def _sync_entity_normalized_profiles(cls, *, entity, actor, profile):
        if profile.get("address"):
            EntityAddress.objects.update_or_create(
                entity=entity,
                address_type=EntityAddress.AddressType.REGISTERED,
                defaults={
                    "line1": profile.get("address"),
                    "line2": profile.get("address2"),
                    "floor_no": profile.get("addressfloorno"),
                    "street": profile.get("addressstreet"),
                    "country": profile.get("country"),
                    "state": profile.get("state"),
                    "district": profile.get("district"),
                    "city": profile.get("city"),
                    "pincode": profile.get("pincode"),
                    "is_primary": True,
                    "createdby": actor,
                    "isactive": True,
                },
            )

        primary_name = profile.get("contact_person_name") or profile.get("ownername")
        if primary_name:
            EntityContact.objects.update_or_create(
                entity=entity,
                contact_type=EntityContact.ContactType.OWNER,
                name=primary_name,
                defaults={
                    "designation": profile.get("contact_person_designation"),
                    "mobile": profile.get("mobile_primary") or profile.get("phoneoffice"),
                    "email": profile.get("email_primary") or profile.get("email"),
                    "is_primary": True,
                    "createdby": actor,
                    "isactive": True,
                },
            )

        if profile.get("accounts_email"):
            EntityContact.objects.update_or_create(
                entity=entity,
                contact_type=EntityContact.ContactType.ACCOUNTS,
                name="Accounts",
                defaults={"email": profile.get("accounts_email"), "createdby": actor, "isactive": True},
            )
        if profile.get("support_email"):
            EntityContact.objects.update_or_create(
                entity=entity,
                contact_type=EntityContact.ContactType.SUPPORT,
                name="Support",
                defaults={"email": profile.get("support_email"), "createdby": actor, "isactive": True},
            )

        tax_keys = {
            "panno", "tds", "tan_no", "cin_no", "llpin_no",
            "iec_code", "udyam_no", "incorporation_date", "business_commencement_date",
        }
        if any(key in profile for key in tax_keys):
            EntityTaxProfile.objects.update_or_create(
                entity=entity,
                defaults={
                    "pan": profile.get("panno"),
                    "tan": profile.get("tan_no") or profile.get("tds"),
                    "cin_no": profile.get("cin_no"),
                    "llpin_no": profile.get("llpin_no"),
                    "iec_code": profile.get("iec_code"),
                    "udyam_no": profile.get("udyam_no"),
                    "incorporation_date": profile.get("incorporation_date"),
                    "business_commencement_date": profile.get("business_commencement_date"),
                    "createdby": actor,
                    "isactive": True,
                },
            )

        compliance_keys = {
            "is_tds_applicable", "is_tcs_applicable", "is_einvoice_applicable",
            "is_ewaybill_applicable", "is_msme_registered", "msme_category",
        }
        if any(key in profile for key in compliance_keys):
            EntityComplianceProfile.objects.update_or_create(
                entity=entity,
                defaults={
                    "is_tds_applicable": bool(profile.get("is_tds_applicable", False)),
                    "is_tcs_applicable": bool(profile.get("is_tcs_applicable", False)),
                    "is_einvoice_applicable": bool(profile.get("is_einvoice_applicable", False)),
                    "is_ewaybill_applicable": bool(profile.get("is_ewaybill_applicable", False)),
                    "is_msme_registered": bool(profile.get("is_msme_registered", False)),
                    "msme_category": profile.get("msme_category"),
                    "createdby": actor,
                    "isactive": True,
                },
            )

        gstno = (profile.get("gstno") or "").strip().upper()
        if gstno:
            # Current operating model keeps one active GST registration per entity.
            # When onboarding changes the GSTIN, retire any previous active row first.
            EntityGstRegistration.objects.filter(
                entity=entity,
                isactive=True,
            ).exclude(gstin=gstno).update(is_primary=False, isactive=False)

            EntityGstRegistration.objects.update_or_create(
                entity=entity,
                gstin=gstno,
                defaults={
                    "registration_type": profile.get("GstRegitrationType"),
                    "gst_status": entity.gst_registration_status or Entity.GstStatus.REGISTERED,
                    "state": profile.get("state"),
                    "nature_of_business": profile.get("nature_of_business"),
                    "gst_effective_from": profile.get("gst_effective_from"),
                    "gst_cancelled_from": profile.get("gst_cancelled_from"),
                    "is_primary": True,
                    "createdby": actor,
                    "isactive": True,
                },
            )

        if profile.get("bankacno") and profile.get("ifsccode"):
            has_primary = EntityBankAccountV2.objects.filter(entity=entity, isactive=True, is_primary=True).exists()
            EntityBankAccountV2.objects.create(
                entity=entity,
                bank_name=getattr(profile.get("bank"), "bankname", None) or "Bank",
                account_number=profile.get("bankacno"),
                ifsc_code=profile.get("ifsccode"),
                account_type="current",
                is_primary=not has_primary,
                createdby=actor,
                isactive=True,
            )

    @classmethod
    def _sync_subentity_normalized_profiles(cls, *, subentity, profile):
        if profile.get("address"):
            SubEntityAddress.objects.update_or_create(
                subentity=subentity,
                address_type=SubEntityAddress.AddressType.OPERATIONS,
                defaults={
                    "line1": profile.get("address"),
                    "line2": profile.get("address2"),
                    "floor_no": profile.get("addressfloorno"),
                    "street": profile.get("addressstreet"),
                    "country": profile.get("country"),
                    "state": profile.get("state"),
                    "district": profile.get("district"),
                    "city": profile.get("city"),
                    "pincode": profile.get("pincode"),
                    "is_primary": True,
                    "isactive": True,
                },
            )

        name = profile.get("contact_person_name") or subentity.subentityname
        SubEntityContact.objects.update_or_create(
            subentity=subentity,
            name=name,
            defaults={
                "designation": profile.get("contact_person_designation"),
                "mobile": profile.get("mobile_primary") or profile.get("phoneoffice"),
                "email": profile.get("email_primary") or profile.get("email"),
                "is_primary": True,
                "isactive": True,
            },
        )

        gstno = (profile.get("gstno") or "").strip().upper()
        if gstno:
            SubEntityGstRegistration.objects.filter(
                subentity=subentity,
                isactive=True,
                is_primary=True,
            ).exclude(gstin=gstno).update(is_primary=False)
            SubEntityGstRegistration.objects.update_or_create(
                subentity=subentity,
                gstin=gstno,
                defaults={
                    "registration_type": profile.get("GstRegitrationType"),
                    "gst_status": getattr(subentity.entity, "gst_registration_status", Entity.GstStatus.REGISTERED),
                    "state": profile.get("state"),
                    "nature_of_business": profile.get("nature_of_business"),
                    "is_primary": True,
                    "isactive": True,
                },
            )

        SubEntityCapability.objects.update_or_create(
            subentity=subentity,
            defaults={
                "can_sell": bool(profile.get("can_sell", True)),
                "can_purchase": bool(profile.get("can_purchase", True)),
                "can_stock": bool(profile.get("can_stock", True)),
                "can_bank": bool(profile.get("can_bank", True)),
                "isactive": True,
            },
        )

    @staticmethod
    def _entity_primary_gstin(entity) -> str | None:
        gst_row = entity.gst_registrations.filter(isactive=True, is_primary=True).only("gstin").first()
        gstin = str(getattr(gst_row, "gstin", "") or "").strip().upper()
        return gstin or None

    @classmethod
    def _sync_compliance_credentials(cls, *, entity, rows=None):
        from sales.models.mastergst_models import SalesMasterGSTCredential, MasterGSTServiceScope

        entity_gstin = cls._entity_primary_gstin(entity)
        existing = {
            (int(obj.environment), int(obj.service_scope)): obj
            for obj in SalesMasterGSTCredential.objects.filter(entity=entity)
        }

        if rows is None:
            if entity_gstin:
                for obj in existing.values():
                    if obj.gstin != entity_gstin:
                        obj.gstin = entity_gstin
                        obj.save(update_fields=["gstin", "updated_at"])
            return

        if rows and not entity_gstin:
            raise ValidationError({"compliance_credentials": "Primary entity GSTIN is required before saving compliance credentials."})

        keep_keys = set()
        for row in rows:
            data = dict(row)
            env = int(data.get("environment") or 0)
            scope = int(data.get("service_scope") or int(MasterGSTServiceScope.EINVOICE))
            key = (env, scope)
            keep_keys.add(key)
            obj = existing.get(key)
            secret_in = data.get("client_secret")
            password_in = data.get("gst_password")
            defaults = {
                "gstin": entity_gstin or "",
                "client_id": data.get("client_id") or "",
                "email": data.get("email") or "",
                "gst_username": data.get("gst_username") or "",
                "allow_all_ips": bool(data.get("allow_all_ips", True)),
                "ip_address": data.get("ip_address"),
                "is_active": bool(data.get("is_active", True)),
            }
            if obj:
                for field, value in defaults.items():
                    setattr(obj, field, value)
                if secret_in not in (None, ""):
                    obj.client_secret = secret_in
                if password_in not in (None, ""):
                    obj.gst_password = password_in
                obj.save()
                continue

            if secret_in in (None, "") or password_in in (None, ""):
                raise ValidationError(
                    {
                        "compliance_credentials": (
                            f"client_secret and gst_password are required for new credential "
                            f"(environment={env}, service_scope={scope})."
                        )
                    }
                )
            SalesMasterGSTCredential.objects.create(
                entity=entity,
                environment=env,
                service_scope=scope,
                client_secret=secret_in,
                gst_password=password_in,
                **defaults,
            )

        for key, obj in existing.items():
            if key not in keep_keys:
                obj.delete()

    @staticmethod
    def _normalize_bank_row(row):
        payload = dict(row)
        payload.pop("entity", None)
        payload.pop("entity_id", None)
        payload.setdefault("account_type", "current")
        payload.setdefault("isactive", True)
        return payload

    @staticmethod
    def _normalize_constitution_row(row):
        payload = dict(row)
        payload.pop("entity", None)
        payload.pop("entity_id", None)
        if payload.get("share_percentage") in (None, "") and payload.get("sharepercentage") not in (None, ""):
            payload["share_percentage"] = payload.get("sharepercentage")
        payload.pop("sharepercentage", None)
        payload.setdefault("constitution_code", "OWNER")
        payload.setdefault("constitution_name", "Ownership")
        payload.setdefault("account_preference", "capital")
        payload.setdefault("isactive", True)
        return payload

    @staticmethod
    def _normalize_ownership_row(row):
        payload = dict(row)
        payload.pop("entity", None)
        payload.pop("entity_id", None)
        if payload.get("name") in (None, ""):
            payload["name"] = payload.get("shareholder") or payload.get("constitution_name")
        if payload.get("pan_number") in (None, ""):
            payload["pan_number"] = payload.get("pan")
        if payload.get("share_percentage") in (None, "") and payload.get("sharepercentage") not in (None, ""):
            payload["share_percentage"] = payload.get("sharepercentage")
        payload.pop("sharepercentage", None)
        payload.setdefault("ownership_type", EntityOwnershipV2.OwnershipType.OTHER)
        payload.setdefault("account_preference", EntityOwnershipV2.AccountPreference.AUTO)
        payload.setdefault("is_primary", False)
        payload.setdefault("isactive", True)
        return payload

    @staticmethod
    def _ownership_to_constitution_row(row):
        payload = dict(row)
        payload.pop("entity", None)
        payload.pop("entity_id", None)
        ownership_name = payload.get("name") or payload.get("shareholder")
        ownership_pan = payload.get("pan_number") or payload.get("pan")
        if payload.get("share_percentage") in (None, "") and payload.get("sharepercentage") not in (None, ""):
            payload["share_percentage"] = payload.get("sharepercentage")
        payload.pop("sharepercentage", None)
        payload.pop("ownership_type", None)
        payload.pop("name", None)
        payload.pop("email", None)
        payload.pop("mobile", None)
        payload.pop("pan_number", None)
        payload.pop("capital_contribution", None)
        payload.pop("designation", None)
        payload.pop("remarks", None)
        payload.pop("is_primary", None)
        payload["shareholder"] = ownership_name
        payload["pan"] = ownership_pan
        payload.setdefault("constitution_code", "OWNER")
        payload.setdefault("constitution_name", "Ownership")
        payload.setdefault("account_preference", "capital")
        payload.setdefault("isactive", True)
        return payload

    @classmethod
    def _normalize_ownership_rows(cls, *, ownership_rows):
        rows = [dict(row) for row in ownership_rows]
        if not rows:
            return rows
        normalized = [cls._normalize_ownership_row(row) for row in rows]
        if not any(bool(row.get("is_primary")) for row in normalized):
            normalized[0]["is_primary"] = True
        return normalized

    @classmethod
    def _normalize_subentity_rows(cls, *, subentity_rows):
        rows = [dict(row) for row in subentity_rows]
        if not rows:
            return rows

        normalized = []
        for row in rows:
            if row.get("ismainentity"):
                row["is_head_office"] = True
            if row.get("branch_type") == SubEntity.BranchType.HEAD_OFFICE:
                row["is_head_office"] = True
            normalized.append(row)

        head_office_indexes = [
            index for index, row in enumerate(normalized)
            if bool(row.get("is_head_office"))
        ]
        if not head_office_indexes:
            normalized[0]["is_head_office"] = True
            normalized[0]["branch_type"] = SubEntity.BranchType.HEAD_OFFICE
        return normalized

    @classmethod
    def _validate_subentity_boundary(cls, *, entity):
        policy = EntityPolicyService.ensure_policy(entity=entity)
        warnings = []
        active_subentities = list(entity.subentity.filter(isactive=True).order_by("sort_order", "id"))
        head_office_count = sum(1 for row in active_subentities if row.is_head_office)

        if not active_subentities:
            EntityPolicyService.enforce(
                mode=policy.require_subentity_mode,
                field="subentities",
                code="entity.require_subentity",
                message="At least one active subentity is required for this entity.",
                warnings=warnings,
            )

        if active_subentities and head_office_count != 1:
            EntityPolicyService.enforce(
                mode=policy.require_head_office_subentity_mode,
                field="subentities",
                code="entity.require_single_head_office",
                message="Exactly one active head office subentity is required for this entity.",
                warnings=warnings,
            )
        return warnings

    @classmethod
    def _validate_entity_gst_rules(cls, *, entity):
        policy = EntityPolicyService.ensure_policy(entity=entity)
        warnings = []

        active_gst_rows = list(entity.gst_registrations.filter(isactive=True).select_related("state"))
        if len(active_gst_rows) > 1:
            EntityPolicyService.enforce(
                mode=EntityPolicy.ValidationMode.HARD,
                field="entity.gst",
                code="entity.single_active_gstin_required",
                message="Only one active GST registration is allowed per entity.",
                warnings=warnings,
            )
        primary_rows = [row for row in active_gst_rows if row.is_primary]
        if active_gst_rows and not primary_rows:
            EntityPolicyService.enforce(
                mode=policy.require_entity_primary_gstin_mode,
                field="entity.gst",
                code="entity.primary_gstin_required",
                message="At least one active primary GST registration is required for this entity.",
                warnings=warnings,
            )

        if not _relaxed_gstin_enabled():
            for row in active_gst_rows:
                if row.gstin and row.state_id:
                    gst_state_code = str(row.gstin[:2]).strip()
                    state_code = str(getattr(row.state, "statecode", "") or "").strip().zfill(2)
                    if state_code and gst_state_code != state_code:
                        EntityPolicyService.enforce(
                            mode=policy.gstin_state_match_mode,
                            field="entity.gst.state",
                            code="entity.gstin_state_mismatch",
                            message=f"GSTIN {row.gstin} must match state code {state_code}.",
                            warnings=warnings,
                        )
        return warnings

    @classmethod
    def _validate_subentity_gst_rules(cls, *, entity):
        policy = EntityPolicyService.ensure_policy(entity=entity)
        warnings = []

        for subentity in entity.subentity.filter(isactive=True).prefetch_related("gst_registrations__state"):
            active_gst_rows = [row for row in subentity.gst_registrations.all() if row.isactive]
            if _relaxed_gstin_enabled():
                continue
            for row in active_gst_rows:
                if row.gstin and row.state_id:
                    gst_state_code = str(row.gstin[:2]).strip()
                    state_code = str(getattr(row.state, "statecode", "") or "").strip().zfill(2)
                    if state_code and gst_state_code != state_code:
                        EntityPolicyService.enforce(
                            mode=policy.subentity_gstin_state_match_mode,
                            field="subentity.gst.state",
                            code="subentity.gstin_state_mismatch",
                            message=f"GSTIN {row.gstin} for subentity '{subentity.subentityname}' must match state code {state_code}.",
                            warnings=warnings,
                        )
        return warnings

    @classmethod
    def _collect_validation_warnings(cls, *, entity):
        warnings = []
        warnings.extend(cls._validate_subentity_boundary(entity=entity))
        warnings.extend(cls._validate_entity_gst_rules(entity=entity))
        warnings.extend(cls._validate_subentity_gst_rules(entity=entity))
        return warnings

    @classmethod
    @transaction.atomic
    def create_entity(cls, *, actor, payload):
        customer_account = SubscriptionService.assert_can_create_entity(user=actor)
        entity_data = dict(payload["entity"])
        policy_data = dict(payload.get("policy") or {})
        fy_rows = [dict(row) for row in payload.get("financial_years", [])]
        bank_rows = [dict(row) for row in payload.get("bank_accounts", [])]
        subentity_rows = cls._normalize_subentity_rows(subentity_rows=payload.get("subentities", []))
        constitution_rows = [dict(row) for row in payload.get("constitution_details", [])]
        ownership_rows = cls._normalize_ownership_rows(
            ownership_rows=payload.get("ownership_details", []) or payload.get("constitution_details", [])
        )
        compliance_credential_rows = [dict(row) for row in payload.get("compliance_credentials", [])]
        if not constitution_rows and ownership_rows:
            constitution_rows = [
                cls._normalize_constitution_row(cls._ownership_to_constitution_row(row))
                for row in ownership_rows
            ]
        seed_options = dict(payload.get("seed_options") or {})

        entity_profile_data = cls._extract_entity_profile_data(entity_data)
        entity = Entity.objects.create(createdby=actor, customer_account=customer_account, **entity_data)
        EntityPolicyService.sync_policy(entity=entity, policy_data=policy_data, actor=actor)
        cls._sync_entity_normalized_profiles(entity=entity, actor=actor, profile=entity_profile_data)
        if not entity.entity_code:
            entity.entity_code = f"ENT{entity.id:05d}"
            entity.save(update_fields=["entity_code"])

        fy_ids = []
        active_rows = [row for row in fy_rows if row.get("isactive")]
        if not active_rows and fy_rows:
            fy_rows[0]["isactive"] = True

        for row in fy_rows:
            fy = EntityFinancialYear.objects.create(entity=entity, createdby=actor, **row)
            fy_ids.append(fy.id)

        bank_ids = []
        for row in bank_rows:
            bank = EntityBankAccountV2.objects.create(entity=entity, createdby=actor, **cls._normalize_bank_row(row))
            bank_ids.append(bank.id)

        subentity_ids = []
        if subentity_rows:
            for row in subentity_rows:
                sub_profile = cls._extract_subentity_profile_data(row)
                if sub_profile.get("ismainentity"):
                    row["is_head_office"] = True
                subentity = SubEntity.objects.create(entity=entity, **row)
                cls._sync_subentity_normalized_profiles(subentity=subentity, profile=sub_profile)
                if not subentity.subentity_code:
                    subentity.subentity_code = f"BR{entity.id:03d}{subentity.id:03d}"
                    subentity.save(update_fields=["subentity_code"])
                subentity_ids.append(subentity.id)
        elif seed_options.get("seed_default_subentity", True):
            primary_addr = entity.addresses.filter(isactive=True, is_primary=True).first()
            primary_contact = entity.contacts.filter(isactive=True, is_primary=True).first()
            primary_gst = entity.gst_registrations.filter(isactive=True, is_primary=True).first()
            subentity = SubEntity.objects.create(
                entity=entity,
                subentityname="Main-Branch",
                is_head_office=True,
                branch_type=SubEntity.BranchType.HEAD_OFFICE,
                isactive=True,
            )
            cls._sync_subentity_normalized_profiles(
                subentity=subentity,
                profile={
                    "address": getattr(primary_addr, "line1", None),
                    "address2": getattr(primary_addr, "line2", None),
                    "addressfloorno": getattr(primary_addr, "floor_no", None),
                    "addressstreet": getattr(primary_addr, "street", None),
                    "country": getattr(primary_addr, "country", None),
                    "state": getattr(primary_addr, "state", None),
                    "district": getattr(primary_addr, "district", None),
                    "city": getattr(primary_addr, "city", None),
                    "pincode": getattr(primary_addr, "pincode", None),
                    "phoneoffice": getattr(primary_contact, "mobile", None),
                    "phoneresidence": getattr(primary_contact, "mobile", None),
                    "email": getattr(primary_contact, "email", None),
                    "email_primary": getattr(primary_contact, "email", None),
                    "contact_person_name": getattr(primary_contact, "name", None),
                    "contact_person_designation": getattr(primary_contact, "designation", None),
                    "gstno": getattr(primary_gst, "gstin", None),
                    "GstRegitrationType": getattr(primary_gst, "registration_type", None),
                    "can_sell": True,
                    "can_purchase": True,
                    "can_stock": True,
                    "can_bank": True,
                },
            )
            subentity.subentity_code = f"HO{entity.id:05d}"
            subentity.save(update_fields=["subentity_code"])
            subentity_ids.append(subentity.id)

        validation_warnings = cls._collect_validation_warnings(entity=entity)

        posting_static_accounts_summary = StaticAccountService.seed_static_account_master()

        constitution_ids = []
        for row in constitution_rows:
            constitution = EntityConstitutionV2.objects.create(
                entity=entity,
                createdby=actor,
                **cls._normalize_constitution_row(row),
            )
            constitution_ids.append(constitution.id)

        ownership_ids = []
        for row in ownership_rows:
            ownership = EntityOwnershipV2.objects.create(
                entity=entity,
                createdby=actor,
                **row,
            )
            ownership_ids.append(ownership.id)

        cls._sync_compliance_credentials(entity=entity, rows=compliance_credential_rows or [])

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

        numbering_summary = []
        if seed_options.get("seed_numbering", True) and fy_ids:
            # Keep create/update flows aligned by seeding both entity-wide and
            # branch-scoped series for every active numbering spec.
            target_subentities = [None, *subentity_ids] if subentity_ids else [None]
            for fy_id in fy_ids:
                for sub_id in target_subentities:
                    numbering_summary.extend(
                        NumberingSeedService.seed_documents(
                            entity_id=entity.id,
                            entityfinid_id=fy_id,
                            subentity_id=sub_id,
                            specs=DEFAULT_NUMBERING_SPECS,
                        )
                    )

        catalog_summary = {}
        if seed_options.get("seed_catalog", True):
            catalog_summary = CatalogSeedService.seed_entity(entity=entity)

        asset_summary = {}
        if seed_options.get("seed_assets", True):
            asset_summary = AssetSeedService.seed_entity(entity=entity, actor=actor)

        purchase_choice_summary = {}
        if seed_options.get("seed_purchase_choices", True):
            purchase_choice_summary = PurchaseSeedService.seed_choice_overrides(entity=entity, subentity=None)

        sales_choice_summary = {}
        if seed_options.get("seed_sales_choices", True):
            sales_choice_summary = SalesSeedService.seed_choice_overrides(entity=entity, subentity=None)

        SubscriptionService.register_entity_creation(
            entity=entity,
            owner=actor,
        )

        return {
            "entity": entity,
            "financial_year_ids": fy_ids,
            "bank_account_ids": bank_ids,
            "subentity_ids": subentity_ids,
            "constitution_ids": constitution_ids,
            "ownership_ids": ownership_ids,
            "compliance_credential_ids": [row["id"] for row in cls.build_entity_payload(entity=entity).get("compliance_credentials", []) if row.get("id")],
            "posting_static_accounts": posting_static_accounts_summary,
            "financial": financial_summary,
            "rbac": rbac_summary,
            "numbering": numbering_summary,
            "catalog": catalog_summary,
            "assets": asset_summary,
            "purchase_choice_overrides": purchase_choice_summary,
            "sales_choice_overrides": sales_choice_summary,
            "validation_warnings": validation_warnings,
        }

    @staticmethod
    def can_manage_entity(*, user, entity) -> bool:
        if not user or not user.is_authenticated:
            return False
        if not SubscriptionService.has_entity_membership(user=user, entity=entity, backfill_owner=True):
            return False
        now = timezone.now()
        current_assignment_exists = UserRoleAssignment.objects.filter(entity=entity, user=user, isactive=True).filter(
            Q(effective_from__isnull=True) | Q(effective_from__lte=now),
            Q(effective_to__isnull=True) | Q(effective_to__gte=now),
        ).exists()
        if current_assignment_exists:
            return True
        if entity.createdby_id != user.id:
            return False
        return not UserRoleAssignment.objects.filter(entity=entity, user=user).exists()

    @classmethod
    def build_entity_payload(cls, *, entity):
        primary_addr = entity.addresses.filter(isactive=True, is_primary=True).first()
        primary_contact = entity.contacts.filter(isactive=True, is_primary=True).first()
        gst_row = entity.gst_registrations.filter(isactive=True, is_primary=True).first()
        tax_profile = getattr(entity, "tax_profile", None)
        compliance = getattr(entity, "compliance_profile", None)
        from sales.models.mastergst_models import SalesMasterGSTCredential

        entity_payload = {
            "id": entity.id,
            "entityname": entity.entityname,
            "entitydesc": entity.entitydesc,
            "legalname": entity.legalname,
            "entity_code": entity.entity_code,
            "trade_name": entity.trade_name,
            "short_name": entity.short_name,
            "organization_status": entity.organization_status,
            "business_type": entity.business_type,
            "GstRegitrationType": getattr(gst_row, "registration_type_id", None),
            "gst_registration_status": entity.gst_registration_status,
            "website": entity.website,
            "address": getattr(primary_addr, "line1", None),
            "address2": getattr(primary_addr, "line2", None),
            "addressfloorno": getattr(primary_addr, "floor_no", None),
            "addressstreet": getattr(primary_addr, "street", None),
            "country": getattr(primary_addr, "country_id", None),
            "state": getattr(primary_addr, "state_id", None),
            "district": getattr(primary_addr, "district_id", None),
            "city": getattr(primary_addr, "city_id", None),
            "pincode": getattr(primary_addr, "pincode", None),
            "registered_address_same_as_principal": True,
            "ownername": getattr(primary_contact, "name", None),
            "contact_person_name": getattr(primary_contact, "name", None),
            "contact_person_designation": getattr(primary_contact, "designation", None),
            "phoneoffice": getattr(primary_contact, "mobile", None),
            "phoneresidence": getattr(primary_contact, "mobile", None),
            "mobile_primary": getattr(primary_contact, "mobile", None),
            "mobile_secondary": None,
            "panno": getattr(tax_profile, "pan", None),
            "tds": getattr(tax_profile, "tan", None),
            "tdscircle": None,
            "tan_no": getattr(tax_profile, "tan", None),
            "cin_no": getattr(tax_profile, "cin_no", None),
            "llpin_no": getattr(tax_profile, "llpin_no", None),
            "udyam_no": getattr(tax_profile, "udyam_no", None),
            "iec_code": getattr(tax_profile, "iec_code", None),
            "email": getattr(primary_contact, "email", None),
            "email_primary": getattr(primary_contact, "email", None),
            "email_secondary": None,
            "support_email": entity.contacts.filter(contact_type=EntityContact.ContactType.SUPPORT, isactive=True).values_list("email", flat=True).first(),
            "accounts_email": entity.contacts.filter(contact_type=EntityContact.ContactType.ACCOUNTS, isactive=True).values_list("email", flat=True).first(),
            "tcs206c1honsale": None,
            "is_tds_applicable": getattr(compliance, "is_tds_applicable", False),
            "is_tcs_applicable": getattr(compliance, "is_tcs_applicable", False),
            "is_einvoice_applicable": getattr(compliance, "is_einvoice_applicable", False),
            "is_ewaybill_applicable": getattr(compliance, "is_ewaybill_applicable", False),
            "is_msme_registered": getattr(compliance, "is_msme_registered", False),
            "msme_category": getattr(compliance, "msme_category", None),
            "gstno": getattr(gst_row, "gstin", None),
            "gstintype": entity.gst_registration_status,
            "gst_effective_from": getattr(gst_row, "gst_effective_from", None),
            "gst_cancelled_from": getattr(gst_row, "gst_cancelled_from", None),
            "nature_of_business": getattr(gst_row, "nature_of_business", None),
            "incorporation_date": getattr(tax_profile, "incorporation_date", None),
            "business_commencement_date": getattr(tax_profile, "business_commencement_date", None),
            "blockstatus": None,
            "dateofreg": getattr(entity, "created_at", None),
            "dateofdreg": None,
            "const": None,
            "parent_entity": entity.parent_entity_id,
            "metadata": entity.metadata,
        }
        policy_payload = EntityPolicyService.build_payload(entity=entity)

        subentity_rows = []
        for sub in entity.subentity.all().order_by("id"):
            sub_addr = sub.addresses.filter(isactive=True, is_primary=True).first()
            sub_contact = sub.contacts.filter(isactive=True, is_primary=True).first()
            sub_gst = sub.gst_registrations.filter(isactive=True, is_primary=True).first()
            capability = getattr(sub, "capability", None)
            subentity_rows.append(
                {
                    "id": sub.id,
                    "subentityname": sub.subentityname,
                    "subentity_code": sub.subentity_code,
                    "branch_type": sub.branch_type,
                    "address": getattr(sub_addr, "line1", None),
                    "address2": getattr(sub_addr, "line2", None),
                    "addressfloorno": getattr(sub_addr, "floor_no", None),
                    "addressstreet": getattr(sub_addr, "street", None),
                    "country": getattr(sub_addr, "country_id", None),
                    "state": getattr(sub_addr, "state_id", None),
                    "district": getattr(sub_addr, "district_id", None),
                    "city": getattr(sub_addr, "city_id", None),
                    "pincode": getattr(sub_addr, "pincode", None),
                    "phoneoffice": getattr(sub_contact, "mobile", None),
                    "phoneresidence": getattr(sub_contact, "mobile", None),
                    "email": getattr(sub_contact, "email", None),
                    "email_primary": getattr(sub_contact, "email", None),
                    "mobile_primary": getattr(sub_contact, "mobile", None),
                    "mobile_secondary": None,
                    "contact_person_name": getattr(sub_contact, "name", None),
                    "contact_person_designation": getattr(sub_contact, "designation", None),
                    "gstno": getattr(sub_gst, "gstin", None),
                    "GstRegitrationType": getattr(sub_gst, "registration_type_id", None),
                    "ismainentity": sub.is_head_office,
                    "is_head_office": sub.is_head_office,
                    "can_sell": getattr(capability, "can_sell", True),
                    "can_purchase": getattr(capability, "can_purchase", True),
                    "can_stock": getattr(capability, "can_stock", True),
                    "can_bank": getattr(capability, "can_bank", True),
                    "sort_order": sub.sort_order,
                    "metadata": sub.metadata,
                }
            )

        compliance_credentials = []
        for cred in SalesMasterGSTCredential.objects.filter(entity=entity).order_by("environment", "service_scope", "id"):
            compliance_credentials.append(
                {
                    "id": cred.id,
                    "environment": int(cred.environment),
                    "service_scope": int(cred.service_scope),
                    "client_id": cred.client_id,
                    "client_secret": "",
                    "email": cred.email,
                    "gst_username": cred.gst_username,
                    "gst_password": "",
                    "allow_all_ips": cred.allow_all_ips,
                    "ip_address": cred.ip_address,
                    "is_active": cred.is_active,
                    "gstin": cred.gstin,
                    "has_client_secret": bool(cred.get_client_secret()),
                    "has_gst_password": bool(cred.get_gst_password()),
                }
            )

        return {
            "entity_id": entity.id,
            "entity": entity_payload,
            "policy": policy_payload,
            "validation_warnings": cls._collect_validation_warnings(entity=entity),
            "financial_years": entity.fy.all().order_by("finstartyear", "id"),
            "bank_accounts": entity.bank_accounts_v2.all().order_by("id"),
            "subentities": subentity_rows,
            "constitution_details": entity.constitutions_v2.all().order_by("id"),
            "ownership_details": entity.ownerships_v2.all().order_by("id"),
            "compliance_credentials": compliance_credentials,
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
    def _ensure_numbering_for_current_scopes(cls, *, entity):
        fy_ids = list(
            EntityFinancialYear.objects.filter(entity=entity).order_by("id").values_list("id", flat=True)
        )
        if not fy_ids:
            return []

        subentity_ids = list(
            SubEntity.objects.filter(entity=entity).order_by("id").values_list("id", flat=True)
        )
        target_subentities = [None, *subentity_ids] if subentity_ids else [None]
        numbering_rows = []
        for fy_id in fy_ids:
            for subentity_id in target_subentities:
                numbering_rows.extend(
                    NumberingSeedService.seed_documents(
                        entity_id=entity.id,
                        entityfinid_id=fy_id,
                        subentity_id=subentity_id,
                        specs=DEFAULT_NUMBERING_SPECS,
                    )
                )
        return numbering_rows

    @classmethod
    @transaction.atomic
    def update_entity(cls, *, actor, entity, payload):
        if not cls.can_manage_entity(user=actor, entity=entity):
            raise PermissionDenied("You are not allowed to update this entity.")

        entity_data = payload.get("entity")
        if entity_data is not None:
            entity_data = dict(entity_data)
            entity_profile_data = cls._extract_entity_profile_data(entity_data)
            for field, value in dict(entity_data).items():
                setattr(entity, field, value)
            if hasattr(entity, "updatedby_id"):
                entity.updatedby = actor
            entity.save()
            cls._sync_entity_normalized_profiles(entity=entity, actor=actor, profile=entity_profile_data)

        if "policy" in payload:
            EntityPolicyService.sync_policy(
                entity=entity,
                policy_data=dict(payload.get("policy") or {}),
                actor=actor,
            )

        fy_rows = payload.get("financial_years")
        touched_numbering_scopes = False
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
            touched_numbering_scopes = True

        cls._upsert_nested(
            model=EntityBankAccountV2,
            parent_instance=entity,
            related_name="bank_accounts_v2",
            parent_field="entity",
            items=(
                [cls._normalize_bank_row(item) for item in payload.get("bank_accounts", [])]
                if payload.get("bank_accounts") is not None
                else None
            ),
            actor=actor,
        )
        sub_rows = payload.get("subentities")
        if sub_rows is not None:
            incoming = cls._normalize_subentity_rows(subentity_rows=sub_rows)
            existing = {obj.id: obj for obj in entity.subentity.all()}
            keep_ids = set()
            for row in incoming:
                row_id = int(row.get("id") or 0)
                profile = cls._extract_subentity_profile_data(row)
                if profile.get("ismainentity"):
                    row["is_head_office"] = True
                if row_id and row_id in existing:
                    obj = existing[row_id]
                    for key, value in row.items():
                        if key != "id":
                            setattr(obj, key, value)
                    obj.save()
                    cls._sync_subentity_normalized_profiles(subentity=obj, profile=profile)
                    keep_ids.add(obj.id)
                else:
                    row.pop("id", None)
                    obj = SubEntity.objects.create(entity=entity, **row)
                    cls._sync_subentity_normalized_profiles(subentity=obj, profile=profile)
                    keep_ids.add(obj.id)
            for obj_id, obj in existing.items():
                if obj_id not in keep_ids:
                    obj.delete()
            touched_numbering_scopes = True

        if touched_numbering_scopes:
            cls._ensure_numbering_for_current_scopes(entity=entity)

        constitution_payload = payload.get("constitution_details")
        ownership_payload = payload.get("ownership_details")
        compliance_credential_payload = payload.get("compliance_credentials")
        if (constitution_payload is None or not constitution_payload) and ownership_payload:
            constitution_payload = [
                cls._normalize_constitution_row(cls._ownership_to_constitution_row(item))
                for item in ownership_payload
            ]
        cls._upsert_nested(
            model=EntityConstitutionV2,
            parent_instance=entity,
            related_name="constitutions_v2",
            parent_field="entity",
            items=(
                [cls._normalize_constitution_row(item) for item in constitution_payload]
                if constitution_payload is not None
                else None
            ),
            actor=actor,
        )
        cls._upsert_nested(
            model=EntityOwnershipV2,
            parent_instance=entity,
            related_name="ownerships_v2",
            parent_field="entity",
            items=(
                [cls._normalize_ownership_row(item) for item in ownership_payload]
                if ownership_payload is not None
                else (
                    [cls._normalize_ownership_row(item) for item in constitution_payload]
                    if constitution_payload is not None
                    else None
                )
            ),
            actor=actor,
        )

        cls._sync_compliance_credentials(
            entity=entity,
            rows=([dict(row) for row in compliance_credential_payload] if compliance_credential_payload is not None else None),
        )

        entity.refresh_from_db()
        return cls.build_entity_payload(entity=entity)

    @classmethod
    @transaction.atomic
    def register_user_and_create_entity(cls, *, payload, user_agent="", ip_address=None):
        user_data = dict(payload["user"])
        onboarding_payload = dict(payload["onboarding"])
        intent = payload.get("intent") or SubscriptionService.INTENT_STANDARD

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
        SubscriptionService.handle_signup(user=user, intent=intent)

        onboarding_result = cls.create_entity(actor=user, payload=onboarding_payload)
        otp = AuthOTPService.create_otp(user=user, email=email, purpose="email_verification")

        return {
            "user": user,
            "intent": intent,
            "onboarding": onboarding_result,
            "verification": {
                "email": user.email,
                "email_verified": user.email_verified,
                "otp_generated": bool(otp),
                "verification_required": True,
            },
            "subscription": SubscriptionService.build_subscription_snapshot(entity=onboarding_result["entity"]),
        }
