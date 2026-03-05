from types import SimpleNamespace
from decimal import Decimal

from django.test import SimpleTestCase

from sales.models import SalesInvoiceHeader
from sales.services.sales_invoice_service import SalesInvoiceService


class SalesInvoiceServiceUnitTests(SimpleTestCase):
    def test_reverse_move_type(self):
        self.assertEqual(SalesInvoiceService._reverse_move_type("IN"), "OUT")
        self.assertEqual(SalesInvoiceService._reverse_move_type("OUT"), "IN")
        self.assertEqual(SalesInvoiceService._reverse_move_type("ADJ"), "REV")

    def test_recompute_settlement_fields_open(self):
        header = SimpleNamespace(
            grand_total=Decimal("1000.00"),
            tcs_amount=Decimal("20.00"),
            settled_amount=Decimal("0.00"),
            settlement_status=None,
            outstanding_amount=None,
        )
        SalesInvoiceService.recompute_settlement_fields(header=header)
        self.assertEqual(header.outstanding_amount, Decimal("1020.00"))
        self.assertEqual(header.settlement_status, int(SalesInvoiceHeader.SettlementStatus.OPEN))

    def test_recompute_settlement_fields_partial(self):
        header = SimpleNamespace(
            grand_total=Decimal("1000.00"),
            tcs_amount=Decimal("20.00"),
            settled_amount=Decimal("500.00"),
            settlement_status=None,
            outstanding_amount=None,
        )
        SalesInvoiceService.recompute_settlement_fields(header=header)
        self.assertEqual(header.outstanding_amount, Decimal("520.00"))
        self.assertEqual(header.settlement_status, int(SalesInvoiceHeader.SettlementStatus.PARTIAL))

    def test_recompute_settlement_fields_settled_caps_to_gross(self):
        header = SimpleNamespace(
            grand_total=Decimal("1000.00"),
            tcs_amount=Decimal("20.00"),
            settled_amount=Decimal("2000.00"),
            settlement_status=None,
            outstanding_amount=None,
        )
        SalesInvoiceService.recompute_settlement_fields(header=header)
        self.assertEqual(header.settled_amount, Decimal("1020.00"))
        self.assertEqual(header.outstanding_amount, Decimal("0.00"))
        self.assertEqual(header.settlement_status, int(SalesInvoiceHeader.SettlementStatus.SETTLED))

    def test_validate_doc_linkage_cn_requires_original(self):
        with self.assertRaisesMessage(ValueError, "original_invoice is required"):
            SalesInvoiceService._validate_doc_linkage(
                doc_type=int(SalesInvoiceHeader.DocType.CREDIT_NOTE),
                original_invoice=None,
                entity_id=1,
                entityfinid_id=1,
                subentity_id=None,
                customer_id=10,
            )

    def test_validate_doc_linkage_tax_invoice_disallows_original(self):
        original = SimpleNamespace(entity_id=1, entityfinid_id=1, subentity_id=None, customer_id=10)
        with self.assertRaisesMessage(ValueError, "allowed only for Credit Note / Debit Note"):
            SalesInvoiceService._validate_doc_linkage(
                doc_type=int(SalesInvoiceHeader.DocType.TAX_INVOICE),
                original_invoice=original,
                entity_id=1,
                entityfinid_id=1,
                subentity_id=None,
                customer_id=10,
            )
