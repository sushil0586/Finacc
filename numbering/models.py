from django.db import models, transaction
from django.db.models import Q, F, UniqueConstraint, CheckConstraint,Index
from django.utils import timezone
from django.core.validators import RegexValidator
from django.db.models.functions import Lower
from entity.models import Entity,entityfinancialyear,subentity
from Authentication.models import User
from invoice.models import doctype

# If you have TrackingModel with created_at/updated_at/user fields, keep it.
# from common.models import TrackingModel


UPPER_CODE = RegexValidator(r'^[A-Z0-9_-]{2,20}$',
                            "Code must be 2–20 chars (A–Z, 0–9, _, -).")

class DocumentType(models.Model):
    class Direction(models.TextChoices):
        OUTWARD = "OUT", "Outward (Sales/Issue)"
        INWARD  = "IN",  "Inward (Purchase/Receipt)"
        ADJUST  = "ADJ", "Adjustment/Journal"

    docname  = models.CharField(max_length=255, verbose_name="Document name")
    doccode  = models.CharField(max_length=20, validators=[UPPER_CODE], unique=False)
    entity   = models.ForeignKey('entity.Entity', null=True, blank=True, on_delete=models.CASCADE)
    createdby = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='financial_doctypes_created'
    )

    # NEW flags:
    direction          = models.CharField(max_length=3, choices=Direction.choices, default=Direction.ADJUST)
    is_return          = models.BooleanField(default=False)
    affects_stock      = models.BooleanField(default=False)
    affects_accounting = models.BooleanField(default=True)
    supports_einvoice  = models.BooleanField(default=False)
    supports_ewaybill  = models.BooleanField(default=False)
    is_active          = models.BooleanField(default=True)

    class Meta:
        db_table = "financial_doctype"
        constraints = [
            UniqueConstraint(fields=["doccode"], condition=Q(entity__isnull=True), name="uq_doctype_code_global1"),
            UniqueConstraint(fields=["entity","doccode"], condition=Q(entity__isnull=False), name="uq_doctype_code_entity1"),
        ]
        indexes = [Index(fields=["entity","doccode"], name="ix_doctype_entity_code")]
        ordering = ["entity_id", "doccode"]

    def save(self, *args, **kwargs):
        if self.doccode: self.doccode = self.doccode.strip().upper()
        if self.docname: self.docname = self.docname.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        scope = getattr(self.entity, "entityname", "GLOBAL") if self.entity_id else "GLOBAL"
        return f"{scope}:{self.doccode} — {self.docname}"




