from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Case, CharField, DecimalField, F, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce

from financial.models import account
from financial.profile_access import account_partytype
from financial.services_opening_balance import ACCOUNT_OPENING_TXN_ID_BASE
from assets.models import DepreciationRun, FixedAsset
from payments.models.payment_core import PaymentVoucherHeader
from posting.models import Entry, EntryStatus, EntityStaticAccountMap, JournalLine, StaticAccount, TxnType
from purchase.models.purchase_core import PurchaseInvoiceHeader, PurchaseInvoiceLine
from receipts.models.receipt_core import ReceiptVoucherHeader
from reports.services.financial.opening_balance_source import effective_opening_map_for_ledgers
from reports.selectors.financial import normalize_scope_ids, resolve_date_window, resolve_scope_names
from sales.models.sales_core import SalesInvoiceHeader, SalesInvoiceLine
from vouchers.models.voucher_core import VoucherHeader

ZERO = Decimal("0.00")

BOOK_REPORT_DEFAULTS = {
    "default_page_size": 100,
    "default_page_size_page": 1,
    "decimal_places": 2,
    "show_zero_balances_default": True,
    "show_opening_balance_default": True,
    "enable_drilldown": True,
}


TXN_SOURCE_META = {
    TxnType.SALES: ("sales", "Sales"),
    TxnType.SALES_CREDIT_NOTE: ("sales", "Sales Credit Note"),
    TxnType.SALES_DEBIT_NOTE: ("sales", "Sales Debit Note"),
    TxnType.PURCHASE: ("purchase", "Purchase"),
    TxnType.FIXED_ASSET_CAPITALIZATION: ("assets", "Fixed Asset Capitalization"),
    TxnType.FIXED_ASSET_DEPRECIATION: ("assets", "Fixed Asset Depreciation"),
    TxnType.FIXED_ASSET_IMPAIRMENT: ("assets", "Fixed Asset Impairment"),
    TxnType.FIXED_ASSET_DISPOSAL: ("assets", "Fixed Asset Disposal"),
    TxnType.JOURNAL: ("vouchers", "Journal"),
    TxnType.YEAR_END_CLOSE: ("controls", "Year-End Close"),
    TxnType.SALES_RETURN: ("sales", "Sales Return"),
    TxnType.PURCHASE_RETURN: ("purchase", "Purchase Return"),
    TxnType.PURCHASE_CREDIT_NOTE: ("purchase", "Purchase Credit Note"),
    TxnType.PURCHASE_DEBIT_NOTE: ("purchase", "Purchase Debit Note"),
    TxnType.JOURNAL_CASH: ("vouchers", "Cash Voucher"),
    TxnType.JOURNAL_BANK: ("vouchers", "Bank Voucher"),
    TxnType.RECEIPT: ("receipts", "Receipt Voucher"),
    TxnType.PAYMENT: ("payments", "Payment Voucher"),
}

DOCUMENT_TYPE_SOURCE_MODULES = {
    "purchase_invoice": {"purchase"},
    "purchase_credit_note": {"purchase"},
    "purchase_debit_note": {"purchase"},
    "sales_invoice": {"sales"},
    "sales_credit_note": {"sales"},
    "sales_debit_note": {"sales"},
    "payment_voucher": {"payment"},
    "receipt_voucher": {"receipt"},
    "journal_voucher": {"journal"},
    "cash_voucher": {"journal"},
    "bank_voucher": {"journal"},
    "asset_capitalization": {"asset"},
    "asset_depreciation": {"asset"},
    "asset_impairment": {"asset"},
    "asset_disposal": {"asset"},
}


@dataclass(frozen=True)
class CashbookAccountRef:
    key: str
    account_id: int
    ledger_id: int | None
    name: str
    code: int | None
    kind: str
    opening_balance: Decimal


def _money(value):
    """Format monetary values as fixed 2-decimal strings for stable frontend rendering."""
    return f"{Decimal(value or ZERO):.2f}"


def _entry_status_name(entry: Entry):
    return entry.get_status_display() if hasattr(entry, "get_status_display") else str(entry.status)


def _txn_source(txn_type: str):
    return TXN_SOURCE_META.get(txn_type, ("posting", txn_type))


def _decimal_or_zero(value, places="0.0000"):
    try:
        return Decimal(str(value or 0)).quantize(Decimal(places))
    except Exception:
        return Decimal(places)


def _drilldown_target_for_txn(txn_type: str) -> str:
    mapping = {
        TxnType.SALES: "sales_invoice_detail",
        TxnType.SALES_CREDIT_NOTE: "sales_invoice_detail",
        TxnType.SALES_DEBIT_NOTE: "sales_invoice_detail",
        TxnType.SALES_RETURN: "sales_invoice_detail",
        TxnType.PURCHASE: "purchase_invoice_detail",
        TxnType.PURCHASE_CREDIT_NOTE: "purchase_invoice_detail",
        TxnType.PURCHASE_DEBIT_NOTE: "purchase_invoice_detail",
        TxnType.PURCHASE_RETURN: "purchase_invoice_detail",
        TxnType.FIXED_ASSET_CAPITALIZATION: "asset_history_detail",
        TxnType.FIXED_ASSET_IMPAIRMENT: "asset_history_detail",
        TxnType.FIXED_ASSET_DISPOSAL: "asset_history_detail",
        TxnType.FIXED_ASSET_DEPRECIATION: "posting_entry_detail",
        TxnType.OPENING_BALANCE: "posting_entry_detail",
        TxnType.JOURNAL: "voucher_detail",
        TxnType.YEAR_END_CLOSE: "posting_entry_detail",
        TxnType.JOURNAL_CASH: "voucher_detail",
        TxnType.JOURNAL_BANK: "voucher_detail",
        TxnType.RECEIPT: "receipt_voucher_detail",
        TxnType.PAYMENT: "payment_voucher_detail",
    }
    return mapping.get(txn_type, "journal_entry_detail")


