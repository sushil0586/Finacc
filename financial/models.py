from django.db import models
from django.utils.translation import gettext as _
from django.core.exceptions import ValidationError
from django.db.models import Q

from helpers.models import TrackingModel
from Authentication.models import User
from geography.models import Country, State, District, City
from entity.models import Entity


# ============================================================
# CHOICES (keep outside models for easy API exposure)
# ============================================================

Debit = "Debit"
Credit = "Credit"

BALANCE_TYPE_CHOICES = [
    (Credit, _("Credit")),
    (Debit, _("Debit")),
]

PARTY_TYPE_CHOICES = [
    ("Customer", _("Customer")),
    ("Vendor", _("Vendor")),
    ("Both", _("Customer & Vendor")),
    ("Bank", _("Bank")),
    ("Employee", _("Employee")),
    ("Government", _("Government")),
    ("Other", _("Other")),
]

GSTIN_TYPE_CHOICES = [
    ("Regular", _("Regular")),
    ("Composition", _("Composition")),
    ("Unregistered", _("Unregistered")),
    ("Consumer", _("Consumer")),
    ("SEZ", _("SEZ")),
    ("DeemedExport", _("Deemed Export")),
    ("Export", _("Export")),
]

GST_REG_TYPE_CHOICES = [
    ("Regular", _("Regular")),
    ("Composition", _("Composition")),
    ("UIN", _("UIN")),
    ("SEZ", _("SEZ")),
    ("Unregistered", _("Unregistered")),
]

CURRENCY_CHOICES = [
    ("INR", _("INR")),
    ("USD", _("USD")),
    ("EUR", _("EUR")),
    ("GBP", _("GBP")),
    ("AUD", _("AUD")),
    ("CAD", _("CAD")),
]

BLOCK_STATUS_CHOICES = [
    ("Active", _("Active")),
    ("Blocked", _("Blocked")),
    ("OnHold", _("On Hold")),
]

PAYMENT_TERMS_CHOICES = [
    ("Immediate", _("Immediate")),
    ("Net7", _("Net 7")),
    ("Net15", _("Net 15")),
    ("Net30", _("Net 30")),
    ("Net45", _("Net 45")),
    ("Net60", _("Net 60")),
]


# ============================================================
# Shared helper: enforce "no delete if referenced"
# ============================================================

def _protect_if_referenced(instance, label: str, display_value: str):
    """
    Blocks deletion if ANY related rows exist (enforces: 'no delete if referenced').
    PostgreSQL friendly.
    """
    related_models = set()

    for rel in instance._meta.related_objects:
        accessor = rel.get_accessor_name()
        if not accessor:
            continue

        try:
            manager_or_obj = getattr(instance, accessor)
        except Exception:
            continue

        # reverse FK manager
        try:
            if manager_or_obj.exists():
                related_models.add(rel.related_model.__name__)
                continue
        except Exception:
            pass

        # reverse OneToOne object
        try:
            if manager_or_obj is not None:
                related_models.add(rel.related_model.__name__)
        except Exception:
            pass

    if related_models:
        raise ValidationError(
            f"Cannot delete {label} '{display_value}' because it is referenced in: {', '.join(sorted(related_models))}."
        )


# ============================================================
# MODELS
# ============================================================

class accounttype(TrackingModel):
    accounttypename = models.CharField(max_length=255, verbose_name=_("Acc type Name"))
    accounttypecode = models.CharField(max_length=255, verbose_name=_("Acc Type Code"))
    balanceType = models.BooleanField(verbose_name=_("Balance details"), default=True)

    entity = models.ForeignKey(Entity, null=True, blank=True, on_delete=models.CASCADE)
    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.accounttypename} "

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entity", "accounttypecode"], name="uq_accounttype_entity_accounttypecode"),
            models.UniqueConstraint(fields=["entity", "accounttypename"], name="uq_accounttype_entity_accounttypename"),
        ]
        indexes = [
            models.Index(fields=["entity", "accounttypecode"], name="ix_accounttype_entity_code"),
            models.Index(fields=["entity", "accounttypename"], name="ix_accounttype_entity_name"),
        ]


