from django.core.validators import MinLengthValidator, RegexValidator
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import models
from django.db.models import Q
from helpers.models import TrackingModel
from Authentication.models import User
from geography.models import Country,State,District,City
from geography.validators import validate_geography_hierarchy
from django.utils.dateformat import DateFormat
#from Authentication.models import User 

# Create your models here.

_RELAXED_GSTIN = bool(getattr(settings, "ALLOW_RELAXED_GSTIN_FOR_SANDBOX", False))
gstin_validator = RegexValidator(
    regex=(
        r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]{3}$"
        if _RELAXED_GSTIN
        else r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
    ),
    message="Enter a valid GSTIN.",
)
pan_validator = RegexValidator(
    regex=r"^[A-Z]{5}[0-9]{4}[A-Z]$",
    message="Enter a valid PAN.",
)
tan_validator = RegexValidator(
    regex=r"^[A-Z]{4}[0-9]{5}[A-Z]$",
    message="Enter a valid TAN.",
)
cin_validator = RegexValidator(
    regex=r"^[A-Z0-9]{21}$",
    message="Enter a valid CIN.",
)
llpin_validator = RegexValidator(
    regex=r"^[A-Z]{3}-[0-9]{4}$",
    message="Enter a valid LLPIN.",
)
iec_validator = RegexValidator(
    regex=r"^[0-9A-Z]{10}$",
    message="Enter a valid IEC code.",
)
phone_validator = RegexValidator(
    regex=r"^[0-9+() -]{8,20}$",
    message="Enter a valid phone number.",
)
pincode_validator = RegexValidator(
    regex=r"^[0-9]{6}$",
    message="Enter a valid 6 digit pincode.",
)

class UnitType(models.Model):
    UnitName =    models.CharField(max_length= 100)
    UnitDesc =    models.CharField(max_length= 255)
    #createdby = models.ForeignKey(to= 'Authentication.User', on_delete= models.CASCADE,null=True,default=1,blank=True)


    def __str__(self):
        return f'{self.UnitName}'
    

class GstRegistrationType(models.Model):
    Name =           models.CharField(max_length= 100)
    Description =    models.CharField(max_length= 255)
    #createdby = models.ForeignKey(to= 'Authentication.User', on_delete= models.CASCADE,null=True,default=1,blank=True)


    def __str__(self):
        return f'{self.Name}'
    
class Constitution(models.Model):
    constitutionname =    models.CharField(max_length= 255)
    constitutiondesc =    models.TextField()
    constcode =    models.CharField(max_length= 255)
    createdby = models.ForeignKey(to= 'Authentication.User', on_delete= models.CASCADE,null=True,default=1,blank=True)


    def __str__(self):
        return f'{self.constitutionname}'
    

class BankDetail(TrackingModel):
    bankname =  models.CharField(max_length= 100)
    bankcode =  models.CharField(max_length= 100,null=True)
    ifsccode =  models.CharField(max_length= 100,null=True)

    def __str__(self):
        return f'{self.bankname}'





        


