from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from catalog.models import (
    GstType,
    HsnSac,
    PriceList,
    Product,
    ProductCategory,
    ProductGstRate,
    ProductPrice,
    ProductPurchaseBehavior,
    ProductStatus,
    UnitOfMeasure,
)
from catalog.seeding import CatalogSeedService
from entity.models import Entity, Godown, SubEntity
from entity.seeding import EntitySeedService
from financial.party_accounting_defaults import resolve_party_accounting_ids
from financial.services import apply_normalized_profile_payload, create_account_with_synced_ledger
from financial.models import AccountAddress, ShippingDetails, account
from geography.models import City, Country, District, State


INDIA_STATES_GST = [
    ("01", "Jammu and Kashmir"),
    ("02", "Himachal Pradesh"),
    ("03", "Punjab"),
    ("04", "Chandigarh"),
    ("05", "Uttarakhand"),
    ("06", "Haryana"),
    ("07", "Delhi"),
    ("08", "Rajasthan"),
    ("09", "Uttar Pradesh"),
    ("10", "Bihar"),
    ("11", "Sikkim"),
    ("12", "Arunachal Pradesh"),
    ("13", "Nagaland"),
    ("14", "Manipur"),
    ("15", "Mizoram"),
    ("16", "Tripura"),
    ("17", "Meghalaya"),
    ("18", "Assam"),
    ("19", "West Bengal"),
    ("20", "Jharkhand"),
    ("21", "Odisha"),
    ("22", "Chhattisgarh"),
    ("23", "Madhya Pradesh"),
    ("24", "Gujarat"),
    ("26", "Dadra and Nagar Haveli and Daman and Diu"),
    ("27", "Maharashtra"),
    ("28", "Andhra Pradesh"),
    ("29", "Karnataka"),
    ("30", "Goa"),
    ("31", "Lakshadweep"),
    ("32", "Kerala"),
    ("33", "Tamil Nadu"),
    ("34", "Puducherry"),
    ("35", "Andaman and Nicobar Islands"),
    ("36", "Telangana"),
    ("37", "Andhra Pradesh (New)"),
    ("38", "Ladakh"),
    ("97", "Other Territory"),
]

