import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.db.models import Model, Q
from django.utils import timezone
from rest_framework import serializers

from Authentication.models import AuthSession, User
from Authentication.services import AuthOTPService, AuthTokenService
from entity.models import Entity, EntityFinancialYear, EntityGstRegistration, SubEntity, gstin_validator
from entity.onboarding_serializers import (
    EntityOnboardingCreateSerializer,
    OnboardingFinancialYearSerializer,
    OnboardingSubEntitySerializer,
)
from entity.onboarding_services import DEFAULT_NUMBERING_SPECS, EntityOnboardingService
from numbering.seeding import NumberingSeedService
from numbering.models import DocumentNumberSeries, DocumentType
from financial.models import Ledger, account
from posting.models import EntityStaticAccountMap, StaticAccount
from posting.services.static_accounts import StaticAccountService
from rbac.models import Permission, Role, RolePermission
from rbac.seeding import RBACSeedService
from rbac.services import RoleTemplateService
from catalog.models import HsnSac, ProductCategory, UnitOfMeasure
from catalog.seeding import CatalogSeedService
from assets.models import AssetCategory, AssetSettings
from assets.seeding import (
    ACCUMULATED_DEPRECIATION_LEDGER_CODE, AMORTIZATION_EXPENSE_LEDGER_CODE,
    ASSET_LEDGER_DEFINITIONS, CATEGORY_DEFINITIONS, DEPRECIATION_EXPENSE_LEDGER_CODE,
    GAIN_ON_SALE_LEDGER_CODE, IMPAIRMENT_EXPENSE_LEDGER_CODE,
    IMPAIRMENT_RESERVE_LEDGER_CODE, INTANGIBLE_ACCUMULATED_AMORTIZATION_LEDGER_CODE,
    LOSS_ON_SALE_LEDGER_CODE, ROU_ACCUMULATED_DEPRECIATION_LEDGER_CODE,
    VEHICLE_ACCUMULATED_DEPRECIATION_LEDGER_CODE,
)
from purchase.models.purchase_config import PurchaseChoiceOverride, PurchaseSettings
from purchase.seeding import PURCHASE_CHOICE_GROUPS
from sales.models.sales_settings import SalesChoiceOverride, SalesSettings
from sales.seeding import SALES_CHOICE_GROUPS
from subscriptions.models import CustomerAccount, CustomerSubscription, SubscriptionPlan, UserEntityAccess
from subscriptions.services import SubscriptionService

from .models import (
    PlatformAuditEvent, PlatformOperationApproval, PlatformOperationRequest,
    PlatformProvisioningJob, PlatformRole, PlatformUserRole,
)
from .onboarding import PlatformOnboardingValidationSerializer, PlatformOnboardingValidationService
from .services import PlatformAuditService


class PlatformOnboardingRequestSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=120)
    reason = serializers.CharField(max_length=500)
    ticket_reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    payload = PlatformOnboardingValidationSerializer()

    def validate_idempotency_key(self, value):
        return value.strip()

    def validate_reason(self, value):
        value = value.strip()
        if len(value) < 10:
            raise serializers.ValidationError("Provide a specific operational reason of at least 10 characters.")
        return value


class PlatformCustomerContactUpdateSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=120)
    reason = serializers.CharField(max_length=500)
    ticket_reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    expected_target_version = serializers.DateTimeField()
    changes = serializers.DictField()

    ALLOWED_FIELDS = {
        "primary_contact_name": serializers.CharField(max_length=150, allow_blank=True),
        "primary_contact_email": serializers.EmailField(allow_blank=True),
        "primary_contact_phone": serializers.CharField(max_length=30, allow_blank=True),
        "billing_contact_name": serializers.CharField(max_length=150, allow_blank=True),
        "billing_contact_phone": serializers.CharField(max_length=30, allow_blank=True),
        "billing_email": serializers.EmailField(allow_blank=True),
        "support_email": serializers.EmailField(allow_blank=True),
        "status_notes": serializers.CharField(max_length=2000, allow_blank=True),
    }

    def validate_idempotency_key(self, value):
        return value.strip()

    def validate_reason(self, value):
        value = value.strip()
        if len(value) < 10:
            raise serializers.ValidationError("Provide a specific operational reason of at least 10 characters.")
        return value

    def validate_changes(self, value):
        unknown = sorted(set(value) - set(self.ALLOWED_FIELDS))
        if unknown:
            raise serializers.ValidationError({field: "This field cannot be changed by this operation." for field in unknown})
        if not value:
            raise serializers.ValidationError("Provide at least one contact or notes change.")
        validated = {}
        errors = {}
        for field, field_serializer in self.ALLOWED_FIELDS.items():
            if field not in value:
                continue
            try:
                validated[field] = field_serializer.run_validation(value[field])
            except serializers.ValidationError as exc:
                errors[field] = exc.detail
        if errors:
            raise serializers.ValidationError(errors)
        return validated


class PlatformCustomerStatusUpdateSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=120)
    reason = serializers.CharField(min_length=10, max_length=500)
    ticket_reference = serializers.CharField(min_length=3, max_length=120)
    expected_target_version = serializers.DateTimeField()
    desired_status = serializers.ChoiceField(choices=(
        CustomerAccount.Status.ACTIVE,
        CustomerAccount.Status.SUSPENDED,
    ))

    def validate_idempotency_key(self, value):
        return value.strip()

    def validate(self, attrs):
        attrs["reason"] = attrs["reason"].strip()
        attrs["ticket_reference"] = attrs["ticket_reference"].strip()
        return attrs


class PlatformApprovalDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=PlatformOperationApproval.Decision.choices)
    comment = serializers.CharField(min_length=5, max_length=500)


class PlatformEntityChildRequestSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=120)
    reason = serializers.CharField(min_length=10, max_length=500)
    ticket_reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    expected_target_version = serializers.DateTimeField()

    def validate_idempotency_key(self, value):
        return value.strip()


class PlatformAddBranchSerializer(PlatformEntityChildRequestSerializer):
    branch = serializers.DictField()

    def validate_branch(self, value):
        serializer = OnboardingSubEntitySerializer(data=value)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if data.get("is_head_office") or data.get("branch_type") == SubEntity.BranchType.HEAD_OFFICE:
            raise serializers.ValidationError("Adding or replacing a head office requires a separate high-risk operation.")
        allowed = ("subentityname", "subentity_code", "branch_type", "sort_order")
        return {field: data[field] for field in allowed if field in data}


class PlatformAddFinancialYearSerializer(PlatformEntityChildRequestSerializer):
    ticket_reference = serializers.CharField(min_length=3, max_length=120)
    financial_year = serializers.DictField()

    def validate_financial_year(self, value):
        serializer = OnboardingFinancialYearSerializer(data=value)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        start = data.get("finstartyear")
        end = data.get("finendyear")
        if not start or not end:
            raise serializers.ValidationError("Start date and end date are required.")
        if end <= start:
            raise serializers.ValidationError("End date must be later than start date.")
        data.pop("id", None)
        data.pop("metadata", None)
        return data


class PlatformEntityGstUpdateSerializer(PlatformEntityChildRequestSerializer):
    ticket_reference = serializers.CharField(min_length=3, max_length=120)
    gst_registration_status = serializers.ChoiceField(choices=Entity.GstStatus.choices)
    gstin = serializers.CharField(max_length=15, required=False, allow_blank=True)
    effective_from = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        status = attrs["gst_registration_status"]
        gstin = (attrs.get("gstin") or "").strip().upper()
        if status == Entity.GstStatus.UNREGISTERED:
            if gstin:
                raise serializers.ValidationError({"gstin": "GSTIN must be blank for an unregistered entity."})
        else:
            if not gstin:
                raise serializers.ValidationError({"gstin": "GSTIN is required for this registration status."})
            try:
                gstin_validator(gstin)
            except Exception as exc:
                raise serializers.ValidationError({"gstin": "Enter a valid GSTIN."}) from exc
        attrs["gstin"] = gstin
        return attrs


class PlatformSubscriptionPlanChangeSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=120)
    reason = serializers.CharField(min_length=10, max_length=500)
    ticket_reference = serializers.CharField(min_length=3, max_length=120)
    expected_target_version = serializers.DateTimeField()
    plan_code = serializers.SlugField(max_length=80)

    def validate_idempotency_key(self, value):
        return value.strip()

    def validate_plan_code(self, value):
        return value.strip().lower()


class PlatformTenantMembershipUpdateSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=120)
    reason = serializers.CharField(min_length=10, max_length=500)
    ticket_reference = serializers.CharField(min_length=3, max_length=120)
    expected_target_version = serializers.DateTimeField()
    role = serializers.ChoiceField(choices=UserEntityAccess.Role.choices)
    is_active = serializers.BooleanField()
    expires_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs):
        if attrs.get("expires_at") and attrs["expires_at"] <= timezone.now():
            raise serializers.ValidationError({"expires_at": "Expiry must be in the future."})
        return attrs


class PlatformTenantUserInviteSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=120)
    reason = serializers.CharField(min_length=10, max_length=500)
    ticket_reference = serializers.CharField(min_length=3, max_length=120)
    expected_target_version = serializers.DateTimeField()
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=UserEntityAccess.Role.choices)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate_email(self, value):
        return value.strip().lower()

    def validate_role(self, value):
        if value == UserEntityAccess.Role.OWNER:
            raise serializers.ValidationError("Owner access must be assigned through ownership transfer.")
        return value

    def validate(self, attrs):
        if attrs.get("expires_at") and attrs["expires_at"] <= timezone.now():
            raise serializers.ValidationError({"expires_at": "Expiry must be in the future."})
        return attrs


class PlatformTenantInvitationResendSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=120)
    reason = serializers.CharField(min_length=10, max_length=500)
    ticket_reference = serializers.CharField(min_length=3, max_length=120)
    expected_target_version = serializers.DateTimeField()


class PlatformCustomerOwnershipTransferSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=120)
    reason = serializers.CharField(min_length=10, max_length=500)
    ticket_reference = serializers.CharField(min_length=3, max_length=120)
    expected_target_version = serializers.DateTimeField()
    target_membership_id = serializers.IntegerField(min_value=1)
    expected_membership_version = serializers.DateTimeField()


class PlatformOperationCancellationSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=10, max_length=500)


class PlatformEntityNumberingRepairSerializer(PlatformEntityChildRequestSerializer):
    ticket_reference = serializers.CharField(min_length=3, max_length=120)


class PlatformEntityPostingMappingRepairSerializer(PlatformEntityChildRequestSerializer):
    ticket_reference = serializers.CharField(min_length=3, max_length=120)


class PlatformEntityRbacRoleRepairSerializer(PlatformEntityChildRequestSerializer):
    ticket_reference = serializers.CharField(min_length=3, max_length=120)


class PlatformEntityCatalogRepairSerializer(PlatformEntityChildRequestSerializer):
    ticket_reference = serializers.CharField(min_length=3, max_length=120)


class PlatformEntityAssetRepairSerializer(PlatformEntityChildRequestSerializer):
    ticket_reference = serializers.CharField(min_length=3, max_length=120)


class PlatformEntityTradeSettingsRepairSerializer(PlatformEntityChildRequestSerializer):
    ticket_reference = serializers.CharField(min_length=3, max_length=120)


class PlatformRoleChangeSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=120)
    reason = serializers.CharField(min_length=10, max_length=500)
    ticket_reference = serializers.CharField(min_length=3, max_length=120)
    action = serializers.ChoiceField(choices=("grant", "revoke"))
    user_id = serializers.IntegerField(min_value=1, required=False)
    role_code = serializers.SlugField(max_length=80, required=False)
    assignment_id = serializers.IntegerField(min_value=1, required=False)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    emergency_access = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if attrs["action"] == "grant":
            if not attrs.get("user_id") or not attrs.get("role_code"):
                raise serializers.ValidationError("User and role are required for a grant.")
            if attrs.get("assignment_id"):
                raise serializers.ValidationError({"assignment_id": "Assignment is only used for revocation."})
            if attrs.get("expires_at") and attrs["expires_at"] <= timezone.now():
                raise serializers.ValidationError({"expires_at": "Expiry must be in the future."})
            if attrs["emergency_access"]:
                if attrs.get("role_code") != "support-operator":
                    raise serializers.ValidationError({"role_code": "Emergency access uses the Support Operator role."})
                if not attrs.get("expires_at"):
                    raise serializers.ValidationError({"expires_at": "Emergency access requires an expiry."})
                if attrs["expires_at"] > timezone.now() + timedelta(hours=8):
                    raise serializers.ValidationError({"expires_at": "Emergency access cannot exceed eight hours."})
        elif not attrs.get("assignment_id"):
            raise serializers.ValidationError({"assignment_id": "Select an assignment to revoke."})
        return attrs


class PlatformSessionRevocationSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=120)
    reason = serializers.CharField(min_length=10, max_length=500)
    ticket_reference = serializers.CharField(min_length=3, max_length=120)
    user_id = serializers.IntegerField(min_value=1)


