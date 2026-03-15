from django.core.validators import MinLengthValidator, RegexValidator
from django.db import models
from django.db.models import Q
from helpers.models import TrackingModel
from Authentication.models import User,MainMenu,Submenu
from geography.models import Country,State,District,City
from django.utils.dateformat import DateFormat
#from Authentication.models import User 

# Create your models here.

gstin_validator = RegexValidator(
    regex=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$",
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
    
class OwnerShipTypes(models.Model):
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
    unitType =        models.ForeignKey(UnitType, on_delete=models.CASCADE,null= True)
    GstRegitrationType =        models.ForeignKey(GstRegistrationType, on_delete=models.CASCADE,null= True)
    gst_registration_status = models.CharField(
        max_length=20,
        choices=GstStatus.choices,
        default=GstStatus.REGISTERED,
    )
    website = models.URLField(blank=True, null=True)
    address =     models.CharField(max_length= 100)
    address2 =     models.CharField(max_length= 100,null= True,blank = True)
    addressfloorno =     models.CharField(max_length= 50,null= True,blank = True)
    addressstreet =     models.CharField(max_length= 100,null= True,blank = True)
    ownername =   models.CharField(max_length= 100,null= True)
    country =     models.ForeignKey(Country, on_delete=models.CASCADE,null= True)
    state =       models.ForeignKey(State, on_delete=models.CASCADE,null= True)
    district =    models.ForeignKey(District, on_delete=models.CASCADE,null= True)
    city =        models.ForeignKey(City, on_delete=models.CASCADE,null= True)
    registered_address_same_as_principal = models.BooleanField(default=True)
    bank =        models.ForeignKey(BankDetail, on_delete=models.CASCADE,null= True)
    bankacno =    models.CharField(max_length= 50,null= True)
    ifsccode     =    models.CharField(max_length= 50,null= True)
    pincode =    models.CharField(max_length= 50,null= True, validators=[pincode_validator])
    phoneoffice = models.CharField(max_length= 20, validators=[phone_validator])
    phoneresidence = models.CharField(max_length= 20, validators=[phone_validator])
    contact_person_name = models.CharField(max_length=100, null=True, blank=True)
    contact_person_designation = models.CharField(max_length=100, null=True, blank=True)
    mobile_primary = models.CharField(max_length=20, null=True, blank=True, validators=[phone_validator])
    mobile_secondary = models.CharField(max_length=20, null=True, blank=True, validators=[phone_validator])
    panno =        models.CharField(max_length= 20,null= True, validators=[pan_validator])
    tds =           models.CharField(max_length= 20,null= True, validators=[tan_validator])
    tdscircle =        models.CharField(max_length= 20,null= True)
    tan_no = models.CharField(max_length=20, null=True, blank=True, validators=[tan_validator])
    cin_no = models.CharField(max_length=21, null=True, blank=True, validators=[cin_validator])
    llpin_no = models.CharField(max_length=8, null=True, blank=True, validators=[llpin_validator])
    udyam_no = models.CharField(max_length=30, null=True, blank=True)
    iec_code = models.CharField(max_length=10, null=True, blank=True, validators=[iec_validator])
    email =    models.CharField(max_length= 50,null= True)
    email_primary = models.EmailField(max_length=100, null=True, blank=True)
    email_secondary = models.EmailField(max_length=100, null=True, blank=True)
    support_email = models.EmailField(max_length=100, null=True, blank=True)
    accounts_email = models.EmailField(max_length=100, null=True, blank=True)
    tcs206c1honsale  = models.BooleanField(blank =True,null = True)
    is_tds_applicable = models.BooleanField(default=False)
    is_tcs_applicable = models.BooleanField(default=False)
    is_einvoice_applicable = models.BooleanField(default=False)
    is_ewaybill_applicable = models.BooleanField(default=False)
    is_msme_registered = models.BooleanField(default=False)
    msme_category = models.CharField(max_length=20, choices=MsmeCategory.choices, null=True, blank=True)
   # tds194qonsale  = models.BooleanField(blank =True,null = True)
    gstno =        models.CharField(max_length= 20,null= True, validators=[gstin_validator])
    gstintype =        models.CharField(max_length= 20,null= True)
    gst_effective_from = models.DateField(null=True, blank=True)
    gst_cancelled_from = models.DateField(null=True, blank=True)
    gst_username = models.CharField(max_length=100, null=True, blank=True)
    nature_of_business = models.CharField(max_length=150, null=True, blank=True)
    incorporation_date = models.DateField(null=True, blank=True)
    business_commencement_date = models.DateField(null=True, blank=True)
    blockstatus = models.CharField(max_length= 10,null= True,verbose_name='Block Status')
    dateofreg = models.DateTimeField(verbose_name='Date of Registration',null = True)
    dateofdreg = models.DateTimeField(verbose_name='Date of De Regitration',null = True)
    const =    models.ForeignKey(to= Constitution, on_delete= models.CASCADE,null=True)
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
            models.Index(fields=["gstno"]),
            models.Index(fields=["panno"]),
            models.Index(fields=["organization_status"]),
        ]

    def save(self, *args, **kwargs):
        self.entity_code = (self.entity_code or "").strip().upper() or None
        self.trade_name = (self.trade_name or "").strip() or None
        self.short_name = (self.short_name or "").strip() or None
        self.contact_person_name = (self.contact_person_name or self.ownername or "").strip() or None
        self.mobile_primary = (self.mobile_primary or self.phoneoffice or "").strip() or None
        self.mobile_secondary = (self.mobile_secondary or self.phoneresidence or "").strip() or None
        self.email_primary = (self.email_primary or self.email or "").strip().lower() or None
        self.tan_no = (self.tan_no or self.tds or "").strip().upper() or None
        self.gstno = (self.gstno or "").strip().upper() or None
        self.panno = (self.panno or "").strip().upper() or None
        self.tds = (self.tds or "").strip().upper() or None
        self.cin_no = (self.cin_no or "").strip().upper() or None
        self.llpin_no = (self.llpin_no or "").strip().upper() or None
        self.iec_code = (self.iec_code or "").strip().upper() or None
        self.udyam_no = (self.udyam_no or "").strip().upper() or None
        super().save(*args, **kwargs)
    


    

