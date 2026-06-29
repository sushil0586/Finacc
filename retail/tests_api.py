from __future__ import annotations

from datetime import datetime

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from catalog.models import Product, ProductCategory, UnitOfMeasure
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, Godown, SubEntity


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class RetailOversizedValidationTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="retail-user",
            email="retail-user@example.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.user)

        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Retail Entity",
            entitydesc="Retail entity",
            legalname="Retail Entity Pvt Ltd",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Retail Branch")
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2025-26",
            finstartyear=timezone.make_aware(datetime(2025, 4, 1)),
            finendyear=timezone.make_aware(datetime(2026, 3, 31)),
            createdby=self.user,
        )
        self.location = Godown.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            name="Store Floor",
            code="STR-01",
            address="Main Market",
            city="Ludhiana",
            state="Punjab",
            pincode="141001",
            is_active=True,
        )
        self.category = ProductCategory.objects.create(entity=self.entity, pcategoryname="Retail Goods", level=1)
        self.uom = UnitOfMeasure.objects.create(entity=self.entity, code="PCS", description="Pieces", uqc="NOS")
        self.product = Product.objects.create(
            entity=self.entity,
            productname="Retail Product",
            sku="RTL-001",
            productdesc="Retail product",
            productcategory=self.category,
            base_uom=self.uom,
            is_service=False,
        )

    def test_ticket_create_rejects_oversized_fields(self):
        response = self.client.post(
            reverse("retail:ticket-list-create"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "bill_date": "2025-04-12",
                "location": self.location.id,
                "customer_name": "N" * 201,
                "customer_phone": "9" * 31,
                "customer_email": ("a" * 110) + "@example.com",
                "customer_gstin": "G" * 31,
                "address1": "A" * 256,
                "address2": "B" * 256,
                "city": "C" * 101,
                "state_code": "S" * 21,
                "pincode": "1" * 13,
                "narration": "R" * 501,
                "lines": [
                    {
                        "product": self.product.id,
                        "scanned_barcode": "B" * 51,
                        "product_desc_snapshot": "D" * 256,
                        "product_hsn_snapshot": "H" * 31,
                        "uom_code_snapshot": "U" * 21,
                        "promotion_code_snapshot": "P" * 51,
                        "qty": "1.0000",
                        "note": "T" * 201,
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("customer_name", response.json())
        self.assertIn("customer_phone", response.json())
        self.assertIn("customer_email", response.json())
        self.assertIn("customer_gstin", response.json())
        self.assertIn("address1", response.json())
        self.assertIn("address2", response.json())
        self.assertIn("city", response.json())
        self.assertIn("state_code", response.json())
        self.assertIn("pincode", response.json())
        self.assertIn("narration", response.json())

    def test_session_open_rejects_oversized_opening_note(self):
        response = self.client.post(
            reverse("retail:session-open"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "location": self.location.id,
                "session_date": "2025-04-12",
                "opening_note": "O" * 201,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("opening_note", response.json())

    def test_session_close_rejects_oversized_closing_note(self):
        open_response = self.client.post(
            reverse("retail:session-open"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "location": self.location.id,
                "session_date": "2025-04-12",
                "opening_note": "Open shift",
            },
            format="json",
        )
        self.assertEqual(open_response.status_code, 201)

        response = self.client.post(
            reverse("retail:session-close", kwargs={"pk": open_response.json()["id"]}),
            {"closing_note": "C" * 201},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("closing_note", response.json())