class PlatformOperationService:
    APPROVAL_TTL_HOURS = 24
    ONBOARDING_STAGES = [
        "owner", "customer_account", "subscription", "entity", "financial_years",
        "branches", "defaults", "membership", "verification",
    ]

    @staticmethod
    def required_approval_count(operation):
        return 2 if operation.risk == PlatformOperationRequest.Risk.CRITICAL else 1

    @staticmethod
    def _hash(payload):
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def _json_value(cls, value):
        if isinstance(value, dict):
            return {str(key): cls._json_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_value(item) for item in value]
        if isinstance(value, Model):
            return value.pk
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, UUID):
            return str(value)
        return value

    @classmethod
    def onboarding_readiness(cls, *, entity, owner, customer_account, onboarding_result):
        financial = onboarding_result.get("financial") or {}
        numbering = cls.entity_numbering_repair_preview(entity)
        posting = cls.entity_posting_mapping_repair_preview(entity)
        rbac = cls.entity_rbac_role_repair_preview(entity)
        catalog = cls.entity_catalog_repair_preview(entity)
        assets = cls.entity_asset_repair_preview(entity)
        trade = cls.entity_trade_settings_repair_preview(entity)
        choices = cls.entity_choice_override_audit(entity)
        subscription_count = CustomerSubscription.objects.filter(
            customer_account=customer_account,
            is_active=True,
            ended_at__isnull=True,
        ).count()
        owner_membership_count = UserEntityAccess.objects.filter(
            customer_account=customer_account,
            user=owner,
            role=UserEntityAccess.Role.OWNER,
            is_active=True,
        ).count()

        def check(code, label, ready, count, detail):
            return {
                "code": code,
                "label": label,
                "status": "ready" if ready else "attention",
                "count": count,
                "detail": detail,
                "repair_route": f"/platform/entities/{entity.id}#configuration-health" if not ready else "",
            }

        checks = [
            check("owner", "Owner access", owner_membership_count == 1, owner_membership_count, "One active owner membership is required."),
            check("branch", "Head office branch", entity.subentity.filter(isactive=True, is_head_office=True).exists(), entity.subentity.filter(isactive=True).count(), "An active head office is required."),
            check("financial_year", "Active financial year", entity.fy.filter(isactive=True).exists(), entity.fy.filter(isactive=True).count(), "At least one active financial year is required."),
            check("financial", "Chart of accounts", bool(financial.get("account_head_count")) and bool(financial.get("default_account_count")), financial.get("default_account_count", 0), "Standard account heads and default ledgers must be seeded."),
            check("posting", "Posting mappings", posting["healthy"], posting["existing_required_mapping_count"], "All required posting roles must resolve to entity ledgers."),
            check("numbering", "Document numbering", numbering["healthy"], numbering["expected_series_count"] - numbering["missing_series_count"], "Every active document type needs entity and branch numbering."),
            check("rbac", "Roles and permissions", rbac["healthy"], rbac["existing_role_count"], "Default operational roles must be active."),
            check("subscription", "Subscription", subscription_count == 1, subscription_count, "One current subscription is required."),
            check("catalog", "Product and tax catalog", catalog["healthy"], sum(catalog["expected_counts"].values()) - catalog["missing_count"], "Default categories, units, and HSN/SAC rows must exist."),
            check("assets", "Asset defaults", assets["healthy"], assets["existing_category_count"], "Asset settings, categories, and ledgers must be available."),
            check("trade", "Purchase and sales settings", trade["healthy"], 2 - trade["missing_count"], "Entity-level purchase and sales settings are required."),
            check(
                "choices", "Purchase and sales choices",
                choices["purchase"]["missing_global_count"] == 0 and choices["sales"]["missing_global_count"] == 0,
                choices["purchase"]["configured_global_count"] + choices["sales"]["configured_global_count"],
                "Default purchase and sales choices must be available.",
            ),
        ]
        ready_count = sum(row["status"] == "ready" for row in checks)
        return {
            "status": "ready" if ready_count == len(checks) else "attention",
            "ready_count": ready_count,
            "total_count": len(checks),
            "checks": checks,
        }

    @classmethod
    def entity_numbering_repair_preview(cls, entity):
        financial_years = list(entity.fy.filter(isactive=True).order_by("id"))
        branches = list(entity.subentity.filter(isactive=True).order_by("id"))
        scopes = [(financial_year, None) for financial_year in financial_years]
        scopes.extend((financial_year, branch) for financial_year in financial_years for branch in branches)
        doc_types = {
            (row.module, row.doc_key): row
            for row in DocumentType.objects.filter(
                Q(*[Q(module=spec.module, doc_key=spec.doc_key) for spec in DEFAULT_NUMBERING_SPECS], _connector=Q.OR)
            )
        } if DEFAULT_NUMBERING_SPECS else {}
        missing = []
        for financial_year, branch in scopes:
            for spec in DEFAULT_NUMBERING_SPECS:
                doc_type = doc_types.get((spec.module, spec.doc_key))
                exists = bool(doc_type) and DocumentNumberSeries.objects.filter(
                    entity=entity,
                    entityfinid=financial_year,
                    subentity=branch,
                    doc_type=doc_type,
                    doc_code=spec.default_code,
                ).exists()
                if not exists:
                    missing.append({
                        "financial_year_id": financial_year.id,
                        "financial_year": financial_year.year_code or financial_year.desc,
                        "branch_id": branch.id if branch else None,
                        "branch": branch.subentityname if branch else "Entity-wide",
                        "module": spec.module,
                        "document_key": spec.doc_key,
                        "document_code": spec.default_code,
                    })
        blockers = []
        if not financial_years:
            blockers.append({"code": "no_active_financial_year", "message": "An active financial year is required before numbering can be repaired."})
        return {
            "eligible": bool(missing) and not blockers,
            "healthy": not missing and not blockers,
            "entity_id": entity.id,
            "active_financial_years": len(financial_years),
            "active_branches": len(branches),
            "scope_count": len(scopes),
            "expected_series_count": len(scopes) * len(DEFAULT_NUMBERING_SPECS),
            "missing_series_count": len(missing),
            "missing_series": missing,
            "blockers": blockers,
        }

    @classmethod
    def entity_posting_mapping_repair_preview(cls, entity):
        required = list(StaticAccount.objects.filter(is_required=True, is_active=True).order_by("code"))
        existing_codes = set(EntityStaticAccountMap.objects.filter(
            entity=entity, sub_entity__isnull=True, is_active=True,
            static_account__in=required,
        ).values_list("static_account__code", flat=True))
        template_entity_id = StaticAccountService.get_default_template_entity_id()
        source_rows = EntityStaticAccountMap.objects.filter(
            entity_id=template_entity_id, sub_entity__isnull=True, is_active=True,
            static_account__in=required,
        ).select_related("static_account", "account__ledger", "ledger").order_by("static_account__code", "-id")
        sources = {}
        for source in source_rows:
            sources.setdefault(source.static_account.code, source)
        target_accounts = {
            str(row["ledger__ledger_code"]): row
            for row in account.objects.filter(entity=entity, ledger__isnull=False).values("id", "ledger_id", "ledger__ledger_code")
        }
        target_ledgers = {
            str(row["ledger_code"]): row["id"]
            for row in Ledger.objects.filter(entity=entity, ledger_code__isnull=False).values("id", "ledger_code")
        }
        repairable = []
        blockers = []
        for static_account in required:
            if static_account.code in existing_codes:
                continue
            source = sources.get(static_account.code)
            source_ledger_code = None
            if source and source.account_id and getattr(source.account, "ledger_id", None):
                source_ledger_code = source.account.ledger.ledger_code
            if source_ledger_code is None and source and source.ledger_id:
                source_ledger_code = source.ledger.ledger_code
            target_account = target_accounts.get(str(source_ledger_code))
            target_ledger_id = target_account["ledger_id"] if target_account else target_ledgers.get(str(source_ledger_code))
            if source_ledger_code is None or target_ledger_id is None:
                blockers.append({
                    "code": "required_mapping_unresolved",
                    "static_account_code": static_account.code,
                    "message": f"Required role {static_account.code} cannot be resolved to an existing target ledger.",
                })
                continue
            repairable.append({
                "static_account_id": static_account.id,
                "static_account_code": static_account.code,
                "static_account_name": static_account.name,
                "ledger_code": str(source_ledger_code),
                "account_id": target_account["id"] if target_account else None,
                "ledger_id": target_ledger_id,
            })
        return {
            "eligible": bool(repairable) and not blockers,
            "healthy": not repairable and not blockers,
            "entity_id": entity.id,
            "template_entity_id": template_entity_id,
            "required_mapping_count": len(required),
            "existing_required_mapping_count": len(existing_codes),
            "missing_mapping_count": len(repairable) + len(blockers),
            "repairable_mappings": repairable,
            "blockers": blockers,
        }

    @classmethod
    def entity_rbac_role_repair_preview(cls, entity):
        role_codes = [row["code"] for row in RBACSeedService.DEFAULT_ROLE_SHELLS]
        existing = {row.code: row for row in Role.objects.filter(entity=entity, code__in=role_codes)}
        missing_roles = []
        blockers = []
        for spec in RBACSeedService.DEFAULT_ROLE_SHELLS:
            role = existing.get(spec["code"])
            if role and role.isactive:
                continue
            if role:
                blockers.append({
                    "code": "inactive_role_conflict", "role_code": spec["code"],
                    "message": f"Role {spec['code']} exists but is inactive and requires manual review.",
                })
                continue
            permission_ids = list(RoleTemplateService._permission_queryset_for_template(
                spec["template"]
            ).order_by("id").values_list("id", flat=True))
            if not permission_ids:
                blockers.append({
                    "code": "template_permissions_missing", "role_code": spec["code"],
                    "message": f"Template {spec['template']} has no active permissions.",
                })
                continue
            missing_roles.append({
                "name": spec["name"], "code": spec["code"], "priority": spec["priority"],
                "template": spec["template"], "permission_ids": permission_ids,
                "permission_count": len(permission_ids),
            })
        return {
            "eligible": bool(missing_roles) and not blockers,
            "healthy": not missing_roles and not blockers,
            "entity_id": entity.id,
            "baseline_role_count": len(role_codes),
            "existing_role_count": sum(1 for code in role_codes if code in existing and existing[code].isactive),
            "missing_role_count": len(missing_roles) + len(blockers),
            "missing_roles": missing_roles,
            "blockers": blockers,
        }

    @classmethod
    def entity_catalog_repair_preview(cls, entity):
        missing = {"categories": [], "uoms": [], "hsn_sac": []}
        blockers = []
        categories = {row.pcategoryname: row for row in ProductCategory.objects.filter(
            entity=entity, pcategoryname__in=[spec["name"] for spec in CatalogSeedService.CATEGORY_ROWS],
        )}
        for spec in CatalogSeedService.CATEGORY_ROWS:
            existing = categories.get(spec["name"])
            if existing and existing.isactive:
                continue
            if existing:
                blockers.append({"code": "inactive_catalog_conflict", "kind": "category", "key": spec["name"], "message": f"Category {spec['name']} exists but is inactive."})
                continue
            missing["categories"].append({"name": spec["name"], "parent": spec["parent"]})

        uoms = {row.code: row for row in UnitOfMeasure.objects.filter(
            entity=entity, code__in=[spec["code"] for spec in CatalogSeedService.UOM_ROWS],
        )}
        used_uqc = set(UnitOfMeasure.objects.filter(entity=entity).exclude(uqc__isnull=True).exclude(uqc="").values_list("uqc", flat=True))
        for spec in CatalogSeedService.UOM_ROWS:
            existing = uoms.get(spec["code"])
            if existing and existing.isactive:
                continue
            if existing:
                blockers.append({"code": "inactive_catalog_conflict", "kind": "uom", "key": spec["code"], "message": f"UOM {spec['code']} exists but is inactive."})
                continue
            desired_uqc = spec["uqc"] if spec["uqc"] not in used_uqc else None
            missing["uoms"].append({"code": spec["code"], "description": spec["description"], "uqc": desired_uqc})
            if desired_uqc:
                used_uqc.add(desired_uqc)

        hsn_rows = {row.code: row for row in HsnSac.objects.filter(
            entity=entity, code__in=[spec["code"] for spec in CatalogSeedService.HSN_ROWS],
        )}
        for spec in CatalogSeedService.HSN_ROWS:
            existing = hsn_rows.get(spec["code"])
            if existing and existing.isactive:
                continue
            if existing:
                blockers.append({"code": "inactive_catalog_conflict", "kind": "hsn_sac", "key": spec["code"], "message": f"HSN/SAC {spec['code']} exists but is inactive."})
                continue
            missing["hsn_sac"].append(dict(spec))
        missing_count = sum(len(rows) for rows in missing.values())
        return {
            "eligible": missing_count > 0 and not blockers, "healthy": missing_count == 0 and not blockers,
            "entity_id": entity.id, "expected_counts": {
                "categories": len(CatalogSeedService.CATEGORY_ROWS), "uoms": len(CatalogSeedService.UOM_ROWS),
                "hsn_sac": len(CatalogSeedService.HSN_ROWS),
            }, "missing_count": missing_count + len(blockers), "missing": missing, "blockers": blockers,
        }

    @classmethod
    @transaction.atomic
    def create_entity_catalog_repair(cls, *, actor, entity, validated_data):
        entity = Entity.objects.select_for_update().get(pk=entity.pk)
        if entity.updated_at != validated_data["expected_target_version"]:
            raise serializers.ValidationError({"expected_target_version": "Entity changed. Refresh before submitting."})
        preview = cls.entity_catalog_repair_preview(entity)
        if not preview["eligible"]:
            raise serializers.ValidationError({"repair": "No conflict-free catalog default repair is available.", "preview": preview})
        snapshot = {"entity_id": entity.id, "expected_target_version": validated_data["expected_target_version"].isoformat(), "missing": preview["missing"]}
        snapshot_hash = cls._hash(snapshot)
        existing = PlatformOperationRequest.objects.select_for_update().filter(requested_by=actor, idempotency_key=validated_data["idempotency_key"]).first()
        if existing:
            if existing.payload_hash != snapshot_hash:
                raise serializers.ValidationError({"idempotency_key": "This key was already used with a different operation payload."})
            return existing, False
        operation = PlatformOperationRequest.objects.create(
            operation_type=PlatformOperationRequest.OperationType.REPAIR_ENTITY_CATALOG_DEFAULTS,
            risk=PlatformOperationRequest.Risk.HIGH, status=PlatformOperationRequest.Status.PENDING_APPROVAL,
            requested_by=actor, reason=validated_data["reason"].strip(), ticket_reference=validated_data["ticket_reference"].strip(),
            idempotency_key=validated_data["idempotency_key"], payload_hash=snapshot_hash, request_snapshot=snapshot,
            validation_snapshot={"valid": True, "preview": preview}, customer_account_id=entity.customer_account_id,
            entity_id=entity.id, expected_target_version=validated_data["expected_target_version"],
        )
        return operation, True

    @classmethod
    def entity_asset_repair_preview(cls, entity):
        ledger_codes = {row["key"]: row["ledger_code"] for row in ASSET_LEDGER_DEFINITIONS}
        ledger_codes.update({
            "acc_dep_tangible": ACCUMULATED_DEPRECIATION_LEDGER_CODE,
            "impairment_reserve": IMPAIRMENT_RESERVE_LEDGER_CODE,
            "acc_dep_vehicle": VEHICLE_ACCUMULATED_DEPRECIATION_LEDGER_CODE,
            "acc_amortization_intangible": INTANGIBLE_ACCUMULATED_AMORTIZATION_LEDGER_CODE,
            "acc_dep_rou": ROU_ACCUMULATED_DEPRECIATION_LEDGER_CODE,
            "depreciation_expense": DEPRECIATION_EXPENSE_LEDGER_CODE,
            "amortization_expense": AMORTIZATION_EXPENSE_LEDGER_CODE,
            "gain_on_sale": GAIN_ON_SALE_LEDGER_CODE,
            "loss_on_sale": LOSS_ON_SALE_LEDGER_CODE,
            "impairment_expense": IMPAIRMENT_EXPENSE_LEDGER_CODE,
        })
        ledgers = {str(row.ledger_code): row for row in Ledger.objects.filter(
            entity=entity, ledger_code__in=ledger_codes.values(), isactive=True,
        )}
        existing = {row.code: row for row in AssetCategory.objects.filter(
            entity=entity, subentity__isnull=True,
            code__in=[row["code"] for row in CATEGORY_DEFINITIONS],
        )}
        names = set(AssetCategory.objects.filter(entity=entity, subentity__isnull=True).values_list("name", flat=True))
        missing_categories, blockers = [], []
        ledger_fields = {
            "asset_ledger_id": "asset_ledger_key",
            "accumulated_depreciation_ledger_id": "accumulated_depreciation_key",
            "depreciation_expense_ledger_id": "depreciation_expense_key",
            "impairment_expense_ledger_id": "impairment_expense_key",
            "impairment_reserve_ledger_id": "impairment_reserve_key",
            "gain_on_sale_ledger_id": "gain_on_sale_key",
            "loss_on_sale_ledger_id": "loss_on_sale_key",
            "cwip_ledger_id": "cwip_ledger_key",
        }
        for spec in CATEGORY_DEFINITIONS:
            current = existing.get(spec["code"])
            if current and current.is_active:
                continue
            if current:
                blockers.append({"code": "inactive_asset_category", "key": spec["code"], "message": f"Asset category {spec['code']} exists but is inactive."})
                continue
            if spec["name"] in names:
                blockers.append({"code": "asset_category_name_conflict", "key": spec["code"], "message": f"Asset category name {spec['name']} is already used by another code."})
                continue
            row = {
                "code": spec["code"], "name": spec["name"], "nature": spec["nature"],
                "depreciation_method": AssetCategory.DepreciationMethod.SLM,
                "useful_life_months": spec["useful_life_months"],
                "residual_value_percent": str(spec["residual_value_percent"]),
            }
            unresolved = []
            for field, key_field in ledger_fields.items():
                key = spec[key_field]
                ledger = ledgers.get(str(ledger_codes[key])) if key else None
                row[field] = ledger.id if ledger else None
                if key and not ledger:
                    unresolved.append(str(ledger_codes[key]))
            if unresolved:
                blockers.append({"code": "missing_asset_ledger", "key": spec["code"], "message": f"Asset category {spec['code']} requires missing ledgers: {', '.join(unresolved)}."})
            else:
                missing_categories.append(row)
        settings_count = AssetSettings.objects.filter(entity=entity, subentity__isnull=True).count()
        if settings_count > 1:
            blockers.append({"code": "duplicate_asset_settings", "key": "global", "message": "Multiple entity-level asset settings rows require manual consolidation."})
        missing_settings = settings_count == 0
        missing_count = len(missing_categories) + int(missing_settings)
        return {
            "eligible": missing_count > 0 and not blockers,
            "healthy": missing_count == 0 and not blockers,
            "entity_id": entity.id, "expected_category_count": len(CATEGORY_DEFINITIONS),
            "existing_category_count": len(CATEGORY_DEFINITIONS) - len(missing_categories) - sum(1 for row in blockers if row["code"] in {"inactive_asset_category", "asset_category_name_conflict", "missing_asset_ledger"}),
            "missing_count": missing_count + len(blockers), "missing_settings": missing_settings,
            "missing_categories": missing_categories, "blockers": blockers,
        }

    @classmethod
    @transaction.atomic
    def create_entity_asset_repair(cls, *, actor, entity, validated_data):
        entity = Entity.objects.select_for_update().get(pk=entity.pk)
        if entity.updated_at != validated_data["expected_target_version"]:
            raise serializers.ValidationError({"expected_target_version": "Entity changed. Refresh before submitting."})
        preview = cls.entity_asset_repair_preview(entity)
        if not preview["eligible"]:
            raise serializers.ValidationError({"repair": "No conflict-free asset default repair is available.", "preview": preview})
        snapshot = {
            "entity_id": entity.id,
            "expected_target_version": validated_data["expected_target_version"].isoformat(),
            "missing_settings": preview["missing_settings"], "categories": preview["missing_categories"],
        }
        snapshot_hash = cls._hash(snapshot)
        existing = PlatformOperationRequest.objects.select_for_update().filter(
            requested_by=actor, idempotency_key=validated_data["idempotency_key"],
        ).first()
        if existing:
            if existing.payload_hash != snapshot_hash:
                raise serializers.ValidationError({"idempotency_key": "This key was already used with a different operation payload."})
            return existing, False
        return PlatformOperationRequest.objects.create(
            operation_type=PlatformOperationRequest.OperationType.REPAIR_ENTITY_ASSET_DEFAULTS,
            risk=PlatformOperationRequest.Risk.HIGH, status=PlatformOperationRequest.Status.PENDING_APPROVAL,
            requested_by=actor, reason=validated_data["reason"].strip(), ticket_reference=validated_data["ticket_reference"].strip(),
            idempotency_key=validated_data["idempotency_key"], payload_hash=snapshot_hash, request_snapshot=snapshot,
            validation_snapshot={"valid": True, "preview": preview}, customer_account_id=entity.customer_account_id,
            entity_id=entity.id, expected_target_version=validated_data["expected_target_version"],
        ), True

    @classmethod
    def entity_trade_settings_repair_preview(cls, entity):
        purchase_count = PurchaseSettings.objects.filter(entity=entity, subentity__isnull=True).count()
        sales_rows = SalesSettings.objects.filter(entity=entity, subentity__isnull=True)
        sales_count = sales_rows.count()
        active_years = list(EntityFinancialYear.objects.filter(entity=entity, isactive=True).values("id", "finstartyear", "finendyear"))
        blockers = []
        if purchase_count > 1:
            blockers.append({"code": "duplicate_purchase_settings", "key": "purchase", "message": "Multiple entity-level purchase settings rows require manual consolidation."})
        if sales_count > 1:
            blockers.append({"code": "duplicate_sales_settings", "key": "sales", "message": "Multiple entity-level sales settings rows require manual consolidation."})
        missing_purchase = purchase_count == 0
        missing_sales = sales_count == 0
        sales_financial_year_id = None
        if missing_sales:
            if len(active_years) != 1:
                blockers.append({"code": "ambiguous_sales_financial_year", "key": "sales", "message": "Exactly one active financial year is required to restore sales settings."})
            else:
                sales_financial_year_id = active_years[0]["id"]
        missing_count = int(missing_purchase) + int(missing_sales)
        return {
            "eligible": missing_count > 0 and not blockers,
            "healthy": missing_count == 0 and not blockers,
            "entity_id": entity.id, "missing_count": missing_count + len(blockers),
            "missing_purchase_settings": missing_purchase, "missing_sales_settings": missing_sales,
            "sales_financial_year_id": sales_financial_year_id, "blockers": blockers,
        }

    @staticmethod
    def entity_choice_override_audit(entity):
        def audit_domain(model, catalog):
            expected = {(group, key) for group, keys in catalog.items() for key in keys}
            rows = list(model.objects.filter(entity=entity).values(
                "id", "subentity_id", "choice_group", "choice_key", "is_enabled", "override_label",
            ))
            grouped = {}
            for row in rows:
                identity = (row["subentity_id"], row["choice_group"], row["choice_key"])
                grouped.setdefault(identity, []).append(row["id"])
            global_present = {(row["choice_group"], row["choice_key"]) for row in rows if row["subentity_id"] is None}
            missing_global = [{"group": group, "key": key} for group, key in sorted(expected - global_present)]
            unknown = [{"id": row["id"], "subentity_id": row["subentity_id"], "group": row["choice_group"], "key": row["choice_key"]}
                       for row in rows if (row["choice_group"], row["choice_key"]) not in expected]
            duplicates = [{"subentity_id": scope, "group": group, "key": key, "row_ids": ids}
                          for (scope, group, key), ids in grouped.items() if len(ids) > 1]
            return {
                "expected_global_count": len(expected), "configured_global_count": len(expected & global_present),
                "missing_global_count": len(missing_global), "missing_global": missing_global,
                "configured_row_count": len(rows), "disabled_count": sum(not row["is_enabled"] for row in rows),
                "relabeled_count": sum(bool((row["override_label"] or "").strip()) for row in rows),
                "unknown_count": len(unknown), "unknown": unknown,
                "duplicate_count": len(duplicates), "duplicates": duplicates,
            }
        purchase = audit_domain(PurchaseChoiceOverride, PURCHASE_CHOICE_GROUPS)
        sales = audit_domain(SalesChoiceOverride, SALES_CHOICE_GROUPS)
        attention_count = purchase["unknown_count"] + purchase["duplicate_count"] + sales["unknown_count"] + sales["duplicate_count"]
        return {
            "entity_id": entity.id, "read_only": True, "attention_count": attention_count,
            "healthy": attention_count == 0, "purchase": purchase, "sales": sales,
            "guidance": "Missing global rows inherit system choices and are informational; disabled and relabeled rows are tenant policy.",
        }

    @classmethod
    @transaction.atomic
    def create_entity_trade_settings_repair(cls, *, actor, entity, validated_data):
        entity = Entity.objects.select_for_update().get(pk=entity.pk)
        if entity.updated_at != validated_data["expected_target_version"]:
            raise serializers.ValidationError({"expected_target_version": "Entity changed. Refresh before submitting."})
        preview = cls.entity_trade_settings_repair_preview(entity)
        if not preview["eligible"]:
            raise serializers.ValidationError({"repair": "No conflict-free purchase/sales settings repair is available.", "preview": preview})
        snapshot = {
            "entity_id": entity.id, "expected_target_version": validated_data["expected_target_version"].isoformat(),
            "missing_purchase_settings": preview["missing_purchase_settings"],
            "missing_sales_settings": preview["missing_sales_settings"],
            "sales_financial_year_id": preview["sales_financial_year_id"],
        }
        snapshot_hash = cls._hash(snapshot)
        existing = PlatformOperationRequest.objects.select_for_update().filter(
            requested_by=actor, idempotency_key=validated_data["idempotency_key"],
        ).first()
        if existing:
            if existing.payload_hash != snapshot_hash:
                raise serializers.ValidationError({"idempotency_key": "This key was already used with a different operation payload."})
            return existing, False
        return PlatformOperationRequest.objects.create(
            operation_type=PlatformOperationRequest.OperationType.REPAIR_ENTITY_TRADE_SETTINGS,
            risk=PlatformOperationRequest.Risk.HIGH, status=PlatformOperationRequest.Status.PENDING_APPROVAL,
            requested_by=actor, reason=validated_data["reason"].strip(), ticket_reference=validated_data["ticket_reference"].strip(),
            idempotency_key=validated_data["idempotency_key"], payload_hash=snapshot_hash, request_snapshot=snapshot,
            validation_snapshot={"valid": True, "preview": preview}, customer_account_id=entity.customer_account_id,
            entity_id=entity.id, expected_target_version=validated_data["expected_target_version"],
        ), True

    @classmethod
    @transaction.atomic
    def create_entity_rbac_role_repair(cls, *, actor, entity, validated_data):
        entity = Entity.objects.select_for_update().get(pk=entity.pk)
        if entity.updated_at != validated_data["expected_target_version"]:
            raise serializers.ValidationError({"expected_target_version": "Entity changed. Refresh before submitting."})
        preview = cls.entity_rbac_role_repair_preview(entity)
        if not preview["eligible"]:
            raise serializers.ValidationError({"repair": "No fully resolvable baseline role repair is available.", "preview": preview})
        snapshot = {
            "entity_id": entity.id,
            "expected_target_version": validated_data["expected_target_version"].isoformat(),
            "roles": preview["missing_roles"],
        }
        snapshot_hash = cls._hash(snapshot)
        existing = PlatformOperationRequest.objects.select_for_update().filter(
            requested_by=actor, idempotency_key=validated_data["idempotency_key"],
        ).first()
        if existing:
            if existing.payload_hash != snapshot_hash:
                raise serializers.ValidationError({"idempotency_key": "This key was already used with a different operation payload."})
            return existing, False
        operation = PlatformOperationRequest.objects.create(
            operation_type=PlatformOperationRequest.OperationType.REPAIR_ENTITY_RBAC_ROLES,
            risk=PlatformOperationRequest.Risk.HIGH, status=PlatformOperationRequest.Status.PENDING_APPROVAL,
            requested_by=actor, reason=validated_data["reason"].strip(),
            ticket_reference=validated_data["ticket_reference"].strip(), idempotency_key=validated_data["idempotency_key"],
            payload_hash=snapshot_hash, request_snapshot=snapshot,
            validation_snapshot={"valid": True, "preview": preview}, customer_account_id=entity.customer_account_id,
            entity_id=entity.id, expected_target_version=validated_data["expected_target_version"],
        )
        return operation, True

    @classmethod
    @transaction.atomic
    def create_entity_posting_mapping_repair(cls, *, actor, entity, validated_data):
        entity = Entity.objects.select_for_update().get(pk=entity.pk)
        if entity.updated_at != validated_data["expected_target_version"]:
            raise serializers.ValidationError({"expected_target_version": "Entity changed. Refresh before submitting."})
        preview = cls.entity_posting_mapping_repair_preview(entity)
        if not preview["eligible"]:
            raise serializers.ValidationError({"repair": "No fully resolvable required posting repair is available.", "preview": preview})
        snapshot = {
            "entity_id": entity.id,
            "expected_target_version": validated_data["expected_target_version"].isoformat(),
            "mappings": preview["repairable_mappings"],
        }
        snapshot_hash = cls._hash(snapshot)
        existing = PlatformOperationRequest.objects.select_for_update().filter(
            requested_by=actor, idempotency_key=validated_data["idempotency_key"],
        ).first()
        if existing:
            if existing.payload_hash != snapshot_hash:
                raise serializers.ValidationError({"idempotency_key": "This key was already used with a different operation payload."})
            return existing, False
        operation = PlatformOperationRequest.objects.create(
            operation_type=PlatformOperationRequest.OperationType.REPAIR_ENTITY_POSTING_MAPPINGS,
            risk=PlatformOperationRequest.Risk.HIGH,
            status=PlatformOperationRequest.Status.PENDING_APPROVAL,
            requested_by=actor,
            reason=validated_data["reason"].strip(), ticket_reference=validated_data["ticket_reference"].strip(),
            idempotency_key=validated_data["idempotency_key"], payload_hash=snapshot_hash,
            request_snapshot=snapshot, validation_snapshot={"valid": True, "preview": preview},
            customer_account_id=entity.customer_account_id, entity_id=entity.id,
            expected_target_version=validated_data["expected_target_version"],
        )
        return operation, True

    @classmethod
    @transaction.atomic
    def create_entity_numbering_repair(cls, *, actor, entity, validated_data):
        entity = Entity.objects.select_for_update().get(pk=entity.pk)
        if entity.updated_at != validated_data["expected_target_version"]:
            raise serializers.ValidationError({"expected_target_version": "Entity changed. Refresh before submitting."})
        preview = cls.entity_numbering_repair_preview(entity)
        if not preview["eligible"]:
            raise serializers.ValidationError({"repair": "No repairable numbering gaps were found.", "preview": preview})
        snapshot = {
            "entity_id": entity.id,
            "expected_target_version": validated_data["expected_target_version"].isoformat(),
            "missing_series": preview["missing_series"],
        }
        snapshot_hash = cls._hash(snapshot)
        existing = PlatformOperationRequest.objects.select_for_update().filter(
            requested_by=actor, idempotency_key=validated_data["idempotency_key"],
        ).first()
        if existing:
            if existing.payload_hash != snapshot_hash:
                raise serializers.ValidationError({"idempotency_key": "This key was already used with a different operation payload."})
            return existing, False
        operation = PlatformOperationRequest.objects.create(
            operation_type=PlatformOperationRequest.OperationType.REPAIR_ENTITY_NUMBERING,
            risk=PlatformOperationRequest.Risk.HIGH,
            status=PlatformOperationRequest.Status.PENDING_APPROVAL,
            requested_by=actor,
            reason=validated_data["reason"].strip(),
            ticket_reference=validated_data["ticket_reference"].strip(),
            idempotency_key=validated_data["idempotency_key"],
            payload_hash=snapshot_hash,
            request_snapshot=snapshot,
            validation_snapshot={"valid": True, "preview": preview},
            customer_account_id=entity.customer_account_id,
            entity_id=entity.id,
            expected_target_version=validated_data["expected_target_version"],
        )
        return operation, True

    @classmethod
    @transaction.atomic
    def create_onboarding_request(cls, *, actor, validated_data):
        snapshot = PlatformAuditService.redact(cls._json_value(validated_data["payload"]))
        validation = PlatformOnboardingValidationService.build_result(validated_data["payload"])
        snapshot_hash = cls._hash(snapshot)

        existing = PlatformOperationRequest.objects.select_for_update().filter(
            requested_by=actor,
            idempotency_key=validated_data["idempotency_key"],
        ).first()
        if existing:
            if existing.payload_hash != snapshot_hash:
                raise serializers.ValidationError({
                    "idempotency_key": "This key was already used with a different onboarding payload."
                }, code="idempotency_conflict")
            return existing, False, validation

        if not validation["valid"]:
            return None, False, validation

        operation = PlatformOperationRequest.objects.create(
            operation_type=PlatformOperationRequest.OperationType.ONBOARD_CUSTOMER,
            risk=PlatformOperationRequest.Risk.MEDIUM,
            status=PlatformOperationRequest.Status.VALIDATED,
            requested_by=actor,
            reason=validated_data["reason"],
            ticket_reference=validated_data.get("ticket_reference", ""),
            idempotency_key=validated_data["idempotency_key"],
            payload_hash=snapshot_hash,
            request_snapshot=snapshot,
            validation_snapshot=validation,
        )
        PlatformProvisioningJob.objects.create(
            operation=operation,
            stage_results={stage: {"status": "pending"} for stage in cls.ONBOARDING_STAGES},
        )
        return operation, True, validation

    @classmethod
    @transaction.atomic
    def create_customer_contact_update(cls, *, actor, customer, validated_data):
        changes = cls._json_value(validated_data["changes"])
        snapshot = {
            "customer_account_id": customer.id,
            "expected_target_version": validated_data["expected_target_version"].isoformat(),
            "changes": changes,
        }
        snapshot_hash = cls._hash(snapshot)
        existing = PlatformOperationRequest.objects.select_for_update().filter(
            requested_by=actor, idempotency_key=validated_data["idempotency_key"],
        ).first()
        if existing:
            if existing.payload_hash != snapshot_hash:
                raise serializers.ValidationError({
                    "idempotency_key": "This key was already used with a different operation payload."
                }, code="idempotency_conflict")
            return existing, False

        before = {field: getattr(customer, field) or "" for field in changes}
        operation = PlatformOperationRequest.objects.create(
            operation_type=PlatformOperationRequest.OperationType.CUSTOMER_CONTACT_UPDATE,
            risk=PlatformOperationRequest.Risk.MEDIUM,
            status=PlatformOperationRequest.Status.VALIDATED,
            requested_by=actor,
            reason=validated_data["reason"],
            ticket_reference=validated_data.get("ticket_reference", ""),
            idempotency_key=validated_data["idempotency_key"],
            payload_hash=snapshot_hash,
            request_snapshot=snapshot,
            validation_snapshot={"valid": True, "before": before, "after": {**before, **changes}},
            customer_account_id=customer.id,
            expected_target_version=validated_data["expected_target_version"],
        )
        return operation, True

    @classmethod
    @transaction.atomic
    def create_customer_status_update(cls, *, actor, customer, validated_data):
        desired_status = validated_data["desired_status"]
        if customer.status == desired_status:
            raise serializers.ValidationError({"desired_status": "Customer already has this status."})
        allowed_transition = {
            CustomerAccount.Status.ACTIVE: CustomerAccount.Status.SUSPENDED,
            CustomerAccount.Status.SUSPENDED: CustomerAccount.Status.ACTIVE,
        }
        if allowed_transition.get(customer.status) != desired_status:
            raise serializers.ValidationError({
                "desired_status": f"Transition from '{customer.status}' to '{desired_status}' is not permitted."
            })

        snapshot = {
            "customer_account_id": customer.id,
            "expected_target_version": validated_data["expected_target_version"].isoformat(),
            "desired_status": desired_status,
        }
        snapshot_hash = cls._hash(snapshot)
        existing = PlatformOperationRequest.objects.select_for_update().filter(
            requested_by=actor, idempotency_key=validated_data["idempotency_key"],
        ).first()
        if existing:
            if existing.payload_hash != snapshot_hash:
                raise serializers.ValidationError({
                    "idempotency_key": "This key was already used with a different operation payload."
                }, code="idempotency_conflict")
            return existing, False

        operation = PlatformOperationRequest.objects.create(
            operation_type=PlatformOperationRequest.OperationType.CUSTOMER_STATUS_UPDATE,
            risk=PlatformOperationRequest.Risk.HIGH,
            status=PlatformOperationRequest.Status.PENDING_APPROVAL,
            requested_by=actor,
            reason=validated_data["reason"],
            ticket_reference=validated_data["ticket_reference"],
            idempotency_key=validated_data["idempotency_key"],
            payload_hash=snapshot_hash,
            request_snapshot=snapshot,
            validation_snapshot={
                "valid": True,
                "before": {"status": customer.status},
                "after": {"status": desired_status},
            },
            customer_account_id=customer.id,
            expected_target_version=validated_data["expected_target_version"],
        )
        return operation, True

    @classmethod
    @transaction.atomic
    def create_customer_ownership_transfer(cls, *, actor, customer, validated_data):
        customer = CustomerAccount.objects.select_for_update().get(pk=customer.pk)
        if customer.updated_at != validated_data["expected_target_version"]:
            raise serializers.ValidationError({"expected_target_version": "Customer changed. Refresh before submitting."})
        membership = UserEntityAccess.objects.select_for_update().select_related("user").filter(
            pk=validated_data["target_membership_id"], customer_account=customer,
        ).first()
        if membership is None:
            raise serializers.ValidationError({"target_membership_id": "Select a membership belonging to this customer."})
        if membership.updated_at != validated_data["expected_membership_version"]:
            raise serializers.ValidationError({"expected_membership_version": "Target membership changed. Refresh before submitting."})
        if membership.user_id == customer.owner_id:
            raise serializers.ValidationError({"target_membership_id": "This user already owns the customer account."})
        if not membership.is_active or membership.is_expired:
            raise serializers.ValidationError({"target_membership_id": "New owner membership must be active and unexpired."})
        if not membership.user.is_active or not membership.user.email_verified:
            raise serializers.ValidationError({"target_membership_id": "New owner identity must be active and email verified."})
        snapshot = {
            "customer_account_id": customer.id,
            "expected_target_version": validated_data["expected_target_version"].isoformat(),
            "target_membership_id": membership.id,
            "target_user_id": membership.user_id,
            "expected_membership_version": validated_data["expected_membership_version"].isoformat(),
        }
        snapshot_hash = cls._hash(snapshot)
        existing = PlatformOperationRequest.objects.select_for_update().filter(
            requested_by=actor, idempotency_key=validated_data["idempotency_key"],
        ).first()
        if existing:
            if existing.payload_hash != snapshot_hash:
                raise serializers.ValidationError({"idempotency_key": "This key was already used with a different operation payload."})
            return existing, False
        operation = PlatformOperationRequest.objects.create(
            operation_type=PlatformOperationRequest.OperationType.TRANSFER_CUSTOMER_OWNERSHIP,
            risk=PlatformOperationRequest.Risk.CRITICAL,
            status=PlatformOperationRequest.Status.PENDING_APPROVAL,
            requested_by=actor,
            reason=validated_data["reason"],
            ticket_reference=validated_data["ticket_reference"],
            idempotency_key=validated_data["idempotency_key"],
            payload_hash=snapshot_hash,
            request_snapshot=snapshot,
            validation_snapshot={
                "valid": True,
                "before": {"owner_user_id": customer.owner_id},
                "after": {"owner_user_id": membership.user_id, "target_membership_id": membership.id},
            },
            customer_account_id=customer.id,
            expected_target_version=validated_data["expected_target_version"],
        )
        return operation, True

    @classmethod
    @transaction.atomic
    def create_entity_child_request(cls, *, actor, entity, validated_data, operation_type):
        payload_key = "branch" if operation_type == PlatformOperationRequest.OperationType.ADD_ENTITY_BRANCH else "financial_year"
        child = cls._json_value(validated_data[payload_key])
        snapshot = {
            "entity_id": entity.id,
            "expected_target_version": validated_data["expected_target_version"].isoformat(),
            payload_key: child,
        }
        snapshot_hash = cls._hash(snapshot)
        existing = PlatformOperationRequest.objects.select_for_update().filter(
            requested_by=actor, idempotency_key=validated_data["idempotency_key"],
        ).first()
        if existing:
            if existing.payload_hash != snapshot_hash:
                raise serializers.ValidationError({"idempotency_key": "This key was already used with a different operation payload."})
            return existing, False

        if operation_type == PlatformOperationRequest.OperationType.ADD_ENTITY_BRANCH:
            code = (child.get("subentity_code") or "").strip().upper()
            if code and entity.subentity.filter(subentity_code__iexact=code).exists():
                raise serializers.ValidationError({"branch": {"subentity_code": "This branch code already exists for the entity."}})
            risk = PlatformOperationRequest.Risk.MEDIUM
            status = PlatformOperationRequest.Status.VALIDATED
        else:
            start = validated_data[payload_key].get("finstartyear")
            end = validated_data[payload_key].get("finendyear")
            code = child.get("year_code")
            if code and entity.fy.filter(year_code__iexact=code).exists():
                raise serializers.ValidationError({"financial_year": {"year_code": "This financial year already exists for the entity."}})
            if start and end and entity.fy.filter(finstartyear__date__lte=end.date(), finendyear__date__gte=start.date()).exists():
                raise serializers.ValidationError({"financial_year": "This financial year overlaps an existing period."})
            risk = PlatformOperationRequest.Risk.HIGH
            status = PlatformOperationRequest.Status.PENDING_APPROVAL

        operation = PlatformOperationRequest.objects.create(
            operation_type=operation_type,
            risk=risk,
            status=status,
            requested_by=actor,
            reason=validated_data["reason"],
            ticket_reference=validated_data.get("ticket_reference", ""),
            idempotency_key=validated_data["idempotency_key"],
            payload_hash=snapshot_hash,
            request_snapshot=snapshot,
            validation_snapshot={"valid": True, "before": None, "after": child},
            customer_account_id=entity.customer_account_id,
            entity_id=entity.id,
            expected_target_version=validated_data["expected_target_version"],
        )
        return operation, True

    @classmethod
    @transaction.atomic
    def create_entity_gst_update(cls, *, actor, entity, validated_data):
        status = validated_data["gst_registration_status"]
        gstin = validated_data.get("gstin", "")
        current = entity.gst_registrations.filter(isactive=True, is_primary=True).first()
        current_gstin = current.gstin if current else ""
        if entity.gst_registration_status == status and current_gstin == gstin:
            raise serializers.ValidationError({"gstin": "Entity already has this GST registration configuration."})
        if gstin:
            duplicate = EntityGstRegistration.objects.filter(gstin__iexact=gstin, isactive=True)
            if current:
                duplicate = duplicate.exclude(pk=current.pk)
            if duplicate.exists():
                raise serializers.ValidationError({"gstin": "This GSTIN is already active for another entity."})
            address = entity.addresses.filter(isactive=True, is_primary=True, state__isnull=False).select_related("state").first()
            if address:
                state_code = str(address.state.statecode or "").strip().zfill(2)
                if state_code and gstin[:2] != state_code:
                    raise serializers.ValidationError({"gstin": f"GSTIN must match entity state code {state_code}."})

        snapshot = {
            "entity_id": entity.id,
            "expected_target_version": validated_data["expected_target_version"].isoformat(),
            "gst_registration_status": status,
            "gstin": gstin,
            "effective_from": cls._json_value(validated_data.get("effective_from")),
        }
        snapshot_hash = cls._hash(snapshot)
        existing = PlatformOperationRequest.objects.select_for_update().filter(
            requested_by=actor, idempotency_key=validated_data["idempotency_key"],
        ).first()
        if existing:
            if existing.payload_hash != snapshot_hash:
                raise serializers.ValidationError({"idempotency_key": "This key was already used with a different operation payload."})
            return existing, False
        operation = PlatformOperationRequest.objects.create(
            operation_type=PlatformOperationRequest.OperationType.UPDATE_ENTITY_GST_REGISTRATION,
            risk=PlatformOperationRequest.Risk.HIGH,
            status=PlatformOperationRequest.Status.PENDING_APPROVAL,
            requested_by=actor,
            reason=validated_data["reason"],
            ticket_reference=validated_data["ticket_reference"],
            idempotency_key=validated_data["idempotency_key"],
            payload_hash=snapshot_hash,
            request_snapshot=snapshot,
            validation_snapshot={
                "valid": True,
                "before": {"gst_registration_status": entity.gst_registration_status, "gstin": current_gstin},
                "after": {"gst_registration_status": status, "gstin": gstin},
            },
            customer_account_id=entity.customer_account_id,
            entity_id=entity.id,
            expected_target_version=validated_data["expected_target_version"],
        )
        return operation, True

    @classmethod
    @transaction.atomic
    def create_subscription_plan_change(cls, *, actor, customer, validated_data):
        subscription = (
            CustomerSubscription.objects.select_for_update()
            .filter(customer_account=customer, is_active=True, ended_at__isnull=True)
            .order_by("-started_at", "-id")
            .first()
        )
        if subscription is None:
            raise serializers.ValidationError({"subscription": "Customer has no current subscription."})
        if subscription.updated_at != validated_data["expected_target_version"]:
            raise serializers.ValidationError({"expected_target_version": "Subscription changed. Refresh before submitting."})
        try:
            plan = SubscriptionService.plan_queryset().get(code=validated_data["plan_code"])
        except SubscriptionPlan.DoesNotExist as exc:
            raise serializers.ValidationError({"plan_code": "Select an active subscription plan."}) from exc
        if not plan.is_active:
            raise serializers.ValidationError({"plan_code": "Select an active subscription plan."})
        if plan.id == subscription.plan_id:
            raise serializers.ValidationError({"plan_code": "Customer is already on this plan."})

        snapshot = {
            "customer_account_id": customer.id,
            "subscription_id": subscription.id,
            "expected_target_version": validated_data["expected_target_version"].isoformat(),
            "plan_code": plan.code,
            "plan_id": plan.id,
        }
        snapshot_hash = cls._hash(snapshot)
        existing = PlatformOperationRequest.objects.select_for_update().filter(
            requested_by=actor, idempotency_key=validated_data["idempotency_key"],
        ).first()
        if existing:
            if existing.payload_hash != snapshot_hash:
                raise serializers.ValidationError({"idempotency_key": "This key was already used with a different operation payload."})
            return existing, False
        operation = PlatformOperationRequest.objects.create(
            operation_type=PlatformOperationRequest.OperationType.CHANGE_SUBSCRIPTION_PLAN,
            risk=PlatformOperationRequest.Risk.HIGH,
            status=PlatformOperationRequest.Status.PENDING_APPROVAL,
            requested_by=actor,
            reason=validated_data["reason"],
            ticket_reference=validated_data["ticket_reference"],
            idempotency_key=validated_data["idempotency_key"],
            payload_hash=snapshot_hash,
            request_snapshot=snapshot,
            validation_snapshot={
                "valid": True,
                "before": {"subscription_id": subscription.id, "plan_code": subscription.plan.code},
                "after": {"plan_code": plan.code},
            },
            customer_account_id=customer.id,
            subscription_id=subscription.id,
            expected_target_version=validated_data["expected_target_version"],
        )
        return operation, True

    @classmethod
    @transaction.atomic
    def create_tenant_membership_update(cls, *, actor, customer, membership, validated_data):
        membership = UserEntityAccess.objects.select_for_update().get(pk=membership.pk, customer_account=customer)
        if membership.role == UserEntityAccess.Role.OWNER:
            raise serializers.ValidationError({"membership": "Owner access must be changed through ownership transfer."})
        if membership.updated_at != validated_data["expected_target_version"]:
            raise serializers.ValidationError({"expected_target_version": "Membership changed. Refresh before submitting."})
        before = {
            "role": membership.role,
            "is_active": membership.is_active,
            "expires_at": cls._json_value(membership.expires_at),
        }
        after = {
            "role": validated_data["role"],
            "is_active": validated_data["is_active"],
            "expires_at": cls._json_value(validated_data.get("expires_at")),
        }
        if before == after:
            raise serializers.ValidationError({"membership": "Membership already has this access configuration."})
        snapshot = {
            "customer_account_id": customer.id,
            "membership_id": membership.id,
            "user_id": membership.user_id,
            "expected_target_version": validated_data["expected_target_version"].isoformat(),
            **after,
        }
        snapshot_hash = cls._hash(snapshot)
        existing = PlatformOperationRequest.objects.select_for_update().filter(
            requested_by=actor, idempotency_key=validated_data["idempotency_key"],
        ).first()
        if existing:
            if existing.payload_hash != snapshot_hash:
                raise serializers.ValidationError({"idempotency_key": "This key was already used with a different operation payload."})
            return existing, False
        operation = PlatformOperationRequest.objects.create(
            operation_type=PlatformOperationRequest.OperationType.UPDATE_TENANT_MEMBERSHIP,
            risk=PlatformOperationRequest.Risk.HIGH,
            status=PlatformOperationRequest.Status.PENDING_APPROVAL,
            requested_by=actor,
            reason=validated_data["reason"],
            ticket_reference=validated_data["ticket_reference"],
            idempotency_key=validated_data["idempotency_key"],
            payload_hash=snapshot_hash,
            request_snapshot=snapshot,
            validation_snapshot={"valid": True, "before": before, "after": after},
            customer_account_id=customer.id,
            membership_id=membership.id,
            expected_target_version=validated_data["expected_target_version"],
        )
        return operation, True

    @classmethod
    @transaction.atomic
    def create_tenant_user_invite(cls, *, actor, customer, validated_data):
        customer = CustomerAccount.objects.select_for_update().get(pk=customer.pk)
        if customer.updated_at != validated_data["expected_target_version"]:
            raise serializers.ValidationError({"expected_target_version": "Customer changed. Refresh before submitting."})
        user = User.objects.filter(email__iexact=validated_data["email"]).first()
        if user and UserEntityAccess.objects.filter(customer_account=customer, user=user, is_active=True).exists():
            raise serializers.ValidationError({"email": "This user is already an active tenant member."})
        if not customer.entities.filter(isactive=True).exists():
            raise serializers.ValidationError({"customer": "Customer needs an active entity before users can be invited."})
        snapshot = {
            "customer_account_id": customer.id,
            "expected_target_version": validated_data["expected_target_version"].isoformat(),
            "email": validated_data["email"],
            "first_name": validated_data.get("first_name", "").strip(),
            "last_name": validated_data.get("last_name", "").strip(),
            "role": validated_data["role"],
            "expires_at": cls._json_value(validated_data.get("expires_at")),
        }
        snapshot_hash = cls._hash(snapshot)
        existing = PlatformOperationRequest.objects.select_for_update().filter(
            requested_by=actor, idempotency_key=validated_data["idempotency_key"],
        ).first()
        if existing:
            if existing.payload_hash != snapshot_hash:
                raise serializers.ValidationError({"idempotency_key": "This key was already used with a different operation payload."})
            return existing, False
        operation = PlatformOperationRequest.objects.create(
            operation_type=PlatformOperationRequest.OperationType.INVITE_TENANT_USER,
            risk=PlatformOperationRequest.Risk.MEDIUM,
            status=PlatformOperationRequest.Status.VALIDATED,
            requested_by=actor,
            reason=validated_data["reason"],
            ticket_reference=validated_data["ticket_reference"],
            idempotency_key=validated_data["idempotency_key"],
            payload_hash=snapshot_hash,
            request_snapshot=snapshot,
            validation_snapshot={"valid": True, "existing_identity": bool(user)},
            customer_account_id=customer.id,
            expected_target_version=validated_data["expected_target_version"],
        )
        return operation, True

    @staticmethod
    def _assert_invitation_resend_allowed(membership):
        if membership.role == UserEntityAccess.Role.OWNER or membership.customer_account.owner_id == membership.user_id:
            raise serializers.ValidationError({"membership": "Owner invitation cannot be resent."})
        if not membership.is_active:
            raise serializers.ValidationError({"membership": "Reactivate the membership before resending its invitation."})
        if membership.is_expired:
            raise serializers.ValidationError({"membership": "Extend membership expiry before resending its invitation."})
        if membership.user.email_verified:
            raise serializers.ValidationError({"membership": "This user's email is already verified."})
        now = timezone.now()
        metadata = membership.metadata or {}
        history = []
        for raw in metadata.get("platform_invite_resend_history", []):
            try:
                sent_at = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue
            if sent_at > now - timedelta(hours=24):
                history.append(sent_at)
        history.sort()
        if history and history[-1] > now - timedelta(seconds=60):
            raise serializers.ValidationError({"membership": "Wait 60 seconds before resending this invitation."})
        if len(history) >= 5:
            raise serializers.ValidationError({"membership": "Daily invitation resend limit reached."})
        return history

    @classmethod
    @transaction.atomic
    def create_tenant_invitation_resend(cls, *, actor, customer, membership, validated_data):
        snapshot = {
            "customer_account_id": customer.id,
            "membership_id": membership.id,
            "user_id": membership.user_id,
            "expected_target_version": validated_data["expected_target_version"].isoformat(),
        }
        snapshot_hash = cls._hash(snapshot)
        existing = PlatformOperationRequest.objects.select_for_update().filter(
            requested_by=actor, idempotency_key=validated_data["idempotency_key"],
        ).first()
        if existing:
            if existing.payload_hash != snapshot_hash:
                raise serializers.ValidationError({"idempotency_key": "This key was already used with a different operation payload."})
            return existing, False
        membership = UserEntityAccess.objects.select_for_update().select_related("user", "customer_account").get(
            pk=membership.pk, customer_account=customer,
        )
        if membership.updated_at != validated_data["expected_target_version"]:
            raise serializers.ValidationError({"expected_target_version": "Membership changed. Refresh before submitting."})
        cls._assert_invitation_resend_allowed(membership)
        operation = PlatformOperationRequest.objects.create(
            operation_type=PlatformOperationRequest.OperationType.RESEND_TENANT_INVITATION,
            risk=PlatformOperationRequest.Risk.MEDIUM,
            status=PlatformOperationRequest.Status.VALIDATED,
            requested_by=actor,
            reason=validated_data["reason"],
            ticket_reference=validated_data["ticket_reference"],
            idempotency_key=validated_data["idempotency_key"],
            payload_hash=snapshot_hash,
            request_snapshot=snapshot,
            validation_snapshot={"valid": True, "email": membership.user.email},
            customer_account_id=customer.id,
            membership_id=membership.id,
            expected_target_version=validated_data["expected_target_version"],
        )
        return operation, True

    @classmethod
    @transaction.atomic
    def create_platform_role_change(cls, *, actor, validated_data):
        action = validated_data["action"]
        assignment = None
        if action == "grant":
            target = User.objects.select_for_update().filter(pk=validated_data["user_id"], is_active=True).first()
            if target is None:
                raise serializers.ValidationError({"user_id": "Select an active user."})
            if validated_data.get("expires_at") and validated_data["expires_at"] <= timezone.now():
                raise serializers.ValidationError({"expires_at": "Expiry must be in the future."})
            role = PlatformRole.objects.filter(code=validated_data["role_code"], is_active=True).first()
            if role is None:
                raise serializers.ValidationError({"role_code": "Select an active platform role."})
            if PlatformUserRole.objects.filter(user=target, role=role, is_active=True, revoked_at__isnull=True).exists():
                raise serializers.ValidationError({"role_code": "This user already has an active assignment for the role."})
            snapshot = {
                "action": action, "user_id": target.id, "role_code": role.code,
                "expires_at": cls._json_value(validated_data.get("expires_at")),
                "emergency_access": validated_data.get("emergency_access", False),
            }
            target_version = target.updated_at
            before = None
        else:
            assignment = PlatformUserRole.objects.select_for_update().select_related("user", "role").filter(
                pk=validated_data["assignment_id"], is_active=True, revoked_at__isnull=True,
            ).first()
            if assignment is None:
                raise serializers.ValidationError({"assignment_id": "Select an active assignment."})
            if assignment.user_id == actor.id:
                raise serializers.ValidationError({"assignment_id": "You cannot request revocation of your own platform access."})
            target = assignment
            snapshot = {
                "action": action, "assignment_id": assignment.id,
                "user_id": assignment.user_id, "role_code": assignment.role.code,
            }
            target_version = assignment.updated_at
            before = {"state": "effective", "expires_at": cls._json_value(assignment.expires_at)}

        snapshot_hash = cls._hash(snapshot)
        existing = PlatformOperationRequest.objects.select_for_update().filter(
            requested_by=actor, idempotency_key=validated_data["idempotency_key"],
        ).first()
        if existing:
            if existing.payload_hash != snapshot_hash:
                raise serializers.ValidationError({"idempotency_key": "This key was already used with a different operation payload."})
            return existing, False
        operation = PlatformOperationRequest.objects.create(
            operation_type=PlatformOperationRequest.OperationType.CHANGE_PLATFORM_ROLE,
            risk=PlatformOperationRequest.Risk.CRITICAL,
            status=PlatformOperationRequest.Status.PENDING_APPROVAL,
            requested_by=actor,
            reason=validated_data["reason"], ticket_reference=validated_data["ticket_reference"],
            idempotency_key=validated_data["idempotency_key"], payload_hash=snapshot_hash,
            request_snapshot=snapshot,
            validation_snapshot={"valid": True, "before": before, "after": {"state": "effective" if action == "grant" else "revoked"}},
            expected_target_version=target_version,
        )
        return operation, True

    @classmethod
    @transaction.atomic
    def create_platform_session_revocation(cls, *, actor, validated_data):
        target = User.objects.select_for_update().filter(pk=validated_data["user_id"], is_active=True).first()
        if target is None:
            raise serializers.ValidationError({"user_id": "Select an active user."})
        if target.id == actor.id:
            raise serializers.ValidationError({"user_id": "You cannot revoke your own sessions from this workflow."})
        active_sessions = AuthSession.objects.filter(user=target, revoked_at__isnull=True, expires_at__gt=timezone.now()).count()
        if not active_sessions:
            raise serializers.ValidationError({"user_id": "This user has no active sessions."})
        snapshot = {"user_id": target.id, "active_session_count": active_sessions}
        snapshot_hash = cls._hash(snapshot)
        existing = PlatformOperationRequest.objects.select_for_update().filter(
            requested_by=actor, idempotency_key=validated_data["idempotency_key"],
        ).first()
        if existing:
            if existing.payload_hash != snapshot_hash:
                raise serializers.ValidationError({"idempotency_key": "This key was already used with a different operation payload."})
            return existing, False
        operation = PlatformOperationRequest.objects.create(
            operation_type=PlatformOperationRequest.OperationType.REVOKE_PLATFORM_SESSIONS,
            risk=PlatformOperationRequest.Risk.CRITICAL,
            status=PlatformOperationRequest.Status.PENDING_APPROVAL,
            requested_by=actor,
            reason=validated_data["reason"], ticket_reference=validated_data["ticket_reference"],
            idempotency_key=validated_data["idempotency_key"], payload_hash=snapshot_hash,
            request_snapshot=snapshot,
            validation_snapshot={"valid": True, "active_session_count": active_sessions},
            expected_target_version=target.updated_at,
        )
        return operation, True

    @staticmethod
    def _locked_operation_target(operation):
        if operation.operation_type == PlatformOperationRequest.OperationType.CHANGE_PLATFORM_ROLE:
            if operation.request_snapshot["action"] == "revoke":
                return PlatformUserRole.objects.select_for_update().get(pk=operation.request_snapshot["assignment_id"])
            return User.objects.select_for_update().get(pk=operation.request_snapshot["user_id"])
        if operation.operation_type == PlatformOperationRequest.OperationType.REVOKE_PLATFORM_SESSIONS:
            return User.objects.select_for_update().get(pk=operation.request_snapshot["user_id"])
        if operation.membership_id:
            return UserEntityAccess.objects.select_for_update().get(pk=operation.membership_id)
        if operation.subscription_id:
            return CustomerSubscription.objects.select_for_update().get(pk=operation.subscription_id)
        if operation.entity_id:
            return Entity.objects.select_for_update().get(pk=operation.entity_id)
        return CustomerAccount.objects.select_for_update().get(pk=operation.customer_account_id)

    @classmethod
    @transaction.atomic
    def decide_operation(cls, *, operation_id, actor, decision, comment):
        operation = PlatformOperationRequest.objects.select_for_update().get(pk=operation_id)
        if operation.status != PlatformOperationRequest.Status.PENDING_APPROVAL:
            raise serializers.ValidationError({"status": "Only pending operations can be decided."})
        if operation.requested_by_id == actor.id:
            raise serializers.ValidationError({"approver": "The requester cannot decide their own operation."})
        if operation.operation_type in {
            PlatformOperationRequest.OperationType.CHANGE_PLATFORM_ROLE,
            PlatformOperationRequest.OperationType.REVOKE_PLATFORM_SESSIONS,
        } and operation.request_snapshot.get("user_id") == actor.id:
            raise serializers.ValidationError({"approver": "The affected operator cannot approve this security operation."})
        if PlatformOperationApproval.objects.filter(operation=operation, decided_by=actor).exists():
            raise serializers.ValidationError({"approver": "This approver has already decided this operation."})
        if operation.expected_target_version is None:
            raise serializers.ValidationError({"target": "This operation has no target version."})

        target = cls._locked_operation_target(operation)
        if target.updated_at != operation.expected_target_version:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "stale_target"
            operation.failure_message = "Customer changed after this request was prepared. Review and submit a new request."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, None

        approval = PlatformOperationApproval.objects.create(
            operation=operation,
            decided_by=actor,
            decision=decision,
            comment=comment,
            target_version=target.updated_at,
        )
        if decision == PlatformOperationApproval.Decision.REJECTED:
            operation.status = PlatformOperationRequest.Status.REJECTED
        else:
            approval_count = PlatformOperationApproval.objects.filter(
                operation=operation,
                decision=PlatformOperationApproval.Decision.APPROVED,
            ).count()
            operation.status = (
                PlatformOperationRequest.Status.APPROVED
                if approval_count >= cls.required_approval_count(operation)
                else PlatformOperationRequest.Status.PENDING_APPROVAL
            )
        operation.save(update_fields=["status", "updated_at"])
        return operation, approval

    @classmethod
    def approved_target_version(cls, operation):
        approvals = list(PlatformOperationApproval.objects.filter(
            operation=operation,
            decision=PlatformOperationApproval.Decision.APPROVED,
        ).order_by("decided_at"))
        required = cls.required_approval_count(operation)
        if len(approvals) < required:
            raise serializers.ValidationError({"approval": f"Operation requires {required} independent approvals before execution."})
        versions = {approval.target_version for approval in approvals}
        if len(versions) != 1:
            raise serializers.ValidationError({"approval": "Approval target versions do not match."})
        return approvals[-1].target_version

    @classmethod
    @transaction.atomic
    def cancel_operation(cls, *, operation_id, actor, reason):
        operation = PlatformOperationRequest.objects.select_for_update().get(pk=operation_id)
        cancellable = {
            PlatformOperationRequest.Status.DRAFT,
            PlatformOperationRequest.Status.VALIDATED,
            PlatformOperationRequest.Status.PENDING_APPROVAL,
            PlatformOperationRequest.Status.APPROVED,
            PlatformOperationRequest.Status.FAILED,
        }
        if operation.status == PlatformOperationRequest.Status.CANCELLED:
            return operation, True
        if operation.status not in cancellable:
            raise serializers.ValidationError({"status": f"Operation in '{operation.status}' cannot be cancelled."})
        operation.status = PlatformOperationRequest.Status.CANCELLED
        operation.cancelled_by = actor
        operation.cancelled_at = timezone.now()
        operation.cancellation_reason = reason
        operation.save(update_fields=["status", "cancelled_by", "cancelled_at", "cancellation_reason", "updated_at"])
        return operation, False

    @classmethod
    @transaction.atomic
    def expire_approval_if_needed(cls, *, operation_id):
        operation = PlatformOperationRequest.objects.select_for_update().get(pk=operation_id)
        if operation.status != PlatformOperationRequest.Status.APPROVED:
            return operation, False
        approvals = PlatformOperationApproval.objects.filter(
            operation=operation,
            decision=PlatformOperationApproval.Decision.APPROVED,
        )
        ttl_hours = int(getattr(settings, "PLATFORM_OPS_APPROVAL_TTL_HOURS", cls.APPROVAL_TTL_HOURS))
        if approvals.count() >= cls.required_approval_count(operation) and not approvals.filter(
            decided_at__lte=timezone.now() - timedelta(hours=ttl_hours),
        ).exists():
            return operation, False
        operation.status = PlatformOperationRequest.Status.FAILED
        operation.failure_code = "approval_expired"
        operation.failure_message = "Approval expired before execution. Submit and approve a new request."
        operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
        return operation, True

    @classmethod
    def approval_expiry_cutoff(cls, *, now=None):
        ttl_hours = int(getattr(settings, "PLATFORM_OPS_APPROVAL_TTL_HOURS", cls.APPROVAL_TTL_HOURS))
        return (now or timezone.now()) - timedelta(hours=ttl_hours)

    @classmethod
    def expirable_approvals(cls, *, now=None):
        return PlatformOperationRequest.objects.filter(
            status=PlatformOperationRequest.Status.APPROVED,
            approvals__decision=PlatformOperationApproval.Decision.APPROVED,
            approvals__decided_at__lte=cls.approval_expiry_cutoff(now=now),
        ).distinct()

    @classmethod
    def expire_approved_operations(cls, *, now=None, dry_run=False):
        operation_ids = list(cls.expirable_approvals(now=now).values_list("id", flat=True))
        if dry_run:
            return {"matched": len(operation_ids), "expired": 0, "operation_ids": [str(value) for value in operation_ids]}
        expired_ids = []
        for operation_id in operation_ids:
            operation, expired = cls.expire_approval_if_needed(operation_id=operation_id)
            if not expired:
                continue
            expired_ids.append(str(operation.id))
            PlatformAuditService.log(
                actor=None,
                event_type="platform.operation.approval.expired",
                outcome=PlatformAuditEvent.Outcome.FAILED,
                permission_code="system.approval_expiry",
                customer_account_id=operation.customer_account_id,
                entity_id=operation.entity_id,
                details={"operation_id": str(operation.id), "trigger": "scheduled_sweep"},
            )
        return {"matched": len(operation_ids), "expired": len(expired_ids), "operation_ids": expired_ids}

    @staticmethod
    def validate_retry(operation):
        if operation.operation_type != PlatformOperationRequest.OperationType.ONBOARD_CUSTOMER:
            raise serializers.ValidationError({"operation_type": "Only onboarding provisioning failures can be retried."})
        if operation.status != PlatformOperationRequest.Status.FAILED:
            raise serializers.ValidationError({"status": "Only failed onboarding operations can be retried."})
        job = getattr(operation, "provisioning_job", None)
        if job is None or job.status != PlatformProvisioningJob.Status.FAILED:
            raise serializers.ValidationError({"job": "A failed provisioning job is required for retry."})

    @classmethod
    def onboarding_repair_preview(cls, operation):
        blockers = []
        if operation.operation_type != PlatformOperationRequest.OperationType.ONBOARD_CUSTOMER:
            blockers.append({"code": "unsupported_operation", "message": "Only onboarding operations support repair."})
        if operation.status != PlatformOperationRequest.Status.FAILED:
            blockers.append({"code": "operation_not_failed", "message": "Only failed onboarding operations can be repaired."})
        job = getattr(operation, "provisioning_job", None)
        if job is None or job.status != PlatformProvisioningJob.Status.FAILED:
            blockers.append({"code": "job_not_failed", "message": "A failed provisioning job is required for repair."})

        collisions = []
        snapshot = operation.request_snapshot or {}
        owner_email = (snapshot.get("owner") or {}).get("email")
        external_customer_id = (snapshot.get("customer") or {}).get("external_customer_id")
        entity_code = ((snapshot.get("onboarding") or {}).get("entity") or {}).get("entity_code")
        if owner_email and User.objects.filter(email__iexact=owner_email).exists():
            collisions.append({"code": "owner_email_in_use", "field": "owner.email"})
        if external_customer_id and CustomerAccount.objects.filter(external_customer_id=external_customer_id).exists():
            collisions.append({"code": "customer_reference_in_use", "field": "customer.external_customer_id"})
        if entity_code and Entity.objects.filter(entity_code__iexact=entity_code).exists():
            collisions.append({"code": "entity_code_in_use", "field": "onboarding.entity.entity_code"})
        if collisions:
            blockers.append({
                "code": "target_collision",
                "message": "Tenant identifiers are now in use. Submit a new onboarding request after review.",
            })

        return {
            "eligible": not blockers,
            "operation_id": str(operation.id),
            "failed_stage": job.current_stage if job else "",
            "attempt_count": job.attempt_count if job else 0,
            "strategy": "full_transaction_retry" if not blockers else "manual_review",
            "rollback_verified": not collisions,
            "blockers": blockers,
            "collisions": collisions,
        }

    @classmethod
    def validate_onboarding_repair(cls, operation):
        preview = cls.onboarding_repair_preview(operation)
        if not preview["eligible"]:
            raise serializers.ValidationError({"repair": preview})
        return preview

    @classmethod
    @transaction.atomic
    def execute_entity_child_request(cls, *, operation_id):
        operation = PlatformOperationRequest.objects.select_for_update().get(pk=operation_id)
        if operation.status == PlatformOperationRequest.Status.SUCCEEDED:
            return operation, True
        required_status = (
            PlatformOperationRequest.Status.APPROVED
            if operation.risk == PlatformOperationRequest.Risk.HIGH
            else PlatformOperationRequest.Status.VALIDATED
        )
        if operation.status != required_status:
            raise serializers.ValidationError({"status": f"Operation must be '{required_status}' before execution."})

        entity = Entity.objects.select_for_update().get(pk=operation.entity_id)
        approved_version = (
            cls.approved_target_version(operation)
            if operation.risk == PlatformOperationRequest.Risk.HIGH
            else operation.expected_target_version
        )
        if entity.updated_at != approved_version:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "stale_approval" if operation.risk == PlatformOperationRequest.Risk.HIGH else "stale_target"
            operation.failure_message = "Entity changed after review. Submit a new request against the current version."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False

        if operation.operation_type == PlatformOperationRequest.OperationType.ADD_ENTITY_BRANCH:
            data = dict(operation.request_snapshot["branch"])
            branch = SubEntity.objects.create(entity=entity, **data)
            child_id = branch.id
            result = {"branch_id": branch.id, "branch_name": branch.subentityname, "branch_code": branch.subentity_code}
        else:
            data = dict(operation.request_snapshot["financial_year"])
            financial_year = EntityFinancialYear.objects.create(entity=entity, createdby=operation.requested_by, **data)
            child_id = financial_year.id
            result = {"financial_year_id": financial_year.id, "year_code": financial_year.year_code}

        entity.save(update_fields=["updated_at"])
        fy_ids = list(entity.fy.values_list("id", flat=True))
        branch_ids = list(entity.subentity.values_list("id", flat=True))
        for fy_id in fy_ids:
            for branch_id in [None, *branch_ids]:
                NumberingSeedService.seed_documents(
                    entity_id=entity.id,
                    entityfinid_id=fy_id,
                    subentity_id=branch_id,
                    specs=DEFAULT_NUMBERING_SPECS,
                )
        operation.status = PlatformOperationRequest.Status.SUCCEEDED
        operation.result_snapshot = {**result, "entity_id": entity.id, "created_id": child_id, "target_version": entity.updated_at.isoformat()}
        operation.save(update_fields=["status", "result_snapshot", "updated_at"])
        return operation, False

    @classmethod
    @transaction.atomic
    def execute_entity_numbering_repair(cls, *, operation_id):
        operation = PlatformOperationRequest.objects.select_for_update().get(pk=operation_id)
        if operation.status == PlatformOperationRequest.Status.SUCCEEDED:
            return operation, True
        if operation.status != PlatformOperationRequest.Status.APPROVED:
            raise serializers.ValidationError({"status": "Numbering repair requires approval before execution."})

        approved_version = cls.approved_target_version(operation)
        entity = Entity.objects.select_for_update().get(pk=operation.entity_id)
        if entity.updated_at != approved_version:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "stale_approval"
            operation.failure_message = "Entity changed after approval. Reassess numbering and submit a new request."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False

        before = cls.entity_numbering_repair_preview(entity)
        if before["blockers"]:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = before["blockers"][0]["code"]
            operation.failure_message = before["blockers"][0]["message"]
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False

        missing_now = {
            (row["financial_year_id"], row["branch_id"], row["module"], row["document_key"], row["document_code"])
            for row in before["missing_series"]
        }
        approved_missing = operation.request_snapshot.get("missing_series", [])
        rows_to_create = [
            row for row in approved_missing
            if (row["financial_year_id"], row["branch_id"], row["module"], row["document_key"], row["document_code"]) in missing_now
        ]
        for row in rows_to_create:
            spec = next(spec for spec in DEFAULT_NUMBERING_SPECS if spec.doc_key == row["document_key"] and spec.module == row["module"])
            NumberingSeedService.seed_document(
                entity_id=entity.id,
                entityfinid_id=row["financial_year_id"],
                subentity_id=row["branch_id"],
                module=spec.module,
                doc_key=spec.doc_key,
                name=spec.name,
                default_code=spec.default_code,
                prefix=spec.prefix,
                start=spec.start,
                padding=spec.padding,
                reset=spec.reset,
                include_year=spec.include_year,
                include_month=spec.include_month,
            )
        after = cls.entity_numbering_repair_preview(entity)
        operation.status = PlatformOperationRequest.Status.SUCCEEDED
        operation.failure_code = ""
        operation.failure_message = ""
        operation.result_snapshot = {
            "entity_id": entity.id,
            "series_created": len(rows_to_create),
            "before": before,
            "after": after,
            "target_version": entity.updated_at.isoformat(),
        }
        operation.save(update_fields=["status", "failure_code", "failure_message", "result_snapshot", "updated_at"])
        return operation, False

    @classmethod
    @transaction.atomic
    def execute_entity_posting_mapping_repair(cls, *, operation_id):
        operation = PlatformOperationRequest.objects.select_for_update().get(pk=operation_id)
        if operation.status == PlatformOperationRequest.Status.SUCCEEDED:
            return operation, True
        if operation.status != PlatformOperationRequest.Status.APPROVED:
            raise serializers.ValidationError({"status": "Posting mapping repair requires approval before execution."})
        approved_version = cls.approved_target_version(operation)
        entity = Entity.objects.select_for_update().get(pk=operation.entity_id)
        if entity.updated_at != approved_version:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "stale_approval"
            operation.failure_message = "Entity changed after approval. Reassess posting mappings and submit a new request."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False

        created_codes = []
        skipped_codes = []
        for row in operation.request_snapshot.get("mappings", []):
            if EntityStaticAccountMap.objects.filter(
                entity=entity, sub_entity__isnull=True, static_account_id=row["static_account_id"], is_active=True,
            ).exists():
                skipped_codes.append(row["static_account_code"])
                continue
            static_account = StaticAccount.objects.filter(
                pk=row["static_account_id"], code=row["static_account_code"], is_required=True, is_active=True,
            ).first()
            ledger = Ledger.objects.filter(pk=row["ledger_id"], entity=entity, ledger_code=row["ledger_code"]).first()
            target_account = None
            if row.get("account_id"):
                target_account = account.objects.filter(
                    pk=row["account_id"], entity=entity, ledger_id=row["ledger_id"],
                ).first()
            if static_account is None or ledger is None or (row.get("account_id") and target_account is None):
                operation.status = PlatformOperationRequest.Status.FAILED
                operation.failure_code = "approved_mapping_unresolved"
                operation.failure_message = f"Approved target for {row['static_account_code']} is no longer valid."
                operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
                return operation, False
            EntityStaticAccountMap.objects.create(
                entity=entity, sub_entity=None, static_account=static_account,
                account=target_account, ledger=ledger, createdby=operation.requested_by,
            )
            created_codes.append(static_account.code)
        StaticAccountService.invalidate(entity.id)
        after = cls.entity_posting_mapping_repair_preview(entity)
        operation.status = PlatformOperationRequest.Status.SUCCEEDED
        operation.failure_code = ""
        operation.failure_message = ""
        operation.result_snapshot = {
            "entity_id": entity.id, "mappings_created": len(created_codes),
            "created_codes": created_codes, "skipped_existing_codes": skipped_codes,
            "after": after, "target_version": entity.updated_at.isoformat(),
        }
        operation.save(update_fields=["status", "failure_code", "failure_message", "result_snapshot", "updated_at"])
        return operation, False

    @classmethod
    @transaction.atomic
    def execute_entity_rbac_role_repair(cls, *, operation_id):
        operation = PlatformOperationRequest.objects.select_for_update().get(pk=operation_id)
        if operation.status == PlatformOperationRequest.Status.SUCCEEDED:
            return operation, True
        if operation.status != PlatformOperationRequest.Status.APPROVED:
            raise serializers.ValidationError({"status": "RBAC role repair requires approval before execution."})
        approved_version = cls.approved_target_version(operation)
        entity = Entity.objects.select_for_update().get(pk=operation.entity_id)
        if entity.updated_at != approved_version:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "stale_approval"
            operation.failure_message = "Entity changed after approval. Reassess RBAC roles and submit a new request."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False

        created_roles = []
        skipped_roles = []
        for row in operation.request_snapshot.get("roles", []):
            existing = Role.objects.filter(entity=entity, code=row["code"]).first()
            if existing and existing.isactive:
                skipped_roles.append(row["code"])
                continue
            if existing:
                operation.status = PlatformOperationRequest.Status.FAILED
                operation.failure_code = "approved_role_conflict"
                operation.failure_message = f"Role {row['code']} now conflicts with the approved repair."
                operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
                return operation, False
            approved_permission_ids = set(row["permission_ids"])
            active_permission_ids = set(Permission.objects.filter(
                id__in=approved_permission_ids, isactive=True,
            ).values_list("id", flat=True))
            if active_permission_ids != approved_permission_ids:
                operation.status = PlatformOperationRequest.Status.FAILED
                operation.failure_code = "approved_permissions_changed"
                operation.failure_message = f"Approved permissions for role {row['code']} are no longer active."
                operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
                return operation, False
            role = Role.objects.create(
                entity=entity, name=row["name"], code=row["code"], description=row["name"],
                role_level=Role.LEVEL_ENTITY, is_system_role=False, is_assignable=True,
                priority=row["priority"], createdby=operation.requested_by, isactive=True,
                metadata={"seed": "platform_consistency_repair", "template": row["template"]},
            )
            RolePermission.objects.bulk_create([
                RolePermission(
                    role=role, permission_id=permission_id, effect=RolePermission.EFFECT_ALLOW,
                    metadata={"seed": "platform_consistency_repair", "operation_id": str(operation.id)},
                )
                for permission_id in sorted(approved_permission_ids)
            ])
            created_roles.append({"id": role.id, "code": role.code, "permission_count": len(approved_permission_ids)})
        after = cls.entity_rbac_role_repair_preview(entity)
        operation.status = PlatformOperationRequest.Status.SUCCEEDED
        operation.failure_code = ""
        operation.failure_message = ""
        operation.result_snapshot = {
            "entity_id": entity.id, "roles_created": created_roles,
            "skipped_existing_roles": skipped_roles, "after": after,
            "target_version": entity.updated_at.isoformat(),
        }
        operation.save(update_fields=["status", "failure_code", "failure_message", "result_snapshot", "updated_at"])
        return operation, False

    @classmethod
    @transaction.atomic
    def execute_entity_catalog_repair(cls, *, operation_id):
        operation = PlatformOperationRequest.objects.select_for_update().get(pk=operation_id)
        if operation.status == PlatformOperationRequest.Status.SUCCEEDED:
            return operation, True
        if operation.status != PlatformOperationRequest.Status.APPROVED:
            raise serializers.ValidationError({"status": "Catalog repair requires approval before execution."})
        approved_version = cls.approved_target_version(operation)
        entity = Entity.objects.select_for_update().get(pk=operation.entity_id)
        if entity.updated_at != approved_version:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "stale_approval"
            operation.failure_message = "Entity changed after approval. Reassess catalog defaults and submit a new request."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False
        approved = operation.request_snapshot.get("missing", {})
        category_specs = approved.get("categories", [])
        uom_specs = approved.get("uoms", [])
        hsn_specs = approved.get("hsn_sac", [])

        conflicts = []
        category_names = {row["name"] for row in category_specs}
        for row in category_specs:
            existing = ProductCategory.objects.filter(entity=entity, pcategoryname=row["name"]).first()
            if existing and not existing.isactive:
                conflicts.append(f"category:{row['name']}")
            if row.get("parent") and row["parent"] not in category_names and not ProductCategory.objects.filter(
                entity=entity, pcategoryname=row["parent"], isactive=True,
            ).exists():
                conflicts.append(f"category_parent:{row['parent']}")
        for row in uom_specs:
            existing = UnitOfMeasure.objects.filter(entity=entity, code=row["code"]).first()
            if existing and not existing.isactive:
                conflicts.append(f"uom:{row['code']}")
            if row.get("uqc") and UnitOfMeasure.objects.filter(entity=entity, uqc=row["uqc"]).exclude(code=row["code"]).exists():
                conflicts.append(f"uqc:{row['uqc']}")
        for row in hsn_specs:
            existing = HsnSac.objects.filter(entity=entity, code=row["code"]).first()
            if existing and not existing.isactive:
                conflicts.append(f"hsn_sac:{row['code']}")
        if conflicts:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "approved_catalog_conflict"
            operation.failure_message = f"Approved catalog targets now conflict: {', '.join(sorted(set(conflicts)))}."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False

        created = {"categories": [], "uoms": [], "hsn_sac": []}
        skipped = {"categories": [], "uoms": [], "hsn_sac": []}
        category_map = {row.pcategoryname: row for row in ProductCategory.objects.filter(entity=entity, isactive=True)}
        for row in category_specs:
            if row["name"] in category_map:
                skipped["categories"].append(row["name"])
                continue
            parent = category_map.get(row.get("parent"))
            obj = ProductCategory.objects.create(
                entity=entity, pcategoryname=row["name"], maincategory=parent,
                level=parent.level + 1 if parent else 1, isactive=True,
            )
            category_map[row["name"]] = obj
            created["categories"].append(row["name"])
        for row in uom_specs:
            if UnitOfMeasure.objects.filter(entity=entity, code=row["code"], isactive=True).exists():
                skipped["uoms"].append(row["code"])
                continue
            UnitOfMeasure.objects.create(entity=entity, isactive=True, **row)
            created["uoms"].append(row["code"])
        for row in hsn_specs:
            if HsnSac.objects.filter(entity=entity, code=row["code"], isactive=True).exists():
                skipped["hsn_sac"].append(row["code"])
                continue
            HsnSac.objects.create(entity=entity, isactive=True, **row)
            created["hsn_sac"].append(row["code"])
        after = cls.entity_catalog_repair_preview(entity)
        operation.status = PlatformOperationRequest.Status.SUCCEEDED
        operation.failure_code = ""
        operation.failure_message = ""
        operation.result_snapshot = {
            "entity_id": entity.id, "created": created, "skipped_existing": skipped,
            "created_count": sum(len(rows) for rows in created.values()), "after": after,
            "target_version": entity.updated_at.isoformat(),
        }
        operation.save(update_fields=["status", "failure_code", "failure_message", "result_snapshot", "updated_at"])
        return operation, False

    @classmethod
    @transaction.atomic
    def execute_entity_asset_repair(cls, *, operation_id):
        operation = PlatformOperationRequest.objects.select_for_update().get(pk=operation_id)
        if operation.status == PlatformOperationRequest.Status.SUCCEEDED:
            return operation, True
        if operation.status != PlatformOperationRequest.Status.APPROVED:
            raise serializers.ValidationError({"status": "Asset repair requires approval before execution."})
        entity = Entity.objects.select_for_update().get(pk=operation.entity_id)
        if entity.updated_at != cls.approved_target_version(operation):
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "stale_approval"
            operation.failure_message = "Entity changed after approval. Reassess asset defaults and submit a new request."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False
        approved = operation.request_snapshot
        conflicts = []
        categories = approved.get("categories", [])
        ledger_fields = [key for key in categories[0] if key.endswith("_ledger_id")] if categories else []
        ledger_ids = {row[key] for row in categories for key in ledger_fields if row.get(key)}
        valid_ledger_ids = set(Ledger.objects.filter(entity=entity, isactive=True, id__in=ledger_ids).values_list("id", flat=True))
        if valid_ledger_ids != ledger_ids:
            conflicts.append("approved_ledgers")
        for row in categories:
            current = AssetCategory.objects.filter(entity=entity, subentity__isnull=True, code=row["code"]).first()
            if current and not current.is_active:
                conflicts.append(f"category:{row['code']}")
            if not current and AssetCategory.objects.filter(entity=entity, subentity__isnull=True, name=row["name"]).exists():
                conflicts.append(f"category_name:{row['name']}")
        settings_count = AssetSettings.objects.filter(entity=entity, subentity__isnull=True).count()
        if settings_count > 1:
            conflicts.append("settings:duplicate")
        if conflicts:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "approved_asset_conflict"
            operation.failure_message = f"Approved asset targets now conflict: {', '.join(sorted(set(conflicts)))}."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False
        settings_created = False
        if approved.get("missing_settings") and settings_count == 0:
            AssetSettings.objects.create(
                entity=entity, subentity=None, default_doc_code_asset="FA", default_doc_code_disposal="FAD",
                default_useful_life_months=36, default_residual_value_percent=Decimal("5.0000"),
                created_by=operation.requested_by, updated_by=operation.requested_by,
            )
            settings_created = True
        created, skipped = [], []
        for row in categories:
            if AssetCategory.objects.filter(entity=entity, subentity__isnull=True, code=row["code"], is_active=True).exists():
                skipped.append(row["code"])
                continue
            payload = dict(row)
            payload["residual_value_percent"] = Decimal(payload["residual_value_percent"])
            AssetCategory.objects.create(
                entity=entity, subentity=None, created_by=operation.requested_by,
                updated_by=operation.requested_by, **payload,
            )
            created.append(row["code"])
        operation.status = PlatformOperationRequest.Status.SUCCEEDED
        operation.failure_code = ""
        operation.failure_message = ""
        operation.result_snapshot = {
            "entity_id": entity.id, "settings_created": settings_created,
            "categories_created": created, "skipped_existing": skipped,
            "after": cls.entity_asset_repair_preview(entity), "target_version": entity.updated_at.isoformat(),
        }
        operation.save(update_fields=["status", "failure_code", "failure_message", "result_snapshot", "updated_at"])
        return operation, False

    @classmethod
    @transaction.atomic
    def execute_entity_trade_settings_repair(cls, *, operation_id):
        operation = PlatformOperationRequest.objects.select_for_update().get(pk=operation_id)
        if operation.status == PlatformOperationRequest.Status.SUCCEEDED:
            return operation, True
        if operation.status != PlatformOperationRequest.Status.APPROVED:
            raise serializers.ValidationError({"status": "Purchase/sales settings repair requires approval before execution."})
        entity = Entity.objects.select_for_update().get(pk=operation.entity_id)
        if entity.updated_at != cls.approved_target_version(operation):
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "stale_approval"
            operation.failure_message = "Entity changed after approval. Reassess purchase and sales settings."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False
        approved = operation.request_snapshot
        purchase_count = PurchaseSettings.objects.filter(entity=entity, subentity__isnull=True).count()
        sales_count = SalesSettings.objects.filter(entity=entity, subentity__isnull=True).count()
        financial_year = None
        if approved.get("missing_sales_settings"):
            financial_year = EntityFinancialYear.objects.filter(
                pk=approved.get("sales_financial_year_id"), entity=entity, isactive=True,
            ).first()
        conflicts = []
        if purchase_count > 1 or sales_count > 1:
            conflicts.append("duplicate_global_settings")
        if approved.get("missing_sales_settings") and not financial_year:
            conflicts.append("sales_financial_year")
        if conflicts:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "approved_trade_settings_conflict"
            operation.failure_message = f"Approved settings targets now conflict: {', '.join(conflicts)}."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False
        created, skipped = [], []
        if approved.get("missing_purchase_settings"):
            if purchase_count == 0:
                PurchaseSettings.objects.create(entity=entity, subentity=None)
                created.append("purchase_settings")
            else:
                skipped.append("purchase_settings")
        if approved.get("missing_sales_settings"):
            if sales_count == 0:
                SalesSettings.objects.create(
                    entity=entity, entityfinid=financial_year, subentity=None,
                    created_by=operation.requested_by, updated_by=operation.requested_by,
                )
                created.append("sales_settings")
            else:
                skipped.append("sales_settings")
        operation.status = PlatformOperationRequest.Status.SUCCEEDED
        operation.failure_code = ""
        operation.failure_message = ""
        operation.result_snapshot = {
            "entity_id": entity.id, "created": created, "skipped_existing": skipped,
            "after": cls.entity_trade_settings_repair_preview(entity), "target_version": entity.updated_at.isoformat(),
        }
        operation.save(update_fields=["status", "failure_code", "failure_message", "result_snapshot", "updated_at"])
        return operation, False

    @classmethod
    @transaction.atomic
    def execute_entity_gst_update(cls, *, operation_id):
        operation = PlatformOperationRequest.objects.select_for_update().get(pk=operation_id)
        if operation.status == PlatformOperationRequest.Status.SUCCEEDED:
            return operation, True
        if operation.status != PlatformOperationRequest.Status.APPROVED:
            raise serializers.ValidationError({"status": "GST registration changes require approval before execution."})
        approved_version = cls.approved_target_version(operation)
        entity = Entity.objects.select_for_update().get(pk=operation.entity_id)
        if entity.updated_at != approved_version:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "stale_approval"
            operation.failure_message = "Entity changed after approval. A new GST request and approval are required."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False

        from sales.models.mastergst_models import SalesMasterGSTCredential

        before_row = entity.gst_registrations.filter(isactive=True, is_primary=True).first()
        before = {"gst_registration_status": entity.gst_registration_status, "gstin": before_row.gstin if before_row else ""}
        desired_status = operation.request_snapshot["gst_registration_status"]
        gstin = operation.request_snapshot["gstin"]
        if desired_status == Entity.GstStatus.UNREGISTERED:
            entity.gst_registrations.filter(isactive=True).update(
                isactive=False,
                is_primary=False,
                gst_cancelled_from=timezone.localdate(),
                updated_at=timezone.now(),
            )
            SalesMasterGSTCredential.objects.filter(entity=entity, is_active=True).update(is_active=False, updated_at=timezone.now())
        elif before_row:
            before_row.gstin = gstin
            before_row.gst_status = desired_status
            before_row.gst_effective_from = operation.request_snapshot.get("effective_from") or before_row.gst_effective_from
            before_row.gst_cancelled_from = None
            before_row.save()
            EntityOnboardingService._sync_compliance_credentials(entity=entity, rows=None)
        else:
            address = entity.addresses.filter(isactive=True, is_primary=True, state__isnull=False).first()
            EntityGstRegistration.objects.create(
                entity=entity,
                gstin=gstin,
                gst_status=desired_status,
                state_id=getattr(address, "state_id", None),
                gst_effective_from=operation.request_snapshot.get("effective_from"),
                is_primary=True,
                createdby=operation.requested_by,
            )
            EntityOnboardingService._sync_compliance_credentials(entity=entity, rows=None)
        entity.gst_registration_status = desired_status
        entity.save(update_fields=["gst_registration_status", "updated_at"])
        operation.status = PlatformOperationRequest.Status.SUCCEEDED
        operation.result_snapshot = {
            "entity_id": entity.id,
            "before": before,
            "after": {"gst_registration_status": desired_status, "gstin": gstin},
            "target_version": entity.updated_at.isoformat(),
        }
        operation.save(update_fields=["status", "result_snapshot", "updated_at"])
        return operation, False

    @classmethod
    @transaction.atomic
    def execute_subscription_plan_change(cls, *, operation_id):
        operation = PlatformOperationRequest.objects.select_for_update().get(pk=operation_id)
        if operation.status == PlatformOperationRequest.Status.SUCCEEDED:
            return operation, True
        if operation.status != PlatformOperationRequest.Status.APPROVED:
            raise serializers.ValidationError({"status": "Subscription plan changes require approval before execution."})
        approved_version = cls.approved_target_version(operation)
        subscription = CustomerSubscription.objects.select_for_update().select_related("plan").get(
            pk=operation.subscription_id,
        )
        if subscription.updated_at != approved_version or not subscription.is_current:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "stale_approval"
            operation.failure_message = "Subscription changed after approval. A new request and approval are required."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False
        plan = SubscriptionService.plan_queryset().get(pk=operation.request_snapshot["plan_id"])
        before = {"subscription_id": subscription.id, "plan_code": subscription.plan.code, "status": subscription.status}
        customer = CustomerAccount.objects.select_for_update().get(pk=subscription.customer_account_id)
        new_subscription = SubscriptionService.change_plan(
            customer_account=customer,
            new_plan=plan,
            changed_by=operation.requested_by,
        )
        operation.status = PlatformOperationRequest.Status.SUCCEEDED
        operation.result_snapshot = {
            "customer_account_id": customer.id,
            "before": before,
            "after": {
                "subscription_id": new_subscription.id,
                "plan_code": new_subscription.plan.code,
                "status": new_subscription.status,
            },
            "target_version": new_subscription.updated_at.isoformat(),
        }
        operation.save(update_fields=["status", "result_snapshot", "updated_at"])
        return operation, False

    @classmethod
    @transaction.atomic
    def execute_tenant_invitation_resend(cls, *, operation_id):
        operation = PlatformOperationRequest.objects.select_for_update().get(pk=operation_id)
        if operation.status == PlatformOperationRequest.Status.SUCCEEDED:
            return operation, True
        if operation.status != PlatformOperationRequest.Status.VALIDATED:
            raise serializers.ValidationError({"status": "Invitation resend must be validated before execution."})
        membership = UserEntityAccess.objects.select_for_update().select_related("user", "customer_account").get(
            pk=operation.membership_id, customer_account_id=operation.customer_account_id,
        )
        if membership.updated_at != operation.expected_target_version:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "stale_target"
            operation.failure_message = "Membership changed after validation. Submit a new resend request."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False
        history = cls._assert_invitation_resend_allowed(membership)
        AuthOTPService.create_otp(user=membership.user, email=membership.user.email, purpose="email_verification")
        sent_at = timezone.now()
        metadata = dict(membership.metadata or {})
        metadata["invite_last_sent_at"] = sent_at.isoformat()
        metadata["invite_last_sent_by_id"] = operation.requested_by_id
        metadata["invite_resend_count"] = int(metadata.get("invite_resend_count") or 0) + 1
        metadata["platform_invite_resend_history"] = [row.isoformat() for row in history] + [sent_at.isoformat()]
        membership.metadata = metadata
        membership.save(update_fields=["metadata", "updated_at"])
        operation.status = PlatformOperationRequest.Status.SUCCEEDED
        operation.result_snapshot = {
            "customer_account_id": membership.customer_account_id,
            "membership_id": membership.id,
            "user_id": membership.user_id,
            "email": membership.user.email,
            "delivery": "verification_otp_requested",
            "sent_at": sent_at.isoformat(),
            "resend_count": metadata["invite_resend_count"],
            "target_version": membership.updated_at.isoformat(),
        }
        operation.save(update_fields=["status", "result_snapshot", "updated_at"])
        return operation, False

    @classmethod
    @transaction.atomic
    def execute_tenant_user_invite(cls, *, operation_id):
        operation = PlatformOperationRequest.objects.select_for_update().get(pk=operation_id)
        if operation.status == PlatformOperationRequest.Status.SUCCEEDED:
            return operation, True
        if operation.status != PlatformOperationRequest.Status.VALIDATED:
            raise serializers.ValidationError({"status": "Invitation must be validated before execution."})
        customer = CustomerAccount.objects.select_for_update().get(pk=operation.customer_account_id)
        if customer.updated_at != operation.expected_target_version:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "stale_target"
            operation.failure_message = "Customer changed after validation. Submit a new invitation request."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False
        snapshot = operation.request_snapshot
        entity = customer.entities.filter(isactive=True).order_by("id").first()
        if entity is None:
            raise serializers.ValidationError({"customer": "Customer needs an active entity before users can be invited."})
        user = User.objects.filter(email__iexact=snapshot["email"]).first()
        SubscriptionService.assert_can_invite_user(entity=entity, user=user)
        created_user = user is None
        if created_user:
            base = snapshot["email"].split("@", 1)[0][:130] or "user"
            username = base
            counter = 1
            while User.objects.filter(username__iexact=username).exists():
                counter += 1
                username = f"{base}{counter}"
            user = User.objects.create_user(
                username=username,
                email=snapshot["email"],
                password=None,
                first_name=snapshot.get("first_name", ""),
                last_name=snapshot.get("last_name", ""),
                email_verified=False,
                is_active=True,
            )
        membership = SubscriptionService.ensure_account_membership(
            customer_account=customer,
            user=user,
            role=snapshot["role"],
            granted_by=operation.requested_by,
        )
        membership.expires_at = snapshot.get("expires_at")
        metadata = dict(membership.metadata or {})
        metadata.setdefault("created_invite_at", timezone.now().isoformat())
        metadata["invite_last_sent_at"] = timezone.now().isoformat()
        metadata["invite_last_sent_by_id"] = operation.requested_by_id
        membership.metadata = metadata
        membership.full_clean()
        membership.save(update_fields=["expires_at", "metadata", "updated_at"])
        if not user.email_verified:
            AuthOTPService.create_otp(user=user, email=user.email, purpose="email_verification")
        customer.save(update_fields=["updated_at"])
        operation.status = PlatformOperationRequest.Status.SUCCEEDED
        operation.result_snapshot = {
            "customer_account_id": customer.id,
            "membership_id": membership.id,
            "user_id": user.id,
            "email": user.email,
            "created_user": created_user,
            "verification_required": not user.email_verified,
            "target_version": customer.updated_at.isoformat(),
        }
        operation.save(update_fields=["status", "result_snapshot", "updated_at"])
        return operation, False

    @classmethod
    @transaction.atomic
    def execute_tenant_membership_update(cls, *, operation_id):
        operation = PlatformOperationRequest.objects.select_for_update().get(pk=operation_id)
        if operation.status == PlatformOperationRequest.Status.SUCCEEDED:
            return operation, True
        if operation.status != PlatformOperationRequest.Status.APPROVED:
            raise serializers.ValidationError({"status": "Membership changes require approval before execution."})
        approved_version = cls.approved_target_version(operation)
        membership = UserEntityAccess.objects.select_for_update().get(
            pk=operation.membership_id, customer_account_id=operation.customer_account_id,
        )
        if membership.updated_at != approved_version:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "stale_approval"
            operation.failure_message = "Membership changed after approval. A new request and approval are required."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False
        if membership.role == UserEntityAccess.Role.OWNER:
            raise serializers.ValidationError({"membership": "Owner access must be changed through ownership transfer."})
        before = {
            "role": membership.role,
            "is_active": membership.is_active,
            "expires_at": cls._json_value(membership.expires_at),
        }
        desired_active = operation.request_snapshot["is_active"]
        membership.role = operation.request_snapshot["role"]
        membership.expires_at = operation.request_snapshot.get("expires_at")
        membership.granted_by = operation.requested_by
        membership.full_clean()
        if not desired_active:
            membership.save(update_fields=["role", "expires_at", "granted_by", "updated_at"])
            SubscriptionService.deactivate_account_membership(membership=membership, deactivated_by=operation.requested_by)
        else:
            membership.is_active = True
            membership.save(update_fields=["role", "is_active", "expires_at", "granted_by", "updated_at"])
        membership.refresh_from_db()
        operation.status = PlatformOperationRequest.Status.SUCCEEDED
        operation.result_snapshot = {
            "customer_account_id": membership.customer_account_id,
            "membership_id": membership.id,
            "user_id": membership.user_id,
            "before": before,
            "after": {
                "role": membership.role,
                "is_active": membership.is_active,
                "expires_at": cls._json_value(membership.expires_at),
            },
            "target_version": membership.updated_at.isoformat(),
        }
        operation.save(update_fields=["status", "result_snapshot", "updated_at"])
        return operation, False

    @classmethod
    @transaction.atomic
    def execute_platform_role_change(cls, *, operation_id):
        operation = PlatformOperationRequest.objects.select_for_update().get(pk=operation_id)
        if operation.status == PlatformOperationRequest.Status.SUCCEEDED:
            return operation, True
        if operation.status != PlatformOperationRequest.Status.APPROVED:
            raise serializers.ValidationError({"status": "Platform role changes require two independent approvals."})
        approved_version = cls.approved_target_version(operation)
        snapshot = operation.request_snapshot
        target = cls._locked_operation_target(operation)
        if target.updated_at != approved_version:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "stale_approval"
            operation.failure_message = "Platform access changed after approval. Submit a new security request."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False
        if snapshot["action"] == "grant":
            role = PlatformRole.objects.get(code=snapshot["role_code"], is_active=True)
            if PlatformUserRole.objects.filter(user=target, role=role, is_active=True, revoked_at__isnull=True).exists():
                raise serializers.ValidationError({"role": "The approved role assignment already exists."})
            assignment = PlatformUserRole.objects.create(
                user=target, role=role, granted_by=operation.requested_by,
                expires_at=snapshot.get("expires_at") or None, reason=operation.reason,
            )
        else:
            assignment = target
            assignment.is_active = False
            assignment.revoked_at = timezone.now()
            assignment.full_clean()
            assignment.save(update_fields=["is_active", "revoked_at", "updated_at"])
        operation.status = PlatformOperationRequest.Status.SUCCEEDED
        operation.result_snapshot = {
            "assignment_id": assignment.id, "user_id": assignment.user_id,
            "role_code": assignment.role.code, "state": "effective" if snapshot["action"] == "grant" else "revoked",
        }
        operation.save(update_fields=["status", "result_snapshot", "updated_at"])
        return operation, False

    @classmethod
    @transaction.atomic
    def execute_platform_session_revocation(cls, *, operation_id):
        operation = PlatformOperationRequest.objects.select_for_update().get(pk=operation_id)
        if operation.status == PlatformOperationRequest.Status.SUCCEEDED:
            return operation, True
        if operation.status != PlatformOperationRequest.Status.APPROVED:
            raise serializers.ValidationError({"status": "Session revocation requires two independent approvals."})
        approved_version = cls.approved_target_version(operation)
        user = User.objects.select_for_update().get(pk=operation.request_snapshot["user_id"])
        if user.updated_at != approved_version:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "stale_approval"
            operation.failure_message = "User security state changed after approval. Submit a new request."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False
        now = timezone.now()
        revoked_count = AuthSession.objects.filter(user=user, revoked_at__isnull=True).update(
            revoked_at=now, revoked_reason="platform_security", updated_at=now,
        )
        AuthTokenService.bump_token_version(user)
        operation.status = PlatformOperationRequest.Status.SUCCEEDED
        operation.result_snapshot = {"user_id": user.id, "revoked_session_count": revoked_count}
        operation.save(update_fields=["status", "result_snapshot", "updated_at"])
        return operation, False

    @classmethod
    @transaction.atomic
    def execute_customer_ownership_transfer(cls, *, operation_id):
        operation = PlatformOperationRequest.objects.select_for_update().get(pk=operation_id)
        if operation.status == PlatformOperationRequest.Status.SUCCEEDED:
            return operation, True
        if operation.status != PlatformOperationRequest.Status.APPROVED:
            raise serializers.ValidationError({"status": "Ownership transfer requires independent approval before execution."})
        approved_version = cls.approved_target_version(operation)
        customer = CustomerAccount.objects.select_for_update().get(pk=operation.customer_account_id)
        if customer.updated_at != approved_version:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "stale_approval"
            operation.failure_message = "Customer changed after approval. A new ownership request and approval are required."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False
        memberships = list(UserEntityAccess.objects.select_for_update().select_related("user").filter(customer_account=customer))
        target = next((row for row in memberships if row.id == operation.request_snapshot["target_membership_id"]), None)
        expected_member_version = operation.request_snapshot["expected_membership_version"]
        if target is None or target.updated_at.isoformat() != expected_member_version:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "stale_membership"
            operation.failure_message = "Target membership changed after review. A new ownership request is required."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False
        if not target.is_active or target.is_expired or not target.user.is_active or not target.user.email_verified:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "ineligible_new_owner"
            operation.failure_message = "Target user is no longer eligible to own this customer account."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False
        previous_owner_id = customer.owner_id
        for membership in memberships:
            if membership.id != target.id and membership.role == UserEntityAccess.Role.OWNER:
                membership.role = UserEntityAccess.Role.ADMIN
                membership.save(update_fields=["role", "updated_at"])
        target.role = UserEntityAccess.Role.OWNER
        target.is_active = True
        target.expires_at = None
        target.granted_by = operation.requested_by
        target.save(update_fields=["role", "is_active", "expires_at", "granted_by", "updated_at"])
        customer.owner = target.user
        customer.save(update_fields=["owner", "updated_at"])
        operation.status = PlatformOperationRequest.Status.SUCCEEDED
        operation.result_snapshot = {
            "customer_account_id": customer.id,
            "before": {"owner_user_id": previous_owner_id},
            "after": {"owner_user_id": customer.owner_id, "owner_membership_id": target.id},
            "target_version": customer.updated_at.isoformat(),
        }
        operation.save(update_fields=["status", "result_snapshot", "updated_at"])
        return operation, False

    @classmethod
    @transaction.atomic
    def execute_customer_status_update(cls, *, operation_id):
        operation = PlatformOperationRequest.objects.select_for_update().get(pk=operation_id)
        if operation.status == PlatformOperationRequest.Status.SUCCEEDED:
            return operation, True
        if operation.status != PlatformOperationRequest.Status.APPROVED:
            raise serializers.ValidationError({"status": "This high-risk operation requires approval before execution."})

        approved_version = cls.approved_target_version(operation)
        customer = CustomerAccount.objects.select_for_update().get(pk=operation.customer_account_id)
        if customer.updated_at != approved_version:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "stale_approval"
            operation.failure_message = "Customer changed after approval. A new request and approval are required."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False

        before = {"status": customer.status, "status_reason": customer.status_reason or ""}
        customer.status = operation.request_snapshot["desired_status"]
        customer.status_reason = operation.reason
        customer.save(update_fields=["status", "status_reason", "updated_at"])
        operation.status = PlatformOperationRequest.Status.SUCCEEDED
        operation.result_snapshot = {
            "customer_account_id": customer.id,
            "before": before,
            "after": {"status": customer.status, "status_reason": customer.status_reason},
            "target_version": customer.updated_at.isoformat(),
        }
        operation.save(update_fields=["status", "result_snapshot", "updated_at"])
        return operation, False

    @classmethod
    @transaction.atomic
    def execute_customer_contact_update(cls, *, operation_id):
        operation = PlatformOperationRequest.objects.select_for_update().select_related("requested_by").get(pk=operation_id)
        if operation.status == PlatformOperationRequest.Status.SUCCEEDED:
            return operation, True
        if operation.status not in {PlatformOperationRequest.Status.VALIDATED, PlatformOperationRequest.Status.FAILED}:
            raise serializers.ValidationError({"status": f"Operation in '{operation.status}' cannot be executed."})

        customer = CustomerAccount.objects.select_for_update().get(pk=operation.customer_account_id)
        if customer.updated_at != operation.expected_target_version:
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = "stale_target"
            operation.failure_message = "Customer changed after this request was prepared. Review and submit a new request."
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            return operation, False

        changes = operation.request_snapshot["changes"]
        before = {field: getattr(customer, field) or "" for field in changes}
        for field, value in changes.items():
            setattr(customer, field, value or None)
        customer.save(update_fields=[*changes.keys(), "updated_at"])
        after = {field: getattr(customer, field) or "" for field in changes}
        operation.status = PlatformOperationRequest.Status.SUCCEEDED
        operation.failure_code = ""
        operation.failure_message = ""
        operation.result_snapshot = {
            "customer_account_id": customer.id,
            "before": before,
            "after": after,
            "target_version": customer.updated_at.isoformat(),
        }
        operation.save(update_fields=["status", "failure_code", "failure_message", "result_snapshot", "updated_at"])
        return operation, False

    @classmethod
    def serialize(cls, operation, *, include_detail=False):
        job = getattr(operation, "provisioning_job", None)
        payload = {
            "id": str(operation.id),
            "correlation_id": str(operation.correlation_id),
            "operation_type": operation.operation_type,
            "risk": operation.risk,
            "status": operation.status,
            "reason": operation.reason,
            "ticket_reference": operation.ticket_reference,
            "requested_by": {
                "id": operation.requested_by_id,
                "email": operation.requested_by.email,
            },
            "created_at": operation.created_at,
            "updated_at": operation.updated_at,
            "expected_target_version": operation.expected_target_version,
            "subscription_id": operation.subscription_id,
            "membership_id": operation.membership_id,
            "cancellation": None if not operation.cancelled_at else {
                "reason": operation.cancellation_reason,
                "cancelled_at": operation.cancelled_at,
                "cancelled_by": {
                    "id": operation.cancelled_by_id,
                    "email": operation.cancelled_by.email,
                },
            },
            "job": None if not job else {
                "status": job.status,
                "current_stage": job.current_stage,
                "completed_stages": job.completed_stages,
                "stage_results": job.stage_results,
                "attempt_count": job.attempt_count,
            },
        }
        if include_detail:
            payload["validation"] = operation.validation_snapshot
            payload["result"] = operation.result_snapshot
            payload["failure"] = {
                "code": operation.failure_code,
                "message": operation.failure_message,
            }
            approvals = list(operation.approvals.select_related("decided_by").all())
            payload["approvals_required"] = cls.required_approval_count(operation)
            payload["approvals"] = [{
                "decision": approval.decision,
                "comment": approval.comment,
                "decided_by": {"id": approval.decided_by_id, "email": approval.decided_by.email},
                "decided_at": approval.decided_at,
                "target_version": approval.target_version,
            } for approval in approvals]
            approval = approvals[0] if approvals else None
            payload["approval"] = None if approval is None else payload["approvals"][0]
        return payload

    @classmethod
    def _provision_onboarding(cls, operation):
        payload_serializer = PlatformOnboardingValidationSerializer(data=operation.request_snapshot)
        payload_serializer.is_valid(raise_exception=True)
        payload = payload_serializer.validated_data
        owner_data = payload["owner"]
        customer_data = payload["customer"]
        current_stage = "owner"

        try:
            with transaction.atomic():
                owner = User.objects.create_user(
                    username=owner_data["email"],
                    email=owner_data["email"],
                    password=None,
                    first_name=owner_data.get("first_name", ""),
                    last_name=owner_data.get("last_name", ""),
                    email_verified=False,
                )

                current_stage = "customer_account"
                account = SubscriptionService.handle_signup(
                    user=owner,
                    intent=payload["intent"],
                    plan_code=payload["plan_code"],
                )
                account_fields = (
                    "name", "legal_name", "trade_name", "primary_contact_email",
                    "primary_contact_phone", "external_customer_id", "account_type",
                    "country", "timezone",
                )
                for field in account_fields:
                    if field in customer_data:
                        setattr(account, field, customer_data[field] or None)
                account.status = CustomerAccount.Status.ACTIVE
                account.save(update_fields=[*account_fields, "status", "updated_at"])

                current_stage = "subscription"
                SubscriptionService.ensure_active_subscription(
                    customer_account=account,
                    intent=payload["intent"],
                    plan_code=payload["plan_code"],
                )

                current_stage = "entity"
                onboarding_serializer = EntityOnboardingCreateSerializer(data=operation.request_snapshot["onboarding"])
                onboarding_serializer.is_valid(raise_exception=True)
                onboarding_result = EntityOnboardingService.create_entity(
                    actor=owner,
                    payload=onboarding_serializer.validated_data,
                )
                entity = onboarding_result["entity"]

                readiness = cls.onboarding_readiness(
                    entity=entity,
                    owner=owner,
                    customer_account=account,
                    onboarding_result=onboarding_result,
                )

                current_stage = "verification"
                transaction.on_commit(lambda: AuthOTPService.create_otp(
                    user=owner,
                    email=owner.email,
                    purpose="password_reset",
                ))

                return {
                    "owner_id": owner.id,
                    "customer_account_id": account.id,
                    "entity_id": entity.id,
                    "entity_name": entity.entityname,
                    "financial_year_ids": onboarding_result.get("financial_year_ids", []),
                    "subentity_ids": onboarding_result.get("subentity_ids", []),
                    "readiness": readiness,
                    "verification": {"email": owner.email, "status": "password_setup_scheduled"},
                }
        except Exception as exc:
            exc.platform_stage = current_stage
            raise

    @classmethod
    @transaction.atomic
    def execute_onboarding(cls, *, operation_id):
        operation = (
            PlatformOperationRequest.objects.select_for_update()
            .select_related("requested_by")
            .get(pk=operation_id)
        )
        job = PlatformProvisioningJob.objects.select_for_update().get(operation=operation)
        if operation.status == PlatformOperationRequest.Status.SUCCEEDED:
            return operation, True
        allowed = {PlatformOperationRequest.Status.VALIDATED, PlatformOperationRequest.Status.FAILED}
        if operation.status not in allowed:
            raise serializers.ValidationError({
                "status": f"Operation in '{operation.status}' cannot be executed."
            })

        operation.status = PlatformOperationRequest.Status.RUNNING
        operation.failure_code = ""
        operation.failure_message = ""
        operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
        job.status = PlatformProvisioningJob.Status.RUNNING
        job.attempt_count += 1
        job.started_at = timezone.now()
        job.completed_at = None
        job.save(update_fields=["status", "attempt_count", "started_at", "completed_at", "updated_at"])

        try:
            result = cls._provision_onboarding(operation)
        except Exception as exc:
            stage = getattr(exc, "platform_stage", "validation")
            operation.status = PlatformOperationRequest.Status.FAILED
            operation.failure_code = getattr(exc, "default_code", "provisioning_failed")
            operation.failure_message = (
                f"Provisioning failed during the {stage} stage. Use the correlation ID to inspect server logs."
            )
            operation.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            job.status = PlatformProvisioningJob.Status.FAILED
            job.current_stage = stage
            stage_results = dict(job.stage_results)
            stage_results[stage] = {"status": "failed", "message": "Stage failed; tenant changes were rolled back."}
            job.stage_results = stage_results
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "current_stage", "stage_results", "completed_at", "updated_at"])
            return operation, False

        operation.status = PlatformOperationRequest.Status.SUCCEEDED
        operation.customer_account_id = result["customer_account_id"]
        operation.entity_id = result["entity_id"]
        operation.result_snapshot = result
        operation.save(update_fields=[
            "status", "customer_account_id", "entity_id", "result_snapshot", "updated_at",
        ])
        job.status = PlatformProvisioningJob.Status.SUCCEEDED
        job.current_stage = "verification"
        job.completed_stages = list(cls.ONBOARDING_STAGES)
        job.stage_results = {stage: {"status": "completed"} for stage in cls.ONBOARDING_STAGES}
        job.completed_at = timezone.now()
        job.save(update_fields=[
            "status", "current_stage", "completed_stages", "stage_results", "completed_at", "updated_at",
        ])
        return operation, False
