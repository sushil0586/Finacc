from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from catalog.models import PriceList, Product, ProductBarcode, ProductCategory, ProductPrice, UnitOfMeasure
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity

from .models import CommercePromotion, CommercePromotionScope, CommercePromotionSlab


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class CommerceFoundationTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        suffix = uuid4().hex[:8]
        self.user = User.objects.create_user(
            username=f"commerce-user-{suffix}",
            email=f"commerce-{suffix}@example.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.user)

        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Commerce Entity",
            entitydesc="Commerce entity",
            legalname="Commerce Entity Pvt Ltd",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Main Store")
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2025-26",
            finstartyear=timezone.make_aware(datetime(2025, 4, 1)),
            finendyear=timezone.make_aware(datetime(2026, 3, 31)),
            createdby=self.user,
        )
        self.category = ProductCategory.objects.create(entity=self.entity, pcategoryname="Inventory", level=1)
        self.uom = UnitOfMeasure.objects.create(entity=self.entity, code="NOS", description="Numbers", uqc="NOS")
        self.product = Product.objects.create(
            entity=self.entity,
            productname="Retail Pack",
            sku="RTL-001",
            productdesc="Retail pack",
            productcategory=self.category,
            base_uom=self.uom,
            is_service=False,
        )
        self.price_list = PriceList.objects.create(entity=self.entity, name="Default", isdefault=True)
        ProductPrice.objects.create(
            product=self.product,
            pricelist=self.price_list,
            uom=self.uom,
            selling_price="120.00",
            purchase_rate="90.00",
            effective_from="2025-04-01",
        )
        self.barcode = ProductBarcode.objects.create(
            product=self.product,
            uom=self.uom,
            isprimary=True,
            pack_size=1,
            barcode="8901234567890",
            mrp="130.00",
            selling_price="120.00",
        )

    def _create_promotion(self):
        promotion = CommercePromotion.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            code="BUYMORE",
            name="Buy More Free",
        )
        CommercePromotionScope.objects.create(promotion=promotion, product=self.product, barcode=self.barcode)
        CommercePromotionSlab.objects.create(promotion=promotion, sequence_no=1, min_qty="10.0000", free_qty="2.0000")
        CommercePromotionSlab.objects.create(promotion=promotion, sequence_no=2, min_qty="20.0000", free_qty="5.0000")
        return promotion

    def _create_discount_promotion(self):
        promotion = CommercePromotion.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            code="DISC10",
            name="Discount Slab",
        )
        CommercePromotionScope.objects.create(promotion=promotion, product=self.product, barcode=self.barcode)
        CommercePromotionSlab.objects.create(promotion=promotion, sequence_no=1, min_qty="5.0000", discount_percent="10.0000")
        return promotion

    def test_barcode_resolve_returns_pack_context(self):
        response = self.client.get(
            reverse("commerce:barcode-resolve"),
            {"entity": self.entity.id, "code": self.barcode.barcode},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["product_id"], self.product.id)
        self.assertEqual(payload["barcode_id"], self.barcode.id)
        self.assertEqual(payload["uom_code"], "NOS")
        self.assertEqual(payload["pack_size"], 1)
        self.assertEqual(payload["selling_price"], 120.0)

    def test_line_normalize_applies_best_free_qty_slab(self):
        self._create_promotion()

        response_10 = self.client.post(
            reverse("commerce:line-normalize"),
            {
                "entity": self.entity.id,
                "subentity": self.subentity.id,
                "barcode": self.barcode.barcode,
                "qty": "10.0000",
            },
            format="json",
        )
        self.assertEqual(response_10.status_code, 200)
        payload_10 = response_10.json()
        self.assertEqual(payload_10["free_qty"], 2.0)
        self.assertEqual(payload_10["stock_issue_qty"], 12.0)

        response_20 = self.client.post(
            reverse("commerce:line-normalize"),
            {
                "entity": self.entity.id,
                "subentity": self.subentity.id,
                "barcode": self.barcode.barcode,
                "qty": "20.0000",
            },
            format="json",
        )
        self.assertEqual(response_20.status_code, 200)
        payload_20 = response_20.json()
        self.assertEqual(payload_20["free_qty"], 5.0)
        self.assertEqual(payload_20["stock_issue_qty"], 25.0)

    def test_manual_discount_disables_auto_promotion(self):
        self._create_promotion()
        response = self.client.post(
            reverse("commerce:line-normalize"),
            {
                "entity": self.entity.id,
                "subentity": self.subentity.id,
                "barcode": self.barcode.barcode,
                "qty": "20.0000",
                "manual_discount_percent": "5.0000",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["free_qty"], 0.0)
        self.assertEqual(payload["discount_percent"], 5.0)
        self.assertEqual(payload["stock_issue_qty"], 20.0)

    def test_discount_slab_applies_on_product_based_normalization(self):
        self._create_discount_promotion()
        response = self.client.post(
            reverse("commerce:line-normalize"),
            {
                "entity": self.entity.id,
                "subentity": self.subentity.id,
                "product_id": self.product.id,
                "qty": "5.0000",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["free_qty"], 0.0)
        self.assertEqual(payload["discount_percent"], 10.0)
        self.assertEqual(payload["discount_amount"], 60.0)
        self.assertEqual(payload["taxable_value"], 540.0)

    def test_promotion_api_create_and_meta(self):
        meta = self.client.get(reverse("commerce:meta"))
        self.assertEqual(meta.status_code, 200)
        self.assertEqual(meta.json()["promotion_types"][0]["value"], "SAME_ITEM_SLAB")

        create = self.client.post(
            reverse("commerce:promotion-list-create"),
            {
                "entity": self.entity.id,
                "subentity": self.subentity.id,
                "code": "PROMO-API",
                "name": "API Promotion",
                "promotion_type": "SAME_ITEM_SLAB",
                "scopes": [{"product": self.product.id, "barcode": self.barcode.id}],
                "slabs": [
                    {"sequence_no": 1, "min_qty": "10.0000", "free_qty": "2.0000"},
                    {"sequence_no": 2, "min_qty": "20.0000", "discount_percent": "5.0000"},
                ],
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        payload = create.json()
        self.assertEqual(payload["code"], "PROMO-API")
        self.assertEqual(len(payload["slabs"]), 2)
