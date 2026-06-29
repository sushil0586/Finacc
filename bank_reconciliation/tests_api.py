from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from bank_reconciliation.models import BankReconciliationSession
from entity.models import Entity, EntityBankAccountV2, EntityFinancialYear, GstRegistrationType, SubEntity


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class BankReconciliationOversizedValidationTests(APITestCase):
    def setUp(self):
        self.subscription_patcher = patch("bank_reconciliation.views.SubscriptionService.assert_entity_access", return_value=None)
        self.permission_patcher = patch(
            "bank_reconciliation.views.EffectivePermissionService.permission_codes_for_user",
            return_value={
                "reports.financial_hub.bank_reconciliation.view",
                "reports.financial_hub.bank_reconciliation.create",
                "reports.financial_hub.bank_reconciliation.update",
                "reports.financial_hub.bank_reconciliation.import",
            },
        )
        self.subscription_patcher.start()
        self.permission_patcher.start()
        self.addCleanup(self.subscription_patcher.stop)
        self.addCleanup(self.permission_patcher.stop)

        self.client = APIClient()
        self.user = User.objects.create_user(
            username="bank-reco-user",
            email="bank-reco@example.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.user)

        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Bank Reco Entity",
            entitydesc="Bank reconciliation entity",
            legalname="Bank Reco Entity Pvt Ltd",
            GstRegitrationType=self.gst_type,
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
        self.bank_account = EntityBankAccountV2.objects.create(
            entity=self.entity,
            bank_name="Demo Bank",
            branch="City Branch",
            account_number="123456789012",
            ifsc_code="DEMO0001234",
            createdby=self.user,
        )

    def create_session(self) -> BankReconciliationSession:
        return BankReconciliationSession.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            bank_account=self.bank_account,
            createdby=self.user,
        )

    def test_session_create_rejects_oversized_fields(self):
        response = self.client.post(
            reverse("bank_reconciliation_api:bank-reconciliation-session-list"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "bank_account": self.bank_account.id,
                "statement_label": "L" * 256,
                "source_name": "S" * 256,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("statement_label", response.json())
        self.assertIn("source_name", response.json())

    def test_session_patch_rejects_invalid_status_value(self):
        session = self.create_session()

        response = self.client.patch(
            reverse("bank_reconciliation_api:bank-reconciliation-session-detail", kwargs={"session_id": session.id}),
            {"status": "X" * 50},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("status", response.json())

    def test_manual_import_rejects_oversized_fields(self):
        session = self.create_session()

        response = self.client.post(
            reverse("bank_reconciliation_api:bank-reconciliation-session-imports", kwargs={"session_id": session.id}),
            {
                "rows": [
                    {
                        "description": "D" * 256,
                        "reference_number": "R" * 121,
                        "counterparty": "C" * 256,
                        "currency": "I" * 11,
                        "external_id": "E" * 121,
                        "match_status": "M" * 21,
                        "amount": "100.00",
                    }
                ],
                "source_name": "S" * 256,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("source_name", payload)
        self.assertIn("rows", payload)

    def test_upload_rejects_oversized_fields_and_invalid_column_mapping(self):
        session = self.create_session()
        upload_file = SimpleUploadedFile("statement.csv", b"Date,Description,Amount\n2025-04-01,Demo,100.00\n", content_type="text/csv")

        response = self.client.post(
            reverse("bank_reconciliation_api:bank-reconciliation-session-import-upload", kwargs={"session_id": session.id}),
            {
                "file": upload_file,
                "source_name": "S" * 256,
                "delimiter": "DELIMX",
                "column_mapping": "{invalid-json",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("column_mapping", response.json())

    def test_profile_create_rejects_oversized_fields(self):
        response = self.client.post(
            reverse("bank_reconciliation_api:bank-reconciliation-import-profiles"),
            {
                "entity_id": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "bank_account_id": self.bank_account.id,
                "name": "N" * 256,
                "delimiter": "DELIMX",
                "date_format": "D" * 41,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("name", payload)
        self.assertIn("delimiter", payload)
        self.assertIn("date_format", payload)
