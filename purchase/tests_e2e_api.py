from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from assets.models import AssetCategory
from catalog.models import HsnSac, Product, ProductCategory, ProductGstRate, ProductPurchaseBehavior, UnitOfMeasure
from entity.models import Entity, EntityAddress, EntityFinancialYear, EntityGstRegistration, Godown, GstRegistrationType, SubEntity
from financial.models import AccountCommercialProfile, AccountComplianceProfile, Ledger, account, accountHead, accounttype
from financial.services import create_account_with_synced_ledger
from geography.models import City, Country, District, State
from numbering.models import DocumentNumberSeries, DocumentType
from payments.models import PaymentMode, PaymentVoucherAdjustment, PaymentVoucherHeader
from posting.models import Entry, EntryStatus, InventoryMove, JournalLine, PostingBatch, TxnType
from purchase.models.gstr2b_models import Gstr2bImportBatch, Gstr2bImportRow
from purchase.models.purchase_ap import VendorAdvanceBalance, VendorBillOpenItem
from purchase.models import PurchaseLockPeriod
from purchase.models.purchase_core import PurchaseInvoiceHeader, PurchaseInvoiceLine, PurchaseTaxSummary
from purchase.services.purchase_settings_service import PurchaseSettingsService
from withholding.models import WithholdingBaseRule, WithholdingSection, WithholdingTaxType


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
            defaults={
                "entity": self.entity,
                "gstno": "27ABCDE1234F1Z5",
                "pan": "ABCDE1234F",
                "createdby": self.user,
            },
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
        cash_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=1002,
            name="Cash on Hand",
            accounthead=self.debit_head,
            createdby=self.user,
        )
        self.cash_account = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity,
                "ledger": cash_ledger,
                "accountname": "Cash on Hand",
                "createdby": self.user,
            },
            ledger_overrides={"ledger_code": 1002, "accounthead": self.debit_head, "is_party": False},
        )
        tds_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=2105,
            name="TDS Payable",
            accounthead=self.credit_head,
            createdby=self.user,
        )
        self.tds_payable_account = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity,
                "ledger": tds_ledger,
                "accountname": "TDS Payable",
                "createdby": self.user,
            },
            ledger_overrides={"ledger_code": 2105, "accounthead": self.credit_head, "is_party": False},
        )
        self.cash_payment_mode = PaymentMode.objects.create(
            paymentmode="Cash",
            paymentmodecode="CASH",
            iscash=True,
            createdby=self.user,
        )

        self.uom = UnitOfMeasure.objects.create(entity=self.entity, code="KGS", description="Kilograms")
        self.location = Godown.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            name="Main Warehouse",
            code="WH1",
            address="Warehouse Address",
            city="Mumbai",
            state="MH",
            pincode="400001",
            is_active=True,
            is_default=True,
        )
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
        self.asset_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=5002,
            name="CWIP Ledger",
            accounthead=self.debit_head,
            createdby=self.user,
        )
        self.asset_category = AssetCategory.objects.create(
            entity=self.entity,
            code="CWIP-ITC",
            name="Capital WIP",
            nature=AssetCategory.AssetNature.CAPITAL_WIP,
            cwip_ledger=self.asset_ledger,
        )
        self.asset_product = Product.objects.create(
            entity=self.entity,
            productname="Capital Asset",
            sku="AST-001",
            productdesc="Asset product",
            productcategory=self.product_category,
            base_uom=self.uom,
            is_service=False,
            is_batch_managed=False,
            purchase_behavior=ProductPurchaseBehavior.ASSET,
            default_asset_category=self.asset_category,
        )

        self.purchase_doc_type = DocumentType.objects.create(
            module="purchase",
            name="Purchase Tax Invoice",
            doc_key="PURCHASE_TAX_INVOICE",
            default_code="PINV",
            is_active=True,
        )
        self.purchase_credit_note_doc_type = DocumentType.objects.create(
            module="purchase",
            name="Purchase Credit Note",
            doc_key="PURCHASE_CREDIT_NOTE",
            default_code="PCN",
            is_active=True,
        )
        self.purchase_debit_note_doc_type = DocumentType.objects.create(
            module="purchase",
            name="Purchase Debit Note",
            doc_key="PURCHASE_DEBIT_NOTE",
            default_code="PDN",
            is_active=True,
        )
        self.payment_doc_type = DocumentType.objects.create(
            module="payments",
            name="Payment Voucher",
            doc_key="PAYMENT_VOUCHER",
            default_code="PPV",
            is_active=True,
        )
        for doc_type, code, prefix in (
            (self.purchase_doc_type, "PINV", "PI"),
            (self.purchase_credit_note_doc_type, "PCN", "PCN"),
            (self.purchase_debit_note_doc_type, "PDN", "PDN"),
            (self.payment_doc_type, "PPV", "PPV"),
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
            "purchase.views.rbac.EffectivePermissionService.entity_for_user",
            side_effect=lambda _user, entity_id: SimpleNamespace(id=int(entity_id)),
        )
        self._payment_entity_scope_patch = patch(
            "payments.views.payment_voucher.EffectivePermissionService.entity_for_user",
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
                "purchase.credit_note.view",
                "purchase.credit_note.read",
                "purchase.credit_note.list",
                "purchase.credit_note.create",
                "purchase.credit_note.update",
                "purchase.credit_note.edit",
                "purchase.credit_note.post",
                "purchase.credit_note.unpost",
                "purchase.credit_note.cancel",
                "purchase.debit_note.view",
                "purchase.debit_note.read",
                "purchase.debit_note.list",
                "purchase.debit_note.create",
                "purchase.debit_note.update",
                "purchase.debit_note.edit",
                "purchase.debit_note.post",
                "purchase.debit_note.unpost",
                "purchase.debit_note.cancel",
            },
        )
        self._payment_codes_patch = patch(
            "payments.views.payment_voucher.EffectivePermissionService.permission_codes_for_user",
            return_value={
                "voucher.payment.view",
                "voucher.payment.read",
                "voucher.payment.list",
                "voucher.payment.create",
                "voucher.payment.update",
                "voucher.payment.delete",
                "voucher.payment.confirm",
                "voucher.payment.post",
                "voucher.payment.unpost",
                "voucher.payment.cancel",
            },
        )
        self._payment_request_permission_patch = patch(
            "payments.views.payment_voucher._require_payment_permission",
            return_value=None,
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
        self._gstr2b_codes_patch = patch(
            "purchase.views.purchase_gstr2b.EffectivePermissionService.permission_codes_for_user",
            return_value={
                "purchase.statutory.view",
                "purchase.statutory.manage",
                "purchase.statutory.approve",
            },
        )
        self._invoice_request_permission_patch = patch(
            "purchase.views.purchase_invoice.require_purchase_request_permission",
            side_effect=lambda **kwargs: int(kwargs.get("doc_type") or PurchaseInvoiceHeader.DocType.TAX_INVOICE),
        )
        self._invoice_actions_request_permission_patch = patch(
            "purchase.views.purchase_invoice_actions.require_purchase_request_permission",
            side_effect=lambda **kwargs: int(kwargs.get("doc_type") or PurchaseInvoiceHeader.DocType.TAX_INVOICE),
        )
        self._invoice_actions_scope_permission_patch = patch(
            "purchase.views.purchase_invoice_actions.require_purchase_scope_permission",
            return_value=None,
        )
        self._entity_scope_patch.start()
        self._payment_entity_scope_patch.start()
        self._codes_patch.start()
        self._payment_codes_patch.start()
        self._payment_request_permission_patch.start()
        self._statutory_codes_patch.start()
        self._gstr2b_codes_patch.start()
        self._invoice_request_permission_patch.start()
        self._invoice_actions_request_permission_patch.start()
        self._invoice_actions_scope_permission_patch.start()
        self.addCleanup(self._entity_scope_patch.stop)
        self.addCleanup(self._payment_entity_scope_patch.stop)
        self.addCleanup(self._codes_patch.stop)
        self.addCleanup(self._payment_codes_patch.stop)
        self.addCleanup(self._payment_request_permission_patch.stop)
        self.addCleanup(self._statutory_codes_patch.stop)
        self.addCleanup(self._gstr2b_codes_patch.stop)
        self.addCleanup(self._invoice_request_permission_patch.stop)
        self.addCleanup(self._invoice_actions_request_permission_patch.stop)
        self.addCleanup(self._invoice_actions_scope_permission_patch.stop)

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

    def _service_line_payload(self, *, product_desc: str = "Consulting"):
        return {
            "id": None,
            "line_no": 1,
            "product": None,
            "purchase_account": self.service_purchase_account.id,
            "uom": None,
            "qty": "1.0000",
            "free_qty": "0.0000",
            "rate": "500.00",
            "product_desc": product_desc,
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

    def _asset_line_payload(self, *, qty: str = "1.0000", rate: str = "100000.00"):
        taxable = Decimal(qty) * Decimal(rate)
        igst = (taxable * Decimal("0.18")).quantize(Decimal("0.01"))
        return {
            "id": None,
            "line_no": 1,
            "product": self.asset_product.id,
            "uom": self.uom.id,
            "qty": qty,
            "free_qty": "0.0000",
            "rate": rate,
            "product_desc": "Capital Asset",
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

    def _blocked_goods_line_payload(self, *, line_no: int = 1, product_id: int | None = None, qty: str = "10.0000", rate: str = "100.00"):
        row = self._goods_line_payload(product_id=product_id, qty=qty, rate=rate)
        row["line_no"] = line_no
        row["is_itc_eligible"] = False
        row["itc_block_reason"] = "Blocked ITC"
        return row

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

    def _rcm_service_line_payload(self, *, product_desc: str = "Consulting"):
        line = self._service_line_payload(product_desc=product_desc)
        line.update(
            {
                "cgst_percent": "0.00",
                "sgst_percent": "0.00",
                "igst_percent": "0.00",
                "cgst_amount": "0.00",
                "sgst_amount": "0.00",
                "igst_amount": "0.00",
                "line_total": "500.00",
            }
        )
        return line

    def _create_invoice(
        self,
        supplier_invoice_number: str = "INV-001",
        lines: list[dict] | None = None,
        **overrides,
    ) -> dict:
        payload = self._invoice_payload(lines=lines or [self._goods_line_payload()], supplier_invoice_number=supplier_invoice_number)
        payload.update(overrides)
        response = self.client.post("/api/purchase/purchase-invoices/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        return response.json()

    def _seed_inventory_move(
        self,
        *,
        header: PurchaseInvoiceHeader,
        line: PurchaseInvoiceLine,
        txn_type: str,
        txn_id: int,
        move_type: str,
        qty: str,
        posting_day: date,
    ) -> None:
        batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=txn_type,
            txn_id=txn_id,
            voucher_no=f"{txn_type}-{txn_id}",
            revision=1,
            is_active=True,
            created_by=self.user,
        )
        entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=txn_type,
            txn_id=txn_id,
            voucher_no=f"{txn_type}-{txn_id}",
            voucher_date=posting_day,
            posting_date=posting_day,
            status=EntryStatus.POSTED,
            posting_batch=batch,
            narration="Inventory movement fixture",
            created_by=self.user,
        )
        qty_decimal = Decimal(qty)
        InventoryMove.objects.create(
            entry=entry,
            posting_batch=batch,
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=txn_type,
            txn_id=txn_id,
            detail_id=line.id,
            voucher_no=f"{txn_type}-{txn_id}",
            product=line.product,
            batch_number=getattr(line, "batch_number", "") or "",
            location=self.location,
            source_location=self.location if move_type == InventoryMove.MoveType.OUT else None,
            destination_location=self.location if move_type == InventoryMove.MoveType.IN_ else None,
            uom=self.uom,
            base_uom=self.uom,
            qty=qty_decimal,
            uom_factor=Decimal("1.00000000"),
            base_qty=qty_decimal,
            unit_cost=Decimal("100.0000"),
            ext_cost=Decimal("1000.00"),
            cost_source=InventoryMove.CostSource.PURCHASE,
            move_type=move_type,
            movement_nature=InventoryMove.MovementNature.PURCHASE if move_type == InventoryMove.MoveType.IN_ else InventoryMove.MovementNature.OTHER,
            movement_reason="fixture",
            posting_date=posting_day,
            created_by=self.user,
        )

    def test_create_goods_invoice_with_new_line_id_null(self):
        body = self._create_invoice(lines=[self._goods_line_payload()])
        self.assertIn("id", body)
        self.assertEqual(body["status"], int(PurchaseInvoiceHeader.Status.DRAFT))
        self.assertEqual(len(body["lines"]), 1)
        self.assertIsNotNone(body["lines"][0]["id"])

    def test_supplier_invoice_number_and_date_are_mandatory(self):
        payload = self._invoice_payload(lines=[self._goods_line_payload()], supplier_invoice_number="INV-MISSING-DATE")
        payload["supplier_invoice_date"] = None
        response = self.client.post("/api/purchase/purchase-invoices/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("supplier_invoice_date is required", str(response.json()))

    def test_duplicate_supplier_invoice_is_blocked_for_same_vendor_date_and_amount(self):
        self._create_invoice(supplier_invoice_number="INV-DUPLICATE")
        duplicate_payload = self._invoice_payload(lines=[self._goods_line_payload()], supplier_invoice_number="INV-DUPLICATE")

        response = self.client.post("/api/purchase/purchase-invoices/", duplicate_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Duplicate supplier invoice detected", str(response.json()))

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

    def test_create_sez_purchase_with_tax_uses_inter_igst_totals(self):
        payload = self._invoice_payload(
            lines=[self._goods_line_payload()],
            supplier_invoice_number="INV-SEZ-TAX",
        )
        payload.update(
            {
                "supply_category": int(PurchaseInvoiceHeader.SupplyCategory.SEZ),
                "tax_regime": int(PurchaseInvoiceHeader.TaxRegime.INTER),
                "is_igst": True,
            }
        )

        response = self.client.post("/api/purchase/purchase-invoices/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        body = response.json()
        self.assertEqual(body["supply_category"], int(PurchaseInvoiceHeader.SupplyCategory.SEZ))
        self.assertEqual(Decimal(str(body["total_igst"])), Decimal("180.00"))
        self.assertEqual(Decimal(str(body["grand_total"])), Decimal("1180.00"))

    def test_create_sez_purchase_without_tax_keeps_zero_gst_totals(self):
        exempt_line = self._goods_line_payload()
        exempt_line.update(
            {
                "taxability": int(PurchaseInvoiceHeader.Taxability.EXEMPT),
                "gst_rate": "0.00",
                "igst_percent": "0.00",
                "taxable_value": "1000.00",
                "igst_amount": "0.00",
                "line_total": "1000.00",
                "is_itc_eligible": False,
            }
        )
        payload = self._invoice_payload(
            lines=[exempt_line],
            supplier_invoice_number="INV-SEZ-NOTAX",
        )
        payload.update(
            {
                "supply_category": int(PurchaseInvoiceHeader.SupplyCategory.SEZ),
                "tax_regime": int(PurchaseInvoiceHeader.TaxRegime.INTER),
                "is_igst": True,
                "default_taxability": int(PurchaseInvoiceHeader.Taxability.EXEMPT),
                "is_itc_eligible": False,
            }
        )

        response = self.client.post("/api/purchase/purchase-invoices/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        body = response.json()
        self.assertEqual(body["supply_category"], int(PurchaseInvoiceHeader.SupplyCategory.SEZ))
        self.assertEqual(Decimal(str(body["total_igst"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(body["grand_total"])), Decimal("1000.00"))

    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseApService.sync_open_item_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_urd_same_state_rcm_rebuilds_cgst_sgst_tax_summary_after_post(
        self,
        mocked_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_open_item,
        mocked_sync_contract_ledger,
    ):
        created = self._create_invoice(
            supplier_invoice_number="INV-RCM-INTRA-URD",
            lines=[self._rcm_service_line_payload(product_desc="URD same-state service")],
            vendor_gstin="",
            place_of_supply_state=self.state_home.id,
            supplier_state=self.state_home.id,
            vendor_state=self.state_home.id,
            tax_regime=int(PurchaseInvoiceHeader.TaxRegime.INTRA),
            is_igst=False,
            is_reverse_charge=True,
        )
        invoice_id = created["id"]
        self.assertEqual(Decimal(str(created["total_gst"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(created["grand_total"])), Decimal("500.00"))

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())
        post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        summary = PurchaseTaxSummary.objects.get(header_id=invoice_id)
        self.assertTrue(summary.is_reverse_charge)
        self.assertEqual(summary.taxable_value, Decimal("500.00"))
        self.assertEqual(summary.cgst_amount, Decimal("45.00"))
        self.assertEqual(summary.sgst_amount, Decimal("45.00"))
        self.assertEqual(summary.igst_amount, Decimal("0.00"))
        self.assertEqual(summary.itc_eligible_tax, Decimal("90.00"))
        self.assertEqual(mocked_post_adapter.call_count, 1)
        self.assertEqual(mocked_sync_open_item.call_count, 1)
        self.assertTrue(mocked_sync_contract_ledger.called)
        self.assertEqual(mocked_sync_asset_intakes.call_count, 1)

    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseApService.sync_open_item_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_urd_interstate_gta_rcm_rebuilds_igst_tax_summary_after_post(
        self,
        mocked_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_open_item,
        mocked_sync_contract_ledger,
    ):
        created = self._create_invoice(
            supplier_invoice_number="INV-RCM-INTER-GTA",
            lines=[self._rcm_service_line_payload(product_desc="GTA freight service")],
            vendor_gstin="",
            place_of_supply_state=self.state_other.id,
            supplier_state=self.state_home.id,
            vendor_state=self.state_home.id,
            tax_regime=int(PurchaseInvoiceHeader.TaxRegime.INTER),
            is_igst=True,
            is_reverse_charge=True,
        )
        invoice_id = created["id"]
        self.assertEqual(Decimal(str(created["total_gst"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(created["grand_total"])), Decimal("500.00"))

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())
        post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        summary = PurchaseTaxSummary.objects.get(header_id=invoice_id)
        self.assertTrue(summary.is_reverse_charge)
        self.assertEqual(summary.taxable_value, Decimal("500.00"))
        self.assertEqual(summary.igst_amount, Decimal("90.00"))
        self.assertEqual(summary.cgst_amount, Decimal("0.00"))
        self.assertEqual(summary.sgst_amount, Decimal("0.00"))
        self.assertEqual(summary.itc_eligible_tax, Decimal("90.00"))
        self.assertEqual(PurchaseInvoiceLine.objects.get(header_id=invoice_id).product_desc, "GTA freight service")
        self.assertEqual(mocked_post_adapter.call_count, 1)
        self.assertEqual(mocked_sync_open_item.call_count, 1)
        self.assertTrue(mocked_sync_contract_ledger.called)
        self.assertEqual(mocked_sync_asset_intakes.call_count, 1)

    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseApService.sync_open_item_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_legal_service_rcm_uses_generic_service_reverse_charge_flow(
        self,
        mocked_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_open_item,
        mocked_sync_contract_ledger,
    ):
        created = self._create_invoice(
            supplier_invoice_number="INV-RCM-LEGAL",
            lines=[self._rcm_service_line_payload(product_desc="Legal service fees")],
            vendor_gstin="",
            is_reverse_charge=True,
        )
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())
        post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        summary = PurchaseTaxSummary.objects.get(header_id=invoice_id)
        self.assertTrue(summary.is_service)
        self.assertTrue(summary.is_reverse_charge)
        self.assertEqual(summary.igst_amount, Decimal("90.00"))
        self.assertEqual(PurchaseInvoiceLine.objects.get(header_id=invoice_id).product_desc, "Legal service fees")
        self.assertEqual(mocked_post_adapter.call_count, 1)
        self.assertEqual(mocked_sync_open_item.call_count, 1)
        self.assertTrue(mocked_sync_contract_ledger.called)
        self.assertEqual(mocked_sync_asset_intakes.call_count, 1)

    def test_reverse_charge_goods_invoice_preserves_line_gst_rate_on_create_and_detail(self):
        intra_line = self._goods_line_payload()
        intra_line.update(
            {
                "cgst_percent": "9.00",
                "sgst_percent": "9.00",
                "igst_percent": "0.00",
                "cgst_amount": "0.00",
                "sgst_amount": "0.00",
                "igst_amount": "0.00",
                "line_total": "1000.00",
            }
        )
        created = self._create_invoice(
            supplier_invoice_number="INV-RCM-GOODS-RATE",
            lines=[intra_line],
            vendor_state=self.state_home.id,
            supplier_state=self.state_home.id,
            place_of_supply_state=self.state_home.id,
            tax_regime=int(PurchaseInvoiceHeader.TaxRegime.INTRA),
            is_igst=False,
            is_reverse_charge=True,
        )
        invoice_id = created["id"]

        self.assertEqual(len(created["lines"]), 1)
        created_line = created["lines"][0]
        self.assertEqual(Decimal(str(created_line["gst_rate"])), Decimal("18.00"))
        self.assertEqual(Decimal(str(created_line["cgst_percent"])), Decimal("9.00"))
        self.assertEqual(Decimal(str(created_line["sgst_percent"])), Decimal("9.00"))
        self.assertEqual(Decimal(str(created_line["igst_percent"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(created_line["cgst_amount"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(created_line["sgst_amount"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(created_line["igst_amount"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(created_line["line_total"])), Decimal("1000.00"))

        detail_resp = self.client.get(f"/api/purchase/purchase-invoices/{invoice_id}/{self._scope_qs()}")
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK, detail_resp.json())
        self.assertEqual(len(detail_resp.json()["lines"]), 1)
        detail_line = detail_resp.json()["lines"][0]
        self.assertEqual(Decimal(str(detail_line["gst_rate"])), Decimal("18.00"))
        self.assertEqual(Decimal(str(detail_line["cgst_percent"])), Decimal("9.00"))
        self.assertEqual(Decimal(str(detail_line["sgst_percent"])), Decimal("9.00"))
        self.assertEqual(Decimal(str(detail_line["igst_percent"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(detail_line["cgst_amount"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(detail_line["sgst_amount"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(detail_line["igst_amount"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(detail_line["line_total"])), Decimal("1000.00"))

    def test_reverse_charge_preserves_explicit_line_tax_percentages_without_re_splitting(self):
        intra_line = self._goods_line_payload()
        intra_line.update(
            {
                "gst_rate": "18.00",
                "cgst_percent": "8.00",
                "sgst_percent": "10.00",
                "igst_percent": "0.00",
                "cgst_amount": "0.00",
                "sgst_amount": "0.00",
                "igst_amount": "0.00",
                "line_total": "1000.00",
            }
        )
        created = self._create_invoice(
            supplier_invoice_number="INV-RCM-PRESERVE-PCT",
            lines=[intra_line],
            vendor_state=self.state_home.id,
            supplier_state=self.state_home.id,
            place_of_supply_state=self.state_home.id,
            tax_regime=int(PurchaseInvoiceHeader.TaxRegime.INTRA),
            is_igst=False,
            is_reverse_charge=True,
        )

        created_line = created["lines"][0]
        self.assertEqual(Decimal(str(created_line["gst_rate"])), Decimal("18.00"))
        self.assertEqual(Decimal(str(created_line["cgst_percent"])), Decimal("8.00"))
        self.assertEqual(Decimal(str(created_line["sgst_percent"])), Decimal("10.00"))
        self.assertEqual(Decimal(str(created_line["igst_percent"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(created_line["cgst_amount"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(created_line["sgst_amount"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(created_line["igst_amount"])), Decimal("0.00"))

        inter_line = self._goods_line_payload()
        inter_line.update(
            {
                "gst_rate": "12.00",
                "cgst_percent": "0.00",
                "sgst_percent": "0.00",
                "igst_percent": "12.00",
                "cgst_amount": "0.00",
                "sgst_amount": "0.00",
                "igst_amount": "0.00",
                "line_total": "1000.00",
            }
        )
        inter_created = self._create_invoice(
            supplier_invoice_number="INV-RCM-PRESERVE-IGST",
            lines=[inter_line],
            vendor_state=self.state_home.id,
            supplier_state=self.state_home.id,
            place_of_supply_state=self.state_other.id,
            tax_regime=int(PurchaseInvoiceHeader.TaxRegime.INTER),
            is_igst=True,
            is_reverse_charge=True,
        )

        inter_created_line = inter_created["lines"][0]
        self.assertEqual(Decimal(str(inter_created_line["gst_rate"])), Decimal("12.00"))
        self.assertEqual(Decimal(str(inter_created_line["cgst_percent"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(inter_created_line["sgst_percent"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(inter_created_line["igst_percent"])), Decimal("12.00"))
        self.assertEqual(Decimal(str(inter_created_line["cgst_amount"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(inter_created_line["sgst_amount"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(inter_created_line["igst_amount"])), Decimal("0.00"))

    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseApService.sync_open_item_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_mixed_goods_and_service_invoice_posts_with_both_line_types(
        self,
        mocked_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_open_item,
        mocked_sync_contract_ledger,
    ):
        goods_line = self._goods_line_payload()
        service_line = self._service_line_payload()
        service_line["line_no"] = 2
        payload = self._invoice_payload(
            lines=[goods_line, service_line],
            supplier_invoice_number="INV-MIXED-GS",
        )

        create_resp = self.client.post("/api/purchase/purchase-invoices/", payload, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())
        body = create_resp.json()
        invoice_id = body["id"]
        self.assertEqual(len(body["lines"]), 2)
        self.assertEqual(Decimal(str(body["total_taxable"])), Decimal("1500.00"))
        self.assertEqual(Decimal(str(body["total_igst"])), Decimal("270.00"))
        self.assertEqual(Decimal(str(body["grand_total"])), Decimal("1770.00"))

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        post_call = mocked_post_adapter.call_args.kwargs
        posted_lines = post_call["lines"]
        self.assertEqual(len(posted_lines), 2)
        self.assertEqual(sum(1 for line in posted_lines if bool(getattr(line, "is_service", False))), 1)
        self.assertEqual(sum(1 for line in posted_lines if not bool(getattr(line, "is_service", False))), 1)
        self.assertEqual(mocked_post_adapter.call_count, 1)
        self.assertEqual(mocked_sync_asset_intakes.call_count, 1)
        self.assertEqual(mocked_sync_open_item.call_count, 1)
        self.assertTrue(mocked_sync_contract_ledger.called)

    def test_partial_itc_invoice_tracks_line_level_eligible_and_ineligible_tax_summary(self):
        eligible_line = self._goods_line_payload(qty="10.0000", rate="100.00")
        blocked_line = self._blocked_goods_line_payload(line_no=2, qty="5.0000", rate="100.00")
        payload = self._invoice_payload(
            lines=[eligible_line, blocked_line],
            supplier_invoice_number="INV-PARTIAL-ITC",
        )

        create_resp = self.client.post("/api/purchase/purchase-invoices/", payload, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.json())
        invoice_id = create_resp.json()["id"]

        header = PurchaseInvoiceHeader.objects.get(pk=invoice_id)
        self.assertTrue(header.is_itc_eligible)

        lines = list(PurchaseInvoiceLine.objects.filter(header_id=invoice_id).order_by("line_no"))
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].is_itc_eligible)
        self.assertFalse(lines[1].is_itc_eligible)
        self.assertEqual(lines[1].itc_block_reason, "Blocked ITC")

        summary = PurchaseTaxSummary.objects.get(header_id=invoice_id)
        self.assertEqual(summary.itc_eligible_tax, Decimal("180.00"))
        self.assertEqual(summary.itc_ineligible_tax, Decimal("90.00"))

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

    def test_patch_can_replace_deleted_line_with_new_line_reusing_same_line_no(self):
        created = self._create_invoice(supplier_invoice_number="INV-REPLACE-LINE")
        invoice_id = created["id"]

        replacement_line = self._goods_line_payload(qty="12.0000", rate="150.00")
        replacement_line["line_no"] = created["lines"][0]["line_no"]
        replacement_line["id"] = None
        replacement_line["product_desc"] = "Replacement goods"

        patch_resp = self.client.patch(
            f"/api/purchase/purchase-invoices/{invoice_id}/{self._scope_qs()}",
            {"lines": [replacement_line]},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.json())

        lines = list(PurchaseInvoiceLine.objects.filter(header_id=invoice_id).order_by("line_no", "id"))
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].line_no, 1)
        self.assertEqual(lines[0].product_desc, "Replacement goods")
        self.assertEqual(lines[0].qty, Decimal("12.0000"))
        self.assertEqual(lines[0].rate, Decimal("150.00"))

    def test_confirmed_purchase_invoice_can_be_edited_when_policy_allows(self):
        created = self._create_invoice(supplier_invoice_number="INV-CONF-EDIT")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        updated_line = self._goods_line_payload(qty="12.0000", rate="100.00")
        updated_line["id"] = created["lines"][0]["id"]
        updated_line["line_no"] = created["lines"][0]["line_no"]

        patch_resp = self.client.patch(
            f"/api/purchase/purchase-invoices/{invoice_id}/{self._scope_qs()}",
            {"lines": [updated_line]},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.json())
        body = patch_resp.json()
        self.assertEqual(body["status"], int(PurchaseInvoiceHeader.Status.CONFIRMED))
        self.assertEqual(Decimal(str(body["total_taxable"])), Decimal("1200.00"))
        self.assertEqual(Decimal(str(body["grand_total"])), Decimal("1416.00"))

    def test_confirmed_purchase_invoice_edit_is_blocked_when_policy_disables_it(self):
        PurchaseSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"policy_controls": {"allow_edit_confirmed": "off"}},
        )

        created = self._create_invoice(supplier_invoice_number="INV-CONF-EDIT-OFF")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        updated_line = self._goods_line_payload(qty="12.0000", rate="100.00")
        updated_line["id"] = created["lines"][0]["id"]
        updated_line["line_no"] = created["lines"][0]["line_no"]

        patch_resp = self.client.patch(
            f"/api/purchase/purchase-invoices/{invoice_id}/{self._scope_qs()}",
            {"lines": [updated_line]},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Confirmed purchase invoice editing is disabled by purchase policy.", str(patch_resp.json()))

    def test_purchase_invoice_create_is_blocked_when_no_lines_are_provided(self):
        PurchaseSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"policy_controls": {"require_lines_on_confirm": "hard"}},
        )

        payload = self._invoice_payload(lines=[], supplier_invoice_number="INV-NO-LINES")
        create_resp = self.client.post("/api/purchase/purchase-invoices/", payload, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_400_BAD_REQUEST, create_resp.json())
        self.assertIn("At least one line is required.", str(create_resp.json()))

    def test_purchase_invoice_create_rejects_mixed_taxability_when_setting_disabled(self):
        PurchaseSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"allow_mixed_taxability_in_one_bill": False},
        )

        exempt_line = self._goods_line_payload(qty="1.0000", rate="100.00")
        exempt_line.update(
            {
                "id": None,
                "line_no": 2,
                "taxability": int(PurchaseInvoiceHeader.Taxability.EXEMPT),
                "gst_rate": "0.00",
                "cgst_percent": "0.00",
                "sgst_percent": "0.00",
                "igst_percent": "0.00",
                "cgst_amount": "0.00",
                "sgst_amount": "0.00",
                "igst_amount": "0.00",
                "line_total": "100.00",
                "is_itc_eligible": False,
            }
        )
        payload = self._invoice_payload(
            lines=[self._goods_line_payload(), exempt_line],
            supplier_invoice_number="INV-MIXED-TAXABILITY",
        )

        response = self.client.post("/api/purchase/purchase-invoices/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.json())
        self.assertIn("mixed taxability in one bill is disabled for this entity", str(response.json()).lower())

    def test_purchase_invoice_create_with_mixed_taxability_off_allows_multi_line_same_taxability_documents(self):
        PurchaseSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"allow_mixed_taxability_in_one_bill": False},
        )

        scenarios = [
            {
                "name": "taxable",
                "default_taxability": int(PurchaseInvoiceHeader.Taxability.TAXABLE),
                "header_itc": True,
                "line_taxability": int(PurchaseInvoiceHeader.Taxability.TAXABLE),
                "line_2_taxability": int(PurchaseInvoiceHeader.Taxability.TAXABLE),
                "line_1": self._goods_line_payload(qty="10.0000", rate="100.00"),
                "line_2": {
                    **self._goods_line_payload(qty="5.0000", rate="50.00"),
                    "line_no": 2,
                },
                "expected_taxable": Decimal("1250.00"),
                "expected_igst": Decimal("225.00"),
                "expected_grand": Decimal("1475.00"),
                "expected_summary_taxability": int(PurchaseInvoiceHeader.Taxability.TAXABLE),
            },
            {
                "name": "exempt",
                "default_taxability": int(PurchaseInvoiceHeader.Taxability.EXEMPT),
                "header_itc": False,
                "line_taxability": int(PurchaseInvoiceHeader.Taxability.EXEMPT),
                "line_2_taxability": int(PurchaseInvoiceHeader.Taxability.EXEMPT),
                "line_1": {
                    **self._goods_line_payload(qty="10.0000", rate="100.00"),
                    "taxability": int(PurchaseInvoiceHeader.Taxability.EXEMPT),
                    "gst_rate": "0.00",
                    "cgst_percent": "0.00",
                    "sgst_percent": "0.00",
                    "igst_percent": "0.00",
                    "cgst_amount": "0.00",
                    "sgst_amount": "0.00",
                    "igst_amount": "0.00",
                    "line_total": "1000.00",
                    "is_itc_eligible": False,
                },
                "line_2": {
                    **self._goods_line_payload(qty="5.0000", rate="50.00"),
                    "line_no": 2,
                    "taxability": int(PurchaseInvoiceHeader.Taxability.EXEMPT),
                    "gst_rate": "0.00",
                    "cgst_percent": "0.00",
                    "sgst_percent": "0.00",
                    "igst_percent": "0.00",
                    "cgst_amount": "0.00",
                    "sgst_amount": "0.00",
                    "igst_amount": "0.00",
                    "line_total": "250.00",
                    "is_itc_eligible": False,
                },
                "expected_taxable": Decimal("1250.00"),
                "expected_igst": Decimal("0.00"),
                "expected_grand": Decimal("1250.00"),
                "expected_summary_taxability": int(PurchaseInvoiceHeader.Taxability.EXEMPT),
            },
            {
                "name": "nil-rated",
                "default_taxability": int(PurchaseInvoiceHeader.Taxability.NIL_RATED),
                "header_itc": False,
                "line_taxability": int(PurchaseInvoiceHeader.Taxability.NIL_RATED),
                "line_2_taxability": int(PurchaseInvoiceHeader.Taxability.NIL_RATED),
                "line_1": {
                    **self._goods_line_payload(qty="10.0000", rate="100.00"),
                    "taxability": int(PurchaseInvoiceHeader.Taxability.NIL_RATED),
                    "gst_rate": "0.00",
                    "cgst_percent": "0.00",
                    "sgst_percent": "0.00",
                    "igst_percent": "0.00",
                    "cgst_amount": "0.00",
                    "sgst_amount": "0.00",
                    "igst_amount": "0.00",
                    "line_total": "1000.00",
                    "is_itc_eligible": False,
                },
                "line_2": {
                    **self._goods_line_payload(qty="5.0000", rate="50.00"),
                    "line_no": 2,
                    "taxability": int(PurchaseInvoiceHeader.Taxability.NIL_RATED),
                    "gst_rate": "0.00",
                    "cgst_percent": "0.00",
                    "sgst_percent": "0.00",
                    "igst_percent": "0.00",
                    "cgst_amount": "0.00",
                    "sgst_amount": "0.00",
                    "igst_amount": "0.00",
                    "line_total": "250.00",
                    "is_itc_eligible": False,
                },
                "expected_taxable": Decimal("1250.00"),
                "expected_igst": Decimal("0.00"),
                "expected_grand": Decimal("1250.00"),
                "expected_summary_taxability": int(PurchaseInvoiceHeader.Taxability.NIL_RATED),
            },
            {
                "name": "non-gst",
                "default_taxability": int(PurchaseInvoiceHeader.Taxability.NON_GST),
                "header_itc": False,
                "line_taxability": int(PurchaseInvoiceHeader.Taxability.NON_GST),
                "line_2_taxability": int(PurchaseInvoiceHeader.Taxability.NON_GST),
                "line_1": {
                    **self._goods_line_payload(qty="10.0000", rate="100.00"),
                    "taxability": int(PurchaseInvoiceHeader.Taxability.NON_GST),
                    "gst_rate": "0.00",
                    "cgst_percent": "0.00",
                    "sgst_percent": "0.00",
                    "igst_percent": "0.00",
                    "cgst_amount": "0.00",
                    "sgst_amount": "0.00",
                    "igst_amount": "0.00",
                    "line_total": "1000.00",
                    "is_itc_eligible": False,
                },
                "line_2": {
                    **self._goods_line_payload(qty="5.0000", rate="50.00"),
                    "line_no": 2,
                    "taxability": int(PurchaseInvoiceHeader.Taxability.NON_GST),
                    "gst_rate": "0.00",
                    "cgst_percent": "0.00",
                    "sgst_percent": "0.00",
                    "igst_percent": "0.00",
                    "cgst_amount": "0.00",
                    "sgst_amount": "0.00",
                    "igst_amount": "0.00",
                    "line_total": "250.00",
                    "is_itc_eligible": False,
                },
                "expected_taxable": Decimal("1250.00"),
                "expected_igst": Decimal("0.00"),
                "expected_grand": Decimal("1250.00"),
                "expected_summary_taxability": int(PurchaseInvoiceHeader.Taxability.NON_GST),
            },
        ]

        for scenario in scenarios:
            with self.subTest(scenario=scenario["name"]):
                payload = self._invoice_payload(
                    lines=[scenario["line_1"], scenario["line_2"]],
                    supplier_invoice_number=f"INV-MIXED-OFF-{scenario['name'].upper()}",
                )
                payload["default_taxability"] = scenario["default_taxability"]
                payload["is_itc_eligible"] = scenario["header_itc"]

                response = self.client.post("/api/purchase/purchase-invoices/", payload, format="json")

                self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
                body = response.json()
                self.assertEqual(Decimal(str(body["total_taxable"])), scenario["expected_taxable"])
                self.assertEqual(Decimal(str(body["total_igst"])), scenario["expected_igst"])
                self.assertEqual(Decimal(str(body["grand_total"])), scenario["expected_grand"])

                header = PurchaseInvoiceHeader.objects.get(pk=body["id"])
                self.assertEqual(int(header.default_taxability), scenario["expected_summary_taxability"])
                self.assertEqual(PurchaseInvoiceLine.objects.filter(header=header).count(), 2)

                summary_rows = list(PurchaseTaxSummary.objects.filter(header=header))
                self.assertEqual(len(summary_rows), 1)
                self.assertEqual(int(summary_rows[0].taxability), scenario["expected_summary_taxability"])
                self.assertEqual(summary_rows[0].taxable_value, scenario["expected_taxable"])
                self.assertEqual(summary_rows[0].cgst_amount, Decimal("0.00"))
                self.assertEqual(summary_rows[0].sgst_amount, Decimal("0.00"))
                self.assertEqual(summary_rows[0].igst_amount, scenario["expected_igst"])
                self.assertEqual(summary_rows[0].cess_amount, Decimal("0.00"))

    def test_purchase_invoice_create_rejects_line_amount_mismatch_when_policy_is_hard(self):
        PurchaseSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"policy_controls": {"line_amount_mismatch": "hard"}},
        )

        mismatched_line = self._goods_line_payload()
        mismatched_line["taxable_value"] = "999.00"
        payload = self._invoice_payload(lines=[mismatched_line], supplier_invoice_number="INV-MISMATCH-HARD")

        response = self.client.post("/api/purchase/purchase-invoices/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.json())
        self.assertIn("Line 1: sent 999.00 but expected 1000.00", str(response.json()))

    def test_purchase_invoice_confirm_is_blocked_when_lock_policy_is_hard(self):
        PurchaseSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"policy_controls": {"confirm_lock_check": "hard"}},
        )

        created = self._create_invoice(supplier_invoice_number="INV-CONFIRM-LOCKED")
        invoice_id = created["id"]
        PurchaseLockPeriod.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            lock_date=date(2026, 4, 30),
            reason="April closed",
        )

        response = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.json())
        self.assertIn("Purchase period locked.", str(response.json()))

    def test_purchase_invoice_unpost_is_blocked_when_policy_disables_it(self):
        PurchaseSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"policy_controls": {"allow_unpost_posted": "off"}},
        )

        created = self._create_invoice(supplier_invoice_number="INV-UNPOST-OFF")
        invoice_id = created["id"]
        PurchaseInvoiceHeader.objects.filter(pk=invoice_id).update(status=PurchaseInvoiceHeader.Status.POSTED)

        unpost_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/unpost/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(unpost_resp.status_code, status.HTTP_400_BAD_REQUEST, unpost_resp.json())
        self.assertIn("Unpost after posting is disabled by purchase policy.", str(unpost_resp.json()))

    def test_historical_vendor_snapshot_remains_stable_after_vendor_master_change(self):
        created = self._create_invoice(supplier_invoice_number="INV-SNAPSHOT")
        invoice_id = created["id"]

        compliance = AccountComplianceProfile.objects.get(account=self.vendor)
        compliance.gstno = "27ZZZZZ9999Z1Z5"
        compliance.save(update_fields=["gstno"])

        detail_resp = self.client.get(f"/api/purchase/purchase-invoices/{invoice_id}/{self._scope_qs()}")
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK, detail_resp.json())
        self.assertEqual(detail_resp.json()["vendor_gstin"], "27ABCDE1234F1Z5")

    def test_historical_line_tax_snapshot_remains_stable_after_product_gst_master_change(self):
        hsn = HsnSac.objects.create(
            entity=self.entity,
            code="1001",
            description="Goods HSN",
            is_service=False,
            default_sgst=Decimal("9.00"),
            default_cgst=Decimal("9.00"),
            default_igst=Decimal("18.00"),
        )
        gst_row = ProductGstRate.objects.create(
            product=self.goods_product,
            hsn=hsn,
            gst_type="regular",
            sgst=Decimal("9.00"),
            cgst=Decimal("9.00"),
            igst=Decimal("18.00"),
            valid_from=date(2026, 4, 1),
            isdefault=True,
        )

        created = self._create_invoice(
            supplier_invoice_number="INV-TAX-SNAPSHOT",
            lines=[self._goods_line_payload(product_id=self.goods_product.id)],
        )
        invoice_id = created["id"]

        gst_row.sgst = Decimal("14.00")
        gst_row.cgst = Decimal("14.00")
        gst_row.igst = Decimal("28.00")
        gst_row.save()

        detail_resp = self.client.get(f"/api/purchase/purchase-invoices/{invoice_id}/{self._scope_qs()}")
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK, detail_resp.json())
        self.assertEqual(len(detail_resp.json()["lines"]), 1)
        line = detail_resp.json()["lines"][0]
        self.assertEqual(Decimal(str(line["gst_rate"])), Decimal("18.00"))
        self.assertEqual(Decimal(str(line["igst_percent"])), Decimal("18.00"))
        self.assertEqual(Decimal(str(line["igst_amount"])), Decimal("180.00"))
        self.assertEqual(Decimal(str(line["line_total"])), Decimal("1180.00"))

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

    def test_create_credit_note_action_from_invoice(self):
        created = self._create_invoice(supplier_invoice_number="INV-CN-ACTION")
        invoice_id = created["id"]

        response = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/create-credit-note/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        body = response.json()["data"]
        self.assertEqual(body["doc_type"], int(PurchaseInvoiceHeader.DocType.CREDIT_NOTE))
        self.assertEqual(body["ref_document"], invoice_id)
        self.assertEqual(body["note_reason"], PurchaseInvoiceHeader.NoteReason.QUANTITY_RETURN)
        self.assertTrue(body["affects_inventory"])

    def test_create_debit_note_action_from_invoice(self):
        created = self._create_invoice(supplier_invoice_number="INV-DN-ACTION")
        invoice_id = created["id"]

        response = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/create-debit-note/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        body = response.json()["data"]
        self.assertEqual(body["doc_type"], int(PurchaseInvoiceHeader.DocType.DEBIT_NOTE))
        self.assertEqual(body["ref_document"], invoice_id)
        self.assertEqual(body["note_reason"], PurchaseInvoiceHeader.NoteReason.QUANTITY_RETURN)
        self.assertTrue(body["affects_inventory"])

    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseApService.sync_open_item_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_post_confirmed_invoice_marks_posted_and_calls_adapter(
        self,
        mocked_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_open_item,
        mocked_sync_contract_ledger,
    ):
        created = self._create_invoice(supplier_invoice_number="INV-POST")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())
        self.assertEqual(post_resp.json()["data"]["status"], int(PurchaseInvoiceHeader.Status.POSTED))
        header = PurchaseInvoiceHeader.objects.get(pk=invoice_id)
        self.assertIsNotNone(header.posted_at)
        mocked_post_adapter.assert_called_once()
        mocked_sync_asset_intakes.assert_called_once()
        mocked_sync_open_item.assert_called_once()
        mocked_sync_contract_ledger.assert_called()

    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseApService.sync_open_item_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_repeated_post_call_is_idempotent_for_posted_purchase_invoice(
        self,
        mocked_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_open_item,
        mocked_sync_contract_ledger,
    ):
        created = self._create_invoice(supplier_invoice_number="INV-POST-IDEMPOTENT")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        first_post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(first_post_resp.status_code, status.HTTP_200_OK, first_post_resp.json())
        self.assertEqual(first_post_resp.json()["data"]["status"], int(PurchaseInvoiceHeader.Status.POSTED))

        header = PurchaseInvoiceHeader.objects.get(pk=invoice_id)
        first_posted_at = header.posted_at
        self.assertIsNotNone(first_posted_at)

        second_post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(second_post_resp.status_code, status.HTTP_200_OK, second_post_resp.json())
        self.assertEqual(second_post_resp.json()["data"]["status"], int(PurchaseInvoiceHeader.Status.POSTED))

        header.refresh_from_db()
        self.assertEqual(header.posted_at, first_posted_at)
        mocked_post_adapter.assert_called_once()
        mocked_sync_asset_intakes.assert_called_once()
        mocked_sync_open_item.assert_called_once()
        mocked_sync_contract_ledger.assert_called()

    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PostingService.post")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.revert_asset_intakes_for_unpost")
    @patch("purchase.services.purchase_invoice_actions.GstTdsService._scope_key_for_header", return_value=("scope",))
    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseApService.sync_open_item_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_unpost_posted_invoice_marks_confirmed_and_updates_entry(
        self,
        mocked_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_open_item,
        mocked_post_sync_contract_ledger,
        mocked_scope_key,
        mocked_posting_service_post,
        mocked_revert_asset_intakes,
        mocked_unpost_sync_contract_ledger,
    ):
        created = self._create_invoice(supplier_invoice_number="INV-UNPOST")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        header = PurchaseInvoiceHeader.objects.get(pk=invoice_id)
        batch = PostingBatch.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=header.id,
            voucher_no=header.purchase_number,
            revision=1,
            is_active=True,
            created_by=self.user,
        )
        entry = Entry.objects.create(
            entity=self.entity,
            entityfin=self.entityfin,
            subentity=self.subentity,
            txn_type=TxnType.PURCHASE,
            txn_id=header.id,
            voucher_no=header.purchase_number,
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
            txn_type=TxnType.PURCHASE,
            txn_id=header.id,
            voucher_no=header.purchase_number,
            accounthead=self.debit_head,
            drcr=True,
            amount=Decimal("1180.00"),
            description="Purchase debit",
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
            txn_type=TxnType.PURCHASE,
            txn_id=header.id,
            voucher_no=header.purchase_number,
            accounthead=self.credit_head,
            drcr=False,
            amount=Decimal("1180.00"),
            description="Vendor credit",
            posting_date=header.posting_date or header.bill_date,
            posted_at=timezone.now(),
            created_by=self.user,
        )

        unpost_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/unpost/{self._scope_qs()}",
            {"reason": "Correction"},
            format="json",
        )
        self.assertEqual(unpost_resp.status_code, status.HTTP_200_OK, unpost_resp.json())
        self.assertEqual(unpost_resp.json()["data"]["status"], int(PurchaseInvoiceHeader.Status.CONFIRMED))
        header.refresh_from_db()
        self.assertIsNone(header.posted_at)
        self.assertIsNone(header.posted_by_id)
        mocked_posting_service_post.assert_called_once()
        mocked_revert_asset_intakes.assert_called_once()
        entry.refresh_from_db()
        self.assertEqual(entry.status, EntryStatus.REVERSED)
        self.assertEqual(entry.narration, "Reversed: Correction")
        self.assertTrue(mocked_unpost_sync_contract_ledger.called)
        self.assertTrue(mocked_scope_key.called)

    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseApService.sync_open_item_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_cancel_posted_invoice_requires_credit_note_flow(
        self,
        mocked_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_open_item,
        mocked_sync_contract_ledger,
    ):
        created = self._create_invoice(supplier_invoice_number="INV-CANCEL-POSTED")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        cancel_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/cancel/{self._scope_qs()}",
            {"reason": "Should be blocked"},
            format="json",
        )
        self.assertEqual(cancel_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Create a Credit Note instead.", str(cancel_resp.json()))

    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseApService.sync_open_item_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_cancel_locked_posted_invoice_creates_current_period_reversal_credit_note(
        self,
        mocked_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_open_item,
        mocked_sync_contract_ledger,
    ):
        created = self._create_invoice(supplier_invoice_number="INV-CANCEL-LOCKED")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        PurchaseLockPeriod.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            lock_date=date(2026, 4, 30),
            reason="April GST filed",
        )

        cancel_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/cancel/{self._scope_qs()}",
            {"reason": "Filed period reversal"},
            format="json",
        )
        self.assertEqual(cancel_resp.status_code, status.HTTP_200_OK, cancel_resp.json())
        body = cancel_resp.json()["data"]
        self.assertEqual(body["doc_type"], int(PurchaseInvoiceHeader.DocType.CREDIT_NOTE))
        self.assertEqual(body["status"], int(PurchaseInvoiceHeader.Status.POSTED))
        self.assertEqual(body["ref_document"], invoice_id)
        self.assertEqual(body["note_reason"], PurchaseInvoiceHeader.NoteReason.OTHER)
        self.assertFalse(body["affects_inventory"])
        self.assertEqual(body["bill_date"], timezone.localdate().strftime("%d-%m-%Y"))

        original = PurchaseInvoiceHeader.objects.get(pk=invoice_id)
        self.assertEqual(original.status, PurchaseInvoiceHeader.Status.POSTED)
        self.assertEqual(len(original.match_notes.get("correction_history", [])), 1)

        correction = PurchaseInvoiceHeader.objects.get(pk=body["id"])
        self.assertEqual(correction.match_notes["correction_origin"]["original_invoice_id"], invoice_id)
        self.assertEqual(mocked_post_adapter.call_count, 2)
        self.assertEqual(mocked_sync_asset_intakes.call_count, 2)
        self.assertEqual(mocked_sync_open_item.call_count, 2)
        self.assertTrue(mocked_sync_contract_ledger.called)

    def test_create_credit_note_for_locked_period_invoice_uses_current_open_period_date(self):
        created = self._create_invoice(supplier_invoice_number="INV-FILED-NOTE")
        invoice_id = created["id"]

        PurchaseLockPeriod.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            lock_date=date(2026, 4, 30),
            reason="April GST filed",
        )

        response = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/create-credit-note/{self._scope_qs()}",
            {"reason": "Filed period correction"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        body = response.json()["data"]
        expected_bill_date = timezone.localdate().strftime("%d-%m-%Y")
        self.assertEqual(body["bill_date"], expected_bill_date)
        self.assertEqual(body["posting_date"], expected_bill_date)
        self.assertEqual(body["ref_document"], invoice_id)

    def test_posted_purchase_invoice_cannot_be_edited(self):
        created = self._create_invoice(supplier_invoice_number="INV-EDIT-BLOCK")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        with patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header"), \
             patch("purchase.services.purchase_invoice_actions.PurchaseApService.sync_open_item_for_header"), \
             patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header"), \
             patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice"):
            post_resp = self.client.post(
                f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
                {},
                format="json",
            )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        patch_resp = self.client.patch(
            f"/api/purchase/purchase-invoices/{invoice_id}/{self._scope_qs()}",
            {"vendor_name": "Should Not Update"},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Posted purchase invoice cannot be edited", str(patch_resp.json()))

    def test_edit_locked_period_purchase_is_blocked(self):
        created = self._create_invoice(
            supplier_invoice_number="INV-LOCK-EDIT",
            bill_date="2026-04-10",
            posting_date="2026-04-10",
        )
        invoice_id = created["id"]

        PurchaseLockPeriod.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            lock_date=date(2026, 4, 30),
            reason="April period locked",
        )

        patch_resp = self.client.patch(
            f"/api/purchase/purchase-invoices/{invoice_id}/{self._scope_qs()}",
            {"vendor_name": "Should Not Update"},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Purchase period locked", str(patch_resp.json()))

    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseApService.sync_open_item_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_unpost_locked_posted_invoice_is_blocked(
        self,
        mocked_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_open_item,
        mocked_sync_contract_ledger,
    ):
        created = self._create_invoice(supplier_invoice_number="INV-UNPOST-LOCKED")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        PurchaseLockPeriod.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            lock_date=date(2026, 4, 30),
            reason="April period locked",
        )

        unpost_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/unpost/{self._scope_qs()}",
            {"reason": "Should require amendment"},
            format="json",
        )
        self.assertEqual(unpost_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cannot be unposted", str(unpost_resp.json()))

    def test_create_credit_note_action_accepts_value_only_reason(self):
        created = self._create_invoice(supplier_invoice_number="INV-CN-PRICE")
        invoice_id = created["id"]

        response = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/create-credit-note/{self._scope_qs()}",
            {
                "note_reason": PurchaseInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "reason": "Value-only adjustment",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        body = response.json()["data"]
        self.assertEqual(body["note_reason"], PurchaseInvoiceHeader.NoteReason.PRICE_DIFFERENCE)
        self.assertFalse(body["affects_inventory"])

    def test_create_credit_note_action_blocks_duplicate_active_note_without_override(self):
        created = self._create_invoice(supplier_invoice_number="INV-CN-DUP")
        invoice_id = created["id"]

        first = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/create-credit-note/{self._scope_qs()}",
            {"reason": "First correction"},
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.json())

        second = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/create-credit-note/{self._scope_qs()}",
            {"reason": "Second correction"},
            format="json",
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST, second.json())
        body = second.json()
        self.assertIn("already exists", str(body.get("detail", "")))
        self.assertEqual(body["duplicate_note_guard"]["code"], "purchase_duplicate_note_exists")
        self.assertEqual(int(body["duplicate_note_guard"]["existing_note_id"]), int(first.json()["data"]["id"]))

    def test_create_credit_note_action_allows_duplicate_with_explicit_override(self):
        created = self._create_invoice(supplier_invoice_number="INV-CN-DUP-OVR")
        invoice_id = created["id"]

        first = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/create-credit-note/{self._scope_qs()}",
            {
                "reason": "First correction",
                "note_reason": PurchaseInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
            },
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.json())

        second = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/create-credit-note/{self._scope_qs()}",
            {
                "reason": "Second correction",
                "note_reason": PurchaseInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "allow_duplicate": True,
            },
            format="json",
        )
        self.assertEqual(second.status_code, status.HTTP_201_CREATED, second.json())
        self.assertNotEqual(second.json()["data"]["id"], first.json()["data"]["id"])

    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseApService.sync_open_item_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_reverse_charge_credit_note_action_preserves_rcm_context_for_unwind(
        self,
        mocked_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_open_item,
        mocked_sync_contract_ledger,
    ):
        rcm_service_line = self._service_line_payload()
        rcm_service_line.update(
            {
                "igst_amount": "0.00",
                "line_total": "500.00",
            }
        )
        created = self._create_invoice(
            supplier_invoice_number="INV-RCM-CN",
            lines=[rcm_service_line],
            is_reverse_charge=True,
        )
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_original_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_original_resp.status_code, status.HTTP_200_OK, post_original_resp.json())

        create_note_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/create-credit-note/{self._scope_qs()}",
            {
                "note_reason": PurchaseInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "reason": "RCM value unwind",
            },
            format="json",
        )
        self.assertEqual(create_note_resp.status_code, status.HTTP_201_CREATED, create_note_resp.json())
        note_body = create_note_resp.json()["data"]
        note_id = note_body["id"]
        self.assertEqual(note_body["doc_type"], int(PurchaseInvoiceHeader.DocType.CREDIT_NOTE))
        self.assertEqual(note_body["ref_document"], invoice_id)
        self.assertTrue(note_body["is_reverse_charge"])
        self.assertEqual(note_body["note_reason"], PurchaseInvoiceHeader.NoteReason.PRICE_DIFFERENCE)
        self.assertFalse(note_body["affects_inventory"])

        confirm_note_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{note_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_note_resp.status_code, status.HTTP_200_OK, confirm_note_resp.json())

        post_note_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{note_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_note_resp.status_code, status.HTTP_200_OK, post_note_resp.json())

        correction = PurchaseInvoiceHeader.objects.get(pk=note_id)
        self.assertEqual(correction.ref_document_id, invoice_id)
        self.assertTrue(correction.is_reverse_charge)
        self.assertEqual(correction.note_reason, PurchaseInvoiceHeader.NoteReason.PRICE_DIFFERENCE)

        note_post_call = mocked_post_adapter.call_args_list[-1].kwargs
        self.assertEqual(note_post_call["header"].id, note_id)
        self.assertEqual(int(note_post_call["header"].doc_type), int(PurchaseInvoiceHeader.DocType.CREDIT_NOTE))
        self.assertTrue(note_post_call["header"].is_reverse_charge)
        self.assertEqual(mocked_post_adapter.call_count, 2)
        self.assertEqual(mocked_sync_asset_intakes.call_count, 2)
        self.assertEqual(mocked_sync_open_item.call_count, 2)
        self.assertTrue(mocked_sync_contract_ledger.called)

    def test_price_difference_note_does_not_consume_quantity_return_capacity(self):
        created = self._create_invoice(supplier_invoice_number="INV-CN-LIFECYCLE")
        invoice_id = created["id"]

        value_note_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/create-credit-note/{self._scope_qs()}",
            {
                "note_reason": PurchaseInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "reason": "Value-only adjustment",
            },
            format="json",
        )
        self.assertEqual(value_note_resp.status_code, status.HTTP_201_CREATED, value_note_resp.json())
        self.assertFalse(value_note_resp.json()["data"]["affects_inventory"])

        qty_note_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/create-credit-note/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(qty_note_resp.status_code, status.HTTP_400_BAD_REQUEST, qty_note_resp.json())
        self.assertIn("duplicate_note_guard", qty_note_resp.json())

    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseApService.sync_open_item_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_quantity_return_before_stock_consumption_is_allowed_and_keeps_source_location(
        self,
        mocked_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_open_item,
        mocked_sync_contract_ledger,
    ):
        created = self._create_invoice(
            supplier_invoice_number="INV-RET-BEFORE",
            location=self.location.id,
        )
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        original = PurchaseInvoiceHeader.objects.get(pk=invoice_id)
        original_line = original.lines.get(line_no=1)
        self._seed_inventory_move(
            header=original,
            line=original_line,
            txn_type=TxnType.PURCHASE,
            txn_id=invoice_id,
            move_type=InventoryMove.MoveType.IN_,
            qty="10.0000",
            posting_day=date(2026, 4, 10),
        )

        create_note_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/create-credit-note/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(create_note_resp.status_code, status.HTTP_201_CREATED, create_note_resp.json())
        note_id = create_note_resp.json()["data"]["id"]
        correction = PurchaseInvoiceHeader.objects.get(pk=note_id)
        self.assertEqual(correction.location_id, self.location.id)
        self.assertEqual(correction.ref_document_id, invoice_id)
        self.assertTrue(correction.affects_inventory)
        self.assertEqual(mocked_post_adapter.call_count, 1)
        self.assertEqual(mocked_sync_asset_intakes.call_count, 1)
        self.assertEqual(mocked_sync_open_item.call_count, 1)
        self.assertTrue(mocked_sync_contract_ledger.called)

    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseApService.sync_open_item_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_quantity_return_after_stock_consumption_is_blocked_with_guidance(
        self,
        mocked_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_open_item,
        mocked_sync_contract_ledger,
    ):
        created = self._create_invoice(
            supplier_invoice_number="INV-RET-AFTER",
            location=self.location.id,
        )
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        original = PurchaseInvoiceHeader.objects.get(pk=invoice_id)
        original_line = original.lines.get(line_no=1)
        self._seed_inventory_move(
            header=original,
            line=original_line,
            txn_type=TxnType.PURCHASE,
            txn_id=invoice_id,
            move_type=InventoryMove.MoveType.IN_,
            qty="10.0000",
            posting_day=date(2026, 4, 10),
        )
        self._seed_inventory_move(
            header=original,
            line=original_line,
            txn_type=TxnType.INVENTORY_ADJUSTMENT,
            txn_id=991,
            move_type=InventoryMove.MoveType.OUT,
            qty="10.0000",
            posting_day=date(2026, 4, 12),
        )

        create_note_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/create-credit-note/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(create_note_resp.status_code, status.HTTP_400_BAD_REQUEST, create_note_resp.json())
        self.assertIn("no longer safely returnable", str(create_note_resp.json()).lower())
        self.assertIn("value-only note or inventory adjustment flow", str(create_note_resp.json()).lower())
        self.assertEqual(mocked_post_adapter.call_count, 1)
        self.assertEqual(mocked_sync_asset_intakes.call_count, 1)
        self.assertEqual(mocked_sync_open_item.call_count, 1)
        self.assertTrue(mocked_sync_contract_ledger.called)

    def test_second_quantity_credit_note_action_is_blocked_after_full_qty_consumption(self):
        created = self._create_invoice(supplier_invoice_number="INV-CN-QTY-CAP")
        invoice_id = created["id"]

        first_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/create-credit-note/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(first_resp.status_code, status.HTTP_201_CREATED, first_resp.json())

        second_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/create-credit-note/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(second_resp.status_code, status.HTTP_400_BAD_REQUEST, second_resp.json())
        self.assertIn("duplicate_note_guard", second_resp.json())

    def test_unpost_requires_posted_purchase_invoice(self):
        created = self._create_invoice(supplier_invoice_number="INV-UNPOST-BLOCK")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        unpost_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/unpost/{self._scope_qs()}",
            {"reason": "Not posted yet"},
            format="json",
        )
        self.assertEqual(unpost_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Only posted purchase documents can be unposted.", str(unpost_resp.json()))

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

    def test_itc_lifecycle_covers_block_unblock_match_claim_reverse_and_rcm_gate(self):
        created = self._create_invoice(supplier_invoice_number="INV-ITC-LIFECYCLE")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        block_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/itc/block/{self._scope_qs()}",
            {"reason": "Blocked pending review"},
            format="json",
        )
        self.assertEqual(block_resp.status_code, status.HTTP_200_OK, block_resp.json())
        self.assertEqual(block_resp.json()["data"]["itc_claim_status"], int(PurchaseInvoiceHeader.ItcClaimStatus.BLOCKED))
        self.assertFalse(block_resp.json()["data"]["is_itc_eligible"])

        unblock_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/itc/unblock/{self._scope_qs()}",
            {"reason": "Review closed"},
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
        self.assertEqual(claim_resp.json()["data"]["itc_claim_period"], claim_period)

        reverse_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/itc/reverse/{self._scope_qs()}",
            {"reason": "Current period reversal"},
            format="json",
        )
        self.assertEqual(reverse_resp.status_code, status.HTTP_200_OK, reverse_resp.json())
        self.assertEqual(reverse_resp.json()["data"]["itc_claim_status"], int(PurchaseInvoiceHeader.ItcClaimStatus.REVERSED))
        self.assertEqual(reverse_resp.json()["data"]["itc_block_reason"], "Current period reversal")

        reversed_header = PurchaseInvoiceHeader.objects.get(pk=invoice_id)
        self.assertEqual(int(reversed_header.itc_claim_status), int(PurchaseInvoiceHeader.ItcClaimStatus.REVERSED))
        self.assertEqual(reversed_header.itc_block_reason, "Current period reversal")

        rcm_service_line = self._service_line_payload()
        rcm_service_line.update(
            {
                "igst_amount": "0.00",
                "line_total": "500.00",
            }
        )
        rcm_created = self._create_invoice(
            supplier_invoice_number="INV-RCM-ITC-GATE",
            lines=[rcm_service_line],
            is_reverse_charge=True,
        )
        rcm_id = rcm_created["id"]

        rcm_confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{rcm_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(rcm_confirm_resp.status_code, status.HTTP_200_OK, rcm_confirm_resp.json())

        rcm_match_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{rcm_id}/gstr2b/status/{self._scope_qs()}",
            {"match_status": int(PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED)},
            format="json",
        )
        self.assertEqual(rcm_match_resp.status_code, status.HTTP_200_OK, rcm_match_resp.json())

        rcm_claim_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{rcm_id}/itc/claim/{self._scope_qs()}",
            {"period": claim_period},
            format="json",
        )
        self.assertEqual(rcm_claim_resp.status_code, status.HTTP_400_BAD_REQUEST, rcm_claim_resp.json())
        self.assertIn(
            "reverse-charge tax payment is tracked",
            str(rcm_claim_resp.json()).lower(),
        )

    def test_itc_claim_allows_partial_2b_match_when_policy_allows_it(self):
        created = self._create_invoice(supplier_invoice_number="INV-ITC-PARTIAL-2B")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        partial_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/gstr2b/status/{self._scope_qs()}",
            {"match_status": int(PurchaseInvoiceHeader.Gstr2bMatchStatus.PARTIAL)},
            format="json",
        )
        self.assertEqual(partial_resp.status_code, status.HTTP_200_OK, partial_resp.json())
        self.assertEqual(
            partial_resp.json()["data"]["gstr2b_match_status"],
            int(PurchaseInvoiceHeader.Gstr2bMatchStatus.PARTIAL),
        )

        claim_period = timezone.localdate().strftime("%Y-%m")
        claim_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/itc/claim/{self._scope_qs()}",
            {"period": claim_period},
            format="json",
        )
        self.assertEqual(claim_resp.status_code, status.HTTP_200_OK, claim_resp.json())
        self.assertEqual(claim_resp.json()["data"]["itc_claim_status"], int(PurchaseInvoiceHeader.ItcClaimStatus.CLAIMED))
        self.assertEqual(claim_resp.json()["data"]["itc_claim_period"], claim_period)

        refreshed = PurchaseInvoiceHeader.objects.get(pk=invoice_id)
        self.assertEqual(int(refreshed.gstr2b_match_status), int(PurchaseInvoiceHeader.Gstr2bMatchStatus.PARTIAL))
        self.assertEqual(int(refreshed.itc_claim_status), int(PurchaseInvoiceHeader.ItcClaimStatus.CLAIMED))
        self.assertEqual(refreshed.itc_claim_period, claim_period)

    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseApService.sync_open_item_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_asset_purchase_remains_itc_eligible_through_post_and_claim_flow(
        self,
        mocked_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_open_item,
        mocked_sync_contract_ledger,
    ):
        created = self._create_invoice(
            supplier_invoice_number="INV-ASSET-ITC",
            lines=[self._asset_line_payload()],
        )
        invoice_id = created["id"]

        stored_line = PurchaseInvoiceLine.objects.get(header_id=invoice_id, line_no=1)
        self.assertEqual(stored_line.product_id, self.asset_product.id)
        self.assertEqual(stored_line.purchase_behavior, ProductPurchaseBehavior.ASSET)
        self.assertTrue(stored_line.is_itc_eligible)

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())
        mocked_post_adapter.assert_called_once()
        mocked_sync_asset_intakes.assert_called_once()
        mocked_sync_open_item.assert_called_once()
        self.assertTrue(mocked_sync_contract_ledger.called)

        match_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/gstr2b/status/{self._scope_qs()}",
            {"match_status": int(PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED)},
            format="json",
        )
        self.assertEqual(match_resp.status_code, status.HTTP_200_OK, match_resp.json())

        claim_period = timezone.localdate().strftime("%Y-%m")
        claim_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/itc/claim/{self._scope_qs()}",
            {"period": claim_period},
            format="json",
        )
        self.assertEqual(claim_resp.status_code, status.HTTP_200_OK, claim_resp.json())
        self.assertEqual(claim_resp.json()["data"]["itc_claim_status"], int(PurchaseInvoiceHeader.ItcClaimStatus.CLAIMED))
        self.assertEqual(claim_resp.json()["data"]["itc_claim_period"], claim_period)

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

    def test_ap_settlement_supports_multiple_purchase_invoices_for_same_vendor(self):
        PurchaseSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"policy_controls": {"settlement_mode": "basic", "allocation_policy": "manual"}},
        )

        created_one = self._create_invoice(supplier_invoice_number="INV-AP-MULTI-1")
        created_two = self._create_invoice(
            supplier_invoice_number="INV-AP-MULTI-2",
            lines=[self._service_line_payload()],
        )

        header_one = PurchaseInvoiceHeader.objects.get(pk=created_one["id"])
        header_two = PurchaseInvoiceHeader.objects.get(pk=created_two["id"])
        open_item_one = VendorBillOpenItem.objects.create(
            header=header_one,
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor=self.vendor,
            vendor_ledger_id=self.vendor.ledger_id,
            doc_type=int(header_one.doc_type),
            bill_date=header_one.bill_date,
            due_date=header_one.bill_date,
            purchase_number=header_one.purchase_number,
            supplier_invoice_number=header_one.supplier_invoice_number,
            original_amount=Decimal("1180.00"),
            gross_amount=Decimal("1180.00"),
            tds_deducted=Decimal("0.00"),
            gst_tds_deducted=Decimal("0.00"),
            net_payable_amount=Decimal("1180.00"),
            settled_amount=Decimal("0.00"),
            outstanding_amount=Decimal("1180.00"),
            is_open=True,
        )
        open_item_two = VendorBillOpenItem.objects.create(
            header=header_two,
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor=self.vendor,
            vendor_ledger_id=self.vendor.ledger_id,
            doc_type=int(header_two.doc_type),
            bill_date=header_two.bill_date,
            due_date=header_two.bill_date,
            purchase_number=header_two.purchase_number,
            supplier_invoice_number=header_two.supplier_invoice_number,
            original_amount=Decimal("590.00"),
            gross_amount=Decimal("590.00"),
            tds_deducted=Decimal("0.00"),
            gst_tds_deducted=Decimal("0.00"),
            net_payable_amount=Decimal("590.00"),
            settled_amount=Decimal("0.00"),
            outstanding_amount=Decimal("590.00"),
            is_open=True,
        )

        create_settlement_resp = self.client.post(
            "/api/purchase/ap/settlements/",
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "vendor": self.vendor.id,
                "settlement_type": "payment",
                "settlement_date": "2026-04-15",
                "reference_no": "SET-MULTI-001",
                "lines": [
                    {"open_item_id": open_item_one.id, "amount": "1000.00"},
                    {"open_item_id": open_item_two.id, "amount": "400.00"},
                ],
            },
            format="json",
        )
        self.assertEqual(create_settlement_resp.status_code, status.HTTP_201_CREATED, create_settlement_resp.json())
        settlement_id = create_settlement_resp.json()["data"]["id"]

        post_resp = self.client.post(f"/api/purchase/ap/settlements/{settlement_id}/post/", {}, format="json")
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())
        self.assertEqual(Decimal(str(post_resp.json()["applied_total"])), Decimal("1400.00"))

        open_item_one.refresh_from_db()
        open_item_two.refresh_from_db()
        self.assertEqual(open_item_one.outstanding_amount, Decimal("180.00"))
        self.assertEqual(open_item_two.outstanding_amount, Decimal("190.00"))
        self.assertTrue(open_item_one.is_open)
        self.assertTrue(open_item_two.is_open)

        statement_resp = self.client.get(
            f"/api/purchase/ap/vendor-statement/{self._scope_qs()}&vendor={self.vendor.id}"
        )
        self.assertEqual(statement_resp.status_code, status.HTTP_200_OK, statement_resp.json())
        totals = statement_resp.json()["totals"]
        self.assertEqual(Decimal(str(totals["outstanding_total"])), Decimal("370.00"))

    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_credit_purchase_derives_due_date_and_creates_open_item(
        self,
        mocked_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_contract_ledger,
    ):
        created = self._create_invoice(
            supplier_invoice_number="INV-CREDIT-001",
            credit_days=30,
            due_date=None,
        )
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        header = PurchaseInvoiceHeader.objects.get(pk=invoice_id)
        self.assertEqual(header.due_date.isoformat(), "2026-05-10")
        open_item = VendorBillOpenItem.objects.get(header_id=invoice_id)
        self.assertEqual(open_item.due_date.isoformat(), "2026-05-10")
        self.assertEqual(open_item.original_amount, Decimal("1180.00"))
        self.assertEqual(open_item.outstanding_amount, Decimal("1180.00"))
        self.assertTrue(open_item.is_open)
        self.assertEqual(mocked_post_adapter.call_count, 1)
        self.assertEqual(mocked_sync_asset_intakes.call_count, 1)
        self.assertTrue(mocked_sync_contract_ledger.called)

    @patch("payments.services.payment_voucher_service.PaymentVoucherPostingAdapter.post_payment_voucher")
    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_cash_purchase_flow_posts_payment_voucher_and_closes_open_item(
        self,
        mocked_purchase_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_contract_ledger,
        mocked_payment_post_adapter,
    ):
        PurchaseSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"policy_controls": {"settlement_mode": "basic", "allocation_policy": "manual"}},
        )
        created = self._create_invoice(
            supplier_invoice_number="INV-CASH-001",
            credit_days=0,
            due_date="2026-04-10",
        )
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        open_item = VendorBillOpenItem.objects.get(header_id=invoice_id)
        self.assertEqual(open_item.outstanding_amount, Decimal("1180.00"))
        self.assertTrue(open_item.is_open)

        voucher_resp = self.client.post(
            "/api/payments/payment-vouchers/",
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "voucher_date": "2026-04-10",
                "payment_type": PaymentVoucherHeader.PaymentType.AGAINST_BILL,
                "supply_type": PaymentVoucherHeader.SupplyType.GOODS,
                "paid_from": self.cash_account.id,
                "paid_to": self.vendor.id,
                "payment_mode": self.cash_payment_mode.id,
                "cash_paid_amount": "1180.00",
                "reference_number": "CASH-PUR-001",
                "narration": "Immediate cash settlement for purchase invoice",
                "allocations": [
                    {
                        "open_item": open_item.id,
                        "settled_amount": "1180.00",
                        "is_full_settlement": True,
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(voucher_resp.status_code, status.HTTP_201_CREATED, voucher_resp.json())
        voucher_id = voucher_resp.json()["id"]
        self.assertEqual(voucher_resp.json()["status"], int(PaymentVoucherHeader.Status.DRAFT))

        confirm_voucher_resp = self.client.post(
            f"/api/payments/payment-vouchers/{voucher_id}/confirm/",
            {},
            format="json",
        )
        self.assertEqual(confirm_voucher_resp.status_code, status.HTTP_200_OK, confirm_voucher_resp.json())

        post_voucher_resp = self.client.post(
            f"/api/payments/payment-vouchers/{voucher_id}/post/",
            {},
            format="json",
        )
        self.assertEqual(post_voucher_resp.status_code, status.HTTP_200_OK, post_voucher_resp.json())
        self.assertEqual(
            post_voucher_resp.json()["data"]["status"],
            int(PaymentVoucherHeader.Status.POSTED),
        )

        posted_voucher = PaymentVoucherHeader.objects.get(pk=voucher_id)
        self.assertIsNotNone(posted_voucher.ap_settlement_id)
        open_item.refresh_from_db()
        self.assertEqual(open_item.settled_amount, Decimal("1180.00"))
        self.assertEqual(open_item.outstanding_amount, Decimal("0.00"))
        self.assertFalse(open_item.is_open)
        self.assertEqual(mocked_purchase_post_adapter.call_count, 1)
        self.assertEqual(mocked_sync_asset_intakes.call_count, 1)
        self.assertTrue(mocked_sync_contract_ledger.called)
        mocked_payment_post_adapter.assert_called_once()

    @patch("payments.services.payment_voucher_service.WithholdingSection.objects.filter")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_ledger_id")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_account_id")
    @patch("payments.services.payment_voucher_service.compute_withholding_preview")
    @patch("payments.services.payment_voucher_service.PaymentVoucherPostingAdapter.post_payment_voucher")
    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_payment_stage_tds_full_settlement_closes_vendor_open_item(
        self,
        mocked_purchase_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_contract_ledger,
        mocked_payment_post_adapter,
        mock_preview,
        mock_get_account_id,
        mock_get_ledger_id,
        mock_filter,
    ):
        section = SimpleNamespace(id=5, base_rule=4, section_code="194A")
        mock_filter.return_value.only.return_value.first.return_value = section
        mock_get_account_id.return_value = self.tds_payable_account.id
        mock_get_ledger_id.return_value = self.tds_payable_account.ledger_id
        mock_preview.return_value = SimpleNamespace(
            rate=Decimal("0.8475"),
            amount=Decimal("10.00"),
            reason="payment-stage tds computed",
            reason_code="OK",
            section=section,
        )

        PurchaseSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"policy_controls": {"settlement_mode": "basic", "allocation_policy": "manual"}},
        )
        created = self._create_invoice(supplier_invoice_number="INV-TDS-PAY-FULL")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        open_item = VendorBillOpenItem.objects.get(header_id=invoice_id)
        self.assertEqual(open_item.outstanding_amount, Decimal("1180.00"))

        voucher_resp = self.client.post(
            "/api/payments/payment-vouchers/",
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "voucher_date": "2026-04-10",
                "payment_type": PaymentVoucherHeader.PaymentType.AGAINST_BILL,
                "supply_type": PaymentVoucherHeader.SupplyType.GOODS,
                "paid_from": self.cash_account.id,
                "paid_to": self.vendor.id,
                "payment_mode": self.cash_payment_mode.id,
                "cash_paid_amount": "1170.00",
                "reference_number": "TDS-PAY-FULL-001",
                "narration": "Full purchase settlement with payment-stage TDS",
                "allocations": [
                    {
                        "open_item": open_item.id,
                        "settled_amount": "1180.00",
                        "is_full_settlement": True,
                    }
                ],
                "workflow_payload": {
                    "withholding": {
                        "enabled": True,
                        "section_id": 5,
                        "mode": "AUTO",
                        "allow_static_fallback": True,
                    }
                },
            },
            format="json",
        )
        self.assertEqual(voucher_resp.status_code, status.HTTP_201_CREATED, voucher_resp.json())
        voucher_body = voucher_resp.json()
        voucher_id = voucher_body["id"]
        self.assertEqual(Decimal(str(voucher_body["total_adjustment_amount"])), Decimal("10.00"))
        self.assertEqual(Decimal(str(voucher_body["settlement_effective_amount"])), Decimal("1180.00"))
        self.assertEqual(len(voucher_body["adjustments"]), 1)
        self.assertEqual(voucher_body["adjustments"][0]["adj_type"], PaymentVoucherAdjustment.AdjType.TDS)
        self.assertEqual(Decimal(str(voucher_body["adjustments"][0]["amount"])), Decimal("10.00"))
        runtime = voucher_body["workflow_payload"]["withholding_runtime_result"]
        self.assertEqual(runtime["section_code"], "194A")
        self.assertEqual(runtime["deduction_status"], "DEDUCTED")
        self.assertEqual(runtime["amount"], "10.00")

        confirm_voucher_resp = self.client.post(
            f"/api/payments/payment-vouchers/{voucher_id}/confirm/",
            {},
            format="json",
        )
        self.assertEqual(confirm_voucher_resp.status_code, status.HTTP_200_OK, confirm_voucher_resp.json())

        post_voucher_resp = self.client.post(
            f"/api/payments/payment-vouchers/{voucher_id}/post/",
            {},
            format="json",
        )
        self.assertEqual(post_voucher_resp.status_code, status.HTTP_200_OK, post_voucher_resp.json())

        open_item.refresh_from_db()
        self.assertEqual(open_item.settled_amount, Decimal("1180.00"))
        self.assertEqual(open_item.outstanding_amount, Decimal("0.00"))
        self.assertFalse(open_item.is_open)

        posted_voucher = PaymentVoucherHeader.objects.get(pk=voucher_id)
        self.assertEqual(posted_voucher.status, PaymentVoucherHeader.Status.POSTED)
        self.assertEqual(posted_voucher.total_adjustment_amount, Decimal("10.00"))
        self.assertEqual(posted_voucher.settlement_effective_amount, Decimal("1180.00"))
        self.assertEqual(
            posted_voucher.workflow_payload.get("withholding_runtime_result", {}).get("section_code"),
            "194A",
        )
        self.assertEqual(mocked_purchase_post_adapter.call_count, 1)
        self.assertEqual(mocked_sync_asset_intakes.call_count, 1)
        self.assertTrue(mocked_sync_contract_ledger.called)
        mocked_payment_post_adapter.assert_called_once()

    @patch("payments.services.payment_voucher_service.WithholdingSection.objects.filter")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_ledger_id")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_account_id")
    @patch("payments.services.payment_voucher_service.compute_withholding_preview")
    @patch("payments.services.payment_voucher_service.PaymentVoucherPostingAdapter.post_payment_voucher")
    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_partial_payment_with_tds_keeps_vendor_open_item_partially_open(
        self,
        mocked_purchase_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_contract_ledger,
        mocked_payment_post_adapter,
        mock_preview,
        mock_get_account_id,
        mock_get_ledger_id,
        mock_filter,
    ):
        section = SimpleNamespace(id=5, base_rule=4, section_code="194A")
        mock_filter.return_value.only.return_value.first.return_value = section
        mock_get_account_id.return_value = self.tds_payable_account.id
        mock_get_ledger_id.return_value = self.tds_payable_account.ledger_id
        mock_preview.return_value = SimpleNamespace(
            rate=Decimal("1.6667"),
            amount=Decimal("10.00"),
            reason="payment-stage tds computed",
            reason_code="OK",
            section=section,
        )

        PurchaseSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"policy_controls": {"settlement_mode": "basic", "allocation_policy": "manual"}},
        )
        created = self._create_invoice(supplier_invoice_number="INV-TDS-PAY-PARTIAL")
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())
        post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        open_item = VendorBillOpenItem.objects.get(header_id=invoice_id)

        voucher_resp = self.client.post(
            "/api/payments/payment-vouchers/",
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "voucher_date": "2026-04-10",
                "payment_type": PaymentVoucherHeader.PaymentType.AGAINST_BILL,
                "supply_type": PaymentVoucherHeader.SupplyType.GOODS,
                "paid_from": self.cash_account.id,
                "paid_to": self.vendor.id,
                "payment_mode": self.cash_payment_mode.id,
                "cash_paid_amount": "590.00",
                "reference_number": "TDS-PAY-PART-001",
                "narration": "Partial purchase settlement with payment-stage TDS",
                "allocations": [
                    {
                        "open_item": open_item.id,
                        "settled_amount": "600.00",
                        "is_full_settlement": False,
                    }
                ],
                "workflow_payload": {
                    "withholding": {
                        "enabled": True,
                        "section_id": 5,
                        "mode": "AUTO",
                        "allow_static_fallback": True,
                    }
                },
            },
            format="json",
        )
        self.assertEqual(voucher_resp.status_code, status.HTTP_201_CREATED, voucher_resp.json())
        voucher_id = voucher_resp.json()["id"]
        self.assertEqual(Decimal(str(voucher_resp.json()["settlement_effective_amount"])), Decimal("600.00"))
        self.assertEqual(Decimal(str(voucher_resp.json()["total_adjustment_amount"])), Decimal("10.00"))

        confirm_voucher_resp = self.client.post(
            f"/api/payments/payment-vouchers/{voucher_id}/confirm/",
            {},
            format="json",
        )
        self.assertEqual(confirm_voucher_resp.status_code, status.HTTP_200_OK, confirm_voucher_resp.json())
        post_voucher_resp = self.client.post(
            f"/api/payments/payment-vouchers/{voucher_id}/post/",
            {},
            format="json",
        )
        self.assertEqual(post_voucher_resp.status_code, status.HTTP_200_OK, post_voucher_resp.json())

        open_item.refresh_from_db()
        self.assertEqual(open_item.settled_amount, Decimal("600.00"))
        self.assertEqual(open_item.outstanding_amount, Decimal("580.00"))
        self.assertTrue(open_item.is_open)
        mocked_payment_post_adapter.assert_called_once()
        self.assertEqual(mocked_purchase_post_adapter.call_count, 1)
        self.assertEqual(mocked_sync_asset_intakes.call_count, 1)
        self.assertTrue(mocked_sync_contract_ledger.called)

    @patch("payments.services.payment_voucher_service.WithholdingSection.objects.filter")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_ledger_id")
    @patch("payments.services.payment_voucher_service.StaticAccountService.get_account_id")
    @patch("payments.services.payment_voucher_service.compute_withholding_preview")
    @patch("payments.services.payment_voucher_service.PaymentVoucherPostingAdapter.post_payment_voucher")
    def test_advance_payment_with_tds_creates_vendor_advance_balance_for_effective_amount(
        self,
        mocked_payment_post_adapter,
        mock_preview,
        mock_get_account_id,
        mock_get_ledger_id,
        mock_filter,
    ):
        section = SimpleNamespace(id=5, base_rule=4, section_code="194A")
        mock_filter.return_value.only.return_value.first.return_value = section
        mock_get_account_id.return_value = self.tds_payable_account.id
        mock_get_ledger_id.return_value = self.tds_payable_account.ledger_id
        mock_preview.return_value = SimpleNamespace(
            rate=Decimal("1.0000"),
            amount=Decimal("10.00"),
            reason="payment-stage tds computed",
            reason_code="OK",
            section=section,
        )

        voucher_resp = self.client.post(
            "/api/payments/payment-vouchers/",
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "voucher_date": "2026-04-10",
                "payment_type": PaymentVoucherHeader.PaymentType.ADVANCE,
                "supply_type": PaymentVoucherHeader.SupplyType.SERVICES,
                "paid_from": self.cash_account.id,
                "paid_to": self.vendor.id,
                "payment_mode": self.cash_payment_mode.id,
                "cash_paid_amount": "1000.00",
                "reference_number": "TDS-ADV-001",
                "narration": "Vendor advance payment with payment-stage TDS",
                "workflow_payload": {
                    "withholding": {
                        "enabled": True,
                        "section_id": 5,
                        "mode": "AUTO",
                        "allow_static_fallback": True,
                    }
                },
            },
            format="json",
        )
        self.assertEqual(voucher_resp.status_code, status.HTTP_201_CREATED, voucher_resp.json())
        voucher_id = voucher_resp.json()["id"]
        self.assertEqual(Decimal(str(voucher_resp.json()["total_adjustment_amount"])), Decimal("10.00"))
        self.assertEqual(Decimal(str(voucher_resp.json()["settlement_effective_amount"])), Decimal("1010.00"))
        self.assertEqual(voucher_resp.json()["workflow_payload"]["withholding_runtime_result"]["section_code"], "194A")

        confirm_voucher_resp = self.client.post(
            f"/api/payments/payment-vouchers/{voucher_id}/confirm/",
            {},
            format="json",
        )
        self.assertEqual(confirm_voucher_resp.status_code, status.HTTP_200_OK, confirm_voucher_resp.json())
        post_voucher_resp = self.client.post(
            f"/api/payments/payment-vouchers/{voucher_id}/post/",
            {},
            format="json",
        )
        self.assertEqual(post_voucher_resp.status_code, status.HTTP_200_OK, post_voucher_resp.json())

        advance_balance = VendorAdvanceBalance.objects.get(payment_voucher_id=voucher_id)
        self.assertEqual(advance_balance.original_amount, Decimal("1010.00"))
        self.assertEqual(advance_balance.outstanding_amount, Decimal("1010.00"))
        self.assertTrue(advance_balance.is_open)

        posted_voucher = PaymentVoucherHeader.objects.get(pk=voucher_id)
        self.assertEqual(posted_voucher.status, PaymentVoucherHeader.Status.POSTED)
        mocked_payment_post_adapter.assert_called_once()

    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_credit_note_from_tds_booked_invoice_does_not_create_fresh_tds_deduction(
        self,
        mocked_purchase_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_contract_ledger,
    ):
        PurchaseSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"policy_controls": {"settlement_mode": "off", "allocation_policy": "manual"}},
        )
        section = WithholdingSection.objects.create(
            tax_type=WithholdingTaxType.TDS,
            section_code="194J",
            description="Professional fees",
            base_rule=WithholdingBaseRule.INVOICE_VALUE_EXCL_GST,
            rate_default=Decimal("1.0000"),
            threshold_default=Decimal("0.00"),
            effective_from=date(2020, 4, 1),
            is_active=True,
        )

        created = self._create_invoice(
            supplier_invoice_number="INV-TDS-CN-001",
            withholding_enabled=True,
            tds_is_manual=True,
            tds_section=section.id,
            tds_rate="1.0000",
            tds_base_amount="1000.00",
            tds_amount="10.00",
        )
        invoice_id = created["id"]
        self.assertEqual(Decimal(str(created["tds_amount"])), Decimal("10.00"))

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())
        post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        original_open_item = VendorBillOpenItem.objects.get(header_id=invoice_id)
        self.assertEqual(original_open_item.gross_amount, Decimal("1180.00"))
        self.assertEqual(original_open_item.tds_deducted, Decimal("10.00"))
        self.assertEqual(original_open_item.net_payable_amount, Decimal("1170.00"))
        self.assertEqual(original_open_item.outstanding_amount, Decimal("1170.00"))

        note_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/create-credit-note/{self._scope_qs()}",
            {
                "note_reason": PurchaseInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
            },
            format="json",
        )
        self.assertEqual(note_resp.status_code, status.HTTP_201_CREATED, note_resp.json())
        note_body = note_resp.json()["data"]
        note_id = note_body["id"]
        self.assertEqual(note_body["doc_type"], int(PurchaseInvoiceHeader.DocType.CREDIT_NOTE))
        self.assertEqual(note_body["ref_document"], invoice_id)
        self.assertFalse(note_body["withholding_enabled"])
        self.assertEqual(Decimal(str(note_body["tds_amount"])), Decimal("0.00"))
        self.assertFalse(note_body["affects_inventory"])

        confirm_note_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{note_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_note_resp.status_code, status.HTTP_200_OK, confirm_note_resp.json())
        post_note_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{note_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_note_resp.status_code, status.HTTP_200_OK, post_note_resp.json())

        note_header = PurchaseInvoiceHeader.objects.get(pk=note_id)
        self.assertEqual(note_header.doc_type, PurchaseInvoiceHeader.DocType.CREDIT_NOTE)
        self.assertEqual(note_header.ref_document_id, invoice_id)
        self.assertFalse(note_header.withholding_enabled)
        self.assertEqual(note_header.tds_amount, Decimal("0.00"))

        note_open_item = VendorBillOpenItem.objects.get(header_id=note_id)
        self.assertEqual(note_open_item.gross_amount, Decimal("-1180.00"))
        self.assertEqual(note_open_item.tds_deducted, Decimal("0.00"))
        self.assertEqual(note_open_item.net_payable_amount, Decimal("-1180.00"))
        self.assertEqual(note_open_item.outstanding_amount, Decimal("-1180.00"))

        self.assertEqual(mocked_purchase_post_adapter.call_count, 2)
        self.assertEqual(mocked_sync_asset_intakes.call_count, 2)
        self.assertTrue(mocked_sync_contract_ledger.called)

    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_filed_period_tds_invoice_uses_current_period_credit_note_without_mutating_original(
        self,
        mocked_purchase_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_contract_ledger,
    ):
        PurchaseSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"policy_controls": {"settlement_mode": "off", "allocation_policy": "manual"}},
        )
        section = WithholdingSection.objects.create(
            tax_type=WithholdingTaxType.TDS,
            section_code="194J",
            description="Professional fees",
            base_rule=WithholdingBaseRule.INVOICE_VALUE_EXCL_GST,
            rate_default=Decimal("1.0000"),
            threshold_default=Decimal("0.00"),
            effective_from=date(2020, 4, 1),
            is_active=True,
        )

        created = self._create_invoice(
            supplier_invoice_number="INV-TDS-FILED-001",
            bill_date="2026-04-10",
            posting_date="2026-04-10",
            supplier_invoice_date="2026-04-10",
            withholding_enabled=True,
            tds_is_manual=True,
            tds_section=section.id,
            tds_rate="1.0000",
            tds_base_amount="1000.00",
            tds_amount="10.00",
        )
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())
        post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        PurchaseLockPeriod.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            lock_date=date(2026, 4, 30),
            reason="April GST filed",
        )

        note_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/create-credit-note/{self._scope_qs()}",
            {
                "note_reason": PurchaseInvoiceHeader.NoteReason.PRICE_DIFFERENCE,
                "reason": "Filed-period TDS correction",
            },
            format="json",
        )
        self.assertEqual(note_resp.status_code, status.HTTP_201_CREATED, note_resp.json())
        note_body = note_resp.json()["data"]
        note_id = note_body["id"]
        expected_bill_date = timezone.localdate().strftime("%d-%m-%Y")
        self.assertEqual(note_body["bill_date"], expected_bill_date)
        self.assertEqual(note_body["posting_date"], expected_bill_date)
        self.assertEqual(note_body["ref_document"], invoice_id)
        self.assertFalse(note_body["withholding_enabled"])
        self.assertEqual(Decimal(str(note_body["tds_amount"])), Decimal("0.00"))

        original = PurchaseInvoiceHeader.objects.get(pk=invoice_id)
        self.assertEqual(original.status, PurchaseInvoiceHeader.Status.POSTED)
        self.assertEqual(original.bill_date, date(2026, 4, 10))
        self.assertEqual(original.posting_date, date(2026, 4, 10))
        self.assertTrue(original.withholding_enabled)
        self.assertEqual(original.tds_amount, Decimal("10.00"))
        self.assertEqual(len(original.match_notes.get("correction_history", [])), 1)

        correction_event = original.match_notes["correction_history"][0]
        self.assertEqual(correction_event["original_invoice_id"], invoice_id)
        self.assertEqual(correction_event["correction_document_id"], note_id)
        self.assertEqual(correction_event["reason"], "Filed-period TDS correction")
        self.assertEqual(correction_event["gst_period_impact"], timezone.localdate().strftime("%Y-%m"))

        confirm_note_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{note_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_note_resp.status_code, status.HTTP_200_OK, confirm_note_resp.json())
        post_note_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{note_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_note_resp.status_code, status.HTTP_200_OK, post_note_resp.json())

        note_header = PurchaseInvoiceHeader.objects.get(pk=note_id)
        self.assertEqual(note_header.status, PurchaseInvoiceHeader.Status.POSTED)
        self.assertEqual(note_header.ref_document_id, invoice_id)
        self.assertFalse(note_header.withholding_enabled)
        self.assertEqual(note_header.tds_amount, Decimal("0.00"))
        self.assertEqual(note_header.match_notes["correction_origin"]["original_invoice_id"], invoice_id)
        self.assertEqual(
            note_header.match_notes["correction_origin"]["gst_period_impact"],
            timezone.localdate().strftime("%Y-%m"),
        )

        note_open_item = VendorBillOpenItem.objects.get(header_id=note_id)
        self.assertEqual(note_open_item.gross_amount, Decimal("-1180.00"))
        self.assertEqual(note_open_item.tds_deducted, Decimal("0.00"))
        self.assertEqual(note_open_item.net_payable_amount, Decimal("-1180.00"))

        self.assertEqual(mocked_purchase_post_adapter.call_count, 2)
        self.assertEqual(mocked_sync_asset_intakes.call_count, 2)
        self.assertTrue(mocked_sync_contract_ledger.called)

    @patch("payments.services.payment_voucher_service.PaymentVoucherPostingAdapter.post_payment_voucher")
    @patch("purchase.services.purchase_invoice_actions.GstTdsService.sync_contract_ledger_for_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseAssetIntakeService.sync_asset_intakes_for_posted_header")
    @patch("purchase.services.purchase_invoice_actions.PurchaseInvoicePostingAdapter.post_purchase_invoice")
    def test_rcm_itc_claim_is_allowed_after_any_posted_payment_on_invoice(
        self,
        mocked_purchase_post_adapter,
        mocked_sync_asset_intakes,
        mocked_sync_contract_ledger,
        mocked_payment_post_adapter,
    ):
        PurchaseSettingsService.upsert_settings(
            entity_id=self.entity.id,
            subentity_id=self.subentity.id,
            updates={"policy_controls": {"settlement_mode": "basic", "allocation_policy": "manual"}},
        )
        rcm_service_line = self._service_line_payload()
        rcm_service_line.update(
            {
                "igst_amount": "0.00",
                "line_total": "500.00",
            }
        )
        created = self._create_invoice(
            supplier_invoice_number="INV-RCM-PAY-ITC",
            lines=[rcm_service_line],
            is_reverse_charge=True,
        )
        invoice_id = created["id"]

        confirm_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/confirm/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK, confirm_resp.json())

        post_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/post/{self._scope_qs()}",
            {},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK, post_resp.json())

        match_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/gstr2b/status/{self._scope_qs()}",
            {"match_status": int(PurchaseInvoiceHeader.Gstr2bMatchStatus.MATCHED)},
            format="json",
        )
        self.assertEqual(match_resp.status_code, status.HTTP_200_OK, match_resp.json())

        blocked_claim_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/itc/claim/{self._scope_qs()}",
            {"period": timezone.localdate().strftime("%Y-%m")},
            format="json",
        )
        self.assertEqual(blocked_claim_resp.status_code, status.HTTP_400_BAD_REQUEST, blocked_claim_resp.json())
        self.assertIn("reverse-charge tax payment is tracked", str(blocked_claim_resp.json()).lower())

        open_item = VendorBillOpenItem.objects.get(header_id=invoice_id)
        self.assertTrue(open_item.is_open)

        voucher_resp = self.client.post(
            "/api/payments/payment-vouchers/",
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "voucher_date": "2026-04-10",
                "payment_type": PaymentVoucherHeader.PaymentType.AGAINST_BILL,
                "supply_type": PaymentVoucherHeader.SupplyType.SERVICES,
                "paid_from": self.cash_account.id,
                "paid_to": self.vendor.id,
                "payment_mode": self.cash_payment_mode.id,
                "cash_paid_amount": "500.00",
                "reference_number": "RCM-PAY-001",
                "narration": "RCM purchase payment for ITC release",
                "allocations": [
                    {
                        "open_item": open_item.id,
                        "settled_amount": "500.00",
                        "is_full_settlement": True,
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(voucher_resp.status_code, status.HTTP_201_CREATED, voucher_resp.json())
        voucher_id = voucher_resp.json()["id"]

        confirm_voucher_resp = self.client.post(
            f"/api/payments/payment-vouchers/{voucher_id}/confirm/",
            {},
            format="json",
        )
        self.assertEqual(confirm_voucher_resp.status_code, status.HTTP_200_OK, confirm_voucher_resp.json())

        post_voucher_resp = self.client.post(
            f"/api/payments/payment-vouchers/{voucher_id}/post/",
            {},
            format="json",
        )
        self.assertEqual(post_voucher_resp.status_code, status.HTTP_200_OK, post_voucher_resp.json())
        open_item.refresh_from_db()
        self.assertEqual(open_item.settled_amount, Decimal("500.00"))
        self.assertEqual(open_item.outstanding_amount, Decimal("0.00"))
        self.assertFalse(open_item.is_open)

        claim_period = timezone.localdate().strftime("%Y-%m")
        claim_resp = self.client.post(
            f"/api/purchase/purchase-invoices/{invoice_id}/itc/claim/{self._scope_qs()}",
            {"period": claim_period},
            format="json",
        )
        self.assertEqual(claim_resp.status_code, status.HTTP_200_OK, claim_resp.json())
        self.assertEqual(claim_resp.json()["data"]["itc_claim_status"], int(PurchaseInvoiceHeader.ItcClaimStatus.CLAIMED))
        self.assertEqual(claim_resp.json()["data"]["itc_claim_period"], claim_period)

        refreshed = PurchaseInvoiceHeader.objects.get(pk=invoice_id)
        self.assertEqual(int(refreshed.itc_claim_status), int(PurchaseInvoiceHeader.ItcClaimStatus.CLAIMED))
        self.assertEqual(refreshed.itc_claim_period, claim_period)
        mocked_payment_post_adapter.assert_called_once()

    def test_attachment_upload_list_download_delete(self):
        created = self._create_invoice(supplier_invoice_number="INV-ATTACH")
        invoice_id = created["id"]
        scope = self._scope_qs()

        upload = SimpleUploadedFile(
            "supporting.pdf",
            b"purchase attachment payload",
            content_type="application/pdf",
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

    def test_attachment_upload_rejects_unsupported_text_file(self):
        created = self._create_invoice(supplier_invoice_number="INV-ATTACH-BAD")
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

        self.assertEqual(upload_resp.status_code, status.HTTP_400_BAD_REQUEST, upload_resp.json())
        self.assertEqual(upload_resp.json()["detail"], "supporting.txt is not a supported format.")

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

        match_resp = self.client.post(
            f"/api/purchase/gstr2b/import-batches/{batch_id}/match/",
            {},
            format="json",
            QUERY_STRING=f"entity={self.entity.id}&entityfinid={self.entityfin.id}&subentity={self.subentity.id}",
        )
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

    def test_gstr2b_batch_import_allows_missing_date_row_and_auto_match_marks_not_matched(self):
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
                        "supplier_invoice_number": "G2B-MISSING-DATE",
                        "supplier_invoice_date": None,
                        "is_igst": True,
                        "taxable_value": "0.00",
                        "igst": "0.00",
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
        self.assertIsNone(rows_resp.json()["results"][0]["supplier_invoice_date"])

        match_resp = self.client.post(
            f"/api/purchase/gstr2b/import-batches/{batch_id}/match/",
            {},
            format="json",
            QUERY_STRING=f"entity={self.entity.id}&entityfinid={self.entityfin.id}&subentity={self.subentity.id}",
        )
        self.assertEqual(match_resp.status_code, status.HTTP_200_OK, match_resp.json())
        self.assertEqual(match_resp.json()["summary"]["not_matched"], 1)

        row = Gstr2bImportRow.objects.get(pk=row_id)
        self.assertEqual(row.match_status, "NOT_MATCHED")
        self.assertIsNone(row.matched_purchase_id)

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
