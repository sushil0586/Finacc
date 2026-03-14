from rest_framework import serializers

from Authentication.models import User
from entity.models import BankAccount, Constitution, Entity, EntityConstitution, EntityFinancialYear, GstRegistrationType, SubEntity, UnitType
from geography.models import City, Country, District, State


class OnboardingEntityPayloadSerializer(serializers.Serializer):
    entityname = serializers.CharField(max_length=100)
    legalname = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    entity_code = serializers.CharField(max_length=30, required=False, allow_blank=True, allow_null=True)
    trade_name = serializers.CharField(max_length=150, required=False, allow_blank=True, allow_null=True)
    short_name = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)
    organization_status = serializers.ChoiceField(choices=Entity.OrganizationStatus.choices, required=False, allow_blank=True, allow_null=True)
    business_type = serializers.ChoiceField(choices=Entity.BusinessType.choices, required=False, allow_blank=True, allow_null=True)
    unitType = serializers.PrimaryKeyRelatedField(queryset=UnitType.objects.all(), required=False, allow_null=True)
    GstRegitrationType = serializers.PrimaryKeyRelatedField(queryset=GstRegistrationType.objects.all(), required=False, allow_null=True)
    gst_registration_status = serializers.ChoiceField(choices=Entity.GstStatus.choices, required=False, allow_blank=True, allow_null=True)
    website = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    address = serializers.CharField(max_length=100)
    address2 = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    addressfloorno = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)
    addressstreet = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    registered_address_same_as_principal = serializers.BooleanField(required=False)
    ownername = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    contact_person_name = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    contact_person_designation = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    country = serializers.PrimaryKeyRelatedField(queryset=Entity._meta.get_field("country").remote_field.model.objects.all(), allow_null=True)
    state = serializers.PrimaryKeyRelatedField(queryset=Entity._meta.get_field("state").remote_field.model.objects.all(), allow_null=True)
    district = serializers.PrimaryKeyRelatedField(queryset=Entity._meta.get_field("district").remote_field.model.objects.all(), allow_null=True)
    city = serializers.PrimaryKeyRelatedField(queryset=Entity._meta.get_field("city").remote_field.model.objects.all(), allow_null=True)
    pincode = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)
    phoneoffice = serializers.CharField(max_length=20)
    phoneresidence = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    mobile_primary = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    mobile_secondary = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    panno = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    tds = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    tdscircle = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    email_primary = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    email_secondary = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    support_email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    accounts_email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    tan_no = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    cin_no = serializers.CharField(max_length=21, required=False, allow_blank=True, allow_null=True)
    llpin_no = serializers.CharField(max_length=8, required=False, allow_blank=True, allow_null=True)
    udyam_no = serializers.CharField(max_length=30, required=False, allow_blank=True, allow_null=True)
    iec_code = serializers.CharField(max_length=10, required=False, allow_blank=True, allow_null=True)
    tcs206c1honsale = serializers.BooleanField(required=False, allow_null=True)
    is_tds_applicable = serializers.BooleanField(required=False)
    is_tcs_applicable = serializers.BooleanField(required=False)
    is_einvoice_applicable = serializers.BooleanField(required=False)
    is_ewaybill_applicable = serializers.BooleanField(required=False)
    is_msme_registered = serializers.BooleanField(required=False)
    msme_category = serializers.ChoiceField(choices=Entity.MsmeCategory.choices, required=False, allow_null=True)
    gstno = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    gstintype = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    gst_effective_from = serializers.DateField(required=False, allow_null=True)
    gst_cancelled_from = serializers.DateField(required=False, allow_null=True)
    gst_username = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    nature_of_business = serializers.CharField(max_length=150, required=False, allow_blank=True, allow_null=True)
    incorporation_date = serializers.DateField(required=False, allow_null=True)
    business_commencement_date = serializers.DateField(required=False, allow_null=True)
    blockstatus = serializers.CharField(max_length=10, required=False, allow_blank=True, allow_null=True)
    dateofreg = serializers.DateTimeField(required=False, allow_null=True)
    dateofdreg = serializers.DateTimeField(required=False, allow_null=True)
    const = serializers.PrimaryKeyRelatedField(queryset=Constitution.objects.all(), required=False, allow_null=True)
    parent_entity = serializers.PrimaryKeyRelatedField(queryset=Entity.objects.all(), required=False, allow_null=True)
    metadata = serializers.JSONField(required=False)

    @staticmethod
    def _upper(value):
        return str(value).strip().upper() if value not in (None, "") else None

    def to_internal_value(self, data):
        mutable = dict(data)
        for key in [
            "gstno",
            "panno",
            "tds",
            "tan_no",
            "cin_no",
            "llpin_no",
            "udyam_no",
            "iec_code",
            "entity_code",
        ]:
            if key in mutable:
                mutable[key] = self._upper(mutable.get(key))

        for key in [
            "email",
            "email_primary",
            "email_secondary",
            "support_email",
            "accounts_email",
            "website",
        ]:
            if mutable.get(key) not in (None, ""):
                mutable[key] = str(mutable[key]).strip()

        if mutable.get("gstno") and not mutable.get("panno") and len(mutable["gstno"]) >= 12:
            mutable["panno"] = mutable["gstno"][2:12]

        if mutable.get("gstno") and not mutable.get("gst_registration_status"):
            mutable["gst_registration_status"] = Entity.GstStatus.REGISTERED

        if mutable.get("phoneoffice") and not mutable.get("phoneresidence"):
            mutable["phoneresidence"] = mutable.get("phoneoffice")

        if not mutable.get("organization_status"):
            mutable["organization_status"] = Entity.OrganizationStatus.ACTIVE
        if not mutable.get("business_type"):
            mutable["business_type"] = Entity.BusinessType.TRADER

        return super().to_internal_value(mutable)


