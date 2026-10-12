from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from entity.models import EntityFinancialYear, SubEntity
from financial.models import AccountAddress, account
from payments.models.payment_core import (
    PaymentVoucherAdjustment,
    PaymentVoucherAdvanceAdjustment,
    PaymentVoucherAllocation,
    PaymentVoucherHeader,
)
from posting.models import EntityStaticAccountMap, Entry, JournalLine, PostingBatch
from purchase.models.purchase_ap import VendorBillOpenItem, VendorSettlement, VendorSettlementLine
from purchase.models.purchase_core import PurchaseInvoiceHeader, PurchaseInvoiceLine, PurchaseTaxSummary
from receipts.models.receipt_core import (
    ReceiptVoucherAdjustment,
    ReceiptVoucherAdvanceAdjustment,
    ReceiptVoucherAllocation,
    ReceiptVoucherHeader,
)
from sales.models.sales_ar import CustomerBillOpenItem, CustomerSettlement, CustomerSettlementLine
from sales.models.sales_core import SalesInvoiceHeader, SalesInvoiceLine, SalesTaxSummary

from helpers.utils.meta_cache import REPORTS_META_NAMESPACES, bump_meta_namespaces
from reports.services.report_response_cache import bump_report_response_cache_generation


@receiver([post_save, post_delete], sender=account)
@receiver([post_save, post_delete], sender=AccountAddress)
@receiver([post_save, post_delete], sender=SubEntity)
@receiver([post_save, post_delete], sender=EntityFinancialYear)
@receiver([post_save, post_delete], sender=EntityStaticAccountMap)
def invalidate_reports_meta_cache_on_shared_master_change(sender, **kwargs):
    bump_meta_namespaces(REPORTS_META_NAMESPACES)


@receiver([post_save, post_delete], sender=SalesInvoiceHeader)
@receiver([post_save, post_delete], sender=SalesInvoiceLine)
@receiver([post_save, post_delete], sender=SalesTaxSummary)
@receiver([post_save, post_delete], sender=CustomerBillOpenItem)
@receiver([post_save, post_delete], sender=CustomerSettlement)
@receiver([post_save, post_delete], sender=CustomerSettlementLine)
@receiver([post_save, post_delete], sender=PurchaseInvoiceHeader)
@receiver([post_save, post_delete], sender=PurchaseInvoiceLine)
@receiver([post_save, post_delete], sender=PurchaseTaxSummary)
@receiver([post_save, post_delete], sender=VendorBillOpenItem)
@receiver([post_save, post_delete], sender=VendorSettlement)
@receiver([post_save, post_delete], sender=VendorSettlementLine)
@receiver([post_save, post_delete], sender=PaymentVoucherHeader)
@receiver([post_save, post_delete], sender=PaymentVoucherAllocation)
@receiver([post_save, post_delete], sender=PaymentVoucherAdjustment)
@receiver([post_save, post_delete], sender=PaymentVoucherAdvanceAdjustment)
@receiver([post_save, post_delete], sender=ReceiptVoucherHeader)
@receiver([post_save, post_delete], sender=ReceiptVoucherAllocation)
@receiver([post_save, post_delete], sender=ReceiptVoucherAdjustment)
@receiver([post_save, post_delete], sender=ReceiptVoucherAdvanceAdjustment)
@receiver([post_save, post_delete], sender=PostingBatch)
@receiver([post_save, post_delete], sender=Entry)
@receiver([post_save, post_delete], sender=JournalLine)
def invalidate_report_response_cache_on_financial_change(sender, **kwargs):
    bump_report_response_cache_generation(reason=sender._meta.label)
