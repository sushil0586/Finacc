from django.core.validators import MinLengthValidator, RegexValidator
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from helpers.models import TrackingModel
from Authentication.models import User
from geography.models import Country,State,District,City
from geography.validators import validate_geography_hierarchy
from django.utils.dateformat import DateFormat
import re
#from Authentication.models import User 

# Create your models here.

STRICT_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
RELAXED_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]{3}$")


def _relaxed_gstin_enabled() -> bool:
    if bool(getattr(settings, "ALLOW_RELAXED_GSTIN_FOR_SANDBOX", False)):
        return True
    raw = getattr(settings, "SALES_MASTERGST_ENV", None)
    if raw is None:
        raw = getattr(settings, "MASTERGST_ENV", None)
    if isinstance(raw, str):
        return raw.strip().upper() == "SANDBOX"
    return False


def gstin_validator(value):
    gstin = str(value or "").strip().upper()
    regex = RELAXED_GSTIN_RE if _relaxed_gstin_enabled() else STRICT_GSTIN_RE
    if not regex.fullmatch(gstin):
        raise ValidationError("Enter a valid GSTIN.")
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
            models.Index(fields=["isactive", "entityname"], name="ix_entity_act_name"),
            models.Index(fields=["createdby", "isactive"], name="ix_entity_creator_act"),
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
    is_primary = models.BooleanField(default=False)
    createdby = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["gstin"], condition=Q(isactive=True), name="uq_entity_gst_registration_active_gstin"),
            models.UniqueConstraint(fields=["entity"], condition=Q(isactive=True, is_primary=True), name="uq_entity_gst_registration_primary"),
            models.UniqueConstraint(
                fields=["entity"],
                condition=Q(isactive=True),
                name="uq_entity_gst_registration_entity_active",
            ),
        ]
        indexes = [models.Index(fields=["entity", "is_primary", "isactive"])]

    def clean(self):
        if self.isactive and self.entity_id:
            exists_other_active = EntityGstRegistration.objects.filter(
                entity_id=self.entity_id,
                isactive=True,
            ).exclude(pk=self.pk).exists()
            if exists_other_active:
                raise ValidationError({"entity": "Only one active GST registration is allowed per entity."})

    def save(self, *args, **kwargs):
        self.gstin = (self.gstin or "").strip().upper()
        self.full_clean()
        super().save(*args, **kwargs)


class EntityBankAccountV2(TrackingModel):
    entity = models.ForeignKey("Entity", on_delete=models.CASCADE, related_name="bank_accounts_v2")
    bank_name = models.CharField(max_length=100)
    branch = models.CharField(max_length=100, null=True, blank=True)
    account_number = models.CharField(max_length=32)
    ifsc_code = models.CharField(max_length=11)
    book_ledger = models.ForeignKey("financial.Ledger", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
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
            models.Index(fields=["entity", "isactive", "is_head_office", "subentityname"], name="ix_subent_act_head_nm"),
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


class EntityOrgUnit(TrackingModel):
    class UnitType(models.TextChoices):
        DEPARTMENT = "department", "Department"
        DESIGNATION = "designation", "Designation"
        GRADE = "grade", "Grade"
        BUSINESS_UNIT = "business_unit", "Business Unit"
        COST_CENTER = "cost_center", "Cost Center"
        WORK_LOCATION = "work_location", "Work Location"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        ARCHIVED = "archived", "Archived"

    entity = models.ForeignKey("Entity", on_delete=models.CASCADE, related_name="org_units")
    subentity = models.ForeignKey(
        "SubEntity",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="org_units",
    )
    unit_type = models.CharField(max_length=30, choices=UnitType.choices)
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=150)
    short_name = models.CharField(max_length=80, null=True, blank=True)
    description = models.CharField(max_length=255, null=True, blank=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    manager_title = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=100)
    metadata = models.JSONField(default=dict, blank=True)
    createdby = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["entity_id", "unit_type", "sort_order", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "unit_type", "code"],
                condition=Q(isactive=True, subentity__isnull=True),
                name="uq_entity_org_unit_shared_code_active",
            ),
            models.UniqueConstraint(
                fields=["entity", "subentity", "unit_type", "code"],
                condition=Q(isactive=True, subentity__isnull=False),
                name="uq_entity_org_unit_subentity_code_active",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "unit_type", "isactive"]),
            models.Index(fields=["entity", "subentity", "unit_type"]),
            models.Index(fields=["entity", "status"]),
        ]

    def __str__(self):
        return f"{self.entity_id}:{self.unit_type}:{self.code}"

    def clean(self):
        if self.subentity_id and self.subentity and self.subentity.entity_id != self.entity_id:
            raise ValidationError({"subentity": "Subentity must belong to the selected entity."})

        if self.parent_id and self.parent:
            if self.parent.entity_id != self.entity_id:
                raise ValidationError({"parent": "Parent unit must belong to the same entity."})
            if self.subentity_id and self.parent.subentity_id not in (None, self.subentity_id):
                raise ValidationError({"parent": "Parent unit must be shared or belong to the same subentity."})
            if self.parent_id == self.id:
                raise ValidationError({"parent": "Org unit cannot be its own parent."})

        if self.effective_from and self.effective_to and self.effective_from > self.effective_to:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        self.name = (self.name or "").strip()
        self.short_name = (self.short_name or "").strip() or None
        self.description = (self.description or "").strip() or None
        self.manager_title = (self.manager_title or "").strip() or None
        self.status = (self.status or self.Status.ACTIVE).strip().lower()
        self.full_clean()
        super().save(*args, **kwargs)