class BankAccount(models.Model):
    entity = models.ForeignKey(to= 'Entity', on_delete=models.CASCADE, related_name='bank_accounts')
    bank_name = models.CharField(max_length=100)
    branch = models.CharField(max_length=100)
    account_number = models.CharField(max_length=20)
    ifsc_code = models.CharField(max_length=11)
    account_type = models.CharField(max_length=20, choices=[('current', 'Current'), ('savings', 'Savings')])
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"
    

class GstAccountDetail(TrackingModel):
    gstin = models.CharField(max_length= 25,null= True)
    tradeName = models.CharField(max_length= 255,null= True)
    legalName = models.CharField(max_length= 255,null= True)
    addrBnm = models.CharField(max_length= 255,null= True)
    addrBno = models.CharField(max_length= 255,null= True)
    addrFlno = models.CharField(max_length= 255,null= True)
    addrSt = models.CharField(max_length= 255,null= True)
    addrLoc =  models.ForeignKey(City, on_delete=models.CASCADE,null= True)
    stateCode = models.ForeignKey(State, on_delete=models.CASCADE,null= True)
    district =    models.ForeignKey(District, on_delete=models.CASCADE,null= True)
    country =     models.ForeignKey(Country, on_delete=models.CASCADE,null= True)
    addrPncd = models.CharField(max_length= 10,null= True)
    txpType = models.CharField(max_length= 25,null= True)
    status = models.CharField(max_length= 25,null= True)
    blkStatus = models.CharField(max_length= 10,null= True)
    dtReg = models.DateTimeField(verbose_name='Date of registration',null = True)
    dtDReg = models.DateTimeField(verbose_name='Date of De registration',null = True)

    

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
    address =     models.CharField(max_length= 255)
    address2 =     models.CharField(max_length= 255,null= True,blank = True)
    addressfloorno =     models.CharField(max_length= 50,null= True,blank = True)
    addressstreet =     models.CharField(max_length= 100,null= True,blank = True)
    country =     models.ForeignKey(Country, on_delete=models.CASCADE,null= True)
    state =       models.ForeignKey(State, on_delete=models.CASCADE,null= True)
    district =    models.ForeignKey(District, on_delete=models.CASCADE,null= True)
    city =        models.ForeignKey(City, on_delete=models.CASCADE,null= True)
    pincode =    models.CharField(max_length= 255,null= True, validators=[pincode_validator])
    phoneoffice = models.CharField(max_length= 255,null= True, validators=[phone_validator])
    phoneresidence = models.CharField(max_length= 255,null= True, validators=[phone_validator])
    email =    models.CharField(max_length= 255,null= True)
    email_primary = models.EmailField(max_length=100, null=True, blank=True)
    mobile_primary = models.CharField(max_length=20, null=True, blank=True, validators=[phone_validator])
    mobile_secondary = models.CharField(max_length=20, null=True, blank=True, validators=[phone_validator])
    contact_person_name = models.CharField(max_length=100, null=True, blank=True)
    contact_person_designation = models.CharField(max_length=100, null=True, blank=True)
    gstno = models.CharField(max_length=20, null=True, blank=True, validators=[gstin_validator])
    GstRegitrationType = models.ForeignKey(GstRegistrationType, on_delete=models.SET_NULL, null=True, blank=True)
    ismainentity  = models.BooleanField(blank =True,null = True)
    is_head_office = models.BooleanField(default=False)
    can_sell = models.BooleanField(default=True)
    can_purchase = models.BooleanField(default=True)
    can_stock = models.BooleanField(default=True)
    can_bank = models.BooleanField(default=True)
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
        ]
        ordering = ["sort_order", "subentityname"]
        indexes = [
            models.Index(fields=["entity", "subentityname"]),
            models.Index(fields=["entity", "subentity_code"]),
            models.Index(fields=["gstno"]),
        ]

    def save(self, *args, **kwargs):
        self.subentity_code = (self.subentity_code or "").strip().upper() or None
        self.email_primary = (self.email_primary or self.email or "").strip().lower() or None
        self.mobile_primary = (self.mobile_primary or self.phoneoffice or "").strip() or None
        self.mobile_secondary = (self.mobile_secondary or self.phoneresidence or "").strip() or None
        self.gstno = (self.gstno or "").strip().upper() or None
        self.is_head_office = bool(self.is_head_office or self.ismainentity)
        if self.is_head_office:
            self.branch_type = self.BranchType.HEAD_OFFICE
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
        ]

    def save(self, *args, **kwargs):
        self.year_code = (self.year_code or "").strip().upper() or None
        self.assessment_year_label = (self.assessment_year_label or "").strip().upper() or None
        super().save(*args, **kwargs)
    

