from rest_framework import serializers

from Authentication.models import User
from entity.models import BankAccount, Constitution, Entity, EntityConstitution, EntityFinancialYear, GstRegistrationType, SubEntity, UnitType


class OnboardingEntityPayloadSerializer(serializers.Serializer):
    entityname = serializers.CharField(max_length=100)
    legalname = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    unitType = serializers.PrimaryKeyRelatedField(queryset=UnitType.objects.all(), required=False, allow_null=True)
    GstRegitrationType = serializers.PrimaryKeyRelatedField(queryset=GstRegistrationType.objects.all(), required=False, allow_null=True)
    website = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    address = serializers.CharField(max_length=100)
    address2 = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    addressfloorno = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)
    addressstreet = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    ownername = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    country = serializers.PrimaryKeyRelatedField(queryset=Entity._meta.get_field("country").remote_field.model.objects.all(), allow_null=True)
    state = serializers.PrimaryKeyRelatedField(queryset=Entity._meta.get_field("state").remote_field.model.objects.all(), allow_null=True)
    district = serializers.PrimaryKeyRelatedField(queryset=Entity._meta.get_field("district").remote_field.model.objects.all(), allow_null=True)
    city = serializers.PrimaryKeyRelatedField(queryset=Entity._meta.get_field("city").remote_field.model.objects.all(), allow_null=True)
    pincode = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)
    phoneoffice = serializers.CharField(max_length=20)
    phoneresidence = serializers.CharField(max_length=20)
    panno = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    tds = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    tdscircle = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    tcs206c1honsale = serializers.BooleanField(required=False, allow_null=True)
    gstno = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    gstintype = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    blockstatus = serializers.CharField(max_length=10, required=False, allow_blank=True, allow_null=True)
    dateofreg = serializers.DateTimeField(required=False, allow_null=True)
    dateofdreg = serializers.DateTimeField(required=False, allow_null=True)
    const = serializers.PrimaryKeyRelatedField(queryset=Constitution.objects.all(), required=False, allow_null=True)


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
    class Meta:
        model = EntityFinancialYear
        fields = ("desc", "finstartyear", "finendyear", "isactive")


class OnboardingBankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = ("bank_name", "branch", "account_number", "ifsc_code", "account_type", "is_primary")


class OnboardingSubEntitySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubEntity
        fields = (
            "subentityname",
            "address",
            "country",
            "state",
            "district",
            "city",
            "pincode",
            "phoneoffice",
            "phoneresidence",
            "email",
            "ismainentity",
        )


class OnboardingConstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntityConstitution
        fields = ("shareholder", "pan", "sharepercentage")


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