class EntityEmploymentProfile(TrackingModel):
    class EmploymentStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        PROBATION = "probation", "Probation"
        NOTICE = "notice", "Notice Period"
        HOLD = "hold", "Hold"
        EXITED = "exited", "Exited"

    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", "Full Time"
        PART_TIME = "part_time", "Part Time"
        CONTRACT = "contract", "Contract"
        CONSULTANT = "consultant", "Consultant"
        INTERN = "intern", "Intern"
        APPRENTICE = "apprentice", "Apprentice"
        TEMPORARY = "temporary", "Temporary"

    class WorkType(models.TextChoices):
        ONSITE = "onsite", "Onsite"
        REMOTE = "remote", "Remote"
        HYBRID = "hybrid", "Hybrid"
        FIELD = "field", "Field"

    class ExitStatus(models.TextChoices):
        RESIGNED = "resigned", "Resigned"
        TERMINATED = "terminated", "Terminated"
        RETIRED = "retired", "Retired"
        ABSCONDED = "absconded", "Absconded"
        SEPARATED = "separated", "Separated"

    entity = models.ForeignKey("Entity", on_delete=models.CASCADE, related_name="employment_profiles")
    subentity = models.ForeignKey(
        "SubEntity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employment_profiles",
    )
    employee_user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="employment_profiles",
    )
    employee_code = models.CharField(max_length=40)
    full_name = models.CharField(max_length=200)
    work_email = models.EmailField(blank=True, default="")
    business_unit = models.ForeignKey(
        "EntityOrgUnit",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="employment_business_units",
    )
    department = models.ForeignKey(
        "EntityOrgUnit",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="employment_departments",
    )
    work_location = models.ForeignKey(
        "EntityOrgUnit",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="employment_work_locations",
    )
    cost_center = models.ForeignKey(
        "EntityOrgUnit",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="employment_cost_centers",
    )
    grade = models.ForeignKey(
        "EntityOrgUnit",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="employment_grades",
    )
    designation = models.ForeignKey(
        "EntityOrgUnit",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="employment_designations",
    )
    manager_user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="managed_employment_profiles",
    )
    employment_type = models.CharField(max_length=20, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME)
    work_type = models.CharField(max_length=20, choices=WorkType.choices, default=WorkType.ONSITE)
    status = models.CharField(max_length=20, choices=EmploymentStatus.choices, default=EmploymentStatus.ACTIVE)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    date_of_joining = models.DateField()
    probation_end = models.DateField(null=True, blank=True)
    confirmation_date = models.DateField(null=True, blank=True)
    last_working_day = models.DateField(null=True, blank=True)
    separation_reason = models.CharField(max_length=255, null=True, blank=True)
    exit_status = models.CharField(max_length=20, choices=ExitStatus.choices, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    createdby = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["entity_id", "employee_code", "-effective_from", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "employee_user", "effective_from"],
                condition=Q(isactive=True),
                name="uq_entity_employment_profile_effective_from",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "employee_user", "isactive"]),
            models.Index(fields=["entity", "subentity", "status"]),
            models.Index(fields=["entity", "effective_from"]),
        ]

    def __str__(self):
        return f"{self.entity_id}:{self.employee_code}:{self.effective_from}"

    def _validate_org_unit(self, unit, *, expected_type: str, field_name: str):
        if unit is None:
            return
        if unit.entity_id != self.entity_id:
            raise ValidationError({field_name: "Org unit must belong to the selected entity."})
        if unit.unit_type != expected_type:
            raise ValidationError({field_name: f"Org unit must be of type '{expected_type}'."})
        if self.subentity_id and unit.subentity_id not in (None, self.subentity_id):
            raise ValidationError({field_name: "Org unit must be shared or belong to the selected subentity."})

    def clean(self):
        if self.subentity_id and self.subentity and self.subentity.entity_id != self.entity_id:
            raise ValidationError({"subentity": "Subentity must belong to the selected entity."})
        if self.manager_user_id == self.employee_user_id:
            raise ValidationError({"manager_user": "Employee cannot be their own manager."})
        if self.effective_to and self.effective_from and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})
        if self.date_of_joining and self.effective_from and self.date_of_joining > self.effective_from:
            raise ValidationError({"effective_from": "Effective start date cannot be before date of joining."})
        if self.confirmation_date and self.probation_end and self.confirmation_date < self.probation_end:
            raise ValidationError({"confirmation_date": "Confirmation date cannot be before probation end."})
        if self.last_working_day and self.date_of_joining and self.last_working_day < self.date_of_joining:
            raise ValidationError({"last_working_day": "Last working day cannot be before date of joining."})

        self._validate_org_unit(self.business_unit, expected_type=EntityOrgUnit.UnitType.BUSINESS_UNIT, field_name="business_unit")
        self._validate_org_unit(self.department, expected_type=EntityOrgUnit.UnitType.DEPARTMENT, field_name="department")
        self._validate_org_unit(self.work_location, expected_type=EntityOrgUnit.UnitType.WORK_LOCATION, field_name="work_location")
        self._validate_org_unit(self.cost_center, expected_type=EntityOrgUnit.UnitType.COST_CENTER, field_name="cost_center")
        self._validate_org_unit(self.grade, expected_type=EntityOrgUnit.UnitType.GRADE, field_name="grade")
        self._validate_org_unit(self.designation, expected_type=EntityOrgUnit.UnitType.DESIGNATION, field_name="designation")

    def save(self, *args, **kwargs):
        self.employee_code = (self.employee_code or "").strip().upper()
        self.full_name = (self.full_name or "").strip()
        self.work_email = (self.work_email or "").strip().lower()
        self.separation_reason = (self.separation_reason or "").strip() or None
        self.status = (self.status or self.EmploymentStatus.ACTIVE).strip().lower()
        self.employment_type = (self.employment_type or self.EmploymentType.FULL_TIME).strip().lower()
        self.work_type = (self.work_type or self.WorkType.ONSITE).strip().lower()
        self.exit_status = (self.exit_status or "").strip().lower() or None
        self.full_clean()
        super().save(*args, **kwargs)


