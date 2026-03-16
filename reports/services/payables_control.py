from __future__ import annotations

"""Control reporting and close-validation services for payables."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from purchase.models.purchase_ap import VendorAdvanceBalance, VendorBillOpenItem, VendorSettlement
from purchase.models.purchase_core import PurchaseInvoiceHeader
from reports.selectors.financial import normalize_scope_ids
from reports.selectors.payables import (
    advance_vendor_summary,
    all_last_payment_dates,
    asof_advances,
    asof_open_item_balances,
    coerce_date,
    future_settlement_applications,
    open_item_vendor_summary,
    q2,
    resolve_scope_dates,
    settlement_integrity_issues,
    vendor_control_balance_map,
    vendor_queryset,
)
from reports.services.payables import (
    GL_RECONCILIATION_TOLERANCE,
    _drilldown_item,
    _paginate,
    _report_meta_payload,
    _row_with_meta,
    _sort_rows,
    _stringify_amount_fields,
    _trace_payload,
    _vendor_meta,
)

ZERO = Decimal("0.00")
WARNING_TOLERANCE = Decimal("1.00")
DEFAULT_STALE_ADVANCE_DAYS = 90
DEFAULT_STALE_VENDOR_DAYS = 60
CRITICAL_CHECK_CODES = {
    "ap_gl_mismatch",
    "settlement_integrity_errors",
    "negative_open_invoice_residuals",
}


def _difference_status(value):
    amount = abs(q2(value))
    if amount <= GL_RECONCILIATION_TOLERANCE:
        return "matched"
    if amount <= WARNING_TOLERANCE:
        return "warning"
    return "mismatch"


def _as_of_date(entityfin_id, as_of_date=None, to_date=None):
    _from_date, resolved_to = resolve_scope_dates(entityfin_id, None, to_date, as_of_date)
    if not resolved_to:
        raise ValueError("as_of_date or to_date is required.")
    return resolved_to


def _sample_refs(rows, *keys, limit=5):
    out = []
    for row in rows[:limit]:
        sample = {}
        for key in keys:
            value = row.get(key)
            if value is not None:
                sample[key] = value
        if sample:
            out.append(sample)
    return out


def _vendor_reconciliation_rows(*, entity_id, entityfin_id, subentity_id, as_of_date, vendor_id=None, vendor_group=None, region_id=None, currency=None, search=None):
    vendors = list(
        vendor_queryset(
            entity_id=entity_id,
            vendor_id=vendor_id,
            vendor_group=vendor_group,
            region_id=region_id,
            currency=currency,
            search=search,
        )
    )
    vendor_ids = {vendor.id for vendor in vendors}
    open_item_summary = open_item_vendor_summary(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=as_of_date,
        vendor_ids=vendor_ids,
    )
    advance_summary = advance_vendor_summary(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=as_of_date,
        vendor_ids=vendor_ids,
    )
    gl_balance_map = vendor_control_balance_map(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=as_of_date,
        vendor_ledger_map={vendor.id: getattr(vendor, "ledger_id", None) for vendor in vendors},
    )

    rows = []
    totals = defaultdict(lambda: ZERO)
    for vendor in vendors:
        open_invoice_balance = q2(open_item_summary.get(vendor.id, {}).get("outstanding_total", ZERO))
        unapplied_advance = q2(advance_summary.get(vendor.id, ZERO))
        subledger_balance = q2(open_invoice_balance - unapplied_advance)
        gl_balance = q2(gl_balance_map.get(vendor.id, ZERO))
        difference_amount = q2(subledger_balance - gl_balance)
        if subledger_balance == ZERO and gl_balance == ZERO and vendor_id is None:
            continue
        drilldown = {
            "vendor_outstanding": _drilldown_item(
                label="Vendor Outstanding",
                target="vendor_outstanding",
                report_code="vendor_outstanding",
                path="/api/reports/payables/vendor-outstanding/",
                params={
                    "entity": entity_id,
                    "entityfinid": entityfin_id,
                    "subentity": subentity_id,
                    "to_date": as_of_date,
                    "vendor": vendor.id,
                },
            ),
            "ap_aging": _drilldown_item(
                label="AP Aging Summary",
                target="ap_aging",
                report_code="ap_aging",
                path="/api/reports/payables/aging/",
                params={
                    "entity": entity_id,
                    "entityfinid": entityfin_id,
                    "subentity": subentity_id,
                    "as_of_date": as_of_date,
                    "vendor": vendor.id,
                    "view": "summary",
                },
            ),
            "vendor_statement": _drilldown_item(
                label="Vendor Statement",
                target="purchase_ap_vendor_statement",
                params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": vendor.id},
            ),
        }
        row = _row_with_meta(
            {
                **_vendor_meta(vendor),
                "open_invoice_balance": open_invoice_balance,
                "unapplied_advance": unapplied_advance,
                "subledger_balance": subledger_balance,
                "gl_balance": gl_balance,
                "difference_amount": difference_amount,
                "reconciliation_status": _difference_status(difference_amount),
            },
            drilldown=drilldown,
            trace=_trace_payload(
                source_model="posting.JournalLine",
                source_id=vendor.id,
                source_document_type="ApGlReconciliation",
                source_document_number=vendor.effective_accounting_code,
                vendor_id=vendor.id,
                vendor_ledger_id=getattr(vendor, "ledger_id", None),
                as_of_date=str(as_of_date),
                derived_from=["purchase.VendorBillOpenItem", "purchase.VendorAdvanceBalance", "posting.JournalLine"],
            ),
        )
        rows.append(row)
        totals["open_invoice_balance"] += open_invoice_balance
        totals["unapplied_advance"] += unapplied_advance
        totals["subledger_balance"] += subledger_balance
        totals["gl_balance"] += gl_balance
        totals["difference_amount"] += difference_amount

    return rows, totals


def build_ap_gl_reconciliation_report(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    as_of_date=None,
    vendor_id=None,
    vendor_group=None,
    region_id=None,
    currency=None,
    search=None,
    sort_by=None,
    sort_order="desc",
    page=1,
    page_size=100,
    include_trace=True,
):
    """Compare the AP subledger to posted vendor-ledger balances in the GL."""
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    as_of = _as_of_date(entityfin_id, as_of_date)
    rows, totals = _vendor_reconciliation_rows(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        as_of_date=as_of,
        vendor_id=vendor_id,
        vendor_group=vendor_group,
        region_id=region_id,
        currency=currency,
        search=search,
    )
    if not include_trace:
        for row in rows:
            row.pop("_trace", None)
    _sort_rows(rows, sort_by or "difference_amount", sort_order)
    paged_rows, total_rows = _paginate(rows, page, page_size)
    _stringify_amount_fields(
        paged_rows,
        ("open_invoice_balance", "unapplied_advance", "subledger_balance", "gl_balance", "difference_amount"),
    )
    overall_status = _difference_status(totals["difference_amount"])
    return {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "as_of_date": as_of,
        "rows": paged_rows,
        "totals": {key: f"{q2(value):.2f}" for key, value in totals.items()},
        "summary": {
            "matched_vendor_count": sum(1 for row in rows if row["reconciliation_status"] == "matched"),
            "warning_vendor_count": sum(1 for row in rows if row["reconciliation_status"] == "warning"),
            "mismatch_vendor_count": sum(1 for row in rows if row["reconciliation_status"] == "mismatch"),
            "overall_status": overall_status,
            "component_breakdown": {
                "open_invoices": f"{q2(totals['open_invoice_balance']):.2f}",
                "vendor_advances": f"{q2(totals['unapplied_advance']):.2f}",
                "subledger_total": f"{q2(totals['subledger_balance']):.2f}",
                "gl_total": f"{q2(totals['gl_balance']):.2f}",
            },
        },
        "pagination": {"page": page, "page_size": page_size, "total_rows": total_rows, "paginated": True},
        **_report_meta_payload(
            report_code="ap_gl_reconciliation",
            report_name="AP to GL Reconciliation Report",
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            as_of_date=as_of,
            vendor_id=vendor_id,
            required_menu_code="reports.apglreconciliation",
            required_permissions=["reports.apglreconciliation.view"],
            feature_state={"include_trace": include_trace},
            extra_meta={"overall_reconciliation_status": overall_status},
        ),
    }


def _exception_row(*, exception_type, severity, vendor, amount, message, as_of_date, entity_id, entityfin_id, subentity_id, document_number=None, age_days=None, extra_params=None):
    drilldown = {
        "vendor_outstanding": _drilldown_item(
            label="Vendor Outstanding",
            target="vendor_outstanding",
            report_code="vendor_outstanding",
            path="/api/reports/payables/vendor-outstanding/",
            params={
                "entity": entity_id,
                "entityfinid": entityfin_id,
                "subentity": subentity_id,
                "to_date": as_of_date,
                "vendor": vendor.id,
            },
        ),
        "ap_aging": _drilldown_item(
            label="AP Aging Invoice",
            target="ap_aging",
            report_code="ap_aging",
            path="/api/reports/payables/aging/",
            params={
                "entity": entity_id,
                "entityfinid": entityfin_id,
                "subentity": subentity_id,
                "as_of_date": as_of_date,
                "vendor": vendor.id,
                "view": "invoice",
            },
        ),
    }
    if extra_params:
        drilldown.update(extra_params)
    return _row_with_meta(
        {
            **_vendor_meta(vendor),
            "exception_type": exception_type,
            "severity": severity,
            "document_number": document_number,
            "amount": q2(amount),
            "age_days": age_days,
            "message": message,
        },
        drilldown=drilldown,
    )


def build_vendor_balance_exception_report(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    as_of_date=None,
    vendor_id=None,
    vendor_group=None,
    region_id=None,
    currency=None,
    search=None,
    min_amount=None,
    overdue_days_gt=None,
    stale_days_gt=None,
    include_negative_balances=True,
    include_old_advances=True,
    include_stale_vendors=True,
    sort_by=None,
    sort_order="desc",
    page=1,
    page_size=100,
):
    """Return lightweight payable exceptions with drilldown-friendly rows."""
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    as_of = _as_of_date(entityfin_id, as_of_date)
    min_amount = q2(min_amount or ZERO)
    stale_days_gt = stale_days_gt or DEFAULT_STALE_ADVANCE_DAYS
    overdue_days_gt = overdue_days_gt or 0

    vendors = list(
        vendor_queryset(
            entity_id=entity_id,
            vendor_id=vendor_id,
            vendor_group=vendor_group,
            region_id=region_id,
            currency=currency,
            search=search,
        )
    )
    vendor_by_id = {vendor.id: vendor for vendor in vendors}
    vendor_ids = set(vendor_by_id.keys())
    summary_rows, _summary_totals = _vendor_reconciliation_rows(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        as_of_date=as_of,
        vendor_id=vendor_id,
        vendor_group=vendor_group,
        region_id=region_id,
        currency=currency,
        search=search,
    )
    summary_by_vendor = {row["vendor_id"]: row for row in summary_rows}
    last_payment_map = all_last_payment_dates(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=as_of,
    )
    open_items = asof_open_item_balances(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=as_of,
        vendor_ids=vendor_ids,
    )
    advances = asof_advances(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=as_of,
        vendor_ids=vendor_ids,
    )

    max_overdue_days = defaultdict(int)
    positive_balance_by_vendor = defaultdict(lambda: ZERO)
    credit_pool_by_vendor = defaultdict(lambda: ZERO)
    rows = []
    for item, _settled, outstanding in open_items:
        if item.vendor_id not in vendor_by_id:
            continue
        if outstanding > ZERO:
            positive_balance_by_vendor[item.vendor_id] = q2(positive_balance_by_vendor[item.vendor_id] + outstanding)
            days_overdue = (as_of - (item.due_date or item.bill_date)).days
            max_overdue_days[item.vendor_id] = max(max_overdue_days[item.vendor_id], days_overdue)
        elif outstanding < ZERO:
            credit_pool_by_vendor[item.vendor_id] = q2(credit_pool_by_vendor[item.vendor_id] + abs(outstanding))
            if include_negative_balances and q2(item.original_amount) > ZERO:
                vendor = vendor_by_id[item.vendor_id]
                rows.append(
                    _exception_row(
                        exception_type="negative_invoice_outstanding",
                        severity="error",
                        vendor=vendor,
                        amount=outstanding,
                        message="Invoice-style open item has a negative outstanding balance.",
                        as_of_date=as_of,
                        entity_id=entity_id,
                        entityfin_id=entityfin_id,
                        subentity_id=subentity_id,
                        document_number=item.purchase_number or item.supplier_invoice_number,
                        age_days=(as_of - item.bill_date).days,
                    )
                )

    for adv, _adjusted, outstanding in advances:
        if adv.vendor_id not in vendor_by_id or outstanding <= ZERO:
            continue
        credit_pool_by_vendor[adv.vendor_id] = q2(credit_pool_by_vendor[adv.vendor_id] + outstanding)
        age_days = (as_of - adv.credit_date).days
        if include_old_advances and age_days >= stale_days_gt:
            vendor = vendor_by_id[adv.vendor_id]
            rows.append(
                _exception_row(
                    exception_type="old_unapplied_advance",
                    severity="warning",
                    vendor=vendor,
                    amount=outstanding,
                    message="Vendor advance remains unapplied beyond the stale threshold.",
                    as_of_date=as_of,
                    entity_id=entity_id,
                    entityfin_id=entityfin_id,
                    subentity_id=subentity_id,
                    document_number=adv.reference_no,
                    age_days=age_days,
                )
            )

    for vendor_id_key, summary in summary_by_vendor.items():
        vendor = vendor_by_id[vendor_id_key]
        outstanding = q2(summary["subledger_balance"])
        vendor_outstanding = q2(summary["subledger_balance"])
        if include_negative_balances and vendor_outstanding < ZERO:
            rows.append(
                _exception_row(
                    exception_type="negative_vendor_balance",
                    severity="warning",
                    vendor=vendor,
                    amount=vendor_outstanding,
                    message="Vendor has a net debit-style balance in AP.",
                    as_of_date=as_of,
                    entity_id=entity_id,
                    entityfin_id=entityfin_id,
                    subentity_id=subentity_id,
                )
            )
        if include_stale_vendors and vendor_outstanding > min_amount:
            last_payment = last_payment_map.get(vendor_id_key)
            stale_age = (as_of - last_payment).days if last_payment else None
            if stale_age is None or stale_age >= DEFAULT_STALE_VENDOR_DAYS:
                rows.append(
                    _exception_row(
                        exception_type="stale_open_vendor",
                        severity="warning",
                        vendor=vendor,
                        amount=vendor_outstanding,
                        message="Vendor has open items without recent settlement activity.",
                        as_of_date=as_of,
                        entity_id=entity_id,
                        entityfin_id=entityfin_id,
                        subentity_id=subentity_id,
                        age_days=stale_age,
                    )
                )
        if max_overdue_days[vendor_id_key] > overdue_days_gt and positive_balance_by_vendor[vendor_id_key] >= min_amount:
            rows.append(
                _exception_row(
                    exception_type="overdue_balance_threshold",
                    severity="warning",
                    vendor=vendor,
                    amount=positive_balance_by_vendor[vendor_id_key],
                    message="Vendor has overdue payable balances above the configured threshold.",
                    as_of_date=as_of,
                    entity_id=entity_id,
                    entityfin_id=entityfin_id,
                    subentity_id=subentity_id,
                    age_days=max_overdue_days[vendor_id_key],
                )
            )
        if positive_balance_by_vendor[vendor_id_key] > ZERO and credit_pool_by_vendor[vendor_id_key] > ZERO:
            rows.append(
                _exception_row(
                    exception_type="offsetting_vendor_positions",
                    severity="warning",
                    vendor=vendor,
                    amount=credit_pool_by_vendor[vendor_id_key],
                    message="Vendor has both payable invoices and offsetting credits/advances that can hide net exposure.",
                    as_of_date=as_of,
                    entity_id=entity_id,
                    entityfin_id=entityfin_id,
                    subentity_id=subentity_id,
                )
            )
        if summary.get("reconciliation_status") == "mismatch":
            rows.append(
                _exception_row(
                    exception_type="ap_gl_mismatch",
                    severity="error",
                    vendor=vendor,
                    amount=summary["difference_amount"],
                    message="Vendor subledger balance does not match the GL vendor ledger balance.",
                    as_of_date=as_of,
                    entity_id=entity_id,
                    entityfin_id=entityfin_id,
                    subentity_id=subentity_id,
                )
            )

    _sort_rows(rows, sort_by or "amount", sort_order)
    paged_rows, total_rows = _paginate(rows, page, page_size)
    _stringify_amount_fields(paged_rows, ("amount",))
    counts = defaultdict(int)
    for row in rows:
        counts[row["exception_type"]] += 1
    return {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "as_of_date": as_of,
        "rows": paged_rows,
        "summary": {
            "total_exceptions": total_rows,
            "by_type": dict(counts),
        },
        "pagination": {"page": page, "page_size": page_size, "total_rows": total_rows, "paginated": True},
        **_report_meta_payload(
            report_code="vendor_balance_exceptions",
            report_name="Vendor Balance Exception Report",
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            as_of_date=as_of,
            vendor_id=vendor_id,
            required_menu_code="reports.vendorbalanceexceptions",
            required_permissions=["reports.vendorbalanceexceptions.view"],
            feature_state={
                "include_negative_balances": include_negative_balances,
                "include_old_advances": include_old_advances,
                "include_stale_vendors": include_stale_vendors,
            },
        ),
    }


def build_payables_close_validation(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    as_of_date=None,
):
    """Return JSON-first payables close readiness checks for a close date."""
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    close_date = _as_of_date(entityfin_id, as_of_date)

    checks = []

    unposted_docs_qs = PurchaseInvoiceHeader.objects.filter(
        entity_id=entity_id,
        bill_date__lte=close_date,
        status__in=[PurchaseInvoiceHeader.Status.DRAFT, PurchaseInvoiceHeader.Status.CONFIRMED],
    )
    if entityfin_id:
        unposted_docs_qs = unposted_docs_qs.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        unposted_docs_qs = unposted_docs_qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))
    unposted_docs = list(unposted_docs_qs.values("id", "purchase_number", "bill_date")[:5])
    checks.append({
        "check_code": "unposted_ap_documents",
        "severity": "warning",
        "message": "Purchase/AP documents exist in draft or confirmed status on or before the close date.",
        "affected_count": unposted_docs_qs.count(),
        "sample_references": _sample_refs(unposted_docs, "id", "purchase_number", "bill_date"),
    })

    open_items = asof_open_item_balances(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=close_date,
    )
    negative_residuals = [
        {
            "id": item.id,
            "purchase_number": item.purchase_number or item.supplier_invoice_number,
            "vendor_id": item.vendor_id,
        }
        for item, _settled, outstanding in open_items
        if q2(item.original_amount) > ZERO and outstanding < ZERO
    ]
    checks.append({
        "check_code": "negative_open_invoice_residuals",
        "severity": "error",
        "message": "Positive invoice-style AP open items have negative residual balances.",
        "affected_count": len(negative_residuals),
        "sample_references": _sample_refs(negative_residuals, "id", "purchase_number", "vendor_id"),
    })

    missing_due_dates_qs = VendorBillOpenItem.objects.filter(entity_id=entity_id, bill_date__lte=close_date, original_amount__gt=ZERO, due_date__isnull=True)
    if entityfin_id:
        missing_due_dates_qs = missing_due_dates_qs.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        missing_due_dates_qs = missing_due_dates_qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))
    missing_due_rows = list(missing_due_dates_qs.values("id", "purchase_number", "vendor_id")[:5])
    checks.append({
        "check_code": "missing_due_dates",
        "severity": "warning",
        "message": "Posted AP open items are missing due dates required for aging and overdue controls.",
        "affected_count": missing_due_dates_qs.count(),
        "sample_references": _sample_refs(missing_due_rows, "id", "purchase_number", "vendor_id"),
    })

    zero_anomalies_qs = VendorBillOpenItem.objects.filter(entity_id=entity_id, bill_date__lte=close_date, is_open=True).filter(Q(original_amount=ZERO) | Q(outstanding_amount=ZERO))
    if entityfin_id:
        zero_anomalies_qs = zero_anomalies_qs.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        zero_anomalies_qs = zero_anomalies_qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))
    zero_rows = list(zero_anomalies_qs.values("id", "purchase_number", "vendor_id")[:5])
    checks.append({
        "check_code": "open_item_zero_anomalies",
        "severity": "warning",
        "message": "Open-item records contain zero-value or zero-outstanding anomalies while still marked open.",
        "affected_count": zero_anomalies_qs.count(),
        "sample_references": _sample_refs(zero_rows, "id", "purchase_number", "vendor_id"),
    })

    advances = asof_advances(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=close_date,
    )
    stale_advances = [
        {
            "id": adv.id,
            "reference_no": adv.reference_no,
            "vendor_id": adv.vendor_id,
        }
        for adv, _adjusted, outstanding in advances
        if outstanding > ZERO and (close_date - adv.credit_date).days >= DEFAULT_STALE_ADVANCE_DAYS
    ]
    checks.append({
        "check_code": "long_unapplied_advances",
        "severity": "warning",
        "message": "Vendor advances remain unapplied well beyond the close threshold.",
        "affected_count": len(stale_advances),
        "sample_references": _sample_refs(stale_advances, "id", "reference_no", "vendor_id"),
    })

    future_settlements = future_settlement_applications(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        close_date=close_date,
    )
    checks.append({
        "check_code": "post_close_settlement_activity",
        "severity": "warning",
        "message": "Pre-close AP invoices have posted settlements dated after the close date; review cutoff handling.",
        "affected_count": len(future_settlements),
        "sample_references": _sample_refs(future_settlements, "settlement_id", "reference_no", "document_number", "settlement_date"),
    })

    integrity_rows = settlement_integrity_issues(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
    )
    checks.append({
        "check_code": "settlement_integrity_errors",
        "severity": "error" if any(row["severity"] == "error" for row in integrity_rows) else "warning",
        "message": "Settlement headers and lines contain consistency issues that can distort AP balances.",
        "affected_count": len(integrity_rows),
        "sample_references": _sample_refs(integrity_rows, "settlement_id", "open_item_id", "reference_no", "document_number"),
    })

    reconciliation = build_ap_gl_reconciliation_report(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        as_of_date=close_date,
        page_size=500,
    )
    checks.append({
        "check_code": "ap_gl_mismatch",
        "severity": "error" if reconciliation["summary"]["overall_status"] == "mismatch" else "warning",
        "message": "AP subledger does not fully reconcile to the posted GL vendor balances.",
        "affected_count": reconciliation["summary"]["mismatch_vendor_count"] + reconciliation["summary"]["warning_vendor_count"],
        "sample_references": _sample_refs(reconciliation["rows"], "vendor_id", "vendor_name", "difference_amount", limit=5),
    })

    error_count = sum(1 for check in checks if check["severity"] == "error" and check["affected_count"] > 0)
    warning_count = sum(1 for check in checks if check["severity"] == "warning" and check["affected_count"] > 0)
    return {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "as_of_date": close_date,
        "checks": checks,
        "summary": {
            "validation_error_count": error_count,
            "validation_warning_count": warning_count,
            "is_close_ready": error_count == 0,
        },
        **_report_meta_payload(
            report_code="payables_close_validation",
            report_name="Payables Close Validation",
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            as_of_date=close_date,
            required_menu_code="reports.apglreconciliation",
            required_permissions=["reports.apglreconciliation.view"],
            extra_meta={"json_first": True},
        ),
    }


def build_payables_close_readiness_summary(*, entity_id, entityfin_id=None, subentity_id=None, as_of_date=None):
    """Return a quick close-readiness summary for the payables period close review."""
    close_date = _as_of_date(entityfin_id, as_of_date)
    validation_payload = build_payables_close_validation(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        as_of_date=close_date,
    )
    reconciliation = build_ap_gl_reconciliation_report(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        as_of_date=close_date,
        page_size=1000,
    )
    vendor_rows = reconciliation["rows"]
    top_issues = sorted(
        [check for check in validation_payload["checks"] if check["affected_count"] > 0],
        key=lambda check: (0 if check["check_code"] in CRITICAL_CHECK_CODES else 1, 0 if check["severity"] == "error" else 1, -check["affected_count"]),
    )[:5]
    return {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "as_of_date": close_date,
        "ap_gl_reconciliation_status": reconciliation["summary"]["overall_status"],
        "difference_amount": reconciliation["totals"]["difference_amount"],
        "open_vendor_count": len(vendor_rows),
        "overdue_vendor_count": sum(1 for row in vendor_rows if q2(row["subledger_balance"]) > ZERO and q2(row["open_invoice_balance"]) > ZERO),
        "negative_balance_vendor_count": sum(1 for row in vendor_rows if q2(row["subledger_balance"]) < ZERO),
        "stale_advance_count": next((check["affected_count"] for check in validation_payload["checks"] if check["check_code"] == "long_unapplied_advances"), 0),
        "validation_error_count": validation_payload["summary"]["validation_error_count"],
        "validation_warning_count": validation_payload["summary"]["validation_warning_count"],
        "top_critical_issues": top_issues,
        **_report_meta_payload(
            report_code="payables_close_readiness_summary",
            report_name="Payables Close Readiness Summary",
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            as_of_date=close_date,
            required_menu_code="reports.apglreconciliation",
            required_permissions=["reports.apglreconciliation.view"],
            extra_meta={"dashboard": True, "json_first": True},
        ),
    }