class Entity(TrackingModel):
    class OrganizationStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        SUSPENDED = "suspended", "Suspended"
        CLOSED = "closed", "Closed"

    class BusinessType(models.TextChoices):
        TRADER = "trader", "Trader"
        MANUFACTURER = "manufacturer", "Manufacturer"
        SERVICE = "service", "Service Provider"
        MIXED = "mixed", "Trading + Services"
        NGO = "ngo", "NGO / Trust"
        EDUCATIONAL = "educational", "Educational Institution"
        HEALTHCARE = "healthcare", "Healthcare"
        GOVERNMENT = "government", "Government / PSU"
        OTHER = "other", "Other"

    class GstStatus(models.TextChoices):
        REGISTERED = "registered", "Registered"
        UNREGISTERED = "unregistered", "Unregistered"
        COMPOSITION = "composition", "Composition"
        SEZ = "sez", "SEZ"
        TDS = "tds", "TDS Deductor"
        TCS = "tcs", "TCS Collector"
        UIN = "uin", "UIN Holder"
        NON_RESIDENT = "non_resident", "Non Resident"

    class MsmeCategory(models.TextChoices):
        MICRO = "micro", "Micro"
        SMALL = "small", "Small"
        MEDIUM = "medium", "Medium"

    entityname =  models.CharField(max_length= 100)
    entitydesc =  models.CharField(max_length= 255,null=True)
    legalname =  models.CharField(max_length= 100,null=True)
    entity_code = models.CharField(max_length=30, null=True, blank=True, db_index=True)
    trade_name = models.CharField(max_length=150, null=True, blank=True)
    short_name = models.CharField(max_length=50, null=True, blank=True)
    organization_status = models.CharField(
        max_length=20,
        choices=OrganizationStatus.choices,
        default=OrganizationStatus.ACTIVE,
    )
    business_type = models.CharField(
        max_length=20,
        choices=BusinessType.choices,
        default=BusinessType.MIXED,
    )
    GstRegitrationType =        models.ForeignKey(GstRegistrationType, on_delete=models.CASCADE,null= True)
    gst_registration_status = models.CharField(
        max_length=20,
        choices=GstStatus.choices,
        default=GstStatus.REGISTERED,
    )
    website = models.URLField(blank=True, null=True)
    parent_entity = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="child_entities")
    customer_account = models.ForeignKey(
        "subscriptions.CustomerAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entities",
    )
    metadata = models.JSONField(default=dict, blank=True)
    createdby =  models.ForeignKey(User, on_delete=models.CASCADE,null= True)
    #createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True,default=1,blank=True)
    

    
    def __str__(self):
        return f'{self.entityname}'

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity_code"],
                condition=Q(entity_code__isnull=False),
                name="uq_entity_code_when_present",
            ),
        ]
        indexes = [
            models.Index(fields=["entityname"]),
            models.Index(fields=["legalname"]),
            models.Index(fields=["organization_status"]),
        ]

    def save(self, *args, **kwargs):
        self.entity_code = (self.entity_code or "").strip().upper() or None
        self.trade_name = (self.trade_name or "").strip() or None
        self.short_name = (self.short_name or "").strip() or None
        super().save(*args, **kwargs)


class EntityPolicy(TrackingModel):
    class ValidationMode(models.TextChoices):
        HARD = "hard", "Hard"
        SOFT = "soft", "Soft"
        OFF = "off", "Off"

    entity = models.OneToOneField("Entity", on_delete=models.CASCADE, related_name="policy")
    gstin_state_match_mode = models.CharField(
        max_length=10,
        choices=ValidationMode.choices,
        default=ValidationMode.HARD,
    )
    require_subentity_mode = models.CharField(
        max_length=10,
        choices=ValidationMode.choices,
        default=ValidationMode.HARD,
    )
    require_head_office_subentity_mode = models.CharField(
        max_length=10,
        choices=ValidationMode.choices,
        default=ValidationMode.HARD,
    )
    require_entity_primary_gstin_mode = models.CharField(
        max_length=10,
        choices=ValidationMode.choices,
        default=ValidationMode.HARD,
    )
    subentity_gstin_state_match_mode = models.CharField(
        max_length=10,
        choices=ValidationMode.choices,
        default=ValidationMode.HARD,
    )
    metadata = models.JSONField(default=dict, blank=True)
    createdby = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    def __str__(self):
        return f"Policy - {self.entity}"
class EntityAddress(TrackingModel):
    class AddressType(models.TextChoices):
        REGISTERED = "registered", "Registered"
        PRINCIPAL = "principal", "Principal Place"
        CORRESPONDENCE = "correspondence", "Correspondence"

    entity = models.ForeignKey("Entity", on_delete=models.CASCADE, related_name="addresses")
    address_type = models.CharField(max_length=20, choices=AddressType.choices, default=AddressType.REGISTERED)
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, null=True, blank=True)
    floor_no = models.CharField(max_length=50, null=True, blank=True)
    street = models.CharField(max_length=100, null=True, blank=True)
    country = models.ForeignKey(Country, on_delete=models.PROTECT, null=True, blank=True)
    state = models.ForeignKey(State, on_delete=models.PROTECT, null=True, blank=True)
    district = models.ForeignKey(District, on_delete=models.PROTECT, null=True, blank=True)
    city = models.ForeignKey(City, on_delete=models.PROTECT, null=True, blank=True)
    pincode = models.CharField(max_length=10, null=True, blank=True, validators=[pincode_validator])
    is_primary = models.BooleanField(default=False)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    createdby = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "address_type"],
                condition=Q(isactive=True, is_primary=True),
                name="uq_entity_address_primary_type",
            ),
        ]
        indexes = [models.Index(fields=["entity", "address_type", "isactive"])]

    def clean(self):
        validate_geography_hierarchy(
            country=self.country,
            state=self.state,
            district=self.district,
            city=self.city,
        )

    def save(self, *args, **kwargs):
        self.line1 = (self.line1 or "").strip()
        self.line2 = (self.line2 or "").strip() or None
        self.floor_no = (self.floor_no or "").strip() or None
        self.street = (self.street or "").strip() or None
        self.pincode = (self.pincode or "").strip() or None
        self.full_clean()
        super().save(*args, **kwargs)


