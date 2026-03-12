from django.db import transaction

from catalog.models import (
    Brand,
    HsnSac,
    PriceList,
    ProductAttribute,
    ProductCategory,
    UnitOfMeasure,
)


class CatalogSeedService:
    CATEGORY_ROWS = [
        {"name": "Electronics", "parent": None},
        {"name": "Mobile Phones", "parent": "Electronics"},
        {"name": "Televisions", "parent": "Electronics"},
        {"name": "Appliances", "parent": None},
        {"name": "Services", "parent": None},
    ]

    BRAND_ROWS = [
        {"name": "Generic", "description": "Generic catalog brand"},
        {"name": "Samsung", "description": "Consumer electronics brand"},
        {"name": "Apple", "description": "Consumer electronics brand"},
        {"name": "LG", "description": "Electronics and appliances brand"},
    ]

    UOM_ROWS = [
        {"code": "PCS", "description": "Pieces", "uqc": "NOS"},
        {"code": "BOX", "description": "Box", "uqc": "BOX"},
        {"code": "KGS", "description": "Kilograms", "uqc": "KGS"},
        {"code": "MTR", "description": "Meter", "uqc": "MTR"},
        {"code": "LTR", "description": "Litre", "uqc": "LTR"},
        {"code": "SET", "description": "Set", "uqc": "SET"},
    ]

    HSN_ROWS = [
        {
            "code": "85171200",
            "description": "Smartphones and mobile handsets",
            "is_service": False,
            "default_sgst": "9.00",
            "default_cgst": "9.00",
            "default_igst": "18.00",
            "default_cess": "0.00",
            "is_exempt": False,
            "is_nil_rated": False,
            "is_non_gst": False,
        },
        {
            "code": "85287217",
            "description": "LED televisions",
            "is_service": False,
            "default_sgst": "9.00",
            "default_cgst": "9.00",
            "default_igst": "18.00",
            "default_cess": "0.00",
            "is_exempt": False,
            "is_nil_rated": False,
            "is_non_gst": False,
        },
        {
            "code": "998314",
            "description": "IT design and development services",
            "is_service": True,
            "default_sgst": "9.00",
            "default_cgst": "9.00",
            "default_igst": "18.00",
            "default_cess": "0.00",
            "is_exempt": False,
            "is_nil_rated": False,
            "is_non_gst": False,
        },
        {
            "code": "999000",
            "description": "Exempt supplies",
            "is_service": False,
            "default_sgst": "0.00",
            "default_cgst": "0.00",
            "default_igst": "0.00",
            "default_cess": "0.00",
            "is_exempt": True,
            "is_nil_rated": False,
            "is_non_gst": False,
        },
    ]

    PRICELIST_ROWS = [
        {"name": "Retail", "description": "Default retail price list", "isdefault": True},
        {"name": "Wholesale", "description": "Wholesale customer price list", "isdefault": False},
        {"name": "Purchase", "description": "Reference purchase rate list", "isdefault": False},
    ]

    ATTRIBUTE_ROWS = [
        {"name": "Color", "data_type": "char"},
        {"name": "Size", "data_type": "char"},
        {"name": "Weight", "data_type": "number"},
        {"name": "Expiry Date", "data_type": "date"},
        {"name": "Is Fragile", "data_type": "bool"},
    ]

    @classmethod
    @transaction.atomic
    def seed_entity(cls, *, entity):
        summary = {
            "categories_created": 0,
            "categories_updated": 0,
            "brands_created": 0,
            "brands_updated": 0,
            "uoms_created": 0,
            "uoms_updated": 0,
            "hsn_created": 0,
            "hsn_updated": 0,
            "pricelists_created": 0,
            "pricelists_updated": 0,
            "attributes_created": 0,
            "attributes_updated": 0,
        }

        category_map = {}
        for row in cls.CATEGORY_ROWS:
            parent = category_map.get(row["parent"])
            level = (parent.level + 1) if parent else 1
            obj, created = ProductCategory.objects.update_or_create(
                entity=entity,
                pcategoryname=row["name"],
                defaults={
                    "maincategory": parent,
                    "level": level,
                    "isactive": True,
                },
            )
            category_map[row["name"]] = obj
            key = "categories_created" if created else "categories_updated"
            summary[key] += 1

        for row in cls.BRAND_ROWS:
            _, created = Brand.objects.update_or_create(
                entity=entity,
                name=row["name"],
                defaults={
                    "description": row["description"],
                    "isactive": True,
                },
            )
            key = "brands_created" if created else "brands_updated"
            summary[key] += 1

        for row in cls.UOM_ROWS:
            _, created = UnitOfMeasure.objects.update_or_create(
                entity=entity,
                code=row["code"],
                defaults={
                    "description": row["description"],
                    "uqc": row["uqc"],
                    "isactive": True,
                },
            )
            key = "uoms_created" if created else "uoms_updated"
            summary[key] += 1

        for row in cls.HSN_ROWS:
            _, created = HsnSac.objects.update_or_create(
                entity=entity,
                code=row["code"],
                defaults={
                    "description": row["description"],
                    "is_service": row["is_service"],
                    "default_sgst": row["default_sgst"],
                    "default_cgst": row["default_cgst"],
                    "default_igst": row["default_igst"],
                    "default_cess": row["default_cess"],
                    "is_exempt": row["is_exempt"],
                    "is_nil_rated": row["is_nil_rated"],
                    "is_non_gst": row["is_non_gst"],
                    "isactive": True,
                },
            )
            key = "hsn_created" if created else "hsn_updated"
            summary[key] += 1

        has_existing_default = PriceList.objects.filter(entity=entity, isdefault=True).exists()
        for row in cls.PRICELIST_ROWS:
            desired_default = row["isdefault"] and (
                not has_existing_default or PriceList.objects.filter(entity=entity, name=row["name"], isdefault=True).exists()
            )
            _, created = PriceList.objects.update_or_create(
                entity=entity,
                name=row["name"],
                defaults={
                    "description": row["description"],
                    "isdefault": desired_default,
                    "isactive": True,
                },
            )
            if desired_default:
                has_existing_default = True
            key = "pricelists_created" if created else "pricelists_updated"
            summary[key] += 1

        for row in cls.ATTRIBUTE_ROWS:
            _, created = ProductAttribute.objects.update_or_create(
                entity=entity,
                name=row["name"],
                defaults={
                    "data_type": row["data_type"],
                    "isactive": True,
                },
            )
            key = "attributes_created" if created else "attributes_updated"
            summary[key] += 1

        return summary
