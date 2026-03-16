from __future__ import annotations

from datetime import datetime
from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity, UnitType
from financial.models import Ledger, account, accountHead, accounttype
from geography.models import City, Country, District, State
from purchase.models import PurchaseInvoiceHeader, PurchaseInvoiceLine
from purchase.models.purchase_ap import VendorBillOpenItem


@override_settings(ROOT_URLCONF="FA.urls", AUTH_PASSWORD_VALIDATORS=[])
class PurchaseRegisterAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        suffix = uuid4().hex[:8]
        self.user = User.objects.create_user(
            username=f"purchase-report-user-{suffix}",
            email=f"purchase-report-{suffix}@example.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse("reports_api:purchase-register")

        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state = State.objects.create(statename="Maharashtra", statecode="27", country=self.country)
        self.other_state = State.objects.create(statename="Karnataka", statecode="29", country=self.country)
        self.district = District.objects.create(districtname="District", districtcode="DT", state=self.state)
        self.city = City.objects.create(cityname="Mumbai", citycode="MUM", pincode="400001", distt=self.district)
        self.unit_type = UnitType.objects.create(UnitName="Business", UnitDesc="Business")
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")

        self.entity = Entity.objects.create(
            entityname="Finacc Purchase Entity",
            legalname="Finacc Purchase Entity Pvt Ltd",
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
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Main Branch", address="Main Branch")
        self.other_subentity = SubEntity.objects.create(entity=self.entity, subentityname="Other Branch", address="Other Branch")

        fy_start = timezone.make_aware(datetime(2025, 4, 1))
        fy_end = timezone.make_aware(datetime(2026, 3, 31))
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2025-26",
            finstartyear=fy_start,
            finendyear=fy_end,
            createdby=self.user,
        )

        self.other_entity = Entity.objects.create(
            entityname="Other Entity",
            legalname="Other Entity Pvt Ltd",
            unitType=self.unit_type,
            GstRegitrationType=self.gst_type,
            address="Address 2",
            phoneoffice="8888888888",
            phoneresidence="8888888887",
            country=self.country,
            state=self.state,
            district=self.district,
            city=self.city,
            createdby=self.user,
        )
        self.other_entityfin = EntityFinancialYear.objects.create(
            entity=self.other_entity,
            desc="FY 2025-26",
            finstartyear=fy_start,
            finendyear=fy_end,
            createdby=self.user,
        )
        self.other_entity_subentity = SubEntity.objects.create(
            entity=self.other_entity,
            subentityname="Other Entity Branch",
            address="Other",
        )

        self.acc_type = accounttype.objects.create(
            entity=self.entity,
            accounttypename="Sundry",
            accounttypecode="S100",
            createdby=self.user,
        )
        self.other_acc_type = accounttype.objects.create(
            entity=self.other_entity,
            accounttypename="Sundry",
            accounttypecode="S200",
            createdby=self.user,
        )
        self.vendor_head = accountHead.objects.create(
            entity=self.entity,
            name="Sundry Creditors",
            code=200,
            balanceType="Credit",
            drcreffect="Credit",
            accounttype=self.acc_type,
            createdby=self.user,
        )
        self.other_vendor_head = accountHead.objects.create(
            entity=self.other_entity,
            name="Sundry Creditors",
            code=201,
            balanceType="Credit",
            drcreffect="Credit",
            accounttype=self.other_acc_type,
            createdby=self.user,
        )

        self.vendor_alpha = self._create_vendor(
            name="Alpha Traders",
            gstin="27ABCDE1234F1Z5",
            accountcode=4001,
        )
        self.vendor_beta = self._create_vendor(
            name="Beta Suppliers",
            gstin="27BBBBB1234B1Z5",
            accountcode=4002,
        )
        self.other_entity_vendor = self._create_vendor(
            name="Other Vendor",
            gstin="29CCCCC1234C1Z5",
            accountcode=9001,
            entity=self.other_entity,
            account_head=self.other_vendor_head,
        )

        self.base_params = {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.subentity.id,
        }
        self.doc_no_seq = 1

    def _create_vendor(self, *, name, gstin, accountcode, entity=None, account_head=None):
        entity = entity or self.entity
        account_head = account_head or self.vendor_head
        ledger = Ledger.objects.create(
            entity=entity,
            ledger_code=accountcode,
            name=name,
            accounthead=account_head,
            createdby=self.user,
        )
        return account.objects.create(
            entity=entity,
            ledger=ledger,
            accounthead=account_head,
            accountname=name,
            accountcode=accountcode,
            gstno=gstin,
            partytype="Vendor",
            createdby=self.user,
        )

    def _create_purchase_document(
        self,
        *,
        vendor=None,
        entity=None,
        entityfin=None,
        subentity=None,
        doc_type=PurchaseInvoiceHeader.DocType.TAX_INVOICE,
        status=PurchaseInvoiceHeader.Status.POSTED,
        bill_date="2025-04-05",
        posting_date="2025-04-05",
        purchase_number=None,
        supplier_invoice_number=None,
        supplier_invoice_date="2025-04-04",
        taxable="100.00",
        cgst="9.00",
        sgst="9.00",
        igst="0.00",
        cess="0.00",
        round_off="0.00",
        grand_total="118.00",
        reverse_charge=False,
        ref_document=None,
        discount_amounts=None,
        vendor_name=None,
        vendor_gstin=None,
    ):
        entity = entity or self.entity
        entityfin = entityfin or self.entityfin
        subentity = subentity if subentity is not None else self.subentity
        vendor = vendor or self.vendor_alpha
        discount_amounts = discount_amounts or []

        doc_code_map = {
            PurchaseInvoiceHeader.DocType.TAX_INVOICE: "PINV",
            PurchaseInvoiceHeader.DocType.CREDIT_NOTE: "PCN",
            PurchaseInvoiceHeader.DocType.DEBIT_NOTE: "PDN",
        }
        doc_no = self.doc_no_seq
        self.doc_no_seq += 1

        header = PurchaseInvoiceHeader.objects.create(
            entity=entity,
            entityfinid=entityfin,
            subentity=subentity,
            doc_type=doc_type,
            status=status,
            bill_date=bill_date,
            posting_date=posting_date,
            doc_code=doc_code_map[doc_type],
            doc_no=doc_no,
            purchase_number=purchase_number or f"{doc_code_map[doc_type]}-{doc_no:04d}",
            supplier_invoice_number=supplier_invoice_number or f"SUP-{doc_no:04d}",
            supplier_invoice_date=supplier_invoice_date,
            vendor=vendor,
            vendor_ledger=vendor.ledger,
            vendor_name=vendor_name or vendor.accountname,
            vendor_gstin=vendor_gstin or vendor.gstno,
            place_of_supply_state=self.state,
            supply_category=PurchaseInvoiceHeader.SupplyCategory.DOMESTIC,
            is_reverse_charge=reverse_charge,
            total_taxable=Decimal(taxable),
            total_cgst=Decimal(cgst),
            total_sgst=Decimal(sgst),
            total_igst=Decimal(igst),
            total_cess=Decimal(cess),
            total_gst=Decimal(cgst) + Decimal(sgst) + Decimal(igst) + Decimal(cess),
            round_off=Decimal(round_off),
            grand_total=Decimal(grand_total),
            ref_document=ref_document,
            created_by=self.user,
        )

        for idx, discount in enumerate(discount_amounts, start=1):
            PurchaseInvoiceLine.objects.create(
                header=header,
                line_no=idx,
                discount_amount=Decimal(discount),
                qty=Decimal("1.0000"),
                rate=Decimal("10.00"),
                taxable_value=Decimal("10.00"),
                line_total=Decimal("10.00"),
            )
        return header

    def _create_open_item(self, header, *, amount=None):
        amount = Decimal(amount or header.grand_total)
        return VendorBillOpenItem.objects.create(
            header=header,
            entity=header.entity,
            entityfinid=header.entityfinid,
            subentity=header.subentity,
            vendor=header.vendor,
            vendor_ledger=header.vendor_ledger,
            doc_type=header.doc_type,
            bill_date=header.bill_date,
            due_date=header.due_date,
            purchase_number=header.purchase_number,
            supplier_invoice_number=header.supplier_invoice_number,
            original_amount=amount,
            gross_amount=amount,
            net_payable_amount=amount,
            settled_amount=Decimal("0.00"),
            outstanding_amount=amount,
            is_open=True,
        )

    def _get(self, **params):
        query = {**self.base_params, **params}
        return self.client.get(self.url, query, format="json")

    def _money(self, value):
        return Decimal(str(value))

    def test_default_status_filtering(self):
        self._create_purchase_document(status=PurchaseInvoiceHeader.Status.DRAFT, purchase_number="DRAFT-001")
        confirmed = self._create_purchase_document(status=PurchaseInvoiceHeader.Status.CONFIRMED, purchase_number="CONF-001")
        posted = self._create_purchase_document(status=PurchaseInvoiceHeader.Status.POSTED, purchase_number="POST-001")
        self._create_purchase_document(status=PurchaseInvoiceHeader.Status.CANCELLED, purchase_number="CANC-001")
        self._create_purchase_document(
            entity=self.other_entity,
            entityfin=self.other_entityfin,
            subentity=self.other_entity_subentity,
            vendor=self.other_entity_vendor,
            status=PurchaseInvoiceHeader.Status.POSTED,
            purchase_number="OTHER-ENTITY-001",
        )

        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(
            {row["purchase_number"] for row in response.data["results"]},
            {confirmed.purchase_number, posted.purchase_number},
        )

    def test_explicit_status_override(self):
        draft = self._create_purchase_document(status=PurchaseInvoiceHeader.Status.DRAFT, purchase_number="DRAFT-OVERRIDE")
        self._create_purchase_document(status=PurchaseInvoiceHeader.Status.CONFIRMED, purchase_number="CONF-OVERRIDE")
        cancelled = self._create_purchase_document(status=PurchaseInvoiceHeader.Status.CANCELLED, purchase_number="CANC-OVERRIDE")

        response = self._get(status=f"{PurchaseInvoiceHeader.Status.DRAFT},{PurchaseInvoiceHeader.Status.CANCELLED}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(
            {row["purchase_number"] for row in response.data["results"]},
            {draft.purchase_number, cancelled.purchase_number},
        )

    def test_cancelled_documents_are_listed_but_zero_in_totals(self):
        active = self._create_purchase_document(
            status=PurchaseInvoiceHeader.Status.POSTED,
            purchase_number="ACTIVE-001",
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            grand_total="118.00",
        )
        cancelled = self._create_purchase_document(
            status=PurchaseInvoiceHeader.Status.CANCELLED,
            purchase_number="CANCELLED-001",
            taxable="999.00",
            cgst="99.00",
            sgst="99.00",
            grand_total="1197.00",
        )

        response = self._get(status=f"{PurchaseInvoiceHeader.Status.POSTED},{PurchaseInvoiceHeader.Status.CANCELLED}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(self._money(response.data["totals"]["grand_total"]), Decimal("118.00"))

        cancelled_row = next(row for row in response.data["results"] if row["purchase_number"] == cancelled.purchase_number)
        active_row = next(row for row in response.data["results"] if row["purchase_number"] == active.purchase_number)
        self.assertEqual(self._money(cancelled_row["grand_total"]), Decimal("0.00"))
        self.assertEqual(self._money(cancelled_row["taxable_amount"]), Decimal("0.00"))
        self.assertFalse(cancelled_row["affects_totals"])
        self.assertEqual(self._money(active_row["grand_total"]), Decimal("118.00"))

    def test_credit_note_negative_effect(self):
        invoice = self._create_purchase_document(
            status=PurchaseInvoiceHeader.Status.POSTED,
            purchase_number="INV-BASE-001",
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            grand_total="118.00",
        )
        credit = self._create_purchase_document(
            doc_type=PurchaseInvoiceHeader.DocType.CREDIT_NOTE,
            ref_document=invoice,
            status=PurchaseInvoiceHeader.Status.POSTED,
            purchase_number="CRN-001",
            taxable="40.00",
            cgst="3.60",
            sgst="3.60",
            grand_total="47.20",
        )

        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._money(response.data["totals"]["grand_total"]), Decimal("70.80"))
        credit_row = next(row for row in response.data["results"] if row["purchase_number"] == credit.purchase_number)
        self.assertEqual(self._money(credit_row["grand_total"]), Decimal("-47.20"))
        self.assertEqual(self._money(credit_row["taxable_amount"]), Decimal("-40.00"))

    def test_debit_note_positive_effect(self):
        invoice = self._create_purchase_document(
            status=PurchaseInvoiceHeader.Status.POSTED,
            purchase_number="INV-BASE-002",
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            grand_total="118.00",
        )
        self._create_purchase_document(
            doc_type=PurchaseInvoiceHeader.DocType.DEBIT_NOTE,
            ref_document=invoice,
            status=PurchaseInvoiceHeader.Status.POSTED,
            purchase_number="DBN-001",
            taxable="20.00",
            cgst="1.80",
            sgst="1.80",
            grand_total="23.60",
        )

        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._money(response.data["totals"]["grand_total"]), Decimal("141.60"))

    def test_bill_date_filtering(self):
        in_range = self._create_purchase_document(
            purchase_number="BILL-RANGE-IN",
            bill_date="2025-04-15",
            posting_date="2025-04-16",
        )
        self._create_purchase_document(
            purchase_number="BILL-RANGE-OUT",
            bill_date="2025-05-01",
            posting_date="2025-05-01",
        )

        response = self._get(from_date="2025-04-10", to_date="2025-04-30")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["purchase_number"], in_range.purchase_number)

    def test_posting_date_filtering(self):
        in_range = self._create_purchase_document(
            purchase_number="POST-RANGE-IN",
            bill_date="2025-04-05",
            posting_date="2025-04-20",
        )
        self._create_purchase_document(
            purchase_number="POST-RANGE-OUT",
            bill_date="2025-04-05",
            posting_date="2025-05-02",
        )

        response = self._get(posting_from_date="2025-04-18", posting_to_date="2025-04-25")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["purchase_number"], in_range.purchase_number)

    def test_vendor_filter(self):
        alpha = self._create_purchase_document(vendor=self.vendor_alpha, purchase_number="ALPHA-001")
        self._create_purchase_document(vendor=self.vendor_beta, purchase_number="BETA-001")

        response = self._get(vendor=self.vendor_alpha.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["purchase_number"], alpha.purchase_number)

    def test_supplier_gstin_filter(self):
        match = self._create_purchase_document(vendor=self.vendor_alpha, purchase_number="GSTIN-001")
        self._create_purchase_document(vendor=self.vendor_beta, purchase_number="GSTIN-002")

        response = self._get(supplier_gstin="1234F1Z5")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["purchase_number"], match.purchase_number)

    def test_search_by_purchase_number(self):
        match = self._create_purchase_document(purchase_number="PINV-SRCH-001")
        self._create_purchase_document(purchase_number="PINV-OTHER-001")

        response = self._get(search="SRCH-001")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["purchase_number"], match.purchase_number)

    def test_search_by_supplier_invoice_number(self):
        match = self._create_purchase_document(
            purchase_number="SUPINV-TEST-001",
            supplier_invoice_number="VEND-7788",
        )
        self._create_purchase_document(
            purchase_number="SUPINV-TEST-002",
            supplier_invoice_number="VEND-8899",
        )

        response = self._get(search="7788")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["purchase_number"], match.purchase_number)

    def test_search_by_vendor_name(self):
        match = self._create_purchase_document(vendor=self.vendor_alpha, purchase_number="VENDOR-NAME-001")
        self._create_purchase_document(vendor=self.vendor_beta, purchase_number="VENDOR-NAME-002")

        response = self._get(search="Alpha")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["purchase_number"], match.purchase_number)

    def test_numeric_search_by_doc_no(self):
        match = self._create_purchase_document(purchase_number="DOCNO-001")
        self._create_purchase_document(purchase_number="DOCNO-002")

        response = self._get(search=str(match.doc_no))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["purchase_number"], match.purchase_number)

    def test_totals_are_based_on_all_filtered_rows_not_page_slice(self):
        first = self._create_purchase_document(
            purchase_number="PAGE-001",
            grand_total="118.00",
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
        )
        second = self._create_purchase_document(
            purchase_number="PAGE-002",
            grand_total="236.00",
            taxable="200.00",
            cgst="18.00",
            sgst="18.00",
            bill_date="2025-04-06",
            posting_date="2025-04-06",
        )

        response = self._get(page_size=1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(self._money(response.data["totals"]["grand_total"]), Decimal("354.00"))
        self.assertEqual(self._money(response.data["totals"]["taxable_amount"]), Decimal("300.00"))
        self.assertIn(response.data["results"][0]["purchase_number"], {first.purchase_number, second.purchase_number})

    def test_line_level_discount_subquery_does_not_duplicate_header_rows(self):
        header = self._create_purchase_document(
            purchase_number="DISC-SUBQ-001",
            taxable="100.00",
            cgst="9.00",
            sgst="9.00",
            grand_total="118.00",
            discount_amounts=["10.00", "15.00"],
        )

        response = self._get(search="DISC-SUBQ-001")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["purchase_number"], header.purchase_number)
        self.assertEqual(self._money(response.data["results"][0]["discount_total"]), Decimal("25.00"))
        self.assertEqual(self._money(response.data["totals"]["discount_total"]), Decimal("25.00"))


    def test_outstanding_amount_is_optional_and_derived_from_open_item(self):
        header = self._create_purchase_document(purchase_number="OPEN-ITEM-001", grand_total="118.00")
        self._create_open_item(header, amount="55.00")

        response = self._get(search="OPEN-ITEM-001")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("outstanding_amount", response.data["results"][0])

        response = self._get(search="OPEN-ITEM-001", include_outstanding="true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._money(response.data["results"][0]["outstanding_amount"]), Decimal("55.00"))
        self.assertEqual(self._money(response.data["totals"]["outstanding_amount"]), Decimal("55.00"))

    def test_posting_summary_block_is_optional(self):
        self._create_purchase_document(status=PurchaseInvoiceHeader.Status.POSTED, purchase_number="POSTSUM-001", grand_total="100.00")
        self._create_purchase_document(status=PurchaseInvoiceHeader.Status.CONFIRMED, purchase_number="POSTSUM-002", grand_total="75.00")

        response = self._get(include_posting_summary="true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["posting_summary"]["posted_count"], 1)
        self.assertEqual(response.data["posting_summary"]["unposted_count"], 1)

    def test_purchase_register_exports_return_expected_formats(self):
        header = self._create_purchase_document(purchase_number="EXP-001")
        self._create_open_item(header, amount="25.00")
        params = {**self.base_params, "include_outstanding": "true"}
        checks = [
            ("reports_api:purchase-register-csv", "text/csv", b"Bill Date"),
            ("reports_api:purchase-register-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"PK"),
            ("reports_api:purchase-register-pdf", "application/pdf", b"%PDF"),
            ("reports_api:purchase-register-print", "application/pdf", b"%PDF"),
        ]
        for route_name, content_type, prefix in checks:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name), params)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response["Content-Type"].startswith(content_type))
                self.assertTrue(bytes(response.content).startswith(prefix))

    def test_purchase_register_meta_is_config_driven(self):
        header = self._create_purchase_document(purchase_number="META-001")
        self._create_open_item(header, amount="42.00")

        response = self._get(
            search="META-001",
            include_outstanding="true",
            include_posting_summary="true",
            include_payables_drilldowns="true",
        )
        self.assertEqual(response.status_code, 200)
        meta = response.data["_meta"]
        self.assertTrue(meta["configuration_driven"])
        self.assertIn("outstanding_amount", meta["effective_columns"])
        self.assertIn("posting_summary", meta["enabled_summary_blocks"])
        self.assertIn("purchase_document_detail", {row["target"] for row in meta["drilldown_targets"]})
        related_codes = {row["code"] for row in meta["related_reports"]}
        self.assertIn("vendor_ledger_statement", related_codes)
        self.assertIn("payables_close_pack", related_codes)

    def test_purchase_register_csv_header_tracks_optional_outstanding_column(self):
        header = self._create_purchase_document(purchase_number="CSVHDR-001")
        self._create_open_item(header, amount="33.00")

        response = self.client.get(reverse("reports_api:purchase-register-csv"), self.base_params)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Outstanding Amount", response.content.decode("utf-8").splitlines()[0])

        response = self.client.get(
            reverse("reports_api:purchase-register-csv"),
            {**self.base_params, "include_outstanding": "true"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Outstanding Amount", response.content.decode("utf-8").splitlines()[0])


    def test_purchase_register_supports_date_aliases_and_standardized_response_fields(self):
        header = self._create_purchase_document(purchase_number="ALIAS-001")
        self._create_open_item(header, amount="55.00")
        response = self.client.get(
            reverse("reports_api:purchase-register"),
            {**self.base_params, "date_from": "2025-04-01", "date_to": "2025-04-30"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.data
        self.assertEqual(payload["applied_filters"]["from_date"], date(2025, 4, 1))
        self.assertEqual(payload["applied_filters"]["to_date"], date(2025, 4, 30))
        self.assertIn("rows", payload)
        self.assertIn("pagination", payload)
        self.assertIn("available_exports", payload)
        self.assertIn("available_drilldowns", payload)

    def test_purchase_register_meta_is_frontend_complete(self):
        response = self._get(include_outstanding="true")
        self.assertEqual(response.status_code, 200)
        meta = response.data["_meta"]
        self.assertIn("supported_filters", meta)
        self.assertIn("pagination_mode", meta)
        self.assertIn("available_exports", meta)
        self.assertIn("available_drilldowns", meta)
        self.assertIn("endpoint", meta)