class EntityConstitution(TrackingModel):
    entity =    models.ForeignKey(to= Entity, on_delete=models.CASCADE,null=True,related_name='constitution',)
    shareholder =      models.CharField(max_length= 255,null= True,verbose_name='shareholder')
    pan =      models.CharField(max_length= 25,null= True,verbose_name='pan')
    sharepercentage = models.DecimalField(max_digits=10, decimal_places=2,null=True,blank=True,verbose_name='Share Percentage')
    createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,null=True,)


    def __str__(self):
        return f'{self.entity}'
    
class EntityOwnership(models.Model):
    # OWNERSHIP_TYPE_CHOICES = [
    #     ('owner', 'Owner'),
    #     ('partner', 'Partner'),
    #     ('shareholder', 'Shareholder'),
    #     ('trustee', 'Trustee'),
    #     ('board_member', 'Board Member'),
    #     ('official', 'Government Official'),
    # ]
    OwnerShipType = models.ForeignKey(OwnerShipTypes, on_delete=models.CASCADE, related_name='ownerships')
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name='ownerships')
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    mobile = models.CharField(max_length=15, blank=True, null=True)
    pan_number = models.CharField(max_length=10, blank=True, null=True)
    aadhaar_number = models.CharField(max_length=12, blank=True, null=True)
    share_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    capital_contribution = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    is_primary = models.BooleanField(default=False)
    designation = models.CharField(max_length=100, blank=True, null=True)
    remarks = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} - {self.ownership_type}"
    








