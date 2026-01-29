# catalog/models.py  (FINAL - cleaner + GST-complete improvements)
# Notes:
# - No existing field/column names removed/renamed.
# - Only ADDITIONS + validations/constraints to make GST handling robust.

from decimal import Decimal
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from PIL import Image, ImageDraw, ImageFont

from entity.models import Entity, subentity
from financial.models import account

try:
    from barcode import Code128
    from barcode.writer import ImageWriter
except ImportError:
    Code128 = None
    ImageWriter = None


# ----------------------------------------------------------------------
# Abstract base classes
# ----------------------------------------------------------------------

class TimeStampedModel(models.Model):
    createdon = models.DateTimeField(auto_now_add=True)
    modifiedon = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class EntityScopedModel(TimeStampedModel):
    entity = models.ForeignKey(
        Entity,
        on_delete=models.PROTECT,
        related_name='catalog_%(class)s_set',
    )
    isactive = models.BooleanField(default=True)

    class Meta:
        abstract = True


# ----------------------------------------------------------------------
# Master data
# ----------------------------------------------------------------------

class ProductCategory(EntityScopedModel):
    pcategoryname = models.CharField(max_length=100)
    maincategory = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='subcategories'
    )
    level = models.PositiveSmallIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['entity', 'pcategoryname'],
                name='uq_productcategory_entity_name'
            )
        ]
        ordering = ['pcategoryname']

    def __str__(self):
        return f"{self.pcategoryname} ({self.entity})"


class Brand(EntityScopedModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['entity', 'name'],
                name='uq_brand_entity_name'
            )
        ]
        ordering = ['name']

    def __str__(self):
        return self.name


class UnitOfMeasure(EntityScopedModel):
    """
    UQC is important for Indian e-invoice / e-waybill (NIC UQC codes like KGS, NOS, MTR, etc.)
    Keep your current code field, and add UQC separately.
    """
    code = models.CharField(max_length=20)
    description = models.CharField(max_length=100, blank=True)

    # ✅ NEW: NIC UQC code (optional but strongly recommended)
    uqc = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        help_text="NIC UQC code for e-invoice/e-waybill (e.g., KGS, NOS, MTR).",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['entity', 'code'],
                name='uq_uom_entity_code'
            ),
            # ✅ NEW: prevent duplicate UQC within entity (only if provided)
            models.UniqueConstraint(
                fields=['entity', 'uqc'],
                condition=Q(uqc__isnull=False) & ~Q(uqc=""),
                name='uq_uom_entity_uqc'
            ),
        ]
        ordering = ['code']

    def __str__(self):
        return self.code


class ProductStatus(models.TextChoices):
    ACTIVE = 'active', _('Active')
    DISCONTINUED = 'discontinued', _('Discontinued')
    BLOCKED = 'blocked', _('Blocked')
    UPCOMING = 'upcoming', _('Upcoming')


class Product(EntityScopedModel):
    productname = models.CharField(max_length=200)
    sku = models.CharField(max_length=100)
    productdesc = models.CharField(max_length=500, blank=True)

    productcategory = models.ForeignKey(
        ProductCategory,
        on_delete=models.PROTECT,
        related_name='productsCategory'
    )

    # accounts moved here instead of ProductAccountMapping
    sales_account = models.ForeignKey(
        account,
        on_delete=models.PROTECT,
        related_name='+',
        null=True,
        blank=True,
        help_text="If null, use entity default sales account."
    )
    purchase_account = models.ForeignKey(
        account,
        on_delete=models.PROTECT,
        related_name='+',
        null=True,
        blank=True,
        help_text="If null, use entity default purchase account."
    )

    brand = models.ForeignKey(
        Brand,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='productsCategory'
    )
    base_uom = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name='base_products'
    )

    is_pieces = models.BooleanField(
        default=True,
        help_text="If true, quantity is treated as pieces (integer). Otherwise, allows decimals."
    )

    # GST / compliance flags
    is_service = models.BooleanField(default=False)
    is_batch_managed = models.BooleanField(default=False)
    is_serialized = models.BooleanField(default=False)

    # for section 9(5) cases
    is_ecomm_9_5_service = models.BooleanField(default=False)

    # ✅ NEW: optional compliance helpers
    default_is_rcm = models.BooleanField(
        default=False,
        help_text="Default reverse charge applicability for this product/service (optional helper)."
    )
    is_itc_eligible = models.BooleanField(
        default=True,
        help_text="Whether ITC is generally eligible for this product/service (optional helper)."
    )

    product_status = models.CharField(
        max_length=20,
        choices=ProductStatus.choices,
        default=ProductStatus.ACTIVE,
    )
    launch_date = models.DateField(null=True, blank=True)
    discontinue_date = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['entity', 'sku'],
                name='uq_product_entity_sku'
            )
        ]

    def __str__(self):
        return f"{self.productname} ({self.sku})"

    def clean(self):
        # If marked service, you might want to ensure base_uom has UQC set (optional)
        # Not enforcing hard because many systems keep UQC optional initially.
        if self.launch_date and self.discontinue_date and self.discontinue_date < self.launch_date:
            raise ValidationError({"discontinue_date": "Discontinue date cannot be before launch date."})