class EntityApprovalPolicy(TrackingModel):
    class PolicyKey(models.TextChoices):
        PAYROLL_RUN = "payroll_run", "Payroll Run Approval"
        PAYROLL_ADJUSTMENT = "payroll_adjustment", "Payroll Adjustment Approval"
        PAYROLL_PAYMENT_HANDOFF = "payroll_payment_handoff", "Payroll Payment Handoff"
        PAYROLL_POSTING = "payroll_posting", "Payroll Posting Approval"
        PAYROLL_PAYMENT_BATCH = "payroll_payment_batch", "Payroll Payment Batch Approval"
        FNF_SETTLEMENT = "fnf_settlement", "FnF Settlement Approval"
        CONTRACT_TAX_DECLARATION = "contract_tax_declaration", "Contract Tax Declaration Approval"
        LEAVE_APPLICATION = "leave_application", "Leave Application Approval"
        EMPLOYMENT_CHANGE = "employment_change", "Employment Change Approval"

    class ApprovalMode(models.TextChoices):
        NONE = "none", "No Approval"
        MANAGER_CHAIN = "manager_chain", "Manager Chain"
        FIXED_USERS = "fixed_users", "Fixed Users"
        PERMISSION_BASED = "permission_based", "Permission Based"
        MIXED = "mixed", "Mixed"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        ARCHIVED = "archived", "Archived"

    entity = models.ForeignKey("Entity", on_delete=models.CASCADE, related_name="approval_policies")
    subentity = models.ForeignKey(
        "SubEntity",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="approval_policies",
    )
    org_unit = models.ForeignKey(
        "EntityOrgUnit",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="approval_policies",
    )
    policy_key = models.CharField(max_length=40, choices=PolicyKey.choices)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    approval_mode = models.CharField(max_length=30, choices=ApprovalMode.choices, default=ApprovalMode.MANAGER_CHAIN)
    manager_levels = models.PositiveIntegerField(default=1)
    min_approvers = models.PositiveIntegerField(default=1)
    approver_roles = models.JSONField(default=list, blank=True)
    approver_permissions = models.JSONField(default=list, blank=True)
    fallback_manager_required = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    createdby = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["entity_id", "policy_key", "subentity_id", "org_unit_id", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "code"],
                condition=Q(isactive=True),
                name="uq_entity_approval_policy_code_active",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "policy_key", "isactive"]),
            models.Index(fields=["entity", "subentity", "policy_key"]),
            models.Index(fields=["entity", "org_unit", "policy_key"]),
            models.Index(fields=["entity", "status"]),
            models.Index(fields=["entity", "policy_key", "status", "subentity"], name="ix_ent_appr_pol_resolve"),
        ]

    def __str__(self):
        return f"{self.entity_id}:{self.policy_key}:{self.code}"

    def clean(self):
        if self.subentity_id and self.subentity and self.subentity.entity_id != self.entity_id:
            raise ValidationError({"subentity": "Subentity must belong to the selected entity."})
        if self.org_unit_id and self.org_unit:
            if self.org_unit.entity_id != self.entity_id:
                raise ValidationError({"org_unit": "Org unit must belong to the selected entity."})
            if self.subentity_id and self.org_unit.subentity_id not in (None, self.subentity_id):
                raise ValidationError({"org_unit": "Org unit must be shared or belong to the selected subentity."})
        if self.effective_from and self.effective_to and self.effective_from > self.effective_to:
            raise ValidationError({"effective_to": "Effective end date must be on or after effective start date."})
        if self.min_approvers < 1:
            raise ValidationError({"min_approvers": "At least one approver is required."})
        if self.manager_levels < 0:
            raise ValidationError({"manager_levels": "Manager levels cannot be negative."})

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        self.name = (self.name or "").strip()
        self.policy_key = (self.policy_key or self.PolicyKey.PAYROLL_RUN).strip().lower()
        self.approval_mode = (self.approval_mode or self.ApprovalMode.MANAGER_CHAIN).strip().lower()
        self.status = (self.status or self.Status.ACTIVE).strip().lower()
        self.approver_roles = [str(role).strip() for role in (self.approver_roles or []) if str(role).strip()]
        self.approver_permissions = [str(code).strip() for code in (self.approver_permissions or []) if str(code).strip()]
        self.full_clean()
        super().save(*args, **kwargs)


