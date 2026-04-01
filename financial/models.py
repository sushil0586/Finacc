from django.db import models
from django.utils.translation import gettext as _
from django.core.exceptions import ValidationError
from django.db.models import Q

from helpers.models import TrackingModel
from Authentication.models import User
from geography.models import Country, State, District, City



# ============================================================
# CHOICES (keep outside models for easy API exposure)
# ============================================================

Debit = "Debit"
Credit = "Credit"

BALANCE_TYPE_CHOICES = [
    (Credit, _("Yes")),
    (Debit, _("No")),
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

STATIC_ACCOUNT_SCOPE_CHOICES = [
    ("posting", _("Posting")),
    ("reporting", _("Reporting")),
    ("system", _("System")),
]

OPENING_BALANCE_EDIT_MODE_CHOICES = [
    ("always", _("Always Allow")),
    ("before_posting", _("Allow Before First Posting")),
    ("locked", _("Locked")),
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


class Ledger(TrackingModel):
    """
    Additive parent accounting master.

    Current code still uses `account` as the operational model, so this model is
    introduced in parallel. Later, posting and reporting should move toward
    Ledger-first references while `account` becomes the party/commercial profile.

    Intended steady state:
    - accounting identity lives in Ledger
    - posting/reporting/static mappings point to Ledger
    - account keeps only party/commercial/compliance details for party ledgers
    """

    entity = models.ForeignKey("entity.Entity", null=True, blank=True, on_delete=models.CASCADE, db_index=True)
    ledger_code = models.IntegerField(null=True, blank=True, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    legal_name = models.CharField(max_length=255, null=True, blank=True)

    accounthead = models.ForeignKey(
        "financial.accountHead",
        related_name="ledger_accountheads",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    creditaccounthead = models.ForeignKey(
        "financial.accountHead",
        related_name="ledger_credit_accountheads",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    contra_ledger = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="contra_ledgers",
    )
    accounttype = models.ForeignKey(
        "financial.accounttype",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledgers",
    )

    is_party = models.BooleanField(default=False, db_index=True)
    is_system = models.BooleanField(default=False)
    canbedeleted = models.BooleanField(default=True)

    openingbcr = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    openingbdr = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        code = self.ledger_code if self.ledger_code is not None else "-"
        return f"{code} - {self.name}"

    def clean(self):
        cr = self.openingbcr or 0
        dr = self.openingbdr or 0
        if cr and dr:
            raise ValidationError(_("Only one of Opening Balance Cr or Opening Balance Dr can be non-zero."))

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entity", "ledger_code"], name="uq_ledger_entity_ledger_code"),
            models.CheckConstraint(check=Q(ledger_code__gt=0) | Q(ledger_code__isnull=True), name="ck_ledger_code_positive"),
            models.CheckConstraint(check=Q(openingbcr__gte=0) | Q(openingbcr__isnull=True), name="ck_ledger_openingbcr_nonneg"),
            models.CheckConstraint(check=Q(openingbdr__gte=0) | Q(openingbdr__isnull=True), name="ck_ledger_openingbdr_nonneg"),
        ]
        indexes = [
            models.Index(fields=["entity", "ledger_code"], name="ix_ledger_entity_code"),
            models.Index(fields=["entity", "name"], name="ix_ledger_entity_name"),
            models.Index(fields=["entity", "is_party"], name="ix_ledger_entity_party"),
        ]


class FinancialSettings(TrackingModel):
    """
    Entity-level financial policy/configuration.

    This is intentionally small and additive. The goal is to move finance rules
    out of serializer/view hardcoding over time, without changing any existing
    endpoint contracts right now.

    Immediate expected use:
    - opening balance edit policy
    - uniqueness/validation behavior toggles where business needs policy control

    Later candidates:
    - default currency
    - round-off/default ledger mappings
    - voucher numbering / posting strictness flags
    """

    entity = models.OneToOneField("entity.Entity", on_delete=models.CASCADE, related_name="financial_settings")
    opening_balance_edit_mode = models.CharField(
        max_length=20,
        choices=OPENING_BALANCE_EDIT_MODE_CHOICES,
        default="before_posting",
    )
    enforce_gst_uniqueness = models.BooleanField(default=True)
    enforce_pan_uniqueness = models.BooleanField(default=True)
    require_gst_for_registered_parties = models.BooleanField(default=False)
    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"Financial Settings - {self.entity}"

    class Meta:
        verbose_name = _("Financial Settings")
        verbose_name_plural = _("Financial Settings")

class accounttype(TrackingModel):
    """
    Legacy accounting classification bucket.

    Current purpose:
    - groups account heads / ledgers at a coarse level
    - used by existing create flows, admin imports, and some lookup APIs

    Likely future direction:
    - keep only if the business still needs a separate "account type" taxonomy
    - otherwise this can later be folded into Ledger/AccountHead classification
      once all APIs stop depending on it directly
    """
    accounttypename = models.CharField(max_length=255, verbose_name=_("Acc type Name"))
    accounttypecode = models.CharField(max_length=255, verbose_name=_("Acc Type Code"))
    balanceType = models.BooleanField(verbose_name=_("Balance details"), default=True)

    entity = models.ForeignKey("entity.Entity", null=True, blank=True, on_delete=models.CASCADE)
    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.accounttypename}"

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

    entity = models.ForeignKey("entity.Entity", related_name="entity_accountheads", null=True, blank=True, on_delete=models.CASCADE)

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
            models.CheckConstraint(check=Q(code__gt=0), name="ck_accounthead_code_positive"),
        ]
        indexes = [
            models.Index(fields=["entity", "code"], name="ix_accounthead_entity_code"),
            models.Index(fields=["entity", "name"], name="ix_accounthead_entity_name"),
            models.Index(fields=["entity", "accounttype"], name="ix_accounthead_entity_type"),
        ]

    def __str__(self):
        return f"{self.name} , {self.code}"


class account(TrackingModel):
    # Transitional parent link. Existing posting/invoice code still points to
    # financial.account. Later, accounting identity should live in Ledger and
    # this model should focus on party/commercial profile fields.
    #
    # Fields that are candidates to move fully to Ledger later:
    # - accountcode
    # - accounthead
    # - creditaccounthead
    # - contraaccount
    # - accounttype
    # - openingbcr / openingbdr
    #
    # Fields that are likely to remain here:
    # - GST/PAN/TDS/TCS/compliance fields
    # - party/contact/commercial profile fields
    # - credit terms / payment terms
    #
    # NOTE:
    # New writes for compliance/commercial/address profile data should go to:
    # - AccountComplianceProfile
    # - AccountCommercialProfile
    # - AccountAddress
    # Legacy columns are retained temporarily for controlled schema cutover.
    ledger = models.OneToOneField(
        "financial.Ledger",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="account_profile",
    )

    accountdate = models.DateTimeField(verbose_name="Account date", null=True, blank=True)

    iscompany = models.BooleanField(verbose_name=_("IsCompany"), default=False)

    website = models.URLField(max_length=255, null=True, blank=True, verbose_name=_("Website"))

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

    accountcode = models.IntegerField(verbose_name=_("Account Code"), null=True, blank=True, db_index=True)

    accountname = models.CharField(max_length=200, null=True, blank=True, verbose_name=_("Account Name"), db_index=True)
    legalname = models.CharField(max_length=255, null=True, blank=True)

    contraaccount = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        verbose_name=_("contra account"),
    )

    dateofreg = models.DateTimeField(verbose_name="Date of Registration", null=True, blank=True)
    dateofdreg = models.DateTimeField(verbose_name="Date of De Regitration", null=True, blank=True)

    openingbcr = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Opening Balance Cr"))
    openingbdr = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Opening Balance Dr"))

    contactno = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Contact no"))
    contactno2 = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Contact no2"))

    emailid = models.EmailField(max_length=254, null=True, blank=True, verbose_name=_("Email id"))

    tobel10cr = models.BooleanField(verbose_name=_("Turnover below 10 lac"), default=False)
    isaddsameasbillinf = models.BooleanField(verbose_name=_("isaddsameasbillinf"), default=False)

    entity = models.ForeignKey("entity.Entity", null=True, blank=True, on_delete=models.CASCADE, db_index=True)

    rtgsno = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Rtgs no"))
    bankname = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Bank Name"))
    adhaarno = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Adhaar No"))
    saccode = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("SAC Code"))
    contactperson = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Contact Person"))

    deprate = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Depreciaion Rate"))
    gstshare = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Adhaar No"))

    quanity1 = models.IntegerField(verbose_name=_("Quanity 1"), null=True, blank=True)
    quanity2 = models.IntegerField(verbose_name=_("Quanity 2"), null=True, blank=True)

    banKAcno = models.CharField(max_length=50, verbose_name=_("Bank A/c No"), null=True, blank=True)

    composition = models.BooleanField(verbose_name=_("Bank A/c No"), default=False)

    canbedeleted = models.BooleanField(verbose_name=_("Can be deleted"), default=True)

    accounttype = models.ForeignKey(to=accounttype, on_delete=models.SET_NULL, null=True, blank=True)

    sharepercentage = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Share Percentage"))

    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True, blank=True)

    isactive = models.BooleanField(default=True, verbose_name=_("Is Active"))

    def __str__(self):
        return f"{self.accountname}"

    # Ledger-first helper accessors. These allow downstream code to start
    # reading accounting identity from Ledger without breaking current callers
    # that still expect the legacy account columns to exist.
    @property
    def effective_accounting_code(self):
        return self.ledger.ledger_code if self.ledger_id and self.ledger.ledger_code is not None else self.accountcode

    @property
    def effective_accounting_name(self):
        return self.ledger.name if self.ledger_id and self.ledger.name else self.accountname

    @property
    def effective_accounthead_id(self):
        return self.ledger.accounthead_id if self.ledger_id and self.ledger.accounthead_id else self.accounthead_id

    @property
    def effective_creditaccounthead_id(self):
        return (
            self.ledger.creditaccounthead_id
            if self.ledger_id and self.ledger.creditaccounthead_id
            else self.creditaccounthead_id
        )

    @property
    def effective_openingbdr(self):
        return self.ledger.openingbdr if self.ledger_id and self.ledger.openingbdr is not None else self.openingbdr

    @property
    def effective_openingbcr(self):
        return self.ledger.openingbcr if self.ledger_id and self.ledger.openingbcr is not None else self.openingbcr

    def clean(self):
        cr = self.openingbcr or 0
        dr = self.openingbdr or 0
        if cr and dr:
            raise ValidationError(_("Only one of Opening Balance Cr or Opening Balance Dr can be non-zero."))

        if self.accounthead_id and self.accounttype_id:
            if self.accounthead.accounttype_id and self.accounthead.accounttype_id != self.accounttype_id:
                raise ValidationError(_("Account.accounttype must match AccountHead.accounttype (or leave one of them blank)."))

        if self.ledger_id and self.entity_id and self.ledger.entity_id != self.entity_id:
            raise ValidationError({"ledger": _("Selected ledger belongs to a different entity.")})


    def delete(self, *args, **kwargs):
        if self.canbedeleted is False:
            raise ValidationError(f"Cannot delete account '{self.accountname}' because canbedeleted is False.")
        _protect_if_referenced(self, "account", self.accountname or str(self.pk))
        super().delete(*args, **kwargs)

    class Meta:
        verbose_name = _("Account")
        verbose_name_plural = _("Accounts")
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "accountcode"],
                condition=Q(accountcode__isnull=False),
                name="uq_account_entity_accountcode_present",
            ),
            models.CheckConstraint(check=Q(openingbcr__gte=0) | Q(openingbcr__isnull=True), name="ck_account_openingbcr_nonneg"),
            models.CheckConstraint(check=Q(openingbdr__gte=0) | Q(openingbdr__isnull=True), name="ck_account_openingbdr_nonneg"),
            models.CheckConstraint(check=Q(accountcode__gt=0) | Q(accountcode__isnull=True), name="ck_account_accountcode_positive"),
        ]
        indexes = [
            models.Index(fields=["entity", "accountname"], name="ix_account_entity_name"),
            models.Index(fields=["entity", "accounthead"], name="ix_account_entity_head"),
            models.Index(fields=["entity", "isactive"], name="ix_account_entity_isactive"),
        ]
        # PAN uniqueness is intentionally deferred to a later migration because
        # current data already contains duplicates that must be cleaned first.


