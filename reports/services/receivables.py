from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Max, Q, Sum

from financial.profile_access import (
    account_agent,
    account_creditdays,
    account_creditlimit,
    account_currency,
    account_gstno,
    account_region_state,
)

from financial.models import account
from sales.models.sales_ar import CustomerAdvanceBalance, CustomerBillOpenItem, CustomerSettlement, CustomerSettlementLine
from sales.models.sales_core import SalesInvoiceHeader
from reports.selectors.financial import normalize_scope_ids, resolve_date_window


ZERO = Decimal("0.00")
Q2P = Decimal("0.01")


def q2(value) -> Decimal:
    return Decimal(value or 0).quantize(Q2P, rounding=ROUND_HALF_UP)


def _coerce_date(value):
    if value is None:
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        return value.date()
    return date.fromisoformat(str(value))


def _resolve_scope_dates(entityfin_id=None, from_date=None, to_date=None, as_of_date=None):
    explicit_from = _coerce_date(from_date)
    explicit_to = _coerce_date(as_of_date or to_date)
    if entityfin_id:
        fy_start, fy_end = resolve_date_window(entityfin_id, None, None)
        fy_start = _coerce_date(fy_start)
        fy_end = _coerce_date(fy_end)
        return _coerce_date(explicit_from or fy_start), _coerce_date(explicit_to or fy_end)
    return _coerce_date(explicit_from), _coerce_date(explicit_to)


def _customer_queryset(*, entity_id, customer_id=None, customer_group=None, region_id=None, currency=None, search=None):
    qs = account.objects.filter(entity_id=entity_id)
    qs = qs.filter(
        Q(commercial_profile__partytype__in=["Customer", "Both", "Bank"])
        | Q(commercial_profile__partytype__isnull=True)
        | Q(commercial_profile__partytype="")
    )
    if customer_id:
        qs = qs.filter(id=customer_id)
    if customer_group:
        qs = qs.filter(commercial_profile__agent__iexact=customer_group)
    if region_id:
        qs = qs.filter(state_id=region_id)
    if currency:
        qs = qs.filter(commercial_profile__currency__iexact=currency)
    if search:
        token = str(search).strip()
        qs = qs.filter(
            Q(accountname__icontains=token)
            | Q(legalname__icontains=token)
            | Q(accountcode__icontains=token)
            | Q(compliance_profile__gstno__icontains=token)
        )
    return qs.select_related("ledger", "state", "commercial_profile", "compliance_profile").order_by("accountname", "id")


def _scope_filter(qs, *, entity_id, entityfin_id, subentity_id):
    qs = qs.filter(entity_id=entity_id)
    if entityfin_id:
        qs = qs.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(subentity_id=subentity_id)
    return qs


