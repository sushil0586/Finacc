from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from catalog.models import Product, ProductCategory, ProductPurchaseBehavior, UnitOfMeasure
from entity.models import (
    Entity,
    EntityAddress,
    EntityFinancialYear,
    EntityGstRegistration,
    GstRegistrationType,
    SubEntity,
)
from financial.models import AccountCommercialProfile, AccountComplianceProfile, Ledger, accountHead, accounttype
from financial.services import create_account_with_synced_ledger
from geography.models import City, Country, District, State
from purchase.services.purchase_invoice_import_service import PurchaseInvoiceImportService


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class PurchaseInvoiceImportDraftTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="purchase-import", email="purchase-import@example.com", password="pass123")
        self.client.force_authenticate(user=self.user)
        cache.clear()

        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state = State.objects.create(statename="Maharashtra", statecode="27", country=self.country)
        self.district = District.objects.create(districtname="District", districtcode="DT", state=self.state)
        self.city = City.objects.create(cityname="Mumbai", citycode="MUM", pincode="400001", distt=self.district)
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Purchase Import Entity",
            legalname="Purchase Import Entity Pvt Ltd",
            business_type=Entity.BusinessType.MIXED,
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        EntityAddress.objects.create(
            entity=self.entity,
            address_type=EntityAddress.AddressType.REGISTERED,
            line1="Address",
            country=self.country,
            state=self.state,
            district=self.district,
            city=self.city,
            pincode="400001",
            is_primary=True,
            createdby=self.user,
        )
        EntityGstRegistration.objects.create(
            entity=self.entity,
            gstin="27AAAAA9999A1Z5",
            registration_type=self.gst_type,
            state=self.state,
            is_primary=True,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Branch")
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.user,
        )
        self.acc_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Vendor",
            accounttypecode="V100",
            createdby=self.user,
        )
        self.vendor_head = accountHead.objects.create(
            entity=self.entity,
            name="Creditors",
            code=200,
            balanceType="Credit",
            drcreffect="Credit",
            accounttype=self.acc_type,
            createdby=self.user,
        )
        self.vendor_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=4001,
            name="Alpha Traders",
            accounthead=self.vendor_head,
            createdby=self.user,
        )
        self.vendor = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity,
                "ledger": self.vendor_ledger,
                "accountname": "Alpha Traders",
                "createdby": self.user,
            },
            ledger_overrides={"ledger_code": 4001, "accounthead": self.vendor_head, "is_party": True},
        )
        AccountComplianceProfile.objects.update_or_create(
            account=self.vendor,
            defaults={"entity": self.entity, "gstno": "27ABCDE1234F1Z5", "createdby": self.user},
        )
        AccountCommercialProfile.objects.update_or_create(
            account=self.vendor,
            defaults={"entity": self.entity, "partytype": "Vendor", "createdby": self.user},
        )
        self.uom = UnitOfMeasure.objects.create(entity=self.entity, code="PCS", description="Pieces")
        self.product_category = ProductCategory.objects.create(entity=self.entity, pcategoryname="Inventory Goods")
        self.product = Product.objects.create(
            entity=self.entity,
            productname="Inventory Product",
            sku="INV-001",
            productdesc="Inventory Product",
            productcategory=self.product_category,
            base_uom=self.uom,
            is_service=False,
            purchase_behavior=ProductPurchaseBehavior.INVENTORY,
            purchase_account=self.vendor,
        )

    def _scope(self) -> dict[str, object]:
        return {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.subentity.id,
        }

    def _import_url(self) -> str:
        scope = "&".join(f"{key}={value}" for key, value in self._scope().items())
        return f"{reverse('purchase-invoice-import-draft')}?{scope}"

    def test_import_draft_parses_txt_and_matches_existing_masters(self):
        upload = SimpleUploadedFile(
            "invoice.txt",
            (
                b"Vendor: Alpha Traders\n"
                b"GSTIN: 27ABCDE1234F1Z5\n"
                b"Invoice No: PI-101\n"
                b"Invoice Date: 14/07/2026\n"
                b"Inventory Product|2|150|300\n"
                b"Grand Total: 300\n"
            ),
            content_type="text/plain",
        )

        response = self.client.post(
            self._import_url(),
            data={"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["header"]["supplier_invoice_number"], "PI-101")
        self.assertEqual(response.data["matches"]["vendor"]["status"], "matched")
        self.assertEqual(response.data["matches"]["vendor"]["id"], self.vendor.id)
        self.assertEqual(len(response.data["lines"]), 1)
        self.assertEqual(response.data["lines"][0]["product_match"]["status"], "matched")
        self.assertEqual(response.data["lines"][0]["product_match"]["id"], self.product.id)

    @patch("purchase.services.purchase_invoice_import_service.generate_text")
    def test_import_draft_uses_ai_structuring_when_deterministic_parse_is_weak(self, mocked_generate_text):
        mocked_generate_text.return_value = (
            '{"header":{"vendor_name":"Alpha Traders","vendor_gstin":"27ABCDE1234F1Z5","supplier_invoice_number":"AI-22","supplier_invoice_date":"2026-07-14","grand_total":450},'
            '"lines":[{"description":"Inventory Product","product_name":"Inventory Product","qty":3,"rate":150,"amount":450,"gst_rate":18}]}'
        )
        upload = SimpleUploadedFile(
            "invoice.txt",
            b"Inv AI sample\nUnknown structure\nTotal due maybe 450",
            content_type="text/plain",
        )

        response = self.client.post(
            self._import_url(),
            data={"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["header"]["supplier_invoice_number"], "AI-22")
        self.assertEqual(response.data["matches"]["vendor"]["status"], "matched")
        self.assertEqual(response.data["lines"][0]["product_match"]["status"], "matched")

    @patch("purchase.services.purchase_invoice_import_service.generate_multimodal_text")
    def test_import_draft_can_use_vision_for_image_files(self, mocked_generate_multimodal_text):
        mocked_generate_multimodal_text.return_value = (
            '{"header":{"vendor_name":"Alpha Traders","vendor_gstin":"27ABCDE1234F1Z5","supplier_invoice_number":"IMG-9","supplier_invoice_date":"2026-07-14","grand_total":300},'
            '"lines":[{"description":"Inventory Product","product_name":"Inventory Product","qty":2,"rate":150,"amount":300,"gst_rate":18}]}'
        )
        upload = SimpleUploadedFile("invoice.png", b"fake-image", content_type="image/png")

        response = self.client.post(
            self._import_url(),
            data={"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["header"]["supplier_invoice_number"], "IMG-9")
        self.assertEqual(response.data["matches"]["vendor"]["status"], "matched")
        self.assertEqual(response.data["lines"][0]["product_match"]["status"], "matched")
        warning_codes = {item["code"] for item in response.data["warnings"]}
        self.assertNotIn("image_ocr_pending", warning_codes)

    def test_import_draft_accepts_image_and_returns_ocr_pending_warning(self):
        upload = SimpleUploadedFile("invoice.png", b"fake-image", content_type="image/png")

        response = self.client.post(
            self._import_url(),
            data={"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200, response.data)
        warning_codes = {item["code"] for item in response.data["warnings"]}
        self.assertIn("image_ocr_pending", warning_codes)

    @patch.object(PurchaseInvoiceImportService, "_render_pdf_first_page_image")
    @patch.object(PurchaseInvoiceImportService, "_extract_pdf_embedded_image")
    @patch("purchase.services.purchase_invoice_import_service.generate_multimodal_text")
    def test_import_draft_can_use_embedded_pdf_image_for_vision(self, mocked_generate_multimodal_text, mocked_extract_pdf_embedded_image, mocked_render_pdf_first_page_image):
        mocked_extract_pdf_embedded_image.return_value = (b"pdf-image", "image/png", "page 1 image 1")
        mocked_render_pdf_first_page_image.return_value = None
        mocked_generate_multimodal_text.return_value = (
            '{"header":{"vendor_name":"Alpha Traders","vendor_gstin":"27ABCDE1234F1Z5","supplier_invoice_number":"PDF-IMG-1","supplier_invoice_date":"2026-07-14","grand_total":300},'
            '"lines":[{"description":"Inventory Product","product_name":"Inventory Product","qty":2,"rate":150,"amount":300,"gst_rate":18}]}'
        )
        upload = SimpleUploadedFile("invoice.pdf", b"%PDF-1.4 fake", content_type="application/pdf")

        with patch.object(PurchaseInvoiceImportService, "_extract_text", return_value=""):
            response = self.client.post(
                self._import_url(),
                data={"file": upload},
                format="multipart",
            )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["header"]["supplier_invoice_number"], "PDF-IMG-1")
        self.assertEqual(response.data["matches"]["vendor"]["status"], "matched")
        self.assertEqual(response.data["lines"][0]["product_match"]["status"], "matched")
        warning_codes = {item["code"] for item in response.data["warnings"]}
        self.assertNotIn("pdf_ocr_pending", warning_codes)

    @patch.object(PurchaseInvoiceImportService, "_render_pdf_first_page_image")
    @patch.object(PurchaseInvoiceImportService, "_extract_pdf_embedded_image")
    @patch("purchase.services.purchase_invoice_import_service.generate_multimodal_text")
    def test_import_draft_can_use_rasterized_pdf_page_for_vision(self, mocked_generate_multimodal_text, mocked_extract_pdf_embedded_image, mocked_render_pdf_first_page_image):
        mocked_extract_pdf_embedded_image.return_value = None
        mocked_render_pdf_first_page_image.return_value = (b"pdf-raster", "image/png", "page 1 rasterized")
        mocked_generate_multimodal_text.return_value = (
            '{"header":{"vendor_name":"Alpha Traders","vendor_gstin":"27ABCDE1234F1Z5","supplier_invoice_number":"PDF-RASTER-1","supplier_invoice_date":"2026-07-14","grand_total":300},'
            '"lines":[{"description":"Inventory Product","product_name":"Inventory Product","qty":2,"rate":150,"amount":300,"gst_rate":18}]}'
        )
        upload = SimpleUploadedFile("invoice.pdf", b"%PDF-1.4 fake", content_type="application/pdf")

        with patch.object(PurchaseInvoiceImportService, "_extract_text", return_value=""):
            response = self.client.post(
                self._import_url(),
                data={"file": upload},
                format="multipart",
            )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["header"]["supplier_invoice_number"], "PDF-RASTER-1")
        self.assertEqual(response.data["matches"]["vendor"]["status"], "matched")
        warning_codes = {item["code"] for item in response.data["warnings"]}
        self.assertNotIn("pdf_ocr_pending", warning_codes)