class OnboardingEntityDetailPayloadSerializer(serializers.Serializer):
    style = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    commodity = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    weightDecimal = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True, max_length=24)
    registrationno = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    division = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    collectorate = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    range = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    adhaarudyog = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    cinno = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    jobwork = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    gstno = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    gstintype = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    esino = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class OnboardingFinancialYearSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = EntityFinancialYear
        fields = (
            "id",
            "desc",
            "year_code",
            "assessment_year_label",
            "finstartyear",
            "finendyear",
            "period_status",
            "books_locked_until",
            "gst_locked_until",
            "inventory_locked_until",
            "ap_ar_locked_until",
            "is_year_closed",
            "is_audit_closed",
            "isactive",
            "metadata",
        )

    def to_internal_value(self, data):
        mutable = dict(data)
        if mutable.get("period_status") not in (None, ""):
            mutable["period_status"] = str(mutable["period_status"]).strip().lower()
        return super().to_internal_value(mutable)


class OnboardingBankAccountSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = BankAccount
        fields = ("id", "bank_name", "branch", "account_number", "ifsc_code", "account_type", "is_primary")


class OnboardingSubEntitySerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = SubEntity
        fields = (
            "id",
            "subentityname",
            "subentity_code",
            "branch_type",
            "address",
            "address2",
            "addressfloorno",
            "addressstreet",
            "country",
            "state",
            "district",
            "city",
            "pincode",
            "phoneoffice",
            "phoneresidence",
            "email",
            "email_primary",
            "mobile_primary",
            "mobile_secondary",
            "contact_person_name",
            "contact_person_designation",
            "gstno",
            "GstRegitrationType",
            "ismainentity",
            "is_head_office",
            "can_sell",
            "can_purchase",
            "can_stock",
            "can_bank",
            "sort_order",
            "metadata",
        )

    def to_internal_value(self, data):
        mutable = dict(data)
        if mutable.get("gstno") not in (None, ""):
            mutable["gstno"] = str(mutable["gstno"]).strip().upper()
        if mutable.get("phoneoffice") and not mutable.get("phoneresidence"):
            mutable["phoneresidence"] = mutable.get("phoneoffice")
        if mutable.get("email") and not mutable.get("email_primary"):
            mutable["email_primary"] = mutable.get("email")
        return super().to_internal_value(mutable)


class OnboardingConstitutionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = EntityConstitution
        fields = ("id", "shareholder", "pan", "sharepercentage")

    def to_internal_value(self, data):
        mutable = dict(data)
        if mutable.get("pan") not in (None, ""):
            mutable["pan"] = str(mutable["pan"]).strip().upper()
        return super().to_internal_value(mutable)


class OnboardingSeedOptionsSerializer(serializers.Serializer):
    template_code = serializers.CharField(required=False, default="standard_trading")
    seed_financial = serializers.BooleanField(required=False, default=True)
    seed_rbac = serializers.BooleanField(required=False, default=True)
    seed_default_subentity = serializers.BooleanField(required=False, default=True)
    seed_default_roles = serializers.BooleanField(required=False, default=True)


class EntityOnboardingCreateSerializer(serializers.Serializer):
    entity = OnboardingEntityPayloadSerializer()
    entity_detail = OnboardingEntityDetailPayloadSerializer(required=False)
    financial_years = OnboardingFinancialYearSerializer(many=True)
    bank_accounts = OnboardingBankAccountSerializer(many=True, required=False)
    subentities = OnboardingSubEntitySerializer(many=True, required=False)
    constitution_details = OnboardingConstitutionSerializer(many=True, required=False)
    seed_options = OnboardingSeedOptionsSerializer(required=False)

    def validate_financial_years(self, value):
        if not value:
            raise serializers.ValidationError("At least one financial year is required.")
        active_count = sum(1 for row in value if row.get("isactive"))
        if active_count > 1:
            raise serializers.ValidationError("Only one financial year can be active.")
        return value


