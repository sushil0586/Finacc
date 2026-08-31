from __future__ import annotations

import json
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from catalog.models import Product, ProductGstRate, UnitOfMeasure
from entity.launch_seed import INDIA_STATES_GST, LAUNCH_CUSTOMERS, LaunchSeedService
from entity.models import Entity, Godown, GstRegistrationType, SubEntity
from financial.models import ShippingDetails, account
from geography.models import City, Country, District, State


class LaunchSeedServiceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="launch-seed",
            email="launch-seed@example.com",
            password="testpass123",
        )
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Launch Seed Entity",
            legalname="Launch Seed Entity Pvt Ltd",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(
            entity=self.entity,
            subentityname="Head Office",
            subentity_code="HO",
            branch_type=SubEntity.BranchType.HEAD_OFFICE,
            is_head_office=True,
        )

    def test_dry_run_rolls_back_geography_changes(self):
        summary = LaunchSeedService.seed(dry_run=True)

        self.assertTrue(summary["dry_run"])
        self.assertEqual(summary["geography"]["states_with_active_district_city"], len(INDIA_STATES_GST))
        self.assertFalse(Country.objects.filter(countrycode="IN").exists())
        self.assertEqual(State.objects.count(), 0)
        self.assertEqual(District.objects.count(), 0)
        self.assertEqual(City.objects.count(), 0)

    def test_geography_seed_covers_every_india_gst_state(self):
        summary = LaunchSeedService.seed()

        india = Country.objects.get(countrycode="IN")
        self.assertEqual(summary["geography"]["states_with_active_district_city"], len(INDIA_STATES_GST))
        self.assertEqual(State.objects.filter(country=india, isactive=True).count(), len(INDIA_STATES_GST))
        for state_code, _state_name in INDIA_STATES_GST:
            state = State.objects.get(country=india, statecode=state_code, isactive=True)
            district = District.objects.filter(state=state, isactive=True).first()
            self.assertIsNotNone(district, state_code)
            self.assertTrue(City.objects.filter(distt=district, isactive=True).exists(), state_code)

    def test_entity_seed_creates_browser_launch_fixtures_idempotently(self):
        first = LaunchSeedService.seed(entities=[self.entity], actor=self.user)
        second = LaunchSeedService.seed(entities=[self.entity], actor=self.user)

        first_entity = first["entities"][0]
        second_entity = second["entities"][0]
        self.assertEqual(first_entity["product"]["id"], second_entity["product"]["id"])
        self.assertEqual(
            sorted(row["id"] for row in first_entity["customers"]),
            sorted(row["id"] for row in second_entity["customers"]),
        )

        product = Product.objects.get(entity=self.entity, productname="ABC")
        self.assertEqual(product.sku, "LAUNCH-ABC-GOODS")
        self.assertFalse(product.is_service)
        self.assertTrue(ProductGstRate.objects.filter(product=product, isdefault=True, gst_rate="18.00").exists())

        self.assertTrue(Godown.objects.filter(entity=self.entity, code="LAUNCH-STOCK", is_active=True).exists())
        for spec in LAUNCH_CUSTOMERS:
            customer = account.objects.get(entity=self.entity, compliance_profile__gstno=spec["gstin"])
            self.assertEqual(customer.commercial_profile.partytype, "Customer")
            self.assertTrue(
                ShippingDetails.objects.filter(
                    account=customer,
                    isprimary=True,
                    state__statecode=spec["state_code"],
                ).exists()
            )

    def test_entity_seed_tolerates_legacy_uom_uqc_collision(self):
        UnitOfMeasure.objects.create(
            entity=self.entity,
            code="NOS",
            description="Legacy numbers UOM",
            uqc="NOS",
        )

        LaunchSeedService.seed(entities=[self.entity], actor=self.user)

        pcs = UnitOfMeasure.objects.get(entity=self.entity, code="PCS")
        self.assertNotEqual(pcs.uqc, "NOS")
        self.assertTrue(Product.objects.filter(entity=self.entity, productname="ABC", base_uom=pcs).exists())


class LaunchSeedCommandTests(TestCase):
    def test_command_geography_only_supports_json_and_dry_run(self):
        out = StringIO()

        call_command("seed_launch_validation_data", geography_only=True, dry_run=True, json=True, stdout=out)

        payload = json.loads(out.getvalue())
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["geography"]["states_with_active_district_city"], len(INDIA_STATES_GST))
        self.assertEqual(payload["entities"], [])
        self.assertFalse(Country.objects.filter(countrycode="IN").exists())