class accountHead(TrackingModel):
    Details_in_BS = [("Yes", _("Yes")), ("No", _("No"))]
    Group = [("Balance_sheet", _("Balance Sheet")), ("P/l", _("Profit Loss"))]

    name = models.CharField(max_length=200, verbose_name=_("Account Name"), db_index=True)
    code = models.IntegerField(verbose_name=_("Account Head Code"), db_index=True)

    balanceType = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name=_("Balance Type"),
        choices=BALANCE_TYPE_CHOICES,
    )

    accounttype = models.ForeignKey(
        to=accounttype,
        related_name="accounthead_accounttype",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    drcreffect = models.CharField(
        max_length=20,
        verbose_name=_("Debit/credit Effect"),
        choices=BALANCE_TYPE_CHOICES,
    )

    description = models.CharField(max_length=200, verbose_name=_("Description"), null=True, blank=True)

    # prevent accidental COA wipe
    accountheadsr = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        verbose_name=_("Account head Sr"),
    )

    detailsingroup = models.IntegerField(null=True, blank=True)

    entity = models.ForeignKey(Entity, related_name="entity_accountheads", null=True, blank=True, on_delete=models.CASCADE)

    canbedeleted = models.BooleanField(verbose_name=_("Can be deleted"), default=True)
    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True, blank=True)

    def clean(self):
        # Prevent circular parent references
        if self.accountheadsr_id and self.pk:
            parent = self.accountheadsr
            seen = {self.pk}
            while parent is not None:
                if parent.pk in seen:
                    raise ValidationError({"accountheadsr": _("Circular Account Head hierarchy is not allowed.")})
                seen.add(parent.pk)
                parent = parent.accountheadsr

    def delete(self, *args, **kwargs):
        if self.canbedeleted is False:
            raise ValidationError(f"Cannot delete account head '{self.name}' because canbedeleted is False.")
        _protect_if_referenced(self, "account head", self.name)
        super().delete(*args, **kwargs)

    class Meta:
        verbose_name = _("Account head")
        verbose_name_plural = _("Account Heads")
        constraints = [
            models.UniqueConstraint(fields=["entity", "code"], name="uq_accounthead_entity_code"),
            models.CheckConstraint(condition=Q(code__gt=0), name="ck_accounthead_code_positive"),
        ]
        indexes = [
            models.Index(fields=["entity", "code"], name="ix_accounthead_entity_code"),
            models.Index(fields=["entity", "name"], name="ix_accounthead_entity_name"),
            models.Index(fields=["entity", "accounttype"], name="ix_accounthead_entity_type"),
        ]

    def __str__(self):
        return f"{self.name} , {self.code}"


