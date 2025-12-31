# catalog/serializers.py

from rest_framework import serializers
from django.db import transaction

from .models import (
    ProductCategory,
    Brand,
    UnitOfMeasure,
    Product,
    HsnSac,
    ProductGstRate,
    ProductBarcode,
    ProductUomConversion,
    ProductAttribute,
    ProductAttributeValue,
    ProductImage,
    OpeningStockByLocation,
    PriceList,
    ProductPrice,
    ProductPlanning,
)


# ----------------------------------------------------------------------
# Simple master serializers (for dropdowns / lookups)
# ----------------------------------------------------------------------

class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = (
            "id",
            "entity",
            "pcategoryname",
            "maincategory",
            "level",
            "isactive",
        )


# catalog/serializers.py

class ProductCategorySerializercreate(serializers.ModelSerializer):
    # write: accept parent id
    maincategory_id = serializers.PrimaryKeyRelatedField(
        source="maincategory",
        queryset=ProductCategory.objects.all(),
        required=False,
        allow_null=True
    )

    # read: return parent name (always show key, null if no parent)
    maincategory_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ProductCategory
        fields = [
            "id",
            "entity",
            "pcategoryname",
            "maincategory_id",
            "maincategory_name",
            "level",
            "isactive",
        ]
        extra_kwargs = {
            "entity": {"read_only": True},
            "level": {"read_only": True},
        }

    def get_maincategory_name(self, obj):
        return obj.maincategory.pcategoryname if obj.maincategory else None

    def validate(self, attrs):
        entity = self.context.get("entity")
        parent = attrs.get("maincategory")

        # Parent must be same entity
        if parent and entity and parent.entity_id != entity.id:
            raise serializers.ValidationError({
                "maincategory_id": "Parent category must belong to the same entity."
            })

        # auto-level
        attrs["level"] = (parent.level or 1) + 1 if parent else 1
        return attrs



class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = (
            "id",
            "entity",
            "name",
            "description",
            "isactive",
        )


class UnitOfMeasureSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitOfMeasure
        fields = (
            "id",
            "entity",
            "code",
            "description",
            "isactive",
        )


class HsnSacSerializer(serializers.ModelSerializer):
    class Meta:
        model = HsnSac
        fields = (
            "id",
            "entity",
            "code",
            "description",
            "is_service",
            "default_sgst",
            "default_cgst",
            "default_igst",
            "default_cess",
            "is_exempt",
            "is_nil_rated",
            "is_non_gst",
            "isactive",
        )


class PriceListSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceList
        fields = (
            "id",
            "entity",
            "name",
            "description",
            "isdefault",
            "isactive",
        )


# ----------------------------------------------------------------------
# Nested child serializers
# ----------------------------------------------------------------------

class ProductGstRateSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = ProductGstRate
        fields = (
            "id",
            "product",      # parent sets
            "hsn",
            "gst_type",
            "sgst",
            "cgst",
            "igst",
            "gst_rate",
            "cess",
            "cess_type",
            "valid_from",
            "valid_to",
            "isdefault",
            "createdon",
            "modifiedon",
        )
        read_only_fields = ("product", "createdon", "modifiedon")


class ProductBarcodeSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    barcode_image_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ProductBarcode
        fields = (
            "id",
            "product",            # parent sets
            "barcode",            # auto-generated, read-only
            "uom",
            "isprimary",
            "pack_size",

            # ✅ NEW
            "mrp",
            "selling_price",

            "barcode_image_url",
            "createdon",
            "modifiedon",
        )
        read_only_fields = (
            "product",
            "barcode",
            "barcode_image_url",
            "createdon",
            "modifiedon",
        )

    def get_barcode_image_url(self, obj):
        request = self.context.get("request")
        if obj.barcode_image and hasattr(obj.barcode_image, "url"):
            return request.build_absolute_uri(obj.barcode_image.url) if request else obj.barcode_image.url
        return None

    def validate(self, attrs):
        # default pack_size if not provided
        pack_size = attrs.get("pack_size", None)
        if pack_size in (None, 0, "0", ""):
            attrs["pack_size"] = 1

        mrp = attrs.get("mrp", None)
        sp = attrs.get("selling_price", None)

        # optional: SP <= MRP
        if mrp is not None and sp is not None and sp > mrp:
            raise serializers.ValidationError({"selling_price": "Selling price cannot be greater than MRP."})

        return attrs




class ProductUomConversionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = ProductUomConversion
        fields = (
            "id",
            "product",   # parent sets
            "from_uom",
            "to_uom",
            "factor",
            "createdon",
            "modifiedon",
        )
        read_only_fields = ("product", "createdon", "modifiedon")


class OpeningStockByLocationSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = OpeningStockByLocation
        fields = (
            "id",
            "entity",     # will be derived from product in model.save
            "product",    # parent sets
            "location",
            "openingqty",
            "openingrate",
            "openingvalue",
            "as_of_date",
            "createdon",
            "modifiedon",
        )
        read_only_fields = ("product", "entity", "createdon", "modifiedon")


class ProductPriceSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = ProductPrice
        fields = (
            "id",
            "product",      # parent sets
            "pricelist",
            "uom",
            "purchase_rate",
            "purchase_rate_less_percent",
            "mrp",
            "mrp_less_percent",
            "selling_price",
            "effective_from",
            "effective_to",
            "createdon",
            "modifiedon",
        )
        read_only_fields = ("product", "createdon", "modifiedon")


class ProductPlanningSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = ProductPlanning
        fields = (
            "id",
            "product",  # parent sets
            "min_stock",
            "max_stock",
            "reorder_level",
            "reorder_qty",
            "lead_time_days",
            "abc_class",
            "fsn_class",
            "createdon",
            "modifiedon",
        )
        read_only_fields = ("product", "createdon", "modifiedon")


# Attribute & Image nested serializers

class ProductAttributeValueSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = ProductAttributeValue
        fields = (
            "id",
            "product",      # parent sets
            "attribute",
            "value_char",
            "value_number",
            "value_date",
            "value_bool",
            "createdon",
            "modifiedon",
        )
        read_only_fields = ("product", "createdon", "modifiedon")


class ProductImageNestedSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = ProductImage
        fields = (
            "id",
            "product",  # parent sets
            "image",
            "is_primary",
            "caption",
            "createdon",
            "modifiedon",
        )
        read_only_fields = ("product", "createdon", "modifiedon")


# ----------------------------------------------------------------------
# Main Product serializer with nested create/update
# ----------------------------------------------------------------------

