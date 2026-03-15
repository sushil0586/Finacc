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
from purchase.models.purchase_ap import VendorAdvanceBalance, VendorBillOpenItem, VendorSettlement, VendorSettlementLine
from purchase.models.purchase_core import PurchaseInvoiceHeader


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class PayableReportAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="payable-report-user", email="payable@example.com", password="pass123")
        self.client.force_authenticate(user=self.user)

        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state = State.objects.create(statename="Punjab", statecode="PB", country=self.country)
        self.district = District.objects.create(districtname="District", districtcode="DT", state=self.state)
        self.city = City.objects.create(cityname="Ludhiana", citycode="LDH", pincode="141001", distt=self.district)
        self.unit_type = UnitType.objects.create(UnitName="Business", UnitDesc="Business")
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Payable Entity",
            legalname="Payable Entity Pvt Ltd",
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
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Branch A", address="Branch Address")
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2025-26",
            finstartyear=timezone.make_aware(datetime(2025, 4, 1)),
            finendyear=timezone.make_aware(datetime(2026, 3, 31)),
            createdby=self.user,
        )

        self.acc_type = accounttype.objects.create(entity=self.entity, accounttypename="Liabilities", accounttypecode="L100", createdby=self.user)
        self.vendor_head = accountHead.objects.create(
            entity=self.entity,
            name="Sundry Creditors",
            code=400,
            balanceType="Credit",
            drcreffect="Credit",
            accounttype=self.acc_type,
            createdby=self.user,
        )
        self.vendor_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=5001,
            name="ABC Traders",
            accounthead=self.vendor_head,
            createdby=self.user,
        )
        self.vendor = account.objects.create(
            entity=self.entity,
            ledger=self.vendor_ledger,
            accounthead=self.vendor_head,
            accountname="ABC Traders",
            accountcode=5001,
            gstno="03ABCDE1234F1Z5",
            partytype="Vendor",
            state=self.state,
            city=self.city,
            currency="INR",
            agent="Wholesale",
            creditdays=30,
            creditlimit=Decimal("1000.00"),
            createdby=self.user,
        )
        self.other_vendor_ledger = Ledger.objects.create(
            entity=self.entity,
            ledger_code=5002,
            name="Idle Vendor",
            accounthead=self.vendor_head,
            createdby=self.user,
        )
        self.other_vendor = account.objects.create(
            entity=self.entity,
            ledger=self.other_vendor_ledger,
            accounthead=self.vendor_head,
            accountname="Idle Vendor",
            accountcode=5002,
            partytype="Vendor",
            createdby=self.user,
        )

        self.invoice = PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
            bill_date=date(2025, 4, 1),
            due_date=date(2025, 4, 10),
            doc_code="PINV",
            doc_no=1001,
            purchase_number="PI-PINV-1001",
            supplier_invoice_number="SUP-001",
            vendor=self.vendor,
            vendor_ledger=self.vendor_ledger,
            vendor_name="ABC Traders",
            vendor_gstin="03ABCDE1234F1Z5",
            status=PurchaseInvoiceHeader.Status.POSTED,
            grand_total=Decimal("1000.00"),
            created_by=self.user,
        )
        self.credit_note = PurchaseInvoiceHeader.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            doc_type=PurchaseInvoiceHeader.DocType.CREDIT_NOTE,
            ref_document=self.invoice,
            bill_date=date(2025, 4, 15),
            due_date=date(2025, 4, 15),
            doc_code="PCN",
            doc_no=1002,
            purchase_number="PI-PCN-1002",
            supplier_invoice_number="SUP-CN-001",
            vendor=self.vendor,
            vendor_ledger=self.vendor_ledger,
            vendor_name="ABC Traders",
            vendor_gstin="03ABCDE1234F1Z5",
            status=PurchaseInvoiceHeader.Status.POSTED,
            grand_total=Decimal("-100.00"),
            created_by=self.user,
        )

        self.invoice_item = VendorBillOpenItem.objects.create(
            header=self.invoice,
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor=self.vendor,
            vendor_ledger=self.vendor_ledger,
            doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
            bill_date=date(2025, 4, 1),
            due_date=date(2025, 4, 10),
            purchase_number="PI-PINV-1001",
            supplier_invoice_number="SUP-001",
            original_amount=Decimal("1000.00"),
            gross_amount=Decimal("1000.00"),
            net_payable_amount=Decimal("1000.00"),
            settled_amount=Decimal("200.00"),
            outstanding_amount=Decimal("800.00"),
            is_open=True,
        )
        self.credit_item = VendorBillOpenItem.objects.create(
            header=self.credit_note,
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor=self.vendor,
            vendor_ledger=self.vendor_ledger,
            doc_type=PurchaseInvoiceHeader.DocType.CREDIT_NOTE,
            bill_date=date(2025, 4, 15),
            due_date=date(2025, 4, 15),
            purchase_number="PI-PCN-1002",
            supplier_invoice_number="SUP-CN-001",
            original_amount=Decimal("-100.00"),
            gross_amount=Decimal("-100.00"),
            net_payable_amount=Decimal("-100.00"),
            settled_amount=Decimal("0.00"),
            outstanding_amount=Decimal("-100.00"),
            is_open=True,
        )
        self.advance = VendorAdvanceBalance.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor=self.vendor,
            vendor_ledger=self.vendor_ledger,
            source_type=VendorAdvanceBalance.SourceType.PAYMENT_ADVANCE,
            credit_date=date(2025, 4, 20),
            reference_no="ADV-001",
            original_amount=Decimal("50.00"),
            adjusted_amount=Decimal("0.00"),
            outstanding_amount=Decimal("50.00"),
            is_open=True,
        )
        self.payment = VendorSettlement.objects.create(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            vendor=self.vendor,
            vendor_ledger=self.vendor_ledger,
            settlement_type=VendorSettlement.SettlementType.PAYMENT,
            settlement_date=date(2025, 4, 5),
            reference_no="PAY-001",
            total_amount=Decimal("200.00"),
            status=VendorSettlement.Status.POSTED,
            posted_at=timezone.now(),
            posted_by=self.user,
        )
        VendorSettlementLine.objects.create(
            settlement=self.payment,
            open_item=self.invoice_item,
            amount=Decimal("200.00"),
            applied_amount_signed=Decimal("200.00"),
        )

    def test_vendor_outstanding_report_builds_vendor_totals_and_drilldowns(self):
        response = self.client.get(
            reverse("reports_api:vendor-outstanding-report"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "from_date": "2025-04-01",
                "to_date": "2025-04-30",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["report_code"], "vendor_outstanding")
        self.assertEqual(data["summary"]["vendor_count"], 1)
        self.assertEqual(data["totals"]["bill_amount"], "1000.00")
        self.assertEqual(data["totals"]["payment_amount"], "200.00")
        self.assertEqual(data["totals"]["credit_note"], "100.00")
        self.assertEqual(data["totals"]["net_outstanding"], "650.00")
        self.assertEqual(len(data["rows"]), 1)

        row = data["rows"][0]
        self.assertEqual(row["vendor_name"], "ABC Traders")
        self.assertEqual(row["opening_balance"], "0.00")
        self.assertEqual(row["bill_amount"], "1000.00")
        self.assertEqual(row["payment_amount"], "200.00")
        self.assertEqual(row["credit_note"], "100.00")
        self.assertEqual(row["net_outstanding"], "650.00")
        self.assertEqual(row["overdue_amount"], "650.00")
        self.assertEqual(row["unapplied_advance"], "50.00")
        self.assertEqual(row["drilldown_targets"], ["aging_summary", "aging_bill_list", "vendor_statement", "open_items", "payments"])
        self.assertEqual(row["_meta"]["drilldown"]["aging_summary"]["target"], "ap_aging")

    def test_ap_aging_report_supports_summary_and_invoice_views(self):
        summary_response = self.client.get(
            reverse("reports_api:ap-aging-report"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "as_of_date": "2025-04-30",
                "view": "summary",
            },
        )
        self.assertEqual(summary_response.status_code, 200)
        summary_data = summary_response.json()
        self.assertEqual(summary_data["report_code"], "ap_aging")
        self.assertEqual(summary_data["summary"]["vendor_count"], 1)
        self.assertEqual(summary_data["totals"]["outstanding"], "650.00")
        self.assertEqual(summary_data["totals"]["bucket_1_30"], "650.00")
        self.assertEqual(summary_data["totals"]["unapplied_advance"], "0.00")
        summary_row = summary_data["rows"][0]
        self.assertEqual(summary_row["outstanding"], "650.00")
        self.assertEqual(summary_row["bucket_1_30"], "650.00")
        self.assertEqual(summary_row["bucket_90_plus"], "0.00")
        self.assertEqual(summary_row["unapplied_advance"], "0.00")

        invoice_response = self.client.get(
            reverse("reports_api:ap-aging-report"),
            {
                "entity": self.entity.id,
                "entityfinid": self.entityfin.id,
                "subentity": self.subentity.id,
                "as_of_date": "2025-04-30",
                "view": "invoice",
            },
        )
        self.assertEqual(invoice_response.status_code, 200)
        invoice_data = invoice_response.json()
        self.assertEqual(invoice_data["view"], "invoice")
        self.assertEqual(invoice_data["totals"]["balance"], "650.00")
        self.assertEqual(len(invoice_data["rows"]), 1)
        row = invoice_data["rows"][0]
        self.assertEqual(row["bill_number"], "PI-PINV-1001")
        self.assertEqual(row["bill_amount"], "1000.00")
        self.assertEqual(row["paid_amount"], "200.00")
        self.assertEqual(row["credit_applied_fifo"], "150.00")
        self.assertEqual(row["balance"], "650.00")
        self.assertEqual(row["bucket_1_30"], "650.00")
        self.assertEqual(row["_meta"]["drilldown"]["bill"]["target"], "purchase_document_detail")