class ApprovalRequest(TrackingModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending Approval"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"
        LOCKED = "LOCKED", "Locked"

    entity = models.ForeignKey("Entity", on_delete=models.CASCADE, related_name="approval_requests")
    subentity = models.ForeignKey(
        "SubEntity",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="approval_requests",
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="approval_requests")
    object_id = models.CharField(max_length=64)
    content_object = GenericForeignKey("content_type", "object_id")
    workflow_key = models.CharField(max_length=50)
    title = models.CharField(max_length=180, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="requested_approvals")
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_approvals")
    rejected_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="rejected_approvals")
    cancelled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="cancelled_approvals")
    locked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="locked_approvals")
    requested_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    remarks = models.CharField(max_length=255, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        indexes = [
            models.Index(fields=["entity", "status", "workflow_key"]),
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["entity", "subentity", "status"]),
            models.Index(fields=["entity", "isactive", "workflow_key", "status", "updated_at"], name="ix_appr_req_entity_flow"),
        ]

    def __str__(self):
        return f"{self.workflow_key}:{self.content_type_id}:{self.object_id}:{self.status}"

    def clean(self):
        if self.subentity_id and self.subentity and self.subentity.entity_id != self.entity_id:
            raise ValidationError({"subentity": "Subentity must belong to the selected entity."})

    def save(self, *args, **kwargs):
        self.workflow_key = (self.workflow_key or "").strip().lower()
        self.title = (self.title or "").strip()
        self.status = (self.status or self.Status.DRAFT).strip().upper()
        self.remarks = (self.remarks or "").strip()
        self.full_clean()
        super().save(*args, **kwargs)


