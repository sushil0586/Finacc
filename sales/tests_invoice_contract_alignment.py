from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from catalog.models import Product, ProductCategory, UnitOfMeasure
from entity.models import (
    Entity,
    EntityAddress,
    EntityFinancialYear,
    EntityGstRegistration,
    GstRegistrationType,
    SubEntity,
)
from financial.models import (
    AccountCommercialProfile,
    AccountComplianceProfile,
    Ledger,
    account,
    accountHead,
    accounttype,
)
from financial.services import create_account_with_synced_ledger
from geography.models import City, Country, District, State
from sales.models import SalesInvoiceHeader, SalesInvoiceLine
from sales.models.sales_ar import CustomerBillOpenItem
from sales.models.sales_compliance import SalesEInvoice, SalesEInvoiceStatus, SalesEWayBill, SalesEWayStatus
from sales.models.sales_settings import SalesChoiceOverride
from sales.serializers.sales_invoice_serializers import SalesInvoiceHeaderSerializer
from sales.services.sales_compliance_service import SalesComplianceService
from sales.services.sales_invoice_service import SalesInvoiceService
from sales.services.sales_choices_service import SalesChoicesService
from sales.services.sales_settings_service import SalesSettingsService


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class SalesInvoiceContractAlignmentTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="sales-ui", email="sales-ui@example.com", password="pass123")
        self.client.force_authenticate(user=self.user)
        cache.clear()

        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state = State.objects.create(statename="Maharashtra", statecode="27", country=self.country)
        self.other_state = State.objects.create(statename="Karnataka", statecode="29", country=self.country)
        self.district = District.objects.create(districtname="District", districtcode="DT", state=self.state)
        self.city = City.objects.create(cityname="Mumbai", citycode="MUM", pincode="400001", distt=self.district)
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Sales Contract Entity",
            legalname="Sales Contract Entity Pvt Ltd",
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
            desc="FY 2025-26",
            finstartyear=timezone.make_aware(datetime(2025, 4, 1)),
            finendyear=timezone.make_aware(datetime(2026, 3, 31)),
            createdby=self.user,
        )
        self.acc_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Customer",
            accounttypecode="C100",
            createdby=self.user,
        )
        self.customer_head = accountHead.objects.create(
            entity=self.entity,
            name="Debtors",
            code=100,
            balanceType="Debit",
            drcreffect="Debit",
            accounttype=self.acc_type,
            createdby=self.user,
        )
        self.customer_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=5001,
            name="Alpha Retail",
            accounthead=self.customer_head,
            createdby=self.user,
        )
        self.customer = create_account_with_synced_ledger(
            account_data={
                "entity": self.entity,
                "ledger": self.customer_ledger,
                "accountname": "Alpha Retail",
                "createdby": self.user,
            },
            ledger_overrides={"ledger_code": 5001, "accounthead": self.customer_head, "is_party": True},
        )
        AccountComplianceProfile.objects.update_or_create(
            account=self.customer,
            defaults={
                "entity": self.entity,
                "gstno": "27ABCDE1234F1Z5",
                "createdby": self.user,
            },
        )
        AccountCommercialProfile.objects.update_or_create(
            account=self.customer,
            defaults={
                "entity": self.entity,
                "partytype": "Customer",
                "createdby": self.user,
            },
        )
        self.uom = UnitOfMeasure.objects.create(entity=self.entity, code="NOS", description="Numbers")
        self.category = ProductCategory.objects.create(entity=self.entity, pcategoryname="Goods")
        self.product = Product.objects.create(
            entity=self.entity,
            productname="Widget",
            sku="WIDGET-001",
            productcategory=self.category,
            base_uom=self.uom,
        )

    def test_sales_form_meta_exposes_backend_authoritative_contract(self):
        response = self.client.get(
            reverse("sales-invoice-form-meta"),
            {"entity": self.entity.id, "subentity": self.subentity.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        contract = response.data["ui_contract"]
        self.assertTrue(contract["save_reload"]["use_save_response_as_truth"])
        self.assertEqual(contract["header_fields"]["due_date"]["ui_state"], "read_only")
        self.assertEqual(contract["header_fields"]["tax_regime"]["ui_state"], "read_only")
        self.assertEqual(contract["line_fields"]["cess_amount"]["ui_state"], "provisional")

    def test_sales_detail_meta_reflects_recovered_compliance_flags_and_artifacts(self):
        invoice = SalesInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date=datetime(2025, 4, 10).date(),
            posting_date=datetime(2025, 4, 10).date(),
            due_date=datetime(2025, 4, 15).date(),
            doc_code="SI",
            doc_no=101,
            invoice_number="SI/101",
            customer=self.customer,
            customer_ledger=self.customer.ledger,
            customer_name="Alpha Retail",
            customer_gstin="27ABCDE1234F1Z5",
            customer_state_code="27",
            seller_gstin="27AAAAA9999A1Z5",
            seller_state_code="27",
            place_of_supply_state_code="27",
            place_of_supply_pincode="400001",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxability=SalesInvoiceHeader.Taxability.TAXABLE,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTRA_STATE,
            gst_compliance_mode=SalesInvoiceHeader.GstComplianceMode.EINVOICE_AND_EWAY,
            is_einvoice_applicable=True,
            is_eway_applicable=True,
        )
        SalesInvoiceLine.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            header=invoice,
            line_no=1,
            product=self.product,
            uom=self.uom,
            hsn_sac_code="8471",
            is_service=False,
            qty=Decimal("1.000"),
            free_qty=Decimal("0.000"),
            rate=Decimal("100.0000"),
            discount_type=SalesInvoiceLine.DiscountType.NONE,
            discount_percent=Decimal("0.0000"),
            discount_amount=Decimal("0.00"),
            gst_rate=Decimal("18.00"),
            taxable_value=Decimal("100.00"),
            cgst_amount=Decimal("9.00"),
            sgst_amount=Decimal("9.00"),
            igst_amount=Decimal("0.00"),
            cess_percent=Decimal("0.00"),
            cess_amount=Decimal("0.00"),
            line_total=Decimal("118.00"),
        )
        SalesEInvoice.objects.create(
            invoice=invoice,
            status=SalesEInvoiceStatus.GENERATED,
            irn="IRN123",
            ack_no="ACK123",
            created_by=self.user,
            updated_by=self.user,
        )
        SalesEWayBill.objects.create(
            invoice=invoice,
            status=SalesEWayStatus.GENERATED,
            ewb_no="171001234567",
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.get(
            reverse("sales-invoice-detail-form-meta"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "invoice": invoice.id,
                "line_mode": "goods",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["invoice"]["einvoice_artifact"]["irn"], "IRN123")
        self.assertEqual(response.data["invoice"]["eway_artifact"]["ewb_no"], "171001234567")
        self.assertEqual(response.data["invoice"]["compliance_action_flags"]["can_generate_irn"], False)
        self.assertEqual(response.data["invoice"]["compliance_action_flags"]["can_generate_eway"], False)
        self.assertEqual(response.data["invoice"]["compliance_action_flags"]["can_load_eway_prefill"], False)
        self.assertEqual(response.data["invoice"]["compliance_action_flags"]["can_cancel_irn"], False)
        self.assertEqual(response.data["invoice"]["compliance_action_flags"]["can_cancel_eway"], True)
        self.assertEqual(response.data["compliance_action_flags"]["can_cancel_eway"], True)

    def test_b2c_generated_eway_disables_b2c_prefill_flag(self):
        invoice = SalesInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date=datetime(2025, 4, 20).date(),
            posting_date=datetime(2025, 4, 20).date(),
            due_date=datetime(2025, 4, 25).date(),
            doc_code="SI",
            doc_no=302,
            invoice_number="SI/302",
            customer=self.customer,
            customer_ledger=self.customer.ledger,
            customer_name="Alpha Retail",
            customer_gstin="",
            customer_state_code="27",
            seller_gstin="27AAAAA9999A1Z5",
            seller_state_code="27",
            place_of_supply_state_code="27",
            place_of_supply_pincode="400001",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2C,
            taxability=SalesInvoiceHeader.Taxability.TAXABLE,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTRA_STATE,
            gst_compliance_mode=SalesInvoiceHeader.GstComplianceMode.EWAY_ONLY,
            is_einvoice_applicable=False,
            is_eway_applicable=True,
        )
        SalesInvoiceLine.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            header=invoice,
            line_no=1,
            product=self.product,
            uom=self.uom,
            hsn_sac_code="8471",
            is_service=False,
            qty=Decimal("1.000"),
            free_qty=Decimal("0.000"),
            rate=Decimal("100.0000"),
            discount_type=SalesInvoiceLine.DiscountType.NONE,
            discount_percent=Decimal("0.0000"),
            discount_amount=Decimal("0.00"),
            gst_rate=Decimal("18.00"),
            taxable_value=Decimal("100.00"),
            cgst_amount=Decimal("9.00"),
            sgst_amount=Decimal("9.00"),
            igst_amount=Decimal("0.00"),
            cess_percent=Decimal("0.00"),
            cess_amount=Decimal("0.00"),
            line_total=Decimal("118.00"),
        )
        SalesEWayBill.objects.create(
            invoice=invoice,
            status=SalesEWayStatus.GENERATED,
            ewb_no="171001234568",
            created_by=self.user,
            updated_by=self.user,
        )

        flags = SalesComplianceService.compliance_action_flags(invoice)

        self.assertEqual(flags["state"]["is_b2c"], True)
        self.assertEqual(flags["can_generate_eway"], False)
        self.assertEqual(flags["can_load_eway_b2c_prefill"], False)
        self.assertEqual(flags["can_cancel_eway"], True)

    def test_customer_statement_open_items_expose_service_invoice_route(self):
        invoice = SalesInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            doc_type=SalesInvoiceHeader.DocType.TAX_INVOICE,
            status=SalesInvoiceHeader.Status.POSTED,
            bill_date=datetime(2025, 4, 20).date(),
            posting_date=datetime(2025, 4, 20).date(),
            due_date=datetime(2025, 4, 25).date(),
            doc_code="SI",
            doc_no=202,
            invoice_number="SI/202",
            customer=self.customer,
            customer_ledger=self.customer.ledger,
            customer_name="Alpha Retail",
            customer_gstin="27ABCDE1234F1Z5",
            customer_state_code="27",
            seller_gstin="27AAAAA9999A1Z5",
            seller_state_code="27",
            place_of_supply_state_code="27",
            supply_category=SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
            taxability=SalesInvoiceHeader.Taxability.TAXABLE,
            tax_regime=SalesInvoiceHeader.TaxRegime.INTRA_STATE,
            total_taxable_value=Decimal("100.00"),
            total_cgst=Decimal("9.00"),
            total_sgst=Decimal("9.00"),
            total_igst=Decimal("0.00"),
            total_cess=Decimal("0.00"),
            total_discount=Decimal("0.00"),
            round_off=Decimal("0.00"),
            grand_total=Decimal("118.00"),
            created_by=self.user,
        )
        SalesInvoiceLine.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            header=invoice,
            line_no=1,
            product=self.product,
            uom=self.uom,
            hsn_sac_code="9983",
            is_service=True,
            qty=Decimal("1.000"),
            free_qty=Decimal("0.000"),
            rate=Decimal("100.0000"),
            discount_type=SalesInvoiceLine.DiscountType.NONE,
            discount_percent=Decimal("0.0000"),
            discount_amount=Decimal("0.00"),
            gst_rate=Decimal("18.00"),
            taxable_value=Decimal("100.00"),
            cgst_amount=Decimal("9.00"),
            sgst_amount=Decimal("9.00"),
            igst_amount=Decimal("0.00"),
            cess_percent=Decimal("0.00"),
            cess_amount=Decimal("0.00"),
            line_total=Decimal("118.00"),
        )
        CustomerBillOpenItem.objects.create(
            header=invoice,
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            customer=self.customer,
            customer_ledger=self.customer.ledger,
            doc_type=invoice.doc_type,
            bill_date=invoice.bill_date,
            due_date=invoice.due_date,
            invoice_number=invoice.invoice_number,
            customer_reference_number="REF-202",
            original_amount=Decimal("118.00"),
            gross_amount=Decimal("118.00"),
            net_receivable_amount=Decimal("118.00"),
            settled_amount=Decimal("0.00"),
            outstanding_amount=Decimal("118.00"),
            is_open=True,
        )

        with patch("sales.views.sales_ar.require_sales_scope_permission", return_value=self.entity):
            response = self.client.get(
                reverse("sales-ar-customer-statement"),
                {
                    "entity": self.entity.id,
                    "entityfinid": self.entityfin.id,
                    "subentity": self.subentity.id,
                    "customer": self.customer.id,
                },
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        open_item = next(item for item in response.data["open_items"] if item["invoice_number"] == invoice.invoice_number)
        self.assertEqual(open_item["source_route"], "/saleserviceinvoice")

    @override_settings(META_CACHE_ENABLED=True, META_CACHE_FORM_TTL_SECONDS=600, META_CACHE_VERSION="test")
    def test_sales_form_meta_uses_cache_on_repeated_requests(self):
        with patch(
            "sales.views.sales_meta.SalesChoicesService.get_choices",
            wraps=SalesChoicesService.get_choices,
        ) as mocked_get_choices:
            for _ in range(2):
                response = self.client.get(
                    reverse("sales-invoice-form-meta"),
                    {"entity": self.entity.id, "subentity": self.subentity.id},
                    format="json",
                )
                self.assertEqual(response.status_code, 200)
            self.assertEqual(mocked_get_choices.call_count, 1)

    @override_settings(META_CACHE_ENABLED=True, META_CACHE_SETTINGS_TTL_SECONDS=600, META_CACHE_VERSION="test")
    def test_sales_settings_meta_uses_cache_on_repeated_requests(self):
        with patch(
            "sales.views.sales_meta.SalesSettingsService.get_current_doc_no",
            wraps=SalesSettingsService.get_current_doc_no,
        ) as mocked_doc_no:
            for _ in range(2):
                response = self.client.get(
                    reverse("sales-settings-meta"),
                    {"entity": self.entity.id, "entityfinid": self.entityfin.id, "subentity": self.subentity.id},
                    format="json",
                )
                self.assertEqual(response.status_code, 200)
            # invoice + credit note + debit note only once when cache is effective
            self.assertEqual(mocked_doc_no.call_count, 3)

    @override_settings(META_CACHE_ENABLED=True, META_CACHE_FORM_TTL_SECONDS=600, META_CACHE_VERSION="test")
    def test_sales_form_meta_cache_invalidates_on_choice_override_change(self):
        with patch(
            "sales.views.sales_meta.SalesChoicesService.get_choices",
            wraps=SalesChoicesService.get_choices,
        ) as mocked_get_choices:
            response = self.client.get(
                reverse("sales-invoice-form-meta"),
                {"entity": self.entity.id, "subentity": self.subentity.id},
                format="json",
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(mocked_get_choices.call_count, 1)

            SalesChoiceOverride.objects.create(
                entity=self.entity,
                subentity=self.subentity,
                choice_group="DocType",
                choice_key="TAX_INVOICE",
                is_enabled=True,
            )

            response = self.client.get(
                reverse("sales-invoice-form-meta"),
                {"entity": self.entity.id, "subentity": self.subentity.id},
                format="json",
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(mocked_get_choices.call_count, 2)

    @override_settings(
        META_CACHE_ENABLED=True,
        META_CACHE_FORM_TTL_SECONDS=600,
        META_CACHE_VERSION="test",
        META_CACHE_OBSERVABILITY_ENABLED=True,
        META_CACHE_LOG_LEVEL="INFO",
    )
    def test_sales_form_meta_emits_cache_observability_events(self):
        with self.assertLogs("helpers.utils.meta_cache", level="INFO") as captured:
            for _ in range(2):
                response = self.client.get(
                    reverse("sales-invoice-form-meta"),
                    {"entity": self.entity.id, "subentity": self.subentity.id},
                    format="json",
                )
                self.assertEqual(response.status_code, 200)

        output = "\n".join(captured.output)
        self.assertIn("meta_cache.miss", output)
        self.assertIn("meta_cache.store", output)
        self.assertIn("meta_cache.hit", output)

    def test_sales_header_serializer_ignores_selected_backend_derived_fields(self):
        serializer = SalesInvoiceHeaderSerializer(
            data={
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "doc_type": SalesInvoiceHeader.DocType.TAX_INVOICE,
                "bill_date": "2025-04-10",
                "credit_days": 5,
                "doc_code": "SINV",
                "customer": self.customer.id,
                "customer_name": "Alpha Retail",
                "customer_gstin": "27ABCDE1234F1Z5",
                "customer_state_code": "27",
                "seller_gstin": "27AAAAA9999A1Z5",
                "seller_state_code": "27",
                "place_of_supply_state_code": "29",
                "supply_category": SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
                "taxability": SalesInvoiceHeader.Taxability.TAXABLE,
                "due_date": "2025-04-20",
                "tax_regime": SalesInvoiceHeader.TaxRegime.INTER_STATE,
                "total_other_charges": "25.00",
                "lines": [
                    {
                        "line_no": 1,
                        "product": self.product.id,
                        "uom": self.uom.id,
                        "qty": "1.000",
                        "free_qty": "0.000",
                        "rate": "100.0000",
                        "discount_type": 0,
                        "discount_percent": "0.0000",
                        "discount_amount": "0.00",
                        "gst_rate": "18.00",
                        "cess_percent": "0.00",
                        "cess_amount": "0.00",
                    }
                ],
            },
            context={"request": type("Req", (), {"user": self.user, "data": {}})()},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("due_date", serializer.errors)
        self.assertNotIn("tax_regime", serializer.errors)
        self.assertNotIn("total_other_charges", serializer.errors)

    def test_sales_header_serializer_still_blocks_other_backend_controlled_fields(self):
        serializer = SalesInvoiceHeaderSerializer(
            data={
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "doc_type": SalesInvoiceHeader.DocType.TAX_INVOICE,
                "bill_date": "2025-04-10",
                "credit_days": 5,
                "doc_code": "SINV",
                "customer": self.customer.id,
                "customer_name": "Alpha Retail",
                "customer_gstin": "27ABCDE1234F1Z5",
                "customer_state_code": "27",
                "seller_gstin": "27AAAAA9999A1Z5",
                "seller_state_code": "27",
                "place_of_supply_state_code": "29",
                "supply_category": SalesInvoiceHeader.SupplyCategory.DOMESTIC_B2B,
                "taxability": SalesInvoiceHeader.Taxability.TAXABLE,
                "due_date": "2025-04-20",
                "is_igst": True,
                "total_cgst": "10.00",
                "lines": [
                    {
                        "line_no": 1,
                        "product": self.product.id,
                        "uom": self.uom.id,
                        "qty": "1.000",
                        "free_qty": "0.000",
                        "rate": "100.0000",
                        "discount_type": 0,
                        "discount_percent": "0.0000",
                        "discount_amount": "0.00",
                        "gst_rate": "18.00",
                        "cess_percent": "0.00",
                        "cess_amount": "0.00",
                    }
                ],
            },
            context={"request": type("Req", (), {"user": self.user, "data": {}})()},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("due_date", serializer.errors)
        self.assertIn("is_igst", serializer.errors)
        self.assertIn("total_cgst", serializer.errors)

    def test_sales_service_derives_due_date_and_tax_regime(self):
        header = SalesInvoiceHeader(
            bill_date=datetime(2025, 4, 10).date(),
            credit_days=5,
            seller_state_code="27",
            place_of_supply_state_code="29",
        )
        SalesInvoiceService.apply_dates(header)
        SalesInvoiceService.derive_tax_regime(header)
        self.assertEqual(header.posting_date, datetime(2025, 4, 10).date())
        self.assertEqual(header.due_date, datetime(2025, 4, 15).date())
        self.assertEqual(int(header.tax_regime), int(SalesInvoiceHeader.TaxRegime.INTER_STATE))
        self.assertTrue(header.is_igst)

    def test_sales_compute_line_amounts_recomputes_or_preserves_cess_per_backend_rule(self):
        header = SalesInvoiceHeader(is_igst=False)

        computed_line = SalesInvoiceLine(
            line_no=1,
            product=self.product,
            uom=self.uom,
            qty=Decimal("1.000"),
            free_qty=Decimal("0.000"),
            rate=Decimal("100.0000"),
            discount_type=SalesInvoiceLine.DiscountType.NONE,
            discount_percent=Decimal("0.0000"),
            discount_amount=Decimal("0.00"),
            gst_rate=Decimal("18.0000"),
            cess_percent=Decimal("5.0000"),
            cess_amount=Decimal("999.00"),
            hsn_sac_code="8471",
        )
        SalesInvoiceService.compute_line_amounts(header, computed_line)
        self.assertEqual(computed_line.cess_amount, Decimal("5.00"))

        manual_line = SalesInvoiceLine(
            line_no=2,
            product=self.product,
            uom=self.uom,
            qty=Decimal("1.000"),
            free_qty=Decimal("0.000"),
            rate=Decimal("100.0000"),
            discount_type=SalesInvoiceLine.DiscountType.NONE,
            discount_percent=Decimal("0.0000"),
            discount_amount=Decimal("0.00"),
            gst_rate=Decimal("18.0000"),
            cess_percent=Decimal("0.0000"),
            cess_amount=Decimal("7.50"),
            hsn_sac_code="8471",
        )
        SalesInvoiceService.compute_line_amounts(header, manual_line)
        self.assertEqual(manual_line.cess_amount, Decimal("7.50"))

    def test_sales_compute_line_amounts_uses_taxable_base_for_inclusive_cess(self):
        header = SalesInvoiceHeader(is_igst=True)

        inclusive_line = SalesInvoiceLine(
            line_no=3,
            product=self.product,
            uom=self.uom,
            qty=Decimal("20.000"),
            free_qty=Decimal("0.000"),
            rate=Decimal("20.0000"),
            is_rate_inclusive_of_tax=True,
            discount_type=SalesInvoiceLine.DiscountType.NONE,
            discount_percent=Decimal("0.0000"),
            discount_amount=Decimal("0.00"),
            gst_rate=Decimal("18.0000"),
            cess_percent=Decimal("1.0000"),
            cess_amount=Decimal("0.00"),
            hsn_sac_code="8471",
        )

        SalesInvoiceService.compute_line_amounts(header, inclusive_line)

        self.assertEqual(inclusive_line.taxable_value, Decimal("338.98"))
        self.assertEqual(inclusive_line.igst_amount, Decimal("61.02"))
        self.assertEqual(inclusive_line.cess_amount, Decimal("3.39"))
        self.assertEqual(inclusive_line.line_total, Decimal("403.39"))
