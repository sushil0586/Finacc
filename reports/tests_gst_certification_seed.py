from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from Authentication.models import User
from entity.models import Entity, EntityFinancialYear, GstRegistrationType, SubEntity
from purchase.models import PurchaseInvoiceHeader
from reports.gstr1.services.report import Gstr1ReportService
from reports.gstr3b.services import Gstr3bSummaryService
from sales.models import SalesInvoiceHeader


class GstCertificationMatrixSeedTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="gst-cert-seed",
            email="gst-cert-seed@example.com",
            password="pass123",
        )
        gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="GST Certification Entity",
            legalname="GST Certification Entity Pvt Ltd",
            GstRegitrationType=gst_type,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(
            entity=self.entity,
            subentityname="Head Office",
            is_head_office=True,
        )
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=timezone.make_aware(datetime(2026, 4, 1)),
            finendyear=timezone.make_aware(datetime(2027, 3, 31)),
            createdby=self.user,
        )

    def test_seed_creates_idempotent_gstr1_and_gstr3b_gap_documents(self):
        self._run_seed()
        self._run_seed()

        sales_docs = SalesInvoiceHeader.objects.filter(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            legacy_source_system="gst_certification_matrix",
        )
        purchase_docs = PurchaseInvoiceHeader.objects.filter(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=self.subentity,
            legacy_source_system="gst_certification_matrix",
        )
        self.assertEqual(sales_docs.count(), 4)
        self.assertEqual(purchase_docs.count(), 1)

        gstr1_scope = Gstr1ReportService().build_scope(self._scope_params())
        gstr1_summary = Gstr1ReportService().summary(gstr1_scope)
        sections = {row["section"]: row for row in gstr1_summary["sections"]}
        self.assertEqual(sections["CDNR"]["document_count"], 2)
        self.assertEqual(Decimal(sections["CDNR"]["taxable_amount"]), Decimal("50.00"))
        self.assertEqual(sections["EXP"]["document_count"], 1)
        self.assertEqual(Decimal(sections["EXP"]["taxable_amount"]), Decimal("500.00"))

        gstr3b_scope = Gstr3bSummaryService().build_scope(self._scope_params())
        gstr3b_summary = Gstr3bSummaryService().build(gstr3b_scope)
        section_31 = gstr3b_summary["section_3_1"]
        self.assertEqual(
            Decimal(section_31["outward_zero_rated_supplies"]["taxable_value"]),
            Decimal("500.00"),
        )
        self.assertEqual(
            Decimal(section_31["inward_supplies_reverse_charge"]["taxable_value"]),
            Decimal("1000.00"),
        )
        self.assertEqual(
            Decimal(section_31["inward_supplies_reverse_charge"]["igst"]),
            Decimal("180.00"),
        )

    def _run_seed(self):
        call_command(
            "seed_gst_certification_matrix",
            entity_id=self.entity.id,
            entityfin_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            gstin="29ABCDE1234F1Z5",
            return_period="2026-09",
            user_email=self.user.email,
            confirm_seed=True,
            stdout=StringIO(),
        )

    def _scope_params(self):
        return {
            "entity": self.entity.id,
            "entityfinid": self.entityfin.id,
            "subentity": self.subentity.id,
            "from_date": "2026-09-01",
            "to_date": "2026-09-30",
            "month": 9,
            "year": 2026,
        }