class ShippingDetails(models.Model):
    gstno = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Gst No"))
    account = models.ForeignKey(account, on_delete=models.CASCADE, related_name="shipping_details", db_index=True)

    entity = models.ForeignKey("entity.Entity", null=True, blank=True, on_delete=models.CASCADE)
    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True, blank=True)

    address1 = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Address Line 1"))
    address2 = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Address Line 2"))

    country = models.ForeignKey(Country, null=True, blank=True, on_delete=models.PROTECT)
    state = models.ForeignKey(State, null=True, blank=True, on_delete=models.PROTECT)
    district = models.ForeignKey(District, null=True, blank=True, on_delete=models.PROTECT)
    city = models.ForeignKey(City, null=True, blank=True, on_delete=models.PROTECT)

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

    entity = models.ForeignKey("entity.Entity", null=True, blank=True, on_delete=models.CASCADE)
    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True, blank=True)

    address1 = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Address Line 1"))
    address2 = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Address Line 2"))

    designation = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("designation"))

    country = models.ForeignKey(Country, null=True, blank=True, on_delete=models.PROTECT)
    state = models.ForeignKey(State, null=True, blank=True, on_delete=models.PROTECT)
    district = models.ForeignKey(District, null=True, blank=True, on_delete=models.PROTECT)
    city = models.ForeignKey(City, null=True, blank=True, on_delete=models.PROTECT)

    pincode = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Pincode"))
    phoneno = models.CharField(max_length=50, null=True, blank=True, verbose_name=_("Phone No"))

    emailid = models.EmailField(max_length=254, null=True, blank=True, verbose_name=_("Email id"))
    full_name = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Full Name"))

    isprimary = models.BooleanField(default=False, verbose_name=_("Is Primary"))

    def __str__(self):
        return f"{self.full_name} - {self.account.accountname}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account"],
                condition=Q(isprimary=True),
                name="uq_contactdetails_one_primary_per_account",
            )
        ]
        indexes = [
            models.Index(fields=["account"], name="ix_contact_account"),
            models.Index(fields=["entity", "account"], name="ix_contact_entity_account"),
            models.Index(fields=["account", "isprimary"], name="ix_contact_account_primary"),
        ]


