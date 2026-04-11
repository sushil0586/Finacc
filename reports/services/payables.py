from __future__ import annotations

"""Business services for payable reporting.

These services mirror the receivables reporting style while keeping AP-specific
accounting rules explicit: invoices/debit notes increase payable exposure,
credit notes and advances reduce it, and vendor control balances are credit
balances in the general ledger.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from financial.profile_access import (
    account_agent,
    account_creditdays,
    account_creditlimit,
    account_currency,
    account_gstno,
    account_region_state,
)

from reports.selectors.financial import normalize_scope_ids
from reports.selectors.payables import (
    advance_vendor_summary,
    all_last_payment_dates,
    asof_advances,
    asof_open_item_balances,
    coerce_date,
    open_item_vendor_summary,
    period_bill_credit_totals,
    posted_payment_totals,
    q2,
    resolve_scope_dates,
    vendor_control_balance_map,
    vendor_queryset,
)
from reports.services.payables_config import (
    PAYABLE_EXPORT_FORMATS,
    build_payables_drilldown,
    build_related_report_links,
    get_payables_registry_payload,
    get_payables_report_config,
    get_payables_drilldown_target,
    resolve_pagination_mode,
    resolve_report_columns,
    resolve_report_summary_blocks,
    resolve_supported_filters,
    resolve_view_modes,
)

ZERO = Decimal("0.00")
GL_RECONCILIATION_TOLERANCE = Decimal("0.05")
EXPORTABLE_FORMATS = list(PAYABLE_EXPORT_FORMATS)


def _iso_date(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _drilldown_item(*, label, target, params, path=None, report_code=None, kind=None):
    return build_payables_drilldown(
        target,
        params=params,
        label=label,
        kind=kind,
        path=path,
        report_code=report_code,
    )


def _payable_related_reports(*, report_code, entity_id, entityfin_id, subentity_id, as_of_date=None, from_date=None, to_date=None, vendor_id=None, view=None, permission_codes=None):
    report_config = get_payables_report_config(report_code, view=view)
    return build_related_report_links(
        report_config.get("related_reports", []),
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        as_of_date=_iso_date(as_of_date),
        from_date=_iso_date(from_date),
        to_date=_iso_date(to_date),
        vendor_id=vendor_id,
        view=view,
        permission_codes=permission_codes,
    )


def _paid_amount_asof(item, settled_asof):
    """Clamp applied settlements to the positive payable amount of a bill."""
    if q2(item.original_amount) <= ZERO:
        return ZERO
    return q2(min(q2(settled_asof), q2(item.original_amount)))


def _allocate_vendor_credits(invoice_rows, credit_amount):
    """Apply vendor credits FIFO to the oldest positive payable balances first.

    Credit notes and unapplied advances reduce AP exposure. Mirroring AR aging,
    we apply them against the oldest due items before assigning the remaining
    balance to aging buckets.
    """
    remaining = q2(credit_amount)
    out = []
    for row in invoice_rows:
        residual = q2(row["residual_before_credit"])
        credit_used = min(residual, remaining) if residual > ZERO else ZERO
        remaining = q2(remaining - credit_used)
        residual_after = q2(residual - credit_used)
        enriched = dict(row)
        enriched["credit_applied_fifo"] = credit_used
        enriched["residual_after_credit"] = residual_after
        out.append(enriched)
    return out, remaining


def _aging_bucket(days_overdue):
    """Bucket AP exposure using the same due-date aging convention as AR."""
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "bucket_1_30"
    if days_overdue <= 60:
        return "bucket_31_60"
    if days_overdue <= 90:
        return "bucket_61_90"
    return "bucket_90_plus"


def _vendor_outstanding_bucket(days_overdue):
    if days_overdue <= 0:
        return "not_due"
    if days_overdue <= 30:
        return "bucket_0_30"
    if days_overdue <= 60:
        return "bucket_31_60"
    if days_overdue <= 90:
        return "bucket_61_90"
    if days_overdue <= 180:
        return "bucket_91_180"
    return "bucket_181_plus"


def _voucher_type_matches(raw_type, label, selected_types):
    if not selected_types:
        return True
    if raw_type is None and label is None:
        return False
    candidates = {
        str(raw_type).strip().lower() if raw_type is not None else "",
        str(label).strip().lower() if label is not None else "",
    }
    if raw_type is not None:
        candidates.add(str(int(raw_type)) if str(raw_type).lstrip("-").isdigit() else str(raw_type).strip().lower())
    normalized = {str(item).strip().lower() for item in (selected_types or []) if str(item).strip()}
    return bool(candidates & normalized)


def _date_or_none(value):
    if not value:
        return None
    return value


def _vendor_meta(vendor, *, subentity_name=None):
    return {
        "vendor_id": vendor.id,
        "vendor_name": vendor.effective_accounting_name,
        "vendor_code": vendor.effective_accounting_code,
        "credit_limit": f"{q2(account_creditlimit(vendor) or ZERO):.2f}" if account_creditlimit(vendor) is not None else None,
        "credit_days": account_creditdays(vendor),
        "currency": account_currency(vendor) or "INR",
        "branch": None,
        "subentity_name": subentity_name,
        "gstin": account_gstno(vendor),
        "vendor_group": account_agent(vendor),
        "region": getattr(account_region_state(vendor), "statename", None) or getattr(account_region_state(vendor), "state", None),
    }


def _payable_drilldown_flow():
    return [
        {"level": 1, "code": "vendor_outstanding", "label": "Vendor Outstanding"},
        {"level": 2, "code": "ap_aging", "label": "AP Aging"},
        {"level": 3, "code": "bill_list", "label": "Bill List"},
        {"level": 4, "code": "bill_detail", "label": "Bill Detail"},
        {"level": 5, "code": "payment_allocation", "label": "Payment Allocation"},
    ]


def _trace_payload(**payload):
    trace = {key: value for key, value in payload.items() if value not in (None, [], {}, "")}
    return trace or None


def _row_with_meta(row, *, drilldown, trace=None):
    row = dict(row)
    row["can_drilldown"] = bool(drilldown)
    row["drilldown_targets"] = list(drilldown.keys())
    row["_meta"] = {
        "drilldown": drilldown,
        "supports_drilldown": bool(drilldown),
    }
    if trace:
        row["_trace"] = trace
    return row


def _report_meta_payload(
    *,
    report_code,
    report_name,
    entity_id,
    entityfin_id,
    subentity_id,
    as_of_date=None,
    from_date=None,
    to_date=None,
    view=None,
    vendor_id=None,
    required_menu_code,
    required_permissions,
    feature_state=None,
    extra_meta=None,
):
    hierarchy = _payable_drilldown_flow()
    report_meta = get_payables_report_config(report_code, view=view)
    column_meta = resolve_report_columns(report_code, view=view, enabled_features=feature_state)
    summary_blocks = resolve_report_summary_blocks(report_code, view=view, enabled_features=feature_state)
    permission_set = set(required_permissions or [])
    available_drilldowns = []
    for code in (report_meta or {}).get("drilldown_targets", []):
        target = get_payables_drilldown_target(code) or {"code": code, "target": code, "label": code.replace("_", " ").title()}
        target_report_code = target.get("report_code") or code
        target_report = get_payables_report_config(target_report_code, view=target.get("view"))
        if target_report and target_report.get("required_permission") and target_report.get("required_permission") not in permission_set:
            continue
        available_drilldowns.append(target)
    meta = {
        "drilldown_hierarchy": hierarchy,
        "report_code": report_code,
        "report_name": report_name,
        "label": report_name,
        "endpoint": (report_meta or {}).get("path"),
        "generated_at": timezone.now().isoformat(),
        "as_of_date": _iso_date(as_of_date or to_date),
        "scope_summary": {
            "entity_id": entity_id,
            "entityfin_id": entityfin_id,
            "subentity_id": subentity_id,
            "from_date": _iso_date(from_date),
            "to_date": _iso_date(to_date),
            "as_of_date": _iso_date(as_of_date or to_date),
            "view": view,
        },
        "exportable_formats": list(EXPORTABLE_FORMATS),
        "supports_drilldown": True,
        "available_drilldowns": available_drilldowns,
        "required_menu_code": required_menu_code,
        "required_permission_codes": list(required_permissions),
        "feature_flags": [
            {"code": key, **value}
            for key, value in (report_meta or {}).get("feature_flags", {}).items()
        ],
        "supports_traceability": bool((report_meta or {}).get("supports_traceability")),
        "supported_filters": resolve_supported_filters(report_code, view=view),
        "pagination_mode": resolve_pagination_mode(report_code, view=view),
        "view_modes": resolve_view_modes(report_code),
        "available_exports": list((report_meta or {}).get("export_formats", EXPORTABLE_FORMATS)),
        "feature_state": feature_state or {},
        "available_columns": column_meta,
        "effective_columns": [column["key"] for column in column_meta if column["included"]],
        "available_summary_blocks": summary_blocks,
        "enabled_summary_blocks": [block["code"] for block in summary_blocks if block["enabled"]],
        "print_sections": list((report_meta or {}).get("print_sections", [])),
        "related_reports": _payable_related_reports(
            report_code=report_code,
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            as_of_date=as_of_date,
            from_date=from_date,
            to_date=to_date,
            vendor_id=vendor_id,
            view=view,
            permission_codes=permission_set,
        ),
        "report_registry": get_payables_registry_payload(permission_codes=permission_set),
    }
    if extra_meta:
        meta.update(extra_meta)
    return {
        "drilldown_hierarchy": [step["label"] for step in hierarchy],
        "_meta": meta,
    }


def _sort_rows(rows, sort_by, sort_order):
    reverse = (sort_order or "asc").lower() == "desc"
    field = (sort_by or "").strip().lower()

    def key(row):
        if field in {"outstanding", "net_outstanding", "overdue_amount", "opening_balance", "bill_amount", "balance", "original_amount", "settled_amount", "outstanding_amount"}:
            return q2(row.get(field) or row.get("net_outstanding") or ZERO)
        if field in {"vendor_code", "voucher_no", "bill_ref_no", "voucher_type_name"}:
            return str(row.get(field) or row.get("vendor_code") or row.get("voucher_no") or row.get("bill_ref_no") or "").lower()
        if field in {"last_payment_date", "last_bill_date", "due_date", "bill_date", "date"}:
            return row.get(field) or date.min
        return str(row.get(field) or row.get("vendor_name") or row.get("bill_number") or "").lower()

    rows.sort(key=key, reverse=reverse)
    return rows


def _paginate(rows, page, page_size):
    total = len(rows)
    start = max((page - 1) * page_size, 0)
    return rows[start:start + page_size], total


def _stringify_amount_fields(rows, fields):
    for row in rows:
        for key in fields:
            row[key] = f"{q2(row[key]):.2f}"
    return rows


def _vendor_gl_reconciliation_meta(*, entity_id, entityfin_id, subentity_id, to_date, vendors, report_total, enabled):
    """Compare payable report totals to the posted vendor control ledger balance."""
    if not enabled:
        return {}
    vendor_ledger_map = {vendor.id: getattr(vendor, "ledger_id", None) for vendor in vendors if getattr(vendor, "ledger_id", None)}
    gl_balance_map = vendor_control_balance_map(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=to_date,
        vendor_ledger_map=vendor_ledger_map,
    )
    gl_total = q2(sum((q2(amount) for amount in gl_balance_map.values()), ZERO))
    difference = q2(report_total - gl_total)
    return {
        "gl_reconciliation_warning": abs(difference) > GL_RECONCILIATION_TOLERANCE,
        "difference_amount": f"{difference:.2f}",
        "gl_control_balance": f"{gl_total:.2f}",
        "report_outstanding_total": f"{q2(report_total):.2f}",
        "reconciliation_tolerance": f"{GL_RECONCILIATION_TOLERANCE:.2f}",
    }


def build_vendor_outstanding_report(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    from_date=None,
    to_date=None,
    as_of_date=None,
    vendor_id=None,
    vendor_ids=None,
    vendor_group=None,
    region_id=None,
    currency=None,
    gst_registered=None,
    msme=None,
    voucher_type=None,
    aging_basis="due_date",
    overdue_only=False,
    show_overdue_only=False,
    show_not_due=False,
    include_zero_balance=False,
    include_credit_balances=False,
    include_advances_separately=False,
    show_settled=False,
    outstanding_gt=None,
    credit_limit_exceeded=False,
    search=None,
    sort_by=None,
    sort_order="desc",
    page=1,
    page_size=100,
    view="summary",
    reconcile_gl=False,
    include_trace=True,
):
    """Build the vendor outstanding report with vendor summary and bill-wise detail."""
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    from_date, to_date = resolve_scope_dates(entityfin_id, from_date, to_date, as_of_date)
    if not to_date:
        raise ValueError("to_date or as_of_date is required.")
    if not from_date:
        from_date = to_date
    as_of = to_date
    opening_date = from_date - timedelta(days=1)

    selected_vendor_ids = set(vendor_ids or [])
    if vendor_id is not None:
        selected_vendor_ids.add(vendor_id)

    vendors = list(
        vendor_queryset(
            entity_id=entity_id,
            vendor_id=vendor_id,
            vendor_ids=selected_vendor_ids or None,
            vendor_group=vendor_group,
            region_id=region_id,
            currency=currency,
            search=search,
            gst_registered=gst_registered,
            msme=msme,
        )
    )
    vendor_by_id = {v.id: v for v in vendors}
    vendor_scope_ids = set(vendor_by_id.keys())

    selected_voucher_types = voucher_type or []
    normalized_aging_basis = (aging_basis or "due_date").strip().lower()
    if normalized_aging_basis not in {"due_date", "bill_date"}:
        normalized_aging_basis = "due_date"
    normalized_view = (view or "summary").strip().lower()
    if normalized_view not in {"summary", "detailed"}:
        normalized_view = "summary"
    include_overdue_only = bool(overdue_only or show_overdue_only)

    opening_items = open_item_vendor_summary(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=opening_date,
        vendor_ids=vendor_scope_ids,
    )
    asof_items = open_item_vendor_summary(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=to_date,
        vendor_ids=vendor_scope_ids,
    )
    opening_advances = advance_vendor_summary(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=opening_date,
        vendor_ids=vendor_scope_ids,
    )
    asof_advances_map = advance_vendor_summary(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=to_date,
        vendor_ids=vendor_scope_ids,
    )
    asof_open_item_rows = asof_open_item_balances(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=to_date,
        vendor_ids=vendor_scope_ids,
    )
    asof_advance_rows = asof_advances(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=to_date,
        vendor_ids=vendor_scope_ids,
    )
    payment_totals, _period_last_payment = posted_payment_totals(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        from_date=from_date,
        to_date=to_date,
    )
    all_last_payment = all_last_payment_dates(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=to_date,
    )
    bill_totals, credit_totals, last_bill_dates = period_bill_credit_totals(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        from_date=from_date,
        to_date=to_date,
        vendor_ids=vendor_scope_ids,
    )

    summary_rows = []
    detail_rows = []
    summary_totals = defaultdict(lambda: ZERO)
    items_by_vendor = defaultdict(list)
    advances_by_vendor = defaultdict(list)
    for item, settled, outstanding in asof_open_item_rows:
        items_by_vendor[item.vendor_id].append((item, settled, outstanding))
    for adv, adjusted, outstanding in asof_advance_rows:
        advances_by_vendor[adv.vendor_id].append((adv, adjusted, outstanding))

    for vendor in vendors:
        open_summary = asof_items.get(vendor.id, {})
        opening_summary = opening_items.get(vendor.id, {})
        opening_balance = q2(opening_summary.get("outstanding_total", ZERO) - opening_advances.get(vendor.id, ZERO))
        opening_advances_total = q2(opening_advances.get(vendor.id, ZERO))
        asof_advance_total = q2(asof_advances_map.get(vendor.id, ZERO))
        vendor_credit_limit = account_creditlimit(vendor)
        credit_limit = q2(vendor_credit_limit or ZERO) if vendor_credit_limit is not None else None

        vendor_positive_outstanding = ZERO
        vendor_credit_balance = ZERO
        vendor_advance_balance = asof_advance_total
        vendor_not_due = ZERO
        vendor_overdue = ZERO
        oldest_due_date = None
        last_bill_date = last_bill_dates.get(vendor.id)
        bucket_totals = defaultdict(lambda: ZERO)
        vendor_detail_rows = []

        for item, settled, outstanding in items_by_vendor.get(vendor.id, []):
            doc_type = int(getattr(item, "doc_type", 0) or getattr(getattr(item, "header", None), "doc_type", 0) or 0)
            doc_type_name = item.header.get_doc_type_display() if getattr(item, "header", None) else str(doc_type)
            if not _voucher_type_matches(doc_type, doc_type_name, selected_voucher_types):
                continue

            bill_amount = q2(item.original_amount)
            settled_amount = _paid_amount_asof(item, settled)
            outstanding_amount = q2(outstanding)
            if outstanding_amount <= ZERO and not (show_settled or include_credit_balances or include_zero_balance):
                continue

            reference_date = item.due_date if normalized_aging_basis == "due_date" and item.due_date else item.bill_date
            days_delta = (as_of - reference_date).days if reference_date else 0
            days_overdue = max(days_delta, 0)
            bucket = _vendor_outstanding_bucket(days_overdue)
            is_not_due = bool(reference_date and reference_date > as_of)
            if outstanding_amount > ZERO:
                vendor_positive_outstanding = q2(vendor_positive_outstanding + outstanding_amount)
                if is_not_due:
                    vendor_not_due = q2(vendor_not_due + outstanding_amount)
                else:
                    vendor_overdue = q2(vendor_overdue + outstanding_amount)
                    bucket_totals[bucket] = q2(bucket_totals[bucket] + outstanding_amount)
                    oldest_due_date = reference_date if oldest_due_date is None else min(oldest_due_date, reference_date)
            elif outstanding_amount < ZERO:
                vendor_credit_balance = q2(vendor_credit_balance + abs(outstanding_amount))

            row = _row_with_meta(
                {
                    "id": f"bill-{item.id}",
                    "vendor_id": vendor.id,
                    "vendor_name": vendor.effective_accounting_name,
                    "vendor_code": vendor.effective_accounting_code,
                    "gstin": account_gstno(vendor),
                    "subentity_name": getattr(item.subentity, "subentityname", None),
                    "date": item.bill_date,
                    "bill_date": item.bill_date,
                    "voucher_no": item.purchase_number or item.supplier_invoice_number or f"BILL-{item.id}",
                    "voucher_type_name": doc_type_name,
                    "bill_ref_no": item.supplier_invoice_number or item.purchase_number or item.reference_no or f"BILL-{item.id}",
                    "due_date": item.due_date or item.bill_date,
                    "days_overdue": days_overdue,
                    "original_amount": bill_amount,
                    "settled_amount": settled_amount,
                    "outstanding_amount": outstanding_amount,
                    "aging_bucket": bucket if outstanding_amount > ZERO else "settled",
                    "reference_date": reference_date,
                    "is_not_due": is_not_due,
                },
                drilldown={
                    "source_document": _drilldown_item(
                        label="Purchase Document Detail",
                        target="purchase_document_detail",
                        params={"id": item.header_id, "entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id},
                    ),
                    "vendor_statement": _drilldown_item(
                        label="Vendor Statement",
                        target="purchase_ap_vendor_statement",
                        params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": vendor.id},
                    ),
                    "payment_allocation": _drilldown_item(
                        label="Payment Allocation",
                        target="purchase_ap_payment_allocation",
                        params={
                            "entity": entity_id,
                            "entityfinid": entityfin_id,
                            "subentity": subentity_id,
                            "vendor": vendor.id,
                            "invoice_header": item.header_id,
                            "open_item": item.id,
                            "as_of_date": as_of,
                        },
                    ),
                },
                trace=_trace_payload(
                    source_model="purchase.VendorBillOpenItem",
                    source_id=item.id,
                    source_document_id=item.header_id,
                    source_document_number=item.purchase_number or item.supplier_invoice_number or f"BILL-{item.id}",
                    source_document_type=doc_type_name,
                    vendor_id=vendor.id,
                    open_item_id=item.id,
                    bill_date=_iso_date(item.bill_date),
                    due_date=_iso_date(item.due_date or item.bill_date),
                    aging_basis=normalized_aging_basis,
                    aging_bucket=bucket,
                    settled_amount=f"{settled_amount:.2f}",
                    outstanding_amount=f"{outstanding_amount:.2f}",
                    derived_from=["purchase.VendorBillOpenItem", "purchase.VendorSettlementLine"],
                ) if include_trace else None,
            )

            if outstanding_amount > ZERO:
                if include_overdue_only and not (days_overdue > 0):
                    continue
                if not show_not_due and is_not_due:
                    continue
                vendor_detail_rows.append(row)
            elif outstanding_amount < ZERO and include_credit_balances:
                row["voucher_type_name"] = row["voucher_type_name"] or "Credit Balance"
                row["aging_bucket"] = "credit"
                row["outstanding_amount"] = f"{outstanding_amount:.2f}"
                vendor_detail_rows.append(row)
            elif outstanding_amount == ZERO and show_settled:
                row["voucher_type_name"] = row["voucher_type_name"] or "Settled Bill"
                row["aging_bucket"] = "settled"
                vendor_detail_rows.append(row)

        if include_advances_separately:
            for adv, adjusted, outstanding in advances_by_vendor.get(vendor.id, []):
                if outstanding <= ZERO and not show_settled:
                    continue
                advance_row = _row_with_meta(
                    {
                        "id": f"adv-{adv.id}",
                        "vendor_id": vendor.id,
                        "vendor_name": vendor.effective_accounting_name,
                        "vendor_code": vendor.effective_accounting_code,
                        "gstin": account_gstno(vendor),
                        "subentity_name": getattr(adv.subentity, "subentityname", None),
                        "date": adv.credit_date,
                        "bill_date": adv.credit_date,
                        "voucher_no": adv.reference_no or f"ADV-{adv.id}",
                        "voucher_type_name": adv.source_type.replace("_", " ").title(),
                        "bill_ref_no": adv.reference_no or f"ADV-{adv.id}",
                        "due_date": adv.credit_date,
                        "days_overdue": 0,
                        "original_amount": q2(adv.original_amount),
                        "settled_amount": q2(adjusted),
                        "outstanding_amount": f"{(-q2(outstanding)):.2f}",
                        "aging_bucket": "advance",
                        "reference_date": adv.credit_date,
                        "is_advance": True,
                    },
                    drilldown={
                        "vendor_statement": _drilldown_item(
                            label="Vendor Statement",
                            target="purchase_ap_vendor_statement",
                            params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": vendor.id},
                        ),
                    },
                    trace=_trace_payload(
                        source_model="purchase.VendorAdvanceBalance",
                        source_id=adv.id,
                        source_document_number=adv.reference_no or f"ADV-{adv.id}",
                        vendor_id=vendor.id,
                        credit_date=_iso_date(adv.credit_date),
                        adjusted_amount=f"{q2(adjusted):.2f}",
                        outstanding_amount=f"{q2(outstanding):.2f}",
                        derived_from=["purchase.VendorAdvanceBalance", "purchase.VendorSettlement"],
                    ) if include_trace else None,
                )
                vendor_detail_rows.append(advance_row)

        vendor_net_outstanding = q2(vendor_positive_outstanding - vendor_credit_balance - vendor_advance_balance)
        if include_zero_balance is False and vendor_net_outstanding == ZERO and vendor_credit_balance == ZERO and vendor_advance_balance == ZERO and vendor_overdue == ZERO:
            continue
        if vendor_net_outstanding < ZERO and not include_credit_balances:
            continue
        if include_overdue_only and vendor_overdue <= ZERO:
            continue
        if outstanding_gt is not None and vendor_net_outstanding <= q2(outstanding_gt):
            continue
        if credit_limit_exceeded and credit_limit is not None and vendor_net_outstanding <= credit_limit:
            continue

        summary_row = _row_with_meta(
            {
                **_vendor_meta(vendor),
                "opening_balance": opening_balance,
                "bill_amount": q2(bill_totals.get(vendor.id, ZERO)),
                "payment_amount": q2(payment_totals.get(vendor.id, ZERO)),
                "outstanding": vendor_net_outstanding,
                "not_due": vendor_not_due,
                "bucket_0_30": q2(bucket_totals["bucket_0_30"]),
                "bucket_31_60": q2(bucket_totals["bucket_31_60"]),
                "bucket_61_90": q2(bucket_totals["bucket_61_90"]),
                "bucket_91_180": q2(bucket_totals["bucket_91_180"]),
                "bucket_181_plus": q2(bucket_totals["bucket_181_plus"]),
                "oldest_due_date": oldest_due_date,
                "last_bill_date": last_bill_date,
                "last_payment_date": all_last_payment.get(vendor.id),
                "credit_balance": vendor_credit_balance,
                "advance_balance": vendor_advance_balance,
                "overdue_amount": vendor_overdue,
            },
            drilldown={
                "vendor_detail": _drilldown_item(
                    label="Vendor Outstanding Detail",
                    target="vendor_outstanding",
                    report_code="vendor_outstanding",
                    path="/api/reports/payables/vendor-outstanding/",
                    params={
                        "entity": entity_id,
                        "entityfinid": entityfin_id,
                        "subentity": subentity_id,
                        "vendor": vendor.id,
                        "view": "detailed",
                        "as_of_date": as_of,
                        "aging_basis": normalized_aging_basis,
                        "show_not_due": show_not_due,
                        "show_settled": show_settled,
                        "include_zero_balance": include_zero_balance,
                        "include_credit_balances": include_credit_balances,
                        "include_advances_separately": include_advances_separately,
                    },
                ),
                "aging_summary": _drilldown_item(
                    label="AP Aging Summary",
                    target="ap_aging",
                    report_code="ap_aging",
                    path="/api/reports/payables/aging/",
                    params={
                        "entity": entity_id,
                        "entityfinid": entityfin_id,
                        "subentity": subentity_id,
                        "as_of_date": as_of,
                        "vendor": vendor.id,
                        "view": "summary",
                    },
                ),
                "aging_bill_list": _drilldown_item(
                    label="AP Aging Invoice",
                    target="ap_aging",
                    report_code="ap_aging",
                    path="/api/reports/payables/aging/",
                    params={
                        "entity": entity_id,
                        "entityfinid": entityfin_id,
                        "subentity": subentity_id,
                        "as_of_date": as_of,
                        "vendor": vendor.id,
                        "view": "invoice",
                    },
                ),
                "vendor_statement": _drilldown_item(
                    label="Vendor Statement",
                    target="purchase_ap_vendor_statement",
                    params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": vendor.id},
                ),
                "open_items": _drilldown_item(
                    label="Vendor Open Items",
                    target="purchase_ap_open_items",
                    params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": vendor.id},
                ),
                "payments": _drilldown_item(
                    label="Vendor Settlements",
                    target="purchase_ap_settlements",
                    params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": vendor.id},
                ),
            },
            trace=_trace_payload(
                source_model="purchase.VendorBillOpenItem",
                source_id=vendor.id,
                source_document_type="VendorSummary",
                source_document_number=vendor.effective_accounting_code,
                vendor_id=vendor.id,
                opening_balance=f"{opening_balance:.2f}",
                bill_amount=f"{q2(bill_totals.get(vendor.id, ZERO)):.2f}",
                payment_amount=f"{q2(payment_totals.get(vendor.id, ZERO)):.2f}",
                credit_balance=f"{vendor_credit_balance:.2f}",
                advance_balance=f"{vendor_advance_balance:.2f}",
                outstanding_total=f"{vendor_net_outstanding:.2f}",
                not_due=f"{vendor_not_due:.2f}",
                overdue_total=f"{vendor_overdue:.2f}",
                last_bill_date=_iso_date(last_bill_date),
                last_payment_date=_iso_date(all_last_payment.get(vendor.id)),
                derived_from=["purchase.VendorBillOpenItem", "purchase.VendorAdvanceBalance", "purchase.VendorSettlementLine"],
            ) if include_trace else None,
        )
        summary_rows.append(summary_row)

        if normalized_view == "detailed":
            detail_rows.extend(vendor_detail_rows)

        summary_totals["opening_balance"] += opening_balance
        summary_totals["bill_amount"] += q2(bill_totals.get(vendor.id, ZERO))
        summary_totals["payment_amount"] += q2(payment_totals.get(vendor.id, ZERO))
        summary_totals["outstanding"] += vendor_net_outstanding
        summary_totals["not_due"] += vendor_not_due
        summary_totals["bucket_0_30"] += bucket_totals["bucket_0_30"]
        summary_totals["bucket_31_60"] += bucket_totals["bucket_31_60"]
        summary_totals["bucket_61_90"] += bucket_totals["bucket_61_90"]
        summary_totals["bucket_91_180"] += bucket_totals["bucket_91_180"]
        summary_totals["bucket_181_plus"] += bucket_totals["bucket_181_plus"]
        summary_totals["credit_balance"] += vendor_credit_balance
        summary_totals["advance_balance"] += vendor_advance_balance
        summary_totals["overdue_amount"] += vendor_overdue

    rows = summary_rows if normalized_view == "summary" else detail_rows
    _sort_rows(rows, sort_by or ("outstanding" if normalized_view == "summary" else "outstanding_amount"), sort_order)
    paged_rows, total_rows = _paginate(rows, page, page_size)
    amount_fields = (
        "opening_balance",
        "bill_amount",
        "payment_amount",
        "outstanding",
        "not_due",
        "bucket_0_30",
        "bucket_31_60",
        "bucket_61_90",
        "bucket_91_180",
        "bucket_181_plus",
        "credit_balance",
        "advance_balance",
        "overdue_amount",
    )
    if normalized_view == "detailed":
        amount_fields = ("original_amount", "settled_amount", "outstanding_amount")
    _stringify_amount_fields(paged_rows, amount_fields)
    reconciliation_meta = _vendor_gl_reconciliation_meta(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        to_date=to_date,
        vendors=vendors,
        report_total=summary_totals["outstanding"],
        enabled=reconcile_gl,
    )

    return {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "from_date": from_date,
        "to_date": to_date,
        "view": normalized_view,
        "rows": paged_rows,
        "totals": {k: f"{q2(v):.2f}" for k, v in summary_totals.items()},
        "pagination": {"page": page, "page_size": page_size, "total_rows": total_rows, "paginated": True},
        "summary": {
            "vendor_count": len(summary_rows),
            "vendor_with_detail_count": len(detail_rows) if normalized_view == "detailed" else 0,
        },
        **_report_meta_payload(
            report_code="vendor_outstanding",
            report_name="Vendor Outstanding Report",
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            from_date=from_date,
            to_date=to_date,
            vendor_id=vendor_id,
            required_menu_code="reports.vendoroutstanding",
            required_permissions=["reports.vendoroutstanding.view"],
            view=normalized_view,
            feature_state={
                "reconcile_gl": reconcile_gl,
                "include_trace": include_trace,
                "aging_basis": normalized_aging_basis,
                "show_settled": show_settled,
                "show_not_due": show_not_due,
                "include_zero_balance": include_zero_balance,
                "include_credit_balances": include_credit_balances,
                "include_advances_separately": include_advances_separately,
            },
            extra_meta=reconciliation_meta,
        ),
    }


def build_ap_aging_report(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    as_of_date=None,
    vendor_id=None,
    vendor_group=None,
    region_id=None,
    currency=None,
    overdue_only=False,
    credit_limit_exceeded=False,
    search=None,
    sort_by=None,
    sort_order="desc",
    page=1,
    page_size=100,
    view="summary",
    include_trace=True,
):
    """Build AP aging in summary or invoice view.

    Summary view is intentionally unpaginated to match the payable report
    requirement for full vendor aging rollups. Invoice view remains paginated
    for large open-item datasets.
    """
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    as_of = coerce_date(as_of_date)
    if not as_of:
        raise ValueError("as_of_date is required.")

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
    vendor_by_id = {v.id: v for v in vendors}
    vendor_ids = set(vendor_by_id.keys())

    open_items_asof = asof_open_item_balances(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=as_of,
        vendor_ids=vendor_ids,
    )
    advances_asof = asof_advances(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=as_of,
        vendor_ids=vendor_ids,
    )
    last_payment_map = all_last_payment_dates(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=as_of,
    )

    invoice_rows_by_vendor = defaultdict(list)
    credit_pool = defaultdict(lambda: ZERO)
    for item, settled, outstanding in open_items_asof:
        if item.vendor_id not in vendor_ids:
            continue
        if outstanding > ZERO:
            paid_amount = _paid_amount_asof(item, settled)
            doc_type_name = item.header.get_doc_type_display() if getattr(item, "header", None) else str(item.doc_type)
            drilldown = {
                "invoice_list": _drilldown_item(
                    label="AP Aging Invoice",
                    target="ap_aging",
                    report_code="ap_aging",
                    path="/api/reports/payables/aging/",
                    params={
                        "entity": entity_id,
                        "entityfinid": entityfin_id,
                        "subentity": subentity_id,
                        "as_of_date": as_of,
                        "vendor": item.vendor_id,
                        "view": "invoice",
                    },
                ),
                "bill": _drilldown_item(
                    label="Purchase Document Detail",
                    target="purchase_document_detail",
                    params={"id": item.header_id, "entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id},
                ),
                "payment_allocation": _drilldown_item(
                    label="Settlement Allocation",
                    target="purchase_ap_payment_allocation",
                    params={
                        "entity": entity_id,
                        "entityfinid": entityfin_id,
                        "subentity": subentity_id,
                        "vendor": item.vendor_id,
                        "invoice_header": item.header_id,
                        "open_item": item.id,
                        "as_of_date": as_of,
                    },
                ),
                "vendor_statement": _drilldown_item(
                    label="Vendor Statement",
                    target="purchase_ap_vendor_statement",
                    params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": item.vendor_id},
                ),
            }
            invoice_rows_by_vendor[item.vendor_id].append(
                _row_with_meta(
                    {
                        "item_id": item.id,
                        "header_id": item.header_id,
                        "vendor_id": item.vendor_id,
                        "vendor_name": item.vendor.effective_accounting_name,
                        "vendor_code": item.vendor.effective_accounting_code,
                        "bill_number": item.purchase_number or item.supplier_invoice_number or f"BILL-{item.id}",
                        "supplier_invoice_number": item.supplier_invoice_number,
                        "document_type": item.doc_type,
                        "document_type_name": doc_type_name,
                        "bill_date": item.bill_date,
                        "due_date": item.due_date or item.bill_date,
                        "credit_days": ((item.due_date - item.bill_date).days if item.due_date else None),
                        "bill_amount": q2(item.original_amount),
                        "paid_amount": q2(paid_amount),
                        "residual_before_credit": q2(outstanding),
                        "branch": getattr(item.subentity, "subentityname", None),
                        "currency": getattr(getattr(item, "header", None), "currency_code", None) or account_currency(item.vendor) or "INR",
                        "gstin": account_gstno(item.vendor),
                        "credit_limit": q2(account_creditlimit(item.vendor) or ZERO) if account_creditlimit(item.vendor) is not None else None,
                        "last_payment_date": last_payment_map.get(item.vendor_id),
                    },
                    drilldown=drilldown,
                    trace=_trace_payload(
                        source_model="purchase.VendorBillOpenItem",
                        source_id=item.id,
                        source_document_id=item.header_id,
                        source_document_number=item.purchase_number or item.supplier_invoice_number or f"BILL-{item.id}",
                        source_document_type=doc_type_name,
                        vendor_id=item.vendor_id,
                        open_item_id=item.id,
                        bill_date=_iso_date(item.bill_date),
                        due_date=_iso_date(item.due_date or item.bill_date),
                        settled_amount=f"{q2(settled):.2f}",
                        outstanding_amount=f"{q2(outstanding):.2f}",
                        derived_from=["purchase.VendorBillOpenItem", "purchase.VendorSettlementLine"],
                    ) if include_trace else None,
                )
            )
        elif outstanding < ZERO:
            credit_pool[item.vendor_id] = q2(credit_pool[item.vendor_id] + abs(outstanding))
    for adv, _adjusted, outstanding in advances_asof:
        if adv.vendor_id in vendor_ids and outstanding > ZERO:
            credit_pool[adv.vendor_id] = q2(credit_pool[adv.vendor_id] + outstanding)

    invoice_rows = []
    summary_rows = []
    summary_totals = defaultdict(lambda: ZERO)
    for vendor_id_key, vendor in vendor_by_id.items():
        vendor_invoices = sorted(invoice_rows_by_vendor[vendor_id_key], key=lambda x: (x["due_date"], x["bill_date"], x["item_id"]))
        allocated_rows, residual_credit = _allocate_vendor_credits(vendor_invoices, credit_pool[vendor_id_key])

        buckets = defaultdict(lambda: ZERO)
        outstanding_total = ZERO
        overdue_total = ZERO
        for row in allocated_rows:
            balance = q2(row["residual_after_credit"])
            if balance <= ZERO:
                continue
            days_overdue = (as_of - row["due_date"]).days
            bucket = _aging_bucket(days_overdue)
            buckets[bucket] = q2(buckets[bucket] + balance)
            outstanding_total = q2(outstanding_total + balance)
            if days_overdue > 0:
                overdue_total = q2(overdue_total + balance)
            if view == "invoice":
                detail = {
                    **row,
                    "balance": balance,
                    "current": balance if bucket == "current" else ZERO,
                    "bucket_1_30": balance if bucket == "bucket_1_30" else ZERO,
                    "bucket_31_60": balance if bucket == "bucket_31_60" else ZERO,
                    "bucket_61_90": balance if bucket == "bucket_61_90" else ZERO,
                    "bucket_90_plus": balance if bucket == "bucket_90_plus" else ZERO,
                }
                invoice_rows.append(detail)

        vendor_credit_limit = account_creditlimit(vendor)
        credit_limit = q2(vendor_credit_limit or ZERO) if vendor_credit_limit is not None else None
        if outstanding_total == ZERO and residual_credit == ZERO:
            continue
        if overdue_only and overdue_total <= ZERO:
            continue
        if credit_limit_exceeded and credit_limit is not None and outstanding_total <= credit_limit:
            continue

        drilldown = {
            "vendor_statement": _drilldown_item(
                label="Vendor Statement",
                target="purchase_ap_vendor_statement",
                params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": vendor_id_key},
            ),
            "aging_summary": _drilldown_item(
                label="AP Aging Summary",
                target="ap_aging",
                report_code="ap_aging",
                path="/api/reports/payables/aging/",
                params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "as_of_date": as_of, "vendor": vendor_id_key, "view": "summary"},
            ),
            "invoice_view": _drilldown_item(
                label="AP Aging Invoice",
                target="ap_aging",
                report_code="ap_aging",
                path="/api/reports/payables/aging/",
                params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "as_of_date": as_of, "vendor": vendor_id_key, "view": "invoice"},
            ),
            "open_items": _drilldown_item(
                label="Vendor Open Items",
                target="purchase_ap_open_items",
                params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": vendor_id_key},
            ),
            "payments": _drilldown_item(
                label="Vendor Settlements",
                target="purchase_ap_settlements",
                params={"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": vendor_id_key},
            ),
        }
        summary = _row_with_meta(
            {
                **_vendor_meta(vendor),
                "outstanding": outstanding_total,
                "overdue_amount": overdue_total,
                "current": q2(buckets["current"]),
                "bucket_1_30": q2(buckets["bucket_1_30"]),
                "bucket_31_60": q2(buckets["bucket_31_60"]),
                "bucket_61_90": q2(buckets["bucket_61_90"]),
                "bucket_90_plus": q2(buckets["bucket_90_plus"]),
                "unapplied_advance": q2(residual_credit),
                "last_payment_date": last_payment_map.get(vendor_id_key),
                "credit_limit_exceeded": bool(credit_limit is not None and outstanding_total > credit_limit),
            },
            drilldown=drilldown,
            trace=_trace_payload(
                source_model="purchase.VendorBillOpenItem",
                source_id=vendor_id_key,
                source_document_type="VendorAgingSummary",
                source_document_number=vendor.effective_accounting_code,
                vendor_id=vendor_id_key,
                unapplied_advance=f"{q2(residual_credit):.2f}",
                last_payment_date=_iso_date(last_payment_map.get(vendor_id_key)),
                derived_from=["purchase.VendorBillOpenItem", "purchase.VendorAdvanceBalance", "purchase.VendorSettlementLine"],
            ) if include_trace else None,
        )
        summary_rows.append(summary)
        for key in ("outstanding", "overdue_amount", "current", "bucket_1_30", "bucket_31_60", "bucket_61_90", "bucket_90_plus", "unapplied_advance"):
            summary_totals[key] += summary[key]

    if view == "invoice":
        if vendor_id:
            invoice_rows = [row for row in invoice_rows if row["vendor_id"] == vendor_id]
        if overdue_only:
            invoice_rows = [
                row for row in invoice_rows
                if q2(row["bucket_1_30"]) + q2(row["bucket_31_60"]) + q2(row["bucket_61_90"]) + q2(row["bucket_90_plus"]) > ZERO
            ]
        _sort_rows(invoice_rows, sort_by or "balance", sort_order)
        paged_rows, total_rows = _paginate(invoice_rows, page, page_size)
        _stringify_amount_fields(
            paged_rows,
            ("bill_amount", "paid_amount", "balance", "current", "bucket_1_30", "bucket_31_60", "bucket_61_90", "bucket_90_plus", "credit_applied_fifo"),
        )
        return {
            "entity_id": entity_id,
            "entityfin_id": entityfin_id,
            "subentity_id": subentity_id,
            "as_of_date": as_of,
            "view": "invoice",
            "rows": paged_rows,
            "totals": {
                "balance": f"{q2(sum((q2(r['balance']) for r in invoice_rows), ZERO)):.2f}",
                "current": f"{q2(sum((q2(r['current']) for r in invoice_rows), ZERO)):.2f}",
                "bucket_1_30": f"{q2(sum((q2(r['bucket_1_30']) for r in invoice_rows), ZERO)):.2f}",
                "bucket_31_60": f"{q2(sum((q2(r['bucket_31_60']) for r in invoice_rows), ZERO)):.2f}",
                "bucket_61_90": f"{q2(sum((q2(r['bucket_61_90']) for r in invoice_rows), ZERO)):.2f}",
                "bucket_90_plus": f"{q2(sum((q2(r['bucket_90_plus']) for r in invoice_rows), ZERO)):.2f}",
            },
            "pagination": {"page": page, "page_size": page_size, "total_rows": total_rows, "paginated": True},
            **_report_meta_payload(
                report_code="ap_aging",
                report_name="AP Aging Report",
                entity_id=entity_id,
                entityfin_id=entityfin_id,
                subentity_id=subentity_id,
                as_of_date=as_of,
                view="invoice",
                vendor_id=vendor_id,
                required_menu_code="reports.accountspayableaging",
                required_permissions=["reports.accountspayableaging.view"],
                feature_state={"view": "invoice", "include_trace": include_trace},
            ),
        }

    _sort_rows(summary_rows, sort_by or "outstanding", sort_order)
    _stringify_amount_fields(
        summary_rows,
        ("outstanding", "overdue_amount", "current", "bucket_1_30", "bucket_31_60", "bucket_61_90", "bucket_90_plus", "unapplied_advance"),
    )
    total_rows = len(summary_rows)
    return {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "as_of_date": as_of,
        "view": "summary",
        "rows": summary_rows,
        "totals": {k: f"{q2(v):.2f}" for k, v in summary_totals.items()},
        "pagination": {"page": 1, "page_size": total_rows, "total_rows": total_rows, "paginated": False},
        "summary": {"vendor_count": total_rows},
        **_report_meta_payload(
            report_code="ap_aging",
            report_name="AP Aging Report",
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            as_of_date=as_of,
            view="summary",
            vendor_id=vendor_id,
            required_menu_code="reports.accountspayableaging",
            required_permissions=["reports.accountspayableaging.view"],
            feature_state={"view": "summary", "include_trace": include_trace},
        ),
    }


def build_payables_dashboard_summary(
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
):
    """Return a lightweight AP dashboard rollup for cards and top-vendor widgets."""
    summary_payload = build_ap_aging_report(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        as_of_date=as_of_date,
        vendor_id=vendor_id,
        vendor_group=vendor_group,
        region_id=region_id,
        currency=currency,
        search=search,
        sort_by="outstanding",
        sort_order="desc",
        view="summary",
    )
    rows = summary_payload["rows"]
    top_vendors = sorted(rows, key=lambda row: q2(row.get("outstanding") or ZERO), reverse=True)[:10]
    return {
        "entity_id": summary_payload["entity_id"],
        "entityfin_id": summary_payload["entityfin_id"],
        "subentity_id": summary_payload["subentity_id"],
        "as_of_date": summary_payload["as_of_date"],
        "totals": {
            "vendor_outstanding": summary_payload["totals"].get("outstanding", "0.00"),
            "overdue_outstanding": summary_payload["totals"].get("overdue_amount", "0.00"),
            "current": summary_payload["totals"].get("current", "0.00"),
            "bucket_1_30": summary_payload["totals"].get("bucket_1_30", "0.00"),
            "bucket_31_60": summary_payload["totals"].get("bucket_31_60", "0.00"),
            "bucket_61_90": summary_payload["totals"].get("bucket_61_90", "0.00"),
            "bucket_90_plus": summary_payload["totals"].get("bucket_90_plus", "0.00"),
        },
        "vendor_count_with_open_balance": summary_payload.get("summary", {}).get("vendor_count", 0),
        "summary": {
            "vendor_count_with_open_balance": summary_payload.get("summary", {}).get("vendor_count", 0),
            "top_vendor_count": len(top_vendors),
        },
        "pagination": {"page": 1, "page_size": len(top_vendors), "total_rows": len(top_vendors), "paginated": False},
        "top_vendors": [
            {
                "vendor_id": row["vendor_id"],
                "vendor_name": row["vendor_name"],
                "vendor_code": row["vendor_code"],
                "outstanding": row["outstanding"],
                "overdue_amount": row["overdue_amount"],
                "current": row["current"],
                "bucket_1_30": row["bucket_1_30"],
                "bucket_31_60": row["bucket_31_60"],
                "bucket_61_90": row["bucket_61_90"],
                "bucket_90_plus": row["bucket_90_plus"],
                "currency": row["currency"],
                "credit_limit_exceeded": row.get("credit_limit_exceeded", False),
                "_meta": row.get("_meta", {}),
            }
            for row in top_vendors
        ],
        **_report_meta_payload(
            report_code="payables_dashboard_summary",
            report_name="Payables Dashboard Summary",
            entity_id=entity_id,
            entityfin_id=entityfin_id,
            subentity_id=subentity_id,
            as_of_date=as_of_date,
            required_menu_code="reports.vendoroutstanding",
            required_permissions=["reports.vendoroutstanding.view", "reports.accountspayableaging.view"],
            extra_meta={"dashboard": True, "supports_drilldown": True},
        ),
    }