class EntityContact(TrackingModel):
    class ContactType(models.TextChoices):
        OWNER = "owner", "Owner"
        ACCOUNTS = "accounts", "Accounts"
        SUPPORT = "support", "Support"
        COMPLIANCE = "compliance", "Compliance"
        OTHER = "other", "Other"

    entity = models.ForeignKey("Entity", on_delete=models.CASCADE, related_name="contacts")
    contact_type = models.CharField(max_length=20, choices=ContactType.choices, default=ContactType.OTHER)
    name = models.CharField(max_length=100)
    designation = models.CharField(max_length=100, null=True, blank=True)
    mobile = models.CharField(max_length=20, null=True, blank=True, validators=[phone_validator])
    email = models.EmailField(max_length=100, null=True, blank=True)
    is_primary = models.BooleanField(default=False)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    createdby = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        indexes = [
            models.Index(fields=["entity", "contact_type", "isactive"]),
            models.Index(fields=["entity", "email"]),
        ]

    def save(self, *args, **kwargs):
        self.name = (self.name or "").strip()
        self.designation = (self.designation or "").strip() or None
        self.mobile = (self.mobile or "").strip() or None
        self.email = (self.email or "").strip().lower() or None
        super().save(*args, **kwargs)


class EntityTaxProfile(TrackingModel):
    entity = models.OneToOneField("Entity", on_delete=models.CASCADE, related_name="tax_profile")
    pan = models.CharField(max_length=10, null=True, blank=True, validators=[pan_validator], db_index=True)
    tan = models.CharField(max_length=10, null=True, blank=True, validators=[tan_validator], db_index=True)
    cin_no = models.CharField(max_length=21, null=True, blank=True, validators=[cin_validator])
    llpin_no = models.CharField(max_length=8, null=True, blank=True, validators=[llpin_validator])
    iec_code = models.CharField(max_length=10, null=True, blank=True, validators=[iec_validator])
    udyam_no = models.CharField(max_length=30, null=True, blank=True)
    incorporation_date = models.DateField(null=True, blank=True)
    business_commencement_date = models.DateField(null=True, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    createdby = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    def save(self, *args, **kwargs):
        self.pan = (self.pan or "").strip().upper() or None
        self.tan = (self.tan or "").strip().upper() or None
        self.cin_no = (self.cin_no or "").strip().upper() or None
        self.llpin_no = (self.llpin_no or "").strip().upper() or None
        self.iec_code = (self.iec_code or "").strip().upper() or None
        self.udyam_no = (self.udyam_no or "").strip().upper() or None
        super().save(*args, **kwargs)


class EntityGstRegistration(TrackingModel):
    entity = models.ForeignKey("Entity", on_delete=models.CASCADE, related_name="gst_registrations")
    gstin = models.CharField(max_length=15, validators=[gstin_validator], db_index=True)
    registration_type = models.ForeignKey(GstRegistrationType, on_delete=models.SET_NULL, null=True, blank=True)
    gst_status = models.CharField(max_length=20, choices=Entity.GstStatus.choices, default=Entity.GstStatus.REGISTERED)
    state = models.ForeignKey(State, on_delete=models.PROTECT, null=True, blank=True)
    nature_of_business = models.CharField(max_length=150, null=True, blank=True)
    gst_effective_from = models.DateField(null=True, blank=True)
    gst_cancelled_from = models.DateField(null=True, blank=True)
    credential_ref = models.CharField(max_length=255, null=True, blank=True)
    is_primary = models.BooleanField(default=False)
    createdby = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["gstin"], condition=Q(isactive=True), name="uq_entity_gst_registration_active_gstin"),
            models.UniqueConstraint(fields=["entity"], condition=Q(isactive=True, is_primary=True), name="uq_entity_gst_registration_primary"),
            models.UniqueConstraint(
                fields=["entity", "state"],
                condition=Q(isactive=True, state__isnull=False),
                name="uq_entity_gst_registration_entity_state_active",
            ),
        ]
        indexes = [models.Index(fields=["entity", "is_primary", "isactive"])]

    def clean(self):
        gstin = (self.gstin or "").strip().upper()

        # Prevent multiple active GST rows for same entity+state.
        if self.isactive and self.entity_id and self.state_id:
            exists_same_state = EntityGstRegistration.objects.filter(
                entity_id=self.entity_id,
                state_id=self.state_id,
                isactive=True,
            ).exclude(pk=self.pk).exists()
            if exists_same_state:
                raise ValidationError({"state": "Only one active GST registration is allowed per entity per state."})

    def save(self, *args, **kwargs):
        self.gstin = (self.gstin or "").strip().upper()
        self.credential_ref = (self.credential_ref or "").strip() or None
        self.full_clean()
        super().save(*args, **kwargs)