class EntityDetail(models.Model): 
    entity = models.OneToOneField(Entity,
        on_delete=models.CASCADE,
        primary_key=True,)
    style =        models.CharField(max_length= 255,null= True)
    commodity =        models.CharField(max_length= 255,null= True)
    weightDecimal =        models.CharField(max_length= 255,null= True)
    email =        models.EmailField(max_length= 24,null= True)
    registrationno =        models.CharField(max_length= 255,null= True)
    division =        models.CharField(max_length= 255,null= True)
    collectorate =        models.CharField(max_length= 255,null= True)
    range =        models.CharField(max_length= 255,null= True)
    adhaarudyog =        models.CharField(max_length= 255,null= True)
    cinno =        models.CharField(max_length= 255,null= True)
    jobwork =        models.CharField(max_length= 255,null= True)
    gstno =        models.CharField(max_length= 255,null= True)
    gstintype =        models.CharField(max_length= 255,null= True)
    esino =        models.CharField(max_length= 255,null= True)

# class entity_user(TrackingModel):
#     entity = models.ForeignKey(entity,related_name='entityUser',
#         on_delete=models.CASCADE)
#     user = models.ForeignKey(to= User,related_name='userentity', on_delete= models.CASCADE)
#     createdby = models.ForeignKey(to= User, on_delete= models.CASCADE,related_name='%(class)s_requests_created',default=1)

#     class Meta:
#         constraints = [
#         models.UniqueConstraint(fields=['entity', 'user'], name='unique entity_user')
#     ]
    

class Role(TrackingModel):
    rolename = models.CharField(max_length=150)
    roledesc = models.CharField(max_length=150)
    rolelevel = models.IntegerField()
    entity =    models.ForeignKey(to= Entity, on_delete= models.CASCADE,null=True)

    def __str__(self):
        return f'{self.rolename} - {self.entity}'

    

class RolePrivilege(TrackingModel):
    role =     models.ForeignKey(Role,null= True,on_delete= models.CASCADE,related_name='submenudetails')
    submenu =     models.ForeignKey(Submenu,null= True,on_delete= models.CASCADE)
    entity =    models.ForeignKey(to= Entity, on_delete= models.CASCADE,null=True)
 


    class Meta:
        verbose_name = ('Role Priveledge')
        verbose_name_plural = ('Role Priveledges')


    
    def __str__(self):
        return f'{self.submenu} - {self.role} - {self.entity}'
    


class UserRole(TrackingModel):
    role =     models.ForeignKey(Role,null= True,on_delete= models.CASCADE,related_name='userrole')
    user =     models.ForeignKey(User,null= True,on_delete= models.CASCADE)
    entity =    models.ForeignKey(to= Entity, on_delete= models.CASCADE,null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entity", "user"], name="uq_entity_user_role_once"),
        ]

    def __str__(self):
        return f'{self.role}'
    


class MasterGstDetail(TrackingModel):
    email = models.CharField(max_length=100, null=True,verbose_name='email')
    username = models.CharField(max_length=100, null=True,verbose_name='username')
    password = models.CharField(max_length=100, null=True,verbose_name='password')
    client_id = models.CharField(max_length=200, null=True,verbose_name='clientid')
    client_secret = models.CharField(max_length=200, null=True,verbose_name='client_secret')
    gstin = models.CharField(max_length=20, null=True,verbose_name='gstin')
    entity =    models.ForeignKey(to= Entity, on_delete= models.CASCADE,null=True)

    def __str__(self):
         return f'{self.username}'
    

class Godown(models.Model):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, unique=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    capacity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Godown"
        verbose_name_plural = "Godowns"

    def __str__(self):
        return f"{self.name} ({self.code})"








