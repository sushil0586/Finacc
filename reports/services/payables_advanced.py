from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from financial.profile_access import account_gstno
from purchase.models.purchase_ap import VendorSettlementLine
from purchase.models.purchase_core import PurchaseInvoiceHeader
from reports.selectors.financial import normalize_scope_ids
from reports.selectors.payables import asof_open_item_balances, coerce_date, q2, resolve_scope_dates, vendor_queryset
from reports.services.payables import _iso_date, _report_meta_payload

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

    vendors = list(vendor_queryset(entity_id=entity_id))
    vendor_ids = {vendor.id for vendor in vendors}
    open_items = asof_open_item_balances(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=end_date,
        vendor_ids=vendor_ids,
    )

    day_buckets = defaultdict(lambda: {"vendor_ids": set(), "bill_count": 0, "due_amount": ZERO, "overdue_amount": ZERO})
    total_due = ZERO
    total_overdue = ZERO
    next_7 = ZERO
    next_30 = ZERO

    for item, _settled, outstanding in open_items:
        outstanding = q2(outstanding)
        if outstanding <= ZERO:
            continue
        due_date = item.due_date or item.bill_date
        if due_date is None or due_date < start_date or due_date > end_date:
            continue
        row = day_buckets[due_date]
        row["vendor_ids"].add(item.vendor_id)
        row["bill_count"] += 1
        row["due_amount"] = q2(row["due_amount"] + outstanding)
        if due_date < reference:
            row["overdue_amount"] = q2(row["overdue_amount"] + outstanding)
            total_overdue = q2(total_overdue + outstanding)
        if 0 <= (due_date - reference).days <= 7:
            next_7 = q2(next_7 + outstanding)
        if 0 <= (due_date - reference).days <= 30:
            next_30 = q2(next_30 + outstanding)
        total_due = q2(total_due + outstanding)

    rows = []
    for due_date, values in day_buckets.items():
        days_to_due = (due_date - reference).days
        if days_to_due < 0:
            payment_band = "Overdue"
        elif days_to_due <= 7:
            payment_band = "Next 7 Days"
        elif days_to_due <= 30:
            payment_band = "Next 30 Days"
        else:
            payment_band = "Planned"
        rows.append(
            {
                "due_date": due_date,
                "vendor_count": len(values["vendor_ids"]),
                "bill_count": values["bill_count"],
                "due_amount": values["due_amount"],
                "overdue_amount": values["overdue_amount"],
                "next_7_days_amount": values["due_amount"] if payment_band == "Next 7 Days" else ZERO,
                "next_30_days_amount": values["due_amount"] if payment_band in {"Next 7 Days", "Next 30 Days"} else ZERO,
                "payment_band": payment_band,
            }
        )

    _sort_rows(rows, sort_by or "due_date", sort_order)
    paged_rows, total_rows = _paginate(rows, page, page_size)
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
            "due_amount": f"{q2(total_due):.2f}",
            "overdue_amount": f"{q2(total_overdue):.2f}",
            "next_7_days_amount": f"{q2(next_7):.2f}",
            "next_30_days_amount": f"{q2(next_30):.2f}",
        },
        "summary": {
            "forecast_days": max((end_date - start_date).days + 1, 0),
            "date_bands": len(rows),
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
    vendors = list(vendor_queryset(entity_id=entity_id, search=search))
    vendor_map = {v.id: v for v in vendors}
    vendor_ids = set(vendor_map.keys())
    open_items = asof_open_item_balances(entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id, upto_date=as_of, vendor_ids=vendor_ids)

    invoiced = defaultdict(lambda: ZERO)
    notes = defaultdict(lambda: ZERO)
    settled = defaultdict(lambda: ZERO)
    closing = defaultdict(lambda: ZERO)

    for item, settled_amount, outstanding in open_items:
        amount = q2(item.original_amount)
        if amount >= ZERO:
            invoiced[item.vendor_id] = q2(invoiced[item.vendor_id] + amount)
        else:
            notes[item.vendor_id] = q2(notes[item.vendor_id] + abs(amount))
        settled[item.vendor_id] = q2(settled[item.vendor_id] + q2(settled_amount))
        closing[item.vendor_id] = q2(closing[item.vendor_id] + q2(outstanding))

    rows = []
    totals = defaultdict(lambda: ZERO)
    for vendor_id in vendor_ids:
        vendor = vendor_map[vendor_id]
        closing_balance = closing[vendor_id]
        if closing_balance == ZERO and invoiced[vendor_id] == ZERO and notes[vendor_id] == ZERO:
            continue
        status = "Mismatch" if closing_balance > ZERO else "Reconciled"
        row = {
            "vendor_name": vendor.effective_accounting_name,
            "vendor_code": vendor.effective_accounting_code,
            "opening_balance": ZERO,
            "invoiced": invoiced[vendor_id],
            "notes": notes[vendor_id],
            "settled": settled[vendor_id],
            "closing_balance": closing_balance,
            "status": status,
        }
        rows.append(row)
        for key in ("opening_balance", "invoiced", "notes", "settled", "closing_balance"):
            totals[key] = q2(totals[key] + row[key])

    _sort_rows(rows, sort_by or "closing_balance", sort_order)
    paged_rows, total_rows = _paginate(rows, page, page_size)
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
        qs.select_related("vendor", "subentity", "entityfinid", "ref_document", "ap_open_item")
        .order_by("-bill_date", "-id")[:500]
    )
    duplicate_counter = Counter((h.vendor_id, (h.supplier_invoice_number or "").strip().lower(), str(q2(h.grand_total))) for h in headers if h.supplier_invoice_number)

    rows = []
    issue_counts = Counter()
    for header in headers:
        issue_type = None
        issue_message = None
        if header.status != PurchaseInvoiceHeader.Status.POSTED:
            issue_type = "NOT_POSTED"
            issue_message = "Invoice is not posted."
        elif not header.supplier_invoice_number:
            issue_type = "MISSING_SUPPLIER_INVOICE"
            issue_message = "Supplier invoice number is missing."
        elif duplicate_counter[(header.vendor_id, (header.supplier_invoice_number or "").strip().lower(), str(q2(header.grand_total)))] > 1:
            issue_type = "POSSIBLE_DUPLICATE"
            issue_message = "Same vendor + supplier invoice + amount appears multiple times."
        if not issue_type:
            continue
        issue_counts[issue_type] += 1
        rows.append(
            {
                "purchase_number": header.purchase_number,
                "supplier_invoice_number": header.supplier_invoice_number,
                "bill_date": header.bill_date,
                "status": header.status,
                "posting_status": "Posted" if header.status == PurchaseInvoiceHeader.Status.POSTED else "Pending",
                "grand_total": q2(header.grand_total or ZERO),
                "issue_type": issue_type,
                "issue_message": issue_message,
            }
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
    vendors = list(vendor_queryset(entity_id=entity_id, search=search))
    vendor_map = {v.id: v for v in vendors}
    open_items = asof_open_item_balances(entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id, upto_date=as_of, vendor_ids=set(vendor_map.keys()))
    rows = []
    risk_counts = Counter()
    for item, _settled, outstanding in open_items:
        outstanding = q2(outstanding)
        if outstanding <= ZERO:
            continue
        due_date = item.due_date or item.bill_date
        if not due_date:
            continue
        vendor = vendor_map.get(item.vendor_id) or item.vendor
        days_overdue = (as_of - due_date).days
        gstin = account_gstno(vendor)
        if not gstin:
            risk = "HIGH"
            reason = "Vendor GSTIN missing."
        elif days_overdue > 90:
            risk = "MEDIUM"
            reason = "Outstanding aging beyond 90 days."
        else:
            risk = "LOW"
            reason = "No critical compliance signal."
        risk_counts[risk] += 1
        rows.append(
            {
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
        )
    _sort_rows(rows, sort_by or "days_overdue", sort_order)
    paged_rows, total_rows = _paginate(rows, page, page_size)
    _stringify_amount_fields(paged_rows, ("outstanding",))
    return {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "as_of_date": as_of,
        "rows": paged_rows,
        "totals": {"outstanding": f"{q2(sum((q2(r['outstanding']) for r in rows), ZERO)):.2f}"},
        "summary": {"risk_counts": dict(risk_counts), "row_count": total_rows},
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
    headers = list(qs.select_related("vendor").order_by("-bill_date", "-id")[:1000])
    duplicate_counter = Counter((h.vendor_id, (h.supplier_invoice_number or "").strip().lower(), str(q2(h.grand_total))) for h in headers if h.supplier_invoice_number)
    amounts = [q2(h.grand_total or ZERO) for h in headers]
    median = sorted(amounts)[len(amounts) // 2] if amounts else ZERO
    anomaly_rows = []
    anomaly_counts = Counter()
    for header in headers:
        anomaly_type = None
        reason = None
        score = 0
        dup_key = (header.vendor_id, (header.supplier_invoice_number or "").strip().lower(), str(q2(header.grand_total)))
        if header.supplier_invoice_number and duplicate_counter[dup_key] > 1:
            anomaly_type = "POSSIBLE_DUPLICATE"
            reason = "Duplicate vendor + supplier invoice + amount combination."
            score = min(100, duplicate_counter[dup_key] * 25)
        elif median > ZERO and q2(header.grand_total or ZERO) >= (median * Decimal("10")):
            anomaly_type = "AMOUNT_OUTLIER"
            reason = "Bill amount is significantly higher than period median."
            score = 75
        if not anomaly_type:
            continue
        vendor = header.vendor
        anomaly_counts[anomaly_type] += 1
        anomaly_rows.append(
            {
                "vendor_name": getattr(vendor, "effective_accounting_name", header.vendor_name or "-"),
                "vendor_code": getattr(vendor, "effective_accounting_code", "-"),
                "supplier_invoice_number": header.supplier_invoice_number or "-",
                "bill_date": header.bill_date,
                "grand_total": q2(header.grand_total or ZERO),
                "anomaly_type": anomaly_type,
                "anomaly_score": score,
                "anomaly_reason": reason,
            }
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