class account(TrackingModel):
    accountdate = models.DateTimeField(verbose_name="Account date", null=True, blank=True)

    iscompany = models.BooleanField(verbose_name=_("IsCompany"), default=False)

    website = models.URLField(max_length=255, null=True, blank=True, verbose_name=_("Website"))
    reminders = models.IntegerField(verbose_name=_("Reminders"), null=True, blank=True)

    accounthead = models.ForeignKey(
        to=accountHead,
        related_name="accounthead_accounts",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
    )
    creditaccounthead = models.ForeignKey(
        to=accountHead,
        related_name="accounthead_creditaccounts",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
    )

    accountcode = models.IntegerField(verbose_name=_("Account Code"), null=True, blank=True, default=1000, db_index=True)

    gstno = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Gst No"), db_index=True)

    accountname = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Account Name"), db_index=True)
    legalname = models.CharField(max_length=255, null=True, blank=True)

    contraaccount = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        verbose_name=_("conta account"),
    )

    address1 = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Address Line 1"))
    address2 = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Address Line 2"))
    addressfloorno = models.CharField(max_length=255, null=True, blank=True)
    addressstreet = models.CharField(max_length=255, null=True, blank=True)

    gstintype = models.CharField(max_length=255, null=True, blank=True, choices=GSTIN_TYPE_CHOICES)
    blockstatus = models.CharField(max_length=10, null=True, blank=True, verbose_name="Block Status", choices=BLOCK_STATUS_CHOICES)

    dateofreg = models.DateTimeField(verbose_name="Date of Registration", null=True, blank=True)
    dateofdreg = models.DateTimeField(verbose_name="Date of De Regitration", null=True, blank=True)

    country = models.ForeignKey(Country, null=True, blank=True, on_delete=models.CASCADE)
    state = models.ForeignKey(to=State, on_delete=models.CASCADE, null=True, blank=True)
    district = models.ForeignKey(to=District, on_delete=models.CASCADE, null=True, blank=True)
    city = models.ForeignKey(to=City, on_delete=models.CASCADE, null=True, blank=True)

    openingbcr = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Opening Balance Cr"))
    openingbdr = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Opening Balance Dr"))

    contactno = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Contact no"))
    contactno2 = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Contact no2"))

    pincode = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Pincode"))
    cin = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("cin"))
    msme = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("msme"))
    gsttdsno = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("gsttdsno"))

    emailid = models.EmailField(max_length=254, null=True, blank=True, verbose_name=_("Email id"))

    agent = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Agent/Group"))
    pan = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("PAN"), db_index=True)

    tobel10cr = models.BooleanField(verbose_name=_("Turnover below 10 lac"), default=False)
    isaddsameasbillinf = models.BooleanField(verbose_name=_("isaddsameasbillinf"), default=False)
    approved = models.BooleanField(verbose_name=_("Wheather aproved"), default=False)

    tdsno = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Tds A/c No"))

    entity = models.ForeignKey(Entity, null=True, blank=True, on_delete=models.CASCADE, db_index=True)

    rtgsno = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Rtgs no"))
    bankname = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Bank Name"))
    adhaarno = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Adhaar No"))
    saccode = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("SAC Code"))
    contactperson = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Contact Person"))

    deprate = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Depreciaion Rate"))
    tdsrate = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("TDS Rate"))
    gstshare = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Adhaar No"))

    quanity1 = models.IntegerField(verbose_name=_("Quanity 1"), null=True, blank=True)
    quanity2 = models.IntegerField(verbose_name=_("Quanity 2"), null=True, blank=True)

    banKAcno = models.CharField(max_length=50, verbose_name=_("Bank A/c No"), null=True, blank=True)

    composition = models.BooleanField(verbose_name=_("Bank A/c No"), default=False)

    canbedeleted = models.BooleanField(verbose_name=_("Can be deleted"), default=True)

    accounttype = models.ForeignKey(to=accounttype, on_delete=models.SET_NULL, null=True, blank=True)

    sharepercentage = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Share Percentage"))

    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True, blank=True)

    # Add-only fields to support broader ERP use cases
    partytype = models.CharField(max_length=20, null=True, blank=True, choices=PARTY_TYPE_CHOICES, verbose_name=_("Party Type"))
    creditlimit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Credit Limit"))
    creditdays = models.IntegerField(null=True, blank=True, verbose_name=_("Credit Days"))
    currency = models.CharField(max_length=10, null=True, blank=True, choices=CURRENCY_CHOICES, verbose_name=_("Currency"))
    paymentterms = models.CharField(max_length=100, null=True, blank=True, choices=PAYMENT_TERMS_CHOICES, verbose_name=_("Payment Terms"))
    isactive = models.BooleanField(default=True, verbose_name=_("Is Active"))
    blockedreason = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Blocked Reason"))
    gstregtype = models.CharField(max_length=30, null=True, blank=True, choices=GST_REG_TYPE_CHOICES, verbose_name=_("GST Reg Type"))
    is_sez = models.BooleanField(default=False, verbose_name=_("Is SEZ"))
    tdssection = models.CharField(max_length=20, null=True, blank=True, verbose_name=_("TDS Section"))
    tds_threshold = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("TDS Threshold"))
    istcsapplicable = models.BooleanField(default=False, verbose_name=_("Is TCS Applicable"))
    tcscode = models.CharField(max_length=20, null=True, blank=True, verbose_name=_("TCS Code"))

    def __str__(self):
        return f"{self.accountname} , {self.gstno}"

    def clean(self):
        cr = self.openingbcr or 0
        dr = self.openingbdr or 0
        if cr and dr:
            raise ValidationError(_("Only one of Opening Balance Cr or Opening Balance Dr can be non-zero."))

        if self.pincode:
            pin = str(self.pincode).strip()
            if pin and (not pin.isdigit()):
                raise ValidationError({"pincode": _("Pincode must be numeric.")})

        if self.accounthead_id and self.accounttype_id:
            if self.accounthead.accounttype_id and self.accounthead.accounttype_id != self.accounttype_id:
                raise ValidationError(_("Account.accounttype must match AccountHead.accounttype (or leave one of them blank)."))

        if self.creditdays is not None and self.creditdays < 0:
            raise ValidationError({"creditdays": _("Credit Days cannot be negative.")})
        if self.creditlimit is not None and self.creditlimit < 0:
            raise ValidationError({"creditlimit": _("Credit Limit cannot be negative.")})

    def delete(self, *args, **kwargs):
        if self.canbedeleted is False:
            raise ValidationError(f"Cannot delete account '{self.accountname}' because canbedeleted is False.")
        _protect_if_referenced(self, "account", self.accountname or str(self.pk))
        super().delete(*args, **kwargs)

    class Meta:
        verbose_name = _("Account")
        verbose_name_plural = _("Accounts")
        constraints = [
            
            models.CheckConstraint(condition=Q(openingbcr__gte=0) | Q(openingbcr__isnull=True), name="ck_account_openingbcr_nonneg"),
            models.CheckConstraint(condition=Q(openingbdr__gte=0) | Q(openingbdr__isnull=True), name="ck_account_openingbdr_nonneg"),
            models.CheckConstraint(condition=Q(accountcode__gt=0) | Q(accountcode__isnull=True), name="ck_account_accountcode_positive"),
            models.CheckConstraint(condition=Q(creditdays__gte=0) | Q(creditdays__isnull=True), name="ck_account_creditdays_nonneg"),
            models.CheckConstraint(condition=Q(creditlimit__gte=0) | Q(creditlimit__isnull=True), name="ck_account_creditlimit_nonneg"),
        ]
        indexes = [
            models.Index(fields=["entity", "accountname"], name="ix_account_entity_name"),
            models.Index(fields=["entity", "gstno"], name="ix_account_entity_gstno"),
            models.Index(fields=["entity", "pan"], name="ix_account_entity_pan"),
            models.Index(fields=["entity", "accounthead"], name="ix_account_entity_head"),
            models.Index(fields=["entity", "partytype"], name="ix_account_entity_partytype"),
            models.Index(fields=["entity", "isactive"], name="ix_account_entity_isactive"),
        ]