class EntityBankAccountV2(TrackingModel):
    entity = models.ForeignKey("Entity", on_delete=models.CASCADE, related_name="bank_accounts_v2")
    bank_name = models.CharField(max_length=100)
    branch = models.CharField(max_length=100, null=True, blank=True)
    account_number = models.CharField(max_length=32)
    ifsc_code = models.CharField(max_length=11)
    account_type = models.CharField(max_length=20, choices=[("current", "Current"), ("savings", "Savings")], default="current")
    is_primary = models.BooleanField(default=False)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    createdby = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entity"], condition=Q(isactive=True, is_primary=True), name="uq_entity_bank_account_v2_primary"),
        ]
        indexes = [models.Index(fields=["entity", "ifsc_code", "isactive"])]

    def save(self, *args, **kwargs):
        self.bank_name = (self.bank_name or "").strip()
        self.branch = (self.branch or "").strip() or None
        self.account_number = (self.account_number or "").strip()
        self.ifsc_code = (self.ifsc_code or "").strip().upper()
        super().save(*args, **kwargs)


class EntityComplianceProfile(TrackingModel):
    entity = models.OneToOneField("Entity", on_delete=models.CASCADE, related_name="compliance_profile")
    is_tds_applicable = models.BooleanField(default=False)
    is_tcs_applicable = models.BooleanField(default=False)
    is_einvoice_applicable = models.BooleanField(default=False)
    is_ewaybill_applicable = models.BooleanField(default=False)
    is_msme_registered = models.BooleanField(default=False)
    msme_category = models.CharField(max_length=20, choices=Entity.MsmeCategory.choices, null=True, blank=True)
    createdby = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    def __str__(self):
        return f"Compliance Profile - {self.entity}"