class AccountBankDetails(TrackingModel):
    account = models.ForeignKey(account, on_delete=models.CASCADE, related_name="bank_details")
    entity = models.ForeignKey("entity.Entity", null=True, blank=True, on_delete=models.CASCADE)
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
                condition=Q(isprimary=True, isactive=True),
                name="uq_bankdetails_one_primary_per_account",
            )
        ]
        indexes = [
            models.Index(fields=["account", "isprimary"], name="ix_bank_account_primary"),
            models.Index(fields=["entity", "account"], name="ix_bank_entity_account"),
        ]


class AccountAddress(TrackingModel):
    class AddressType(models.TextChoices):
        REGISTERED = "registered", _("Registered")
        BILLING = "billing", _("Billing")
        SHIPPING = "shipping", _("Shipping")
        CORRESPONDENCE = "correspondence", _("Correspondence")

    account = models.ForeignKey(account, on_delete=models.CASCADE, related_name="addresses")
    entity = models.ForeignKey("entity.Entity", null=True, blank=True, on_delete=models.CASCADE)
    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True, blank=True)

    address_type = models.CharField(max_length=20, choices=AddressType.choices, default=AddressType.BILLING)
    line1 = models.CharField(max_length=255, null=True, blank=True)
    line2 = models.CharField(max_length=255, null=True, blank=True)
    floor_no = models.CharField(max_length=255, null=True, blank=True)
    street = models.CharField(max_length=255, null=True, blank=True)
    country = models.ForeignKey(Country, null=True, blank=True, on_delete=models.PROTECT)
    state = models.ForeignKey(State, null=True, blank=True, on_delete=models.PROTECT)
    district = models.ForeignKey(District, null=True, blank=True, on_delete=models.PROTECT)
    city = models.ForeignKey(City, null=True, blank=True, on_delete=models.PROTECT)
    pincode = models.CharField(max_length=50, null=True, blank=True)
    isprimary = models.BooleanField(default=False, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account"],
                condition=Q(isprimary=True, isactive=True),
                name="uq_accaddr_primary",
            )
        ]
        indexes = [
            models.Index(fields=["entity", "account"], name="ix_accaddr_ent_acc"),
            models.Index(fields=["account", "address_type"], name="ix_accaddr_acc_type"),
        ]