class ShippingDetails(models.Model):
    gstno = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Gst No"))
    account = models.ForeignKey(account, on_delete=models.CASCADE, related_name="shipping_details", db_index=True)

    entity = models.ForeignKey(Entity, null=True, blank=True, on_delete=models.CASCADE)
    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True, blank=True)

    address1 = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Address Line 1"))
    address2 = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Address Line 2"))

    country = models.ForeignKey(Country, null=True, blank=True, on_delete=models.CASCADE)
    state = models.ForeignKey(State, null=True, blank=True, on_delete=models.CASCADE)
    district = models.ForeignKey(District, null=True, blank=True, on_delete=models.CASCADE)
    city = models.ForeignKey(City, null=True, blank=True, on_delete=models.CASCADE)

    isprimary = models.BooleanField(verbose_name=_("Is Primary"), default=False, db_index=True)

    pincode = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Pincode"))
    phoneno = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Phone No"))

    emailid = models.EmailField(max_length=254, null=True, blank=True, verbose_name=_("Email id"))
    full_name = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Full Name"))

    def __str__(self):
        return f"{self.full_name} - {self.account.accountname}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account"],
                condition=Q(isprimary=True),
                name="uq_shippingdetails_one_primary_per_account",
            )
        ]
        indexes = [
            models.Index(fields=["account", "isprimary"], name="ix_ship_account_primary"),
            models.Index(fields=["entity", "account"], name="ix_ship_entity_account"),
        ]