class EntityOwnershipV2(TrackingModel):
    class AccountPreference(models.TextChoices):
        CAPITAL = "capital", "Capital"
        CURRENT = "current", "Current"
        AUTO = "auto", "Auto"

    class OwnershipType(models.TextChoices):
        PROPRIETOR = "proprietor", "Proprietor"
        PARTNER = "partner", "Partner"
        DIRECTOR = "director", "Director"
        SHAREHOLDER = "shareholder", "Shareholder"
        TRUSTEE = "trustee", "Trustee"
        OTHER = "other", "Other"

    entity = models.ForeignKey("Entity", on_delete=models.CASCADE, related_name="ownerships_v2")
    ownership_type = models.CharField(max_length=20, choices=OwnershipType.choices, default=OwnershipType.OTHER)
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    mobile = models.CharField(max_length=20, blank=True, null=True, validators=[phone_validator])
    pan_number = models.CharField(max_length=10, blank=True, null=True, validators=[pan_validator])
    share_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    capital_contribution = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    account_preference = models.CharField(max_length=20, choices=AccountPreference.choices, default=AccountPreference.AUTO)
    agreement_reference = models.CharField(max_length=255, null=True, blank=True)
    is_primary = models.BooleanField(default=False)
    designation = models.CharField(max_length=100, blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    createdby = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        indexes = [models.Index(fields=["entity", "ownership_type", "isactive"])]

    def save(self, *args, **kwargs):
        self.name = (self.name or "").strip()
        self.email = (self.email or "").strip().lower() or None
        self.mobile = (self.mobile or "").strip() or None
        self.pan_number = (self.pan_number or "").strip().upper() or None
        self.agreement_reference = (self.agreement_reference or "").strip() or None
        self.account_preference = (self.account_preference or "").strip().lower() or self.AccountPreference.AUTO
        self.designation = (self.designation or "").strip() or None
        super().save(*args, **kwargs)


class EntityConstitutionV2(TrackingModel):
    class AccountPreference(models.TextChoices):
        CAPITAL = "capital", "Capital"
        CURRENT = "current", "Current"
        AUTO = "auto", "Auto"

    entity = models.ForeignKey("Entity", on_delete=models.CASCADE, related_name="constitutions_v2")
    constitution_code = models.CharField(max_length=20)
    constitution_name = models.CharField(max_length=255)
    shareholder = models.CharField(max_length=255, null=True, blank=True)
    pan = models.CharField(max_length=10, null=True, blank=True, validators=[pan_validator])
    share_percentage = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    account_preference = models.CharField(max_length=20, choices=AccountPreference.choices, default=AccountPreference.CAPITAL)
    agreement_reference = models.CharField(max_length=255, null=True, blank=True)
    createdby = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        indexes = [models.Index(fields=["entity", "constitution_code", "isactive"])]

    def save(self, *args, **kwargs):
        self.constitution_code = (self.constitution_code or "").strip().upper()
        self.constitution_name = (self.constitution_name or "").strip()
        self.shareholder = (self.shareholder or "").strip() or None
        self.pan = (self.pan or "").strip().upper() or None
        self.agreement_reference = (self.agreement_reference or "").strip() or None
        self.account_preference = (self.account_preference or "").strip().lower() or self.AccountPreference.CAPITAL
        super().save(*args, **kwargs)


class SubEntity(TrackingModel):
    class BranchType(models.TextChoices):
        HEAD_OFFICE = "head_office", "Head Office"
        BRANCH = "branch", "Branch"
        WAREHOUSE = "warehouse", "Warehouse"
        FACTORY = "factory", "Factory"
        DEPOT = "depot", "Depot"
        SHOWROOM = "showroom", "Showroom"
        OFFICE = "office", "Office"

    subentityname =  models.CharField(max_length= 255)
    subentity_code = models.CharField(max_length=30, null=True, blank=True)
    branch_type = models.CharField(max_length=20, choices=BranchType.choices, default=BranchType.BRANCH)
    is_head_office = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=100)
    metadata = models.JSONField(default=dict, blank=True)
    entity =    models.ForeignKey(to= Entity, on_delete= models.CASCADE,null=True,related_name='subentity',)

    

    
    def __str__(self):
        return f'{self.subentityname}'

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "subentity_code"],
                condition=Q(subentity_code__isnull=False),
                name="uq_subentity_code_per_entity",
            ),
            models.UniqueConstraint(
                fields=["entity"],
                condition=Q(is_head_office=True, isactive=True),
                name="uq_subentity_single_head_office_per_entity",
            ),
        ]
        ordering = ["sort_order", "subentityname"]
        indexes = [
            models.Index(fields=["entity", "subentityname"]),
            models.Index(fields=["entity", "subentity_code"]),
        ]

    def clean(self):
        if self.branch_type == self.BranchType.HEAD_OFFICE:
            self.is_head_office = True
        if self.is_head_office and self.entity_id:
            exists_other_head_office = SubEntity.objects.filter(
                entity_id=self.entity_id,
                is_head_office=True,
                isactive=True,
            ).exclude(pk=self.pk).exists()
            if exists_other_head_office:
                raise ValidationError({"is_head_office": "Only one active head office is allowed per entity."})

    def save(self, *args, **kwargs):
        self.subentity_code = (self.subentity_code or "").strip().upper() or None
        self.is_head_office = bool(self.is_head_office)
        if self.branch_type == self.BranchType.HEAD_OFFICE:
            self.is_head_office = True
        if self.is_head_office:
            self.branch_type = self.BranchType.HEAD_OFFICE
        self.full_clean()
        super().save(*args, **kwargs)
    




