from __future__ import annotations

from datetime import datetime
from decimal import Decimal

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
    UnitType,
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
from sales.serializers.sales_invoice_serializers import SalesInvoiceHeaderSerializer
from sales.services.sales_invoice_service import SalesInvoiceService


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class SalesInvoiceContractAlignmentTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="sales-ui", email="sales-ui@example.com", password="pass123")
        self.client.force_authenticate(user=self.user)

        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state = State.objects.create(statename="Maharashtra", statecode="27", country=self.country)
        self.other_state = State.objects.create(statename="Karnataka", statecode="29", country=self.country)
        self.district = District.objects.create(districtname="District", districtcode="DT", state=self.state)
        self.city = City.objects.create(cityname="Mumbai", citycode="MUM", pincode="400001", distt=self.district)
        self.unit_type = UnitType.objects.create(UnitName="Business", UnitDesc="Business")
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Sales Contract Entity",
            legalname="Sales Contract Entity Pvt Ltd",
            unitType=self.unit_type,
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
