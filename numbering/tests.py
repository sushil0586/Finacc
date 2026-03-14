from __future__ import annotations

from datetime import datetime, date

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from entity.models import Entity, EntityFinancialYear, SubEntity
from numbering.models import DocumentNumberSeries, DocumentType
from numbering.seeding import NumberingSeedService
from numbering.services import ensure_document_type, ensure_series
from numbering.services.document_number_service import DocumentNumberService


User = get_user_model()


class NumberingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="numuser", email="num@example.com", password="pass123")
        self.entity = Entity.objects.create(entityname="Demo Entity", address="Addr")
        self.subentity = SubEntity.objects.create(entity=self.entity, subentityname="Branch A", address="Branch Addr")
        self.entityfin = EntityFinancialYear.objects.create(
            entity=self.entity,
            desc="FY 2026-27",
            finstartyear=datetime(2026, 4, 1),
            finendyear=datetime(2027, 3, 31),
            createdby=self.user,
        )
        self.doc_type = ensure_document_type(
            module="testmod",
            doc_key="TEST_VOUCHER",
            name="Test Voucher",
            default_code="TV",
        )
        self.series, _ = ensure_series(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=None,
            doc_type_id=self.doc_type.id,
            doc_code="TV",
            prefix="TV",
            start=1,
            padding=4,
            reset="yearly",
        )

    def test_peek_preview_returns_current_number_without_increment(self):
        res = DocumentNumberService.peek_preview(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=None,
            doc_type_id=self.doc_type.id,
            doc_code="TV",
            on_date=date(2026, 4, 1),
        )
        self.assertEqual(res.doc_no, 1)
        self.assertEqual(res.display_no, "TV-TV-2026-0001")
        self.series.refresh_from_db()
        self.assertEqual(self.series.current_number, 1)

    def test_allocate_final_increments_counter(self):
        first = DocumentNumberService.allocate_final(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=None,
            doc_type_id=self.doc_type.id,
            doc_code="TV",
            on_date=date(2026, 4, 1),
        )
        second = DocumentNumberService.allocate_final(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=None,
            doc_type_id=self.doc_type.id,
            doc_code="TV",
            on_date=date(2026, 4, 1),
        )
        self.assertEqual(first.doc_no, 1)
        self.assertEqual(second.doc_no, 2)
        self.series.refresh_from_db()
        self.assertEqual(self.series.current_number, 3)

    def test_allocate_final_resets_yearly_series(self):
        self.series.current_number = 9
        self.series.last_reset_date = date(2025, 4, 1)
        self.series.save(update_fields=["current_number", "last_reset_date", "updated_at"])
        res = DocumentNumberService.allocate_final(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=None,
            doc_type_id=self.doc_type.id,
            doc_code="TV",
            on_date=date(2026, 4, 1),
        )
        self.assertEqual(res.doc_no, 1)
        self.series.refresh_from_db()
        self.assertEqual(self.series.current_number, 2)
        self.assertEqual(self.series.last_reset_date, date(2026, 4, 1))

    def test_series_are_scoped_by_subentity(self):
        sub_series, _ = ensure_series(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            doc_type_id=self.doc_type.id,
            doc_code="TV",
            prefix="TVB",
            start=11,
            padding=3,
            reset="yearly",
        )
        res_main = DocumentNumberService.peek_preview(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=None,
            doc_type_id=self.doc_type.id,
            doc_code="TV",
            on_date=date(2026, 4, 1),
        )
        res_sub = DocumentNumberService.peek_preview(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            doc_type_id=self.doc_type.id,
            doc_code="TV",
            on_date=date(2026, 4, 1),
        )
        self.assertEqual(res_main.doc_no, 1)
        self.assertEqual(res_sub.doc_no, 11)
        self.assertEqual(sub_series.current_number, 11)

    def test_ensure_document_type_and_series_are_idempotent(self):
        dt2 = ensure_document_type(module="testmod", doc_key="TEST_VOUCHER", name="Test Voucher", default_code="TV")
        series2, created = ensure_series(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=None,
            doc_type_id=self.doc_type.id,
            doc_code="TV",
            prefix="TV",
            start=1,
            padding=4,
            reset="yearly",
        )
        self.assertEqual(dt2.id, self.doc_type.id)
        self.assertEqual(series2.id, self.series.id)
        self.assertFalse(created)

    def test_seed_doc_sequences_command_uses_current_models(self):
        call_command(
            "seed_doc_sequences",
            entity=self.entity.id,
            entityfinid=self.entityfin.id,
            doc_code="JV",
            start=5,
            padding=4,
        )
        dt = DocumentType.objects.get(module="vouchers", doc_key="JOURNAL_VOUCHER")
        series = DocumentNumberSeries.objects.get(
            entity=self.entity,
            entityfinid=self.entityfin,
            subentity=None,
            doc_type=dt,
            doc_code="JV",
        )
        self.assertEqual(series.current_number, 5)
        self.assertEqual(series.prefix, "JV")

    def test_numbering_seed_service_creates_document_type_and_series_together(self):
        result = NumberingSeedService.seed_document(
            entity_id=self.entity.id,
            entityfinid_id=self.entityfin.id,
            subentity_id=self.subentity.id,
            module="sales",
            doc_key="SALES_CREDIT_NOTE",
            name="Sales Credit Note",
            default_code="SCN",
            prefix="SCN",
            start=7,
            padding=4,
            reset="yearly",
        )

        dt = DocumentType.objects.get(id=result["doc_type_id"])
        series = DocumentNumberSeries.objects.get(id=result["series_id"])
        self.assertEqual(dt.module, "sales")
        self.assertEqual(dt.doc_key, "SALES_CREDIT_NOTE")
        self.assertEqual(series.doc_code, "SCN")
        self.assertEqual(series.current_number, 7)
        self.assertEqual(series.subentity_id, self.subentity.id)
