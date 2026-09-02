from types import SimpleNamespace

from django.test import SimpleTestCase
from rest_framework import serializers

from helpers.utils.document_scope import DOCUMENT_BRANCH_IMMUTABLE_MESSAGE
from payments.serializers.payment_voucher import PaymentVoucherHeaderSerializer
from purchase.serializers.purchase_invoice import PurchaseInvoiceHeaderSerializer
from receipts.serializers.receipt_voucher import ReceiptVoucherHeaderSerializer
from sales.serializers.sales_invoice_serializers import SalesInvoiceHeaderSerializer
from vouchers.models import VoucherHeader
from vouchers.serializers.voucher import VoucherWriteSerializer


class DocumentBranchImmutabilityTests(SimpleTestCase):
    def _assert_serializer_blocks_branch_change(self, serializer):
        with self.assertRaises(serializers.ValidationError) as exc:
            serializer.validate({"subentity": SimpleNamespace(pk=31)})
        self.assertIn(DOCUMENT_BRANCH_IMMUTABLE_MESSAGE, str(exc.exception.detail))

    def test_purchase_invoice_serializer_blocks_saved_branch_change(self):
        serializer = PurchaseInvoiceHeaderSerializer(instance=SimpleNamespace(subentity_id=30))

        self._assert_serializer_blocks_branch_change(serializer)

    def test_sales_invoice_serializer_blocks_saved_branch_change(self):
        serializer = SalesInvoiceHeaderSerializer(instance=SimpleNamespace(subentity_id=30))

        self._assert_serializer_blocks_branch_change(serializer)

    def test_receipt_voucher_serializer_blocks_saved_branch_change(self):
        serializer = ReceiptVoucherHeaderSerializer(instance=SimpleNamespace(subentity_id=30))

        self._assert_serializer_blocks_branch_change(serializer)

    def test_payment_voucher_serializer_blocks_saved_branch_change(self):
        serializer = PaymentVoucherHeaderSerializer(instance=SimpleNamespace(subentity_id=30))

        self._assert_serializer_blocks_branch_change(serializer)

    def test_cash_bank_and_journal_voucher_serializer_blocks_saved_branch_change(self):
        for voucher_type in (
            VoucherHeader.VoucherType.CASH,
            VoucherHeader.VoucherType.BANK,
            VoucherHeader.VoucherType.JOURNAL,
        ):
            with self.subTest(voucher_type=voucher_type):
                serializer = VoucherWriteSerializer(
                    instance=SimpleNamespace(
                        subentity_id=30,
                        voucher_type=voucher_type,
                    )
                )

                self._assert_serializer_blocks_branch_change(serializer)
