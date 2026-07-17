from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from catalog.models import Product, ProductCategory, UnitOfMeasure
from entity.models import Entity, EntityAddress, EntityFinancialYear, EntityGstRegistration, GstRegistrationType, SubEntity
from financial.models import AccountCommercialProfile, AccountComplianceProfile, Ledger, ShippingDetails, accountHead, accounttype
from financial.services import create_account_with_synced_ledger
from geography.models import City, Country, District, State
from numbering.models import DocumentNumberSeries, DocumentType
from posting.models import Entry, EntryStatus, JournalLine, PostingBatch, TxnType
from sales.models import SalesInvoiceHeader, SalesInvoiceLine, SalesLockPeriod
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
        self._codes_patch.start()
        self.addCleanup(self._entity_scope_patch.stop)
        self.addCleanup(self._codes_patch.stop)

    def _scope_qs(self) -> str:
        return f"?entity_id={self.entity.id}&entityfinid={self.entityfin.id}&subentity_id={self.subentity.id}"

    def _attachment_scope_qs(self) -> str:
        return f"?entity={self.entity.id}&entityfinid={self.entityfin.id}&subentity={self.subentity.id}"

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
    def test_post_requires_confirmed_invoice(self, _mocked_post_adapter):
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
