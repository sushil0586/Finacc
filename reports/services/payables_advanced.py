from __future__ import annotations

from bisect import insort_right
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Case, CharField, Count, DecimalField, Q, Sum, Value, When
from django.db.models.functions import Coalesce, Trim
from django.utils import timezone

from financial.profile_access import account_gstno
from purchase.models.purchase_ap import VendorSettlementLine
from purchase.models.purchase_core import PurchaseInvoiceHeader
from reports.selectors.financial import normalize_scope_ids
from reports.selectors.payables import (
    _open_item_balance_queryset,
    advance_vendor_summary,
    asof_open_item_balances,
    coerce_date,
    open_item_vendor_summary,
    period_bill_credit_totals,
    posted_payment_totals,
    q2,
    resolve_scope_dates,
    vendor_queryset,
)
from reports.services.payables import _drilldown_item, _iso_date, _report_meta_payload, _row_with_meta, _trace_payload

ZERO = Decimal("0.00")


def _sort_rows(rows, sort_by, sort_order):
    reverse = (sort_order or "asc").lower() == "desc"
    field = (sort_by or "").strip().lower()

    def key(row):
        value = row.get(field)
        if isinstance(value, (int, float, Decimal)):
            return Decimal(value)
        return str(value or "").lower()

    rows.sort(key=key, reverse=reverse)
    return rows


def _paginate(rows, page, page_size):
    total = len(rows)
    start = max((page - 1) * page_size, 0)
    return rows[start:start + page_size], total


def _stringify_amount_fields(rows, fields):
    for row in rows:
        for key in fields:
            row[key] = f"{q2(row.get(key) or ZERO):.2f}"
    return rows


def _normalized_sort_value(value):
    if isinstance(value, (int, float, Decimal)):
        return (0, Decimal(value))
    return (1, str(value or "").lower())


def _normalized_identifier(value):
    return str(value or "").strip()


def _collect_sorted_page_rows(*, rows, sort_by, sort_order, page, page_size):
    field = (sort_by or "").strip().lower()
    current_page = max(int(page or 1), 1)
    current_page_size = max(int(page_size or 1), 1)
    limit = current_page * current_page_size
    keep_descending = (sort_order or "asc").lower() == "desc"
    selected = []
    total_rows = 0

    for sequence, row in enumerate(rows):
        total_rows += 1
        key = _normalized_sort_value(row.get(field))
        # Preserve stable ordering for equal keys in both asc and desc modes.
        tie_breaker = -sequence if keep_descending else sequence
        ranked = (key, tie_breaker, row)
        insort_right(selected, ranked)
        if len(selected) > limit:
            if keep_descending:
                selected.pop(0)
            else:
                selected.pop()

    ordered_rows = [item[2] for item in selected]
    if keep_descending:
        ordered_rows.reverse()

    start = (current_page - 1) * current_page_size
    end = start + current_page_size
    return ordered_rows[start:end], total_rows


def _ap_compliance_risk_details(*, gstin: str | None, due_date, as_of):
    gstin = str(gstin or "").strip() or None
    days_overdue = (as_of - due_date).days
    if not gstin:
        return days_overdue, "HIGH", "Vendor GSTIN missing."
    if days_overdue > 90:
        return days_overdue, "MEDIUM", "Outstanding aging beyond 90 days."
    return days_overdue, "LOW", "No critical compliance signal."


def _ap_compliance_sort_mapping(sort_by: str | None, sort_order: str) -> list[str] | None:
    field = (sort_by or "days_overdue").strip().lower()
    descending = (sort_order or "desc").lower() == "desc"
    if field == "days_overdue":
        return ["effective_due_date", "id"] if descending else ["-effective_due_date", "-id"]
    if field == "due_date":
        return ["-effective_due_date", "-id"] if descending else ["effective_due_date", "id"]
    if field == "outstanding":
        return ["-outstanding_asof", "-id"] if descending else ["outstanding_asof", "id"]
    if field == "bill_number":
        return ["-purchase_number", "-supplier_invoice_number", "-id"] if descending else ["purchase_number", "supplier_invoice_number", "id"]
    return None


