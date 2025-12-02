# catalog/models.py

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from entity.models import Entity, subentity, entityfinancialyear
from financial.models import account


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


class Product(EntityScopedModel):
    PRODUCT_STATUS_CHOICES = (
        ('active', 'Active'),
        ('discontinued', 'Discontinued'),
        ('blocked', 'Blocked'),
        ('upcoming', 'Upcoming'),
    )

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

    is_service = models.BooleanField(default=False)
    is_batch_managed = models.BooleanField(default=False)
    is_serialized = models.BooleanField(default=False)
    is_ecomm_9_5_service = models.BooleanField(default=False)  # for section 9(5) cases

    product_status = models.CharField(
        max_length=20,
        choices=PRODUCT_STATUS_CHOICES,
        default='active'
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
        max_length=50,
        blank=True,
        help_text="Optional CESS type (e.g. Ad valorem, Specific)"
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
    barcode = models.CharField(max_length=50)
    uom = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name='barcode_uoms'
    )
    isprimary = models.BooleanField(default=False)
    pack_size = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'barcode'],
                name='uq_product_barcode'
            )
        ]

    def __str__(self):
        return self.barcode


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