class ApprovalStep(TrackingModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"
        SKIPPED = "SKIPPED", "Skipped"

    approval_request = models.ForeignKey(ApprovalRequest, on_delete=models.CASCADE, related_name="steps")
    step_order = models.PositiveIntegerField(default=1)
    step_name = models.CharField(max_length=120, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    approver_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="approval_steps")
    approver_role = models.CharField(max_length=80, blank=True, default="")
    approver_permission = models.CharField(max_length=120, blank=True, default="")
    acted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="acted_approval_steps")
    acted_at = models.DateTimeField(null=True, blank=True)
    remarks = models.CharField(max_length=255, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["approval_request_id", "step_order", "id"]
        indexes = [
            models.Index(fields=["approval_request", "status"]),
            models.Index(fields=["approver_user", "status"]),
            models.Index(fields=["approval_request", "status", "step_order"], name="ix_appr_step_req_status"),
        ]

    def __str__(self):
        return f"{self.approval_request_id}:step{self.step_order}:{self.status}"

    def save(self, *args, **kwargs):
        self.step_name = (self.step_name or "").strip()
        self.status = (self.status or self.Status.PENDING).strip().upper()
        self.approver_role = (self.approver_role or "").strip()
        self.approver_permission = (self.approver_permission or "").strip()
        self.remarks = (self.remarks or "").strip()
        super().save(*args, **kwargs)


class ApprovalActionLog(TrackingModel):
    class Action(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        ROUTED = "ROUTED", "Routed"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"
        LOCKED = "LOCKED", "Locked"
        STATUS_SYNC = "STATUS_SYNC", "Status Sync"

    approval_request = models.ForeignKey(ApprovalRequest, on_delete=models.CASCADE, related_name="action_logs")
    approval_step = models.ForeignKey(ApprovalStep, on_delete=models.SET_NULL, null=True, blank=True, related_name="action_logs")
    action = models.CharField(max_length=20, choices=Action.choices)
    previous_status = models.CharField(max_length=20, blank=True, default="")
    new_status = models.CharField(max_length=20, blank=True, default="")
    acted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="approval_action_logs")
    remarks = models.CharField(max_length=255, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["approval_request", "created_at"]),
            models.Index(fields=["action", "created_at"]),
        ]

    def __str__(self):
        return f"{self.approval_request_id}:{self.action}:{self.new_status}"

    def clean(self):
        if self.pk:
            raise ValidationError("Approval action logs are immutable and cannot be edited.")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Approval action logs are immutable and cannot be edited.")
        self.action = (self.action or "").strip().upper()
        self.previous_status = (self.previous_status or "").strip().upper()
        self.new_status = (self.new_status or "").strip().upper()
        self.remarks = (self.remarks or "").strip()
        super().save(*args, **kwargs)