class AccountComplianceProfile(TrackingModel):
    account = models.OneToOneField(account, on_delete=models.CASCADE, related_name="compliance_profile")
    entity = models.ForeignKey("entity.Entity", null=True, blank=True, on_delete=models.CASCADE)
    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True, blank=True)

    gstno = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    pan = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    gstintype = models.CharField(max_length=255, null=True, blank=True, choices=GSTIN_TYPE_CHOICES)
    gstregtype = models.CharField(max_length=30, null=True, blank=True, choices=GST_REG_TYPE_CHOICES)
    is_sez = models.BooleanField(default=False)

    cin = models.CharField(max_length=50, null=True, blank=True)
    msme = models.CharField(max_length=50, null=True, blank=True)
    gsttdsno = models.CharField(max_length=50, null=True, blank=True)
    tdsno = models.CharField(max_length=50, null=True, blank=True)
    tdsrate = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    tdssection = models.CharField(max_length=20, null=True, blank=True)
    tds_threshold = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    istcsapplicable = models.BooleanField(default=False)
    tcscode = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["entity", "gstno"], name="ix_acccomp_ent_gst"),
            models.Index(fields=["entity", "pan"], name="ix_acccomp_ent_pan"),
        ]


class AccountCommercialProfile(TrackingModel):
    account = models.OneToOneField(account, on_delete=models.CASCADE, related_name="commercial_profile")
    entity = models.ForeignKey("entity.Entity", null=True, blank=True, on_delete=models.CASCADE)
    createdby = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True, blank=True)

    partytype = models.CharField(max_length=20, null=True, blank=True, choices=PARTY_TYPE_CHOICES)
    creditlimit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    creditdays = models.IntegerField(null=True, blank=True)
    paymentterms = models.CharField(max_length=100, null=True, blank=True, choices=PAYMENT_TERMS_CHOICES)
    currency = models.CharField(max_length=10, null=True, blank=True, choices=CURRENCY_CHOICES)
    blockstatus = models.CharField(max_length=10, null=True, blank=True, choices=BLOCK_STATUS_CHOICES)
    blockedreason = models.CharField(max_length=255, null=True, blank=True)
    approved = models.BooleanField(default=False)
    agent = models.CharField(max_length=50, null=True, blank=True)
    reminders = models.IntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(creditdays__gte=0) | Q(creditdays__isnull=True),
                name="ck_acccom_crdays_nn",
            ),
            models.CheckConstraint(
                check=Q(creditlimit__gte=0) | Q(creditlimit__isnull=True),
                name="ck_acccom_crlimit_nn",
            ),
        ]
        indexes = [
            models.Index(fields=["entity", "partytype"], name="ix_acccom_ent_party"),
            models.Index(fields=["entity", "currency"], name="ix_acccom_ent_curr"),
        ]


