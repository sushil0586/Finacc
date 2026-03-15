from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Max, Q, Sum

from financial.models import account
from purchase.models.purchase_ap import (
    VendorAdvanceBalance,
    VendorBillOpenItem,
    VendorSettlement,
    VendorSettlementLine,
)
from reports.selectors.financial import normalize_scope_ids, resolve_date_window

ZERO = Decimal("0.00")
Q2P = Decimal("0.01")


def q2(value) -> Decimal:
    return Decimal(value or 0).quantize(Q2P, rounding=ROUND_HALF_UP)


def coerce_date(value):
    if value is None:
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        return value.date()
    return date.fromisoformat(str(value))


def resolve_scope_dates(entityfin_id=None, from_date=None, to_date=None, as_of_date=None):
    explicit_from = coerce_date(from_date)
    explicit_to = coerce_date(as_of_date or to_date)
    if entityfin_id:
        fy_start, fy_end = resolve_date_window(entityfin_id, None, None)
        fy_start = coerce_date(fy_start)
        fy_end = coerce_date(fy_end)
        return coerce_date(explicit_from or fy_start), coerce_date(explicit_to or fy_end)
    return coerce_date(explicit_from), coerce_date(explicit_to)


def vendor_queryset(*, entity_id, vendor_id=None, vendor_group=None, region_id=None, currency=None, search=None):
    qs = account.objects.filter(entity_id=entity_id)
    qs = qs.filter(Q(partytype__in=["Vendor", "Both"]) | Q(partytype__isnull=True) | Q(partytype=""))
    if vendor_id:
        qs = qs.filter(id=vendor_id)
    if vendor_group:
        qs = qs.filter(agent__iexact=vendor_group)
    if region_id:
        qs = qs.filter(state_id=region_id)
    if currency:
        qs = qs.filter(currency__iexact=currency)
    if search:
        token = str(search).strip()
        qs = qs.filter(
            Q(accountname__icontains=token)
            | Q(legalname__icontains=token)
            | Q(accountcode__icontains=token)
            | Q(gstno__icontains=token)
        )
    return qs.select_related("ledger", "state").order_by("accountname", "id")


def scope_filter(qs, *, entity_id, entityfin_id, subentity_id):
    qs = qs.filter(entity_id=entity_id)
    if entityfin_id:
        qs = qs.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))
    return qs


def settlement_line_sums(*, entity_id, entityfin_id, subentity_id, upto_date):
    qs = VendorSettlementLine.objects.filter(
        settlement__status=VendorSettlement.Status.POSTED,
        settlement__settlement_date__lte=upto_date,
        settlement__entity_id=entity_id,
    )
    if entityfin_id:
        qs = qs.filter(settlement__entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(Q(settlement__subentity_id=subentity_id) | Q(settlement__subentity__isnull=True))
    rows = qs.values("open_item_id").annotate(applied=Sum("applied_amount_signed"))
    return {row["open_item_id"]: q2(row["applied"] or ZERO) for row in rows}


def advance_adjusted_sums(*, entity_id, entityfin_id, subentity_id, upto_date):
    qs = VendorSettlement.objects.filter(
        status=VendorSettlement.Status.POSTED,
        advance_balance_id__isnull=False,
        settlement_date__lte=upto_date,
        entity_id=entity_id,
    )
    if entityfin_id:
        qs = qs.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))
    rows = qs.values("advance_balance_id").annotate(applied=Sum("total_amount"))
    return {row["advance_balance_id"]: q2(row["applied"] or ZERO) for row in rows}


def asof_open_item_balances(*, entity_id, entityfin_id, subentity_id, upto_date):
    line_map = settlement_line_sums(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=upto_date,
    )
    qs = scope_filter(
        VendorBillOpenItem.objects.select_related("vendor", "vendor__ledger", "subentity", "header"),
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


def asof_advances(*, entity_id, entityfin_id, subentity_id, upto_date):
    adjusted_map = advance_adjusted_sums(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=upto_date,
    )
    qs = scope_filter(
        VendorAdvanceBalance.objects.select_related("vendor", "vendor__ledger", "subentity", "payment_voucher"),
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


def posted_payment_totals(*, entity_id, entityfin_id, subentity_id, from_date, to_date):
    qs = VendorSettlement.objects.filter(
        entity_id=entity_id,
        status=VendorSettlement.Status.POSTED,
        settlement_type=VendorSettlement.SettlementType.PAYMENT,
        settlement_date__gte=from_date,
        settlement_date__lte=to_date,
    )
    if entityfin_id:
        qs = qs.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))
    rows = qs.values("vendor_id").annotate(total=Sum("total_amount"), last_payment_date=Max("settlement_date"))
    total_map = {row["vendor_id"]: q2(row["total"] or ZERO) for row in rows}
    last_map = {row["vendor_id"]: row["last_payment_date"] for row in rows}
    return total_map, last_map


def all_last_payment_dates(*, entity_id, entityfin_id, subentity_id, upto_date):
    qs = VendorSettlement.objects.filter(
        entity_id=entity_id,
        status=VendorSettlement.Status.POSTED,
        settlement_type=VendorSettlement.SettlementType.PAYMENT,
        settlement_date__lte=upto_date,
    )
    if entityfin_id:
        qs = qs.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))
    rows = qs.values("vendor_id").annotate(last_payment_date=Max("settlement_date"))
    return {row["vendor_id"]: row["last_payment_date"] for row in rows}


def period_bill_credit_totals(*, entity_id, entityfin_id, subentity_id, from_date, to_date):
    qs = scope_filter(
        VendorBillOpenItem.objects.select_related("header"),
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
    ).filter(bill_date__gte=from_date, bill_date__lte=to_date)
    bill_map = defaultdict(lambda: ZERO)
    credit_map = defaultdict(lambda: ZERO)
    last_bill_date = {}
    for item in qs:
        if q2(item.original_amount) >= ZERO:
            bill_map[item.vendor_id] = q2(bill_map[item.vendor_id] + q2(item.original_amount))
            prev = last_bill_date.get(item.vendor_id)
            if prev is None or item.bill_date > prev:
                last_bill_date[item.vendor_id] = item.bill_date
        else:
            credit_map[item.vendor_id] = q2(credit_map[item.vendor_id] + abs(q2(item.original_amount)))
    return bill_map, credit_map, last_bill_date
