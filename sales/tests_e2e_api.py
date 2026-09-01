from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from catalog.models import Product, ProductCategory, UnitOfMeasure
from entity.models import Entity, EntityAddress, EntityFinancialYear, EntityGstRegistration, GstRegistrationType, SubEntity
from financial.models import AccountAddress, AccountCommercialProfile, AccountComplianceProfile, Ledger, ShippingDetails, account, accountHead, accounttype
from financial.services import create_account_with_synced_ledger
from geography.models import City, Country, District, State
from numbering.models import DocumentNumberSeries, DocumentType
from posting.models import Entry, EntryStatus, JournalLine, PostingBatch, TxnType
from sales.models import SalesInvoiceHeader, SalesInvoiceLine, SalesLockPeriod
from sales.models.sales_addons import SalesChargeLine, SalesChargeType
from sales.models.sales_ar import CustomerBillOpenItem, CustomerSettlement
from sales.models.sales_compliance import SalesEInvoice, SalesEInvoiceStatus, SalesEWayBill, SalesEWayStatus
from sales.services.sales_settings_service import SalesSettingsService


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class SalesApiEndToEndTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="sales-e2e-user",
            email="sales-e2e@example.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.user)

        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state_home = State.objects.create(statename="Maharashtra", statecode="27", country=self.country)
        self.state_other = State.objects.create(statename="Karnataka", statecode="29", country=self.country)
        self.district = District.objects.create(districtname="District", districtcode="D1", state=self.state_home)
        self.city = City.objects.create(cityname="Mumbai", citycode="MUM", pincode="400001", distt=self.district)
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")

        self.entity = Entity.objects.create(
            entityname="Sales E2E Entity",
            legalname="Sales E2E Entity Pvt Ltd",
            business_type=Entity.BusinessType.MIXED,
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Head Office")
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.user,
        )
        EntityAddress.objects.create(
            entity=self.entity,
            address_type=EntityAddress.AddressType.REGISTERED,
            line1="Address 1",
            country=self.country,
            state=self.state_home,
            district=self.district,
            city=self.city,
            pincode="400001",
            is_primary=True,
            createdby=self.user,
        )
        EntityGstRegistration.objects.create(
            entity=self.entity,
            gstin="27AAAAA1234A1Z5",
            registration_type=self.gst_type,
            state=self.state_home,
            is_primary=True,
            createdby=self.user,
        )

        self.acc_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Receivables",
            accounttypecode="AR001",
            createdby=self.user,
        )
        self.customer_head = accountHead.objects.create(
            entity=self.entity,
            name="Sundry Debtors",
            code=1100,
            balanceType="Debit",
            drcreffect="Debit",
            accounttype=self.acc_type,
            createdby=self.user,
        )
        self.income_head = accountHead.objects.create(
            entity=self.entity,
            name="Sales",
            code=4000,
            balanceType="Credit",
            drcreffect="Credit",
            accounttype=self.acc_type,
            createdby=self.user,
        )

        customer_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=9001,
            name="Customer-A",
            accounthead=self.customer_head,
            createdby=self.user,
        )
        self.customer = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity,
                "ledger": customer_ledger,
                "accountname": "Customer-A",
                "createdby": self.user,
            },
            ledger_overrides={"ledger_code": 9001, "accounthead": self.customer_head, "is_party": True},
        )
        AccountCommercialProfile.objects.update_or_create(
            account=self.customer,
            defaults={"entity": self.entity, "partytype": "Customer", "createdby": self.user},
        )
        AccountComplianceProfile.objects.update_or_create(
            account=self.customer,
            defaults={"entity": self.entity, "gstno": "27ABCDE1234F1Z5", "createdby": self.user},
        )
        AccountAddress.objects.create(
            account=self.customer,
            entity=self.entity,
            createdby=self.user,
            address_type=AccountAddress.AddressType.BILLING,
            line1="Customer-A Billing",
            country=self.country,
            state=self.state_home,
            district=self.district,
            city=self.city,
            pincode="400001",
            isprimary=True,
        )
        ShippingDetails.objects.create(
            account=self.customer,
            entity=self.entity,
            createdby=self.user,
            full_name="Customer-A Shipping",
            country=self.country,
            state=self.state_home,
            district=self.district,
            city=self.city,
            pincode="400001",
            isprimary=True,
        )

        service_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=5001,
            name="Consulting Income",
            accounthead=self.income_head,
            createdby=self.user,
        )
        self.service_sales_account = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity,
                "ledger": service_ledger,
                "accountname": "Consulting Income",
                "createdby": self.user,
            },
            ledger_overrides={"ledger_code": 5001, "accounthead": self.income_head, "is_party": False},
        )

        self.uom = UnitOfMeasure.objects.create(entity=self.entity, code="NOS", description="Numbers")
        self.product_category = ProductCategory.objects.create(entity=self.entity, pcategoryname="Goods")
        self.goods_product = Product.objects.create(
            entity=self.entity,
            productname="Product-A",
            sku="PRD-A",
            productdesc="Goods product",
            productcategory=self.product_category,
            base_uom=self.uom,
            is_service=False,
        )

        self.sales_doc_type = DocumentType.objects.create(
            module="sales",
            name="Sales Tax Invoice",
            doc_key="sales_invoice",
            default_code="SINV",
            is_active=True,
        )
        self.sales_credit_note_doc_type = DocumentType.objects.create(
            module="sales",
            name="Sales Credit Note",
            doc_key="sales_credit_note",
            default_code="SCN",
            is_active=True,
        )
        self.sales_debit_note_doc_type = DocumentType.objects.create(
            module="sales",
            name="Sales Debit Note",
            doc_key="sales_debit_note",
            default_code="SDN",
            is_active=True,
        )
        for doc_type, code, prefix in (
            (self.sales_doc_type, "SINV", "SI"),
            (self.sales_credit_note_doc_type, "SCN", "SCN"),
            (self.sales_debit_note_doc_type, "SDN", "SDN"),
        ):
            DocumentNumberSeries.objects.create(
                entity=self.entity,
                entityfinid=self.entityfin,
                subentity=self.subentity,
                doc_type=doc_type,
                doc_code=code,
                prefix=prefix,
                starting_number=1001,
                current_number=1001,
                is_active=True,
                created_by=self.user,
            )

        self._entity_scope_patch = patch(
            "sales.views.sales_invoice_views.EffectivePermissionService.entity_for_user",
            side_effect=lambda _user, entity_id: SimpleNamespace(id=int(entity_id)),
        )
        self._ar_scope_patch = patch(
            "sales.views.sales_ar.require_sales_scope_permission",
            side_effect=lambda **kwargs: self.entity,
        )
        self._codes_patch = patch(
            "sales.views.sales_invoice_views.EffectivePermissionService.permission_codes_for_user",
            return_value={
                "sales.invoice.view",
                "sales.invoice.read",
                "sales.invoice.list",
                "sales.invoice.create",
                "sales.invoice.update",
                "sales.invoice.edit",
                "sales.invoice.delete",
                "sales.invoice.confirm",
                "sales.invoice.post",
                "sales.invoice.unpost",
                "sales.invoice.cancel",
                "sales.credit_note.view",
                "sales.credit_note.read",
                "sales.credit_note.list",
                "sales.credit_note.create",
                "sales.credit_note.update",
                "sales.credit_note.edit",
                "sales.credit_note.confirm",
                "sales.credit_note.post",
                "sales.credit_note.unpost",
                "sales.credit_note.cancel",
                "sales.debit_note.view",
                "sales.debit_note.read",
                "sales.debit_note.list",
                "sales.debit_note.create",
                "sales.debit_note.update",
                "sales.debit_note.edit",
                "sales.debit_note.confirm",
                "sales.debit_note.post",
                "sales.debit_note.unpost",
                "sales.debit_note.cancel",
            },
        )
        self._entity_scope_patch.start()
        self._ar_scope_patch.start()
        self._codes_patch.start()
        self.addCleanup(self._entity_scope_patch.stop)
        self.addCleanup(self._ar_scope_patch.stop)
        self.addCleanup(self._codes_patch.stop)

    def _scope_qs(self) -> str:
        return f"?entity_id={self.entity.id}&entityfinid={self.entityfin.id}&subentity_id={self.subentity.id}"

    def _attachment_scope_qs(self) -> str:
        return f"?entity={self.entity.id}&entityfinid={self.entityfin.id}&subentity={self.subentity.id}"

    def _goods_line_payload(self, *, qty: str = "10.000", rate: str = "100.0000", **overrides) -> dict:
        payload = {
            "id": None,
            "line_no": 1,
            "product": self.goods_product.id,
            "uom": self.uom.id,
            "hsn_sac_code": "8471",
            "qty": qty,
            "free_qty": "0.000",
            "rate": rate,
            "productDesc": "Test goods",
            "is_service": False,
            "discount_type": 0,
            "discount_percent": "0.0000",
            "discount_amount": "0.00",
            "gst_rate": "18.00",
            "cess_percent": "0.00",
            "cess_amount": "0.00",
        }
        payload.update(overrides)
        return payload

    def _service_line_payload(self) -> dict:
        return {
            "id": None,
            "line_no": 1,
            "product": None,
            "sales_account": self.service_sales_account.id,
            "uom": None,
            "hsn_sac_code": "9983",
            "qty": "1.000",
            "free_qty": "0.000",
            "rate": "500.0000",
            "productDesc": "Consulting",
            "is_service": True,
            "discount_type": 0,
            "discount_percent": "0.0000",
            "discount_amount": "0.00",
            "gst_rate": "18.00",
            "cess_percent": "0.00",
            "cess_amount": "0.00",
        }

    def _invoice_payload(self, *, lines: list[dict], doc_type: int | None = None, reference: str = "SO-001", **overrides) -> dict:
        payload = {
            "doc_type": int(doc_type or SalesInvoiceHeader.DocType.TAX_INVOICE),
            "bill_date": "2026-04-10",
            "credit_days": 5,
            "doc_code": "SINV",
            "customer": self.customer.id,
            "customer_name": "Customer-A",
            "customer_gstin": "27ABCDE1234F1Z5",
            "customer_state_code": "27",
            "seller_gstin": "27AAAAA1234A1Z5",
            "seller_state_code": "27",
            "place_of_supply_state_code": "29",
            "supply_category": int(SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B),
            "taxability": int(SalesInvoiceHeader.Taxability.TAXABLE),
            "reference": reference,
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.subentity.id,
            "lines": lines,
            "charges": [],
            "custom_fields": {},
            "withholding_enabled": False,
        }
        payload.update(overrides)
        return payload

    def _create_invoice(self, *, lines: list[dict] | None = None, endpoint: str = "/api/sales/invoices/", **payload_overrides) -> dict:
        payload = self._invoice_payload(lines=lines or [self._goods_line_payload()])
        payload.update(payload_overrides)
        response = self.client.post(endpoint, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        return response.json()

    def _seed_posting_entry(
        self,
        *,
        header: SalesInvoiceHeader,
        txn_type: str,
        amount: Decimal,
        narration: str,
        customer_drcr: bool,
        revenue_drcr: bool,
        customer_description: str,
        revenue_description: str,
    ) -> Entry:
        batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=txn_type,
            txn_id=header.id,
            voucher_no=header.invoice_number,
            revision=1,
            is_active=True,
            created_by=self.user,
        )
        entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=txn_type,
            txn_id=header.id,
            voucher_no=header.invoice_number,
            voucher_date=header.bill_date,
            posting_date=header.posting_date or header.bill_date,
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=batch,
            narration=narration,
            created_by=self.user,
        )
        JournalLine.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=txn_type,
            txn_id=header.id,
            voucher_no=header.invoice_number,
            accounthead=self.customer_head,
            drcr=customer_drcr,
            amount=amount,
            description=customer_description,
            posting_date=header.posting_date or header.bill_date,
            posted_at=timezone.now(),
            created_by=self.user,
        )
        JournalLine.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=txn_type,
            txn_id=header.id,
            voucher_no=header.invoice_number,
            accounthead=self.income_head,
            drcr=revenue_drcr,
            amount=amount,
            description=revenue_description,
            posting_date=header.posting_date or header.bill_date,
            posted_at=timezone.now(),
            created_by=self.user,
        )
        return entry

    def test_create_goods_invoice_with_new_line_id_null(self):
        body = self._create_invoice()
        self.assertIn("id", body)
        self.assertEqual(body["status"], int(SalesInvoiceHeader.Status.DRAFT))
        self.assertEqual(len(body["lines"]), 1)
        self.assertIsNotNone(body["lines"][0]["id"])

    def test_patch_updates_draft_invoice_header_fields(self):
        created = self._create_invoice(reference="SO-UPD")
        invoice_id = created["id"]

        patch_resp = self.client.patch(
            f"/api/sales/invoices/{invoice_id}/{self._scope_qs()}",
            {"reference": "SO-UPD-EDITED", "remarks": "Draft updated"},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.json())
        body = patch_resp.json()
        self.assertEqual(body["reference"], "SO-UPD-EDITED")
        self.assertEqual(body["remarks"], "Draft updated")
        self.assertEqual(body["status"], int(SalesInvoiceHeader.Status.DRAFT))

    def test_patch_can_replace_deleted_line_with_new_line_reusing_same_line_no(self):
        created = self._create_invoice(reference="SO-REPLACE-LINE")
        invoice_id = created["id"]

        replacement_line = self._goods_line_payload(qty="12.000", rate="150.0000")
        replacement_line["id"] = None
        replacement_line["line_no"] = created["lines"][0]["line_no"]
        replacement_line["productDesc"] = "Replacement goods"

        patch_resp = self.client.patch(
            f"/api/sales/invoices/{invoice_id}/{self._scope_qs()}",
            {"lines": [replacement_line]},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.json())

        lines = list(SalesInvoiceLine.objects.filter(header_id=invoice_id).order_by("line_no", "id"))
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].line_no, 1)
        self.assertEqual(lines[0].productDesc, "Replacement goods")
        self.assertEqual(lines[0].qty, Decimal("12.000"))
        self.assertEqual(lines[0].rate, Decimal("150.0000"))

    def test_delete_draft_invoice_is_allowed(self):
        created = self._create_invoice(reference="SO-DEL-DRAFT")
        invoice_id = created["id"]

        delete_resp = self.client.delete(
            f"/api/sales/invoices/{invoice_id}/{self._scope_qs()}",
            format="json",
        )
        self.assertEqual(delete_resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(SalesInvoiceHeader.objects.filter(pk=invoice_id).exists())

    def test_delete_confirmed_invoice_is_blocked_by_draft_only_policy(self):
        settings_obj = SalesSettingsService.get_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            entityfinid_id=self.entityfin.id,
        )
        settings_obj.policy_controls = {"delete_policy": "draft_only"}
        settings_obj.save(update_fields=["policy_controls"])

        created = self._create_invoice(reference="SO-DEL-BLOCK")
        invoice_id = created["id"]
        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        delete_resp = self.client.delete(
            f"/api/sales/invoices/{invoice_id}/{self._scope_qs()}",
            format="json",
        )
        self.assertEqual(delete_resp.status_code, status.HTTP_400_BAD_REQUEST, delete_resp.json())
        self.assertIn("Only draft sale invoices can be deleted", str(delete_resp.json()))

    def test_create_sales_invoice_rejects_line_amount_mismatch_when_policy_is_hard(self):
        settings_obj = SalesSettingsService.get_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            entityfinid_id=self.entityfin.id,
        )
        settings_obj.policy_controls = {"line_amount_mismatch": "hard"}
        settings_obj.save(update_fields=["policy_controls"])

        mismatched_line = self._goods_line_payload()
        mismatched_line["taxable_value"] = "999.00"
        payload = self._invoice_payload(lines=[mismatched_line], reference="SO-MISMATCH-HARD")

        response = self.client.post("/api/sales/invoices/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.json())
        self.assertIn("Line 1: sent 999.00 but expected 1000.00", str(response.json()))

    def test_create_sales_invoice_normalizes_line_amount_mismatch_when_policy_is_off(self):
        settings_obj = SalesSettingsService.get_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            entityfinid_id=self.entityfin.id,
        )
        settings_obj.policy_controls = {"line_amount_mismatch": "off"}
        settings_obj.save(update_fields=["policy_controls"])

        mismatched_line = self._goods_line_payload()
        mismatched_line["taxable_value"] = "999.00"
        payload = self._invoice_payload(lines=[mismatched_line], reference="SO-MISMATCH-OFF")

        response = self.client.post("/api/sales/invoices/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        body = response.json()
        self.assertEqual(len(body["lines"]), 1)
        self.assertEqual(Decimal(str(body["lines"][0]["taxable_value"])), Decimal("1000.00"))
        self.assertEqual(Decimal(str(body["lines"][0]["igst_amount"])), Decimal("180.00"))
        self.assertEqual(Decimal(str(body["lines"][0]["line_total"])), Decimal("1180.00"))

        line = SalesInvoiceLine.objects.get(header_id=body["id"], line_no=1)
        self.assertEqual(line.taxable_value, Decimal("1000.00"))
        self.assertEqual(line.igst_amount, Decimal("180.00"))
        self.assertEqual(line.line_total, Decimal("1180.00"))

    def test_create_sales_invoice_normalizes_line_amount_mismatch_when_policy_is_warn(self):
        settings_obj = SalesSettingsService.get_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            entityfinid_id=self.entityfin.id,
        )
        settings_obj.policy_controls = {"line_amount_mismatch": "warn"}
        settings_obj.save(update_fields=["policy_controls"])

        mismatched_line = self._goods_line_payload()
        mismatched_line["taxable_value"] = "999.00"
        payload = self._invoice_payload(lines=[mismatched_line], reference="SO-MISMATCH-WARN")

        response = self.client.post("/api/sales/invoices/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        body = response.json()
        self.assertEqual(len(body["lines"]), 1)
        self.assertEqual(Decimal(str(body["lines"][0]["taxable_value"])), Decimal("1000.00"))
        self.assertEqual(Decimal(str(body["lines"][0]["igst_amount"])), Decimal("180.00"))
        self.assertEqual(Decimal(str(body["lines"][0]["line_total"])), Decimal("1180.00"))

        line = SalesInvoiceLine.objects.get(header_id=body["id"], line_no=1)
        self.assertEqual(line.taxable_value, Decimal("1000.00"))
        self.assertEqual(line.igst_amount, Decimal("180.00"))
        self.assertEqual(line.line_total, Decimal("1180.00"))

    def test_create_sales_invoice_allows_header_only_draft_when_require_lines_policy_is_off(self):
        settings_obj = SalesSettingsService.get_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            entityfinid_id=self.entityfin.id,
        )
        settings_obj.policy_controls = {"require_lines_on_confirm": "off"}
        settings_obj.save(update_fields=["policy_controls"])

        payload = self._invoice_payload(lines=[], reference="SO-HDR-OFF")
        response = self.client.post("/api/sales/invoices/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        body = response.json()
        self.assertEqual(body["status"], int(SalesInvoiceHeader.Status.DRAFT))
        self.assertEqual(len(body["lines"]), 0)

    def test_create_sales_invoice_allows_header_only_draft_when_require_lines_policy_is_warn(self):
        settings_obj = SalesSettingsService.get_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            entityfinid_id=self.entityfin.id,
        )
        settings_obj.policy_controls = {"require_lines_on_confirm": "warn"}
        settings_obj.save(update_fields=["policy_controls"])

        payload = self._invoice_payload(lines=[], reference="SO-HDR-WARN")
        response = self.client.post("/api/sales/invoices/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        body = response.json()
        self.assertEqual(body["status"], int(SalesInvoiceHeader.Status.DRAFT))
        self.assertEqual(len(body["lines"]), 0)

    def test_confirm_sales_invoice_allows_header_only_draft_when_require_lines_policy_is_warn(self):
        settings_obj = SalesSettingsService.get_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            entityfinid_id=self.entityfin.id,
        )
        settings_obj.policy_controls = {"require_lines_on_confirm": "warn"}
        settings_obj.save(update_fields=["policy_controls"])

        payload = self._invoice_payload(lines=[], reference="SO-HDR-WARN-CONF")
        create_response = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED, create_response.json())
        invoice_id = create_response.json()["id"]

        confirm_response = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK, confirm_response.json())
        self.assertEqual(confirm_response.json()["status"], int(SalesInvoiceHeader.Status.CONFIRMED))

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesArService.sync_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_same_state_taxable_invoice_uses_cgst_sgst_through_posting_flow(
        self,
        mocked_post_adapter,
        mocked_sync_open_item,
        mocked_auto_compliance,
    ):
        body = self._create_invoice(
            reference="SO-SAME-STATE",
            customer_state_code="27",
            place_of_supply_state_code="27",
        )
        invoice_id = body["id"]
        self.assertFalse(body["is_igst"])
        self.assertEqual(Decimal(str(body["total_taxable_value"])), Decimal("1000.00"))
        self.assertEqual(Decimal(str(body["total_cgst"])), Decimal("90.00"))
        self.assertEqual(Decimal(str(body["total_sgst"])), Decimal("90.00"))
        self.assertEqual(Decimal(str(body["total_igst"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(body["grand_total"])), Decimal("1180.00"))

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())
        post_body = post_resp.json()
        self.assertEqual(post_body["status"], int(SalesInvoiceHeader.Status.POSTED))
        self.assertFalse(post_body["is_igst"])
        self.assertEqual(Decimal(str(post_body["total_cgst"])), Decimal("90.00"))
        self.assertEqual(Decimal(str(post_body["total_sgst"])), Decimal("90.00"))
        self.assertEqual(Decimal(str(post_body["total_igst"])), Decimal("0.00"))

        header = SalesInvoiceHeader.objects.get(pk=invoice_id)
        self.assertFalse(header.is_igst)
        self.assertEqual(str(header.place_of_supply_state_code), "27")
        mocked_post_adapter.assert_called_once()
        mocked_sync_open_item.assert_called_once()
        mocked_auto_compliance.assert_called()

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesArService.sync_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_interstate_taxable_invoice_uses_igst_through_posting_flow(
        self,
        mocked_post_adapter,
        mocked_sync_open_item,
        mocked_auto_compliance,
    ):
        body = self._create_invoice(
            reference="SO-INTERSTATE",
            customer_state_code="29",
            place_of_supply_state_code="29",
        )
        invoice_id = body["id"]
        self.assertTrue(body["is_igst"])
        self.assertEqual(Decimal(str(body["total_taxable_value"])), Decimal("1000.00"))
        self.assertEqual(Decimal(str(body["total_cgst"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(body["total_sgst"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(body["total_igst"])), Decimal("180.00"))
        self.assertEqual(Decimal(str(body["grand_total"])), Decimal("1180.00"))

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())
        post_body = post_resp.json()
        self.assertEqual(post_body["status"], int(SalesInvoiceHeader.Status.POSTED))
        self.assertTrue(post_body["is_igst"])
        self.assertEqual(Decimal(str(post_body["total_cgst"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(post_body["total_sgst"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(post_body["total_igst"])), Decimal("180.00"))

        header = SalesInvoiceHeader.objects.get(pk=invoice_id)
        self.assertTrue(header.is_igst)
        self.assertEqual(str(header.place_of_supply_state_code), "29")
        mocked_post_adapter.assert_called_once()
        mocked_sync_open_item.assert_called_once()
        mocked_auto_compliance.assert_called()

    def test_patch_recomputes_tax_regime_when_stale_seller_state_placeholder_is_sent(self):
        created = self._create_invoice(
            reference="SO-SELLER-STATE-RECOVER",
            customer_state_code="29",
            place_of_supply_state_code="29",
        )
        invoice_id = created["id"]
        self.assertTrue(created["is_igst"])

        patch_resp = self.client.patch(
            f"/api/sales/invoices/{invoice_id}/{self._scope_qs()}",
            {
                "seller_state_code": "0",
                "customer_state_code": "27",
                "place_of_supply_state_code": "27",
            },
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.json())

        body = patch_resp.json()
        self.assertEqual(body["seller_state_code"], "27")
        self.assertEqual(body["place_of_supply_state_code"], "27")
        self.assertEqual(body["tax_regime"], int(SalesInvoiceHeader.TaxRegime.INTRA_STATE))
        self.assertFalse(body["is_igst"])

        header = SalesInvoiceHeader.objects.get(pk=invoice_id)
        self.assertEqual(str(header.seller_state_code), "27")
        self.assertEqual(str(header.place_of_supply_state_code), "27")
        self.assertEqual(int(header.tax_regime), int(SalesInvoiceHeader.TaxRegime.INTRA_STATE))
        self.assertFalse(header.is_igst)

    def test_patch_normalizes_alpha_state_aliases_before_tax_regime_recompute(self):
        created = self._create_invoice(
            reference="SO-STATE-ALIAS-NORMALIZE",
            customer_state_code="29",
            place_of_supply_state_code="29",
        )
        invoice_id = created["id"]
        self.assertTrue(created["is_igst"])

        patch_resp = self.client.patch(
            f"/api/sales/invoices/{invoice_id}/{self._scope_qs()}",
            {
                "seller_state_code": "MH",
                "customer_state_code": "MH",
                "place_of_supply_state_code": "MH",
            },
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.json())

        body = patch_resp.json()
        self.assertEqual(body["seller_state_code"], "27")
        self.assertEqual(body["customer_state_code"], "27")
        self.assertEqual(body["place_of_supply_state_code"], "27")
        self.assertEqual(body["tax_regime"], int(SalesInvoiceHeader.TaxRegime.INTRA_STATE))
        self.assertFalse(body["is_igst"])

        header = SalesInvoiceHeader.objects.get(pk=invoice_id)
        self.assertEqual(str(header.seller_state_code), "27")
        self.assertEqual(str(header.customer_state_code), "27")
        self.assertEqual(str(header.place_of_supply_state_code), "27")
        self.assertEqual(int(header.tax_regime), int(SalesInvoiceHeader.TaxRegime.INTRA_STATE))
        self.assertFalse(header.is_igst)

    def test_service_invoice_endpoints_only_return_service_rows(self):
        self._create_invoice(reference="SO-GOODS", lines=[self._goods_line_payload()])
        self._create_invoice(
            endpoint="/api/sales/service-invoices/",
            reference="SO-SERVICE",
            lines=[self._service_line_payload()],
        )

        goods_resp = self.client.get(f"/api/sales/invoices/{self._scope_qs()}&line_mode=goods")
        self.assertEqual(goods_resp.status_code, status.HTTP_200_OK)
        goods_rows = goods_resp.json()
        self.assertEqual(len(goods_rows), 1)
        self.assertEqual(goods_rows[0]["customer_name"], "Customer-A")

    def test_service_invoice_charges_round_trip_through_create_and_detail(self):
        charge_type = SalesChargeType.objects.create(
            entity=self.entity,
            code="LAUNCH_FREIGHT_18",
            name="Launch Freight Charge 18%",
            base_category=SalesChargeType.BaseCategory.FREIGHT,
            is_active=True,
            is_service=True,
            hsn_sac_code_default="996511",
            gst_rate_default=Decimal("18.00"),
            revenue_account=self.service_sales_account,
            created_by=self.user,
            updated_by=self.user,
        )
        payload = self._invoice_payload(
            lines=[{**self._service_line_payload(), "rate": "100.0000"}],
            reference="SO-SERVICE-CHARGE",
            charges=[
                {
                    "line_no": 1,
                    "charge_type_id": charge_type.id,
                    "description": "Taxable launch validation freight charge",
                    "taxability": "TAXABLE",
                    "is_service": True,
                    "hsn_sac_code": "996511",
                    "taxable_value": "100.00",
                    "gst_rate": "18.00",
                }
            ],
        )
        response = self.client.post("/api/sales/service-invoices/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())

        invoice_id = response.json()["id"]
        self.assertEqual(SalesChargeLine.objects.filter(header_id=invoice_id).count(), 1)

        detail_response = self.client.get(f"/api/sales/service-invoices/{invoice_id}/{self._scope_qs()}&line_mode=service")
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK, detail_response.json())
        charges = detail_response.json()["charges"]
        self.assertEqual(len(charges), 1)
        self.assertEqual(Decimal(str(charges[0]["taxable_value"])), Decimal("100.00"))
        self.assertEqual(Decimal(str(charges[0]["gst_rate"])), Decimal("18.00"))
        self.assertEqual(Decimal(str(charges[0]["cgst_amount"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(charges[0]["sgst_amount"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(charges[0]["igst_amount"])), Decimal("18.00"))
        self.assertEqual(Decimal(str(charges[0]["total_value"])), Decimal("118.00"))

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_service_credit_note_preserves_edited_place_of_supply_through_confirm_and_post(
        self,
        mocked_post_adapter,
        mocked_auto_compliance,
    ):
        original = self._create_invoice(
            endpoint="/api/sales/service-invoices/",
            reference="SO-SVC-ORIG-POS",
            lines=[self._service_line_payload()],
            place_of_supply_state_code="03",
            seller_state_code="27",
            customer_state_code="27",
        )
        original_id = original["id"]

        note_create_resp = self.client.post(
            "/api/sales/service-invoices/",
            {
                **self._invoice_payload(
                    lines=[self._service_line_payload()],
                    doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
                    reference=original["reference"],
                ),
                "doc_code": "SCN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
                "place_of_supply_state_code": "29",
            },
            format="json",
        )
        self.assertEqual(note_create_resp.status_code, status.HTTP_201_CREATED, note_create_resp.json())
        note_body = note_create_resp.json()
        note_id = note_body["id"]
        self.assertEqual(note_body["place_of_supply_state_code"], "03")

        patch_resp = self.client.patch(
            f"/api/sales/service-invoices/{note_id}/{self._scope_qs()}&line_mode=service",
            {"place_of_supply_state_code": "29"},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.json())
        patched_body = patch_resp.json()
        self.assertEqual(patched_body["place_of_supply_state_code"], "29")
        self.assertEqual(patched_body["tax_regime"], int(SalesInvoiceHeader.TaxRegime.INTER_STATE))

        draft_note = SalesInvoiceHeader.objects.get(pk=note_id)
        self.assertEqual(str(draft_note.place_of_supply_state_code), "29")

        confirm_resp = self.client.post(
            f"/api/sales/service-invoices/{note_id}/confirm/{self._scope_qs()}&line_mode=service",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())
        confirmed_body = confirm_resp.json()
        self.assertEqual(confirmed_body["place_of_supply_state_code"], "29")
        self.assertEqual(confirmed_body["tax_regime"], int(SalesInvoiceHeader.TaxRegime.INTER_STATE))

        post_resp = self.client.post(
            f"/api/sales/service-invoices/{note_id}/post/{self._scope_qs()}&line_mode=service",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())
        posted_body = post_resp.json()
        self.assertEqual(posted_body["place_of_supply_state_code"], "29")
        self.assertEqual(posted_body["tax_regime"], int(SalesInvoiceHeader.TaxRegime.INTER_STATE))

        final_note = SalesInvoiceHeader.objects.get(pk=note_id)
        self.assertEqual(str(final_note.place_of_supply_state_code), "29")
        self.assertEqual(int(final_note.tax_regime), int(SalesInvoiceHeader.TaxRegime.INTER_STATE))
        mocked_post_adapter.assert_called_once()
        self.assertTrue(mocked_auto_compliance.called)

    def test_goods_credit_note_patch_recomputes_tax_scope_from_shipping_detail_even_if_stale_pos_is_sent(self):
        original = self._create_invoice(
            reference="SO-GOODS-ORIG-SHIP-POS",
            lines=[self._goods_line_payload()],
            place_of_supply_state_code="27",
            customer_state_code="27",
        )
        original_id = original["id"]

        note_create_resp = self.client.post(
            f"/api/sales/invoices/{self._scope_qs()}&line_mode=goods",
            {
                **self._invoice_payload(
                    lines=[self._goods_line_payload()],
                    doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
                    reference=original["reference"],
                ),
                "doc_code": "SCN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
            },
            format="json",
        )
        self.assertEqual(note_create_resp.status_code, status.HTTP_201_CREATED, note_create_resp.json())
        note_id = note_create_resp.json()["id"]

        customer = account.objects.get(pk=self.customer.id)
        inter_ship = ShippingDetails.objects.create(
            account=customer,
            entity=self.entity,
            createdby=self.user,
            full_name="Inter Ship",
            address1="Inter State Address",
            country=self.country,
            state=self.state_other,
            pincode="560001",
        )

        patch_resp = self.client.patch(
            f"/api/sales/invoices/{note_id}/{self._scope_qs()}&line_mode=goods",
            {
                "shipping_detail": inter_ship.id,
                "place_of_supply_state_code": "27",
                "tax_regime": int(SalesInvoiceHeader.TaxRegime.INTRA_STATE),
            },
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.json())

        body = patch_resp.json()
        self.assertEqual(body["shipping_detail"], inter_ship.id)
        self.assertEqual(body["place_of_supply_state_code"], "29")
        self.assertEqual(body["tax_regime"], int(SalesInvoiceHeader.TaxRegime.INTER_STATE))
        self.assertTrue(body["is_igst"])

        draft_note = SalesInvoiceHeader.objects.get(pk=note_id)
        self.assertEqual(int(draft_note.shipping_detail_id or 0), inter_ship.id)
        self.assertEqual(str(draft_note.place_of_supply_state_code), "29")
        self.assertEqual(int(draft_note.tax_regime), int(SalesInvoiceHeader.TaxRegime.INTER_STATE))
        self.assertTrue(draft_note.is_igst)

    def test_confirmed_invoice_can_be_found_by_invoice_number_search(self):
        created = self._create_invoice(reference="SO-SEARCH")
        invoice_id = created["id"]
        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        search_resp = self.client.get(
            f"/api/sales/invoices/{self._scope_qs()}&search=SI-SINV-1001&status={int(SalesInvoiceHeader.Status.CONFIRMED)}"
        )
        self.assertEqual(search_resp.status_code, status.HTTP_200_OK)
        rows = search_resp.json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["invoice_number"], "SI-SINV-1001")

    def test_confirm_allocates_doc_number_and_invoice_number(self):
        created = self._create_invoice(reference="SO-CONFIRM")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())
        confirmed = confirm_resp.json()
        self.assertEqual(confirmed["status"], int(SalesInvoiceHeader.Status.CONFIRMED))
        self.assertEqual(confirmed["doc_no"], 1001)
        self.assertEqual(confirmed["invoice_number"], "SI-SINV-1001")

    def test_branch_without_sales_series_inherits_entity_level_shared_numbering(self):
        DocumentNumberSeries.objects.filter(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            doc_type=self.sales_doc_type,
            doc_code="SINV",
        ).delete()
        shared_series = DocumentNumberSeries.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=None,
            doc_type=self.sales_doc_type,
            doc_code="SINV",
            prefix="SROOT",
            starting_number=2001,
            current_number=2001,
            is_active=True,
            created_by=self.user,
        )

        created = self._create_invoice(reference="SO-SHARED-ROOT-NUMBERING")
        confirm_resp = self.client.post(
            f"/api/sales/invoices/{created['id']}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )

        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())
        self.assertEqual(confirm_resp.json()["doc_no"], 2001)
        self.assertEqual(confirm_resp.json()["invoice_number"], "SI-SINV-2001")
        shared_series.refresh_from_db()
        self.assertEqual(shared_series.current_number, 2002)

    def test_sales_branch_specific_series_are_separate_when_configured(self):
        second_branch = SubEntity.objects.create(
            entity=self.entity,
            subentityname="Independent Sales Branch",
        )
        second_series = DocumentNumberSeries.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=second_branch,
            doc_type=self.sales_doc_type,
            doc_code="S2INV",
            prefix="S2",
            starting_number=1001,
            current_number=1001,
            is_active=True,
            created_by=self.user,
        )

        first = self._create_invoice(reference="SO-SEPARATE-BRANCH-1")
        first_confirm = self.client.post(
            f"/api/sales/invoices/{first['id']}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(first_confirm.status_code, status.HTTP_200_OK, first_confirm.json())
        self.assertEqual(first_confirm.json()["doc_no"], 1001)
        self.assertEqual(first_confirm.json()["invoice_number"], "SI-SINV-1001")

        second_scope = f"?entity_id={self.entity.id}&entityfinid={self.entityfin.id}&subentity_id={second_branch.id}"
        second = self._create_invoice(
            reference="SO-SEPARATE-BRANCH-2",
            subentity=second_branch.id,
            doc_code="S2INV",
        )
        second_confirm = self.client.post(
            f"/api/sales/invoices/{second['id']}/confirm/{second_scope}",
            {},
            format="json",
        )

        self.assertEqual(second_confirm.status_code, status.HTTP_200_OK, second_confirm.json())
        self.assertEqual(second_confirm.json()["doc_no"], 1001)
        self.assertEqual(second_confirm.json()["invoice_number"], "SI-S2INV-1001")
        second_series.refresh_from_db()
        self.assertEqual(second_series.current_number, 1002)

    def test_shared_gstin_branch_confirm_skips_duplicate_invoice_number(self):
        second_branch = SubEntity.objects.create(
            entity=self.entity,
            subentityname="Same GSTIN Branch",
        )
        DocumentNumberSeries.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=second_branch,
            doc_type=self.sales_doc_type,
            doc_code="SINV",
            prefix="SI",
            starting_number=1001,
            current_number=1001,
            is_active=True,
            created_by=self.user,
        )

        first = self._create_invoice(reference="SO-SHARED-GST-1")
        first_confirm = self.client.post(
            f"/api/sales/invoices/{first['id']}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(first_confirm.status_code, status.HTTP_200_OK, first_confirm.json())
        self.assertEqual(first_confirm.json()["invoice_number"], "SI-SINV-1001")

        second_scope = f"?entity_id={self.entity.id}&entityfinid={self.entityfin.id}&subentity_id={second_branch.id}"
        second = self._create_invoice(
            reference="SO-SHARED-GST-2",
            subentity=second_branch.id,
            seller_gstin="27AAAAA1234A1Z5",
        )
        second_confirm = self.client.post(
            f"/api/sales/invoices/{second['id']}/confirm/{second_scope}",
            {},
            format="json",
        )
        self.assertEqual(second_confirm.status_code, status.HTTP_200_OK, second_confirm.json())
        self.assertEqual(second_confirm.json()["doc_no"], 1002)
        self.assertEqual(second_confirm.json()["invoice_number"], "SI-SINV-1002")

    def test_different_gstin_branches_can_use_same_sales_invoice_number(self):
        second_branch = SubEntity.objects.create(
            entity=self.entity,
            subentityname="Different GSTIN Branch",
        )
        DocumentNumberSeries.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=second_branch,
            doc_type=self.sales_doc_type,
            doc_code="SINV",
            prefix="SI",
            starting_number=1001,
            current_number=1001,
            is_active=True,
            created_by=self.user,
        )

        first = self._create_invoice(reference="SO-DIFF-GST-1")
        first_confirm = self.client.post(
            f"/api/sales/invoices/{first['id']}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(first_confirm.status_code, status.HTTP_200_OK, first_confirm.json())
        self.assertEqual(first_confirm.json()["invoice_number"], "SI-SINV-1001")

        second_scope = f"?entity_id={self.entity.id}&entityfinid={self.entityfin.id}&subentity_id={second_branch.id}"
        second = self._create_invoice(
            reference="SO-DIFF-GST-2",
            subentity=second_branch.id,
            seller_gstin="29AAAAA1234A1Z5",
            seller_state_code="29",
        )
        second_confirm = self.client.post(
            f"/api/sales/invoices/{second['id']}/confirm/{second_scope}",
            {},
            format="json",
        )

        self.assertEqual(second_confirm.status_code, status.HTTP_200_OK, second_confirm.json())
        self.assertEqual(second_confirm.json()["doc_no"], 1001)
        self.assertEqual(second_confirm.json()["invoice_number"], "SI-SINV-1001")

    def test_same_gstin_invoice_number_is_database_unique_across_branches(self):
        second_branch = SubEntity.objects.create(
            entity=self.entity,
            subentityname="DB Guard Same GSTIN Branch",
        )

        first = self._create_invoice(reference="SO-DB-GSTIN-1")
        first_header = SalesInvoiceHeader.objects.get(pk=first["id"])
        first_header.status = SalesInvoiceHeader.Status.CONFIRMED
        first_header.doc_no = 9001
        first_header.invoice_number = "SI-SINV-9001"
        first_header.save(update_fields=["status", "doc_no", "invoice_number"])

        second = self._create_invoice(
            reference="SO-DB-GSTIN-2",
            subentity=second_branch.id,
            seller_gstin=first_header.seller_gstin,
        )
        second_header = SalesInvoiceHeader.objects.get(pk=second["id"])
        second_header.status = SalesInvoiceHeader.Status.CONFIRMED
        second_header.doc_no = 9001
        second_header.invoice_number = first_header.invoice_number

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                second_header.save(update_fields=["status", "doc_no", "invoice_number"])

    def test_attachment_upload_list_download_delete_and_summary(self):
        created = self._create_invoice(reference="SO-ATTACH")
        invoice_id = created["id"]
        scope = self._attachment_scope_qs()

        upload = SimpleUploadedFile(
            "sales-supporting.pdf",
            b"sales attachment payload",
            content_type="application/pdf",
        )
        upload_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/attachments/{scope}",
            {"attachments": [upload]},
            format="multipart",
        )
        self.assertEqual(upload_resp.status_code, status.HTTP_201_CREATED, upload_resp.json())
        attachment_id = upload_resp.json()["data"][0]["id"]

        list_resp = self.client.get(f"/api/sales/invoices/{invoice_id}/attachments/{scope}")
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK, list_resp.json())
        self.assertEqual(len(list_resp.json()), 1)

        summary_resp = self.client.get(f"/api/sales/invoices/{invoice_id}/summary/{scope}&line_mode=goods")
        self.assertEqual(summary_resp.status_code, status.HTTP_200_OK, summary_resp.json())
        self.assertEqual(len(summary_resp.json().get("attachments", [])), 1)

        detail_resp = self.client.get(
            f"/api/sales/meta/invoice-detail-form/?entity={self.entity.id}&entityfinid={self.entityfin.id}&subentity={self.subentity.id}&invoice={invoice_id}&line_mode=goods"
        )
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK, detail_resp.json())
        self.assertEqual(len(detail_resp.json().get("attachments", [])), 1)
        self.assertEqual(len(detail_resp.json().get("invoice", {}).get("attachments", [])), 1)

        download_resp = self.client.get(
            f"/api/sales/invoices/{invoice_id}/attachments/{attachment_id}/download/{scope}"
        )
        self.assertEqual(download_resp.status_code, status.HTTP_200_OK)
        self.assertIn("attachment;", download_resp.get("Content-Disposition", ""))

        delete_resp = self.client.delete(
            f"/api/sales/invoices/{invoice_id}/attachments/{attachment_id}/{scope}"
        )
        self.assertEqual(delete_resp.status_code, status.HTTP_200_OK, delete_resp.json())

    def test_attachment_upload_rejects_unsupported_text_file(self):
        created = self._create_invoice(reference="SO-ATTACH-BAD")
        invoice_id = created["id"]
        scope = self._attachment_scope_qs()

        upload = SimpleUploadedFile(
            "sales-supporting.txt",
            b"sales attachment payload",
            content_type="text/plain",
        )
        upload_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/attachments/{scope}",
            {"attachments": [upload]},
            format="multipart",
        )

        self.assertEqual(upload_resp.status_code, status.HTTP_400_BAD_REQUEST, upload_resp.json())
        self.assertEqual(upload_resp.json()["detail"], "sales-supporting.txt is not a supported format.")

    def test_confirmed_invoice_can_be_edited_when_policy_allows(self):
        created = self._create_invoice(reference="SO-CONF-EDIT")
        invoice_id = created["id"]
        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        patch_resp = self.client.patch(
            f"/api/sales/invoices/{invoice_id}/{self._scope_qs()}",
            {"reference": "SO-CONF-EDITED", "remarks": "Confirmed edit allowed"},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.json())
        body = patch_resp.json()
        self.assertEqual(body["status"], int(SalesInvoiceHeader.Status.CONFIRMED))
        self.assertEqual(body["reference"], "SO-CONF-EDITED")
        self.assertEqual(body["remarks"], "Confirmed edit allowed")

    def test_confirmed_invoice_edit_is_blocked_when_policy_disables_it(self):
        settings_obj = SalesSettingsService.get_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            entityfinid_id=self.entityfin.id,
        )
        settings_obj.policy_controls = {"allow_edit_confirmed": "off"}
        settings_obj.save(update_fields=["policy_controls"])

        created = self._create_invoice(reference="SO-CONF-EDIT-OFF")
        invoice_id = created["id"]
        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        patch_resp = self.client.patch(
            f"/api/sales/invoices/{invoice_id}/{self._scope_qs()}",
            {"reference": "SO-CONF-EDIT-BLOCKED"},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Confirmed invoice editing is disabled by sales policy.", str(patch_resp.json()))

    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_post_endpoint_auto_confirms_draft_and_returns_posted_invoice(self, _mocked_post_adapter):
        created = self._create_invoice(reference="SO-POST-BLOCK")
        invoice_id = created["id"]

        post_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())
        post_body = post_resp.json()
        self.assertEqual(post_body["id"], invoice_id)
        self.assertEqual(post_body["status"], int(SalesInvoiceHeader.Status.POSTED))
        self.assertTrue(str(post_body.get("invoice_number") or "").strip())
        header = SalesInvoiceHeader.objects.get(pk=invoice_id)
        self.assertEqual(header.status, SalesInvoiceHeader.Status.POSTED)
        self.assertIsNotNone(header.confirmed_at)
        self.assertIsNotNone(header.posted_at)
        self.assertTrue(int(header.doc_no or 0) > 0)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesArService.sync_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_post_confirmed_invoice_marks_posted_and_calls_adapter(
        self,
        mocked_post_adapter,
        mocked_sync_open_item,
        mocked_auto_compliance,
    ):
        created = self._create_invoice(reference="SO-POST")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())
        body = post_resp.json()
        self.assertEqual(body["status"], int(SalesInvoiceHeader.Status.POSTED))
        header = SalesInvoiceHeader.objects.get(pk=invoice_id)
        self.assertIsNotNone(header.posted_at)
        mocked_post_adapter.assert_called_once()
        mocked_sync_open_item.assert_called_once()
        mocked_auto_compliance.assert_called()

    def test_repeated_confirm_call_is_idempotent_for_confirmed_invoice(self):
        created = self._create_invoice(reference="SO-CONFIRM-IDEMPOTENT")
        invoice_id = created["id"]

        first_confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(first_confirm_resp.status_code, status.HTTP_200_OK, first_confirm_resp.json())
        first_body = first_confirm_resp.json()
        self.assertEqual(first_body["status"], int(SalesInvoiceHeader.Status.CONFIRMED))

        header = SalesInvoiceHeader.objects.get(pk=invoice_id)
        first_confirmed_at = header.confirmed_at
        first_doc_no = header.doc_no
        self.assertIsNotNone(first_confirmed_at)

        second_confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(second_confirm_resp.status_code, status.HTTP_200_OK, second_confirm_resp.json())
        second_body = second_confirm_resp.json()
        self.assertEqual(second_body["status"], int(SalesInvoiceHeader.Status.CONFIRMED))

        header.refresh_from_db()
        self.assertEqual(header.confirmed_at, first_confirmed_at)
        self.assertEqual(header.doc_no, first_doc_no)

    def test_confirm_locked_period_sales_is_blocked_when_policy_is_hard(self):
        created = self._create_invoice(
            reference="SO-CONF-LOCK-HARD",
            bill_date="2026-04-10",
        )
        invoice_id = created["id"]

        settings_obj = SalesSettingsService.get_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            entityfinid_id=self.entityfin.id,
        )
        settings_obj.policy_controls = {"confirm_lock_check": "hard"}
        settings_obj.save(update_fields=["policy_controls"])

        SalesLockPeriod.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            lock_date="2026-04-30",
            reason="April books locked",
        )

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_400_BAD_REQUEST, confirm_resp.json())
        self.assertIn("Period is locked up to 2026-04-30", str(confirm_resp.json()))

    def test_confirm_locked_period_sales_is_allowed_when_policy_is_off(self):
        created = self._create_invoice(
            reference="SO-CONF-LOCK-OFF",
            bill_date="2026-04-10",
        )
        invoice_id = created["id"]

        settings_obj = SalesSettingsService.get_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            entityfinid_id=self.entityfin.id,
        )
        settings_obj.policy_controls = {"confirm_lock_check": "off"}
        settings_obj.save(update_fields=["policy_controls"])

        SalesLockPeriod.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            lock_date="2026-04-30",
            reason="April books locked",
        )

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())
        self.assertEqual(confirm_resp.json()["status"], int(SalesInvoiceHeader.Status.CONFIRMED))

    def test_confirm_locked_period_sales_is_allowed_when_policy_is_warn(self):
        created = self._create_invoice(
            reference="SO-CONF-LOCK-WARN",
            bill_date="2026-04-10",
        )
        invoice_id = created["id"]

        settings_obj = SalesSettingsService.get_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            entityfinid_id=self.entityfin.id,
        )
        settings_obj.policy_controls = {"confirm_lock_check": "warn"}
        settings_obj.save(update_fields=["policy_controls"])

        SalesLockPeriod.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            lock_date="2026-04-30",
            reason="April books locked",
        )

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())
        self.assertEqual(confirm_resp.json()["status"], int(SalesInvoiceHeader.Status.CONFIRMED))

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesArService.sync_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_repeated_post_call_is_idempotent_for_posted_invoice(
        self,
        mocked_post_adapter,
        mocked_sync_open_item,
        mocked_auto_compliance,
    ):
        created = self._create_invoice(reference="SO-POST-IDEMPOTENT")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        first_post_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(first_post_resp.status_code, status.HTTP_200_OK, first_post_resp.json())
        first_body = first_post_resp.json()
        self.assertEqual(first_body["status"], int(SalesInvoiceHeader.Status.POSTED))

        header = SalesInvoiceHeader.objects.get(pk=invoice_id)
        first_posted_at = header.posted_at
        self.assertIsNotNone(first_posted_at)

        second_post_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(second_post_resp.status_code, status.HTTP_200_OK, second_post_resp.json())
        second_body = second_post_resp.json()
        self.assertEqual(second_body["status"], int(SalesInvoiceHeader.Status.POSTED))

        header.refresh_from_db()
        self.assertEqual(header.posted_at, first_posted_at)
        mocked_post_adapter.assert_called_once()
        mocked_sync_open_item.assert_called_once()
        mocked_auto_compliance.assert_called()

    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_post_locked_period_sales_is_blocked_when_policy_is_hard(self, _mocked_post_adapter):
        created = self._create_invoice(
            reference="SO-POST-LOCK-HARD",
            bill_date="2026-04-10",
        )
        invoice_id = created["id"]

        settings_obj = SalesSettingsService.get_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            entityfinid_id=self.entityfin.id,
        )
        settings_obj.policy_controls = {"confirm_lock_check": "off"}
        settings_obj.save(update_fields=["policy_controls"])

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        settings_obj.policy_controls = {"confirm_lock_check": "hard"}
        settings_obj.save(update_fields=["policy_controls"])

        SalesLockPeriod.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            lock_date="2026-04-30",
            reason="April books locked",
        )

        post_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_400_BAD_REQUEST, post_resp.json())
        self.assertIn("Period is locked up to 2026-04-30", str(post_resp.json()))

    @patch("sales.services.sales_invoice_service.SalesArService.close_open_item_for_header")
    @patch("sales.services.sales_invoice_service.PostingService.post")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesArService.sync_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_reverse_posted_invoice_marks_confirmed_and_updates_entry(
        self,
        mocked_post_adapter,
        mocked_sync_open_item,
        mocked_auto_compliance,
        mocked_posting_service_post,
        mocked_close_open_item,
    ):
        created = self._create_invoice(reference="SO-REVERSE")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        header = SalesInvoiceHeader.objects.get(pk=invoice_id)
        batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=header.id,
            voucher_no=header.invoice_number,
            revision=1,
            is_active=True,
            created_by=self.user,
        )
        entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=header.id,
            voucher_no=header.invoice_number,
            voucher_date=header.bill_date,
            posting_date=header.posting_date or header.bill_date,
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=batch,
            narration="Original posting",
            created_by=self.user,
        )
        JournalLine.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=header.id,
            voucher_no=header.invoice_number,
            accounthead=self.customer_head,
            drcr=True,
            amount=Decimal("1180.00"),
            description="Customer debit",
            posting_date=header.posting_date or header.bill_date,
            posted_at=timezone.now(),
            created_by=self.user,
        )
        JournalLine.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=header.id,
            voucher_no=header.invoice_number,
            accounthead=self.income_head,
            drcr=False,
            amount=Decimal("1180.00"),
            description="Sales credit",
            posting_date=header.posting_date or header.bill_date,
            posted_at=timezone.now(),
            created_by=self.user,
        )

        reverse_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/reverse/{self._scope_qs()}",
            {"reason": "Correction"},
            format="json",
        )
        self.assertEqual(reverse_resp.status_code, status.HTTP_200_OK, reverse_resp.json())
        body = reverse_resp.json()
        self.assertEqual(body["status"], int(SalesInvoiceHeader.Status.CONFIRMED))
        header.refresh_from_db()
        self.assertTrue(header.is_posting_reversed)
        self.assertEqual(header.reverse_reason, "Correction")
        mocked_posting_service_post.assert_called_once()
        mocked_close_open_item.assert_called_once()
        entry.refresh_from_db()
        self.assertEqual(entry.status, EntryStatus.REVERSED)
        self.assertEqual(entry.narration, "Reversed: Correction")

    def test_cancel_marks_draft_invoice_cancelled(self):
        created = self._create_invoice(reference="SO-CANCEL")
        invoice_id = created["id"]

        cancel_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/cancel/{self._scope_qs()}",
            {"reason": "Test cancel"},
            format="json",
        )
        self.assertEqual(cancel_resp.status_code, status.HTTP_200_OK, cancel_resp.json())
        self.assertEqual(cancel_resp.json()["status"], int(SalesInvoiceHeader.Status.CANCELLED))

    def test_cancel_marks_confirmed_invoice_cancelled_without_reverse_flow(self):
        created = self._create_invoice(reference="SO-CANCEL-CONFIRMED")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        cancel_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/cancel/{self._scope_qs()}",
            {"reason": "Confirmed cancel"},
            format="json",
        )
        self.assertEqual(cancel_resp.status_code, status.HTTP_200_OK, cancel_resp.json())
        self.assertEqual(cancel_resp.json()["status"], int(SalesInvoiceHeader.Status.CANCELLED))

        header = SalesInvoiceHeader.objects.get(pk=invoice_id)
        self.assertEqual(header.status, SalesInvoiceHeader.Status.CANCELLED)
        self.assertIsNotNone(header.cancelled_at)
        self.assertEqual(header.reverse_reason, "")
        self.assertFalse(header.is_posting_reversed)
        self.assertIn("Cancelled: Confirmed cancel", header.remarks or "")

    def test_repeated_cancel_call_is_idempotent_for_cancelled_invoice(self):
        created = self._create_invoice(reference="SO-CANCEL-IDEMPOTENT")
        invoice_id = created["id"]

        first_cancel_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/cancel/{self._scope_qs()}",
            {"reason": "Test cancel"},
            format="json",
        )
        self.assertEqual(first_cancel_resp.status_code, status.HTTP_200_OK, first_cancel_resp.json())
        self.assertEqual(first_cancel_resp.json()["status"], int(SalesInvoiceHeader.Status.CANCELLED))

        header = SalesInvoiceHeader.objects.get(pk=invoice_id)
        first_cancelled_at = header.cancelled_at
        self.assertIsNotNone(first_cancelled_at)

        second_cancel_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/cancel/{self._scope_qs()}",
            {"reason": "Test cancel again"},
            format="json",
        )
        self.assertEqual(second_cancel_resp.status_code, status.HTTP_200_OK, second_cancel_resp.json())
        self.assertEqual(second_cancel_resp.json()["status"], int(SalesInvoiceHeader.Status.CANCELLED))

        header.refresh_from_db()
        self.assertEqual(header.cancelled_at, first_cancelled_at)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesArService.sync_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_cancel_locked_posted_invoice_creates_current_period_reversal_credit_note(
        self,
        mocked_post_adapter,
        mocked_sync_open_item,
        mocked_auto_compliance,
    ):
        original = self._create_invoice(reference="SO-CANCEL-LOCKED", bill_date="2026-04-10")
        original_id = original["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        SalesLockPeriod.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            lock_date="2026-04-30",
            reason="April books locked",
        )

        cancel_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/cancel/{self._scope_qs()}",
            {"reason": "Filed-period cancellation"},
            format="json",
        )
        self.assertEqual(cancel_resp.status_code, status.HTTP_200_OK, cancel_resp.json())
        body = cancel_resp.json()
        self.assertEqual(body["doc_type"], int(SalesInvoiceHeader.DocType.CREDIT_NOTE))
        self.assertEqual(body["status"], int(SalesInvoiceHeader.Status.POSTED))
        self.assertEqual(body["original_invoice"], original_id)
        self.assertEqual(body["note_reason"], SalesInvoiceHeader.NoteReason.OTHER)
        self.assertFalse(body["affects_inventory"])
        self.assertEqual(body["bill_date"], timezone.localdate().strftime("%d-%m-%Y"))

        original_header = SalesInvoiceHeader.objects.get(pk=original_id)
        self.assertEqual(original_header.status, SalesInvoiceHeader.Status.POSTED)
        self.assertEqual(str(original_header.bill_date), "2026-04-10")
        self.assertEqual(len(original_header.custom_fields_json.get("correction_history", [])), 1)

        correction = SalesInvoiceHeader.objects.get(pk=body["id"])
        self.assertEqual(correction.custom_fields_json["correction_origin"]["original_invoice_id"], original_id)
        self.assertEqual(correction.custom_fields_json["correction_origin"]["reason"], "Filed-period cancellation")
        self.assertGreaterEqual(mocked_post_adapter.call_count, 2)
        self.assertGreaterEqual(mocked_sync_open_item.call_count, 2)
        self.assertTrue(mocked_auto_compliance.called)

    def test_b2b_generate_eway_is_blocked_before_irn_exists(self):
        created = self._create_invoice(
            reference="SO-EWAY-BLOCKED",
            customer_state_code="27",
            place_of_supply_state_code="27",
            lines=[self._goods_line_payload(qty="1.000", rate="60000.0000")],
        )
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        response = self.client.post(
            f"/api/sales/sales-invoices/{invoice_id}/compliance/generate-eway/{self._scope_qs()}",
            {
                "distance_km": 10,
                "trans_mode": "1",
                "transporter_id": "05AAACG0904A1ZL",
                "transporter_name": "ABC Logistics",
                "trans_doc_no": "",
                "vehicle_no": "MH12AB1234",
                "vehicle_type": "R",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.json())
        self.assertIn(
            "Compliance action 'can_generate_eway' is not allowed for current invoice state.",
            str(response.json()),
        )

    @patch("sales.views.sales_invoice_compliance_api.SalesComplianceService.generate_eway")
    @patch("sales.views.sales_invoice_compliance_api.SalesComplianceService.generate_irn")
    def test_generate_irn_and_eway_returns_partial_success_with_structured_eway_error(
        self,
        mocked_generate_irn,
        mocked_generate_eway,
    ):
        created = self._create_invoice(
            reference="SO-IRN-EWAY-PARTIAL",
            customer_state_code="27",
            place_of_supply_state_code="27",
            lines=[self._goods_line_payload(qty="1.000", rate="60000.0000")],
        )
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        mocked_generate_irn.return_value = SimpleNamespace(
            id=501,
            status=int(SalesEInvoiceStatus.GENERATED),
            irn="IRN-SALES-501",
            ack_no="ACK-501",
            ack_date="2026-07-25",
        )
        mocked_generate_eway.side_effect = ValidationError(
            {
                "message": "Duplicate E-Way request.",
                "code": "EWB_DUP",
                "resolution": "Review transporter details and retry.",
            }
        )

        response = self.client.post(
            f"/api/sales/sales-invoices/{invoice_id}/compliance/generate-irn-and-eway/{self._scope_qs()}",
            {
                "generate_eway": True,
                "distance_km": 10,
                "trans_mode": "1",
                "transporter_id": "05AAACG0904A1ZL",
                "transporter_name": "ABC Logistics",
                "vehicle_no": "MH12AB1234",
                "vehicle_type": "R",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["workflow_status"], "PARTIAL_SUCCESS")
        self.assertEqual(body["einvoice"]["irn"], "IRN-SALES-501")
        self.assertEqual(body["eway"]["status"], "FAILED")
        self.assertEqual(body["eway"]["errors"][0]["message"], "Duplicate E-Way request.")
        self.assertEqual(body["eway"]["errors"][0]["code"], "EWB_DUP")
        self.assertEqual(
            body["eway"]["errors"][0]["resolution"],
            "Review transporter details and retry.",
        )

    def test_cancel_irn_is_blocked_when_active_eway_exists(self):
        created = self._create_invoice(
            reference="SO-CANCEL-IRN-BLOCK",
            customer_state_code="27",
            place_of_supply_state_code="27",
            lines=[self._goods_line_payload(qty="1.000", rate="60000.0000")],
        )
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        invoice = SalesInvoiceHeader.objects.get(pk=invoice_id)
        einv, _ = SalesEInvoice.objects.get_or_create(
            invoice=invoice,
            defaults={"created_by": self.user},
        )
        einv.status = SalesEInvoiceStatus.GENERATED
        einv.irn = "IRN-BLOCK-001"
        einv.ack_no = "ACK-BLOCK-001"
        einv.ack_date = timezone.now()
        einv.updated_by = self.user
        einv.save()

        eway, _ = SalesEWayBill.objects.get_or_create(
            invoice=invoice,
            defaults={"created_by": self.user},
        )
        eway.status = SalesEWayStatus.GENERATED
        eway.ewb_no = "171001234567"
        eway.ewb_date = timezone.now()
        eway.valid_upto = timezone.now()
        eway.updated_by = self.user
        eway.save()

        response = self.client.post(
            f"/api/sales/sales-invoices/{invoice_id}/compliance/cancel-irn/{self._scope_qs()}",
            {"reason_code": "1", "remarks": "Need cancellation"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.json())
        self.assertIn(
            "Compliance action 'can_cancel_irn' is not allowed for current invoice state.",
            str(response.json()),
        )

    def test_credit_note_requires_original_invoice(self):
        response = self.client.post(
            "/api/sales/invoices/",
            self._invoice_payload(
                lines=[self._goods_line_payload(qty="1.000", rate="50.0000")],
                doc_type=int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
                reference="CN-001",
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("original_invoice is required", str(response.json()))

    def test_create_credit_note_with_original_invoice(self):
        original = self._create_invoice(reference="SO-ORIG-CN")
        payload = self._invoice_payload(
            lines=[self._goods_line_payload(qty="1.000", rate="50.0000")],
            doc_type=int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
            reference="CN-001",
        )
        payload.update(
            {
                "doc_code": "SCN",
                "original_invoice": original["id"],
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
            }
        )
        response = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        body = response.json()
        self.assertEqual(body["doc_type"], int(SalesInvoiceHeader.DocType.CREDIT_NOTE))
        self.assertEqual(body["original_invoice"], original["id"])
        self.assertEqual(body["note_reason"], SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE)
        self.assertFalse(body["affects_inventory"])

    def test_create_debit_note_with_original_invoice(self):
        original = self._create_invoice(reference="SO-ORIG-DN")
        payload = self._invoice_payload(
            lines=[self._goods_line_payload(qty="1.000", rate="75.0000")],
            doc_type=int(SalesInvoiceHeader.DocType.DEBIT_NOTE),
            reference="DN-001",
        )
        payload.update(
            {
                "doc_code": "SDN",
                "original_invoice": original["id"],
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
            }
        )
        response = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        body = response.json()
        self.assertEqual(body["doc_type"], int(SalesInvoiceHeader.DocType.DEBIT_NOTE))
        self.assertEqual(body["original_invoice"], original["id"])
        self.assertEqual(body["note_reason"], SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE)
        self.assertFalse(body["affects_inventory"])

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesArService.sync_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_sales_return_credit_note_preserves_inventory_return_context_through_post_flow(
        self,
        mocked_post_adapter,
        mocked_sync_open_item,
        mocked_auto_compliance,
    ):
        original = self._create_invoice(reference="SO-ORIG-RETURN")
        original_id = original["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        payload = self._invoice_payload(
            lines=[self._goods_line_payload(qty="2.000", rate="100.0000")],
            doc_type=int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
            reference="SCR-001",
        )
        payload.update(
            {
                "doc_code": "SCN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.QUANTITY_RETURN,
                "affects_inventory": True,
            }
        )
        response = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        body = response.json()
        self.assertEqual(body["doc_type"], int(SalesInvoiceHeader.DocType.CREDIT_NOTE))
        self.assertEqual(body["original_invoice"], original_id)
        self.assertEqual(body["note_reason"], SalesInvoiceHeader.NoteReason.QUANTITY_RETURN)
        self.assertTrue(body["affects_inventory"])
        self.assertEqual(body["place_of_supply_state_code"], original["place_of_supply_state_code"])

        note_id = body["id"]
        confirm_note_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_note_resp.status_code, status.HTTP_200_OK, confirm_note_resp.json())

        post_note_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_note_resp.status_code, status.HTTP_200_OK, post_note_resp.json())
        posted_note = post_note_resp.json()
        self.assertEqual(posted_note["status"], int(SalesInvoiceHeader.Status.POSTED))
        self.assertTrue(posted_note["affects_inventory"])
        self.assertEqual(posted_note["note_reason"], SalesInvoiceHeader.NoteReason.QUANTITY_RETURN)

        note_header = SalesInvoiceHeader.objects.get(pk=note_id)
        self.assertEqual(note_header.original_invoice_id, original_id)
        self.assertTrue(note_header.affects_inventory)
        self.assertEqual(note_header.note_reason, SalesInvoiceHeader.NoteReason.QUANTITY_RETURN)
        self.assertGreaterEqual(mocked_post_adapter.call_count, 2)
        self.assertGreaterEqual(mocked_sync_open_item.call_count, 2)
        self.assertTrue(mocked_auto_compliance.called)

    def test_goods_credit_note_patch_persists_edited_quantity_after_reopen_style_update(self):
        original = self._create_invoice(
            reference="SO-ORIG-CN-PATCH",
            lines=[self._goods_line_payload(qty="2.000", rate="100.0000")],
            place_of_supply_state_code="27",
            seller_state_code="27",
            customer_state_code="27",
        )
        original_id = original["id"]

        note_create_resp = self.client.post(
            "/api/sales/invoices/",
            {
                **self._invoice_payload(
                    lines=[self._goods_line_payload(qty="1.000", rate="100.0000")],
                    doc_type=SalesInvoiceHeader.DocType.CREDIT_NOTE,
                    reference=str(original_id),
                ),
                "doc_code": "SCN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.QUANTITY_RETURN,
                "affects_inventory": True,
                "place_of_supply_state_code": "27",
            },
            format="json",
        )
        self.assertEqual(note_create_resp.status_code, status.HTTP_201_CREATED, note_create_resp.json())
        note_body = note_create_resp.json()
        note_id = note_body["id"]
        self.assertEqual(Decimal(str(note_body["lines"][0]["qty"])), Decimal("1.000"))

        existing_line = note_body["lines"][0]
        patch_payload = {
            "remarks": "reopen quantity edit",
            "lines": [
                {
                    "id": existing_line["id"],
                    "line_no": existing_line["line_no"],
                    "product": self.goods_product.id,
                    "uom": self.uom.id,
                    "qty": "2.000",
                    "free_qty": "0.000",
                    "rate": "100.0000",
                    "productDesc": "Test goods",
                    "is_service": False,
                    "discount_type": 0,
                    "discount_percent": "0.0000",
                    "discount_amount": "0.00",
                    "gst_rate": "18.00",
                    "cess_percent": "0.00",
                    "cess_amount": "0.00",
                }
            ],
        }

        patch_resp = self.client.patch(
            f"/api/sales/invoices/{note_id}/{self._scope_qs()}",
            patch_payload,
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.json())
        patched_body = patch_resp.json()
        self.assertEqual(patched_body["tax_regime"], int(SalesInvoiceHeader.TaxRegime.INTRA_STATE))
        self.assertEqual(Decimal(str(patched_body["lines"][0]["qty"])), Decimal("2.000"))
        self.assertEqual(Decimal(str(patched_body["lines"][0]["cgst_amount"])), Decimal("18.00"))
        self.assertEqual(Decimal(str(patched_body["lines"][0]["sgst_amount"])), Decimal("18.00"))
        self.assertEqual(Decimal(str(patched_body["lines"][0]["igst_amount"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(patched_body["total_taxable_value"])), Decimal("200.00"))

        reloaded = self.client.get(f"/api/sales/invoices/{note_id}/{self._scope_qs()}", format="json")
        self.assertEqual(reloaded.status_code, status.HTTP_200_OK, reloaded.json())
        reloaded_body = reloaded.json()
        self.assertEqual(Decimal(str(reloaded_body["lines"][0]["qty"])), Decimal("2.000"))
        self.assertEqual(Decimal(str(reloaded_body["lines"][0]["cgst_amount"])), Decimal("18.00"))
        self.assertEqual(Decimal(str(reloaded_body["lines"][0]["sgst_amount"])), Decimal("18.00"))
        self.assertEqual(Decimal(str(reloaded_body["lines"][0]["igst_amount"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(reloaded_body["total_taxable_value"])), Decimal("200.00"))

        line = SalesInvoiceLine.objects.get(header_id=note_id, line_no=1)
        self.assertEqual(line.qty, Decimal("2.000"))
        self.assertEqual(line.taxable_value, Decimal("200.00"))
        self.assertEqual(line.cgst_amount, Decimal("18.00"))
        self.assertEqual(line.sgst_amount, Decimal("18.00"))
        self.assertEqual(line.igst_amount, Decimal("0.00"))

    def test_sales_invoice_composite_cess_persists_after_save_and_reload(self):
        line_payload = self._goods_line_payload(
            qty="2.000",
            rate="100.0000",
            cess_percent="1.00",
            cess_type="composite",
            cess_specific_amount="2.00",
        )
        line_payload.pop("cess_amount", None)

        create_resp = self.client.post(
            "/api/sales/invoices/",
            self._invoice_payload(
                lines=[line_payload],
                seller_state_code="29",
                customer_state_code="27",
                place_of_supply_state_code="03",
            ),
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())

        body = create_resp.json()
        self.assertEqual(body["tax_regime"], int(SalesInvoiceHeader.TaxRegime.INTER_STATE))
        self.assertEqual(body["lines"][0]["cess_type"], "composite")
        self.assertEqual(Decimal(str(body["lines"][0]["igst_amount"])), Decimal("36.00"))
        self.assertEqual(Decimal(str(body["lines"][0]["cess_percent"])), Decimal("1.00"))
        self.assertEqual(Decimal(str(body["lines"][0]["cess_specific_amount"])), Decimal("2.00"))
        self.assertEqual(Decimal(str(body["lines"][0]["cess_amount"])), Decimal("6.00"))
        self.assertEqual(Decimal(str(body["lines"][0]["line_total"])), Decimal("242.00"))

        invoice_id = body["id"]
        reload_resp = self.client.get(f"/api/sales/invoices/{invoice_id}/{self._scope_qs()}", format="json")
        self.assertEqual(reload_resp.status_code, status.HTTP_200_OK, reload_resp.json())
        reload_body = reload_resp.json()
        self.assertEqual(reload_body["lines"][0]["cess_type"], "composite")
        self.assertEqual(Decimal(str(reload_body["lines"][0]["cess_specific_amount"])), Decimal("2.00"))
        self.assertEqual(Decimal(str(reload_body["lines"][0]["cess_amount"])), Decimal("6.00"))
        self.assertEqual(Decimal(str(reload_body["lines"][0]["line_total"])), Decimal("242.00"))

        line = SalesInvoiceLine.objects.get(header_id=invoice_id, line_no=1)
        self.assertEqual(line.cess_type, SalesInvoiceLine.CessType.COMPOSITE)
        self.assertEqual(line.cess_specific_amount, Decimal("2.00"))
        self.assertEqual(line.cess_amount, Decimal("6.00"))
        self.assertEqual(line.line_total, Decimal("242.00"))

    def test_sales_invoice_ad_valorem_cess_persists_after_save_and_reload(self):
        line_payload = self._goods_line_payload(
            qty="2.000",
            rate="100.0000",
            cess_percent="1.50",
            cess_type="ad_valorem",
            cess_specific_amount="0.00",
        )
        line_payload.pop("cess_amount", None)

        create_resp = self.client.post(
            "/api/sales/invoices/",
            self._invoice_payload(
                lines=[line_payload],
                seller_state_code="29",
                customer_state_code="27",
                place_of_supply_state_code="03",
            ),
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())

        body = create_resp.json()
        self.assertEqual(body["lines"][0]["cess_type"], "ad_valorem")
        self.assertEqual(Decimal(str(body["lines"][0]["cess_percent"])), Decimal("1.50"))
        self.assertEqual(Decimal(str(body["lines"][0]["cess_specific_amount"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(body["lines"][0]["cess_amount"])), Decimal("3.00"))
        self.assertEqual(Decimal(str(body["lines"][0]["line_total"])), Decimal("239.00"))

        invoice_id = body["id"]
        reload_resp = self.client.get(f"/api/sales/invoices/{invoice_id}/{self._scope_qs()}", format="json")
        self.assertEqual(reload_resp.status_code, status.HTTP_200_OK, reload_resp.json())
        reload_body = reload_resp.json()
        self.assertEqual(reload_body["lines"][0]["cess_type"], "ad_valorem")
        self.assertEqual(Decimal(str(reload_body["lines"][0]["cess_amount"])), Decimal("3.00"))

        line = SalesInvoiceLine.objects.get(header_id=invoice_id, line_no=1)
        self.assertEqual(line.cess_type, SalesInvoiceLine.CessType.AD_VALOREM)
        self.assertEqual(line.cess_specific_amount, Decimal("0.00"))
        self.assertEqual(line.cess_amount, Decimal("3.00"))

    def test_sales_invoice_specific_cess_persists_after_save_and_reload(self):
        line_payload = self._goods_line_payload(
            qty="2.000",
            rate="100.0000",
            cess_percent="0.00",
            cess_type="specific",
            cess_specific_amount="2.50",
        )
        line_payload.pop("cess_amount", None)

        create_resp = self.client.post(
            "/api/sales/invoices/",
            self._invoice_payload(
                lines=[line_payload],
                seller_state_code="29",
                customer_state_code="27",
                place_of_supply_state_code="03",
            ),
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())

        body = create_resp.json()
        self.assertEqual(body["lines"][0]["cess_type"], "specific")
        self.assertEqual(Decimal(str(body["lines"][0]["cess_percent"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(body["lines"][0]["cess_specific_amount"])), Decimal("2.50"))
        self.assertEqual(Decimal(str(body["lines"][0]["cess_amount"])), Decimal("5.00"))
        self.assertEqual(Decimal(str(body["lines"][0]["line_total"])), Decimal("241.00"))

        invoice_id = body["id"]
        reload_resp = self.client.get(f"/api/sales/invoices/{invoice_id}/{self._scope_qs()}", format="json")
        self.assertEqual(reload_resp.status_code, status.HTTP_200_OK, reload_resp.json())
        reload_body = reload_resp.json()
        self.assertEqual(reload_body["lines"][0]["cess_type"], "specific")
        self.assertEqual(Decimal(str(reload_body["lines"][0]["cess_specific_amount"])), Decimal("2.50"))
        self.assertEqual(Decimal(str(reload_body["lines"][0]["cess_amount"])), Decimal("5.00"))

        line = SalesInvoiceLine.objects.get(header_id=invoice_id, line_no=1)
        self.assertEqual(line.cess_type, SalesInvoiceLine.CessType.SPECIFIC)
        self.assertEqual(line.cess_specific_amount, Decimal("2.50"))
        self.assertEqual(line.cess_amount, Decimal("5.00"))

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesArService.sync_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_sales_debit_note_preserves_original_invoice_context_through_post_flow(
        self,
        mocked_post_adapter,
        mocked_sync_open_item,
        mocked_auto_compliance,
    ):
        original = self._create_invoice(reference="SO-ORIG-DEBIT")
        original_id = original["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        payload = self._invoice_payload(
            lines=[self._goods_line_payload(qty="1.000", rate="75.0000")],
            doc_type=int(SalesInvoiceHeader.DocType.DEBIT_NOTE),
            reference="SDN-001",
        )
        payload.update(
            {
                "doc_code": "SDN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
            }
        )
        response = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        body = response.json()
        self.assertEqual(body["doc_type"], int(SalesInvoiceHeader.DocType.DEBIT_NOTE))
        self.assertEqual(body["original_invoice"], original_id)
        self.assertEqual(body["note_reason"], SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE)
        self.assertFalse(body["affects_inventory"])

        note_id = body["id"]
        confirm_note_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_note_resp.status_code, status.HTTP_200_OK, confirm_note_resp.json())

        post_note_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_note_resp.status_code, status.HTTP_200_OK, post_note_resp.json())
        posted_note = post_note_resp.json()
        self.assertEqual(posted_note["status"], int(SalesInvoiceHeader.Status.POSTED))
        self.assertEqual(posted_note["original_invoice"], original_id)
        self.assertEqual(posted_note["note_reason"], SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE)
        self.assertFalse(posted_note["affects_inventory"])

        original_header = SalesInvoiceHeader.objects.get(pk=original_id)
        note_header = SalesInvoiceHeader.objects.get(pk=note_id)
        self.assertEqual(original_header.status, SalesInvoiceHeader.Status.POSTED)
        self.assertEqual(note_header.status, SalesInvoiceHeader.Status.POSTED)
        self.assertEqual(note_header.original_invoice_id, original_id)
        self.assertEqual(note_header.note_reason, SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE)
        self.assertFalse(note_header.affects_inventory)
        self.assertGreaterEqual(mocked_post_adapter.call_count, 2)
        self.assertGreaterEqual(mocked_sync_open_item.call_count, 2)
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesArService.close_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesArService.sync_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_confirmed_sales_debit_note_can_be_cancelled_without_reverse_flow(
        self,
        mocked_post_adapter,
        mocked_sync_open_item,
        mocked_close_open_item,
        mocked_auto_compliance,
    ):
        original = self._create_invoice(reference="SO-ORIG-DEBIT-CONF-CANCEL")
        original_id = original["id"]

        self.assertEqual(
            self.client.post(
                f"/api/sales/invoices/{original_id}/confirm/{self._scope_qs()}",
                {},
                format="json",
            ).status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.post(
                f"/api/sales/invoices/{original_id}/post/{self._scope_qs()}",
                {},
                format="json",
            ).status_code,
            status.HTTP_200_OK,
        )

        payload = self._invoice_payload(
            lines=[self._goods_line_payload(qty="1.000", rate="80.0000")],
            doc_type=int(SalesInvoiceHeader.DocType.DEBIT_NOTE),
            reference="SDN-CONF-CANCEL-001",
        )
        payload.update(
            {
                "doc_code": "SDN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
            }
        )
        create_resp = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())
        note_id = create_resp.json()["id"]

        confirm_note_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_note_resp.status_code, status.HTTP_200_OK, confirm_note_resp.json())

        cancel_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/cancel/{self._scope_qs()}",
            {"reason": "Confirmed debit note cancel"},
            format="json",
        )
        self.assertEqual(cancel_resp.status_code, status.HTTP_200_OK, cancel_resp.json())

        note_header = SalesInvoiceHeader.objects.get(pk=note_id)
        self.assertEqual(note_header.status, SalesInvoiceHeader.Status.CANCELLED)
        self.assertIsNotNone(note_header.cancelled_at)
        self.assertEqual(getattr(note_header.cancelled_by, "id", None), self.user.id)
        self.assertEqual(note_header.reverse_reason, "")
        self.assertFalse(note_header.is_posting_reversed)
        self.assertIn("Cancelled: Confirmed debit note cancel", note_header.remarks or "")
        mocked_post_adapter.assert_called_once()
        mocked_sync_open_item.assert_called_once()
        mocked_close_open_item.assert_called_once()
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesArService.close_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesArService.sync_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_posted_sales_debit_note_can_be_cancelled_and_persists_cancelled_state(
        self,
        mocked_post_adapter,
        mocked_sync_open_item,
        mocked_close_open_item,
        mocked_auto_compliance,
    ):
        original = self._create_invoice(reference="SO-ORIG-DEBIT-CANCEL")
        original_id = original["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        payload = self._invoice_payload(
            lines=[self._goods_line_payload(qty="1.000", rate="80.0000")],
            doc_type=int(SalesInvoiceHeader.DocType.DEBIT_NOTE),
            reference="SDN-CANCEL-001",
        )
        payload.update(
            {
                "doc_code": "SDN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
            }
        )
        create_resp = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())
        note_id = create_resp.json()["id"]

        confirm_note_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_note_resp.status_code, status.HTTP_200_OK, confirm_note_resp.json())

        post_note_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_note_resp.status_code, status.HTTP_200_OK, post_note_resp.json())

        note_header = SalesInvoiceHeader.objects.get(pk=note_id)
        batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES_DEBIT_NOTE,
            txn_id=note_header.id,
            voucher_no=note_header.invoice_number,
            revision=1,
            is_active=True,
            created_by=self.user,
        )
        entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES_DEBIT_NOTE,
            txn_id=note_header.id,
            voucher_no=note_header.invoice_number,
            voucher_date=note_header.bill_date,
            posting_date=note_header.posting_date or note_header.bill_date,
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=batch,
            narration="Posted debit note",
            created_by=self.user,
        )
        JournalLine.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES_DEBIT_NOTE,
            txn_id=note_header.id,
            voucher_no=note_header.invoice_number,
            accounthead=self.customer_head,
            drcr=True,
            amount=Decimal("94.40"),
            description="Customer debit for debit note",
            posting_date=note_header.posting_date or note_header.bill_date,
            posted_at=timezone.now(),
            created_by=self.user,
        )
        JournalLine.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES_DEBIT_NOTE,
            txn_id=note_header.id,
            voucher_no=note_header.invoice_number,
            accounthead=self.income_head,
            drcr=False,
            amount=Decimal("94.40"),
            description="Sales credit for debit note",
            posting_date=note_header.posting_date or note_header.bill_date,
            posted_at=timezone.now(),
            created_by=self.user,
        )

        cancel_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/cancel/{self._scope_qs()}",
            {"reason": "Debit note entered in error"},
            format="json",
        )
        self.assertEqual(cancel_resp.status_code, status.HTTP_200_OK, cancel_resp.json())
        cancelled = cancel_resp.json()
        self.assertEqual(cancelled["status"], int(SalesInvoiceHeader.Status.CANCELLED))

        note_header.refresh_from_db()
        self.assertEqual(note_header.status, SalesInvoiceHeader.Status.CANCELLED)
        self.assertIsNotNone(note_header.cancelled_at)
        self.assertEqual(getattr(note_header.cancelled_by, "id", None), self.user.id)
        self.assertIn("Cancelled: Debit note entered in error", note_header.remarks or "")
        self.assertEqual(note_header.original_invoice_id, original_id)
        self.assertEqual(note_header.note_reason, SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE)
        self.assertFalse(note_header.affects_inventory)
        entry.refresh_from_db()
        self.assertEqual(entry.status, EntryStatus.REVERSED)
        self.assertGreaterEqual(mocked_post_adapter.call_count, 2)
        self.assertGreaterEqual(mocked_sync_open_item.call_count, 2)
        self.assertTrue(mocked_close_open_item.called)
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesArService.close_open_item_for_header")
    @patch("sales.services.sales_invoice_service.PostingService.post")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesArService.sync_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_reverse_posted_sales_debit_note_marks_confirmed_and_updates_entry(
        self,
        mocked_post_adapter,
        mocked_sync_open_item,
        mocked_auto_compliance,
        mocked_posting_service_post,
        mocked_close_open_item,
    ):
        original = self._create_invoice(reference="SO-ORIG-DEBIT-REVERSE")
        original_id = original["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        payload = self._invoice_payload(
            lines=[self._goods_line_payload(qty="1.000", rate="82.0000")],
            doc_type=int(SalesInvoiceHeader.DocType.DEBIT_NOTE),
            reference="SDN-REVERSE-001",
        )
        payload.update(
            {
                "doc_code": "SDN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
            }
        )
        create_resp = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())
        note_id = create_resp.json()["id"]

        confirm_note_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_note_resp.status_code, status.HTTP_200_OK, confirm_note_resp.json())

        post_note_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_note_resp.status_code, status.HTTP_200_OK, post_note_resp.json())

        note_header = SalesInvoiceHeader.objects.get(pk=note_id)
        batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES_DEBIT_NOTE,
            txn_id=note_header.id,
            voucher_no=note_header.invoice_number,
            revision=1,
            is_active=True,
            created_by=self.user,
        )
        entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES_DEBIT_NOTE,
            txn_id=note_header.id,
            voucher_no=note_header.invoice_number,
            voucher_date=note_header.bill_date,
            posting_date=note_header.posting_date or note_header.bill_date,
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=batch,
            narration="Posted debit note",
            created_by=self.user,
        )
        JournalLine.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES_DEBIT_NOTE,
            txn_id=note_header.id,
            voucher_no=note_header.invoice_number,
            accounthead=self.customer_head,
            drcr=True,
            amount=Decimal("96.76"),
            description="Customer debit for debit note",
            posting_date=note_header.posting_date or note_header.bill_date,
            posted_at=timezone.now(),
            created_by=self.user,
        )
        JournalLine.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES_DEBIT_NOTE,
            txn_id=note_header.id,
            voucher_no=note_header.invoice_number,
            accounthead=self.income_head,
            drcr=False,
            amount=Decimal("96.76"),
            description="Sales credit for debit note",
            posting_date=note_header.posting_date or note_header.bill_date,
            posted_at=timezone.now(),
            created_by=self.user,
        )

        reverse_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/reverse/{self._scope_qs()}",
            {"reason": "Debit note correction"},
            format="json",
        )
        self.assertEqual(reverse_resp.status_code, status.HTTP_200_OK, reverse_resp.json())
        body = reverse_resp.json()
        self.assertEqual(body["status"], int(SalesInvoiceHeader.Status.CONFIRMED))

        note_header.refresh_from_db()
        self.assertTrue(note_header.is_posting_reversed)
        self.assertEqual(note_header.reverse_reason, "Debit note correction")
        self.assertIsNone(note_header.posted_at)
        self.assertIsNone(note_header.posted_by)
        entry.refresh_from_db()
        self.assertEqual(entry.status, EntryStatus.REVERSED)
        self.assertEqual(entry.narration, "Reversed: Debit note correction")
        mocked_posting_service_post.assert_called_once()
        mocked_close_open_item.assert_called_once()
        self.assertGreaterEqual(mocked_post_adapter.call_count, 2)
        self.assertGreaterEqual(mocked_sync_open_item.call_count, 2)
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesArService.close_open_item_for_header")
    @patch("sales.services.sales_invoice_service.PostingService.post")
    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesArService.sync_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_reverse_posted_sales_credit_note_marks_confirmed_and_updates_entry(
        self,
        mocked_post_adapter,
        mocked_sync_open_item,
        mocked_auto_compliance,
        mocked_posting_service_post,
        mocked_close_open_item,
    ):
        original = self._create_invoice(reference="SO-ORIG-CREDIT-REVERSE")
        original_id = original["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        payload = self._invoice_payload(
            lines=[self._goods_line_payload(qty="1.000", rate="82.0000")],
            doc_type=int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
            reference="SCN-REVERSE-001",
        )
        payload.update(
            {
                "doc_code": "SCN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
            }
        )
        create_resp = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())
        note_id = create_resp.json()["id"]

        confirm_note_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_note_resp.status_code, status.HTTP_200_OK, confirm_note_resp.json())

        post_note_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_note_resp.status_code, status.HTTP_200_OK, post_note_resp.json())

        note_header = SalesInvoiceHeader.objects.get(pk=note_id)
        batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES_CREDIT_NOTE,
            txn_id=note_header.id,
            voucher_no=note_header.invoice_number,
            revision=1,
            is_active=True,
            created_by=self.user,
        )
        entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES_CREDIT_NOTE,
            txn_id=note_header.id,
            voucher_no=note_header.invoice_number,
            voucher_date=note_header.bill_date,
            posting_date=note_header.posting_date or note_header.bill_date,
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=batch,
            narration="Posted credit note",
            created_by=self.user,
        )
        JournalLine.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES_CREDIT_NOTE,
            txn_id=note_header.id,
            voucher_no=note_header.invoice_number,
            accounthead=self.customer_head,
            drcr=False,
            amount=Decimal("96.76"),
            description="Customer credit for credit note",
            posting_date=note_header.posting_date or note_header.bill_date,
            posted_at=timezone.now(),
            created_by=self.user,
        )
        JournalLine.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES_CREDIT_NOTE,
            txn_id=note_header.id,
            voucher_no=note_header.invoice_number,
            accounthead=self.income_head,
            drcr=True,
            amount=Decimal("96.76"),
            description="Sales debit for credit note",
            posting_date=note_header.posting_date or note_header.bill_date,
            posted_at=timezone.now(),
            created_by=self.user,
        )

        reverse_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/reverse/{self._scope_qs()}",
            {"reason": "Credit note correction"},
            format="json",
        )
        self.assertEqual(reverse_resp.status_code, status.HTTP_200_OK, reverse_resp.json())
        body = reverse_resp.json()
        self.assertEqual(body["status"], int(SalesInvoiceHeader.Status.CONFIRMED))

        note_header.refresh_from_db()
        self.assertTrue(note_header.is_posting_reversed)
        self.assertEqual(note_header.reverse_reason, "Credit note correction")
        self.assertIsNone(note_header.posted_at)
        self.assertIsNone(note_header.posted_by)
        entry.refresh_from_db()
        self.assertEqual(entry.status, EntryStatus.REVERSED)
        self.assertEqual(entry.narration, "Reversed: Credit note correction")
        mocked_posting_service_post.assert_called_once()
        mocked_close_open_item.assert_called_once()
        self.assertGreaterEqual(mocked_post_adapter.call_count, 2)
        self.assertGreaterEqual(mocked_sync_open_item.call_count, 2)
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesArService.close_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesArService.sync_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_confirmed_sales_credit_note_can_be_cancelled_without_reverse_flow(
        self,
        mocked_post_adapter,
        mocked_sync_open_item,
        mocked_close_open_item,
        mocked_auto_compliance,
    ):
        original = self._create_invoice(reference="SO-ORIG-CREDIT-CONF-CANCEL")
        original_id = original["id"]

        self.assertEqual(
            self.client.post(
                f"/api/sales/invoices/{original_id}/confirm/{self._scope_qs()}",
                {},
                format="json",
            ).status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.post(
                f"/api/sales/invoices/{original_id}/post/{self._scope_qs()}",
                {},
                format="json",
            ).status_code,
            status.HTTP_200_OK,
        )

        payload = self._invoice_payload(
            lines=[self._goods_line_payload(qty="1.000", rate="80.0000")],
            doc_type=int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
            reference="SCN-CONF-CANCEL-001",
        )
        payload.update(
            {
                "doc_code": "SCN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
            }
        )
        create_resp = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())
        note_id = create_resp.json()["id"]

        confirm_note_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_note_resp.status_code, status.HTTP_200_OK, confirm_note_resp.json())

        cancel_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/cancel/{self._scope_qs()}",
            {"reason": "Confirmed credit note cancel"},
            format="json",
        )
        self.assertEqual(cancel_resp.status_code, status.HTTP_200_OK, cancel_resp.json())

        note_header = SalesInvoiceHeader.objects.get(pk=note_id)
        self.assertEqual(note_header.status, SalesInvoiceHeader.Status.CANCELLED)
        self.assertIsNotNone(note_header.cancelled_at)
        self.assertEqual(getattr(note_header.cancelled_by, "id", None), self.user.id)
        self.assertEqual(note_header.reverse_reason, "")
        self.assertFalse(note_header.is_posting_reversed)
        self.assertIn("Cancelled: Confirmed credit note cancel", note_header.remarks or "")
        mocked_post_adapter.assert_called_once()
        mocked_sync_open_item.assert_called_once()
        mocked_close_open_item.assert_called_once()
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesArService.close_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesArService.sync_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_posted_sales_credit_note_can_be_cancelled_and_persists_cancelled_state(
        self,
        mocked_post_adapter,
        mocked_sync_open_item,
        mocked_close_open_item,
        mocked_auto_compliance,
    ):
        original = self._create_invoice(reference="SO-ORIG-CREDIT-CANCEL")
        original_id = original["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        payload = self._invoice_payload(
            lines=[self._goods_line_payload(qty="1.000", rate="80.0000")],
            doc_type=int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
            reference="SCN-CANCEL-001",
        )
        payload.update(
            {
                "doc_code": "SCN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
            }
        )
        create_resp = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())
        note_id = create_resp.json()["id"]

        confirm_note_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_note_resp.status_code, status.HTTP_200_OK, confirm_note_resp.json())

        post_note_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_note_resp.status_code, status.HTTP_200_OK, post_note_resp.json())

        note_header = SalesInvoiceHeader.objects.get(pk=note_id)
        batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES_CREDIT_NOTE,
            txn_id=note_header.id,
            voucher_no=note_header.invoice_number,
            revision=1,
            is_active=True,
            created_by=self.user,
        )
        entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES_CREDIT_NOTE,
            txn_id=note_header.id,
            voucher_no=note_header.invoice_number,
            voucher_date=note_header.bill_date,
            posting_date=note_header.posting_date or note_header.bill_date,
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=batch,
            narration="Posted credit note",
            created_by=self.user,
        )
        JournalLine.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES_CREDIT_NOTE,
            txn_id=note_header.id,
            voucher_no=note_header.invoice_number,
            accounthead=self.customer_head,
            drcr=False,
            amount=Decimal("94.40"),
            description="Customer credit for credit note",
            posting_date=note_header.posting_date or note_header.bill_date,
            posted_at=timezone.now(),
            created_by=self.user,
        )
        JournalLine.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES_CREDIT_NOTE,
            txn_id=note_header.id,
            voucher_no=note_header.invoice_number,
            accounthead=self.income_head,
            drcr=True,
            amount=Decimal("94.40"),
            description="Sales debit for credit note",
            posting_date=note_header.posting_date or note_header.bill_date,
            posted_at=timezone.now(),
            created_by=self.user,
        )

        cancel_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/cancel/{self._scope_qs()}",
            {"reason": "Credit note entered in error"},
            format="json",
        )
        self.assertEqual(cancel_resp.status_code, status.HTTP_200_OK, cancel_resp.json())
        cancelled = cancel_resp.json()
        self.assertEqual(cancelled["status"], int(SalesInvoiceHeader.Status.CANCELLED))

        note_header.refresh_from_db()
        self.assertEqual(note_header.status, SalesInvoiceHeader.Status.CANCELLED)
        self.assertIsNotNone(note_header.cancelled_at)
        self.assertEqual(getattr(note_header.cancelled_by, "id", None), self.user.id)
        self.assertIn("Cancelled: Credit note entered in error", note_header.remarks or "")
        self.assertEqual(note_header.original_invoice_id, original_id)
        self.assertEqual(note_header.note_reason, SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE)
        self.assertFalse(note_header.affects_inventory)
        entry.refresh_from_db()
        self.assertEqual(entry.status, EntryStatus.REVERSED)
        self.assertGreaterEqual(mocked_post_adapter.call_count, 2)
        self.assertGreaterEqual(mocked_sync_open_item.call_count, 2)
        self.assertTrue(mocked_close_open_item.called)
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesArService.sync_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_locked_period_original_invoice_allows_current_period_credit_note_correction(
        self,
        mocked_post_adapter,
        mocked_sync_open_item,
        mocked_auto_compliance,
    ):
        original = self._create_invoice(reference="SO-LOCKED-ORIG", bill_date="2026-04-10")
        original_id = original["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        SalesLockPeriod.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            lock_date="2026-04-30",
            reason="April books locked",
        )

        payload = self._invoice_payload(
            lines=[self._goods_line_payload(qty="1.000", rate="100.0000")],
            doc_type=int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
            reference="SO-LOCKED-CN",
        )
        payload.update(
            {
                "bill_date": "2026-05-10",
                "doc_code": "SCN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
                "remarks": "Filed-period correction",
            }
        )
        response = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        note = response.json()
        self.assertEqual(note["original_invoice"], original_id)
        self.assertEqual(note["bill_date"], "10-05-2026")

        confirm_note_resp = self.client.post(
            f"/api/sales/invoices/{note['id']}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_note_resp.status_code, status.HTTP_200_OK, confirm_note_resp.json())

        post_note_resp = self.client.post(
            f"/api/sales/invoices/{note['id']}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_note_resp.status_code, status.HTTP_200_OK, post_note_resp.json())

        original_header = SalesInvoiceHeader.objects.get(pk=original_id)
        note_header = SalesInvoiceHeader.objects.get(pk=note["id"])
        self.assertEqual(original_header.status, SalesInvoiceHeader.Status.POSTED)
        self.assertEqual(str(original_header.bill_date), "2026-04-10")
        self.assertEqual(note_header.status, SalesInvoiceHeader.Status.POSTED)
        self.assertEqual(str(note_header.bill_date), "2026-05-10")
        self.assertEqual(note_header.original_invoice_id, original_id)
        self.assertEqual(len(original_header.custom_fields_json.get("correction_history", [])), 1)
        correction_event = original_header.custom_fields_json["correction_history"][0]
        self.assertEqual(correction_event["correction_document_id"], note_header.id)
        self.assertEqual(correction_event["original_invoice_id"], original_id)
        self.assertEqual(correction_event["reason"], "Filed-period correction")
        self.assertEqual(correction_event["gst_period_impact"], "2026-05")
        self.assertEqual(correction_event["old_value"]["bill_date"], "2026-04-10")
        self.assertEqual(correction_event["new_value"]["bill_date"], "2026-05-10")
        self.assertEqual(note_header.custom_fields_json["correction_origin"]["original_invoice_id"], original_id)
        self.assertEqual(note_header.custom_fields_json["correction_origin"]["correction_document_id"], note_header.id)
        self.assertGreaterEqual(mocked_post_adapter.call_count, 2)
        self.assertGreaterEqual(mocked_sync_open_item.call_count, 2)
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesArService.sync_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_locked_period_original_invoice_allows_current_period_debit_note_correction(
        self,
        mocked_post_adapter,
        mocked_sync_open_item,
        mocked_auto_compliance,
    ):
        original = self._create_invoice(reference="SO-LOCKED-ORIG-DN", bill_date="2026-04-10")
        original_id = original["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        SalesLockPeriod.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            lock_date="2026-04-30",
            reason="April books locked",
        )

        payload = self._invoice_payload(
            lines=[self._goods_line_payload(qty="1.000", rate="125.0000")],
            doc_type=int(SalesInvoiceHeader.DocType.DEBIT_NOTE),
            reference="SO-LOCKED-DN",
        )
        payload.update(
            {
                "bill_date": "2026-05-11",
                "doc_code": "SDN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
                "remarks": "Filed-period debit correction",
            }
        )
        response = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        note = response.json()
        self.assertEqual(note["doc_type"], int(SalesInvoiceHeader.DocType.DEBIT_NOTE))
        self.assertEqual(note["original_invoice"], original_id)
        self.assertEqual(note["bill_date"], "11-05-2026")

        confirm_note_resp = self.client.post(
            f"/api/sales/invoices/{note['id']}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_note_resp.status_code, status.HTTP_200_OK, confirm_note_resp.json())

        post_note_resp = self.client.post(
            f"/api/sales/invoices/{note['id']}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_note_resp.status_code, status.HTTP_200_OK, post_note_resp.json())

        original_header = SalesInvoiceHeader.objects.get(pk=original_id)
        note_header = SalesInvoiceHeader.objects.get(pk=note["id"])
        self.assertEqual(original_header.status, SalesInvoiceHeader.Status.POSTED)
        self.assertEqual(str(original_header.bill_date), "2026-04-10")
        self.assertEqual(note_header.status, SalesInvoiceHeader.Status.POSTED)
        self.assertEqual(str(note_header.bill_date), "2026-05-11")
        self.assertEqual(note_header.original_invoice_id, original_id)
        self.assertEqual(note_header.note_reason, SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE)
        self.assertFalse(note_header.affects_inventory)
        self.assertEqual(len(original_header.custom_fields_json.get("correction_history", [])), 1)
        correction_event = original_header.custom_fields_json["correction_history"][0]
        self.assertEqual(correction_event["correction_document_id"], note_header.id)
        self.assertEqual(correction_event["original_invoice_id"], original_id)
        self.assertEqual(correction_event["reason"], "Filed-period debit correction")
        self.assertEqual(correction_event["correction_type"], "debit_note")
        self.assertEqual(correction_event["gst_period_impact"], "2026-05")
        self.assertEqual(correction_event["old_value"]["bill_date"], "2026-04-10")
        self.assertEqual(correction_event["new_value"]["bill_date"], "2026-05-11")
        self.assertEqual(note_header.custom_fields_json["correction_origin"]["original_invoice_id"], original_id)
        self.assertEqual(note_header.custom_fields_json["correction_origin"]["correction_document_id"], note_header.id)
        self.assertEqual(note_header.custom_fields_json["correction_origin"]["correction_type"], "debit_note")
        self.assertGreaterEqual(mocked_post_adapter.call_count, 2)
        self.assertGreaterEqual(mocked_sync_open_item.call_count, 2)
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesArService.sync_open_item_for_header")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_locked_period_posted_invoice_blocks_direct_unpost_and_requires_current_period_correction(
        self,
        mocked_post_adapter,
        mocked_sync_open_item,
        mocked_auto_compliance,
    ):
        original = self._create_invoice(reference="SO-LOCKED-UNPOST", bill_date="2026-04-10")
        original_id = original["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        SalesLockPeriod.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            lock_date="2026-04-30",
            reason="April books locked",
        )

        unpost_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/reverse/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(unpost_resp.status_code, status.HTTP_400_BAD_REQUEST, unpost_resp.json())
        self.assertEqual(
            unpost_resp.json(),
            {
                "detail": (
                    "Posted sales invoice belongs to a locked/filed period and cannot be unposted. "
                    "Create a current-period correction document instead."
                )
            },
        )

        original_header = SalesInvoiceHeader.objects.get(pk=original_id)
        self.assertEqual(original_header.status, SalesInvoiceHeader.Status.POSTED)
        self.assertFalse(original_header.is_posting_reversed)
        self.assertGreaterEqual(mocked_post_adapter.call_count, 1)
        self.assertGreaterEqual(mocked_sync_open_item.call_count, 1)
        self.assertTrue(mocked_auto_compliance.called)

    def test_edit_locked_period_sales_is_blocked(self):
        created = self._create_invoice(
            reference="SO-LOCK-EDIT",
            bill_date="2026-04-10",
        )
        invoice_id = created["id"]

        SalesLockPeriod.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            lock_date="2026-04-30",
            reason="April books locked",
        )

        patch_resp = self.client.patch(
            f"/api/sales/invoices/{invoice_id}/{self._scope_qs()}",
            {"reference": "SHOULD-NOT-UPDATE"},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Period is locked up to 2026-04-30", str(patch_resp.json()))

    def test_reverse_requires_posted_invoice(self):
        created = self._create_invoice(reference="SO-REVERSE-BLOCK")
        invoice_id = created["id"]
        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        reverse_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/reverse/{self._scope_qs()}",
            {"reason": "Not posted yet"},
            format="json",
        )
        self.assertEqual(reverse_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Only posted invoices can be reversed.", str(reverse_resp.json()))

    def test_posted_invoice_cannot_be_edited(self):
        created = self._create_invoice(reference="SO-EDIT-BLOCK")
        invoice_id = created["id"]
        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        with patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance"), \
             patch("sales.services.sales_invoice_service.SalesArService.sync_open_item_for_header"), \
             patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice"):
            post_resp = self.client.post(
                f"/api/sales/invoices/{invoice_id}/post/{self._scope_qs()}",
                {},
                format="json",
            )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        patch_resp = self.client.patch(
            f"/api/sales/invoices/{invoice_id}/{self._scope_qs()}",
            {"reference": "SHOULD-NOT-UPDATE"},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Posted/Cancelled invoices cannot be edited.", str(patch_resp.json()))

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_post_creates_open_item_and_reverse_closes_it_for_invoice(
        self,
        mocked_post_adapter,
        mocked_auto_compliance,
    ):
        created = self._create_invoice(reference="SO-OPEN-ITEM")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        header = SalesInvoiceHeader.objects.get(pk=invoice_id)
        open_item = CustomerBillOpenItem.objects.get(header_id=invoice_id)
        self.assertEqual(open_item.doc_type, int(SalesInvoiceHeader.DocType.TAX_INVOICE))
        self.assertEqual(open_item.customer_id, self.customer.id)
        self.assertEqual(open_item.invoice_number, header.invoice_number)
        self.assertEqual(open_item.original_amount, Decimal("1180.00"))
        self.assertEqual(open_item.outstanding_amount, Decimal("1180.00"))
        self.assertEqual(open_item.settled_amount, Decimal("0.00"))
        self.assertTrue(open_item.is_open)
        self.assertEqual(header.outstanding_amount, Decimal("1180.00"))
        self.assertEqual(header.settled_amount, Decimal("0.00"))

        batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=header.id,
            voucher_no=header.invoice_number,
            revision=1,
            is_active=True,
            created_by=self.user,
        )
        entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=header.id,
            voucher_no=header.invoice_number,
            voucher_date=header.bill_date,
            posting_date=header.posting_date or header.bill_date,
            status=EntryStatus.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
            posting_batch=batch,
            narration="Original posting",
            created_by=self.user,
        )
        JournalLine.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=header.id,
            voucher_no=header.invoice_number,
            accounthead=self.customer_head,
            drcr=True,
            amount=Decimal("1180.00"),
            description="Customer debit",
            posting_date=header.posting_date or header.bill_date,
            posted_at=timezone.now(),
            created_by=self.user,
        )
        JournalLine.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.SALES,
            txn_id=header.id,
            voucher_no=header.invoice_number,
            accounthead=self.income_head,
            drcr=False,
            amount=Decimal("1180.00"),
            description="Sales credit",
            posting_date=header.posting_date or header.bill_date,
            posted_at=timezone.now(),
            created_by=self.user,
        )

        reverse_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/reverse/{self._scope_qs()}",
            {"reason": "Open item reverse check"},
            format="json",
        )
        self.assertEqual(reverse_resp.status_code, status.HTTP_200_OK, reverse_resp.json())

        open_item.refresh_from_db()
        header.refresh_from_db()
        entry.refresh_from_db()
        self.assertFalse(open_item.is_open)
        self.assertEqual(open_item.outstanding_amount, Decimal("0.00"))
        self.assertIsNotNone(open_item.last_settled_at)
        self.assertEqual(entry.status, EntryStatus.REVERSED)
        self.assertEqual(header.status, SalesInvoiceHeader.Status.CONFIRMED)
        self.assertTrue(header.is_posting_reversed)
        mocked_post_adapter.assert_called_once()
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_cancel_posted_invoice_closes_open_item_in_real_ar_state(
        self,
        mocked_post_adapter,
        mocked_auto_compliance,
    ):
        created = self._create_invoice(reference="SO-OPEN-CANCEL")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        header = SalesInvoiceHeader.objects.get(pk=invoice_id)
        open_item = CustomerBillOpenItem.objects.get(header_id=invoice_id)
        self.assertTrue(open_item.is_open)
        self.assertEqual(open_item.outstanding_amount, Decimal("1180.00"))

        self._seed_posting_entry(
            header=header,
            txn_type=TxnType.SALES,
            amount=Decimal("1180.00"),
            narration="Posted invoice",
            customer_drcr=True,
            revenue_drcr=False,
            customer_description="Customer debit",
            revenue_description="Sales credit",
        )

        cancel_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/cancel/{self._scope_qs()}",
            {"reason": "Real AR cancel check"},
            format="json",
        )
        self.assertEqual(cancel_resp.status_code, status.HTTP_200_OK, cancel_resp.json())

        open_item.refresh_from_db()
        header.refresh_from_db()
        self.assertFalse(open_item.is_open)
        self.assertEqual(open_item.outstanding_amount, Decimal("0.00"))
        self.assertIsNotNone(open_item.last_settled_at)
        self.assertEqual(header.status, SalesInvoiceHeader.Status.CANCELLED)
        self.assertEqual(header.outstanding_amount, Decimal("0.00"))
        mocked_post_adapter.assert_called_once()
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_cancel_posted_service_invoice_closes_open_item_in_real_ar_state(
        self,
        mocked_post_adapter,
        mocked_auto_compliance,
    ):
        created = self._create_invoice(
            reference="SO-SVC-OPEN-CANCEL",
            lines=[self._service_line_payload()],
        )
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        header = SalesInvoiceHeader.objects.get(pk=invoice_id)
        open_item = CustomerBillOpenItem.objects.get(header_id=invoice_id)
        self.assertTrue(open_item.is_open)
        self.assertEqual(open_item.outstanding_amount, Decimal("590.00"))

        self._seed_posting_entry(
            header=header,
            txn_type=TxnType.SALES,
            amount=Decimal("590.00"),
            narration="Posted service invoice",
            customer_drcr=True,
            revenue_drcr=False,
            customer_description="Customer debit for service invoice",
            revenue_description="Service sales credit",
        )

        cancel_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/cancel/{self._scope_qs()}",
            {"reason": "Real AR service invoice cancel check"},
            format="json",
        )
        self.assertEqual(cancel_resp.status_code, status.HTTP_200_OK, cancel_resp.json())

        open_item.refresh_from_db()
        header.refresh_from_db()
        self.assertFalse(open_item.is_open)
        self.assertEqual(open_item.outstanding_amount, Decimal("0.00"))
        self.assertIsNotNone(open_item.last_settled_at)
        self.assertEqual(header.status, SalesInvoiceHeader.Status.CANCELLED)
        self.assertEqual(header.outstanding_amount, Decimal("0.00"))
        mocked_post_adapter.assert_called_once()
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_reverse_posted_service_invoice_closes_open_item_in_real_ar_state(
        self,
        mocked_post_adapter,
        mocked_auto_compliance,
    ):
        created = self._create_invoice(
            reference="SO-SVC-OPEN-REVERSE",
            lines=[self._service_line_payload()],
        )
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        header = SalesInvoiceHeader.objects.get(pk=invoice_id)
        open_item = CustomerBillOpenItem.objects.get(header_id=invoice_id)
        self.assertTrue(open_item.is_open)
        self.assertEqual(open_item.outstanding_amount, Decimal("590.00"))

        entry = self._seed_posting_entry(
            header=header,
            txn_type=TxnType.SALES,
            amount=Decimal("590.00"),
            narration="Posted service invoice",
            customer_drcr=True,
            revenue_drcr=False,
            customer_description="Customer debit for service invoice",
            revenue_description="Service sales credit",
        )

        reverse_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/reverse/{self._scope_qs()}",
            {"reason": "Real AR service invoice reverse check"},
            format="json",
        )
        self.assertEqual(reverse_resp.status_code, status.HTTP_200_OK, reverse_resp.json())

        open_item.refresh_from_db()
        header.refresh_from_db()
        entry.refresh_from_db()
        self.assertFalse(open_item.is_open)
        self.assertEqual(open_item.outstanding_amount, Decimal("0.00"))
        self.assertIsNotNone(open_item.last_settled_at)
        self.assertEqual(entry.status, EntryStatus.REVERSED)
        self.assertEqual(header.status, SalesInvoiceHeader.Status.CONFIRMED)
        self.assertEqual(header.outstanding_amount, Decimal("0.00"))
        self.assertTrue(header.is_posting_reversed)
        mocked_post_adapter.assert_called_once()
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_post_creates_negative_open_item_for_credit_note(
        self,
        mocked_post_adapter,
        mocked_auto_compliance,
    ):
        original = self._create_invoice(reference="SO-OPEN-CN-ORIG")
        original_id = original["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        payload = self._invoice_payload(
            lines=[self._goods_line_payload(qty="1.000", rate="100.0000")],
            doc_type=int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
            reference="SCN-OPEN-001",
        )
        payload.update(
            {
                "doc_code": "SCN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
            }
        )
        create_resp = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())
        note_id = create_resp.json()["id"]

        confirm_note_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_note_resp.status_code, status.HTTP_200_OK, confirm_note_resp.json())

        post_note_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_note_resp.status_code, status.HTTP_200_OK, post_note_resp.json())

        header = SalesInvoiceHeader.objects.get(pk=note_id)
        open_item = CustomerBillOpenItem.objects.get(header_id=note_id)
        self.assertEqual(open_item.doc_type, int(SalesInvoiceHeader.DocType.CREDIT_NOTE))
        self.assertEqual(open_item.customer_id, self.customer.id)
        self.assertEqual(open_item.invoice_number, header.invoice_number)
        self.assertEqual(open_item.original_amount, Decimal("-118.00"))
        self.assertEqual(open_item.outstanding_amount, Decimal("-118.00"))
        self.assertEqual(open_item.settled_amount, Decimal("0.00"))
        self.assertTrue(open_item.is_open)
        self.assertEqual(header.outstanding_amount, Decimal("-118.00"))
        self.assertEqual(header.settled_amount, Decimal("0.00"))
        mocked_post_adapter.assert_called()
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_post_creates_positive_open_item_for_debit_note(
        self,
        mocked_post_adapter,
        mocked_auto_compliance,
    ):
        original = self._create_invoice(reference="SO-OPEN-DN-ORIG")
        original_id = original["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{original_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        payload = self._invoice_payload(
            lines=[self._goods_line_payload(qty="1.000", rate="100.0000")],
            doc_type=int(SalesInvoiceHeader.DocType.DEBIT_NOTE),
            reference="SDN-OPEN-001",
        )
        payload.update(
            {
                "doc_code": "SDN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
            }
        )
        create_resp = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())
        note_id = create_resp.json()["id"]

        confirm_note_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_note_resp.status_code, status.HTTP_200_OK, confirm_note_resp.json())

        post_note_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_note_resp.status_code, status.HTTP_200_OK, post_note_resp.json())

        header = SalesInvoiceHeader.objects.get(pk=note_id)
        open_item = CustomerBillOpenItem.objects.get(header_id=note_id)
        self.assertEqual(open_item.doc_type, int(SalesInvoiceHeader.DocType.DEBIT_NOTE))
        self.assertEqual(open_item.customer_id, self.customer.id)
        self.assertEqual(open_item.invoice_number, header.invoice_number)
        self.assertEqual(open_item.original_amount, Decimal("118.00"))
        self.assertEqual(open_item.outstanding_amount, Decimal("118.00"))
        self.assertEqual(open_item.settled_amount, Decimal("0.00"))
        self.assertTrue(open_item.is_open)
        self.assertEqual(header.outstanding_amount, Decimal("118.00"))
        self.assertEqual(header.settled_amount, Decimal("0.00"))
        mocked_post_adapter.assert_called()
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_reverse_credit_note_closes_open_item_in_real_ar_state(
        self,
        mocked_post_adapter,
        mocked_auto_compliance,
    ):
        original = self._create_invoice(reference="SO-REAL-AR-CN-ORIG")
        original_id = original["id"]

        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{original_id}/confirm/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{original_id}/post/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )

        payload = self._invoice_payload(
            lines=[self._goods_line_payload(qty="1.000", rate="100.0000")],
            doc_type=int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
            reference="SCN-REAL-AR-REV",
        )
        payload.update(
            {
                "doc_code": "SCN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
            }
        )
        create_resp = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())
        note_id = create_resp.json()["id"]

        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{note_id}/confirm/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{note_id}/post/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )

        note_header = SalesInvoiceHeader.objects.get(pk=note_id)
        open_item = CustomerBillOpenItem.objects.get(header_id=note_id)
        self.assertEqual(open_item.outstanding_amount, Decimal("-118.00"))
        entry = self._seed_posting_entry(
            header=note_header,
            txn_type=TxnType.SALES_CREDIT_NOTE,
            amount=Decimal("118.00"),
            narration="Posted credit note",
            customer_drcr=False,
            revenue_drcr=True,
            customer_description="Customer credit for credit note",
            revenue_description="Sales debit for credit note",
        )

        reverse_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/reverse/{self._scope_qs()}",
            {"reason": "Real AR reverse check"},
            format="json",
        )
        self.assertEqual(reverse_resp.status_code, status.HTTP_200_OK, reverse_resp.json())

        open_item.refresh_from_db()
        note_header.refresh_from_db()
        entry.refresh_from_db()
        self.assertFalse(open_item.is_open)
        self.assertEqual(open_item.outstanding_amount, Decimal("0.00"))
        self.assertIsNotNone(open_item.last_settled_at)
        self.assertEqual(note_header.status, SalesInvoiceHeader.Status.CONFIRMED)
        self.assertEqual(note_header.outstanding_amount, Decimal("0.00"))
        self.assertTrue(note_header.is_posting_reversed)
        self.assertEqual(entry.status, EntryStatus.REVERSED)
        mocked_post_adapter.assert_called()
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_cancel_credit_note_closes_open_item_in_real_ar_state(
        self,
        mocked_post_adapter,
        mocked_auto_compliance,
    ):
        original = self._create_invoice(reference="SO-REAL-AR-CN-CANCEL-ORIG")
        original_id = original["id"]

        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{original_id}/confirm/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{original_id}/post/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )

        payload = self._invoice_payload(
            lines=[self._goods_line_payload(qty="1.000", rate="100.0000")],
            doc_type=int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
            reference="SCN-REAL-AR-CANCEL",
        )
        payload.update(
            {
                "doc_code": "SCN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
            }
        )
        create_resp = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())
        note_id = create_resp.json()["id"]

        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{note_id}/confirm/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{note_id}/post/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )

        note_header = SalesInvoiceHeader.objects.get(pk=note_id)
        open_item = CustomerBillOpenItem.objects.get(header_id=note_id)
        self.assertEqual(open_item.outstanding_amount, Decimal("-118.00"))
        self._seed_posting_entry(
            header=note_header,
            txn_type=TxnType.SALES_CREDIT_NOTE,
            amount=Decimal("118.00"),
            narration="Posted credit note",
            customer_drcr=False,
            revenue_drcr=True,
            customer_description="Customer credit for credit note",
            revenue_description="Sales debit for credit note",
        )

        cancel_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/cancel/{self._scope_qs()}",
            {"reason": "Real AR credit note cancel check"},
            format="json",
        )
        self.assertEqual(cancel_resp.status_code, status.HTTP_200_OK, cancel_resp.json())

        open_item.refresh_from_db()
        note_header.refresh_from_db()
        self.assertFalse(open_item.is_open)
        self.assertEqual(open_item.outstanding_amount, Decimal("0.00"))
        self.assertIsNotNone(open_item.last_settled_at)
        self.assertEqual(note_header.status, SalesInvoiceHeader.Status.CANCELLED)
        self.assertEqual(note_header.outstanding_amount, Decimal("0.00"))
        mocked_post_adapter.assert_called()
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_cancel_debit_note_closes_open_item_in_real_ar_state(
        self,
        mocked_post_adapter,
        mocked_auto_compliance,
    ):
        original = self._create_invoice(reference="SO-REAL-AR-DN-ORIG")
        original_id = original["id"]

        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{original_id}/confirm/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{original_id}/post/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )

        payload = self._invoice_payload(
            lines=[self._goods_line_payload(qty="1.000", rate="100.0000")],
            doc_type=int(SalesInvoiceHeader.DocType.DEBIT_NOTE),
            reference="SDN-REAL-AR-CANCEL",
        )
        payload.update(
            {
                "doc_code": "SDN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
            }
        )
        create_resp = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())
        note_id = create_resp.json()["id"]

        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{note_id}/confirm/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{note_id}/post/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )

        note_header = SalesInvoiceHeader.objects.get(pk=note_id)
        open_item = CustomerBillOpenItem.objects.get(header_id=note_id)
        self.assertEqual(open_item.outstanding_amount, Decimal("118.00"))
        self._seed_posting_entry(
            header=note_header,
            txn_type=TxnType.SALES_DEBIT_NOTE,
            amount=Decimal("118.00"),
            narration="Posted debit note",
            customer_drcr=True,
            revenue_drcr=False,
            customer_description="Customer debit for debit note",
            revenue_description="Sales credit for debit note",
        )

        cancel_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/cancel/{self._scope_qs()}",
            {"reason": "Real AR cancel check"},
            format="json",
        )
        self.assertEqual(cancel_resp.status_code, status.HTTP_200_OK, cancel_resp.json())

        open_item.refresh_from_db()
        note_header.refresh_from_db()
        self.assertFalse(open_item.is_open)
        self.assertEqual(open_item.outstanding_amount, Decimal("0.00"))
        self.assertIsNotNone(open_item.last_settled_at)
        self.assertEqual(note_header.status, SalesInvoiceHeader.Status.CANCELLED)
        self.assertEqual(note_header.outstanding_amount, Decimal("0.00"))
        mocked_post_adapter.assert_called()
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_reverse_debit_note_closes_open_item_in_real_ar_state(
        self,
        mocked_post_adapter,
        mocked_auto_compliance,
    ):
        original = self._create_invoice(reference="SO-REAL-AR-DN-REV-ORIG")
        original_id = original["id"]

        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{original_id}/confirm/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{original_id}/post/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )

        payload = self._invoice_payload(
            lines=[self._goods_line_payload(qty="1.000", rate="100.0000")],
            doc_type=int(SalesInvoiceHeader.DocType.DEBIT_NOTE),
            reference="SDN-REAL-AR-REV",
        )
        payload.update(
            {
                "doc_code": "SDN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
            }
        )
        create_resp = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())
        note_id = create_resp.json()["id"]

        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{note_id}/confirm/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{note_id}/post/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )

        note_header = SalesInvoiceHeader.objects.get(pk=note_id)
        open_item = CustomerBillOpenItem.objects.get(header_id=note_id)
        self.assertEqual(open_item.outstanding_amount, Decimal("118.00"))
        entry = self._seed_posting_entry(
            header=note_header,
            txn_type=TxnType.SALES_DEBIT_NOTE,
            amount=Decimal("118.00"),
            narration="Posted debit note",
            customer_drcr=True,
            revenue_drcr=False,
            customer_description="Customer debit for debit note",
            revenue_description="Sales credit for debit note",
        )

        reverse_resp = self.client.post(
            f"/api/sales/invoices/{note_id}/reverse/{self._scope_qs()}",
            {"reason": "Real AR debit note reverse check"},
            format="json",
        )
        self.assertEqual(reverse_resp.status_code, status.HTTP_200_OK, reverse_resp.json())

        open_item.refresh_from_db()
        note_header.refresh_from_db()
        entry.refresh_from_db()
        self.assertFalse(open_item.is_open)
        self.assertEqual(open_item.outstanding_amount, Decimal("0.00"))
        self.assertIsNotNone(open_item.last_settled_at)
        self.assertEqual(note_header.status, SalesInvoiceHeader.Status.CONFIRMED)
        self.assertEqual(note_header.outstanding_amount, Decimal("0.00"))
        self.assertTrue(note_header.is_posting_reversed)
        self.assertEqual(entry.status, EntryStatus.REVERSED)
        mocked_post_adapter.assert_called()
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_credit_note_auto_adjust_reduces_original_invoice_and_consumes_note(
        self,
        mocked_post_adapter,
        mocked_auto_compliance,
    ):
        settings_obj = SalesSettingsService.get_settings(
            self.entity.id,
            self.subentity.id,
            entityfinid_id=self.entityfin.id,
        )
        settings_obj.policy_controls = {
            **(settings_obj.policy_controls or {}),
            "auto_adjust_credit_notes": "on",
        }
        settings_obj.save(update_fields=["policy_controls"])

        original = self._create_invoice(reference="SO-AUTO-CN-ORIG")
        original_id = original["id"]

        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{original_id}/confirm/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{original_id}/post/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )

        payload = self._invoice_payload(
            lines=[self._goods_line_payload(qty="1.000", rate="100.0000")],
            doc_type=int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
            reference="SCN-AUTO-ADJUST-001",
        )
        payload.update(
            {
                "doc_code": "SCN",
                "original_invoice": original_id,
                "note_reason": SalesInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "affects_inventory": False,
            }
        )
        create_resp = self.client.post("/api/sales/invoices/", payload, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())
        note_id = create_resp.json()["id"]

        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{note_id}/confirm/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.post(f"/api/sales/invoices/{note_id}/post/{self._scope_qs()}", {}, format="json").status_code,
            status.HTTP_200_OK,
        )

        original_header = SalesInvoiceHeader.objects.get(pk=original_id)
        note_header = SalesInvoiceHeader.objects.get(pk=note_id)
        original_open_item = CustomerBillOpenItem.objects.get(header_id=original_id)
        note_open_item = CustomerBillOpenItem.objects.get(header_id=note_id)
        settlement = CustomerSettlement.objects.get(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            customer_id=self.customer.id,
            reference_no=f"AUTO-CN-{note_id}",
            status=CustomerSettlement.Status.POSTED,
        )

        self.assertEqual(settlement.settlement_type, CustomerSettlement.SettlementType.CREDIT_NOTE_ADJUSTMENT)
        self.assertEqual(settlement.total_amount, Decimal("236.00"))
        self.assertEqual(original_open_item.outstanding_amount, Decimal("1062.00"))
        self.assertEqual(original_open_item.settled_amount, Decimal("118.00"))
        self.assertTrue(original_open_item.is_open)
        self.assertEqual(note_open_item.outstanding_amount, Decimal("0.00"))
        self.assertEqual(note_open_item.settled_amount, Decimal("-118.00"))
        self.assertFalse(note_open_item.is_open)
        self.assertEqual(original_header.outstanding_amount, Decimal("1062.00"))
        self.assertEqual(original_header.settled_amount, Decimal("118.00"))
        self.assertEqual(note_header.outstanding_amount, Decimal("0.00"))
        self.assertEqual(note_header.settlement_status, SalesInvoiceHeader.SettlementStatus.SETTLED)
        mocked_post_adapter.assert_called()
        self.assertTrue(mocked_auto_compliance.called)

    @patch("sales.services.sales_invoice_service.SalesInvoiceService._run_auto_compliance")
    @patch("sales.services.sales_invoice_service.SalesInvoicePostingAdapter.post_sales_invoice")
    def test_manual_settlement_post_and_cancel_updates_invoice_and_statement(
        self,
        mocked_post_adapter,
        mocked_auto_compliance,
    ):
        created = self._create_invoice(reference="SO-SETTLEMENT-MANUAL")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        header = SalesInvoiceHeader.objects.get(pk=invoice_id)
        open_item = CustomerBillOpenItem.objects.get(header_id=invoice_id)
        self.assertEqual(open_item.outstanding_amount, Decimal("1180.00"))

        create_settlement_resp = self.client.post(
            "/api/sales/ar/settlements/",
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "customer": self.customer.id,
                "settlement_type": CustomerSettlement.SettlementType.RECEIPT,
                "settlement_date": "2026-04-12",
                "reference_no": "SETTLE-001",
                "external_voucher_no": "RCPT-001",
                "remarks": "Manual receipt adjustment",
                "lines": [
                    {
                        "open_item_id": open_item.id,
                        "amount": "300.00",
                        "note": "Part receipt",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(create_settlement_resp.status_code, status.HTTP_201_CREATED, create_settlement_resp.json())
        settlement_id = create_settlement_resp.json()["data"]["id"]
        self.assertEqual(create_settlement_resp.json()["data"]["status"], CustomerSettlement.Status.DRAFT)

        post_settlement_resp = self.client.post(
            f"/api/sales/ar/settlements/{settlement_id}/post/",
            {},
            format="json",
        )
        self.assertEqual(post_settlement_resp.status_code, status.HTTP_200_OK, post_settlement_resp.json())
        self.assertEqual(post_settlement_resp.json()["applied_total"], "300.00")

        header.refresh_from_db()
        open_item.refresh_from_db()
        settlement = CustomerSettlement.objects.get(pk=settlement_id)
        settlement_line = settlement.lines.get()
        self.assertEqual(settlement.status, CustomerSettlement.Status.POSTED)
        self.assertEqual(settlement.total_amount, Decimal("300.00"))
        self.assertEqual(settlement_line.applied_amount_signed, Decimal("300.00"))
        self.assertEqual(open_item.settled_amount, Decimal("300.00"))
        self.assertEqual(open_item.outstanding_amount, Decimal("880.00"))
        self.assertTrue(open_item.is_open)
        self.assertEqual(header.settled_amount, Decimal("300.00"))
        self.assertEqual(header.outstanding_amount, Decimal("880.00"))
        self.assertEqual(header.settlement_status, SalesInvoiceHeader.SettlementStatus.PARTIAL)

        statement_resp = self.client.get(
            f"/api/sales/ar/customer-statement/?entity={self.entity.id}&entityfinid={self.entityfin.id}&subentity={self.subentity.id}&customer={self.customer.id}&include_closed=true",
            format="json",
        )
        self.assertEqual(statement_resp.status_code, status.HTTP_200_OK, statement_resp.json())
        statement_body = statement_resp.json()
        statement_open_item = next(row for row in statement_body["open_items"] if row["header"] == invoice_id)
        statement_settlement = next(row for row in statement_body["settlements"] if row["id"] == settlement_id)
        self.assertEqual(Decimal(str(statement_open_item["settled_amount"])), Decimal("300.00"))
        self.assertEqual(Decimal(str(statement_open_item["outstanding_amount"])), Decimal("880.00"))
        self.assertEqual(Decimal(str(statement_settlement["total_amount"])), Decimal("300.00"))
        self.assertEqual(statement_settlement["status"], CustomerSettlement.Status.POSTED)
        self.assertEqual(Decimal(str(statement_body["totals"]["settled_total"])), Decimal("300.00"))
        self.assertEqual(Decimal(str(statement_body["totals"]["outstanding_total"])), Decimal("880.00"))

        cancel_settlement_resp = self.client.post(
            f"/api/sales/ar/settlements/{settlement_id}/cancel/",
            {},
            format="json",
        )
        self.assertEqual(cancel_settlement_resp.status_code, status.HTTP_200_OK, cancel_settlement_resp.json())

        header.refresh_from_db()
        open_item.refresh_from_db()
        settlement.refresh_from_db()
        settlement_line.refresh_from_db()
        self.assertEqual(settlement.status, CustomerSettlement.Status.CANCELLED)
        self.assertEqual(settlement_line.applied_amount_signed, Decimal("0.00"))
        self.assertEqual(open_item.settled_amount, Decimal("0.00"))
        self.assertEqual(open_item.outstanding_amount, Decimal("1180.00"))
        self.assertTrue(open_item.is_open)
        self.assertEqual(header.settled_amount, Decimal("0.00"))
        self.assertEqual(header.outstanding_amount, Decimal("1180.00"))
        self.assertEqual(header.settlement_status, SalesInvoiceHeader.SettlementStatus.OPEN)
        mocked_post_adapter.assert_called_once()
        self.assertTrue(mocked_auto_compliance.called)
