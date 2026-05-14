from __future__ import annotations

from datetime import datetime

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient, APITestCase
from unittest.mock import patch

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class Gstr9MetaAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="gstr9-user",
            email="gstr9@example.com",
            password="pass123",
        )
        self.permission_codes_patch = patch(
            "reports.api.report_permissions.EffectivePermissionService.permission_codes_for_user",
            return_value=["reports.gstr9.view"],
        )
        self.permission_codes_patch.start()
        self.addCleanup(self.permission_codes_patch.stop)
        self.client.force_authenticate(user=self.user)
        self.meta_url = reverse("reports_api:gstr9-meta")

        gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Finacc Entity",
            legalname="Finacc Entity Pvt Ltd",
            GstRegitrationType=gst_type,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Main Branch")
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2025-26",
            finstartyear=timezone.make_aware(datetime(2025, 4, 1)),
            finendyear=timezone.make_aware(datetime(2026, 3, 31)),
            createdby=self.user,
        )

    def test_meta_requires_entity(self):
        response = self.client.get(self.meta_url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json().get("detail"), "entity is required.")

    def test_meta_returns_phase0_contract(self):
        response = self.client.get(
            self.meta_url,
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["report_code"], "gstr9")
        self.assertEqual(payload["phase"], 0)
        self.assertEqual(payload["entity_id"], self.entity.id)
        self.assertGreaterEqual(len(payload["tables"]), 1)
        self.assertEqual(payload["filing"]["status"], "phase1_prepared")
        self.assertEqual(payload["filing"]["provider"], "simulated")
        self.assertEqual(payload["endpoints"]["freeze_history"], "/api/reports/gstr9/freeze/history/")
        self.assertEqual(payload["endpoints"]["filing_prepare"], "/api/reports/gstr9/filing/prepare/")
        self.assertEqual(payload["endpoints"]["filing_submit"], "/api/reports/gstr9/filing/submit/")
        self.assertEqual(payload["endpoints"]["filing_status"], "/api/reports/gstr9/filing/status/")

    @patch("reports.gstr9.views.meta.Gstr9MetaAPIView.enforce_entity_scope", side_effect=PermissionDenied("forbidden"))
    def test_meta_denies_when_scope_enforcement_fails(self, _enforce_scope):
        response = self.client.get(
            self.meta_url,
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id},
        )
        self.assertEqual(response.status_code, 403)

    @patch("reports.gstr9.views.utils.assert_any_report_permission", side_effect=PermissionDenied("forbidden"))
    def test_meta_denies_when_report_permission_is_missing(self, _assert_permission):
        response = self.client.get(
            self.meta_url,
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id},
        )
        self.assertEqual(response.status_code, 403)