class EntityOnboardingUpdateSerializer(serializers.Serializer):
    entity = OnboardingEntityPayloadSerializer(required=False)
    entity_detail = OnboardingEntityDetailPayloadSerializer(required=False)
    financial_years = OnboardingFinancialYearSerializer(many=True, required=False)
    bank_accounts = OnboardingBankAccountSerializer(many=True, required=False)
    subentities = OnboardingSubEntitySerializer(many=True, required=False)
    constitution_details = OnboardingConstitutionSerializer(many=True, required=False)

    def validate_financial_years(self, value):
        if value == []:
            raise serializers.ValidationError("At least one financial year is required.")
        active_count = sum(1 for row in value if row.get("isactive"))
        if active_count > 1:
            raise serializers.ValidationError("Only one financial year can be active.")
        return value


class EntityOnboardingDetailResponseSerializer(serializers.Serializer):
    entity_id = serializers.IntegerField()
    entity = OnboardingEntityPayloadSerializer()
    entity_detail = OnboardingEntityDetailPayloadSerializer(required=False)
    financial_years = OnboardingFinancialYearSerializer(many=True)
    bank_accounts = OnboardingBankAccountSerializer(many=True)
    subentities = OnboardingSubEntitySerializer(many=True)
    constitution_details = OnboardingConstitutionSerializer(many=True)


class OnboardingUserPayloadSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    email = serializers.EmailField()
    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    password = serializers.CharField(min_length=6, max_length=128, write_only=True)

    def validate_email(self, value):
        normalized = value.strip().lower()
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return normalized


class RegisterAndOnboardSerializer(serializers.Serializer):
    user = OnboardingUserPayloadSerializer()
    onboarding = EntityOnboardingCreateSerializer()

    @staticmethod
    def _blank_to_none(value):
        if isinstance(value, dict):
            return {key: RegisterAndOnboardSerializer._blank_to_none(val) for key, val in value.items()}
        if isinstance(value, list):
            return [RegisterAndOnboardSerializer._blank_to_none(item) for item in value]
        if value == "":
            return None
        return value

    def to_internal_value(self, data):
        mutable = self._blank_to_none(dict(data))
        if "onboarding" not in mutable and "entity" in mutable:
            entity_payload = dict(mutable.get("entity") or {})
            onboarding_payload = {
                "entity": {},
                "entity_detail": mutable.get("entity_detail"),
                "financial_years": entity_payload.pop("financial_years", mutable.get("financial_years")),
                "bank_accounts": entity_payload.pop("bank_accounts", mutable.get("bank_accounts")),
                "subentities": entity_payload.pop("subentities", mutable.get("subentities")),
                "constitution_details": entity_payload.pop("constitution_details", mutable.get("constitution_details")),
                "seed_options": mutable.get("seed_options"),
            }
            onboarding_payload["entity"] = entity_payload
            mutable["onboarding"] = onboarding_payload
        return super().to_internal_value(mutable)


class EntityOnboardingResponseSerializer(serializers.Serializer):
    entity_id = serializers.IntegerField()
    entity_name = serializers.CharField()
    gstno = serializers.CharField(allow_blank=True, allow_null=True)
    financial_year_ids = serializers.ListField(child=serializers.IntegerField())
    bank_account_ids = serializers.ListField(child=serializers.IntegerField())
    subentity_ids = serializers.ListField(child=serializers.IntegerField())
    constitution_ids = serializers.ListField(child=serializers.IntegerField())
    financial = serializers.DictField()
    rbac = serializers.DictField()


class RegisterAndOnboardResponseSerializer(serializers.Serializer):
    user = serializers.DictField()
    onboarding = EntityOnboardingResponseSerializer()
    verification = serializers.DictField()


class OnboardingSimpleOptionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    label = serializers.CharField()
    code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class OnboardingMetaResponseSerializer(serializers.Serializer):
    defaults = serializers.DictField()
    dropdowns = serializers.DictField()
    geography_filters = serializers.DictField()
    endpoints = serializers.DictField()
    field_choices = serializers.DictField(required=False)


class CountryOptionSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="countryname")
    code = serializers.CharField(source="countrycode")

    class Meta:
        model = Country
        fields = ("id", "label", "code")


class StateOptionSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="statename")
    code = serializers.CharField(source="statecode")
    country_id = serializers.IntegerField()

    class Meta:
        model = State
        fields = ("id", "label", "code", "country_id")


class DistrictOptionSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="districtname")
    code = serializers.CharField(source="districtcode")
    state_id = serializers.IntegerField()

    class Meta:
        model = District
        fields = ("id", "label", "code", "state_id")


class CityOptionSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="cityname")
    code = serializers.CharField(source="citycode")
    district_id = serializers.IntegerField(source="distt_id")

    class Meta:
        model = City
        fields = ("id", "label", "code", "pincode", "district_id")
