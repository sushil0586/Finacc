# catalog/serializers.py  (UPDATED AS PER NEW MODELS)
# Changes made:
# - UnitOfMeasureSerializer: added `uqc`
# - ProductSerializer: added `default_is_rcm`, `is_itc_eligible`
# - ProductGstRateSerializer: added `cess_specific_amount`
# - ProductGstRateSerializer: gst_rate read-only (computed in model.save) to avoid mismatch bugs
# - ProductGstRateSerializer: added validations aligned with model (cess_type rules, zero-tax types)
# - ProductBarcodeSerializer: no change needed except it must respect "one primary" constraint;
#   we enforce in serializer create/update as a friendly behavior (optional but recommended)
# - ProductBarcodeManageSerializer: unchanged fields, but kept primary enforcement
# Note: Your model constraints will enforce correctness even if serializer misses.

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
    GstType,
    CessType,
    ProductStatus,
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


class ProductCategorySerializercreate(serializers.ModelSerializer):
    maincategory_id = serializers.PrimaryKeyRelatedField(
        source="maincategory",
        queryset=ProductCategory.objects.all(),
        required=False,
        allow_null=True
    )
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

        if parent and entity and parent.entity_id != entity.id:
            raise serializers.ValidationError({
                "maincategory_id": "Parent category must belong to the same entity."
            })

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
            "uqc",        # ✅ NEW
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
    """
    Aligns with new model:
    - includes cess_specific_amount
    - gst_rate is safer as read-only because model.save() derives it
    - adds validations mirroring model clean() (gives nicer API errors)
    """
    id = serializers.IntegerField(required=False)

    class Meta:
        model = ProductGstRate
        fields = (
            "id",
            "product",      # parent sets (read-only)
            "hsn",
            "gst_type",
            "sgst",
            "cgst",
            "igst",
            "gst_rate",                 # derived by model
            "cess",
            "cess_type",
            "cess_specific_amount",     # ✅ NEW
            "valid_from",
            "valid_to",
            "isdefault",
            "createdon",
            "modifiedon",
        )
        read_only_fields = ("product", "gst_rate", "createdon", "modifiedon")

    def validate(self, attrs):
        # validate dates
        vf = attrs.get("valid_from")
        vt = attrs.get("valid_to")
        if vf and vt and vt < vf:
            raise serializers.ValidationError({"valid_to": "valid_to cannot be before valid_from."})

        gst_type = attrs.get("gst_type", None)
        cess_type = attrs.get("cess_type", None)

        sgst = attrs.get("sgst", None) or 0
        cgst = attrs.get("cgst", None) or 0
        igst = attrs.get("igst", None) or 0
        cess = attrs.get("cess", None) or 0
        cess_specific = attrs.get("cess_specific_amount", None)

        # zero tax for exempt/nil/non-gst
        if gst_type in (GstType.EXEMPT, GstType.NIL, GstType.NON_GST):
            if any([
                float(sgst) != 0,
                float(cgst) != 0,
                float(igst) != 0,
                float(cess) != 0,
                (cess_specific not in (None, 0, 0.0)),
            ]):
                raise serializers.ValidationError({
                    "gst_type": "For exempt/nil/non-gst items, all GST/CESS values must be zero/blank."
                })

        # cess_type rules
        if cess_type == CessType.NONE:
            if float(cess) != 0 or (cess_specific not in (None, 0, 0.0)):
                raise serializers.ValidationError({
                    "cess_type": "cess_type=NONE requires cess and cess_specific_amount to be 0/blank."
                })
        elif cess_type == CessType.AD_VALOREM:
            if float(cess) <= 0:
                raise serializers.ValidationError({"cess": "For ad valorem cess, cess (%) must be > 0."})
            if cess_specific not in (None, 0, 0.0):
                raise serializers.ValidationError({"cess_specific_amount": "For ad valorem cess, cess_specific_amount must be blank/0."})
        elif cess_type == CessType.SPECIFIC:
            if cess_specific in (None, 0, 0.0):
                raise serializers.ValidationError({"cess_specific_amount": "For specific cess, cess_specific_amount per unit must be > 0."})
            if float(cess) != 0:
                raise serializers.ValidationError({"cess": "For specific cess, cess (%) must be 0."})
        elif cess_type == CessType.COMPOSITE:
            if float(cess) <= 0:
                raise serializers.ValidationError({"cess": "For composite cess, cess (%) must be > 0."})
            if cess_specific in (None, 0, 0.0):
                raise serializers.ValidationError({"cess_specific_amount": "For composite cess, cess_specific_amount per unit must be > 0."})

        # prevent IGST + CGST/SGST combo (friendly check)
        if float(igst) > 0 and (float(sgst) + float(cgst)) > 0:
            raise serializers.ValidationError({
                "igst": "When IGST is used, SGST/CGST should typically be 0."
            })

        return attrs


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
        pack_size = attrs.get("pack_size", None)
        if pack_size in (None, 0, "0", ""):
            attrs["pack_size"] = 1

        mrp = attrs.get("mrp", None)
        sp = attrs.get("selling_price", None)
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
            "entity",     # derived from product in model.save
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
    gst_rates = ProductGstRateSerializer(many=True, required=False)

    barcodes = ProductBarcodeSerializer(
        many=True,
        required=False,
        source="barcode_details",
    )

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

            "default_is_rcm",     # ✅ NEW
            "is_itc_eligible",    # ✅ NEW

            "product_status",
            "launch_date",
            "discontinue_date",
            "isactive",
            "createdon",
            "modifiedon",

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
                          child_data_list, fk_name, existing_qs,
                          strip_fields=None):
        """
        Generic helper for 1:M nested lists:
        - update existing by id (id > 0)
        - create new when id is missing or <= 0
        - delete missing ones
        """
        strip_fields = set(strip_fields or [])
        sent_ids = []

        for item_data in child_data_list:
            raw_id = item_data.get("id", None)
            item_id = raw_id if raw_id not in (None, 0, "0") else None

            # do not allow client to override parent fk/entity
            item_data.pop("product", None)
            item_data.pop("entity", None)

            for f in strip_fields:
                item_data.pop(f, None)

            if item_id:
                try:
                    child_obj = existing_qs.get(id=item_id)
                except child_model.DoesNotExist:
                    item_data.pop("id", None)
                    child_obj = child_model.objects.create(
                        **item_data,
                        **{fk_name: parent_instance},
                    )
                else:
                    for attr, value in item_data.items():
                        if attr != "id":
                            setattr(child_obj, attr, value)
                    child_obj.save()
                sent_ids.append(child_obj.id)
            else:
                item_data.pop("id", None)
                child_obj = child_model.objects.create(
                    **item_data,
                    **{fk_name: parent_instance},
                )
                sent_ids.append(child_obj.id)

        if sent_ids:
            existing_qs.exclude(id__in=sent_ids).delete()
        else:
            existing_qs.delete()

    # -------------------- create & update --------------------

    @transaction.atomic
    def create(self, validated_data):
        gst_rates_data = validated_data.pop("gst_rates", [])
        barcodes_data = validated_data.pop("barcode_details", [])
        uom_conversions_data = validated_data.pop("uom_conversions", [])
        opening_stocks_data = validated_data.pop("opening_stocks", [])
        prices_data = validated_data.pop("prices", [])
        planning_data = validated_data.pop("planning", None)
        attributes_data = validated_data.pop("attributes", [])
        images_data = validated_data.pop("images", [])

        # strip ids on create
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

        product = Product.objects.create(**validated_data)

        for gr in gst_rates_data:
            # gst_rate is computed by model, ignore any client-provided value
            gr.pop("gst_rate", None)
            ProductGstRate.objects.create(product=product, **gr)

        for bd in barcodes_data:
            bd.pop("barcode", None)
            bd.pop("barcode_image", None)
            ProductBarcode.objects.create(product=product, **bd)

        for uc in uom_conversions_data:
            ProductUomConversion.objects.create(product=product, **uc)

        for os in opening_stocks_data:
            OpeningStockByLocation.objects.create(
                product=product,
                entity=product.entity,
                **os,
            )

        for pr in prices_data:
            ProductPrice.objects.create(product=product, **pr)

        if planning_data:
            planning_data.pop("id", None)
            ProductPlanning.objects.create(product=product, **planning_data)

        for av in attributes_data:
            ProductAttributeValue.objects.create(product=product, **av)

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

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if gst_rates_data is not None:
            # ignore gst_rate if sent
            for item in gst_rates_data:
                item.pop("gst_rate", None)
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
                strip_fields=["barcode", "barcode_image", "barcode_image_url"],
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

        if planning_data is not None:
            planning_data.pop("id", None)

            existing_planning_obj = instance.planning.first() if hasattr(instance, "planning") else None
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


# ----------------------------------------------------------------------
# Choice serializers (unchanged)
# ----------------------------------------------------------------------

class GstTypeChoiceSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class CessTypeChoiceSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class ProductStatusChoiceSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


# ----------------------------------------------------------------------
# Barcode manage serializer (updated only if you want strict primary handling)
# ----------------------------------------------------------------------

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

        # friendly behavior: ensure only one primary barcode
        if obj.isprimary:
            ProductBarcode.objects.filter(product=product).exclude(pk=obj.pk).update(isprimary=False)

        return obj

    @transaction.atomic
    def update(self, instance, validated_data):
        obj = super().update(instance, validated_data)

        if obj.isprimary:
            ProductBarcode.objects.filter(product=obj.product).exclude(pk=obj.pk).update(isprimary=False)

        return obj