def _invoice_drilldown_route(txn_type: str | None, txn_id: int | None) -> str | None:
    if not txn_id:
        return None
    if txn_type in {
        TxnType.PURCHASE,
        TxnType.PURCHASE_CREDIT_NOTE,
        TxnType.PURCHASE_DEBIT_NOTE,
        TxnType.PURCHASE_RETURN,
    }:
        if PurchaseInvoiceLine.objects.filter(header_id=txn_id, is_service=True).exists():
            return "/purchaseserviceinvoice"
        return "/purchaseinvoice"
    if txn_type in {
        TxnType.SALES,
        TxnType.SALES_CREDIT_NOTE,
        TxnType.SALES_DEBIT_NOTE,
        TxnType.SALES_RETURN,
    }:
        if SalesInvoiceLine.objects.filter(header_id=txn_id, is_service=True).exists():
            return "/saleserviceinvoice"
        return "/saleinvoice"
    return None


def _document_lookup_binding(document_type: str, source_module: str | None):
    document_type = str(document_type or "").strip().lower()
    source_module = str(source_module or "").strip().lower() or None

    # Support the UI's generic invoice / credit-note / debit-note identifiers and
    # resolve them into module-specific document families using the provided source.
    if document_type == "invoice" and source_module in {"sales", "purchase"}:
        document_type = "sales_invoice" if source_module == "sales" else "purchase_invoice"
    elif document_type == "credit_note" and source_module in {"sales", "purchase"}:
        document_type = "sales_credit_note" if source_module == "sales" else "purchase_credit_note"
    elif document_type == "debit_note" and source_module in {"sales", "purchase"}:
        document_type = "sales_debit_note" if source_module == "sales" else "purchase_debit_note"

    allowed_modules = DOCUMENT_TYPE_SOURCE_MODULES.get(document_type)
    if not allowed_modules:
        raise ValueError({"document_type": "Unsupported document type."})

    if source_module and source_module not in allowed_modules:
        raise ValueError({"source_module": "Source module does not match the selected document type."})

    if not source_module:
        if len(allowed_modules) > 1:
            raise ValueError({"source_module": "Source module is required for this document type."})
        source_module = next(iter(allowed_modules))

    if document_type == "purchase_invoice":
        return PurchaseInvoiceHeader, {"doc_type": PurchaseInvoiceHeader.DocType.TAX_INVOICE}, TxnType.PURCHASE, source_module
    if document_type == "purchase_credit_note":
        return PurchaseInvoiceHeader, {"doc_type": PurchaseInvoiceHeader.DocType.CREDIT_NOTE}, TxnType.PURCHASE_CREDIT_NOTE, source_module
    if document_type == "purchase_debit_note":
        return PurchaseInvoiceHeader, {"doc_type": PurchaseInvoiceHeader.DocType.DEBIT_NOTE}, TxnType.PURCHASE_DEBIT_NOTE, source_module
    if document_type == "sales_invoice":
        return SalesInvoiceHeader, {"doc_type": SalesInvoiceHeader.DocType.TAX_INVOICE}, TxnType.SALES, source_module
    if document_type == "sales_credit_note":
        return SalesInvoiceHeader, {"doc_type": SalesInvoiceHeader.DocType.CREDIT_NOTE}, TxnType.SALES_CREDIT_NOTE, source_module
    if document_type == "sales_debit_note":
        return SalesInvoiceHeader, {"doc_type": SalesInvoiceHeader.DocType.DEBIT_NOTE}, TxnType.SALES_DEBIT_NOTE, source_module
    if document_type == "payment_voucher":
        return PaymentVoucherHeader, {}, TxnType.PAYMENT, source_module
    if document_type == "receipt_voucher":
        return ReceiptVoucherHeader, {}, TxnType.RECEIPT, source_module
    if document_type == "journal_voucher":
        return VoucherHeader, {"voucher_type": VoucherHeader.VoucherType.JOURNAL}, TxnType.JOURNAL, source_module
    if document_type == "cash_voucher":
        return VoucherHeader, {"voucher_type": VoucherHeader.VoucherType.CASH}, TxnType.JOURNAL_CASH, source_module
    if document_type == "bank_voucher":
        return VoucherHeader, {"voucher_type": VoucherHeader.VoucherType.BANK}, TxnType.JOURNAL_BANK, source_module
    if document_type == "asset_capitalization":
        return FixedAsset, {}, TxnType.FIXED_ASSET_CAPITALIZATION, source_module
    if document_type == "asset_depreciation":
        return DepreciationRun, {}, TxnType.FIXED_ASSET_DEPRECIATION, source_module
    if document_type == "asset_impairment":
        return FixedAsset, {}, TxnType.FIXED_ASSET_IMPAIRMENT, source_module
    if document_type == "asset_disposal":
        return FixedAsset, {}, TxnType.FIXED_ASSET_DISPOSAL, source_module
    raise ValueError({"document_type": "Unsupported document type."})


def resolve_posting_entry_for_document(
    *,
    entity_id,
    document_type,
    document_id,
    entityfin_id=None,
    subentity_id=None,
    source_module=None,
):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    if not document_id:
        raise ValueError({"document_id": "Document id is required."})

    document_model, extra_filters, txn_type, source_module = _document_lookup_binding(document_type, source_module)
    document_filters = {
        "id": document_id,
        "entity_id": entity_id,
        **extra_filters,
    }
    if entityfin_id:
        document_filters["entityfinid_id"] = entityfin_id
    if subentity_id is not None:
        document_filters["subentity_id"] = subentity_id

    document = document_model.objects.get(**document_filters)
    entry_filters = {
        "entity_id": entity_id,
        "txn_type": txn_type,
        "txn_id": document.id,
    }
    if entityfin_id:
        entry_filters["entityfin_id"] = entityfin_id
    if subentity_id is not None:
        entry_filters["subentity_id"] = subentity_id

    entry = Entry.objects.filter(**entry_filters).order_by("-id").first()
    if not entry:
        raise Entry.DoesNotExist

    return {
        "entry_id": entry.id,
        "txn_id": entry.txn_id,
        "txn_type": entry.txn_type,
        "voucher_number": entry.voucher_no,
        "posting_date": entry.posting_date,
        "voucher_date": entry.voucher_date,
        "status": entry.status,
        "status_name": _entry_status_name(entry),
        "source_module": source_module,
        "document_type": document_type,
        "document_id": document.id,
    }