LAUNCH_GEOGRAPHY_FIXTURES = [
    {"state_code": "01", "district": "Srinagar", "district_code": "SRI", "city": "Srinagar", "city_code": "SRG", "pincode": "190001"},
    {"state_code": "02", "district": "Shimla", "district_code": "SHM", "city": "Shimla", "city_code": "SHM", "pincode": "171001"},
    {"state_code": "03", "district": "Fatehgarh Sahib", "district_code": "FGS", "city": "Sirhind", "city_code": "SRH", "pincode": "140406"},
    {"state_code": "04", "district": "Chandigarh", "district_code": "CHD", "city": "Chandigarh", "city_code": "CHD", "pincode": "160017"},
    {"state_code": "05", "district": "Dehradun", "district_code": "DDN", "city": "Dehradun", "city_code": "DDN", "pincode": "248001"},
    {"state_code": "06", "district": "Gurugram", "district_code": "GGM", "city": "Gurugram", "city_code": "GGM", "pincode": "122001"},
    {"state_code": "07", "district": "New Delhi", "district_code": "NDL", "city": "New Delhi", "city_code": "NDL", "pincode": "110001"},
    {"state_code": "08", "district": "Jaipur", "district_code": "JPR", "city": "Jaipur", "city_code": "JPR", "pincode": "302001"},
    {"state_code": "09", "district": "Lucknow", "district_code": "LKO", "city": "Lucknow", "city_code": "LKO", "pincode": "226001"},
    {"state_code": "10", "district": "Patna", "district_code": "PAT", "city": "Patna", "city_code": "PAT", "pincode": "800001"},
    {"state_code": "11", "district": "Gangtok", "district_code": "GTK", "city": "Gangtok", "city_code": "GTK", "pincode": "737101"},
    {"state_code": "12", "district": "Itanagar", "district_code": "ITA", "city": "Itanagar", "city_code": "ITA", "pincode": "791111"},
    {"state_code": "13", "district": "Kohima", "district_code": "KOH", "city": "Kohima", "city_code": "KOH", "pincode": "797001"},
    {"state_code": "14", "district": "Imphal West", "district_code": "IMW", "city": "Imphal", "city_code": "IMP", "pincode": "795001"},
    {"state_code": "15", "district": "Aizawl", "district_code": "AIZ", "city": "Aizawl", "city_code": "AIZ", "pincode": "796001"},
    {"state_code": "16", "district": "West Tripura", "district_code": "WTR", "city": "Agartala", "city_code": "AGT", "pincode": "799001"},
    {"state_code": "17", "district": "East Khasi Hills", "district_code": "EKH", "city": "Shillong", "city_code": "SHL", "pincode": "793001"},
    {"state_code": "18", "district": "Kamrup Metropolitan", "district_code": "KMP", "city": "Guwahati", "city_code": "GHY", "pincode": "781001"},
    {"state_code": "19", "district": "Kolkata", "district_code": "KOL", "city": "Kolkata", "city_code": "KOL", "pincode": "700001"},
    {"state_code": "20", "district": "Ranchi", "district_code": "RAN", "city": "Ranchi", "city_code": "RAN", "pincode": "834001"},
    {"state_code": "21", "district": "Khordha", "district_code": "KHR", "city": "Bhubaneswar", "city_code": "BBS", "pincode": "751001"},
    {"state_code": "22", "district": "Raipur", "district_code": "RPR", "city": "Raipur", "city_code": "RPR", "pincode": "492001"},
    {"state_code": "23", "district": "Bhopal", "district_code": "BPL", "city": "Bhopal", "city_code": "BPL", "pincode": "462001"},
    {"state_code": "24", "district": "Ahmedabad", "district_code": "AHD", "city": "Ahmedabad", "city_code": "AHD", "pincode": "380001"},
    {"state_code": "26", "district": "Daman", "district_code": "DAM", "city": "Daman", "city_code": "DAM", "pincode": "396210"},
    {"state_code": "27", "district": "Pune", "district_code": "PUN", "city": "Pune", "city_code": "PUN", "pincode": "411001"},
    {"state_code": "28", "district": "NTR", "district_code": "NTR", "city": "Vijayawada", "city_code": "VJA", "pincode": "520001"},
    {"state_code": "29", "district": "Bengaluru Urban", "district_code": "BLRU", "city": "Bengaluru", "city_code": "BLR", "pincode": "560001"},
    {"state_code": "30", "district": "North Goa", "district_code": "NGA", "city": "Panaji", "city_code": "PNJ", "pincode": "403001"},
    {"state_code": "31", "district": "Lakshadweep", "district_code": "LKD", "city": "Kavaratti", "city_code": "KVT", "pincode": "682555"},
    {"state_code": "32", "district": "Ernakulam", "district_code": "ERN", "city": "Kochi", "city_code": "COK", "pincode": "682001"},
    {"state_code": "33", "district": "Chennai", "district_code": "CHE", "city": "Chennai", "city_code": "CHE", "pincode": "600001"},
    {"state_code": "34", "district": "Puducherry", "district_code": "PDY", "city": "Puducherry", "city_code": "PDY", "pincode": "605001"},
    {"state_code": "35", "district": "South Andaman", "district_code": "SAN", "city": "Port Blair", "city_code": "PBL", "pincode": "744101"},
    {"state_code": "36", "district": "Hyderabad", "district_code": "HYD", "city": "Hyderabad", "city_code": "HYD", "pincode": "500001"},
    {"state_code": "37", "district": "Guntur", "district_code": "GNT", "city": "Amaravati", "city_code": "AMV", "pincode": "522020"},
    {"state_code": "38", "district": "Leh", "district_code": "LEH", "city": "Leh", "city_code": "LEH", "pincode": "194101"},
    {"state_code": "97", "district": "Other Territory", "district_code": "OTH", "city": "Other Territory", "city_code": "OTC", "pincode": "999999"},
]

LAUNCH_CUSTOMERS = [
    {
        "name": "Launch GST Customer Karnataka",
        "legal_name": "Launch GST Customer Karnataka",
        "gstin": "29AWGPV7107B1Z1",
        "pan": "AWGPV7107B",
        "state_code": "29",
        "pincode": "560001",
    },
    {
        "name": "Launch GST Customer Maharashtra",
        "legal_name": "Launch GST Customer Maharashtra",
        "gstin": "27AWGPV7107B1Z5",
        "pan": "AWGPV7107B",
        "state_code": "27",
        "pincode": "411001",
    },
]


