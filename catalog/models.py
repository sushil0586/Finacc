# catalog/models.py

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal

from entity.models import Entity, subentity, entityfinancialyear
from financial.models import account

from io import BytesIO
from django.core.files.base import ContentFile
from django.db.models.signals import post_save
from django.dispatch import receiver

from PIL import Image, ImageDraw, ImageFont  # ⬅️ NEW

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
        # Unique reverse name per class in catalog app
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
    code = models.CharField(max_length=20)
    description = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['entity', 'code'],
                name='uq_uom_entity_code'
            )
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

    is_service = models.BooleanField(default=False)
    is_batch_managed = models.BooleanField(default=False)
    is_serialized = models.BooleanField(default=False)
    is_ecomm_9_5_service = models.BooleanField(default=False)  # for section 9(5) cases

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
    GST rate for a product, with validity period and type.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='gst_rates'
    )
    hsn = models.ForeignKey(
        HsnSac,
        on_delete=models.PROTECT,
        related_name='product_gst_rates'
    )

    # GST type (regular, exempt, nil, non-gst, composition)
    gst_type = models.CharField(
        max_length=20,
        choices=GstType.choices,
        default=GstType.REGULAR
    )

    # component rates
    sgst = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    cgst = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    igst = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # combined GST rate (CGST+SGST or IGST)
    gst_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        help_text="Total GST rate (CGST+SGST or IGST)"
    )

    # CESS
    cess = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    cess_type = models.CharField(
        max_length=20,
        choices=CessType.choices,
        default=CessType.NONE,
        help_text="Type of CESS (if any)",
    )

    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    isdefault = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'hsn', 'valid_from'],
                name='uq_product_hsn_validfrom'
            )
        ]
        ordering = ['product', 'valid_from']

    def __str__(self):
        return f"{self.product} GST {self.gst_rate}% ({self.gst_type})"


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

    # ✅ NEW: prices per UOM+pack_size barcode
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

    # Auto-generated barcode image
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
            # ✅ NEW: one row per product+uom+pack_size (prevents duplicate 250g entries)
            models.UniqueConstraint(
                fields=['product', 'uom', 'pack_size'],
                name='uq_product_uom_packsize'
            ),
        ]

    def __str__(self):
        return self.barcode or f"Barcode for {self.product_id}"

    def clean(self):
        # normalize pack_size
        if not self.pack_size:
            self.pack_size = 1

        # optional rule: SP cannot exceed MRP
        if self.mrp is not None and self.selling_price is not None:
            if self.selling_price > self.mrp:
                raise ValidationError({"selling_price": "Selling price cannot be greater than MRP."})

    def _generate_barcode_value(self):
        product_id = self.product_id or 0
        self_id = self.pk or 0
        return f"PRD-{product_id:06d}-{self_id:06d}"

    def _generate_barcode_image(self):
        """
        Generate barcode image + overlay key product info as text
        (Product name, SKU, UOM, Pack size, MRP, Selling price) at the bottom.
        """
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

        # ✅ include prices (only if present)
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
        # ✅ run validations + default pack_size
        self.full_clean()

        super().save(*args, **kwargs)

        updated_fields = []

        if not self.barcode:
            self.barcode = self._generate_barcode_value()
            updated_fields.append('barcode')

        # ✅ regenerate image if missing OR price changed and you want updated sticker
        # (simple approach: regenerate only if missing)
        if not self.barcode_image and self.barcode:
            self._generate_barcode_image()
            updated_fields.append('barcode_image')

        if updated_fields:
            super().save(update_fields=updated_fields)



@receiver(post_save, sender=Product)
def create_default_barcode_for_product(sender, instance, created, **kwargs):
    """
    When a Product is created:
    - If it has a base_uom
    - And no barcode exists yet
    → create one primary barcode automatically.
    """
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
        # auto-derive entity from product if missing
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
            )
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

    # purchase side
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

    # MRP side
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

    # selling price
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
