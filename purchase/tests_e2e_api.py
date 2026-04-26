from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from catalog.models import Product, ProductCategory, UnitOfMeasure
from entity.models import Entity, EntityAddress, EntityFinancialYear, EntityGstRegistration, GstRegistrationType, SubEntity
from financial.models import AccountCommercialProfile, AccountComplianceProfile, Ledger, account, accountHead, accounttype
from financial.services import create_account_with_synced_ledger
from geography.models import City, Country, District, State
from numbering.models import DocumentNumberSeries, DocumentType
from purchase.models.gstr2b_models import Gstr2bImportBatch, Gstr2bImportRow
from purchase.models.purchase_ap import VendorBillOpenItem
from purchase.models.purchase_core import PurchaseInvoiceHeader, PurchaseInvoiceLine
from purchase.services.purchase_settings_service import PurchaseSettingsService


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class PurchaseApiEndToEndTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="purchase-e2e-user",
            email="purchase-e2e@example.com",
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
            entityname="Purchase E2E Entity",
            legalname="Purchase E2E Entity Pvt Ltd",
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
            accounttypename="Current Liabilities",
            accounttypecode="CL001",
            createdby=self.user,
        )
        self.credit_head = accountHead.objects.create(
            entity=self.entity,
            name="Sundry Creditors",
            code=7000,
            balanceType="Credit",
            drcreffect="Credit",
            accounttype=self.acc_type,
            createdby=self.user,
        )
        self.debit_head = accountHead.objects.create(
            entity=self.entity,
            name="Purchase",
            code=1000,
            balanceType="Debit",
            drcreffect="Debit",
            accounttype=self.acc_type,
            createdby=self.user,
        )

        vendor_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=9001,
            name="Vendor-A",
            accounthead=self.credit_head,
            createdby=self.user,
        )
        self.vendor = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity,
                "ledger": vendor_ledger,
                "accountname": "Vendor-A",
                "createdby": self.user,
            },
            ledger_overrides={"ledger_code": 9001, "accounthead": self.credit_head, "is_party": True},
        )
        AccountCommercialProfile.objects.update_or_create(
            account=self.vendor,
            defaults={"entity": self.entity, "partytype": "Vendor", "createdby": self.user},
        )
        AccountComplianceProfile.objects.update_or_create(
            account=self.vendor,
            defaults={"entity": self.entity, "gstno": "27ABCDE1234F1Z5", "createdby": self.user},
        )

        service_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=5001,
            name="Service Expense",
            accounthead=self.debit_head,
            createdby=self.user,
        )
        self.service_purchase_account = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity,
                "ledger": service_ledger,
                "accountname": "Service Expense",
                "createdby": self.user,
            },
            ledger_overrides={"ledger_code": 5001, "accounthead": self.debit_head, "is_party": False},
        )

        self.uom = UnitOfMeasure.objects.create(entity=self.entity, code="KGS", description="Kilograms")
        self.product_category = ProductCategory.objects.create(entity=self.entity, pcategoryname="Raw Material")
        self.goods_product = Product.objects.create(
            entity=self.entity,
            productname="Product-A",
            sku="PRD-A",
            productdesc="Goods product",
            productcategory=self.product_category,
            base_uom=self.uom,
            is_service=False,
            is_batch_managed=False,
        )
        self.batch_product = Product.objects.create(
            entity=self.entity,
            productname="Product-Batch",
            sku="PRD-B",
            productdesc="Batch product",
            productcategory=self.product_category,
            base_uom=self.uom,
            is_service=False,
            is_batch_managed=True,
        )

        self.purchase_doc_type = DocumentType.objects.create(
            module="purchase",
            name="Purchase Tax Invoice",
            doc_key="PURCHASE_TAX_INVOICE",
            default_code="PINV",
            is_active=True,
        )
        DocumentNumberSeries.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            doc_type=self.purchase_doc_type,
            doc_code="PINV",
            prefix="PI",
            starting_number=1001,
            current_number=1001,
            is_active=True,
            created_by=self.user,
        )

        self._entity_scope_patch = patch(
            "purchase.views.rbac.EffectivePermissionService.entity_for_user",
            side_effect=lambda _user, entity_id: SimpleNamespace(id=int(entity_id)),
        )
        self._codes_patch = patch(
            "purchase.views.rbac.EffectivePermissionService.permission_codes_for_user",
            return_value={
                "purchase.invoice.view",
                "purchase.invoice.read",
                "purchase.invoice.list",
                "purchase.invoice.create",
                "purchase.invoice.update",
                "purchase.invoice.edit",
                "purchase.invoice.delete",
                "purchase.invoice.post",
                "purchase.invoice.unpost",
                "purchase.invoice.cancel",
            },
        )
        self._statutory_codes_patch = patch(
            "purchase.views.purchase_statutory.EffectivePermissionService.permission_codes_for_user",
            return_value={
                "purchase.invoice.view",
                "purchase.invoice.read",
                "purchase.invoice.list",
                "purchase.invoice.create",
                "purchase.invoice.update",
                "purchase.invoice.edit",
                "purchase.invoice.delete",
                "purchase.invoice.post",
                "purchase.invoice.unpost",
                "purchase.invoice.cancel",
                "purchase.statutory.view",
                "purchase.statutory.manage",
                "purchase.statutory.approve",
            },
        )
        self._entity_scope_patch.start()
        self._codes_patch.start()
        self._statutory_codes_patch.start()
        self.addCleanup(self._entity_scope_patch.stop)
        self.addCleanup(self._codes_patch.stop)
        self.addCleanup(self._statutory_codes_patch.stop)

    def _scope_qs(self) -> str:
        return f"?entity={self.entity.id}&entityfinid={self.entityfin.id}&subentity={self.subentity.id}"

    def _goods_line_payload(self, *, product_id: int | None = None, qty: str = "10.0000", rate: str = "100.00"):
        taxable = Decimal(qty) * Decimal(rate)
        igst = (taxable * Decimal("0.18")).quantize(Decimal("0.01"))
        return {
            "id": None,
            "line_no": 1,
            "product": product_id or self.goods_product.id,
            "uom": self.uom.id,
            "qty": qty,
            "free_qty": "0.0000",
            "rate": rate,
            "product_desc": "Test goods",
            "is_service": False,
            "taxability": int(PurchaseInvoiceHeader.Taxability.TAXABLE),
            "gst_rate": "18.00",
            "cgst_percent": "0.00",
            "sgst_percent": "0.00",
            "igst_percent": "18.00",
            "taxable_value": str(taxable.quantize(Decimal("0.01"))),
            "cgst_amount": "0.00",
            "sgst_amount": "0.00",
            "igst_amount": str(igst),
            "cess_percent": "0.00",
            "cess_amount": "0.00",
            "line_total": str((taxable + igst).quantize(Decimal("0.01"))),
            "is_itc_eligible": True,
        }

    def _service_line_payload(self):
        return {
            "id": None,
            "line_no": 1,
            "product": None,
            "purchase_account": self.service_purchase_account.id,
            "uom": None,
            "qty": "1.0000",
            "free_qty": "0.0000",
            "rate": "500.00",
            "product_desc": "Consulting",
            "is_service": True,
            "taxability": int(PurchaseInvoiceHeader.Taxability.TAXABLE),
            "gst_rate": "18.00",
            "cgst_percent": "0.00",
            "sgst_percent": "0.00",
            "igst_percent": "18.00",
            "taxable_value": "500.00",
            "cgst_amount": "0.00",
            "sgst_amount": "0.00",
            "igst_amount": "90.00",
            "cess_percent": "0.00",
            "cess_amount": "0.00",
            "line_total": "590.00",
            "is_itc_eligible": True,
        }

    def _invoice_payload(self, *, lines: list[dict], supplier_invoice_number: str = "INV-001"):
        return {
            "doc_type": int(PurchaseInvoiceHeader.DocType.TAX_INVOICE),
            "bill_date": "2026-04-10",
            "posting_date": "2026-04-10",
            "supplier_invoice_number": supplier_invoice_number,
            "supplier_invoice_date": "2026-04-10",
            "vendor": self.vendor.id,
            "vendor_name": "Vendor-A",
            "vendor_gstin": "27ABCDE1234F1Z5",
            "vendor_state": self.state_home.id,
            "supplier_state": self.state_home.id,
            "place_of_supply_state": self.state_other.id,
            "supply_category": int(PurchaseInvoiceHeader.SupplyCategory.DOMESTIC),
            "default_taxability": int(PurchaseInvoiceHeader.Taxability.TAXABLE),
            "tax_regime": int(PurchaseInvoiceHeader.TaxRegime.INTER),
            "is_igst": True,
            "is_reverse_charge": False,
            "is_itc_eligible": True,
            "itc_claim_status": int(PurchaseInvoiceHeader.ItcClaimStatus.PENDING),
            "status": int(PurchaseInvoiceHeader.Status.DRAFT),
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.subentity.id,
            "lines": lines,
            "charges": [],
            "custom_fields": {},
            "withholding_enabled": False,
            "gst_tds_enabled": False,
            "vendor_gst_tds_declared": False,
            "vendor_tds_declared": False,
        }

    def _create_invoice(self, supplier_invoice_number: str = "INV-001", lines: list[dict] | None = None) -> dict:
        payload = self._invoice_payload(lines=lines or [self._goods_line_payload()], supplier_invoice_number=supplier_invoice_number)
        response = self.client.post("/api/purchase/purchase-invoices/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        return response.json()

    def test_create_goods_invoice_with_new_line_id_null(self):
        body = self._create_invoice(lines=[self._goods_line_payload()])
        self.assertIn("id", body)
        self.assertEqual(body["status"], int(PurchaseInvoiceHeader.Status.DRAFT))
        self.assertEqual(len(body["lines"]), 1)
        self.assertIsNotNone(body["lines"][0]["id"])

    def test_create_batch_managed_product_requires_batch_number(self):
        bad_line = self._goods_line_payload(product_id=self.batch_product.id)
        bad_line["batch_number"] = ""
        response = self.client.post(
            "/api/purchase/purchase-invoices/",
            self._invoice_payload(lines=[bad_line], supplier_invoice_number="INV-BATCH"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("batch", str(response.json()).lower())

    def test_line_mode_filters_goods_vs_service(self):
        self._create_invoice(supplier_invoice_number="INV-GOODS", lines=[self._goods_line_payload()])
        self._create_invoice(supplier_invoice_number="INV-SERVICE", lines=[self._service_line_payload()])

        goods_resp = self.client.get(f"/api/purchase/purchase-invoices/{self._scope_qs()}&line_mode=goods")
        self.assertEqual(goods_resp.status_code, status.HTTP_200_OK)
        goods_payload = goods_resp.json()
        goods_rows = goods_payload.get("results", goods_payload) if isinstance(goods_payload, dict) else goods_payload
        self.assertEqual(len(goods_rows), 1)
        self.assertEqual(goods_rows[0]["supplier_invoice_number"], "INV-GOODS")

        service_resp = self.client.get(f"/api/purchase/purchase-invoices/{self._scope_qs()}&line_mode=service")
        self.assertEqual(service_resp.status_code, status.HTTP_200_OK)
        service_payload = service_resp.json()
        service_rows = service_payload.get("results", service_payload) if isinstance(service_payload, dict) else service_payload
        self.assertEqual(len(service_rows), 1)
        self.assertEqual(service_rows[0]["supplier_invoice_number"], "INV-SERVICE")

    def test_patch_updates_line_and_recomputes_totals(self):
        created = self._create_invoice(supplier_invoice_number="INV-UPD")
        invoice_id = created["id"]

        updated_line = self._goods_line_payload(qty="20.0000", rate="100.00")
        updated_line["id"] = created["lines"][0]["id"]
        updated_line["line_no"] = created["lines"][0]["line_no"]

        patch_resp = self.client.patch(
            f"/api/purchase/purchase-invoices/{invoice_id}/{self._scope_qs()}",
            {"lines": [updated_line]},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.json())
        body = patch_resp.json()
        self.assertEqual(Decimal(str(body["total_taxable"])), Decimal("2000.00"))
        self.assertEqual(Decimal(str(body["total_igst"])), Decimal("360.00"))
        self.assertEqual(Decimal(str(body["grand_total"])), Decimal("2360.00"))

    def test_confirm_allocates_number_and_delete_policy_allows_only_draft_delete(self):
        created = self._create_invoice(supplier_invoice_number="INV-CONFIRM")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())
        confirmed_data = confirm_resp.json()["data"]
        self.assertEqual(confirmed_data["status"], int(PurchaseInvoiceHeader.Status.CONFIRMED))
        self.assertEqual(confirmed_data["doc_no"], 1001)
        self.assertTrue(confirmed_data["purchase_number"])

        delete_confirmed = self.client.delete(f"/api/purchase/purchase-invoices/{invoice_id}/{self._scope_qs()}")
        self.assertEqual(delete_confirmed.status_code, status.HTTP_400_BAD_REQUEST)

        draft = self._create_invoice(supplier_invoice_number="INV-DEL-DRAFT")
        delete_draft = self.client.delete(f"/api/purchase/purchase-invoices/{draft['id']}/{self._scope_qs()}")
        self.assertEqual(delete_draft.status_code, status.HTTP_204_NO_CONTENT)

    def test_cancel_marks_draft_invoice_cancelled(self):
        created = self._create_invoice(supplier_invoice_number="INV-CANCEL")
        invoice_id = created["id"]

        cancel_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/cancel/{self._scope_qs()}",
            {"reason": "Test cancel"},
            format="json",
        )
        self.assertEqual(cancel_resp.status_code, status.HTTP_200_OK, cancel_resp.json())
        self.assertEqual(cancel_resp.json()["data"]["status"], int(PurchaseInvoiceHeader.Status.CANCELLED))

    def test_itc_and_2b_actions_after_confirm(self):
        created = self._create_invoice(supplier_invoice_number="INV-ITC")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        block_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/itc/block/{self._scope_qs()}",
            {"reason": "Blocked for review"},
            format="json",
        )
        self.assertEqual(block_resp.status_code, status.HTTP_200_OK, block_resp.json())
        self.assertEqual(block_resp.json()["data"]["itc_claim_status"], int(PurchaseInvoiceHeader.ItcClaimStatus.BLOCKED))
        self.assertFalse(block_resp.json()["data"]["is_itc_eligible"])

        unblock_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/itc/unblock/{self._scope_qs()}",
            {"reason": "Review done"},
            format="json",
        )
        self.assertEqual(unblock_resp.status_code, status.HTTP_200_OK, unblock_resp.json())
        self.assertEqual(unblock_resp.json()["data"]["itc_claim_status"], int(PurchaseInvoiceHeader.ItcClaimStatus.PENDING))
        self.assertTrue(unblock_resp.json()["data"]["is_itc_eligible"])

        match_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/gstr2b/status/{self._scope_qs()}",
            {"match_status": int(PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED)},
            format="json",
        )
        self.assertEqual(match_resp.status_code, status.HTTP_200_OK, match_resp.json())
        self.assertEqual(
            match_resp.json()["data"]["gstr2b_match_status"],
            int(PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED),
        )

        claim_period = timezone.localdate().strftime("%Y-%m")
        claim_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/itc/claim/{self._scope_qs()}",
            {"period": claim_period},
            format="json",
        )
        self.assertEqual(claim_resp.status_code, status.HTTP_200_OK, claim_resp.json())
        self.assertEqual(claim_resp.json()["data"]["itc_claim_status"], int(PurchaseInvoiceHeader.ItcClaimStatus.CLAIMED))

    def test_ap_open_items_create_post_cancel_settlement_flow(self):
        PurchaseSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"policy_controls": {"settlement_mode": "basic", "allocation_policy": "manual"}},
        )

        created = self._create_invoice(supplier_invoice_number="INV-AP")
        header = PurchaseInvoiceHeader.objects.get(pk=created["id"])
        open_item = VendorBillOpenItem.objects.create(
            header=header,
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor=self.vendor,
            vendor_ledger_id=self.vendor.ledger_id,
            doc_type=int(header.doc_type),
            bill_date=header.bill_date,
            due_date=header.bill_date,
            purchase_number=header.purchase_number,
            supplier_invoice_number=header.supplier_invoice_number,
            original_amount=Decimal("1180.00"),
            gross_amount=Decimal("1180.00"),
            tds_deducted=Decimal("0.00"),
            gst_tds_deducted=Decimal("0.00"),
            net_payable_amount=Decimal("1180.00"),
            settled_amount=Decimal("0.00"),
            outstanding_amount=Decimal("1180.00"),
            is_open=True,
        )

        open_items_resp = self.client.get(
            f"/api/purchase/ap/open-items/{self._scope_qs()}&vendor={self.vendor.id}"
        )
        self.assertEqual(open_items_resp.status_code, status.HTTP_200_OK, open_items_resp.json())
        self.assertTrue(any(int(r["id"]) == int(open_item.id) for r in open_items_resp.json()))

        create_settlement_resp = self.client.post(
            "/api/purchase/ap/settlements/",
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "vendor": self.vendor.id,
                "settlement_type": "payment",
                "settlement_date": "2026-04-12",
                "reference_no": "SET-001",
                "lines": [{"open_item_id": open_item.id, "amount": "500.00"}],
            },
            format="json",
        )
        self.assertEqual(create_settlement_resp.status_code, status.HTTP_201_CREATED, create_settlement_resp.json())
        settlement_id = create_settlement_resp.json()["data"]["id"]

        post_resp = self.client.post(f"/api/purchase/ap/settlements/{settlement_id}/post/", {}, format="json")
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())
        self.assertEqual(post_resp.json()["data"]["status"], 2)
        self.assertEqual(Decimal(str(post_resp.json()["applied_total"])), Decimal("500.00"))

        cancel_resp = self.client.post(f"/api/purchase/ap/settlements/{settlement_id}/cancel/", {}, format="json")
        self.assertEqual(cancel_resp.status_code, status.HTTP_200_OK, cancel_resp.json())
        self.assertEqual(cancel_resp.json()["data"]["status"], 9)

    def test_attachment_upload_list_download_delete(self):
        created = self._create_invoice(supplier_invoice_number="INV-ATTACH")
        invoice_id = created["id"]
        scope = self._scope_qs()

        upload = SimpleUploadedFile(
            "supporting.txt",
            b"purchase attachment payload",
            content_type="text/plain",
        )
        upload_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/attachments/{scope}",
            {"attachments": [upload]},
            format="multipart",
        )
        self.assertEqual(upload_resp.status_code, status.HTTP_201_CREATED, upload_resp.json())
        attachment_id = upload_resp.json()["data"][0]["id"]

        list_resp = self.client.get(f"/api/purchase/purchase-invoices/{invoice_id}/attachments/{scope}")
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK, list_resp.json())
        self.assertEqual(len(list_resp.json()), 1)

        download_resp = self.client.get(
            f"/api/purchase/purchase-invoices/{invoice_id}/attachments/{attachment_id}/download/{scope}"
        )
        self.assertEqual(download_resp.status_code, status.HTTP_200_OK)
        self.assertIn("attachment;", download_resp.get("Content-Disposition", ""))

        delete_resp = self.client.delete(
            f"/api/purchase/purchase-invoices/{invoice_id}/attachments/{attachment_id}/{scope}"
        )
        self.assertEqual(delete_resp.status_code, status.HTTP_200_OK, delete_resp.json())

    def test_gstr2b_batch_import_match_and_review(self):
        created = self._create_invoice(supplier_invoice_number="G2B-INV-1")
        invoice_id = created["id"]

        import_resp = self.client.post(
            "/api/purchase/gstr2b/import-batches/",
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "period": "2026-04",
                "source": "gstr2b",
                "rows": [
                    {
                        "supplier_gstin": "27ABCDE1234F1Z5",
                        "supplier_name": "Vendor-A",
                        "supplier_invoice_number": "G2B-INV-1",
                        "supplier_invoice_date": "2026-04-10",
                        "is_igst": True,
                        "taxable_value": "1000.00",
                        "igst": "180.00",
                        "cgst": "0.00",
                        "sgst": "0.00",
                        "cess": "0.00",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(import_resp.status_code, status.HTTP_201_CREATED, import_resp.json())
        batch_id = import_resp.json()["data"]["id"]

        rows_resp = self.client.get(f"/api/purchase/gstr2b/import-batches/{batch_id}/rows/{self._scope_qs()}")
        self.assertEqual(rows_resp.status_code, status.HTTP_200_OK, rows_resp.json())
        self.assertEqual(rows_resp.json()["count"], 1)
        row_id = rows_resp.json()["results"][0]["id"]

        match_resp = self.client.post(f"/api/purchase/gstr2b/import-batches/{batch_id}/match/", {}, format="json")
        self.assertEqual(match_resp.status_code, status.HTTP_200_OK, match_resp.json())
        self.assertEqual(match_resp.json()["summary"]["total_rows"], 1)

        review_resp = self.client.post(
            f"/api/purchase/gstr2b/import-rows/{row_id}/review/{self._scope_qs()}",
            {"match_status": "MATCHED", "matched_purchase": invoice_id, "comment": "Reviewed"},
            format="json",
        )
        self.assertEqual(review_resp.status_code, status.HTTP_200_OK, review_resp.json())
        self.assertEqual(review_resp.json()["data"]["match_status"], "MATCHED")

        self.assertTrue(Gstr2bImportBatch.objects.filter(pk=batch_id).exists())
        self.assertTrue(Gstr2bImportRow.objects.filter(pk=row_id).exists())

    @patch("purchase.views.purchase_statutory.PurchaseStatutoryService.reconciliation_summary")
    def test_statutory_summary_endpoint(self, mock_summary):
        mock_summary.return_value = {
            "totals": {"rows": 1, "liability": "100.00"},
            "sections": [{"code": "IT_TDS", "amount": "100.00"}],
        }
        resp = self.client.get(
            f"/api/purchase/statutory/summary/{self._scope_qs()}&tax_type=IT_TDS&period_from=2026-04-01&period_to=2026-04-30"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.json())
        self.assertIn("summary", resp.json())
        self.assertIn("totals", resp.json()["summary"])
