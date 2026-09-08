from django.db.models import Q
from rest_framework import serializers

from Authentication.models import User
from entity.models import Entity, EntityGstRegistration
from entity.onboarding_serializers import EntityOnboardingCreateSerializer
from subscriptions.models import CustomerAccount, SubscriptionPlan

from .read_models import mask_email, mask_gstin, mask_phone


class PlatformOwnerSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate_email(self, value):
        return value.strip().lower()


class PlatformCustomerOnboardingSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    legal_name = serializers.CharField(max_length=255)
    trade_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    primary_contact_email = serializers.EmailField(required=False, allow_blank=True)
    primary_contact_phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    external_customer_id = serializers.CharField(max_length=120, required=False, allow_blank=True)
    account_type = serializers.ChoiceField(
        choices=CustomerAccount.AccountType.choices,
        default=CustomerAccount.AccountType.BUSINESS,
    )
    country = serializers.CharField(max_length=2, required=False, allow_blank=True)
    timezone = serializers.CharField(max_length=64, default="UTC")

    def validate(self, attrs):
        for field in ("primary_contact_email",):
            if attrs.get(field):
                attrs[field] = attrs[field].strip().lower()
        if attrs.get("country"):
            attrs["country"] = attrs["country"].strip().upper()
        return attrs


class PlatformOnboardingValidationSerializer(serializers.Serializer):
    owner = PlatformOwnerSerializer()
    customer = PlatformCustomerOnboardingSerializer()
    plan_code = serializers.SlugField(max_length=80)
    intent = serializers.ChoiceField(choices=("standard", "trial"), default="standard")
    onboarding = EntityOnboardingCreateSerializer()

    def validate_onboarding(self, value):
        if value.get("compliance_credentials"):
            raise serializers.ValidationError({
                "compliance_credentials": (
                    "Compliance credentials cannot be stored in an onboarding operation. "
                    "Configure them after provisioning."
                )
            })
        return value

    def validate_plan_code(self, value):
        if not SubscriptionPlan.objects.filter(code=value, is_active=True).exists():
            raise serializers.ValidationError("Select an active subscription plan.")
        return value