class SubEntityAddress(TrackingModel):
    class AddressType(models.TextChoices):
        OPERATIONS = "operations", "Operations"
        REGISTERED = "registered", "Registered"
        BILLING = "billing", "Billing"

    subentity = models.ForeignKey("SubEntity", on_delete=models.CASCADE, related_name="addresses")
    address_type = models.CharField(max_length=20, choices=AddressType.choices, default=AddressType.OPERATIONS)
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, null=True, blank=True)
    floor_no = models.CharField(max_length=50, null=True, blank=True)
    street = models.CharField(max_length=100, null=True, blank=True)
    country = models.ForeignKey(Country, on_delete=models.PROTECT, null=True, blank=True)
    state = models.ForeignKey(State, on_delete=models.PROTECT, null=True, blank=True)
    district = models.ForeignKey(District, on_delete=models.PROTECT, null=True, blank=True)
    city = models.ForeignKey(City, on_delete=models.PROTECT, null=True, blank=True)
    pincode = models.CharField(max_length=10, null=True, blank=True, validators=[pincode_validator])
    is_primary = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["subentity", "address_type", "isactive"])]

    def clean(self):
        validate_geography_hierarchy(
            country=self.country,
            state=self.state,
            district=self.district,
            city=self.city,
        )

    def save(self, *args, **kwargs):
        self.line1 = (self.line1 or "").strip()
        self.line2 = (self.line2 or "").strip() or None
        self.floor_no = (self.floor_no or "").strip() or None
        self.street = (self.street or "").strip() or None
        self.pincode = (self.pincode or "").strip() or None
        self.full_clean()
        super().save(*args, **kwargs)


class SubEntityContact(TrackingModel):
    subentity = models.ForeignKey("SubEntity", on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=100)
    designation = models.CharField(max_length=100, null=True, blank=True)
    mobile = models.CharField(max_length=20, null=True, blank=True, validators=[phone_validator])
    email = models.EmailField(max_length=100, null=True, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["subentity", "is_primary", "isactive"])]


class SubEntityGstRegistration(TrackingModel):
    subentity = models.ForeignKey("SubEntity", on_delete=models.CASCADE, related_name="gst_registrations")
    gstin = models.CharField(max_length=15, validators=[gstin_validator], db_index=True)
    registration_type = models.ForeignKey(GstRegistrationType, on_delete=models.SET_NULL, null=True, blank=True)
    gst_status = models.CharField(max_length=20, choices=Entity.GstStatus.choices, default=Entity.GstStatus.REGISTERED)
    state = models.ForeignKey(State, on_delete=models.PROTECT, null=True, blank=True)
    nature_of_business = models.CharField(max_length=150, null=True, blank=True)
    gst_effective_from = models.DateField(null=True, blank=True)
    gst_cancelled_from = models.DateField(null=True, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["gstin"], condition=Q(isactive=True), name="uq_subentity_gst_registration_active_gstin"),
            models.UniqueConstraint(fields=["subentity"], condition=Q(isactive=True, is_primary=True), name="uq_subentity_gst_registration_primary"),
            models.UniqueConstraint(
                fields=["subentity", "state"],
                condition=Q(isactive=True, state__isnull=False),
                name="uq_subentity_gst_registration_subentity_state_active",
            ),
        ]
        indexes = [models.Index(fields=["subentity", "is_primary", "isactive"])]

    def clean(self):
        gstin = (self.gstin or "").strip().upper()

        if self.isactive and self.subentity_id and self.state_id:
            exists_same_state = SubEntityGstRegistration.objects.filter(
                subentity_id=self.subentity_id,
                state_id=self.state_id,
                isactive=True,
            ).exclude(pk=self.pk).exists()
            if exists_same_state:
                raise ValidationError({"state": "Only one active GST registration is allowed per subentity per state."})

    def save(self, *args, **kwargs):
        self.gstin = (self.gstin or "").strip().upper()
        self.nature_of_business = (self.nature_of_business or "").strip() or None
        self.full_clean()
        super().save(*args, **kwargs)


class SubEntityCapability(TrackingModel):
    subentity = models.OneToOneField("SubEntity", on_delete=models.CASCADE, related_name="capability")
    can_sell = models.BooleanField(default=True)
    can_purchase = models.BooleanField(default=True)
    can_stock = models.BooleanField(default=True)
    can_bank = models.BooleanField(default=True)

    def __str__(self):
        return f"Capability - {self.subentity}"