class NotificationTemplate(TrackingModel):
    class Channel(models.TextChoices):
        IN_APP = "IN_APP", "In App"
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"
        WHATSAPP = "WHATSAPP", "WhatsApp"

    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.IN_APP)
    subject_template = models.CharField(max_length=255, blank=True, default="")
    body_template = models.TextField(blank=True, default="")
    description = models.CharField(max_length=255, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["code"]
        indexes = [
            models.Index(fields=["channel", "isactive"]),
        ]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        self.name = (self.name or "").strip()
        self.channel = (self.channel or self.Channel.IN_APP).strip().upper()
        self.subject_template = (self.subject_template or "").strip()
        self.description = (self.description or "").strip()
        super().save(*args, **kwargs)


class NotificationPreference(TrackingModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notification_preferences")
    entity = models.ForeignKey("Entity", on_delete=models.CASCADE, null=True, blank=True, related_name="notification_preferences")
    event_code = models.CharField(max_length=80)
    in_app_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=False)
    sms_enabled = models.BooleanField(default=False)
    whatsapp_enabled = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["user_id", "entity_id", "event_code"]
        constraints = [
            models.UniqueConstraint(fields=["user", "entity", "event_code"], name="uq_notification_pref_scope_event"),
        ]
        indexes = [
            models.Index(fields=["user", "entity", "event_code"]),
            models.Index(fields=["user", "event_code", "entity"], name="ix_notif_pref_usr_evt"),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.entity_id or 0}:{self.event_code}"

    def clean(self):
        if self.entity_id and self.entity_id <= 0:
            raise ValidationError({"entity": "Entity must be a valid scope when provided."})

    def save(self, *args, **kwargs):
        self.event_code = (self.event_code or "").strip().upper()
        self.full_clean()
        super().save(*args, **kwargs)


class NotificationEvent(TrackingModel):
    class Channel(models.TextChoices):
        IN_APP = "IN_APP", "In App"
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"
        WHATSAPP = "WHATSAPP", "WhatsApp"

    class DeliveryStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CREATED = "CREATED", "Created"
        SKIPPED = "SKIPPED", "Skipped"
        FAILED = "FAILED", "Failed"

    entity = models.ForeignKey("Entity", on_delete=models.CASCADE, related_name="notification_events")
    subentity = models.ForeignKey("SubEntity", on_delete=models.CASCADE, null=True, blank=True, related_name="notification_events")
    template = models.ForeignKey(NotificationTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name="events")
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="notification_events")
    object_id = models.CharField(max_length=64)
    content_object = GenericForeignKey("content_type", "object_id")
    event_code = models.CharField(max_length=80)
    title = models.CharField(max_length=180)
    message = models.TextField(blank=True, default="")
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.IN_APP)
    delivery_status = models.CharField(max_length=20, choices=DeliveryStatus.choices, default=DeliveryStatus.CREATED)
    target_url = models.CharField(max_length=255, blank=True, default="")
    target_label = models.CharField(max_length=120, blank=True, default="")
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="triggered_notification_events")
    recipient_count = models.PositiveIntegerField(default=0)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["entity", "event_code", "created_at"]),
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["channel", "delivery_status", "created_at"]),
            models.Index(fields=["entity", "subentity", "created_at"], name="ix_notif_evt_scope_dt"),
        ]

    def __str__(self):
        return f"{self.event_code}:{self.content_type_id}:{self.object_id}"

    def clean(self):
        if self.subentity_id and self.subentity and self.subentity.entity_id != self.entity_id:
            raise ValidationError({"subentity": "Subentity must belong to the selected entity."})

    def save(self, *args, **kwargs):
        self.event_code = (self.event_code or "").strip().upper()
        self.title = (self.title or "").strip()
        self.channel = (self.channel or self.Channel.IN_APP).strip().upper()
        self.delivery_status = (self.delivery_status or self.DeliveryStatus.CREATED).strip().upper()
        self.target_url = (self.target_url or "").strip()
        self.target_label = (self.target_label or "").strip()
        self.full_clean()
        super().save(*args, **kwargs)


class UserNotification(TrackingModel):
    event = models.ForeignKey(NotificationEvent, on_delete=models.CASCADE, related_name="user_notifications")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_notifications")
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    title_override = models.CharField(max_length=180, blank=True, default="")
    message_override = models.TextField(blank=True, default="")
    target_url_override = models.CharField(max_length=255, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["event", "user"], name="uq_user_notification_event_user"),
        ]
        indexes = [
            models.Index(fields=["user", "is_read", "created_at"]),
            models.Index(fields=["event", "user"]),
            models.Index(fields=["user", "isactive", "is_read", "created_at"], name="ix_user_notif_active_rd"),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.event_id}:{'READ' if self.is_read else 'UNREAD'}"

    @property
    def title(self) -> str:
        return (self.title_override or self.event.title or "").strip()

    @property
    def message(self) -> str:
        return (self.message_override or self.event.message or "").strip()

    @property
    def target_url(self) -> str:
        return (self.target_url_override or self.event.target_url or "").strip()

    def save(self, *args, **kwargs):
        self.title_override = (self.title_override or "").strip()
        self.target_url_override = (self.target_url_override or "").strip()
        super().save(*args, **kwargs)


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
            models.Index(fields=["entity", "isactive", "finstartyear"], name="ix_entfy_act_start"),
            models.Index(fields=["entity", "isactive", "is_year_closed", "finstartyear"], name="ix_entfy_act_closed"),
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
