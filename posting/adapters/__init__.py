from django.apps import apps

from .payment_voucher import PaymentVoucherPostingAdapter, PaymentVoucherPostingConfig
from .purchase_invoice import PurchaseInvoicePostingAdapter, PurchaseInvoicePostingConfig
from .voucher import VoucherPostingAdapter, VoucherPostingConfig

if apps.is_installed("payroll"):
    from .payroll_adapter import PayrollPostingAdapter
else:
    PayrollPostingAdapter = None

__all__ = [
    "PaymentVoucherPostingAdapter",
    "PaymentVoucherPostingConfig",
    "PayrollPostingAdapter",
    "PurchaseInvoicePostingAdapter",
    "PurchaseInvoicePostingConfig",
    "VoucherPostingAdapter",
    "VoucherPostingConfig",
]