class UserEntityContext(TrackingModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="entity_contexts")
    entity = models.ForeignKey("Entity", on_delete=models.CASCADE, related_name="user_contexts")
    entityfinid = models.ForeignKey("EntityFinancialYear", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    subentity = models.ForeignKey("SubEntity", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    def __str__(self):
        return f"{self.user} @ {self.entity}"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "entity"], name="uq_user_entity_context"),
        ]
        indexes = [
            models.Index(fields=["user", "entity"]),
        ]


class EntityFinancialYear(TrackingModel):
    class PeriodStatus(models.TextChoices):
        OPEN = "open", "Open"
        SOFT_LOCKED = "soft_locked", "Soft Locked"
        CLOSED = "closed", "Closed"
        ARCHIVED = "archived", "Archived"

    entity =    models.ForeignKey(to= Entity, on_delete= models.CASCADE,null=True,related_name='fy',)
    desc =      models.CharField(max_length= 255,null= True,verbose_name='description')
    year_code = models.CharField(max_length=20, null=True, blank=True)
    assessment_year_label = models.CharField(max_length=20, null=True, blank=True)
    finstartyear =      models.DateTimeField(verbose_name='Fin Start Date',null = True)
    finendyear =        models.DateTimeField(verbose_name='Fin End Date',null = True)
    period_status = models.CharField(max_length=20, choices=PeriodStatus.choices, default=PeriodStatus.OPEN)
    books_locked_until = models.DateField(null=True, blank=True)
    gst_locked_until = models.DateField(null=True, blank=True)
    inventory_locked_until = models.DateField(null=True, blank=True)
    ap_ar_locked_until = models.DateField(null=True, blank=True)
    is_year_closed = models.BooleanField(default=False)
    is_audit_closed = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True,)


    def __str__(self):
        entity_str = str(self.entity) if self.entity else 'No Entity'
        if self.finstartyear and self.finendyear:
            
            start_str = DateFormat(self.finstartyear).format('m-Y')
            end_str = DateFormat(self.finendyear).format('m-Y')
            return f'{entity_str} | {start_str} - {end_str}'
        return f'{entity_str} | Financial Year'

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "year_code"],
                condition=Q(year_code__isnull=False),
                name="uq_entity_year_code",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "isactive"]),
            models.Index(fields=["entity", "period_status"]),
        ]

    def save(self, *args, **kwargs):
        self.year_code = (self.year_code or "").strip().upper() or None
        self.assessment_year_label = (self.assessment_year_label or "").strip().upper() or None
        super().save(*args, **kwargs)
    

class Godown(models.Model):
    entity = models.ForeignKey("Entity", on_delete=models.CASCADE, related_name="godowns", null=True, blank=True)
    subentity = models.ForeignKey("SubEntity", on_delete=models.SET_NULL, null=True, blank=True, related_name="godowns")
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    capacity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Godown"
        verbose_name_plural = "Godowns"
        constraints = [
            models.UniqueConstraint(fields=["entity", "code"], name="uq_godown_entity_code"),
            models.UniqueConstraint(fields=["entity", "name"], name="uq_godown_entity_name"),
        ]
        indexes = [
            models.Index(fields=["entity", "is_active"]),
            models.Index(fields=["entity", "subentity", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def display_name(self) -> str:
        parts = []
        if self.subentity_id and getattr(self.subentity, "subentityname", None):
            parts.append(str(self.subentity.subentityname))
        elif self.entity_id and getattr(self.entity, "entityname", None):
            parts.append(str(self.entity.entityname))
        parts.append(self.name)
        return " - ".join([part for part in parts if part])

    def clean(self):
        self.name = (self.name or "").strip()
        self.code = (self.code or "").strip().upper()

        if self.subentity_id and not self.entity_id:
            self.entity_id = self.subentity.entity_id

        if not self.entity_id:
            raise ValidationError({"entity": "Entity is required for a godown."})

        if self.subentity_id and self.subentity.entity_id != self.entity_id:
            raise ValidationError({"subentity": "Subentity must belong to the same entity as the godown."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        if self.is_default and self.entity_id:
            qs = Godown.objects.filter(entity_id=self.entity_id, is_active=True)
            if self.subentity_id:
                qs = qs.filter(subentity_id=self.subentity_id)
            else:
                qs = qs.filter(subentity__isnull=True)
            qs.exclude(pk=self.pk).update(is_default=False)