class ProductSerializer(serializers.ModelSerializer):
    """
    Nested serializer for Product with:
      - gst_rates
      - barcodes
      - uom_conversions
      - opening_stocks
      - prices
      - planning (1:1 via unique constraint)
      - attributes
      - images
    """

    gst_rates = ProductGstRateSerializer(many=True, required=False)

    # Name != related_name → we use source
    barcodes = ProductBarcodeSerializer(
        many=True,
        required=False,
        source="barcode_details",
    )

    # related_name == field name → no source
    uom_conversions = ProductUomConversionSerializer(
        many=True,
        required=False,
    )

    opening_stocks = OpeningStockByLocationSerializer(many=True, required=False)
    prices = ProductPriceSerializer(many=True, required=False)
    planning = ProductPlanningSerializer(required=False, allow_null=True)
    attributes = ProductAttributeValueSerializer(many=True, required=False)
    images = ProductImageNestedSerializer(many=True, required=False)

    class Meta:
        model = Product
        fields = (
            # product core
            "id",
            "entity",
            "productname",
            "sku",
            "productdesc",
            "productcategory",
            "brand",
            "base_uom",
            "sales_account",
            "purchase_account",
            "is_service",
            "is_batch_managed",
            "is_serialized",
            "is_ecomm_9_5_service",
            "product_status",
            "launch_date",
            "discontinue_date",
            "isactive",
            "createdon",
            "modifiedon",

            # nested
            "gst_rates",
            "barcodes",
            "uom_conversions",
            "opening_stocks",
            "prices",
            "planning",
            "attributes",
            "images",
        )
        read_only_fields = ("createdon", "modifiedon")

    # -------------------- generic helper --------------------

    def _upsert_child_list(self, *, parent_instance, child_model,
                           child_data_list, fk_name, existing_qs):
        """
        Generic helper for 1:M nested lists:
        - update existing by id (id > 0)
        - create new when id is missing or <= 0
        - delete missing ones
        """
        sent_ids = []

        for item_data in child_data_list:
            raw_id = item_data.get("id", None)
            # id <= 0 or None should be treated as "no id"
            item_id = raw_id if raw_id not in (None, 0, "0") else None

            # do not allow client to override product/entity directly
            item_data.pop("product", None)
            item_data.pop("entity", None)

            item_data.pop("barcode", None)
            item_data.pop("barcode_image", None)

            if item_id:
                # UPDATE EXISTING
                try:
                    child_obj = existing_qs.get(id=item_id)
                except child_model.DoesNotExist:
                    # treat as new if id not found
                    item_data.pop("id", None)
                    child_obj = child_model.objects.create(
                        **item_data,
                        **{fk_name: parent_instance},
                    )
                else:
                    # normal update
                    for attr, value in item_data.items():
                        if attr != "id":
                            setattr(child_obj, attr, value)
                    child_obj.save()
                sent_ids.append(child_obj.id)
            else:
                # NEW ROW: make sure we don't pass id=0
                item_data.pop("id", None)
                child_obj = child_model.objects.create(
                    **item_data,
                    **{fk_name: parent_instance},
                )
                sent_ids.append(child_obj.id)

        # delete records not sent in payload
        if sent_ids:
            existing_qs.exclude(id__in=sent_ids).delete()
        else:
            existing_qs.delete()

    # -------------------- create & update --------------------

    @transaction.atomic
    def create(self, validated_data):
        # keys: for "barcodes" we use source="barcode_details"
        gst_rates_data = validated_data.pop("gst_rates", [])
        barcodes_data = validated_data.pop("barcode_details", [])
        uom_conversions_data = validated_data.pop("uom_conversions", [])
        opening_stocks_data = validated_data.pop("opening_stocks", [])
        prices_data = validated_data.pop("prices", [])
        planning_data = validated_data.pop("planning", None)
        attributes_data = validated_data.pop("attributes", [])
        images_data = validated_data.pop("images", [])

        # ---- strip id from all nested data (id=0 / any id) ----
        for lst in (
            gst_rates_data,
            barcodes_data,
            uom_conversions_data,
            opening_stocks_data,
            prices_data,
            attributes_data,
            images_data,
        ):
            for item in lst:
                item.pop("id", None)

        # Create product
        product = Product.objects.create(**validated_data)

        # GST Rates
        for gr in gst_rates_data:
            ProductGstRate.objects.create(product=product, **gr)

        # Barcodes
        for bd in barcodes_data:
            bd.pop("barcode", None)
            bd.pop("barcode_image", None)
            ProductBarcode.objects.create(product=product, **bd)

        # UOM conversions
        for uc in uom_conversions_data:
            ProductUomConversion.objects.create(product=product, **uc)

        # Opening stocks (entity can be set by model save, but we set explicitly)
        for os in opening_stocks_data:
            OpeningStockByLocation.objects.create(
                product=product,
                entity=product.entity,
                **os,
            )

        # Prices
        for pr in prices_data:
            ProductPrice.objects.create(product=product, **pr)

        # Planning (1:1)
        if planning_data:
            # if planning_data has an id=0/malformed, strip it
            planning_data.pop("id", None)
            ProductPlanning.objects.create(product=product, **planning_data)

        # Attributes
        for av in attributes_data:
            ProductAttributeValue.objects.create(product=product, **av)

        # Images
        for img in images_data:
            ProductImage.objects.create(product=product, **img)

        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        gst_rates_data = validated_data.pop("gst_rates", None)
        barcodes_data = validated_data.pop("barcode_details", None)
        uom_conversions_data = validated_data.pop("uom_conversions", None)
        opening_stocks_data = validated_data.pop("opening_stocks", None)
        prices_data = validated_data.pop("prices", None)
        planning_data = validated_data.pop("planning", None)
        attributes_data = validated_data.pop("attributes", None)
        images_data = validated_data.pop("images", None)

        # update core product fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # nested lists (only if key present in payload)
        if gst_rates_data is not None:
            self._upsert_child_list(
                parent_instance=instance,
                child_model=ProductGstRate,
                child_data_list=gst_rates_data,
                fk_name="product",
                existing_qs=instance.gst_rates.all(),
            )

        if barcodes_data is not None:
            self._upsert_child_list(
                parent_instance=instance,
                child_model=ProductBarcode,
                child_data_list=barcodes_data,
                fk_name="product",
                existing_qs=instance.barcode_details.all(),
            )

        if uom_conversions_data is not None:
            self._upsert_child_list(
                parent_instance=instance,
                child_model=ProductUomConversion,
                child_data_list=uom_conversions_data,
                fk_name="product",
                existing_qs=instance.uom_conversions.all(),
            )

        if opening_stocks_data is not None:
            # strip entity from client; model will derive from product if needed
            for os in opening_stocks_data:
                os.pop("entity", None)

            self._upsert_child_list(
                parent_instance=instance,
                child_model=OpeningStockByLocation,
                child_data_list=opening_stocks_data,
                fk_name="product",
                existing_qs=instance.opening_stocks.all(),
            )

        if prices_data is not None:
            self._upsert_child_list(
                parent_instance=instance,
                child_model=ProductPrice,
                child_data_list=prices_data,
                fk_name="product",
                existing_qs=instance.prices.all(),
            )

        # planning 1:1 via unique constraint on product
        if planning_data is not None:
            # id=0 should be treated as new
            planning_data.pop("id", None)

            existing_planning_obj = (
                instance.planning.first()
                if hasattr(instance, "planning")
                else None
            )
            if existing_planning_obj:
                for attr, value in planning_data.items():
                    if attr != "id":
                        setattr(existing_planning_obj, attr, value)
                existing_planning_obj.save()
            elif planning_data:
                ProductPlanning.objects.create(product=instance, **planning_data)

        if attributes_data is not None:
            self._upsert_child_list(
                parent_instance=instance,
                child_model=ProductAttributeValue,
                child_data_list=attributes_data,
                fk_name="product",
                existing_qs=instance.attributes.all(),
            )

        if images_data is not None:
            self._upsert_child_list(
                parent_instance=instance,
                child_model=ProductImage,
                child_data_list=images_data,
                fk_name="product",
                existing_qs=instance.images.all(),
            )

        return instance

    

class GstTypeChoiceSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class CessTypeChoiceSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class ProductStatusChoiceSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()



class ProductBarcodeManageSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source="product.id", read_only=True)
    product_name = serializers.CharField(source="product.productname", read_only=True)
    sku = serializers.CharField(source="product.sku", read_only=True)

    uom_code = serializers.CharField(source="uom.code", read_only=True)
    barcode_image_url = serializers.SerializerMethodField(read_only=True)

    createdon = serializers.DateTimeField(read_only=True)
    modifiedon = serializers.DateTimeField(read_only=True)

    class Meta:
        model = ProductBarcode
        fields = [
            "id",
            "product_id",
            "product_name",
            "sku",
            "barcode",

            "uom",
            "uom_code",
            "pack_size",
            "isprimary",

            # ✅ NEW
            "mrp",
            "selling_price",

            "barcode_image",
            "barcode_image_url",

            "createdon",
            "modifiedon",
        ]
        read_only_fields = [
            "barcode",
            "barcode_image",
            "barcode_image_url",
            "product_id",
            "product_name",
            "sku",
            "uom_code",
            "createdon",
            "modifiedon",
        ]

    def get_barcode_image_url(self, obj):
        request = self.context.get("request")
        if not obj.barcode_image:
            return None
        url = obj.barcode_image.url
        return request.build_absolute_uri(url) if request else url

    def validate(self, attrs):
        # default pack_size if not provided
        pack_size = attrs.get("pack_size", None)
        if pack_size in (None, 0, "0", ""):
            attrs["pack_size"] = 1

        mrp = attrs.get("mrp", None)
        sp = attrs.get("selling_price", None)
        if mrp is not None and sp is not None and sp > mrp:
            raise serializers.ValidationError({"selling_price": "Selling price cannot be greater than MRP."})

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        product = self.context["product"]
        validated_data["product"] = product

        obj = super().create(validated_data)

        if obj.isprimary:
            ProductBarcode.objects.filter(product=product).exclude(pk=obj.pk).update(isprimary=False)

        return obj

    @transaction.atomic
    def update(self, instance, validated_data):
        obj = super().update(instance, validated_data)

        if obj.isprimary:
            ProductBarcode.objects.filter(product=obj.product).exclude(pk=obj.pk).update(isprimary=False)

        return obj