class LaunchSeedService:
    """
    Idempotent data seed for stage launch-validation runs.

    This intentionally seeds only master/fixture data, not posted business
    transactions, so it can be safely rerun before browser validation.
    """

    @classmethod
    @transaction.atomic
    def seed(cls, *, entities=None, actor=None, dry_run=False, include_entity_bootstrap=True):
        entities = list(entities or [])
        summary = {
            "dry_run": bool(dry_run),
            "geography": cls.seed_geography(),
            "entities": [],
        }

        for entity in entities:
            summary["entities"].append(
                cls.seed_entity(
                    entity=entity,
                    actor=actor,
                    include_entity_bootstrap=include_entity_bootstrap,
                )
            )

        if dry_run:
            transaction.set_rollback(True)
        return summary

    @classmethod
    def seed_geography(cls):
        stats = {
            "country_created": 0,
            "country_updated": 0,
            "states_created": 0,
            "states_updated": 0,
            "districts_created": 0,
            "districts_updated": 0,
            "cities_created": 0,
            "cities_updated": 0,
            "states_with_active_district_city": 0,
        }
        india = Country.objects.filter(countrycode__iexact="IN").first()
        if india is None:
            india = Country.objects.create(countryname="India", countrycode="IN", isactive=True)
            stats["country_created"] += 1
        else:
            changed = cls._assign_if_changed(india, countryname="India", countrycode="IN", isactive=True)
            if changed:
                india.save(update_fields=[*changed, "updated_at"])
                stats["country_updated"] += 1

        state_map = {}
        for state_code, state_name in INDIA_STATES_GST:
            state, created = cls._get_or_create_state(india, state_code, state_name)
            state_map[state_code] = state
            stats["states_created" if created else "states_updated"] += 1 if cls._last_changed else 0

        for row in LAUNCH_GEOGRAPHY_FIXTURES:
            state = state_map[row["state_code"]]
            district, district_created = cls._get_or_create_district(
                state=state,
                district_name=row["district"],
                district_code=row["district_code"],
            )
            if district_created:
                stats["districts_created"] += 1
            elif cls._last_changed:
                stats["districts_updated"] += 1

            city, city_created = cls._get_or_create_city(
                district=district,
                city_name=row["city"],
                city_code=row["city_code"],
                pincode=row["pincode"],
            )
            if city_created:
                stats["cities_created"] += 1
            elif cls._last_changed:
                stats["cities_updated"] += 1
            if district.isactive and city.isactive:
                stats["states_with_active_district_city"] += 1
        return stats

    @classmethod
    def seed_entity(cls, *, entity, actor=None, include_entity_bootstrap=True):
        summary = {
            "entity_id": entity.id,
            "entity_name": entity.entityname,
            "bootstrap": None,
        }
        if include_entity_bootstrap:
            summary["bootstrap"] = EntitySeedService.repair_entity_bootstrap(entity=entity, actor=actor)

        summary["godown"] = cls._ensure_default_godown(entity=entity)
        summary["product"] = cls._ensure_launch_goods_product(entity=entity)
        summary["customers"] = [cls._ensure_launch_customer(entity=entity, actor=actor, spec=spec) for spec in LAUNCH_CUSTOMERS]
        return summary

    @staticmethod
    def _assign_if_changed(obj, **values):
        changed = []
        for field, value in values.items():
            if getattr(obj, field) != value:
                setattr(obj, field, value)
                changed.append(field)
        return changed

    _last_changed = False

    @classmethod
    def _get_or_create_state(cls, country, state_code, state_name):
        cls._last_changed = False
        state = (
            State.objects.filter(country=country, statecode=state_code).first()
            or State.objects.filter(country=country, statename__iexact=state_name).first()
        )
        if state is None:
            cls._last_changed = True
            return State.objects.create(country=country, statecode=state_code, statename=state_name, isactive=True), True
        changed = cls._assign_if_changed(state, country=country, statecode=state_code, statename=state_name, isactive=True)
        if changed:
            state.save(update_fields=[*changed, "updated_at"])
            cls._last_changed = True
        return state, False

    @classmethod
    def _get_or_create_district(cls, *, state, district_name, district_code):
        cls._last_changed = False
        district = (
            District.objects.filter(state=state, districtcode__iexact=district_code).first()
            or District.objects.filter(state=state, districtname__iexact=district_name).first()
        )
        if district is None:
            cls._last_changed = True
            return District.objects.create(
                state=state,
                districtname=district_name,
                districtcode=district_code,
                isactive=True,
            ), True
        changed = cls._assign_if_changed(
            district,
            state=state,
            districtname=district_name,
            districtcode=district_code,
            isactive=True,
        )
        if changed:
            district.save(update_fields=[*changed, "updated_at"])
            cls._last_changed = True
        return district, False

    @classmethod
    def _get_or_create_city(cls, *, district, city_name, city_code, pincode):
        cls._last_changed = False
        city = (
            City.objects.filter(distt=district, citycode__iexact=city_code).first()
            or City.objects.filter(distt=district, cityname__iexact=city_name, pincode=pincode).first()
        )
        if city is None:
            cls._last_changed = True
            return City.objects.create(
                distt=district,
                cityname=city_name,
                citycode=city_code,
                pincode=pincode,
                isactive=True,
            ), True
        changed = cls._assign_if_changed(
            city,
            distt=district,
            cityname=city_name,
            citycode=city_code,
            pincode=pincode,
            isactive=True,
        )
        if changed:
            city.save(update_fields=[*changed, "updated_at"])
            cls._last_changed = True
        return city, False

    @classmethod
    def _fixture_for_state(cls, state_code):
        return next(row for row in LAUNCH_GEOGRAPHY_FIXTURES if row["state_code"] == state_code)

    @classmethod
    def _geography_for_state(cls, state_code):
        row = cls._fixture_for_state(state_code)
        country = Country.objects.get(countrycode="IN")
        state = State.objects.get(country=country, statecode=state_code)
        district = District.objects.filter(state=state, districtcode=row["district_code"], isactive=True).first()
        city = City.objects.filter(distt=district, citycode=row["city_code"], isactive=True).first()
        if district is None or city is None:
            raise ValidationError(f"Launch geography is incomplete for state {state_code}.")
        return country, state, district, city

    @staticmethod
    def _first_subentity(entity):
        return SubEntity.objects.filter(entity=entity, isactive=True).order_by("-is_head_office", "id").first()

    @classmethod
    def _ensure_default_godown(cls, *, entity):
        subentity = cls._first_subentity(entity)
        obj, created = Godown.objects.update_or_create(
            entity=entity,
            code="LAUNCH-STOCK",
            defaults={
                "subentity": subentity,
                "name": "Launch Validation Stock",
                "address": "Launch validation stock location",
                "city": "Bengaluru",
                "state": "Karnataka",
                "pincode": "560001",
                "is_active": True,
                "is_default": True,
            },
        )
        return {"id": obj.id, "created": created, "name": obj.name, "code": obj.code}

    @classmethod
    def _ensure_launch_goods_product(cls, *, entity):
        CatalogSeedService.seed_entity(entity=entity)
        category = (
            ProductCategory.objects.filter(entity=entity, pcategoryname="Electronics", isactive=True).first()
            or ProductCategory.objects.filter(entity=entity, isactive=True).order_by("id").first()
        )
        uom = (
            UnitOfMeasure.objects.filter(entity=entity, code="PCS", isactive=True).first()
            or UnitOfMeasure.objects.filter(entity=entity, isactive=True).order_by("id").first()
        )
        hsn = (
            HsnSac.objects.filter(entity=entity, code="85171200", isactive=True).first()
            or HsnSac.objects.filter(entity=entity, is_service=False, isactive=True).order_by("id").first()
        )
        if category is None or uom is None or hsn is None:
            raise ValidationError("Catalog launch dependencies were not created.")

        product = (
            Product.objects.filter(entity=entity, sku="LAUNCH-ABC-GOODS").first()
            or Product.objects.filter(entity=entity, productname__iexact="ABC").order_by("id").first()
        )
        created = False
        if product is None:
            product = Product(entity=entity, sku="LAUNCH-ABC-GOODS")
            created = True
        product.productname = "ABC"
        product.productdesc = "Launch validation goods item"
        product.productcategory = category
        product.base_uom = uom
        product.is_service = False
        product.item_classification = "trading_item"
        product.purchase_behavior = ProductPurchaseBehavior.INVENTORY
        product.default_taxability = 1
        product.is_batch_managed = False
        product.is_serialized = False
        product.is_expiry_tracked = False
        product.shelf_life_days = None
        product.expiry_warning_days = 30
        product.is_ecomm_9_5_service = False
        product.default_is_rcm = False
        product.is_itc_eligible = True
        product.product_status = ProductStatus.ACTIVE
        product.launch_date = date(2026, 4, 1)
        product.discontinue_date = None
        product.isactive = True
        product.save()

        gst_rate, gst_created = cls._ensure_default_product_gst_rate(product=product, hsn=hsn)

        default_price_list = PriceList.objects.filter(entity=entity, isdefault=True, isactive=True).order_by("id").first()
        price_id = None
        if default_price_list is not None:
            price, _ = ProductPrice.objects.update_or_create(
                product=product,
                pricelist=default_price_list,
                uom=uom,
                effective_from=date(2026, 4, 1),
                defaults={
                    "purchase_rate": Decimal("100.00"),
                    "mrp": Decimal("150.00"),
                    "selling_price": Decimal("100.00"),
                    "effective_to": None,
                },
            )
            price_id = price.id

        return {
            "id": product.id,
            "created": created,
            "productname": product.productname,
            "sku": product.sku,
            "gst_rate_id": gst_rate.id,
            "gst_rate_created": gst_created,
            "price_id": price_id,
        }

    @classmethod
    def _ensure_default_product_gst_rate(cls, *, product, hsn):
        existing = ProductGstRate.objects.filter(product=product).order_by("-isdefault", "-valid_from", "-id").first()
        values = {
            "gst_type": GstType.REGULAR,
            "sgst": Decimal("9.00"),
            "cgst": Decimal("9.00"),
            "igst": Decimal("18.00"),
            "gst_rate": Decimal("18.00"),
            "cess": Decimal("0.00"),
            "cess_type": "none",
            "cess_specific_amount": None,
            "valid_to": None,
            "isdefault": True,
        }
        if existing is not None:
            ProductGstRate.objects.filter(product=product, isdefault=True).exclude(pk=existing.pk).update(isdefault=False)
            ProductGstRate.objects.filter(pk=existing.pk).update(**values)
            existing.refresh_from_db()
            return existing, False

        ProductGstRate.objects.filter(product=product, isdefault=True).update(isdefault=False)
        return ProductGstRate.objects.create(
            product=product,
            hsn=hsn,
            valid_from=None,
            **values,
        ), True

    @classmethod
    def _ensure_launch_customer(cls, *, entity, actor=None, spec):
        country, state, district, city = cls._geography_for_state(spec["state_code"])
        defaults = resolve_party_accounting_ids(entity=entity, partytype="Customer")
        if not defaults["accounthead_id"]:
            raise ValidationError("Customer account head is missing. Run financial bootstrap first.")

        acc = (
            account.objects.filter(entity=entity, compliance_profile__gstno=spec["gstin"]).first()
            or account.objects.filter(entity=entity, accountname__iexact=spec["name"]).first()
        )
        created = False
        if acc is None:
            acc = create_account_with_synced_ledger(
                account_data={
                    "entity": entity,
                    "accountname": spec["name"],
                    "legalname": spec["legal_name"],
                    "iscompany": True,
                    "isactive": True,
                    "canbedeleted": True,
                    "createdby": actor,
                },
                ledger_overrides={
                    "name": spec["name"],
                    "legal_name": spec["legal_name"],
                    "accounthead_id": defaults["accounthead_id"],
                    "creditaccounthead_id": defaults["creditaccounthead_id"],
                    "accounttype_id": defaults["accounttype_id"],
                    "openingbcr": Decimal("0.00"),
                    "openingbdr": Decimal("0.00"),
                    "is_party": True,
                    "is_system": False,
                },
            )
            created = True
        else:
            acc.accountname = spec["name"]
            acc.legalname = spec["legal_name"]
            acc.iscompany = True
            acc.isactive = True
            acc.save()

        apply_normalized_profile_payload(
            acc,
            compliance_data={
                "gstno": spec["gstin"],
                "pan": spec["pan"],
                "gstregtype": "Regular",
                "gstintype": "Regular",
            },
            commercial_data={
                "partytype": "Customer",
                "approved": True,
                "currency": "INR",
                "paymentterms": "Net30",
                "blockstatus": "Active",
            },
            primary_address_data={
                "address_type": AccountAddress.AddressType.BILLING,
                "line1": f"{spec['name']} billing address",
                "country": country,
                "state": state,
                "district": district,
                "city": city,
                "pincode": spec["pincode"],
                "isprimary": True,
            },
            primary_contact_data={
                "full_name": spec["name"],
                "emailid": f"{spec['name'].lower().replace(' ', '.')}@example.com",
            },
            createdby=actor,
        )

        shipping, shipping_created = ShippingDetails.objects.update_or_create(
            account=acc,
            isprimary=True,
            defaults={
                "entity": entity,
                "createdby": actor,
                "gstno": spec["gstin"],
                "address1": f"{spec['name']} ship-to address",
                "country": country,
                "state": state,
                "district": district,
                "city": city,
                "pincode": spec["pincode"],
                "emailid": f"{spec['name'].lower().replace(' ', '.')}@example.com",
                "full_name": spec["name"],
            },
        )
        return {
            "id": acc.id,
            "created": created,
            "name": acc.accountname,
            "gstin": spec["gstin"],
            "shipping_detail_id": shipping.id,
            "shipping_detail_created": shipping_created,
        }