def _cashbook_target_key(line):
    """Use ledger-first identity when available so balances stay tied to accounting identity."""
    return f"ledger:{line.resolved_ledger_id}" if line.resolved_ledger_id else f"account:{line.account_id}"


def _line_delta(line):
    """Signed movement for the cash/bank-side journal line only."""
    return Decimal(line.amount if line.drcr else -line.amount)


def _entry_reference_annotation():
    """Resolve reference numbers from source modules without duplicating posting storage."""
    voucher_ref = VoucherHeader.objects.filter(id=OuterRef("txn_id")).values("reference_number")[:1]
    receipt_ref = ReceiptVoucherHeader.objects.filter(id=OuterRef("txn_id")).values("reference_number")[:1]
    payment_ref = PaymentVoucherHeader.objects.filter(id=OuterRef("txn_id")).values("reference_number")[:1]
    purchase_supplier_ref = PurchaseInvoiceHeader.objects.filter(id=OuterRef("txn_id")).values("supplier_invoice_number")[:1]
    return Coalesce(
        Subquery(voucher_ref),
        Subquery(receipt_ref),
        Subquery(payment_ref),
        Subquery(purchase_supplier_ref),
        Value(""),
        output_field=CharField(),
    )


def _entry_document_number_annotation():
    """Resolve human-facing document numbers for invoice/note style documents."""
    purchase_doc_number = PurchaseInvoiceHeader.objects.filter(id=OuterRef("txn_id")).values("purchase_number")[:1]
    sales_doc_number = SalesInvoiceHeader.objects.filter(id=OuterRef("txn_id")).values("invoice_number")[:1]
    return Coalesce(
        Subquery(purchase_doc_number),
        Subquery(sales_doc_number),
        Value(""),
        output_field=CharField(),
    )


def _entry_counterparty_name_annotation():
    """Resolve vendor/customer snapshots for report search and discoverability."""
    purchase_vendor_name = PurchaseInvoiceHeader.objects.filter(id=OuterRef("txn_id")).values("vendor_name")[:1]
    sales_customer_name = SalesInvoiceHeader.objects.filter(id=OuterRef("txn_id")).values("customer_name")[:1]
    return Coalesce(
        Subquery(purchase_vendor_name),
        Subquery(sales_customer_name),
        Value(""),
        output_field=CharField(),
    )


def _validate_entity_accounts(entity_id: int, ids: list[int], *, field_name: str):
    """Enforce entity-level account scope before report logic runs."""
    if not ids:
        return {}
    rows = {
        row.id: row
        for row in account.objects.filter(entity_id=entity_id, id__in=ids)
        .select_related("ledger", "ledger__accounthead", "ledger__accounttype")
    }
    missing = sorted(set(ids) - set(rows.keys()))
    if missing:
        raise ValueError({field_name: f"Account(s) not found in entity scope: {', '.join(map(str, missing))}."})
    return rows


def _cancelled_source_filter_q(*, prefix: str, entity_id: int, entityfin_id=None, subentity_id=None):
    def scoped_ids(model):
        qs = model.objects.filter(entity_id=entity_id)
        if entityfin_id:
            qs = qs.filter(entityfinid_id=entityfin_id)
        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        return qs.values("id")

    return (
        Q(**{f"{prefix}txn_type": TxnType.SALES, f"{prefix}txn_id__in": scoped_ids(SalesInvoiceHeader).filter(status=SalesInvoiceHeader.Status.CANCELLED)})
        | Q(**{f"{prefix}txn_type": TxnType.SALES_CREDIT_NOTE, f"{prefix}txn_id__in": scoped_ids(SalesInvoiceHeader).filter(status=SalesInvoiceHeader.Status.CANCELLED)})
        | Q(**{f"{prefix}txn_type": TxnType.SALES_DEBIT_NOTE, f"{prefix}txn_id__in": scoped_ids(SalesInvoiceHeader).filter(status=SalesInvoiceHeader.Status.CANCELLED)})
        | Q(**{f"{prefix}txn_type": TxnType.PURCHASE, f"{prefix}txn_id__in": scoped_ids(PurchaseInvoiceHeader).filter(status=PurchaseInvoiceHeader.Status.CANCELLED)})
        | Q(**{f"{prefix}txn_type": TxnType.PURCHASE_CREDIT_NOTE, f"{prefix}txn_id__in": scoped_ids(PurchaseInvoiceHeader).filter(status=PurchaseInvoiceHeader.Status.CANCELLED)})
        | Q(**{f"{prefix}txn_type": TxnType.PURCHASE_DEBIT_NOTE, f"{prefix}txn_id__in": scoped_ids(PurchaseInvoiceHeader).filter(status=PurchaseInvoiceHeader.Status.CANCELLED)})
        | Q(**{f"{prefix}txn_type": TxnType.RECEIPT, f"{prefix}txn_id__in": scoped_ids(ReceiptVoucherHeader).filter(status=ReceiptVoucherHeader.Status.CANCELLED)})
        | Q(**{f"{prefix}txn_type": TxnType.PAYMENT, f"{prefix}txn_id__in": scoped_ids(PaymentVoucherHeader).filter(status=PaymentVoucherHeader.Status.CANCELLED)})
        | Q(**{f"{prefix}txn_type": TxnType.JOURNAL, f"{prefix}txn_id__in": scoped_ids(VoucherHeader).filter(status=VoucherHeader.Status.CANCELLED)})
        | Q(**{f"{prefix}txn_type": TxnType.JOURNAL_CASH, f"{prefix}txn_id__in": scoped_ids(VoucherHeader).filter(status=VoucherHeader.Status.CANCELLED)})
        | Q(**{f"{prefix}txn_type": TxnType.JOURNAL_BANK, f"{prefix}txn_id__in": scoped_ids(VoucherHeader).filter(status=VoucherHeader.Status.CANCELLED)})
    )