# ----------------------------------------------------------------------
# GST / HSN
# ----------------------------------------------------------------------

class HsnSac(EntityScopedModel):
    code = models.CharField(max_length=20)
    description = models.CharField(max_length=255, blank=True)
    is_service = models.BooleanField(default=False)

    default_sgst = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    default_cgst = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    default_igst = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    default_cess = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # GST classification helpers
    is_exempt = models.BooleanField(default=False)
    is_nil_rated = models.BooleanField(default=False)
    is_non_gst = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['entity', 'code'],
                name='uq_hsnsac_entity_code'
            )
        ]

    def __str__(self):
        return self.code


class GstType(models.TextChoices):
    REGULAR = 'regular', _('Regular')
    EXEMPT = 'exempt', _('Exempt')
    NIL = 'nil_rated', _('Nil Rated')
    NON_GST = 'non_gst', _('Non-GST')
    COMPOSITION = 'composition', _('Composition')


class CessType(models.TextChoices):
    NONE = 'none', _('None')                    # default / no cess
    AD_VALOREM = 'ad_valorem', _('Ad valorem')  # % of value
    SPECIFIC = 'specific', _('Specific')        # per unit (qty-based)
    COMPOSITE = 'composite', _('Composite')     # % + specific


class ProductGstRate(TimeStampedModel):
    """
    FINAL RULESET
    ------------
    1) Stores CGST, SGST, IGST.
    2) Enforces: IGST == (CGST + SGST) for taxable types.
    3) Computes gst_rate automatically as (CGST + SGST).
    4) One default GST rate row per product.
    5) Prevents overlapping validity periods for same product.
    6) Enforces cess rules with specific cess amount support.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="gst_rates"
    )
    hsn = models.ForeignKey(
        HsnSac,
        on_delete=models.PROTECT,
        related_name="product_gst_rates"
    )

    gst_type = models.CharField(
        max_length=20,
        choices=GstType.choices,
        default=GstType.REGULAR
    )

    sgst = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    cgst = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    igst = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # total GST for convenience/reporting (computed)
    gst_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        help_text="Computed total GST rate (CGST+SGST)."
    )

    # CESS (%)
    cess = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    cess_type = models.CharField(
        max_length=20,
        choices=CessType.choices,
        default=CessType.NONE,
        help_text="Type of CESS (if any)."
    )

    # Specific cess amount per unit (SPECIFIC/COMPOSITE)
    cess_specific_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Specific CESS amount per unit (used when cess_type is specific or composite)."
    )

    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    isdefault = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "hsn", "valid_from"],
                name="uq_product_hsn_validfrom"
            ),
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(isdefault=True),
                name="uq_product_one_default_gst_rate"
            ),
        ]
        ordering = ["product", "valid_from"]

    def __str__(self):
        return f"{self.product} GST {self.gst_rate}% ({self.gst_type})"

    # --------------------
    # Helpers
    # --------------------
    @staticmethod
    def _d(v) -> Decimal:
        try:
            return Decimal(v or 0)
        except Exception:
            return Decimal("0")

    @staticmethod
    def _q2(v: Decimal) -> Decimal:
        return (v or Decimal("0")).quantize(Decimal("0.01"))

    # --------------------
    # Validation
    # --------------------
    def clean(self):
        errors = {}

        # date sanity
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            errors["valid_to"] = "valid_to cannot be before valid_from."

        # no overlapping validity periods for same product
        if self.product_id and self.valid_from:
            qs = ProductGstRate.objects.filter(product_id=self.product_id)
            if self.pk:
                qs = qs.exclude(pk=self.pk)

            A_from = self.valid_from
            A_to = self.valid_to

            cond2 = Q(valid_to__isnull=True) | Q(valid_to__gte=A_from)  # B_to open or >= A_from
            if A_to:
                cond1 = Q(valid_from__lte=A_to)  # B_from <= A_to
                overlap = qs.filter(cond2).filter(cond1)
            else:
                overlap = qs.filter(cond2)  # A open-ended: only need B_to open or >= A_from

            if overlap.exists():
                errors["valid_from"] = (
                    "Overlapping GST rate period exists for this product. "
                    "Adjust valid_from/valid_to."
                )

        sgst = self._q2(self._d(self.sgst))
        cgst = self._q2(self._d(self.cgst))
        igst = self._q2(self._d(self.igst))
        gst_rate = self._q2(self._d(self.gst_rate))
        cess = self._q2(self._d(self.cess))
        cess_specific = self._q2(self._d(self.cess_specific_amount))

        # gst_type enforcement
        if self.gst_type in (GstType.EXEMPT, GstType.NIL, GstType.NON_GST):
            if any(x != 0 for x in (sgst, cgst, igst, gst_rate, cess, cess_specific)):
                errors["gst_type"] = "For exempt/nil/non-gst items, all GST/CESS rates must be 0."

        # ✅ FINAL GST rule: IGST == CGST + SGST (for taxable types)
        if self.gst_type not in (GstType.EXEMPT, GstType.NIL, GstType.NON_GST):
            expected_total = self._q2(sgst + cgst)

            if igst != expected_total:
                errors["igst"] = f"IGST must be equal to CGST+SGST ({expected_total})."

            # optional strictness: gst_rate must also equal total
            if gst_rate != expected_total:
                errors["gst_rate"] = f"gst_rate must be equal to CGST+SGST ({expected_total})."

        # cess_type enforcement
        if self.cess_type == "CessType".NONE:
            if cess != 0 or (self.cess_specific_amount not in (None, Decimal("0"), 0)):
                errors["cess_type"] = "cess_type=NONE requires cess and cess_specific_amount to be 0/blank."
        elif self.cess_type == "CessType".AD_VALOREM:
            if cess <= 0:
                errors["cess"] = "For ad valorem cess, cess (%) must be > 0."
            if self.cess_specific_amount not in (None, Decimal("0"), 0):
                errors["cess_specific_amount"] = "For ad valorem cess, cess_specific_amount should be blank/0."
        elif self.cess_type == "CessType".SPECIFIC:
            if self.cess_specific_amount is None or cess_specific <= 0:
                errors["cess_specific_amount"] = "For specific cess, cess_specific_amount per unit must be > 0."
            if cess != 0:
                errors["cess"] = "For specific cess, cess (%) should be 0."
        elif self.cess_type == "CessType".COMPOSITE:
            if cess <= 0:
                errors["cess"] = "For composite cess, cess (%) must be > 0."
            if self.cess_specific_amount is None or cess_specific <= 0:
                errors["cess_specific_amount"] = "For composite cess, cess_specific_amount per unit must be > 0."

        # soft check: product.is_service vs hsn.is_service (kept non-blocking)
        # if self.product_id and self.hsn_id and self.product.is_service != self.hsn.is_service:
        #     pass

        if errors:
            raise ValidationError(errors)

    # --------------------
    # Save normalization
    # --------------------
    def save(self, *args, **kwargs):
        # validate first
        self.full_clean()

        # normalize taxable vs non-taxable
        if self.gst_type in (GstType.EXEMPT, GstType.NIL, GstType.NON_GST):
            self.sgst = Decimal("0.00")
            self.cgst = Decimal("0.00")
            self.igst = Decimal("0.00")
            self.gst_rate = Decimal("0.00")
            self.cess = Decimal("0.00")
            self.cess_specific_amount = None
            self.cess_type = "CessType".NONE
        else:
            total = self._q2(Decimal(self.sgst or 0) + Decimal(self.cgst or 0))
            # enforce your final storage rule: keep igst and gst_rate equal to total
            self.igst = total
            self.gst_rate = total

        super().save(*args, **kwargs)


# ----------------------------------------------------------------------
# Identification / attributes / images
# ----------------------------------------------------------------------

class ProductBarcode(TimeStampedModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='barcode_details'
    )

    # Auto-generated; do NOT send from frontend
    barcode = models.CharField(max_length=50, blank=True)

    uom = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name='barcode_uoms'
    )
    isprimary = models.BooleanField(default=False)
    pack_size = models.PositiveIntegerField(null=True, blank=True)

    mrp = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.00"))]
    )
    selling_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.00"))]
    )

    barcode_image = models.ImageField(
        upload_to='barcodes/',
        blank=True,
        null=True,
        help_text="Auto-generated barcode image",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'barcode'],
                name='uq_product_barcode'
            ),
            models.UniqueConstraint(
                fields=['product', 'uom', 'pack_size'],
                name='uq_product_uom_packsize'
            ),
            # ✅ NEW: only one primary barcode per product
            models.UniqueConstraint(
                fields=['product'],
                condition=Q(isprimary=True),
                name='uq_product_one_primary_barcode'
            ),
        ]

    def __str__(self):
        return self.barcode or f"Barcode for {self.product_id}"

    def clean(self):
        if not self.pack_size:
            self.pack_size = 1

        if self.mrp is not None and self.selling_price is not None:
            if self.selling_price > self.mrp:
                raise ValidationError({"selling_price": "Selling price cannot be greater than MRP."})

    def _generate_barcode_value(self):
        product_id = self.product_id or 0
        self_id = self.pk or 0
        return f"PRD-{product_id:06d}-{self_id:06d}"

    def _generate_barcode_image(self):
        if Code128 is None or ImageWriter is None:
            return
        if not self.barcode:
            return

        buffer = BytesIO()
        barcode_obj = Code128(self.barcode, writer=ImageWriter())
        barcode_obj.write(buffer)
        buffer.seek(0)

        base_img = Image.open(buffer).convert("RGB")

        product_name = (self.product.productname or "").strip()
        sku = (getattr(self.product, "sku", "") or "").strip()
        uom_code = (getattr(self.uom, "code", "") or "").strip()
        pack = self.pack_size or 1

        if len(product_name) > 40:
            product_name = product_name[:37] + "..."

        price_part = ""
        if self.mrp is not None:
            price_part += f" | MRP: {self.mrp:.2f}"
        if self.selling_price is not None:
            price_part += f" | SP: {self.selling_price:.2f}"

        text = f"Product: {product_name} | SKU: {sku} | UOM: {uom_code} | Pack: {pack}{price_part}"

        font = ImageFont.load_default()
        dummy_draw = ImageDraw.Draw(base_img)

        if hasattr(dummy_draw, "textbbox"):
            bbox = dummy_draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        else:
            text_width, text_height = dummy_draw.textsize(text, font=font)

        padding = 10
        extra_height = text_height + 2 * padding
        new_width = max(base_img.width, text_width + 2 * padding)
        new_height = base_img.height + extra_height

        new_img = Image.new("RGB", (new_width, new_height), "white")
        draw = ImageDraw.Draw(new_img)

        barcode_x = (new_width - base_img.width) // 2
        new_img.paste(base_img, (barcode_x, 0))

        text_x = (new_width - text_width) // 2
        text_y = base_img.height + padding
        draw.text((text_x, text_y), text, fill="black", font=font)

        final_buffer = BytesIO()
        new_img.save(final_buffer, format="PNG")
        final_buffer.seek(0)

        filename = f"barcode_{self.pk}.png"
        self.barcode_image.save(filename, ContentFile(final_buffer.getvalue()), save=False)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

        updated_fields = []

        if not self.barcode:
            self.barcode = self._generate_barcode_value()
            updated_fields.append('barcode')

        if not self.barcode_image and self.barcode:
            self._generate_barcode_image()
            updated_fields.append('barcode_image')

        if updated_fields:
            super().save(update_fields=updated_fields)


@receiver(post_save, sender=Product)
def create_default_barcode_for_product(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.base_uom and not instance.barcode_details.exists():
        ProductBarcode.objects.create(
            product=instance,
            uom=instance.base_uom,
            isprimary=True,
            pack_size=1,
        )


class ProductUomConversion(TimeStampedModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='uom_conversions'
    )
    from_uom = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name='from_conversions'
    )
    to_uom = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name='to_conversions'
    )
    factor = models.DecimalField(max_digits=12, decimal_places=4)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'from_uom', 'to_uom'],
                name='uq_product_uomconversion'
            )
        ]

    def __str__(self):
        return f"{self.product} {self.from_uom} -> {self.to_uom} ({self.factor})"


class ProductAttribute(EntityScopedModel):
    DATA_TYPE_CHOICES = (
        ('char', 'Text'),
        ('number', 'Number'),
        ('date', 'Date'),
        ('bool', 'Boolean'),
    )

    name = models.CharField(max_length=100)
    data_type = models.CharField(max_length=20, choices=DATA_TYPE_CHOICES)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['entity', 'name'],
                name='uq_productattribute_entity_name'
            )
        ]

    def __str__(self):
        return self.name


class ProductAttributeValue(TimeStampedModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='attributes'
    )
    attribute = models.ForeignKey(
        ProductAttribute,
        on_delete=models.PROTECT,
        related_name='values'
    )

    value_char = models.CharField(max_length=255, blank=True)
    value_number = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True
    )
    value_date = models.DateField(null=True, blank=True)
    value_bool = models.BooleanField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'attribute'],
                name='uq_product_attribute'
            )
        ]

    def __str__(self):
        return f"{self.product} - {self.attribute}"


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_primary = models.BooleanField(default=False)
    caption = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            # ✅ NEW: only one primary image per product (optional but clean)
            models.UniqueConstraint(
                fields=['product'],
                condition=Q(is_primary=True),
                name='uq_product_one_primary_image'
            )
        ]

    def __str__(self):
        return f"Image for {self.product}"


# ----------------------------------------------------------------------
# Opening stock
# ----------------------------------------------------------------------

class OpeningStockByLocation(TimeStampedModel):
    entity = models.ForeignKey(
        Entity,
        on_delete=models.PROTECT,
        related_name='catalog_opening_stocks',
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='opening_stocks'
    )
    location = models.ForeignKey(
        subentity,
        on_delete=models.PROTECT,
        related_name='opening_stocks'
    )
    openingqty = models.DecimalField(max_digits=18, decimal_places=2)
    openingrate = models.DecimalField(max_digits=18, decimal_places=2)
    openingvalue = models.DecimalField(max_digits=18, decimal_places=2)
    as_of_date = models.DateField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['entity', 'product', 'location', 'as_of_date'],
                name='uq_openingstock_entity_product_location_date'
            )
        ]

    def __str__(self):
        return f"Opening {self.product} @ {self.location} ({self.as_of_date})"

    def save(self, *args, **kwargs):
        if self.product_id and self.entity_id is None:
            self.entity_id = self.product.entity_id
        super().save(*args, **kwargs)


# ----------------------------------------------------------------------
# Pricing
# ----------------------------------------------------------------------

class PriceList(EntityScopedModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    isdefault = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['entity', 'name'],
                name='uq_pricelist_entity_name'
            ),
            # ✅ NEW: only one default pricelist per entity
            models.UniqueConstraint(
                fields=['entity'],
                condition=Q(isdefault=True),
                name='uq_pricelist_one_default_per_entity'
            ),
        ]
        ordering = ['name']

    def __str__(self):
        return self.name


class ProductPrice(TimeStampedModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='prices'
    )
    pricelist = models.ForeignKey(
        PriceList,
        on_delete=models.PROTECT,
        related_name='prices'
    )
    uom = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name='product_prices'
    )

    purchase_rate = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Base purchase rate"
    )
    purchase_rate_less_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Discount % on purchase rate"
    )

    mrp = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True
    )
    mrp_less_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Discount % on MRP"
    )

    selling_price = models.DecimalField(max_digits=18, decimal_places=2)

    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'pricelist', 'uom', 'effective_from'],
                name='uq_productprice_key'
            )
        ]
        ordering = ['product', 'pricelist', 'uom', 'effective_from']

    def __str__(self):
        return f"{self.product} @ {self.pricelist} ({self.uom})"

    def clean(self):
        errors = {}
        if self.effective_to and self.effective_to < self.effective_from:
            errors["effective_to"] = "effective_to cannot be before effective_from."
        if errors:
            raise ValidationError(errors)


# ----------------------------------------------------------------------
# Planning / replenishment
# ----------------------------------------------------------------------

class ProductPlanning(TimeStampedModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='planning'
    )

    min_stock = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    max_stock = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    reorder_level = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    reorder_qty = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    lead_time_days = models.IntegerField(null=True, blank=True)

    abc_class = models.CharField(max_length=1, blank=True)  # 'A', 'B', 'C'
    fsn_class = models.CharField(max_length=1, blank=True)  # 'F', 'S', 'N'

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product'],
                name='uq_productplanning_product'
            )
        ]

    def __str__(self):
        return f"Planning for {self.product}"
