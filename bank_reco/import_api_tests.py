from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from entity.models import Entity, EntityBankAccountV2, EntityFinancialYear, GstRegistrationType, SubEntity
from financial.models import AccountBankDetails, Ledger, account, accountHead
from subscriptions.services import SubscriptionService

from .models import BankStatementImport, BankStatementLine


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class BankRecoImportAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        suffix = uuid4().hex[:8]
        self.user = User.objects.create_user(
            username=f"bank-reco-{suffix}",
            email=f"bank-reco-{suffix}@example.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.user)
        customer_account = SubscriptionService.ensure_customer_account(user=self.user)
        gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Bank Reco Entity",
            legalname="Bank Reco Entity Pvt Ltd",
            GstRegitrationType=gst_type,
            createdby=self.user,
            customer_account=customer_account,
        )
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            year_code="FY2627",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.user,
        )
        self.other_entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2027-28",
            year_code="FY2728",
            finstartyear=timezone.make_aware(datetime(2027, 4, 1)),
            finendyear=timezone.make_aware(datetime(2028, 3, 31)),
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Head Office", is_head_office=True)
        self.other_subentity = SubEntity.objects.create(entity=self.entity, subentityname="Branch Office")
        self.bank_account = EntityBankAccountV2.objects.create(
            entity=self.entity,
            bank_name="HDFC",
            branch="Main",
            account_number="123456789012",
            ifsc_code="HDFC0001234",
            createdby=self.user,
        )
        self.other_bank_account = EntityBankAccountV2.objects.create(
            entity=self.entity,
            bank_name="ICICI",
            branch="City",
            account_number="222233334444",
            ifsc_code="ICIC0004321",
            createdby=self.user,
        )
        self.other_entity = Entity.objects.create(
            entityname="Foreign Scope Entity",
            legalname="Foreign Scope Entity Pvt Ltd",
            GstRegitrationType=gst_type,
            createdby=self.user,
            customer_account=customer_account,
        )
        self.foreign_bank_account = EntityBankAccountV2.objects.create(
            entity=self.other_entity,
            bank_name="Axis",
            branch="Metro",
            account_number="555566667777",
            ifsc_code="UTIB0001234",
            createdby=self.user,
        )

    def _csv_file(self, name: str, body: str):
        return SimpleUploadedFile(name, body.encode("utf-8"), content_type="text/csv")

    def _create_import(self, *, name: str, lines: list[str], bank_account=None, entityfin=None, subentity=None, opening="1000.00", closing="1000.00"):
        bank_account = bank_account or self.bank_account
        entityfin = entityfin or self.entityfin
        payload = {
            "entity": self.entity.id,
            "entityfinid": entityfin.id,
            "bank_account": bank_account.id,
            "source_file_type": "csv",
            "opening_balance": opening,
            "closing_balance": closing,
            "file": self._csv_file(
                name,
                "transaction_date,description,reference_number,debit_amount,credit_amount,balance_amount\n"
                + "\n".join(lines),
            ),
        }
        if subentity is not None:
            payload["subentity"] = subentity.id
        response = self.client.post(reverse("bank_reco_api:bank-reco-import-create"), payload, format="multipart")
        self.assertEqual(response.status_code, 201, response.json())
        return response.json()

    def test_meta_endpoint_returns_accessible_entities_and_active_bank_accounts(self):
        response = self.client.get(
            reverse("bank_reco_api:bank-reco-meta"),
            {"entity": self.entity.id},
        )
        self.assertEqual(response.status_code, 200, response.json())
        payload = response.json()
        self.assertEqual(payload["entities"][0]["id"], self.entity.id)
        self.assertEqual(payload["bank_accounts"][0]["id"], self.bank_account.id)
        self.assertEqual(payload["bank_accounts"][0]["bank_name"], self.bank_account.bank_name)
        self.assertTrue(payload["bank_accounts"][0]["is_active"])
        self.assertIn("bank_charges", payload["voucher_types"])
        self.assertIn("hold_for_review", payload["exception_actions"])
        self.assertIn(BankStatementImport.Status.UPLOADED, payload["statuses"])

    def test_meta_endpoint_prefers_explicit_bank_account_ledger_mapping(self):
        bank_head = accountHead.objects.create(
            entity=self.entity,
            name="Bank Head",
            code=5001,
            drcreffect="Debit",
        )
        bank_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=6001,
            name="Mapped Bank Ledger",
            accounthead=bank_head,
            is_party=True,
            createdby=self.user,
        )
        bank_account_profile = account.objects.create(
            entity=self.entity,
            accountname="Mapped Bank Account",
            ledger=bank_ledger,
            createdby=self.user,
        )
        self.bank_account.book_ledger = bank_ledger
        self.bank_account.save(update_fields=["book_ledger"])

        response = self.client.get(
            reverse("bank_reco_api:bank-reco-meta"),
            {"entity": self.entity.id},
        )

        self.assertEqual(response.status_code, 200, response.json())
        payload = response.json()["bank_accounts"][0]
        self.assertEqual(payload["ledger_id"], bank_ledger.id)
        self.assertEqual(payload["ledger_name"], bank_ledger.name)
        self.assertEqual(bank_account_profile.ledger_id, bank_ledger.id)

    def test_import_csv_creates_import_and_lines_and_workspace_lists_it(self):
        response = self.client.post(
            reverse("bank_reco_api:bank-reco-import-create"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "bank_account": self.bank_account.id,
                "source_file_type": "csv",
                "opening_balance": "1000.00",
                "closing_balance": "1250.00",
                "file": self._csv_file(
                    "statement.csv",
                    "\n".join(
                        [
                            "transaction_date,description,reference_number,debit_amount,credit_amount,balance_amount",
                            "2026-04-01,Salary credit,REF001,0,500,1500",
                            "2026-04-02,ATM withdrawal,REF002,250,0,1250",
                        ]
                    ),
                ),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.json())
        import_id = response.json()["id"]

        self.assertEqual(BankStatementImport.objects.count(), 1)
        self.assertEqual(BankStatementLine.objects.count(), 2)

        lines_response = self.client.get(reverse("bank_reco_api:bank-reco-import-lines", args=[import_id]))
        self.assertEqual(lines_response.status_code, 200)
        self.assertEqual(lines_response.json()["count"], 2)
        self.assertEqual(lines_response.json()["results"][0]["reference_no"], "REF001")

        workspace_response = self.client.get(
            reverse("bank_reco_api:bank-reco-workspace"),
            {"entity": self.entity.id, "entityfinid": self.entityfin.id, "bank_account": self.bank_account.id},
        )
        self.assertEqual(workspace_response.status_code, 200)
        workspace = workspace_response.json()
        self.assertEqual(workspace["imports_count"], 1)
        self.assertEqual(len(workspace["recent_imports"]), 1)

    def test_workspace_summary_scopes_kpis_selected_bank_and_recent_activity(self):
        scoped_import = self._create_import(
            name="scope-statement.csv",
            lines=["2026-04-01,Scoped credit,REF001,0,500,1500"],
            subentity=self.subentity,
            opening="1000.00",
            closing="1500.00",
        )
        self._create_import(
            name="other-scope-statement.csv",
            lines=["2027-04-01,Other scope credit,REF002,0,600,1600"],
            bank_account=self.other_bank_account,
            entityfin=self.other_entityfin,
            subentity=self.other_subentity,
            opening="1000.00",
            closing="1600.00",
        )

        validate_response = self.client.post(reverse("bank_reco_api:bank-reco-import-validate", args=[scoped_import["id"]]))
        self.assertEqual(validate_response.status_code, 200, validate_response.json())

        response = self.client.get(
            reverse("bank_reco_api:bank-reco-workspace"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "bank_account": self.bank_account.id,
            },
        )
        self.assertEqual(response.status_code, 200, response.json())
        payload = response.json()
        self.assertEqual(payload["module"], "bank_reco")
        self.assertEqual(payload["imports_count"], 1)
        self.assertEqual(payload["status_counts"][BankStatementImport.Status.VALIDATED], 1)
        self.assertEqual(payload["status_counts"][BankStatementImport.Status.UPLOADED], 0)
        self.assertEqual(len(payload["recent_imports"]), 1)
        self.assertEqual(payload["recent_imports"][0]["id"], scoped_import["id"])
        self.assertEqual(payload["selected_bank_account"]["id"], self.bank_account.id)
        self.assertEqual(payload["selected_bank_account"]["bank_name"], self.bank_account.bank_name)
        self.assertTrue(payload["recent_activity"])
        self.assertEqual(payload["recent_activity"][0]["bank_account"]["id"], self.bank_account.id)
        self.assertEqual(payload["recent_activity"][0]["actor"], self.user.username)
        self.assertIn(payload["recent_activity"][0]["action"], {"import_created", "import_validated"})

    def test_workspace_summary_returns_no_data_state_for_empty_scope(self):
        response = self.client.get(
            reverse("bank_reco_api:bank-reco-workspace"),
            {
                "entity": self.other_entity.id,
                "bank_account": self.foreign_bank_account.id,
            },
        )
        self.assertEqual(response.status_code, 200, response.json())
        payload = response.json()
        self.assertEqual(payload["imports_count"], 0)
        self.assertEqual(payload["recent_imports"], [])
        self.assertEqual(payload["recent_activity"], [])
        self.assertEqual(payload["selected_bank_account"]["id"], self.foreign_bank_account.id)

    def test_import_rejects_duplicate_file_hash_for_same_bank_account(self):
        payload = {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "bank_account": self.bank_account.id,
            "source_file_type": "csv",
            "file": self._csv_file(
                "statement.csv",
                "\n".join(
                    [
                        "transaction_date,description,reference_number,debit_amount,credit_amount,balance_amount",
                        "2026-04-01,Salary credit,REF001,0,500,1500",
                    ]
                ),
            ),
        }
        first = self.client.post(reverse("bank_reco_api:bank-reco-import-create"), payload, format="multipart")
        self.assertEqual(first.status_code, 201)
        second = self.client.post(
            reverse("bank_reco_api:bank-reco-import-create"),
            {
                **payload,
                "file": self._csv_file(
                    "statement.csv",
                    "\n".join(
                        [
                            "transaction_date,description,reference_number,debit_amount,credit_amount,balance_amount",
                            "2026-04-01,Salary credit,REF001,0,500,1500",
                        ]
                    ),
                ),
            },
            format="multipart",
        )
        self.assertEqual(second.status_code, 400)
        self.assertIn("already been imported", str(second.json()))

    def test_import_preview_supports_column_mapping_and_same_period_duplicate_is_blocked(self):
        preview = self.client.post(
            reverse("bank_reco_api:bank-reco-import-preview"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "bank_account": self.bank_account.id,
                "source_file_type": "csv",
                "column_map": json.dumps(
                    {
                        "txn_date": "Txn Dt",
                        "debit_amount": "Withdrawals",
                        "credit_amount": "Deposits",
                        "reference_no": "UTR No",
                        "narration": "Remarks",
                    }
                ),
                "file": self._csv_file(
                    "mapped.csv",
                    "\n".join(
                        [
                            "Txn Dt,Remarks,UTR No,Withdrawals,Deposits,Closing Balance",
                            "2026-04-01,Direct credit,UTR-1,0,2500,2500",
                        ]
                    ),
                ),
            },
            format="multipart",
        )
        self.assertEqual(preview.status_code, 200, preview.json())
        self.assertEqual(preview.json()["suggested_column_map"]["txn_date"], "Txn Dt")
        self.assertFalse(preview.json()["mapping_errors"])

        payload = {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "bank_account": self.bank_account.id,
            "source_file_type": "csv",
            "statement_from": "2026-04-01",
            "statement_to": "2026-04-30",
            "column_map": json.dumps(
                {
                    "txn_date": "Txn Dt",
                    "debit_amount": "Withdrawals",
                    "credit_amount": "Deposits",
                    "reference_no": "UTR No",
                    "narration": "Remarks",
                }
            ),
            "file": self._csv_file(
                "mapped.csv",
                "\n".join(
                    [
                        "Txn Dt,Remarks,UTR No,Withdrawals,Deposits,Closing Balance",
                        "2026-04-01,Direct credit,UTR-1,0,2500,2500",
                    ]
                ),
            ),
        }
        first = self.client.post(reverse("bank_reco_api:bank-reco-import-create"), payload, format="multipart")
        self.assertEqual(first.status_code, 201, first.json())
        second = self.client.post(
            reverse("bank_reco_api:bank-reco-import-create"),
            {
                **payload,
                "file": self._csv_file(
                    "mapped-second.csv",
                    "\n".join(
                        [
                            "Txn Dt,Remarks,UTR No,Withdrawals,Deposits,Closing Balance",
                            "2026-04-02,Direct credit,UTR-2,0,1000,3500",
                        ]
                    ),
                ),
            },
            format="multipart",
        )
        self.assertEqual(second.status_code, 400)
        self.assertIn("statement period", str(second.json()).lower())

    def test_import_preview_rejects_missing_mandatory_columns(self):
        preview = self.client.post(
            reverse("bank_reco_api:bank-reco-import-preview"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "bank_account": self.bank_account.id,
                "source_file_type": "csv",
                "file": self._csv_file(
                    "bad-mapping.csv",
                    "\n".join(
                        [
                            "Narration,Amount",
                            "Only row,2500",
                        ]
                    ),
                ),
            },
            format="multipart",
        )
        self.assertEqual(preview.status_code, 200, preview.json())
        self.assertTrue(preview.json()["mapping_errors"])

    def test_repeated_preview_does_not_create_imports_or_lines(self):
        payload = {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.subentity.id,
            "bank_account": self.bank_account.id,
            "source_file_type": "csv",
            "file": self._csv_file(
                "preview-only.csv",
                "\n".join(
                    [
                        "transaction_date,description,reference_number,debit_amount,credit_amount,balance_amount",
                        "2026-04-01,Preview only,PREV001,0,500,1500",
                    ]
                ),
            ),
        }
        first = self.client.post(reverse("bank_reco_api:bank-reco-import-preview"), payload, format="multipart")
        self.assertEqual(first.status_code, 200, first.json())
        second = self.client.post(
            reverse("bank_reco_api:bank-reco-import-preview"),
            {
                **payload,
                "file": self._csv_file(
                    "preview-only-again.csv",
                    "\n".join(
                        [
                            "transaction_date,description,reference_number,debit_amount,credit_amount,balance_amount",
                            "2026-04-01,Preview only,PREV001,0,500,1500",
                        ]
                    ),
                ),
            },
            format="multipart",
        )
        self.assertEqual(second.status_code, 200, second.json())
        self.assertEqual(BankStatementImport.objects.count(), 0)
        self.assertEqual(BankStatementLine.objects.count(), 0)

    def test_import_create_requires_bank_account(self):
        response = self.client.post(
            reverse("bank_reco_api:bank-reco-import-create"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "source_file_type": "csv",
                "file": self._csv_file(
                    "missing-bank.csv",
                    "\n".join(
                        [
                            "transaction_date,description,reference_number,debit_amount,credit_amount,balance_amount",
                            "2026-04-01,Missing bank,REF001,0,500,1500",
                        ]
                    ),
                ),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("bank_account", response.json())

    def test_import_preview_rejects_bank_account_outside_selected_entity_scope(self):
        response = self.client.post(
            reverse("bank_reco_api:bank-reco-import-preview"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "bank_account": self.foreign_bank_account.id,
                "source_file_type": "csv",
                "file": self._csv_file(
                    "foreign-bank.csv",
                    "\n".join(
                        [
                            "transaction_date,description,reference_number,debit_amount,credit_amount,balance_amount",
                            "2026-04-01,Wrong bank,REF001,0,500,1500",
                        ]
                    ),
                ),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Bank account is not valid for the selected entity.")

    def test_validate_marks_invalid_rows_and_balance_mismatch(self):
        response = self.client.post(
            reverse("bank_reco_api:bank-reco-import-create"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "bank_account": self.bank_account.id,
                "source_file_type": "csv",
                "opening_balance": "999.00",
                "closing_balance": "1300.00",
                "metadata": json.dumps({"statement_account_number": "00001234"}),
                "file": self._csv_file(
                    "statement-invalid.csv",
                    "\n".join(
                        [
                            "transaction_date,description,reference_number,debit_amount,credit_amount,balance_amount",
                            "2026-04-01,Bad row,REF001,100,100,1100",
                            "2026-04-02,Empty amounts,REF002,0,0,1100",
                        ]
                    ),
                ),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.json())
        import_id = response.json()["id"]

        validate_response = self.client.post(reverse("bank_reco_api:bank-reco-import-validate", args=[import_id]))
        self.assertEqual(validate_response.status_code, 200)
        payload = validate_response.json()
        self.assertEqual(payload["status"], BankStatementImport.Status.REJECTED)
        self.assertEqual(payload["invalid_line_count"], 2)
        self.assertIn("Opening balance mismatch", " ".join(payload["validation_summary"]["import_errors"]))
        self.assertIn("Closing balance mismatch", " ".join(payload["validation_summary"]["import_errors"]))
        self.assertIn("Statement account number does not match", " ".join(payload["validation_summary"]["import_errors"]))

        line = BankStatementLine.objects.get(statement_import_id=import_id, line_no=1)
        self.assertEqual(line.validation_status, BankStatementLine.ValidationStatus.INVALID)
        self.assertTrue(any("Both debit and credit" in item for item in line.validation_errors))