def _entry_base_queryset(entity_id, entityfin_id=None, subentity_id=None, from_date=None, to_date=None):
    """
    Base Daybook queryset.

    Daybook is entry-first because `posting.Entry` is the voucher-level accounting header,
    while `JournalLine` remains the line-level truth used only for totals and drill-down.
    """
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    from_date, to_date = resolve_date_window(entityfin_id, from_date, to_date)
    qs = (
        Entry.objects.filter(entity_id=entity_id)
        .exclude(txn_type=TxnType.OPENING_BALANCE)
        .select_related("created_by", "posted_by", "entity", "entityfin", "subentity")
        .annotate(
            debit_total=Coalesce(
                Sum(
                    Case(
                        When(posting_journal_lines__drcr=True, then=F("posting_journal_lines__amount")),
                        default=ZERO,
                        output_field=DecimalField(max_digits=14, decimal_places=2),
                    )
                ),
                ZERO,
            ),
            credit_total=Coalesce(
                Sum(
                    Case(
                        When(posting_journal_lines__drcr=False, then=F("posting_journal_lines__amount")),
                        default=ZERO,
                        output_field=DecimalField(max_digits=14, decimal_places=2),
                    )
                ),
                ZERO,
            ),
            reference_number=_entry_reference_annotation(),
            document_number=_entry_document_number_annotation(),
            counterparty_name=_entry_counterparty_name_annotation(),
        )
    )
    if entityfin_id:
        qs = qs.filter(entityfin_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(subentity_id=subentity_id)
    if from_date:
        qs = qs.filter(posting_date__gte=from_date)
    if to_date:
        qs = qs.filter(posting_date__lte=to_date)
    qs = qs.exclude(
        _cancelled_source_filter_q(
            prefix="",
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
        )
    )
    return qs, entity_id, entityfin_id, subentity_id, from_date, to_date


def _paginate_queryset(qs, *, page: int, page_size: int):
    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(page)
    return {
        "count": paginator.count,
        "page": page_obj.number,
        "pages": paginator.num_pages,
        "page_size": page_size,
        "results": list(page_obj.object_list),
    }


def _drilldown_payload(entry: Entry, *, entity_id, entityfin_id, subentity_id):
    """Stable drill-down identifiers used by the frontend to open source documents/details."""
    source_module, _ = _txn_source(entry.txn_type)
    drilldown_target = _drilldown_target_for_txn(entry.txn_type)
    account_opening_account_id = None
    if entry.txn_type == TxnType.OPENING_BALANCE and int(entry.txn_id or 0) >= ACCOUNT_OPENING_TXN_ID_BASE:
        account_opening_account_id = int(entry.txn_id) - ACCOUNT_OPENING_TXN_ID_BASE
        drilldown_target = "account_opening_detail"
    asset_txn_types = {
        TxnType.FIXED_ASSET_CAPITALIZATION,
        TxnType.FIXED_ASSET_IMPAIRMENT,
        TxnType.FIXED_ASSET_DISPOSAL,
    }
    drilldown_params = {
        "id": entry.txn_id,
        "entry_id": entry.id,
        "entity": entity_id,
        "entityfinid": entityfin_id,
        "subentity": subentity_id,
    }
    if drilldown_target == "asset_history_detail" or entry.txn_type in asset_txn_types:
        drilldown_params["asset_id"] = entry.txn_id
    if account_opening_account_id:
        drilldown_params["account_id"] = account_opening_account_id
    return {
        "entry_id": entry.id,
        "txn_type": entry.txn_type,
        "txn_type_name": entry.get_txn_type_display() if hasattr(entry, "get_txn_type_display") else entry.txn_type,
        "txn_id": entry.txn_id,
        "source_module": source_module,
        "drilldown_target": drilldown_target,
        "drilldown_route": _invoice_drilldown_route(entry.txn_type, entry.txn_id),
        "drilldown_params": drilldown_params,
    }


def build_daybook(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    from_date=None,
    to_date=None,
    voucher_types=None,
    account_ids=None,
    statuses=None,
    posted=None,
    search=None,
    page=1,
    page_size=100,
):
    """
    Build Daybook from posting entries within the requested scope.

    Totals are computed from the full filtered dataset, never from paginated rows.
    """
    qs, entity_id, entityfin_id, subentity_id, from_date, to_date = _entry_base_queryset(
        entity_id, entityfin_id, subentity_id, from_date, to_date
    )
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    account_ids = account_ids or []
    voucher_types = voucher_types or []
    statuses = statuses or []

    if account_ids:
        _validate_entity_accounts(entity_id, account_ids, field_name="account")
        matched_entry_ids = Entry.objects.filter(entity_id=entity_id, posting_journal_lines__account_id__in=account_ids).values("id")
        qs = qs.filter(id__in=matched_entry_ids)
    if voucher_types:
        qs = qs.filter(txn_type__in=voucher_types)
    if statuses:
        qs = qs.filter(status__in=statuses)
    if posted is True:
        qs = qs.filter(status=EntryStatus.POSTED)
    elif posted is False:
        qs = qs.exclude(status=EntryStatus.POSTED)
    if search:
        qs = qs.filter(
            Q(voucher_no__icontains=search)
            | Q(narration__icontains=search)
            | Q(reference_number__icontains=search)
            | Q(document_number__icontains=search)
            | Q(counterparty_name__icontains=search)
        )

    qs = qs.distinct().order_by("posting_date", "voucher_date", "created_at", "id")

    summary = JournalLine.objects.filter(entry_id__in=qs.values("id")).aggregate(
        debit_total=Coalesce(
            Sum(
                Case(
                    When(drcr=True, then=F("amount")),
                    default=ZERO,
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            ),
            ZERO,
        ),
        credit_total=Coalesce(
            Sum(
                Case(
                    When(drcr=False, then=F("amount")),
                    default=ZERO,
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            ),
            ZERO,
        ),
    )
    paged = _paginate_queryset(qs, page=page, page_size=page_size)
    rows = []
    for entry in paged["results"]:
        source_module, voucher_type_name = _txn_source(entry.txn_type)
        rows.append(
            {
                "transaction_date": entry.posting_date,
                "voucher_date": entry.voucher_date,
                "voucher_number": entry.voucher_no,
                "voucher_type": entry.txn_type,
                "voucher_type_name": voucher_type_name,
                "narration": entry.narration,
                "reference_number": entry.reference_number or None,
                "document_number": getattr(entry, "document_number", "") or None,
                "counterparty_name": getattr(entry, "counterparty_name", "") or None,
                "debit_total": _money(entry.debit_total),
                "credit_total": _money(entry.credit_total),
                "status": entry.status,
                "status_name": _entry_status_name(entry),
                "posted": int(entry.status) == int(EntryStatus.POSTED),
                "source_module": source_module,
                "created_by": getattr(entry.created_by, "email", None) or getattr(entry.created_by, "username", None),
                **_drilldown_payload(
                    entry,
                    entity_id=entity_id,
                    entityfin_id=entityfin_id,
                    subentity_id=subentity_id,
                ),
            }
        )

    return {
        "entity_id": entity_id,
        "entity_name": scope_names["entity_name"],
        "entityfin_id": entityfin_id,
        "entityfin_name": scope_names["entityfin_name"],
        "subentity_id": subentity_id,
        "subentity_name": scope_names["subentity_name"],
        "from_date": from_date,
        "to_date": to_date,
        "mode": "voucher_list",
        "running_balance_scope": None,
        "balance_basis": "entry_header_with_journal_totals",
        "balance_integrity": True,
        "balance_note": "Daybook is derived from posting entries and ordered deterministically by posting date, voucher date, created_at, and entry id.",
        "opening_balance": None,
        "closing_balance": None,
        "account_summaries": [],
        "totals": {
            "transaction_count": paged["count"],
            "debit_total": _money(summary["debit_total"]),
            "credit_total": _money(summary["credit_total"]),
        },
        "count": paged["count"],
        "page": paged["page"],
        "page_size": paged["page_size"],
        "pages": paged["pages"],
        "next": None,
        "previous": None,
        "results": rows,
    }


def build_daybook_entry_detail(*, entry_id, entity_id, entityfin_id=None, subentity_id=None):
    """Return the exact journal lines for an entry drill-down."""
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    entry = (
        Entry.objects.filter(id=entry_id, entity_id=entity_id)
        .select_related("created_by", "posted_by", "entity", "entityfin", "subentity")
        .first()
    )
    if entry is None:
        raise Entry.DoesNotExist(f"Entry {entry_id} not found.")
    if entityfin_id and entry.entityfin_id != entityfin_id:
        raise Entry.DoesNotExist(f"Entry {entry_id} not found in requested entity financial year.")
    if subentity_id is not None and entry.subentity_id != subentity_id:
        raise Entry.DoesNotExist(f"Entry {entry_id} not found in requested subentity.")

    lines = (
        JournalLine.objects.filter(entry_id=entry.id)
        .select_related("account", "ledger", "accounthead", "created_by")
        .order_by("posting_date", "id")
    )
    inventory_moves = (
        entry.posting_inventory_moves.select_related(
            "product",
            "uom",
            "base_uom",
            "location",
            "source_location",
            "destination_location",
        ).order_by("posting_date", "id")
    )
    return {
        "entry_id": entry.id,
        "voucher_number": entry.voucher_no,
        "voucher_type": entry.txn_type,
        "voucher_type_name": entry.get_txn_type_display() if hasattr(entry, "get_txn_type_display") else entry.txn_type,
        "posting_date": entry.posting_date,
        "voucher_date": entry.voucher_date,
        "status": entry.status,
        "status_name": _entry_status_name(entry),
        "narration": entry.narration,
        "created_by": getattr(entry.created_by, "email", None) or getattr(entry.created_by, "username", None),
        "lines": [
            {
                "journal_line_id": line.id,
                "account_id": line.account_id,
                "account_name": getattr(line.account, "accountname", None),
                "ledger_id": line.ledger_id,
                "ledger_name": getattr(line.ledger, "name", None),
                "accounthead_id": line.accounthead_id or getattr(line.ledger, "accounthead_id", None),
                "debit": _money(line.amount if line.drcr else ZERO),
                "credit": _money(line.amount if not line.drcr else ZERO),
                "description": line.description,
                "detail_id": line.detail_id,
            }
            for line in lines
        ],
        "inventory_moves": [
            {
                "inventory_move_id": move.id,
                "detail_id": move.detail_id,
                "product_id": move.product_id,
                "product_name": getattr(move.product, "productname", None) or getattr(move.product, "product_name", None) or str(move.product),
                "batch_number": move.batch_number or None,
                "location_id": move.location_id,
                "location_name": getattr(move.location, "godownname", None) or getattr(move.location, "name", None),
                "source_location_id": move.source_location_id,
                "source_location_name": getattr(move.source_location, "godownname", None) or getattr(move.source_location, "name", None),
                "destination_location_id": move.destination_location_id,
                "destination_location_name": getattr(move.destination_location, "godownname", None) or getattr(move.destination_location, "name", None),
                "uom_id": move.uom_id,
                "uom_name": getattr(move.uom, "code", None) or getattr(move.uom, "description", None),
                "base_uom_id": move.base_uom_id,
                "base_uom_name": getattr(move.base_uom, "code", None) or getattr(move.base_uom, "description", None),
                "qty": f"{Decimal(move.qty or ZERO4):.4f}",
                "base_qty": f"{Decimal(move.base_qty or ZERO4):.4f}",
                "unit_cost": format(
                    (
                        (
                            _decimal_or_zero((move.cost_meta or {}).get("taxable_value"), "0.01")
                            + _decimal_or_zero((move.cost_meta or {}).get("cap_share"), "0.01")
                        ) / abs(_decimal_or_zero((move.cost_meta or {}).get("qty_for_cost") or move.qty, "0.0000"))
                    ) if abs(_decimal_or_zero((move.cost_meta or {}).get("qty_for_cost") or move.qty, "0.0000")) else Decimal(move.unit_cost or ZERO4),
                    ".4f",
                ),
                "base_unit_cost": format(
                    (
                        (
                            _decimal_or_zero((move.cost_meta or {}).get("taxable_value"), "0.01")
                            + _decimal_or_zero((move.cost_meta or {}).get("cap_share"), "0.01")
                        ) / abs(Decimal(move.base_qty or ZERO4))
                    ) if abs(Decimal(move.base_qty or ZERO4)) else Decimal(move.unit_cost or ZERO4),
                    ".4f",
                ),
                "ext_cost": _money(
                    (
                        _decimal_or_zero((move.cost_meta or {}).get('taxable_value'), '0.01')
                        + _decimal_or_zero((move.cost_meta or {}).get('cap_share'), '0.01')
                    ) or move.ext_cost
                ),
                "move_type": move.move_type,
                "move_type_name": move.get_move_type_display() if hasattr(move, "get_move_type_display") else move.move_type,
                "movement_nature": move.movement_nature,
                "movement_nature_name": move.get_movement_nature_display() if hasattr(move, "get_movement_nature_display") else move.movement_nature,
                "movement_reason": move.movement_reason or None,
                "posting_date": move.posting_date,
            }
            for move in inventory_moves
        ],
    }


def _infer_account_kind(row, *, static_kind_by_account):
    """Classify cash/bank accounts using static mapping first, then safe metadata fallbacks."""
    explicit_kind = static_kind_by_account.get(row.id)
    if explicit_kind:
        return explicit_kind
    if str(account_partytype(row) or "").lower() == "bank":
        return "bank"
    label = f"{getattr(row, 'accountname', '')} {getattr(getattr(row, 'ledger', None), 'name', '')}".lower()
    if "bank" in label:
        return "bank"
    return "cash"


def _cashbook_target_accounts(entity_id, *, mode, cash_account_ids, bank_account_ids, entityfin_id=None, subentity_id=None):
    """Resolve Cashbook target accounts for the requested mode and explicit filters."""
    explicit_rows = {}
    if cash_account_ids:
        explicit_rows.update(_validate_entity_accounts(entity_id, cash_account_ids, field_name="cash_account"))
    if bank_account_ids:
        explicit_rows.update(_validate_entity_accounts(entity_id, bank_account_ids, field_name="bank_account"))

    static_maps = (
        EntityStaticAccountMap.objects.filter(
            entity_id=entity_id,
            is_active=True,
            static_account__code__in=["CASH", "BANK_MAIN"],
            static_account__is_active=True,
        )
        .select_related("static_account")
        .values("account_id", "static_account__code")
    )
    static_kind_by_account = {
        row["account_id"]: ("cash" if row["static_account__code"] == "CASH" else "bank")
        for row in static_maps
    }

    if explicit_rows:
        rows = explicit_rows
    else:
        account_ids = set(static_kind_by_account.keys())
        account_ids.update(
            VoucherHeader.objects.filter(entity_id=entity_id, cash_bank_account_id__isnull=False).values_list(
                "cash_bank_account_id", flat=True
            )
        )
        account_ids.update(
            ReceiptVoucherHeader.objects.filter(entity_id=entity_id).values_list("received_in_id", flat=True)
        )
        account_ids.update(
            PaymentVoucherHeader.objects.filter(entity_id=entity_id).values_list("paid_from_id", flat=True)
        )
        rows = {
            row.id: row
            for row in account.objects.filter(entity_id=entity_id, id__in=account_ids)
            .select_related("ledger")
        }

    refs = []
    opening_map = effective_opening_map_for_ledgers(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        ledgers=[row.ledger for row in rows.values() if getattr(row, "ledger", None)],
        posted_only=True,
    )
    for row in rows.values():
        kind = (
            "cash"
            if row.id in set(cash_account_ids or [])
            else "bank"
            if row.id in set(bank_account_ids or [])
            else _infer_account_kind(row, static_kind_by_account=static_kind_by_account)
        )
        if mode != "both" and kind != mode:
            continue
        opening = ZERO
        if getattr(row, "ledger", None):
            opening = opening_map.get(int(row.ledger_id), ZERO)
        else:
            opening = ZERO
        refs.append(
            CashbookAccountRef(
                key=f"ledger:{row.ledger_id}" if row.ledger_id else f"account:{row.id}",
                account_id=row.id,
                ledger_id=row.ledger_id,
                name=getattr(getattr(row, "ledger", None), "name", None) or row.accountname or f"Account {row.id}",
                code=getattr(getattr(row, "ledger", None), "ledger_code", None),
                kind=kind,
                opening_balance=opening,
            )
        )
    return refs


def _cashbook_line_queryset(entity_id, entityfin_id=None, subentity_id=None, *, to_date=None):
    """
    Return posted Cashbook candidate lines.

    Reversed entries are included because they are still posted accounting movements and
    therefore must affect opening and closing balances.
    """
    qs = (
        JournalLine.objects.filter(entity_id=entity_id, entry__status__in=[EntryStatus.POSTED, EntryStatus.REVERSED])
        .exclude(entry__txn_type=TxnType.OPENING_BALANCE)
        .annotate(resolved_ledger_id=Coalesce(F("ledger_id"), F("account__ledger_id")))
        .select_related("entry", "account", "ledger", "account__ledger")
    )
    if entityfin_id:
        qs = qs.filter(entityfin_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(subentity_id=subentity_id)
    if to_date:
        qs = qs.filter(posting_date__lte=to_date)
    qs = qs.exclude(
        _cancelled_source_filter_q(
            prefix="entry__",
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
        )
    )
    return qs


def build_cashbook(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    from_date=None,
    to_date=None,
    mode="both",
    cash_account_ids=None,
    bank_account_ids=None,
    counter_account_ids=None,
    voucher_types=None,
    search=None,
    page=1,
    page_size=100,
):
    """
    Build Cashbook from cash/bank-side journal lines.

    Opening and closing balances use the true posted movement scope for the selected
    cash/bank accounts. Visible row filters may narrow the displayed subset, but they do
    not redefine the accounting balance basis.
    """
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    from_date, to_date = resolve_date_window(entityfin_id, from_date, to_date)
    scope_names = resolve_scope_names(entity_id, entityfin_id, subentity_id)

    counter_rows = _validate_entity_accounts(entity_id, counter_account_ids or [], field_name="account")
    refs = _cashbook_target_accounts(
        entity_id,
        mode=mode,
        cash_account_ids=cash_account_ids or [],
        bank_account_ids=bank_account_ids or [],
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
    )
    ref_by_key = {ref.key: ref for ref in refs}
    account_ids = [ref.account_id for ref in refs]
    ledger_ids = [ref.ledger_id for ref in refs if ref.ledger_id]
    selective_filters_applied = bool(counter_account_ids or voucher_types or search)
    single_account_mode = len(refs) == 1 and not selective_filters_applied

    if not refs:
        return {
            "entity_id": entity_id,
            "entity_name": scope_names["entity_name"],
            "entityfin_id": entityfin_id,
            "entityfin_name": scope_names["entityfin_name"],
            "subentity_id": subentity_id,
            "subentity_name": scope_names["subentity_name"],
            "from_date": from_date,
            "to_date": to_date,
            "mode": "empty",
            "running_balance_scope": "account",
            "balance_basis": "actual_account_movement",
            "balance_integrity": True,
            "balance_note": "No cash/bank accounts matched the requested scope.",
            "totals": {"receipt_total": _money(ZERO), "payment_total": _money(ZERO), "transaction_count": 0},
            "opening_balance": _money(ZERO),
            "closing_balance": _money(ZERO),
            "count": 0,
            "page": page,
            "page_size": page_size,
            "pages": 0,
            "next": None,
            "previous": None,
            "account_summaries": [],
            "results": [],
        }

    all_account_lines_qs = _cashbook_line_queryset(entity_id, entityfin_id, subentity_id, to_date=to_date).filter(
        Q(account_id__in=account_ids) | Q(resolved_ledger_id__in=ledger_ids)
    )
    all_account_lines_qs = all_account_lines_qs.order_by("posting_date", "entry_id", "id")

    visible_lines_qs = all_account_lines_qs
    if voucher_types:
        visible_lines_qs = visible_lines_qs.filter(txn_type__in=voucher_types)
    if counter_rows:
        counter_ids = list(counter_rows.keys())
        visible_lines_qs = visible_lines_qs.filter(entry__posting_journal_lines__account_id__in=counter_ids)
    if search:
        visible_lines_qs = visible_lines_qs.filter(
            Q(voucher_no__icontains=search)
            | Q(entry__narration__icontains=search)
            | Q(description__icontains=search)
        )
    visible_lines_qs = visible_lines_qs.distinct().order_by("posting_date", "entry_id", "id")

    all_account_lines = list(all_account_lines_qs)
    visible_lines = list(visible_lines_qs)
    visible_entry_ids = {line.entry_id for line in visible_lines}
    entry_lines = defaultdict(list)
    if visible_entry_ids:
        for line in (
            JournalLine.objects.filter(entry_id__in=visible_entry_ids)
            .select_related("account", "ledger", "account__ledger")
            .order_by("entry_id", "id")
        ):
            entry_lines[line.entry_id].append(line)

    actual_opening = {ref.key: Decimal(ref.opening_balance) for ref in refs}
    actual_period_receipts = defaultdict(lambda: ZERO)
    actual_period_payments = defaultdict(lambda: ZERO)
    closing_balances = {ref.key: Decimal(ref.opening_balance) for ref in refs}
    visible_receipts = defaultdict(lambda: ZERO)
    visible_payments = defaultdict(lambda: ZERO)
    visible_counts = defaultdict(int)

    visible_in_range = []
    for line in all_account_lines:
        key = _cashbook_target_key(line)
        if key not in ref_by_key:
            continue
        delta = _line_delta(line)
        if from_date and line.posting_date < from_date:
            actual_opening[key] += delta
        else:
            receipt_amount = Decimal(line.amount if line.drcr else ZERO)
            payment_amount = Decimal(line.amount if not line.drcr else ZERO)
            actual_period_receipts[key] += receipt_amount
            actual_period_payments[key] += payment_amount
        closing_balances[key] += delta

    for line in visible_lines:
        if from_date and line.posting_date < from_date:
            continue
        if to_date and line.posting_date > to_date:
            continue
        visible_in_range.append(line)
        key = _cashbook_target_key(line)
        visible_receipts[key] += Decimal(line.amount if line.drcr else ZERO)
        visible_payments[key] += Decimal(line.amount if not line.drcr else ZERO)
        visible_counts[key] += 1

    running_balance_scope = "account" if len(refs) == 1 else "combined_accounts"
    running_balance_by_line_id = {}

    if len(refs) == 1:
        running = {ref.key: Decimal(actual_opening[ref.key]) for ref in refs}
        for line in all_account_lines:
            key = _cashbook_target_key(line)
            if key not in ref_by_key:
                continue
            if from_date and line.posting_date < from_date:
                continue
            if to_date and line.posting_date > to_date:
                continue
            running[key] += _line_delta(line)
            running_balance_by_line_id[line.id] = _money(running[key])
    else:
        combined_running = sum((actual_opening[ref.key] for ref in refs), ZERO)
        for line in all_account_lines:
            key = _cashbook_target_key(line)
            if key not in ref_by_key:
                continue
            if from_date and line.posting_date < from_date:
                continue
            if to_date and line.posting_date > to_date:
                continue
            combined_running += _line_delta(line)
            running_balance_by_line_id[line.id] = _money(combined_running)

    rows = []
    if single_account_mode:
        for line in visible_in_range:
            key = _cashbook_target_key(line)
            ref = ref_by_key.get(key)
            if ref is None:
                continue
            receipt_amount = Decimal(line.amount if line.drcr else ZERO)
            payment_amount = Decimal(line.amount if not line.drcr else ZERO)
            counters = []
            for other in entry_lines.get(line.entry_id, []):
                if other.id == line.id:
                    continue
                name = (
                    getattr(getattr(other, "ledger", None), "name", None)
                    or getattr(getattr(other, "account", None), "accountname", None)
                    or f"Line {other.id}"
                )
                if name not in counters:
                    counters.append(name)

            source_module, voucher_type_name = _txn_source(line.txn_type)
            rows.append(
                {
                    "date": line.posting_date,
                    "voucher_number": line.voucher_no or getattr(line.entry, "voucher_no", None),
                    "voucher_type": line.txn_type,
                    "voucher_type_name": voucher_type_name,
                    "account_impacted": {
                        "account_id": ref.account_id,
                        "ledger_id": ref.ledger_id,
                        "name": ref.name,
                        "code": ref.code,
                        "kind": ref.kind,
                    },
                    "counter_account": ", ".join(counters),
                    "particulars": ", ".join(counters),
                    "receipt_amount": _money(receipt_amount),
                    "payment_amount": _money(payment_amount),
                    "running_balance": running_balance_by_line_id.get(line.id),
                    "running_balance_scope": running_balance_scope,
                    "narration": line.entry.narration or line.description,
                    "source_module": source_module,
                    "entry_id": line.entry_id,
                    "journal_line_id": line.id,
                    "detail_id": line.detail_id,
                    "drilldown": _drilldown_payload(
                        line.entry,
                        entity_id=entity_id,
                        entityfin_id=entityfin_id,
                        subentity_id=subentity_id,
                    ),
                }
            )
    else:
        # Suppress running balance outside single-account detail mode because a filtered
        # subset or mixed-account stream can hide required movements and become misleading.
        for line in visible_in_range:
            key = _cashbook_target_key(line)
            ref = ref_by_key.get(key)
            if ref is None:
                continue
            counters = []
            for other in entry_lines.get(line.entry_id, []):
                if other.id == line.id:
                    continue
                name = (
                    getattr(getattr(other, "ledger", None), "name", None)
                    or getattr(getattr(other, "account", None), "accountname", None)
                    or f"Line {other.id}"
                )
                if name not in counters:
                    counters.append(name)

            receipt_amount = Decimal(line.amount if line.drcr else ZERO)
            payment_amount = Decimal(line.amount if not line.drcr else ZERO)
            source_module, voucher_type_name = _txn_source(line.txn_type)
            rows.append(
                {
                    "date": line.posting_date,
                    "voucher_number": line.voucher_no or getattr(line.entry, "voucher_no", None),
                    "voucher_type": line.txn_type,
                    "voucher_type_name": voucher_type_name,
                    "account_impacted": {
                        "account_id": ref.account_id,
                        "ledger_id": ref.ledger_id,
                        "name": ref.name,
                        "code": ref.code,
                        "kind": ref.kind,
                    },
                    "counter_account": ", ".join(counters),
                    "particulars": ", ".join(counters),
                    "receipt_amount": _money(receipt_amount),
                    "payment_amount": _money(payment_amount),
                    "running_balance": running_balance_by_line_id.get(line.id),
                    "running_balance_scope": running_balance_scope,
                    "narration": line.entry.narration or line.description,
                    "source_module": source_module,
                    "entry_id": line.entry_id,
                    "journal_line_id": line.id,
                    "detail_id": line.detail_id,
                    "drilldown": _drilldown_payload(
                        line.entry,
                        entity_id=entity_id,
                        entityfin_id=entityfin_id,
                        subentity_id=subentity_id,
                    ),
                }
            )

    paginator = Paginator(rows, page_size)
    page_obj = paginator.get_page(page)
    account_summaries = []
    for ref in refs:
        summary_row = {
            "account_id": ref.account_id,
            "ledger_id": ref.ledger_id,
            "name": ref.name,
            "code": ref.code,
            "kind": ref.kind,
            "opening_balance": _money(actual_opening[ref.key]),
            "period_receipt_total": _money(actual_period_receipts[ref.key]),
            "period_payment_total": _money(actual_period_payments[ref.key]),
            "closing_balance": _money(closing_balances[ref.key]),
        }
        if selective_filters_applied:
            summary_row.update(
                {
                    "visible_receipt_total": _money(visible_receipts[ref.key]),
                    "visible_payment_total": _money(visible_payments[ref.key]),
                    "visible_transaction_count": visible_counts[ref.key],
                }
            )
        account_summaries.append(summary_row)

    consolidated_opening = sum((actual_opening[ref.key] for ref in refs), ZERO)
    consolidated_closing = sum((closing_balances[ref.key] for ref in refs), ZERO)
    consolidated_period_receipts = sum((actual_period_receipts[ref.key] for ref in refs), ZERO)
    consolidated_period_payments = sum((actual_period_payments[ref.key] for ref in refs), ZERO)
    consolidated_visible_receipts = sum((visible_receipts[ref.key] for ref in refs), ZERO)
    consolidated_visible_payments = sum((visible_payments[ref.key] for ref in refs), ZERO)

    payload = {
        "entity_id": entity_id,
        "entity_name": scope_names["entity_name"],
        "entityfin_id": entityfin_id,
        "entityfin_name": scope_names["entityfin_name"],
        "subentity_id": subentity_id,
        "subentity_name": scope_names["subentity_name"],
        "from_date": from_date,
        "to_date": to_date,
        "mode": mode,
        "mode": "single_account_detail" if single_account_mode else "multi_account_summary",
        "running_balance_scope": running_balance_scope,
        "balance_basis": "actual_account_movement",
        "balance_integrity": True,
        "balance_note": (
            "Opening, movement, and closing balances are computed from all posted entries for the scoped cash/bank account."
            if single_account_mode
            else (
                "Running balance reflects the true post-transaction balance for the scoped cash/bank selection. "
                "Filtered views may omit intermediate rows while still showing the correct balance at each visible movement."
                if selective_filters_applied
                else "Running balance reflects the combined post-transaction balance across all scoped cash/bank accounts."
            )
        ),
        "totals": {
            "transaction_count": len(visible_in_range),
            "receipt_total": _money(consolidated_visible_receipts if selective_filters_applied else consolidated_period_receipts),
            "payment_total": _money(consolidated_visible_payments if selective_filters_applied else consolidated_period_payments),
            "period_receipt_total": _money(consolidated_period_receipts),
            "period_payment_total": _money(consolidated_period_payments),
        },
        "opening_balance": _money(consolidated_opening),
        "closing_balance": _money(consolidated_closing),
        "account_summaries": account_summaries,
        "count": paginator.count,
        "page": page_obj.number,
        "page_size": page_size,
        "pages": paginator.num_pages,
        "next": None,
        "previous": None,
        "results": list(page_obj.object_list),
    }
    if len(refs) == 1:
        payload["opening_balance"] = _money(actual_opening[refs[0].key])
        payload["closing_balance"] = _money(closing_balances[refs[0].key])
    return payload
