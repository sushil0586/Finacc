from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from reports.selectors.financial import normalize_scope_ids
from reports.selectors.payables import (
    all_last_payment_dates,
    asof_advances,
    asof_open_item_balances,
    coerce_date,
    period_bill_credit_totals,
    posted_payment_totals,
    q2,
    resolve_scope_dates,
    vendor_queryset,
)

ZERO = Decimal("0.00")


def _paid_amount_asof(item, settled_asof):
    if q2(item.original_amount) <= ZERO:
        return ZERO
    return q2(min(q2(settled_asof), q2(item.original_amount)))


def _allocate_vendor_credits(invoice_rows, credit_amount):
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
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "bucket_1_30"
    if days_overdue <= 60:
        return "bucket_31_60"
    if days_overdue <= 90:
        return "bucket_61_90"
    return "bucket_90_plus"


def _vendor_meta(vendor, *, subentity_name=None):
    return {
        "vendor_id": vendor.id,
        "vendor_name": vendor.effective_accounting_name,
        "vendor_code": vendor.effective_accounting_code,
        "credit_limit": f"{q2(vendor.creditlimit or ZERO):.2f}" if vendor.creditlimit is not None else None,
        "credit_days": vendor.creditdays,
        "currency": vendor.currency or "INR",
        "branch": None,
        "subentity_name": subentity_name,
        "gstin": vendor.gstno,
        "vendor_group": vendor.agent,
        "region": getattr(getattr(vendor, "state", None), "statename", None) or getattr(getattr(vendor, "state", None), "state", None),
    }


def _payable_drilldown_flow():
    return [
        {"level": 1, "code": "vendor_outstanding", "label": "Vendor Outstanding"},
        {"level": 2, "code": "ap_aging", "label": "AP Aging"},
        {"level": 3, "code": "bill_list", "label": "Bill List"},
        {"level": 4, "code": "bill_detail", "label": "Bill Detail"},
        {"level": 5, "code": "payment_allocation", "label": "Payment Allocation"},
    ]


def _row_with_meta(row, *, drilldown):
    row = dict(row)
    row["can_drilldown"] = bool(drilldown)
    row["drilldown_targets"] = list(drilldown.keys())
    row["_meta"] = {"drilldown": drilldown}
    return row


def _report_meta_payload():
    hierarchy = _payable_drilldown_flow()
    return {
        "drilldown_hierarchy": [step["label"] for step in hierarchy],
        "_meta": {"drilldown_hierarchy": hierarchy},
    }


def _sort_rows(rows, sort_by, sort_order):
    reverse = (sort_order or "asc").lower() == "desc"
    field = (sort_by or "").strip().lower()

    def key(row):
        if field in {"outstanding", "net_outstanding", "overdue_amount", "opening_balance", "bill_amount", "balance"}:
            return q2(row.get(field) or row.get("net_outstanding") or ZERO)
        if field in {"vendor_code"}:
            return row.get("vendor_code") or 0
        if field in {"last_payment_date", "last_bill_date", "due_date", "bill_date"}:
            return row.get(field) or date.min
        return str(row.get(field) or row.get("vendor_name") or row.get("bill_number") or "").lower()

    rows.sort(key=key, reverse=reverse)
    return rows


def _paginate(rows, page, page_size):
    total = len(rows)
    start = max((page - 1) * page_size, 0)
    return rows[start:start + page_size], total


