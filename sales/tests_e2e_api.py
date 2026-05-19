from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from catalog.models import Product, ProductCategory, UnitOfMeasure
from entity.models import Entity, EntityAddress, EntityFinancialYear, EntityGstRegistration, GstRegistrationType, SubEntity
from financial.models import AccountCommercialProfile, AccountComplianceProfile, Ledger, accountHead, accounttype
from financial.services import create_account_with_synced_ledger
from geography.models import City, Country, District, State
from numbering.models import DocumentNumberSeries, DocumentType
from posting.models import Entry, EntryStatus, JournalLine, PostingBatch, TxnType
from sales.models import SalesInvoiceHeader


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
                "sales.credit_note.post",
                "sales.credit_note.unpost",
                "sales.credit_note.cancel",
                "sales.debit_note.view",
                "sales.debit_note.read",
                "sales.debit_note.list",
                "sales.debit_note.create",
                "sales.debit_note.update",
                "sales.debit_note.edit",
                "sales.debit_note.post",
                "sales.debit_note.unpost",
                "sales.debit_note.cancel",
            },
        )
        self._entity_scope_patch.start()
        self._codes_patch.start()
        self.addCleanup(self._entity_scope_patch.stop)
        self.addCleanup(self._codes_patch.stop)

    def _scope_qs(self) -> str:
        return f"?entity_id={self.entity.id}&entityfinid={self.entityfin.id}&subentity_id={self.subentity.id}"

    def _goods_line_payload(self, *, qty: str = "10.000", rate: str = "100.0000") -> dict:
        return {
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

    def _invoice_payload(self, *, lines: list[dict], doc_type: int | None = None, reference: str = "SO-001") -> dict:
        return {
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

    def _create_invoice(self, *, lines: list[dict] | None = None, endpoint: str = "/api/sales/invoices/", **payload_overrides) -> dict:
        payload = self._invoice_payload(lines=lines or [self._goods_line_payload()])
        payload.update(payload_overrides)
        response = self.client.post(endpoint, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        return response.json()

    def test_create_goods_invoice_with_new_line_id_null(self):
        body = self._create_invoice()
        self.assertIn("id", body)
        self.assertEqual(body["status"], int(SalesInvoiceHeader.Status.DRAFT))
        self.assertEqual(len(body["lines"]), 1)
        self.assertIsNotNone(body["lines"][0]["id"])

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

        service_resp = self.client.get(f"/api/sales/service-invoices/{self._scope_qs()}&line_mode=service")
        self.assertEqual(service_resp.status_code, status.HTTP_200_OK)
        service_rows = service_resp.json()
        self.assertEqual(len(service_rows), 1)
        self.assertEqual(service_rows[0]["customer_name"], "Customer-A")

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

    def test_post_requires_confirmed_invoice(self):
        created = self._create_invoice(reference="SO-POST-BLOCK")
        invoice_id = created["id"]

        post_resp = self.client.post(
            f"/api/sales/invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Only Confirmed invoices can be posted.", str(post_resp.json()))

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