class InvoiceCustomFieldDefinition(TrackingModel):
    class Module(models.TextChoices):
        SALES_INVOICE = "sales_invoice", _("Sales Invoice")
        PURCHASE_INVOICE = "purchase_invoice", _("Purchase Invoice")

    class FieldType(models.TextChoices):
        TEXT = "text", _("Text")
        NUMBER = "number", _("Number")
        DATE = "date", _("Date")
        BOOLEAN = "boolean", _("Boolean")
        SELECT = "select", _("Select")
        MULTISELECT = "multiselect", _("Multi Select")

    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE, related_name="invoice_custom_field_defs")
    subentity = models.ForeignKey("entity.SubEntity", null=True, blank=True, on_delete=models.CASCADE, related_name="invoice_custom_field_defs")
    module = models.CharField(max_length=30, choices=Module.choices)
    key = models.CharField(max_length=64)
    label = models.CharField(max_length=120)
    field_type = models.CharField(max_length=20, choices=FieldType.choices, default=FieldType.TEXT)
    is_required = models.BooleanField(default=False)
    order_no = models.PositiveIntegerField(default=0)
    help_text = models.CharField(max_length=255, blank=True, default="")
    options_json = models.JSONField(default=list, blank=True)
    applies_to_account = models.ForeignKey(
        "financial.account",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="invoice_custom_field_defs",
    )

    class Meta:
        indexes = [
            models.Index(fields=["entity", "module", "isactive"], name="ix_icfdef_ent_mod_act"),
            models.Index(fields=["entity", "subentity", "module"], name="ix_icfdef_ent_sub_mod"),
            models.Index(fields=["entity", "module", "key"], name="ix_icfdef_ent_mod_key"),
            models.Index(fields=["entity", "module", "applies_to_account"], name="ix_icfdef_ent_mod_acc"),
        ]


class InvoiceCustomFieldDefault(TrackingModel):
    definition = models.ForeignKey(
        InvoiceCustomFieldDefinition,
        on_delete=models.CASCADE,
        related_name="defaults",
    )
    party_account = models.ForeignKey(
        "financial.account",
        on_delete=models.CASCADE,
        related_name="invoice_custom_field_defaults",
    )
    default_value = models.JSONField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["definition", "party_account"],
                name="uq_icfdefault_definition_party",
            )
        ]
        indexes = [
            models.Index(fields=["definition", "party_account"], name="ix_icfdefault_def_party"),
        ]