class ContactDetails(models.Model):
    account = models.ForeignKey(account, on_delete=models.CASCADE, related_name="contact_details", db_index=True)

    entity = models.ForeignKey(Entity, null=True, blank=True, on_delete=models.CASCADE)
    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True, blank=True)

    address1 = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Address Line 1"))
    address2 = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Address Line 2"))

    designation = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("designation"))

    country = models.ForeignKey(Country, null=True, blank=True, on_delete=models.CASCADE)
    state = models.ForeignKey(State, null=True, blank=True, on_delete=models.CASCADE)
    district = models.ForeignKey(District, null=True, blank=True, on_delete=models.CASCADE)
    city = models.ForeignKey(City, null=True, blank=True, on_delete=models.CASCADE)

    pincode = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Pincode"))
    phoneno = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Phone No"))

    emailid = models.EmailField(max_length=254, null=True, blank=True, verbose_name=_("Email id"))
    full_name = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Full Name"))

    isprimary = models.BooleanField(default=False, verbose_name=_("Is Primary"))

    def __str__(self):
        return f"{self.full_name} - {self.account.accountname}"

    class Meta:
        indexes = [
            models.Index(fields=["account"], name="ix_contact_account"),
            models.Index(fields=["entity", "account"], name="ix_contact_entity_account"),
            models.Index(fields=["account", "isprimary"], name="ix_contact_account_primary"),
        ]


class staticacounts(TrackingModel):
    accounttype = models.ForeignKey(to=accounttype, on_delete=models.SET_NULL, null=True, blank=True)
    staticaccount = models.CharField(max_length=255, verbose_name=_("static acount"))
    code = models.CharField(max_length=255, verbose_name=_("Code"))
    entity = models.ForeignKey(Entity, null=True, blank=True, on_delete=models.CASCADE)
    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.staticaccount}"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entity", "code"], name="uq_staticacounts_entity_code"),
            models.UniqueConstraint(fields=["entity", "staticaccount"], name="uq_staticacounts_entity_name"),
        ]
        indexes = [
            models.Index(fields=["entity", "code"], name="ix_staticacc_entity_code"),
            models.Index(fields=["entity", "staticaccount"], name="ix_staticacc_entity_name"),
        ]


class staticacountsmapping(TrackingModel):
    staticaccount = models.ForeignKey(to=staticacounts, on_delete=models.SET_NULL, null=True, blank=True)
    account = models.ForeignKey(to=account, on_delete=models.SET_NULL, null=True, blank=True)
    entity = models.ForeignKey(Entity, null=True, blank=True, on_delete=models.CASCADE)
    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entity", "staticaccount"], name="uq_staticmap_entity_staticaccount"),
        ]
        indexes = [
            models.Index(fields=["entity", "staticaccount"], name="ix_staticmap_entity_static"),
            models.Index(fields=["entity", "account"], name="ix_staticmap_entity_account"),
        ]


class AccountBankDetails(TrackingModel):
    account = models.ForeignKey(account, on_delete=models.CASCADE, related_name="bank_details")
    entity = models.ForeignKey(Entity, null=True, blank=True, on_delete=models.CASCADE)
    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True, blank=True)

    bankname = models.CharField(max_length=100, null=True, blank=True, verbose_name=_("Bank Name"))
    banKAcno = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Bank A/c No"))
    ifsc = models.CharField(max_length=20, null=True, blank=True, verbose_name=_("IFSC"))
    branch = models.CharField(max_length=100, null=True, blank=True, verbose_name=_("Branch"))
    isprimary = models.BooleanField(default=False, verbose_name=_("Is Primary"))

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account"],
                condition=Q(isprimary=True),
                name="uq_bankdetails_one_primary_per_account",
            )
        ]
        indexes = [
            models.Index(fields=["account", "isprimary"], name="ix_bank_account_primary"),
            models.Index(fields=["entity", "account"], name="ix_bank_entity_account"),
        ]