def build_ap_payment_forecast_report(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    from_date=None,
    to_date=None,
    as_of_date=None,
    sort_by=None,
    sort_order="asc",
    page=1,
    page_size=100,
    user=None,
):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    reference = coerce_date(as_of_date) or timezone.localdate()
    start_date, end_date = resolve_scope_dates(entityfin_id, from_date, to_date, as_of_date) if (from_date or to_date or entityfin_id) else (reference, reference + timedelta(days=30))
    if end_date is None:
        end_date = start_date + timedelta(days=30)
    if start_date is None:
        start_date = reference
    base_qs = (
        _open_item_balance_queryset(
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            upto_date=end_date,
        )
        .annotate(effective_due_date=Coalesce("due_date", "bill_date"))
        .filter(
            outstanding_asof__gt=ZERO,
            effective_due_date__isnull=False,
            effective_due_date__gte=start_date,
            effective_due_date__lte=end_date,
        )
    )
    summary = base_qs.aggregate(
        total_due=Coalesce(
            Sum("outstanding_asof"),
            Value(ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)),
        ),
        total_overdue=Coalesce(
            Sum(
                Case(
                    When(effective_due_date__lt=reference, then="outstanding_asof"),
                    default=Value(ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            ),
            Value(ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)),
        ),
        next_7=Coalesce(
            Sum(
                Case(
                    When(
                        effective_due_date__gte=reference,
                        effective_due_date__lte=reference + timedelta(days=7),
                        then="outstanding_asof",
                    ),
                    default=Value(ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            ),
            Value(ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)),
        ),
        next_30=Coalesce(
            Sum(
                Case(
                    When(
                        effective_due_date__gte=reference,
                        effective_due_date__lte=reference + timedelta(days=30),
                        then="outstanding_asof",
                    ),
                    default=Value(ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            ),
            Value(ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)),
        ),
    )
    grouped_rows = list(
        base_qs.values("effective_due_date").annotate(
            vendor_count=Count("vendor_id", distinct=True),
            bill_count=Count("id"),
            due_amount=Coalesce(
                Sum("outstanding_asof"),
                Value(ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)),
            ),
            overdue_amount=Coalesce(
                Sum(
                    Case(
                        When(effective_due_date__lt=reference, then="outstanding_asof"),
                        default=Value(ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)),
                        output_field=DecimalField(max_digits=14, decimal_places=2),
                    )
                ),
                Value(ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)),
            ),
        )
    )
    sample_vendor_names: dict = defaultdict(list)
    sample_bill_numbers: dict = defaultdict(list)
    for sample in (
        base_qs.order_by("effective_due_date", "id")
        .values("effective_due_date", "vendor__accountname", "purchase_number", "supplier_invoice_number")
        .iterator(chunk_size=2000)
    ):
        due_date = sample["effective_due_date"]
        vendor_name = str(sample.get("vendor__accountname") or "").strip()
        bill_number = str(sample.get("purchase_number") or sample.get("supplier_invoice_number") or "").strip()
        if vendor_name and vendor_name not in sample_vendor_names[due_date] and len(sample_vendor_names[due_date]) < 3:
            sample_vendor_names[due_date].append(vendor_name)
        if bill_number and bill_number not in sample_bill_numbers[due_date] and len(sample_bill_numbers[due_date]) < 5:
            sample_bill_numbers[due_date].append(bill_number)

    def iter_rows():
        for values in grouped_rows:
            due_date = values["effective_due_date"]
            days_to_due = (due_date - reference).days
            if days_to_due < 0:
                payment_band = "Overdue"
            elif days_to_due <= 7:
                payment_band = "Next 7 Days"
            elif days_to_due <= 30:
                payment_band = "Next 30 Days"
            else:
                payment_band = "Planned"
            due_amount = q2(values["due_amount"])
            overdue_amount = q2(values["overdue_amount"])
            row = {
                "due_date": due_date,
                "vendor_count": int(values["vendor_count"] or 0),
                "bill_count": int(values["bill_count"] or 0),
                "due_amount": due_amount,
                "overdue_amount": overdue_amount,
                "next_7_days_amount": due_amount if payment_band == "Next 7 Days" else ZERO,
                "next_30_days_amount": due_amount if payment_band in {"Next 7 Days", "Next 30 Days"} else ZERO,
                "payment_band": payment_band,
                "days_to_due": days_to_due,
                "sample_vendor_names": list(sample_vendor_names.get(due_date, [])),
                "sample_bill_numbers": list(sample_bill_numbers.get(due_date, [])),
            }
            drilldown = {
                "forecast_detail": {
                    "label": "Details",
                    "target": "ap_payment_forecast_detail",
                    "kind": "detail",
                    "params": {
                        "due_date": _iso_date(due_date),
                        "payment_band": payment_band,
                        "days_to_due": days_to_due,
                        "vendor_count": int(values["vendor_count"] or 0),
                        "bill_count": int(values["bill_count"] or 0),
                        "due_amount": f"{due_amount:.2f}",
                        "overdue_amount": f"{overdue_amount:.2f}",
                    },
                },
                "upcoming_payments_calendar": _drilldown_item(
                    label="Due Window",
                    target="upcoming_payments_calendar",
                    params={
                        "entity": entity_id,
                        "entityfinid": entityfin_id,
                        "subentity": subentity_id,
                        "from_date": _iso_date(due_date),
                        "to_date": _iso_date(due_date),
                        "as_of_date": _iso_date(reference),
                        "overdue_only": payment_band == "Overdue",
                    },
                    report_code="upcoming_payments_calendar",
                    kind="report",
                ),
                "vendor_outstanding": _drilldown_item(
                    label="Vendor Outstanding",
                    target="vendor_outstanding",
                    params={
                        "entity": entity_id,
                        "entityfinid": entityfin_id,
                        "subentity": subentity_id,
                        "from_date": _iso_date(start_date),
                        "to_date": _iso_date(reference),
                        "as_of_date": _iso_date(reference),
                    },
                    report_code="vendor_outstanding",
                    kind="report",
                ),
                "ap_aging": _drilldown_item(
                    label="AP Aging",
                    target="ap_aging",
                    params={
                        "entity": entity_id,
                        "entityfinid": entityfin_id,
                        "subentity": subentity_id,
                        "as_of_date": _iso_date(reference),
                        "view": "invoice",
                    },
                    report_code="ap_aging",
                    kind="report",
                ),
            }
            yield _row_with_meta(
                row,
                drilldown=drilldown,
                trace=_trace_payload(
                    source="ap_payment_forecast",
                    due_date=_iso_date(due_date),
                    payment_band=payment_band,
                    sample_vendor_names=row["sample_vendor_names"],
                    sample_bill_numbers=row["sample_bill_numbers"],
                ),
            )

    paged_rows, total_rows = _collect_sorted_page_rows(
        rows=iter_rows(),
        sort_by=sort_by or "due_date",
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    _stringify_amount_fields(paged_rows, ("due_amount", "overdue_amount", "next_7_days_amount", "next_30_days_amount"))

    return {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "from_date": start_date,
        "to_date": end_date,
        "as_of_date": reference,
        "rows": paged_rows,
        "totals": {
            "due_amount": f"{q2(summary['total_due'] or ZERO):.2f}",
            "overdue_amount": f"{q2(summary['total_overdue'] or ZERO):.2f}",
            "next_7_days_amount": f"{q2(summary['next_7'] or ZERO):.2f}",
            "next_30_days_amount": f"{q2(summary['next_30'] or ZERO):.2f}",
        },
        "summary": {
            "forecast_days": max((end_date - start_date).days + 1, 0),
            "date_bands": len(grouped_rows),
        },
        "pagination": {"page": page, "page_size": page_size, "total_rows": total_rows, "paginated": True},
        **_report_meta_payload(
            report_code="ap_payment_forecast",
            report_name="AP Payment Forecast",
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            from_date=start_date,
            to_date=end_date,
            as_of_date=reference,
            required_menu_code="reports.payables.ap_payment_forecast",
            required_permissions=["reports.payables.view"],
            user=user,
        ),
    }


def build_vendor_reconciliation_statement_report(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    from_date=None,
    to_date=None,
    as_of_date=None,
    search=None,
    sort_by=None,
    sort_order="desc",
    page=1,
    page_size=100,
    user=None,
):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    start_date, end_date = resolve_scope_dates(entityfin_id, from_date, to_date, as_of_date)
    as_of = coerce_date(as_of_date) or end_date
    opening_cutoff = start_date - timedelta(days=1) if start_date else None
    vendors = list(vendor_queryset(entity_id=entity_id, search=search))
    vendor_map = {v.id: v for v in vendors}
    vendor_ids = set(vendor_map.keys())
    open_item_summary = {}
    opening_items = {}
    opening_advances = {}
    payment_totals = {}
    bill_totals = defaultdict(lambda: ZERO)
    note_totals = defaultdict(lambda: ZERO)
    if vendor_ids:
        aggregated_rows = (
            _open_item_balance_queryset(
                entity_id=entity_id,
                entityfin_id=entityfin_id,
                subentity_id=subentity_id,
                upto_date=as_of,
                vendor_ids=vendor_ids,
            )
            .values("vendor_id")
            .annotate(
                invoiced=Coalesce(
                    Sum(
                        Case(
                            When(original_amount__gte=ZERO, then="original_amount"),
                            default=Value(ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)),
                            output_field=DecimalField(max_digits=14, decimal_places=2),
                        )
                    ),
                    Value(ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)),
                ),
                notes=Coalesce(
                    Sum(
                        Case(
                            When(original_amount__lt=ZERO, then=-1 * Coalesce("original_amount", Value(ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)))),
                            default=Value(ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)),
                            output_field=DecimalField(max_digits=14, decimal_places=2),
                        )
                    ),
                    Value(ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)),
                ),
                settled=Coalesce(
                    Sum("settled_asof"),
                    Value(ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)),
                ),
                closing_balance=Coalesce(
                    Sum("outstanding_asof"),
                    Value(ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)),
                ),
            )
        )
        open_item_summary = {
            row["vendor_id"]: {
                "invoiced": q2(row["invoiced"]),
                "notes": q2(row["notes"]),
                "settled": q2(row["settled"]),
                "closing_balance": q2(row["closing_balance"]),
            }
            for row in aggregated_rows
        }
        if opening_cutoff is not None:
            opening_items = open_item_vendor_summary(
                entity_id=entity_id,
                entityfin_id=entityfin_id,
                subentity_id=subentity_id,
                upto_date=opening_cutoff,
                vendor_ids=vendor_ids,
            )
            opening_advances = advance_vendor_summary(
                entity_id=entity_id,
                entityfin_id=entityfin_id,
                subentity_id=subentity_id,
                upto_date=opening_cutoff,
                vendor_ids=vendor_ids,
            )
            bill_totals, note_totals, _last_bill_dates = period_bill_credit_totals(
                entity_id=entity_id,
                entityfin_id=entityfin_id,
                subentity_id=subentity_id,
                from_date=start_date,
                to_date=as_of,
                vendor_ids=vendor_ids,
            )
            payment_totals, _last_payment_dates = posted_payment_totals(
                entity_id=entity_id,
                entityfin_id=entityfin_id,
                subentity_id=subentity_id,
                from_date=start_date,
                to_date=as_of,
            )

    totals = defaultdict(lambda: ZERO)

    def iter_rows():
        for vendor in vendors:
            vendor_id = vendor.id
            summary = open_item_summary.get(vendor_id)
            opening_summary = opening_items.get(vendor_id, {})
            opening_balance = q2(opening_summary.get("outstanding_total", ZERO) - opening_advances.get(vendor_id, ZERO))
            invoiced_amount = q2(bill_totals.get(vendor_id, ZERO))
            notes_amount = q2(note_totals.get(vendor_id, ZERO))
            settled_amount = q2(payment_totals.get(vendor_id, ZERO))
            closing_balance = q2(summary["closing_balance"]) if summary else ZERO
            if (
                closing_balance == ZERO
                and opening_balance == ZERO
                and invoiced_amount == ZERO
                and notes_amount == ZERO
                and settled_amount == ZERO
            ):
                continue
            status = "Reconciled" if closing_balance == ZERO else "Mismatch"
            row = {
                "vendor_id": vendor_id,
                "vendor_name": vendor.effective_accounting_name,
                "vendor_code": vendor.effective_accounting_code,
                "opening_balance": opening_balance,
                "invoiced": invoiced_amount,
                "notes": notes_amount,
                "settled": settled_amount,
                "closing_balance": closing_balance,
                "status": status,
            }
            for key in ("opening_balance", "invoiced", "notes", "settled", "closing_balance"):
                totals[key] = q2(totals[key] + row[key])
            drilldown = {
                "reconciliation_detail": {
                    "label": "Details",
                    "target": "vendor_reconciliation_detail",
                    "kind": "detail",
                    "params": {
                        "vendor_id": vendor_id,
                        "vendor_name": vendor.effective_accounting_name,
                        "vendor_code": vendor.effective_accounting_code,
                        "status": status,
                        "opening_balance": f"{opening_balance:.2f}",
                        "invoiced": f"{invoiced_amount:.2f}",
                        "notes": f"{notes_amount:.2f}",
                        "settled": f"{settled_amount:.2f}",
                        "closing_balance": f"{closing_balance:.2f}",
                    },
                },
                "vendor_ledger_statement": _drilldown_item(
                    label="Vendor Ledger",
                    target="vendor_ledger_statement",
                    params={
                        "entity": entity_id,
                        "entityfinid": entityfin_id,
                        "subentity": subentity_id,
                        "vendor": vendor_id,
                        "from_date": _iso_date(start_date),
                        "to_date": _iso_date(as_of),
                    },
                    report_code="vendor_ledger_statement",
                    kind="report",
                ),
                "vendor_outstanding": _drilldown_item(
                    label="Vendor Outstanding",
                    target="vendor_outstanding",
                    params={
                        "entity": entity_id,
                        "entityfinid": entityfin_id,
                        "subentity": subentity_id,
                        "vendor": vendor_id,
                        "from_date": _iso_date(start_date),
                        "to_date": _iso_date(as_of),
                        "as_of_date": _iso_date(as_of),
                    },
                    report_code="vendor_outstanding",
                    kind="report",
                ),
                "ap_aging": _drilldown_item(
                    label="AP Aging",
                    target="ap_aging",
                    params={
                        "entity": entity_id,
                        "entityfinid": entityfin_id,
                        "subentity": subentity_id,
                        "vendor": vendor_id,
                        "as_of_date": _iso_date(as_of),
                        "view": "invoice",
                    },
                    report_code="ap_aging",
                    kind="report",
                ),
            }
            yield _row_with_meta(
                row,
                drilldown=drilldown,
                trace=_trace_payload(
                    source="vendor_reconciliation_statement",
                    vendor_id=vendor_id,
                    vendor_name=vendor.effective_accounting_name,
                    status=status,
                ),
            )

    paged_rows, total_rows = _collect_sorted_page_rows(
        rows=iter_rows(),
        sort_by=sort_by or "closing_balance",
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    _stringify_amount_fields(paged_rows, ("opening_balance", "invoiced", "notes", "settled", "closing_balance"))

    return {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "from_date": start_date,
        "to_date": end_date,
        "as_of_date": as_of,
        "rows": paged_rows,
        "totals": {k: f"{q2(v):.2f}" for k, v in totals.items()},
        "summary": {"vendor_count": total_rows},
        "pagination": {"page": page, "page_size": page_size, "total_rows": total_rows, "paginated": True},
        **_report_meta_payload(
            report_code="vendor_reconciliation_statement",
            report_name="Vendor Reconciliation Statement",
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            from_date=start_date,
            to_date=end_date,
            as_of_date=as_of,
            required_menu_code="reports.payables.vendor_reconciliation_statement",
            required_permissions=["reports.payables.view"],
            user=user,
        ),
    }


def build_grn_invoice_posting_exceptions_report(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    from_date=None,
    to_date=None,
    search=None,
    sort_by=None,
    sort_order="desc",
    page=1,
    page_size=100,
    user=None,
):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    start_date, end_date = resolve_scope_dates(entityfin_id, from_date, to_date, None)
    qs = PurchaseInvoiceHeader.objects.filter(entity_id=entity_id, bill_date__range=(start_date, end_date))
    if entityfin_id:
        qs = qs.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(subentity_id=subentity_id)
    if search:
        qs = qs.filter(
            Q(purchase_number__icontains=search)
            | Q(supplier_invoice_number__icontains=search)
            | Q(vendor_name__icontains=search)
        )
    headers = list(
        qs.values(
            "id",
            "vendor_id",
            "purchase_number",
            "supplier_invoice_number",
            "bill_date",
            "status",
            "grand_total",
        ).order_by("-bill_date", "-id")[:500]
    )
    duplicate_counter = Counter(
        (
            h["vendor_id"],
            _normalized_identifier(h.get("supplier_invoice_number")).lower(),
            str(q2(h.get("grand_total") or ZERO)),
        )
        for h in headers
        if _normalized_identifier(h.get("supplier_invoice_number"))
    )

    rows = []
    issue_counts = Counter()
    for header in headers:
        issue_type = None
        issue_message = None
        supplier_invoice_number = _normalized_identifier(header.get("supplier_invoice_number"))
        if header["status"] != PurchaseInvoiceHeader.Status.POSTED:
            issue_type = "NOT_POSTED"
            issue_message = "Invoice is not posted."
        elif not supplier_invoice_number:
            issue_type = "MISSING_SUPPLIER_INVOICE"
            issue_message = "Supplier invoice number is missing."
        elif duplicate_counter[(
            header["vendor_id"],
            supplier_invoice_number.lower(),
            str(q2(header.get("grand_total") or ZERO)),
        )] > 1:
            issue_type = "POSSIBLE_DUPLICATE"
            issue_message = "Same vendor + supplier invoice + amount appears multiple times."
        if not issue_type:
            continue
        issue_counts[issue_type] += 1
        grand_total = q2(header.get("grand_total") or ZERO)
        posting_status = "Posted" if header["status"] == PurchaseInvoiceHeader.Status.POSTED else "Pending"
        row = {
            "header_id": header["id"],
            "vendor_id": header["vendor_id"],
            "purchase_number": header["purchase_number"],
            "supplier_invoice_number": supplier_invoice_number or "-",
            "bill_date": header["bill_date"],
            "status": header["status"],
            "posting_status": posting_status,
            "grand_total": grand_total,
            "issue_type": issue_type,
            "issue_message": issue_message,
        }
        rows.append(
            _row_with_meta(
                row,
                drilldown={
                    "grn_exception_detail": {
                        "label": "Details",
                        "target": "grn_exception_detail",
                        "kind": "detail",
                        "params": {
                            "header_id": header["id"],
                            "vendor_id": header["vendor_id"],
                            "purchase_number": header["purchase_number"],
                            "supplier_invoice_number": supplier_invoice_number or "-",
                            "bill_date": _iso_date(header["bill_date"]),
                            "status": header["status"],
                            "posting_status": posting_status,
                            "grand_total": f"{grand_total:.2f}",
                            "issue_type": issue_type,
                            "issue_message": issue_message,
                        },
                    },
                    "bill_detail": _drilldown_item(
                        label="Purchase Document Detail",
                        target="purchase_document_detail",
                        params={"id": header["id"], "entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id},
                    ),
                    "vendor_outstanding": _drilldown_item(
                        label="Vendor Outstanding",
                        target="vendor_outstanding",
                        report_code="vendor_outstanding",
                        params={
                            "entity": entity_id,
                            "entityfinid": entityfin_id,
                            "subentity": subentity_id,
                            "vendor": header["vendor_id"],
                            "as_of_date": _iso_date(end_date),
                            "view": "detailed",
                            "show_not_due": True,
                        },
                        kind="report",
                    ),
                    "ap_aging": _drilldown_item(
                        label="AP Aging",
                        target="ap_aging",
                        report_code="ap_aging",
                        params={
                            "entity": entity_id,
                            "entityfinid": entityfin_id,
                            "subentity": subentity_id,
                            "vendor": header["vendor_id"],
                            "as_of_date": _iso_date(end_date),
                            "view": "invoice",
                        },
                        kind="report",
                    ),
                },
                trace=_trace_payload(
                    source="grn_invoice_posting_exceptions",
                    header_id=header["id"],
                    vendor_id=header["vendor_id"],
                    issue_type=issue_type,
                ),
            )
        )

    _sort_rows(rows, sort_by or "bill_date", sort_order)
    paged_rows, total_rows = _paginate(rows, page, page_size)
    _stringify_amount_fields(paged_rows, ("grand_total",))
    return {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "from_date": start_date,
        "to_date": end_date,
        "rows": paged_rows,
        "totals": {"grand_total": f"{q2(sum((q2(r['grand_total']) for r in rows), ZERO)):.2f}"},
        "summary": {"issue_counts": dict(issue_counts), "issue_count_total": total_rows},
        "pagination": {"page": page, "page_size": page_size, "total_rows": total_rows, "paginated": True},
        **_report_meta_payload(
            report_code="grn_invoice_posting_exceptions",
            report_name="GRN vs Invoice vs Posting Exceptions",
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            from_date=start_date,
            to_date=end_date,
            required_menu_code="reports.payables.grn_invoice_posting_exceptions",
            required_permissions=["reports.payables.view"],
            user=user,
        ),
    }


def build_ap_compliance_aging_report(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    as_of_date=None,
    search=None,
    sort_by=None,
    sort_order="desc",
    page=1,
    page_size=100,
    user=None,
):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    as_of = coerce_date(as_of_date) or timezone.localdate()
    base_qs = (
        _open_item_balance_queryset(
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            upto_date=as_of,
            search=search,
        )
        .annotate(
            effective_due_date=Coalesce("due_date", "bill_date"),
            gstin_value=Trim(
                Coalesce("vendor__compliance_profile__gstno", Value("", output_field=CharField()))
            ),
        )
        .filter(outstanding_asof__gt=ZERO)
        .exclude(effective_due_date__isnull=True)
    )
    medium_cutoff = as_of - timedelta(days=90)
    summary = base_qs.aggregate(
        total_outstanding=Coalesce(
            Sum("outstanding_asof"),
            Value(ZERO, output_field=DecimalField(max_digits=14, decimal_places=2)),
        ),
        row_count=Count("id"),
        high_count=Count("id", filter=Q(gstin_value="")),
        medium_count=Count("id", filter=~Q(gstin_value="") & Q(effective_due_date__lt=medium_cutoff)),
        low_count=Count("id", filter=~Q(gstin_value="") & Q(effective_due_date__gte=medium_cutoff)),
    )
    db_ordering = _ap_compliance_sort_mapping(sort_by, sort_order)
    paged_rows = []
    total_rows = int(summary["row_count"] or 0)
    if db_ordering is not None:
        current_page = max(int(page or 1), 1)
        current_page_size = max(int(page_size or 1), 1)
        start = (current_page - 1) * current_page_size
        stop = start + current_page_size
        page_items = list(base_qs.order_by(*db_ordering)[start:stop])
        for item in page_items:
            vendor = item.vendor
            gstin = str(getattr(item, "gstin_value", "") or "").strip()
            due_date = item.effective_due_date
            days_overdue, risk, reason = _ap_compliance_risk_details(gstin=gstin or None, due_date=due_date, as_of=as_of)
            outstanding = q2(item.outstanding_asof)
            row = {
                "vendor_id": item.vendor_id,
                "header_id": item.header_id,
                "vendor_name": vendor.effective_accounting_name,
                "vendor_code": vendor.effective_accounting_code,
                "gstin": gstin or "-",
                "bill_number": item.purchase_number or item.supplier_invoice_number or f"BILL-{item.id}",
                "due_date": due_date,
                "days_overdue": days_overdue,
                "outstanding": outstanding,
                "compliance_risk": risk,
                "risk_reason": reason,
            }
            paged_rows.append(
                _row_with_meta(
                    row,
                    drilldown={
                        "compliance_detail": {
                            "label": "Details",
                            "target": "ap_compliance_detail",
                            "kind": "detail",
                            "params": {
                                "vendor_id": item.vendor_id,
                                "header_id": item.header_id,
                                "bill_number": row["bill_number"],
                                "due_date": _iso_date(due_date),
                                "days_overdue": days_overdue,
                                "compliance_risk": risk,
                                "risk_reason": reason,
                                "outstanding": f"{outstanding:.2f}",
                            },
                        },
                        "bill_detail": _drilldown_item(
                            label="Purchase Document Detail",
                            target="purchase_document_detail",
                            params={"id": item.header_id, "entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id},
                        ),
                        "vendor_outstanding": _drilldown_item(
                            label="Vendor Outstanding",
                            target="vendor_outstanding",
                            report_code="vendor_outstanding",
                            params={
                                "entity": entity_id,
                                "entityfinid": entityfin_id,
                                "subentity": subentity_id,
                                "vendor": item.vendor_id,
                                "as_of_date": _iso_date(as_of),
                                "view": "detailed",
                                "show_not_due": True,
                            },
                            kind="report",
                        ),
                        "ap_aging": _drilldown_item(
                            label="AP Aging",
                            target="ap_aging",
                            report_code="ap_aging",
                            params={
                                "entity": entity_id,
                                "entityfinid": entityfin_id,
                                "subentity": subentity_id,
                                "vendor": item.vendor_id,
                                "as_of_date": _iso_date(as_of),
                                "view": "invoice",
                            },
                            kind="report",
                        ),
                        "vendor_ledger_statement": _drilldown_item(
                            label="Vendor Ledger",
                            target="vendor_ledger_statement",
                            report_code="vendor_ledger_statement",
                            params={
                                "entity": entity_id,
                                "entityfinid": entityfin_id,
                                "subentity": subentity_id,
                                "vendor": item.vendor_id,
                                "from_date": _iso_date(as_of),
                                "to_date": _iso_date(as_of),
                            },
                            kind="report",
                        ),
                    },
                    trace=_trace_payload(
                        source="ap_compliance_aging",
                        vendor_id=item.vendor_id,
                        header_id=item.header_id,
                        risk=risk,
                    ),
                )
            )
    else:
        risk_counts = Counter()
        total_outstanding = ZERO

        def iter_rows():
            nonlocal total_outstanding
            for item, _settled, outstanding in asof_open_item_balances(
                entity_id=entity_id,
                entityfin_id=entityfin_id,
                subentity_id=subentity_id,
                upto_date=as_of,
                search=search,
            ):
                outstanding = q2(outstanding)
                if outstanding <= ZERO:
                    continue
                due_date = item.due_date or item.bill_date
                if not due_date:
                    continue
                vendor = item.vendor
                gstin = str(account_gstno(vendor) or "").strip()
                days_overdue, risk, reason = _ap_compliance_risk_details(gstin=gstin, due_date=due_date, as_of=as_of)
                risk_counts[risk] += 1
                total_outstanding = q2(total_outstanding + outstanding)
                row = {
                    "vendor_id": item.vendor_id,
                    "header_id": item.header_id,
                    "vendor_name": vendor.effective_accounting_name,
                    "vendor_code": vendor.effective_accounting_code,
                    "gstin": gstin or "-",
                    "bill_number": item.purchase_number or item.supplier_invoice_number or f"BILL-{item.id}",
                    "due_date": due_date,
                    "days_overdue": days_overdue,
                    "outstanding": outstanding,
                    "compliance_risk": risk,
                    "risk_reason": reason,
                }
                yield _row_with_meta(
                    row,
                    drilldown={
                        "compliance_detail": {
                            "label": "Details",
                            "target": "ap_compliance_detail",
                            "kind": "detail",
                            "params": {
                                "vendor_id": item.vendor_id,
                                "header_id": item.header_id,
                                "bill_number": row["bill_number"],
                                "due_date": _iso_date(due_date),
                                "days_overdue": days_overdue,
                                "compliance_risk": risk,
                                "risk_reason": reason,
                                "outstanding": f"{outstanding:.2f}",
                            },
                        },
                        "bill_detail": _drilldown_item(
                            label="Purchase Document Detail",
                            target="purchase_document_detail",
                            params={"id": item.header_id, "entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id},
                        ),
                        "vendor_outstanding": _drilldown_item(
                            label="Vendor Outstanding",
                            target="vendor_outstanding",
                            report_code="vendor_outstanding",
                            params={
                                "entity": entity_id,
                                "entityfinid": entityfin_id,
                                "subentity": subentity_id,
                                "vendor": item.vendor_id,
                                "as_of_date": _iso_date(as_of),
                                "view": "detailed",
                                "show_not_due": True,
                            },
                            kind="report",
                        ),
                        "ap_aging": _drilldown_item(
                            label="AP Aging",
                            target="ap_aging",
                            report_code="ap_aging",
                            params={
                                "entity": entity_id,
                                "entityfinid": entityfin_id,
                                "subentity": subentity_id,
                                "vendor": item.vendor_id,
                                "as_of_date": _iso_date(as_of),
                                "view": "invoice",
                            },
                            kind="report",
                        ),
                        "vendor_ledger_statement": _drilldown_item(
                            label="Vendor Ledger",
                            target="vendor_ledger_statement",
                            report_code="vendor_ledger_statement",
                            params={
                                "entity": entity_id,
                                "entityfinid": entityfin_id,
                                "subentity": subentity_id,
                                "vendor": item.vendor_id,
                                "from_date": _iso_date(as_of),
                                "to_date": _iso_date(as_of),
                            },
                            kind="report",
                        ),
                    },
                    trace=_trace_payload(
                        source="ap_compliance_aging",
                        vendor_id=item.vendor_id,
                        header_id=item.header_id,
                        risk=risk,
                    ),
                )

        paged_rows, total_rows = _collect_sorted_page_rows(
            rows=iter_rows(),
            sort_by=sort_by or "days_overdue",
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )
        summary = {
            "total_outstanding": total_outstanding,
            "row_count": total_rows,
            "high_count": risk_counts.get("HIGH", 0),
            "medium_count": risk_counts.get("MEDIUM", 0),
            "low_count": risk_counts.get("LOW", 0),
        }

    _stringify_amount_fields(paged_rows, ("outstanding",))
    return {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "as_of_date": as_of,
        "rows": paged_rows,
        "totals": {"outstanding": f"{q2(summary['total_outstanding'] or ZERO):.2f}"},
        "summary": {
            "risk_counts": {
                "HIGH": int(summary["high_count"] or 0),
                "MEDIUM": int(summary["medium_count"] or 0),
                "LOW": int(summary["low_count"] or 0),
            },
            "row_count": total_rows,
        },
        "pagination": {"page": page, "page_size": page_size, "total_rows": total_rows, "paginated": True},
        **_report_meta_payload(
            report_code="ap_compliance_aging",
            report_name="AP Compliance Aging",
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            as_of_date=as_of,
            required_menu_code="reports.payables.ap_compliance_aging",
            required_permissions=["reports.payables.view"],
            user=user,
        ),
    }


def build_duplicate_anomalous_bill_detection_report(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    from_date=None,
    to_date=None,
    search=None,
    sort_by=None,
    sort_order="desc",
    page=1,
    page_size=100,
    user=None,
):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    start_date, end_date = resolve_scope_dates(entityfin_id, from_date, to_date, None)
    qs = PurchaseInvoiceHeader.objects.filter(entity_id=entity_id, bill_date__range=(start_date, end_date))
    if entityfin_id:
        qs = qs.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(subentity_id=subentity_id)
    if search:
        qs = qs.filter(
            Q(vendor_name__icontains=search)
            | Q(supplier_invoice_number__icontains=search)
            | Q(purchase_number__icontains=search)
        )
    headers = list(
        qs.values(
            "id",
            "vendor_id",
            "vendor_name",
            "vendor__ledger__name",
            "vendor__ledger__ledger_code",
            "supplier_invoice_number",
            "purchase_number",
            "bill_date",
            "grand_total",
        ).order_by("-bill_date", "-id")[:1000]
    )
    duplicate_counter = Counter(
        (
            h["vendor_id"],
            _normalized_identifier(h.get("supplier_invoice_number")).lower(),
            str(q2(h.get("grand_total") or ZERO)),
        )
        for h in headers
        if _normalized_identifier(h.get("supplier_invoice_number"))
    )
    amounts = [q2(h.get("grand_total") or ZERO) for h in headers]
    median = sorted(amounts)[len(amounts) // 2] if amounts else ZERO
    anomaly_rows = []
    anomaly_counts = Counter()
    for header in headers:
        anomaly_type = None
        reason = None
        score = 0
        dup_key = (
            header["vendor_id"],
            _normalized_identifier(header.get("supplier_invoice_number")).lower(),
            str(q2(header.get("grand_total") or ZERO)),
        )
        supplier_invoice_number = _normalized_identifier(header.get("supplier_invoice_number"))
        if supplier_invoice_number and duplicate_counter[dup_key] > 1:
            anomaly_type = "POSSIBLE_DUPLICATE"
            reason = "Duplicate vendor + supplier invoice + amount combination."
            score = min(100, duplicate_counter[dup_key] * 25)
        elif median > ZERO and q2(header.get("grand_total") or ZERO) >= (median * Decimal("10")):
            anomaly_type = "AMOUNT_OUTLIER"
            reason = "Bill amount is significantly higher than period median."
            score = 75
        if not anomaly_type:
            continue
        anomaly_counts[anomaly_type] += 1
        grand_total = q2(header.get("grand_total") or ZERO)
        row = {
            "header_id": header["id"],
            "vendor_id": header["vendor_id"],
            "purchase_number": header.get("purchase_number") or "-",
            "vendor_name": header.get("vendor__ledger__name") or header.get("vendor_name") or "-",
            "vendor_code": header.get("vendor__ledger__ledger_code") or "-",
            "supplier_invoice_number": supplier_invoice_number or "-",
            "bill_date": header["bill_date"],
            "grand_total": grand_total,
            "anomaly_type": anomaly_type,
            "anomaly_score": score,
            "anomaly_reason": reason,
        }
        anomaly_rows.append(
            _row_with_meta(
                row,
                drilldown={
                    "duplicate_bill_detail": {
                        "label": "Details",
                        "target": "duplicate_bill_detail",
                        "kind": "detail",
                        "params": {
                            "header_id": header["id"],
                            "vendor_id": header["vendor_id"],
                            "purchase_number": row["purchase_number"],
                            "vendor_name": row["vendor_name"],
                            "vendor_code": row["vendor_code"],
                            "supplier_invoice_number": row["supplier_invoice_number"],
                            "bill_date": _iso_date(header["bill_date"]),
                            "grand_total": f"{grand_total:.2f}",
                            "anomaly_type": anomaly_type,
                            "anomaly_score": score,
                            "anomaly_reason": reason,
                        },
                    },
                    "bill_detail": _drilldown_item(
                        label="Purchase Document Detail",
                        target="purchase_document_detail",
                        params={"id": header["id"], "entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id},
                    ),
                    "vendor_outstanding": _drilldown_item(
                        label="Vendor Outstanding",
                        target="vendor_outstanding",
                        report_code="vendor_outstanding",
                        params={
                            "entity": entity_id,
                            "entityfinid": entityfin_id,
                            "subentity": subentity_id,
                            "vendor": header["vendor_id"],
                            "as_of_date": _iso_date(end_date),
                            "view": "detailed",
                            "show_not_due": True,
                        },
                        kind="report",
                    ),
                    "ap_aging": _drilldown_item(
                        label="AP Aging",
                        target="ap_aging",
                        report_code="ap_aging",
                        params={
                            "entity": entity_id,
                            "entityfinid": entityfin_id,
                            "subentity": subentity_id,
                            "vendor": header["vendor_id"],
                            "as_of_date": _iso_date(end_date),
                            "view": "invoice",
                        },
                        kind="report",
                    ),
                },
                trace=_trace_payload(
                    source="duplicate_anomalous_bill_detection",
                    header_id=header["id"],
                    vendor_id=header["vendor_id"],
                    anomaly_type=anomaly_type,
                ),
            )
        )
    _sort_rows(anomaly_rows, sort_by or "bill_date", sort_order)
    paged_rows, total_rows = _paginate(anomaly_rows, page, page_size)
    _stringify_amount_fields(paged_rows, ("grand_total",))
    return {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "from_date": start_date,
        "to_date": end_date,
        "rows": paged_rows,
        "totals": {"grand_total": f"{q2(sum((q2(r['grand_total']) for r in anomaly_rows), ZERO)):.2f}"},
        "summary": {"anomaly_counts": dict(anomaly_counts), "anomaly_count_total": total_rows},
        "pagination": {"page": page, "page_size": page_size, "total_rows": total_rows, "paginated": True},
        **_report_meta_payload(
            report_code="duplicate_anomalous_bill_detection",
            report_name="Duplicate / Anomalous Bill Detection",
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            from_date=start_date,
            to_date=end_date,
            required_menu_code="reports.payables.duplicate_anomalous_bill_detection",
            required_permissions=["reports.payables.view"],
            user=user,
        ),
    }