class DocumentSequenceSettings(models.Model):
    """
    Generalized per-(entity, finyear, subentity?, doctype, series?) numbering settings.
    Use allocate_document_numbers(...) to atomically allocate the next values.
    """

    # ---- Scope keys ----
    entity      = models.ForeignKey(Entity, on_delete=models.CASCADE)
    entityfinid = models.ForeignKey(entityfinancialyear, on_delete=models.CASCADE,
                                    verbose_name='Financial Year', null=True, blank=True)
    subentity   = models.ForeignKey(subentity, on_delete=models.CASCADE, null=True, blank=True)

    # Keep as FK to your existing doctype model (assumed to be financial.doctype with a "code" field)
    doctype     = models.ForeignKey(DocumentType, on_delete=models.CASCADE)

    # Optional extra partition (multiple series per tuple)
    series_key  = models.CharField(max_length=30, blank=True, null=True,
                                   help_text="Optional series/branch key (e.g., BR01, WH-A, CASH, BANK)")

    # ---- Counters ----
    starting_number = models.BigIntegerField(default=1)
    current_number  = models.BigIntegerField(default=1)    # NEXT display sequence to issue
    next_integer    = models.BigIntegerField(default=1)    # NEXT pure integer id to issue (bill/voucher no)

    # ---- Formatting ----
    prefix  = models.CharField(max_length=20, default='', blank=True)
    suffix  = models.CharField(max_length=20, default='', blank=True)
    number_padding = models.IntegerField(default=0)        # zero-pad width for {number}
    include_year   = models.BooleanField(default=False)
    include_month  = models.BooleanField(default=False)
    separator      = models.CharField(max_length=5, default='-')

    custom_format  = models.CharField(
        max_length=120, blank=True,
        help_text="Placeholders: {prefix} {year} {month} {number} {suffix} {series} {entity} {subentity}"
    )

    # ---- Reset policy ----
    RESET_CHOICES = [
        ('none',    'Do not reset'),
        ('monthly', 'Reset every month'),
        ('yearly',  'Reset every year'),
    ]
    reset_frequency = models.CharField(max_length=10, choices=RESET_CHOICES, default='none')

    # Track last reset via deterministic key (YYYY or YYYYMM)
    last_reset_key  = models.CharField(max_length=8, blank=True, null=True)
    last_reset_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Document Sequence Setting"
        verbose_name_plural = "Document Sequence Settings"
        constraints = [
            UniqueConstraint(
                fields=("entity", "entityfinid", "subentity", "doctype", "series_key"),
                name="uq_docseq_entity_fin_sub_doctype_series",
            ),
            CheckConstraint(name="ck_padding_nonneg", check=Q(number_padding__gte=0)),
            CheckConstraint(name="ck_curr_ge_start",  check=Q(current_number__gte=F('starting_number'))),
            CheckConstraint(name="ck_nextint_ge_zero",check=Q(next_integer__gte=0)),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "doctype"], name="ix_docseq_entity_fin_doctype"),
            models.Index(fields=["series_key"], name="ix_docseq_series"),
        ]

    def __str__(self):
        se = f"/{self.subentity_id}" if self.subentity_id else ""
        sk = f"/{self.series_key}" if self.series_key else ""
        return f"{self.entity_id}/{self.entityfinid_id}{se}{sk} :: {self.doctype_id} -> {self.current_number}"

    # ---- helpers ----
    def _current_reset_key(self) -> str | None:
        today = timezone.localdate()
        if self.reset_frequency == 'monthly':
            return f"{today:%Y}{today:%m}"  # YYYYMM
        if self.reset_frequency == 'yearly':
            return f"{today:%Y}"           # YYYY
        return None

    def _maybe_reset(self) -> bool:
        """
        Reset the display sequence to starting_number when the reset key changes.
        Returns True if a reset happened.
        """
        key = self._current_reset_key()
        if not key:
            return False
        if key != self.last_reset_key:
            self.current_number = self.starting_number
            self.last_reset_key = key
            self.last_reset_date = timezone.localdate()
            return True
        return False

    def render_number(self, n: int) -> str:
        today = timezone.localdate()
        year  = f"{today:%Y}" if self.include_year  else ""
        month = f"{today:%m}" if self.include_month else ""
        num   = str(n).zfill(self.number_padding or 0)
        series = self.series_key or ""
        ent    = str(self.entity_id) if self.entity_id else ""
        subent = str(self.subentity_id) if self.subentity_id else ""

        if self.custom_format:
            return self.custom_format.format(
                prefix=self.prefix or "",
                year=year,
                month=month,
                number=num,
                suffix=self.suffix or "",
                series=series,
                entity=ent,
                subentity=subent,
            )

        parts = [p for p in [self.prefix, year, month, num, self.suffix] if p]
        return self.separator.join(parts)


# -------- Allocator API (call this from serializers/services) ------------------

def _docseq_qs(*, entity, entityfinid, doctype, subentity=None, series_key=None):
    qs = DocumentSequenceSettings.objects.select_for_update().filter(
        entity=entity, entityfinid=entityfinid, doctype=doctype
    )
    qs = qs.filter(subentity=subentity) if subentity else qs.filter(subentity__isnull=True)
    qs = qs.filter(series_key=series_key) if series_key else qs.filter(series_key__isnull=True)
    return qs


@transaction.atomic
def allocate_document_numbers(*, entity, entityfinid, doctype, subentity=None, series_key=None) -> tuple[int, str]:
    """
    Atomically allocate (integer_id, display_no).
    Requires a pre-seeded DocumentSequenceSettings row for the given tuple.
    """
    settings = _docseq_qs(entity=entity, entityfinid=entityfinid, doctype=doctype,
                          subentity=subentity, series_key=series_key).get()

    if settings._maybe_reset():
        settings.save(update_fields=["current_number", "last_reset_key", "last_reset_date"])

    seq = settings.current_number
    settings.current_number = seq + 1

    int_no = settings.next_integer
    settings.next_integer = int_no + 1

    settings.save(update_fields=["current_number", "next_integer"])

    display_no = settings.render_number(seq)
    return int_no, display_no
