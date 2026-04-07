from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Case, CharField, DecimalField, F, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce

from financial.models import account
from financial.profile_access import account_partytype
from payments.models.payment_core import PaymentVoucherHeader
from posting.models import Entry, EntryStatus, EntityStaticAccountMap, JournalLine, StaticAccount, TxnType
from receipts.models.receipt_core import ReceiptVoucherHeader
from reports.selectors.financial import normalize_scope_ids, resolve_date_window, resolve_scope_names
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
    TxnType.SALES_RETURN: ("sales", "Sales Return"),
    TxnType.PURCHASE_RETURN: ("purchase", "Purchase Return"),
    TxnType.PURCHASE_CREDIT_NOTE: ("purchase", "Purchase Credit Note"),
    TxnType.PURCHASE_DEBIT_NOTE: ("purchase", "Purchase Debit Note"),
    TxnType.JOURNAL_CASH: ("vouchers", "Cash Voucher"),
    TxnType.JOURNAL_BANK: ("vouchers", "Bank Voucher"),
    TxnType.RECEIPT: ("receipts", "Receipt Voucher"),
    TxnType.PAYMENT: ("payments", "Payment Voucher"),
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
        TxnType.JOURNAL: "voucher_detail",
        TxnType.JOURNAL_CASH: "voucher_detail",
        TxnType.JOURNAL_BANK: "voucher_detail",
        TxnType.RECEIPT: "receipt_voucher_detail",
        TxnType.PAYMENT: "payment_voucher_detail",
    }
    return mapping.get(txn_type, "journal_entry_detail")


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
    return Coalesce(
        Subquery(voucher_ref),
        Subquery(receipt_ref),
        Subquery(payment_ref),
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
    return {
        "entry_id": entry.id,
        "txn_type": entry.txn_type,
        "txn_type_name": entry.get_txn_type_display() if hasattr(entry, "get_txn_type_display") else entry.txn_type,
        "txn_id": entry.txn_id,
        "source_module": source_module,
        "drilldown_target": _drilldown_target_for_txn(entry.txn_type),
        "drilldown_params": {
            "id": entry.txn_id,
            "entry_id": entry.id,
            "entity": entity_id,
            "entityfinid": entityfin_id,
            "subentity": subentity_id,
        },
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


def _cashbook_target_accounts(entity_id, *, mode, cash_account_ids, bank_account_ids):
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
            opening = Decimal(getattr(row.ledger, "openingbdr", ZERO) or ZERO) - Decimal(
                getattr(row.ledger, "openingbcr", ZERO) or ZERO
            )
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
        .annotate(resolved_ledger_id=Coalesce(F("ledger_id"), F("account__ledger_id")))
        .select_related("entry", "account", "ledger", "account__ledger")
    )
    if entityfin_id:
        qs = qs.filter(entityfin_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(subentity_id=subentity_id)
    if to_date:
        qs = qs.filter(posting_date__lte=to_date)
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

    rows = []
    if single_account_mode:
        running = {ref.key: Decimal(actual_opening[ref.key]) for ref in refs}
        for line in visible_in_range:
            key = _cashbook_target_key(line)
            ref = ref_by_key.get(key)
            if ref is None:
                continue
            running[key] += _line_delta(line)
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
                    "running_balance": _money(running[key]),
                    "running_balance_scope": "account",
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
                    "running_balance": None,
                    "running_balance_scope": None,
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
        "running_balance_scope": "account" if single_account_mode else None,
        "balance_basis": "actual_account_movement",
        "balance_integrity": True,
        "balance_note": (
            "Running balance is shown only for a single scoped cash/bank account without selective filters; filtered or multi-account views suppress it to avoid misleading balances."
            if not single_account_mode
            else "Opening, movement, and closing balances are computed from all posted entries for the account."
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