def build_vendor_outstanding_report(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    from_date=None,
    to_date=None,
    as_of_date=None,
    vendor_id=None,
    vendor_group=None,
    region_id=None,
    currency=None,
    overdue_only=False,
    outstanding_gt=None,
    credit_limit_exceeded=False,
    search=None,
    sort_by=None,
    sort_order="desc",
    page=1,
    page_size=100,
):
    entity_id, entityfin_id, subentity_id = normalize_scope_ids(entity_id, entityfin_id, subentity_id)
    from_date, to_date = resolve_scope_dates(entityfin_id, from_date, to_date, as_of_date)
    if not to_date:
        raise ValueError("to_date or as_of_date is required.")
    if not from_date:
        from_date = to_date
    opening_date = from_date - timedelta(days=1)

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
    vendor_ids = {v.id for v in vendors}

    open_items_opening = asof_open_item_balances(entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id, upto_date=opening_date)
    open_items_asof = asof_open_item_balances(entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id, upto_date=to_date)
    advances_opening = asof_advances(entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id, upto_date=opening_date)
    advances_asof = asof_advances(entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id, upto_date=to_date)
    payment_totals, _period_last_payment = posted_payment_totals(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        from_date=from_date,
        to_date=to_date,
    )
    all_last_payment = all_last_payment_dates(entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id, upto_date=to_date)
    bill_totals, credit_totals, last_bill_dates = period_bill_credit_totals(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        from_date=from_date,
        to_date=to_date,
    )

    opening_map = defaultdict(lambda: ZERO)
    for item, _settled, outstanding in open_items_opening:
        if item.vendor_id in vendor_ids:
            opening_map[item.vendor_id] = q2(opening_map[item.vendor_id] + outstanding)
    for adv, _adjusted, outstanding in advances_opening:
        if adv.vendor_id in vendor_ids:
            opening_map[adv.vendor_id] = q2(opening_map[adv.vendor_id] - outstanding)

    asof_item_map = defaultdict(lambda: ZERO)
    credit_source_map = defaultdict(lambda: ZERO)
    overdue_map = defaultdict(lambda: ZERO)
    for item, _settled, outstanding in open_items_asof:
        if item.vendor_id not in vendor_ids:
            continue
        asof_item_map[item.vendor_id] = q2(asof_item_map[item.vendor_id] + outstanding)
        if outstanding < ZERO:
            credit_source_map[item.vendor_id] = q2(credit_source_map[item.vendor_id] + abs(outstanding))
        elif outstanding > ZERO and item.due_date and item.due_date < to_date:
            overdue_map[item.vendor_id] = q2(overdue_map[item.vendor_id] + outstanding)
    unapplied_map = defaultdict(lambda: ZERO)
    for adv, _adjusted, outstanding in advances_asof:
        if adv.vendor_id in vendor_ids and outstanding > ZERO:
            unapplied_map[adv.vendor_id] = q2(unapplied_map[adv.vendor_id] + outstanding)

    rows = []
    totals = defaultdict(lambda: ZERO)
    for vendor in vendors:
        net_outstanding = q2(asof_item_map[vendor.id] - unapplied_map[vendor.id])
        overdue_amount = q2(max(overdue_map[vendor.id] - credit_source_map[vendor.id] - unapplied_map[vendor.id], ZERO))
        if (
            net_outstanding == ZERO
            and opening_map[vendor.id] == ZERO
            and bill_totals[vendor.id] == ZERO
            and payment_totals.get(vendor.id, ZERO) == ZERO
            and credit_totals[vendor.id] == ZERO
            and unapplied_map[vendor.id] == ZERO
        ):
            continue
        if overdue_only and overdue_amount <= ZERO:
            continue
        if outstanding_gt is not None and net_outstanding <= q2(outstanding_gt):
            continue
        if credit_limit_exceeded and vendor.creditlimit is not None and net_outstanding <= q2(vendor.creditlimit):
            continue

        drilldown = {
            "aging_summary": {
                "target": "ap_aging",
                "params": {
                    "entity": entity_id,
                    "entityfinid": entityfin_id,
                    "subentity": subentity_id,
                    "as_of_date": to_date,
                    "vendor": vendor.id,
                    "view": "summary",
                },
            },
            "aging_bill_list": {
                "target": "ap_aging",
                "params": {
                    "entity": entity_id,
                    "entityfinid": entityfin_id,
                    "subentity": subentity_id,
                    "as_of_date": to_date,
                    "vendor": vendor.id,
                    "view": "invoice",
                },
            },
            "vendor_statement": {
                "target": "purchase_ap_vendor_statement",
                "params": {"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": vendor.id},
            },
            "open_items": {
                "target": "purchase_ap_open_items",
                "params": {"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": vendor.id},
            },
            "payments": {
                "target": "purchase_ap_settlements",
                "params": {"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": vendor.id},
            },
        }
        row = _row_with_meta({
            **_vendor_meta(vendor),
            "opening_balance": q2(opening_map[vendor.id]),
            "bill_amount": q2(bill_totals[vendor.id]),
            "payment_amount": q2(payment_totals.get(vendor.id, ZERO)),
            "credit_note": q2(credit_totals[vendor.id]),
            "net_outstanding": net_outstanding,
            "overdue_amount": overdue_amount,
            "unapplied_advance": q2(unapplied_map[vendor.id]),
            "last_bill_date": last_bill_dates.get(vendor.id),
            "last_payment_date": all_last_payment.get(vendor.id),
        }, drilldown=drilldown)
        rows.append(row)
        totals["opening_balance"] += row["opening_balance"]
        totals["bill_amount"] += row["bill_amount"]
        totals["payment_amount"] += row["payment_amount"]
        totals["credit_note"] += row["credit_note"]
        totals["net_outstanding"] += row["net_outstanding"]
        totals["overdue_amount"] += row["overdue_amount"]
        totals["unapplied_advance"] += row["unapplied_advance"]

    _sort_rows(rows, sort_by or "net_outstanding", sort_order)
    paged_rows, total_rows = _paginate(rows, page, page_size)
    for row in paged_rows:
        for key in ("opening_balance", "bill_amount", "payment_amount", "credit_note", "net_outstanding", "overdue_amount", "unapplied_advance"):
            row[key] = f"{q2(row[key]):.2f}"

    return {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "from_date": from_date,
        "to_date": to_date,
        "rows": paged_rows,
        "totals": {k: f"{q2(v):.2f}" for k, v in totals.items()},
        "pagination": {"page": page, "page_size": page_size, "total_rows": total_rows},
        "summary": {"vendor_count": total_rows},
        **_report_meta_payload(),
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
):
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

    open_items_asof = asof_open_item_balances(entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id, upto_date=as_of)
    advances_asof = asof_advances(entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id, upto_date=as_of)
    last_payment_map = all_last_payment_dates(entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id, upto_date=as_of)

    invoice_rows_by_vendor = defaultdict(list)
    credit_pool = defaultdict(lambda: ZERO)
    for item, settled, outstanding in open_items_asof:
        if item.vendor_id not in vendor_ids:
            continue
        if outstanding > ZERO:
            paid_amount = _paid_amount_asof(item, settled)
            doc_type_name = item.header.get_doc_type_display() if getattr(item, "header", None) else str(item.doc_type)
            drilldown = {
                "invoice_list": {
                    "target": "ap_aging",
                    "params": {
                        "entity": entity_id,
                        "entityfinid": entityfin_id,
                        "subentity": subentity_id,
                        "as_of_date": as_of,
                        "vendor": item.vendor_id,
                        "view": "invoice",
                    },
                },
                "bill": {
                    "target": "purchase_document_detail",
                    "params": {"id": item.header_id, "entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id},
                },
                "payment_allocation": {
                    "target": "purchase_ap_payment_allocation",
                    "params": {
                        "entity": entity_id,
                        "entityfinid": entityfin_id,
                        "subentity": subentity_id,
                        "vendor": item.vendor_id,
                        "invoice_header": item.header_id,
                        "open_item": item.id,
                        "as_of_date": as_of,
                    },
                },
                "vendor_statement": {
                    "target": "purchase_ap_vendor_statement",
                    "params": {"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": item.vendor_id},
                },
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
                        "currency": getattr(getattr(item, "header", None), "currency_code", None) or item.vendor.currency or "INR",
                        "gstin": item.vendor.gstno,
                        "credit_limit": q2(item.vendor.creditlimit or ZERO) if item.vendor.creditlimit is not None else None,
                        "last_payment_date": last_payment_map.get(item.vendor_id),
                    },
                    drilldown=drilldown,
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
                if view == "invoice":
                    continue
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

        credit_limit = q2(vendor.creditlimit or ZERO) if vendor.creditlimit is not None else None
        if outstanding_total == ZERO and residual_credit == ZERO:
            continue
        if overdue_only and overdue_total <= ZERO:
            continue
        if credit_limit_exceeded and credit_limit is not None and outstanding_total <= credit_limit:
            continue

        drilldown = {
            "vendor_statement": {
                "target": "purchase_ap_vendor_statement",
                "params": {"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "vendor": vendor_id_key},
            },
            "aging_summary": {
                "target": "ap_aging",
                "params": {"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "as_of_date": as_of, "vendor": vendor_id_key, "view": "summary"},
            },
            "invoice_view": {
                "target": "ap_aging",
                "params": {"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "as_of_date": as_of, "vendor": vendor_id_key, "view": "invoice"},
            },
        }
        summary = _row_with_meta({
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
        }, drilldown=drilldown)
        summary_rows.append(summary)
        for key in ("outstanding", "overdue_amount", "current", "bucket_1_30", "bucket_31_60", "bucket_61_90", "bucket_90_plus", "unapplied_advance"):
            summary_totals[key] += summary[key]

    if view == "invoice":
        if vendor_id:
            invoice_rows = [row for row in invoice_rows if row["vendor_id"] == vendor_id]
        if overdue_only:
            invoice_rows = [row for row in invoice_rows if q2(row["bucket_1_30"]) + q2(row["bucket_31_60"]) + q2(row["bucket_61_90"]) + q2(row["bucket_90_plus"]) > ZERO]
        _sort_rows(invoice_rows, sort_by or "balance", sort_order)
        paged_rows, total_rows = _paginate(invoice_rows, page, page_size)
        for row in paged_rows:
            for key in ("bill_amount", "paid_amount", "balance", "current", "bucket_1_30", "bucket_31_60", "bucket_61_90", "bucket_90_plus", "credit_applied_fifo"):
                row[key] = f"{q2(row[key]):.2f}"
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
            "pagination": {"page": page, "page_size": page_size, "total_rows": total_rows},
            **_report_meta_payload(),
        }

    _sort_rows(summary_rows, sort_by or "outstanding", sort_order)
    paged_rows, total_rows = _paginate(summary_rows, page, page_size)
    for row in paged_rows:
        for key in ("outstanding", "overdue_amount", "current", "bucket_1_30", "bucket_31_60", "bucket_61_90", "bucket_90_plus", "unapplied_advance"):
            row[key] = f"{q2(row[key]):.2f}"
    return {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "as_of_date": as_of,
        "view": "summary",
        "rows": paged_rows,
        "totals": {k: f"{q2(v):.2f}" for k, v in summary_totals.items()},
        "pagination": {"page": page, "page_size": page_size, "total_rows": total_rows},
        "summary": {"vendor_count": total_rows},
        **_report_meta_payload(),
    }
