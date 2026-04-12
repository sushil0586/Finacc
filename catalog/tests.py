from django.contrib.auth import get_user_model
from django.test import TestCase

from catalog.models import HsnSac, Product, ProductCategory, ProductClassification, UnitOfMeasure
from catalog.serializers import ProductSerializer
from entity.models import Entity, GstRegistrationType, UnitType


class CatalogPhase1Tests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="catalog-phase1",
            email="catalog-phase1@example.com",
            password="testpass123",
        )
        self.unit_type = UnitType.objects.create(UnitName="Trader", UnitDesc="Trader")
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Catalog Phase1 Entity",
            unitType=self.unit_type,
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.category = ProductCategory.objects.create(
            entity=self.entity,
            pcategoryname="Finished Goods",
        )
        self.uom = UnitOfMeasure.objects.create(
            entity=self.entity,
            code="PCS",
            description="Pieces",
        )
        self.hsn = HsnSac.objects.create(
            entity=self.entity,
            code="9983",
            description="Services",
        )

    def _valid_payload(self, **overrides):
        payload = {
            "entity": self.entity.id,
            "productname": "Inventory Ready Product",
            "sku": "IRP-001",
            "productdesc": "Phase 1 product",
            "productcategory": self.category.id,
            "brand": None,
            "base_uom": self.uom.id,
            "sales_account": None,
            "purchase_account": None,
            "is_service": False,
            "item_classification": ProductClassification.TRADING,
            "is_batch_managed": False,
            "is_serialized": False,
            "is_expiry_tracked": True,
            "shelf_life_days": 180,
            "expiry_warning_days": 30,
            "is_ecomm_9_5_service": False,
            "default_is_rcm": False,
            "is_itc_eligible": True,
            "product_status": "active",
            "launch_date": "2026-04-12",
            "discontinue_date": None,
            "isactive": True,
        }
        payload.update(overrides)
        return payload

    def test_product_serializer_accepts_classification_and_expiry_fields(self):
        serializer = ProductSerializer(
            data=self._valid_payload(),
            context={"entity": self.entity},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

        product = serializer.save(entity=self.entity)

        self.assertEqual(product.item_classification, ProductClassification.TRADING)
        self.assertTrue(product.is_expiry_tracked)
        self.assertEqual(product.shelf_life_days, 180)
        self.assertEqual(product.expiry_warning_days, 30)

    def test_expiry_warning_cannot_exceed_shelf_life(self):
        serializer = ProductSerializer(
            data=self._valid_payload(expiry_warning_days=365, shelf_life_days=180),
            context={"entity": self.entity},
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("expiry_warning_days", serializer.errors)

    def test_expiry_tracking_requires_shelf_life(self):
        serializer = ProductSerializer(
            data=self._valid_payload(is_expiry_tracked=True, shelf_life_days=None),
            context={"entity": self.entity},
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("shelf_life_days", serializer.errors)