def _settlement_line_sums(*, entity_id, entityfin_id, subentity_id, upto_date):
    qs = CustomerSettlementLine.objects.filter(
        settlement__status=CustomerSettlement.Status.POSTED,
        settlement__settlement_date__lte=upto_date,
        settlement__entity_id=entity_id,
    )
    if entityfin_id:
        qs = qs.filter(settlement__entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(settlement__subentity_id=subentity_id)
    rows = qs.values("open_item_id").annotate(applied=Sum("applied_amount_signed"))
    return {row["open_item_id"]: q2(row["applied"] or ZERO) for row in rows}


def _advance_adjusted_sums(*, entity_id, entityfin_id, subentity_id, upto_date):
    qs = CustomerSettlement.objects.filter(
        status=CustomerSettlement.Status.POSTED,
        advance_balance_id__isnull=False,
        settlement_date__lte=upto_date,
        entity_id=entity_id,
    )
    if entityfin_id:
        qs = qs.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(subentity_id=subentity_id)
    rows = qs.values("advance_balance_id").annotate(applied=Sum("total_amount"))
    return {row["advance_balance_id"]: q2(row["applied"] or ZERO) for row in rows}


def _asof_open_item_balances(*, entity_id, entityfin_id, subentity_id, upto_date):
    line_map = _settlement_line_sums(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=upto_date,
    )
    qs = _scope_filter(
        CustomerBillOpenItem.objects.select_related("customer", "customer__ledger", "customer__commercial_profile", "customer__compliance_profile", "subentity", "header"),
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
    ).filter(bill_date__lte=upto_date)
    rows = []
    for item in qs:
        settled = line_map.get(item.id, ZERO)
        outstanding = q2(item.original_amount - settled)
        rows.append((item, settled, outstanding))
    return rows


def _asof_advances(*, entity_id, entityfin_id, subentity_id, upto_date):
    adjusted_map = _advance_adjusted_sums(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=upto_date,
    )
    qs = _scope_filter(
        CustomerAdvanceBalance.objects.select_related("customer", "customer__ledger", "customer__commercial_profile", "customer__compliance_profile", "subentity", "receipt_voucher"),
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
    ).filter(credit_date__lte=upto_date)
    rows = []
    for adv in qs:
        adjusted = adjusted_map.get(adv.id, ZERO)
        outstanding = q2(adv.original_amount - adjusted)
        rows.append((adv, adjusted, outstanding))
    return rows


def _posted_receipt_totals(*, entity_id, entityfin_id, subentity_id, from_date, to_date):
    qs = CustomerSettlement.objects.filter(
        entity_id=entity_id,
        status=CustomerSettlement.Status.POSTED,
        settlement_type=CustomerSettlement.SettlementType.RECEIPT,
        settlement_date__gte=from_date,
        settlement_date__lte=to_date,
    )
    if entityfin_id:
        qs = qs.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(subentity_id=subentity_id)
    rows = qs.values("customer_id").annotate(total=Sum("total_amount"), last_payment_date=Max("settlement_date"))
    total_map = {row["customer_id"]: q2(row["total"] or ZERO) for row in rows}
    last_map = {row["customer_id"]: row["last_payment_date"] for row in rows}
    return total_map, last_map


def _all_last_payment_dates(*, entity_id, entityfin_id, subentity_id, upto_date):
    qs = CustomerSettlement.objects.filter(
        entity_id=entity_id,
        status=CustomerSettlement.Status.POSTED,
        settlement_type=CustomerSettlement.SettlementType.RECEIPT,
        settlement_date__lte=upto_date,
    )
    if entityfin_id:
        qs = qs.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(subentity_id=subentity_id)
    rows = qs.values("customer_id").annotate(last_payment_date=Max("settlement_date"))
    return {row["customer_id"]: row["last_payment_date"] for row in rows}


def _period_invoice_credit_totals(*, entity_id, entityfin_id, subentity_id, from_date, to_date):
    qs = _scope_filter(
        CustomerBillOpenItem.objects.select_related("header"),
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
    ).filter(bill_date__gte=from_date, bill_date__lte=to_date)
    invoice_map = defaultdict(lambda: ZERO)
    credit_map = defaultdict(lambda: ZERO)
    last_invoice_date = {}
    for item in qs:
        if q2(item.original_amount) >= ZERO:
            invoice_map[item.customer_id] = q2(invoice_map[item.customer_id] + q2(item.original_amount))
            prev = last_invoice_date.get(item.customer_id)
            if prev is None or item.bill_date > prev:
                last_invoice_date[item.customer_id] = item.bill_date
        else:
            credit_map[item.customer_id] = q2(credit_map[item.customer_id] + abs(q2(item.original_amount)))
    return invoice_map, credit_map, last_invoice_date


def _received_amount_asof(item, settled_asof):
    if q2(item.original_amount) <= ZERO:
        return ZERO
    return q2(min(q2(settled_asof), q2(item.original_amount)))


def _allocate_customer_credits(invoice_rows, credit_amount):
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


def _customer_meta(cust, *, subentity_name=None):
    return {
        "customer_id": cust.id,
        "customer_name": cust.effective_accounting_name,
        "customer_code": cust.effective_accounting_code,
        "credit_limit": f"{q2(account_creditlimit(cust) or ZERO):.2f}" if account_creditlimit(cust) is not None else None,
        "credit_days": account_creditdays(cust),
        "currency": account_currency(cust) or "INR",
        "branch": None,
        "subentity_name": subentity_name,
        "gstin": account_gstno(cust),
        "customer_group": account_agent(cust),
        "region": getattr(account_region_state(cust), "statename", None) or getattr(account_region_state(cust), "state", None),
        "salesperson": None,
    }


def _receivable_drilldown_flow():
    return [
        {"level": 1, "code": "customer_outstanding", "label": "Customer Outstanding"},
        {"level": 2, "code": "receivable_aging", "label": "Receivable Aging"},
        {"level": 3, "code": "invoice_list", "label": "Invoice List"},
        {"level": 4, "code": "invoice_detail", "label": "Invoice Detail"},
        {"level": 5, "code": "payment_allocation", "label": "Payment Allocation"},
    ]


def _row_with_meta(row, *, drilldown):
    row = dict(row)
    row["can_drilldown"] = bool(drilldown)
    row["drilldown_targets"] = list(drilldown.keys())
    row["_meta"] = {"drilldown": drilldown}
    return row


def _report_meta_payload():
    hierarchy = _receivable_drilldown_flow()
    return {
        "drilldown_hierarchy": [step["label"] for step in hierarchy],
        "_meta": {"drilldown_hierarchy": hierarchy},
    }


def _sort_rows(rows, sort_by, sort_order):
    reverse = (sort_order or "asc").lower() == "desc"
    field = (sort_by or "").strip().lower()

    def key(row):
        if field in {"outstanding", "net_outstanding", "overdue_amount", "opening_balance", "invoice_amount"}:
            return q2(row.get(field) or row.get("net_outstanding") or ZERO)
        if field in {"customer_code"}:
            return row.get("customer_code") or 0
        if field in {"last_payment_date", "last_invoice_date", "due_date", "invoice_date"}:
            return row.get(field) or date.min
        return str(row.get(field) or row.get("customer_name") or row.get("invoice_number") or "").lower()

    rows.sort(key=key, reverse=reverse)
    return rows


def _paginate(rows, page, page_size):
    total = len(rows)
    start = max((page - 1) * page_size, 0)
    return rows[start:start + page_size], total


def build_customer_outstanding_report(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    from_date=None,
    to_date=None,
    as_of_date=None,
    customer_id=None,
    customer_group=None,
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
    from_date, to_date = _resolve_scope_dates(entityfin_id, from_date, to_date, as_of_date)
    if not to_date:
        raise ValueError("to_date or as_of_date is required.")
    if not from_date:
        from_date = to_date
    opening_date = from_date - timedelta(days=1)

    customers = list(
        _customer_queryset(
            entity_id=entity_id,
            customer_id=customer_id,
            customer_group=customer_group,
            region_id=region_id,
            currency=currency,
            search=search,
        )
    )
    customer_ids = {c.id for c in customers}

    open_items_opening = _asof_open_item_balances(
        entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id, upto_date=opening_date
    )
    open_items_asof = _asof_open_item_balances(
        entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id, upto_date=to_date
    )
    advances_opening = _asof_advances(
        entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id, upto_date=opening_date
    )
    advances_asof = _asof_advances(
        entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id, upto_date=to_date
    )
    receipt_totals, _period_last_pay = _posted_receipt_totals(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        from_date=from_date,
        to_date=to_date,
    )
    all_last_payment = _all_last_payment_dates(
        entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id, upto_date=to_date
    )
    invoice_totals, credit_totals, last_invoice_dates = _period_invoice_credit_totals(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        from_date=from_date,
        to_date=to_date,
    )

    opening_map = defaultdict(lambda: ZERO)
    for item, _settled, outstanding in open_items_opening:
        if item.customer_id in customer_ids:
            opening_map[item.customer_id] = q2(opening_map[item.customer_id] + outstanding)
    for adv, _adjusted, outstanding in advances_opening:
        if adv.customer_id in customer_ids:
            opening_map[adv.customer_id] = q2(opening_map[adv.customer_id] - outstanding)

    asof_item_map = defaultdict(lambda: ZERO)
    credit_source_map = defaultdict(lambda: ZERO)
    overdue_map = defaultdict(lambda: ZERO)
    for item, settled, outstanding in open_items_asof:
        if item.customer_id not in customer_ids:
            continue
        asof_item_map[item.customer_id] = q2(asof_item_map[item.customer_id] + outstanding)
        if outstanding < ZERO:
            credit_source_map[item.customer_id] = q2(credit_source_map[item.customer_id] + abs(outstanding))
        elif outstanding > ZERO and item.due_date and item.due_date < to_date:
            overdue_map[item.customer_id] = q2(overdue_map[item.customer_id] + outstanding)
    unapplied_map = defaultdict(lambda: ZERO)
    for adv, _adjusted, outstanding in advances_asof:
        if adv.customer_id in customer_ids and outstanding > ZERO:
            unapplied_map[adv.customer_id] = q2(unapplied_map[adv.customer_id] + outstanding)

    rows = []
    totals = defaultdict(lambda: ZERO)
    for cust in customers:
        net_outstanding = q2(asof_item_map[cust.id] - unapplied_map[cust.id])
        overdue_amount = q2(max(overdue_map[cust.id] - credit_source_map[cust.id] - unapplied_map[cust.id], ZERO))
        if (
            net_outstanding == ZERO
            and opening_map[cust.id] == ZERO
            and invoice_totals[cust.id] == ZERO
            and receipt_totals.get(cust.id, ZERO) == ZERO
            and credit_totals[cust.id] == ZERO
            and unapplied_map[cust.id] == ZERO
        ):
            continue
        if overdue_only and overdue_amount <= ZERO:
            continue
        if outstanding_gt is not None and net_outstanding <= q2(outstanding_gt):
            continue
        customer_credit_limit = account_creditlimit(cust)
        if credit_limit_exceeded and customer_credit_limit is not None and net_outstanding <= q2(customer_credit_limit):
            continue

        drilldown = {
            "aging_summary": {
                "target": "receivable_aging",
                "params": {
                    "entity": entity_id,
                    "entityfinid": entityfin_id,
                    "subentity": subentity_id,
                    "as_of_date": to_date,
                    "customer": cust.id,
                    "view": "summary",
                },
            },
            "aging_invoice_list": {
                "target": "receivable_aging",
                "params": {
                    "entity": entity_id,
                    "entityfinid": entityfin_id,
                    "subentity": subentity_id,
                    "as_of_date": to_date,
                    "customer": cust.id,
                    "view": "invoice",
                },
            },
            "customer_statement": {
                "target": "sales_ar_customer_statement",
                "params": {"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "customer": cust.id},
            },
            "open_items": {
                "target": "sales_ar_open_items",
                "params": {"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "customer": cust.id},
            },
            "payments": {
                "target": "sales_ar_settlements",
                "params": {"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "customer": cust.id},
            },
        }
        row = _row_with_meta({
            **_customer_meta(cust),
            "opening_balance": q2(opening_map[cust.id]),
            "invoice_amount": q2(invoice_totals[cust.id]),
            "receipt_amount": q2(receipt_totals.get(cust.id, ZERO)),
            "credit_note": q2(credit_totals[cust.id]),
            "net_outstanding": net_outstanding,
            "overdue_amount": overdue_amount,
            "unapplied_receipt": q2(unapplied_map[cust.id]),
            "last_invoice_date": last_invoice_dates.get(cust.id),
            "last_payment_date": all_last_payment.get(cust.id),
        }, drilldown=drilldown)
        rows.append(row)
        totals["opening_balance"] += row["opening_balance"]
        totals["invoice_amount"] += row["invoice_amount"]
        totals["receipt_amount"] += row["receipt_amount"]
        totals["credit_note"] += row["credit_note"]
        totals["net_outstanding"] += row["net_outstanding"]
        totals["overdue_amount"] += row["overdue_amount"]
        totals["unapplied_receipt"] += row["unapplied_receipt"]

    _sort_rows(rows, sort_by or "net_outstanding", sort_order)
    paged_rows, total_rows = _paginate(rows, page, page_size)

    for row in paged_rows:
        for key in ("opening_balance", "invoice_amount", "receipt_amount", "credit_note", "net_outstanding", "overdue_amount", "unapplied_receipt"):
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
        "summary": {"customer_count": total_rows},
        **_report_meta_payload(),
    }


def build_receivable_aging_report(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    as_of_date=None,
    customer_id=None,
    customer_group=None,
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
    as_of = _coerce_date(as_of_date)
    if not as_of:
        raise ValueError("as_of_date is required.")

    customers = list(
        _customer_queryset(
            entity_id=entity_id,
            customer_id=customer_id,
            customer_group=customer_group,
            region_id=region_id,
            currency=currency,
            search=search,
        )
    )
    customer_by_id = {c.id: c for c in customers}
    customer_ids = set(customer_by_id.keys())

    open_items_asof = _asof_open_item_balances(
        entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id, upto_date=as_of
    )
    advances_asof = _asof_advances(
        entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id, upto_date=as_of
    )
    last_payment_map = _all_last_payment_dates(
        entity_id=entity_id, entityfin_id=entityfin_id, subentity_id=subentity_id, upto_date=as_of
    )

    invoice_rows_by_customer = defaultdict(list)
    credit_pool = defaultdict(lambda: ZERO)
    for item, settled, outstanding in open_items_asof:
        if item.customer_id not in customer_ids:
            continue
        if outstanding > ZERO:
            received_amount = _received_amount_asof(item, settled)
            drilldown = {
                "invoice_list": {
                    "target": "receivable_aging",
                    "params": {
                        "entity": entity_id,
                        "entityfinid": entityfin_id,
                        "subentity": subentity_id,
                        "as_of_date": as_of,
                        "customer": item.customer_id,
                        "view": "invoice",
                    },
                },
                "invoice": {
                    "target": "sales_invoice",
                    "params": {"id": item.header_id, "entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id},
                },
                "payment_allocation": {
                    "target": "sales_ar_payment_allocation",
                    "params": {
                        "entity": entity_id,
                        "entityfinid": entityfin_id,
                        "subentity": subentity_id,
                        "customer": item.customer_id,
                        "invoice_header": item.header_id,
                        "open_item": item.id,
                        "as_of_date": as_of,
                    },
                },
                "customer_statement": {
                    "target": "sales_ar_customer_statement",
                    "params": {"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "customer": item.customer_id},
                },
            }
            invoice_rows_by_customer[item.customer_id].append(
                _row_with_meta(
                    {
                        "item_id": item.id,
                        "header_id": item.header_id,
                        "customer_id": item.customer_id,
                        "customer_name": item.customer.effective_accounting_name,
                        "customer_code": item.customer.effective_accounting_code,
                        "invoice_number": item.invoice_number or item.customer_reference_number or f"INV-{item.id}",
                        "invoice_date": item.bill_date,
                        "due_date": item.due_date or item.bill_date,
                        "credit_days": ((item.due_date - item.bill_date).days if item.due_date else None),
                        "invoice_amount": q2(item.original_amount),
                        "received_amount": q2(received_amount),
                        "residual_before_credit": q2(outstanding),
                        "salesperson": None,
                        "branch": getattr(item.subentity, "subentityname", None),
                        "currency": account_currency(item.customer) or "INR",
                        "gstin": account_gstno(item.customer),
                        "credit_limit": q2(account_creditlimit(item.customer) or ZERO) if account_creditlimit(item.customer) is not None else None,
                        "last_payment_date": last_payment_map.get(item.customer_id),
                    },
                    drilldown=drilldown,
                )
            )
        elif outstanding < ZERO:
            credit_pool[item.customer_id] = q2(credit_pool[item.customer_id] + abs(outstanding))
    for adv, _adjusted, outstanding in advances_asof:
        if adv.customer_id in customer_ids and outstanding > ZERO:
            credit_pool[adv.customer_id] = q2(credit_pool[adv.customer_id] + outstanding)

    invoice_rows = []
    summary_rows = []
    summary_totals = defaultdict(lambda: ZERO)
    for cust_id, cust in customer_by_id.items():
        cust_invoices = sorted(invoice_rows_by_customer[cust_id], key=lambda x: (x["due_date"], x["invoice_date"], x["item_id"]))
        allocated_rows, residual_credit = _allocate_customer_credits(cust_invoices, credit_pool[cust_id])

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

        customer_credit_limit = account_creditlimit(cust)
        credit_limit = q2(customer_credit_limit or ZERO) if customer_credit_limit is not None else None
        if outstanding_total == ZERO and residual_credit == ZERO:
            continue
        if overdue_only and overdue_total <= ZERO:
            continue
        if credit_limit_exceeded and credit_limit is not None and outstanding_total <= credit_limit:
            continue

        drilldown = {
            "customer_statement": {
                "target": "sales_ar_customer_statement",
                "params": {"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "customer": cust_id},
            },
            "aging_summary": {
                "target": "receivable_aging",
                "params": {"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "as_of_date": as_of, "customer": cust_id, "view": "summary"},
            },
            "invoice_view": {
                "target": "receivable_aging",
                "params": {"entity": entity_id, "entityfinid": entityfin_id, "subentity": subentity_id, "as_of_date": as_of, "customer": cust_id, "view": "invoice"},
            },
        }
        summary = _row_with_meta({
            **_customer_meta(cust),
            "outstanding": outstanding_total,
            "overdue_amount": overdue_total,
            "current": q2(buckets["current"]),
            "bucket_1_30": q2(buckets["bucket_1_30"]),
            "bucket_31_60": q2(buckets["bucket_31_60"]),
            "bucket_61_90": q2(buckets["bucket_61_90"]),
            "bucket_90_plus": q2(buckets["bucket_90_plus"]),
            "unapplied_receipt": q2(residual_credit),
            "last_payment_date": last_payment_map.get(cust_id),
            "credit_limit_exceeded": bool(credit_limit is not None and outstanding_total > credit_limit),
        }, drilldown=drilldown)
        summary_rows.append(summary)
        for key in ("outstanding", "overdue_amount", "current", "bucket_1_30", "bucket_31_60", "bucket_61_90", "bucket_90_plus", "unapplied_receipt"):
            summary_totals[key] += summary[key]

    if view == "invoice":
        if customer_id:
            invoice_rows = [row for row in invoice_rows if row["customer_id"] == customer_id]
        if overdue_only:
            invoice_rows = [row for row in invoice_rows if q2(row["bucket_1_30"]) + q2(row["bucket_31_60"]) + q2(row["bucket_61_90"]) + q2(row["bucket_90_plus"]) > ZERO]
        _sort_rows(invoice_rows, sort_by or "balance", sort_order)
        paged_rows, total_rows = _paginate(invoice_rows, page, page_size)
        for row in paged_rows:
            for key in ("invoice_amount", "received_amount", "balance", "current", "bucket_1_30", "bucket_31_60", "bucket_61_90", "bucket_90_plus", "credit_applied_fifo"):
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
        for key in ("outstanding", "overdue_amount", "current", "bucket_1_30", "bucket_31_60", "bucket_61_90", "bucket_90_plus", "unapplied_receipt"):
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
        "summary": {"customer_count": total_rows},
        **_report_meta_payload(),
    }