class PlatformOnboardingValidationService:
    @staticmethod
    def _finding(*, code, field, resource, resource_id, display, message, severity="blocking"):
        return {
            "code": code,
            "severity": severity,
            "field": field,
            "matched_resource": resource,
            "matched_id": resource_id,
            "matched_display": display,
            "message": message,
        }

    @classmethod
    def duplicate_findings(cls, data):
        owner = data["owner"]
        customer = data["customer"]
        entity = data["onboarding"]["entity"]
        findings = []

        owner_match = User.objects.filter(email__iexact=owner["email"]).first()
        if owner_match:
            findings.append(cls._finding(
                code="owner_email_exists",
                field="owner.email",
                resource="user",
                resource_id=owner_match.pk,
                display=mask_email(owner_match.email),
                message="An account already uses this owner email. Select the existing owner or use another email.",
            ))

        contact_email = customer.get("primary_contact_email")
        if contact_email:
            account = CustomerAccount.objects.filter(
                Q(primary_contact_email__iexact=contact_email) | Q(billing_email__iexact=contact_email)
            ).first()
            if account:
                findings.append(cls._finding(
                    code="customer_contact_email_exists",
                    field="customer.primary_contact_email",
                    resource="customer_account",
                    resource_id=account.pk,
                    display=mask_email(contact_email),
                    message="This contact email is already associated with a customer account.",
                    severity="warning",
                ))

        phone = (customer.get("primary_contact_phone") or "").strip()
        if phone:
            account = CustomerAccount.objects.filter(
                Q(primary_contact_phone__iexact=phone) | Q(billing_contact_phone__iexact=phone)
            ).first()
            if account:
                findings.append(cls._finding(
                    code="customer_phone_exists",
                    field="customer.primary_contact_phone",
                    resource="customer_account",
                    resource_id=account.pk,
                    display=mask_phone(phone),
                    message="This phone number is already associated with a customer account.",
                    severity="warning",
                ))

        external_id = (customer.get("external_customer_id") or "").strip()
        if external_id:
            account = CustomerAccount.objects.filter(external_customer_id__iexact=external_id).first()
            if account:
                findings.append(cls._finding(
                    code="external_customer_id_exists",
                    field="customer.external_customer_id",
                    resource="customer_account",
                    resource_id=account.pk,
                    display="Already assigned",
                    message="This external customer ID must be unique.",
                ))

        legal_name = customer["legal_name"].strip()
        account = CustomerAccount.objects.filter(legal_name__iexact=legal_name).first()
        if account:
            findings.append(cls._finding(
                code="customer_legal_name_exists",
                field="customer.legal_name",
                resource="customer_account",
                resource_id=account.pk,
                display=account.name,
                message="A customer account with this legal name already exists.",
            ))

        entity_code = (entity.get("entity_code") or "").strip()
        if entity_code:
            match = Entity.objects.filter(entity_code__iexact=entity_code).first()
            if match:
                findings.append(cls._finding(
                    code="entity_code_exists",
                    field="onboarding.entity.entity_code",
                    resource="entity",
                    resource_id=match.pk,
                    display=match.entityname,
                    message="This entity code is already in use.",
                ))

        entity_name = (entity.get("legalname") or entity["entityname"]).strip()
        match = Entity.objects.filter(Q(legalname__iexact=entity_name) | Q(entityname__iexact=entity_name)).first()
        if match:
            findings.append(cls._finding(
                code="entity_legal_name_exists",
                field="onboarding.entity.legalname",
                resource="entity",
                resource_id=match.pk,
                display=match.entityname,
                message="An entity with this legal name already exists.",
                severity="warning",
            ))

        gstin = (entity.get("gstno") or "").strip().upper()
        if gstin:
            match = EntityGstRegistration.objects.filter(gstin__iexact=gstin, isactive=True).first()
            if match:
                findings.append(cls._finding(
                    code="gstin_exists",
                    field="onboarding.entity.gstno",
                    resource="entity",
                    resource_id=match.entity_id,
                    display=mask_gstin(gstin),
                    message="An active entity GST registration already uses this GSTIN.",
                ))
        return findings

    @classmethod
    def build_result(cls, validated_data):
        findings = cls.duplicate_findings(validated_data)
        blocking = [row for row in findings if row["severity"] == "blocking"]
        warnings = [row for row in findings if row["severity"] == "warning"]
        onboarding = validated_data["onboarding"]
        entity = onboarding["entity"]
        return {
            "valid": not blocking,
            "blocking_errors": blocking,
            "warnings": warnings,
            "preview": {
                "owner": {
                    "email": mask_email(validated_data["owner"]["email"]),
                    "name": " ".join(filter(None, [
                        validated_data["owner"].get("first_name"),
                        validated_data["owner"].get("last_name"),
                    ])).strip(),
                },
                "customer": {
                    "name": validated_data["customer"]["name"],
                    "legal_name": validated_data["customer"]["legal_name"],
                    "account_type": validated_data["customer"]["account_type"],
                },
                "entity": {
                    "name": entity["entityname"],
                    "legal_name": entity.get("legalname"),
                    "entity_code": entity.get("entity_code"),
                    "gst_status": entity.get("gst_registration_status"),
                    "gstin": mask_gstin(entity.get("gstno")),
                },
                "plan_code": validated_data["plan_code"],
                "intent": validated_data["intent"],
                "counts": {
                    "financial_years": len(onboarding.get("financial_years", [])),
                    "branches": len(onboarding.get("subentities", [])) or 1,
                    "bank_accounts": len(onboarding.get("bank_accounts", [])),
                },
                "provisioning_stages": [
                    "owner", "customer_account", "subscription", "entity",
                    "financial_years", "branches", "defaults", "membership", "verification",
                ],
            },
        }
