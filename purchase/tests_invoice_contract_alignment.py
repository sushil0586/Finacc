from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity, UnitType
from financial.models import Ledger, account, accountHead, accounttype
from geography.models import City, Country, District, State
from purchase.serializers.purchase_invoice import PurchaseInvoiceLineSerializer
from purchase.services.purchase_invoice_service import DerivedRegime, PurchaseInvoiceService


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class PurchaseInvoiceContractAlignmentTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="purchase-ui", email="purchase-ui@example.com", password="pass123")
        self.client.force_authenticate(user=self.user)

        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state = State.objects.create(statename="Maharashtra", statecode="27", country=self.country)
        self.district = District.objects.create(districtname="District", districtcode="DT", state=self.state)
        self.city = City.objects.create(cityname="Mumbai", citycode="MUM", pincode="400001", distt=self.district)
        self.unit_type = UnitType.objects.create(UnitName="Business", UnitDesc="Business")
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Purchase Contract Entity",
            legalname="Purchase Contract Entity Pvt Ltd",
            unitType=self.unit_type,
            GstRegitrationType=self.gst_type,
            address="Address",
            phoneoffice="9999999999",
            phoneresidence="9999999998",
            country=self.country,
            state=self.state,
            district=self.district,
            city=self.city,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Branch", address="Branch")
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2025-26",
            finstartyear=timezone.make_aware(datetime(2025, 4, 1)),
            finendyear=timezone.make_aware(datetime(2026, 3, 31)),
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
        self.vendor = account.objects.create(
            entity=self.entity,
            ledger=self.vendor_ledger,
            accounthead=self.vendor_head,
            accountname="Alpha Traders",
            accountcode=4001,
            gstno="27ABCDE1234F1Z5",
            partytype="Vendor",
            createdby=self.user,
        )

    def test_purchase_form_meta_exposes_backend_authoritative_contract(self):
        response = self.client.get(
            reverse("purchase-invoice-form-meta"),
            {"entity": self.entity.id, "subentity": self.subentity.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        contract = response.data["ui_contract"]
        self.assertTrue(contract["save_reload"]["use_save_response_as_truth"])
        self.assertEqual(contract["header_fields"]["due_date"]["ui_state"], "provisional")
        self.assertEqual(contract["header_fields"]["total_taxable"]["ui_state"], "read_only")
        self.assertEqual(contract["line_fields"]["cgst_amount"]["ui_state"], "read_only")
        self.assertEqual(contract["line_fields"]["cess_amount"]["save_behavior"], "recomputed_on_save")

    def test_purchase_apply_dates_derives_due_date_and_posting_date(self):
        attrs = {"bill_date": date(2025, 4, 10), "credit_days": 7}
        PurchaseInvoiceService.apply_dates(attrs)
        self.assertEqual(attrs["posting_date"], date(2025, 4, 10))
        self.assertEqual(attrs["due_date"], date(2025, 4, 17))

    def test_purchase_compute_line_recomputes_cess_and_suppresses_rcm_gst(self):
        non_rcm = PurchaseInvoiceService.compute_line_authoritative(
            header_attrs={"default_taxability": 1, "is_reverse_charge": False},
            line={
                "qty": Decimal("2.0000"),
                "rate": Decimal("50.00"),
                "gst_rate": Decimal("18.00"),
                "discount_type": "N",
                "discount_percent": Decimal("0.00"),
                "discount_amount": Decimal("0.00"),
                "cess_percent": Decimal("5.00"),
                "cess_amount": Decimal("999.00"),
                "taxability": 1,
            },
            derived=DerivedRegime(tax_regime=1, is_igst=False),
        )
        self.assertEqual(non_rcm["cess_amount"], Decimal("5.00"))
        self.assertEqual(non_rcm["cgst_amount"], Decimal("9.00"))
        self.assertEqual(non_rcm["sgst_amount"], Decimal("9.00"))

        rcm = PurchaseInvoiceService.compute_line_authoritative(
            header_attrs={"default_taxability": 1, "is_reverse_charge": True},
            line={
                "qty": Decimal("1.0000"),
                "rate": Decimal("100.00"),
                "gst_rate": Decimal("18.00"),
                "discount_type": "N",
                "discount_percent": Decimal("0.00"),
                "discount_amount": Decimal("0.00"),
                "cess_percent": Decimal("5.00"),
                "cess_amount": Decimal("50.00"),
                "taxability": 1,
            },
            derived=DerivedRegime(tax_regime=1, is_igst=False),
        )
        self.assertEqual(rcm["cgst_amount"], Decimal("0.00"))
        self.assertEqual(rcm["sgst_amount"], Decimal("0.00"))
        self.assertEqual(rcm["igst_amount"], Decimal("0.00"))
        self.assertEqual(rcm["cess_amount"], Decimal("0.00"))

    def test_purchase_line_serializer_auto_fills_itc_block_reason(self):
        serializer = PurchaseInvoiceLineSerializer(
            data={
                "line_no": 1,
                "qty": "1.0000",
                "free_qty": "0.0000",
                "rate": "100.00",
                "discount_type": "N",
                "discount_percent": "0.00",
                "discount_amount": "0.00",
                "taxability": 1,
                "taxable_value": "0.00",
                "gst_rate": "18.00",
                "cgst_percent": "0.00",
                "sgst_percent": "0.00",
                "igst_percent": "0.00",
                "cgst_amount": "0.00",
                "sgst_amount": "0.00",
                "igst_amount": "0.00",
                "cess_percent": "0.00",
                "cess_amount": "0.00",
                "line_total": "0.00",
                "is_itc_eligible": False,
                "itc_block_reason": "",
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["itc_block_reason"], "ITC not eligible")
