from __future__ import annotations

"""Query helpers for payable reporting.

These selectors keep the read model close to the database so the report
services can stay focused on accounting semantics and payload shaping.
Open-item and advance balances are annotated as-of a reporting date to avoid
N+1 settlement lookups and to keep vendor-level aggregation database-side.
"""

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import (
    Case,
    DateField,
    DecimalField,
    ExpressionWrapper,
    F,
    Max,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
    Count,
)
from django.db.models.functions import Abs, Coalesce

from financial.models import account
from posting.models import EntryStatus, JournalLine
from purchase.models.purchase_ap import (
    VendorAdvanceBalance,
    VendorBillOpenItem,
    VendorSettlement,
    VendorSettlementLine,
)
from purchase.models.purchase_core import PurchaseInvoiceHeader
from reports.selectors.financial import normalize_scope_ids, resolve_date_window

ZERO = Decimal("0.00")
Q2P = Decimal("0.01")
AMOUNT_FIELD = DecimalField(max_digits=14, decimal_places=2)


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
    """Return vendor masters eligible for AP reports within the entity scope."""
    qs = account.objects.filter(entity_id=entity_id)
    qs = qs.filter(
        Q(commercial_profile__partytype__in=["Vendor", "Both"])
        | Q(commercial_profile__partytype__isnull=True)
        | Q(commercial_profile__partytype="")
    )
    if vendor_id:
        qs = qs.filter(id=vendor_id)
    if vendor_group:
        qs = qs.filter(commercial_profile__agent__iexact=vendor_group)
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
    return qs.select_related("ledger", "state", "commercial_profile", "compliance_profile").only(
        "id",
        "entity_id",
        "ledger_id",
        "ledger__id",
        "ledger__ledger_code",
        "ledger__name",
        "ledger__accounthead_id",
        "accountname",
        "legalname",
        "accountcode",
        "commercial_profile__partytype",
        "commercial_profile__currency",
        "commercial_profile__agent",
        "commercial_profile__creditdays",
        "commercial_profile__creditlimit",
        "compliance_profile__gstno",
        "state_id",
        "state__statename",
        "state__statecode",
    ).order_by("accountname", "id")


def scope_filter(qs, *, entity_id, entityfin_id, subentity_id):
    qs = qs.filter(entity_id=entity_id)
    if entityfin_id:
        qs = qs.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))
    return qs


def settlement_line_sums(*, entity_id, entityfin_id, subentity_id, upto_date):
    """Return applied settlement totals per open item as of the reporting date."""
    qs = VendorSettlementLine.objects.filter(
        settlement__status=VendorSettlement.Status.POSTED,
        settlement__settlement_date__lte=upto_date,
        settlement__entity_id=entity_id,
    )
    if entityfin_id:
        qs = qs.filter(settlement__entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(Q(settlement__subentity_id=subentity_id) | Q(settlement__subentity__isnull=True))
    rows = qs.values("open_item_id").annotate(applied=Coalesce(Sum("applied_amount_signed"), Value(ZERO, output_field=AMOUNT_FIELD)))
    return {row["open_item_id"]: q2(row["applied"] or ZERO) for row in rows}


def advance_adjusted_sums(*, entity_id, entityfin_id, subentity_id, upto_date):
    """Return advance adjustments posted up to the reporting date."""
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
    rows = qs.values("advance_balance_id").annotate(applied=Coalesce(Sum("total_amount"), Value(ZERO, output_field=AMOUNT_FIELD)))
    return {row["advance_balance_id"]: q2(row["applied"] or ZERO) for row in rows}


def _open_item_balance_queryset(*, entity_id, entityfin_id, subentity_id, upto_date, vendor_ids=None):
    settled_sq = VendorSettlementLine.objects.filter(
        open_item_id=OuterRef("pk"),
        settlement__status=VendorSettlement.Status.POSTED,
        settlement__settlement_date__lte=upto_date,
        settlement__entity_id=entity_id,
    )
    if entityfin_id:
        settled_sq = settled_sq.filter(settlement__entityfinid_id=entityfin_id)
    if subentity_id is not None:
        settled_sq = settled_sq.filter(Q(settlement__subentity_id=subentity_id) | Q(settlement__subentity__isnull=True))
    settled_sq = settled_sq.values("open_item_id").annotate(
        total=Coalesce(Sum("applied_amount_signed"), Value(ZERO, output_field=AMOUNT_FIELD))
    ).values("total")[:1]

    qs = scope_filter(
        VendorBillOpenItem.objects.select_related("vendor", "vendor__ledger", "vendor__commercial_profile", "vendor__compliance_profile", "subentity", "header"),
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
    ).filter(bill_date__lte=upto_date)
    if vendor_ids:
        qs = qs.filter(vendor_id__in=list(vendor_ids))
    return qs.only(
        "id",
        "header_id",
        "vendor_id",
        "vendor__id",
        "vendor__ledger_id",
        "vendor__accountname",
        "vendor__legalname",
        "vendor__accountcode",
        "vendor__commercial_profile__creditlimit",
        "vendor__commercial_profile__creditdays",
        "vendor__commercial_profile__currency",
        "vendor__compliance_profile__gstno",
        "vendor__commercial_profile__agent",
        "vendor__state_id",
        "vendor__state__statename",
        "vendor__state__statecode",
        "subentity_id",
        "subentity__subentityname",
        "header__id",
        "header__doc_type",
        "header__currency_code",
        "doc_type",
        "bill_date",
        "due_date",
        "purchase_number",
        "supplier_invoice_number",
        "original_amount",
    ).annotate(
        settled_asof=Coalesce(Subquery(settled_sq, output_field=AMOUNT_FIELD), Value(ZERO, output_field=AMOUNT_FIELD)),
        outstanding_asof=ExpressionWrapper(F("original_amount") - F("settled_asof"), output_field=AMOUNT_FIELD),
    )


def _advance_balance_queryset(*, entity_id, entityfin_id, subentity_id, upto_date, vendor_ids=None):
    adjusted_sq = VendorSettlement.objects.filter(
        advance_balance_id=OuterRef("pk"),
        status=VendorSettlement.Status.POSTED,
        settlement_date__lte=upto_date,
        entity_id=entity_id,
    )
    if entityfin_id:
        adjusted_sq = adjusted_sq.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        adjusted_sq = adjusted_sq.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))
    adjusted_sq = adjusted_sq.values("advance_balance_id").annotate(
        total=Coalesce(Sum("total_amount"), Value(ZERO, output_field=AMOUNT_FIELD))
    ).values("total")[:1]

    qs = scope_filter(
        VendorAdvanceBalance.objects.select_related("vendor", "vendor__ledger", "subentity", "payment_voucher"),
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
    ).filter(credit_date__lte=upto_date)
    if vendor_ids:
        qs = qs.filter(vendor_id__in=list(vendor_ids))
    return qs.only(
        "id",
        "vendor_id",
        "vendor__id",
        "vendor__ledger_id",
        "subentity_id",
        "subentity__subentityname",
        "payment_voucher_id",
        "credit_date",
        "reference_no",
        "original_amount",
    ).annotate(
        adjusted_asof=Coalesce(Subquery(adjusted_sq, output_field=AMOUNT_FIELD), Value(ZERO, output_field=AMOUNT_FIELD)),
        outstanding_asof=ExpressionWrapper(F("original_amount") - F("adjusted_asof"), output_field=AMOUNT_FIELD),
    )


def asof_open_item_balances(*, entity_id, entityfin_id, subentity_id, upto_date, vendor_ids=None):
    """Return open items with balances annotated up to the supplied reporting date."""
    qs = _open_item_balance_queryset(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=upto_date,
        vendor_ids=vendor_ids,
    )
    rows = []
    for item in qs.iterator(chunk_size=2000):
        rows.append((item, q2(item.settled_asof), q2(item.outstanding_asof)))
    return rows


def open_item_vendor_summary(*, entity_id, entityfin_id, subentity_id, upto_date, vendor_ids=None):
    """Aggregate vendor open-item balances database-side for outstanding reporting."""
    qs = _open_item_balance_queryset(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=upto_date,
        vendor_ids=vendor_ids,
    )
    rows = qs.values("vendor_id").annotate(
        outstanding_total=Coalesce(Sum("outstanding_asof"), Value(ZERO, output_field=AMOUNT_FIELD)),
        credit_total=Coalesce(
            Sum(
                Case(
                    When(outstanding_asof__lt=ZERO, then=Abs(F("outstanding_asof"))),
                    default=Value(ZERO, output_field=AMOUNT_FIELD),
                    output_field=AMOUNT_FIELD,
                )
            ),
            Value(ZERO, output_field=AMOUNT_FIELD),
        ),
        overdue_total=Coalesce(
            Sum(
                Case(
                    When(Q(outstanding_asof__gt=ZERO) & Q(due_date__lt=upto_date), then=F("outstanding_asof")),
                    default=Value(ZERO, output_field=AMOUNT_FIELD),
                    output_field=AMOUNT_FIELD,
                )
            ),
            Value(ZERO, output_field=AMOUNT_FIELD),
        ),
    )
    return {
        row["vendor_id"]: {
            "outstanding_total": q2(row["outstanding_total"]),
            "credit_total": q2(row["credit_total"]),
            "overdue_total": q2(row["overdue_total"]),
        }
        for row in rows
    }


def asof_advances(*, entity_id, entityfin_id, subentity_id, upto_date, vendor_ids=None):
    """Return vendor advances with adjusted and outstanding values as of the date."""
    qs = _advance_balance_queryset(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=upto_date,
        vendor_ids=vendor_ids,
    )
    rows = []
    for adv in qs.iterator(chunk_size=2000):
        rows.append((adv, q2(adv.adjusted_asof), q2(adv.outstanding_asof)))
    return rows


def advance_vendor_summary(*, entity_id, entityfin_id, subentity_id, upto_date, vendor_ids=None):
    """Aggregate unapplied vendor advances database-side for outstanding reporting."""
    qs = _advance_balance_queryset(
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        upto_date=upto_date,
        vendor_ids=vendor_ids,
    )
    rows = qs.values("vendor_id").annotate(
        outstanding_total=Coalesce(
            Sum(
                Case(
                    When(outstanding_asof__gt=ZERO, then=F("outstanding_asof")),
                    default=Value(ZERO, output_field=AMOUNT_FIELD),
                    output_field=AMOUNT_FIELD,
                )
            ),
            Value(ZERO, output_field=AMOUNT_FIELD),
        )
    )
    return {row["vendor_id"]: q2(row["outstanding_total"]) for row in rows}


def posted_payment_totals(*, entity_id, entityfin_id, subentity_id, from_date, to_date):
    """Posted payment totals during the reporting period."""
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
    rows = qs.values("vendor_id").annotate(
        total=Coalesce(Sum("total_amount"), Value(ZERO, output_field=AMOUNT_FIELD)),
        last_payment_date=Max("settlement_date"),
    )
    total_map = {row["vendor_id"]: q2(row["total"] or ZERO) for row in rows}
    last_map = {row["vendor_id"]: row["last_payment_date"] for row in rows}
    return total_map, last_map


def all_last_payment_dates(*, entity_id, entityfin_id, subentity_id, upto_date):
    """Last posted payment date per vendor up to the report date."""
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


def period_bill_credit_totals(*, entity_id, entityfin_id, subentity_id, from_date, to_date, vendor_ids=None):
    """Aggregate bill and credit-note movement for the requested period."""
    qs = scope_filter(
        VendorBillOpenItem.objects.all(),
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
    ).filter(bill_date__gte=from_date, bill_date__lte=to_date)
    if vendor_ids:
        qs = qs.filter(vendor_id__in=list(vendor_ids))
    rows = qs.values("vendor_id").annotate(
        bill_total=Coalesce(
            Sum(
                Case(
                    When(original_amount__gte=ZERO, then=F("original_amount")),
                    default=Value(ZERO, output_field=AMOUNT_FIELD),
                    output_field=AMOUNT_FIELD,
                )
            ),
            Value(ZERO, output_field=AMOUNT_FIELD),
        ),
        credit_total=Coalesce(
            Sum(
                Case(
                    When(original_amount__lt=ZERO, then=Abs(F("original_amount"))),
                    default=Value(ZERO, output_field=AMOUNT_FIELD),
                    output_field=AMOUNT_FIELD,
                )
            ),
            Value(ZERO, output_field=AMOUNT_FIELD),
        ),
        last_bill_date=Max(
            Case(
                When(original_amount__gte=ZERO, then=F("bill_date")),
                default=None,
                output_field=DateField(),
            )
        ),
    )
    bill_map = defaultdict(lambda: ZERO)
    credit_map = defaultdict(lambda: ZERO)
    last_bill_date = {}
    for row in rows:
        bill_map[row["vendor_id"]] = q2(row["bill_total"])
        credit_map[row["vendor_id"]] = q2(row["credit_total"])
        last_bill_date[row["vendor_id"]] = row["last_bill_date"]
    return bill_map, credit_map, last_bill_date


def vendor_control_balance_map(*, entity_id, entityfin_id, subentity_id, upto_date, vendor_ledger_map):
    """Return vendor ledger balances from posted journal lines as of the report date.

    Payables are liability balances, so the control balance is measured as
    credit minus debit on the vendor's control ledger.
    """
    ledger_to_vendor = {ledger_id: vendor_id for vendor_id, ledger_id in vendor_ledger_map.items() if ledger_id}
    if not ledger_to_vendor:
        return {}
    qs = JournalLine.objects.filter(
        entity_id=entity_id,
        posting_date__lte=upto_date,
        entry__status=EntryStatus.POSTED,
    )
    if entityfin_id:
        qs = qs.filter(entityfin_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))
    qs = qs.annotate(resolved_ledger_id=Coalesce(F("ledger_id"), F("account__ledger_id"))).filter(
        resolved_ledger_id__in=list(ledger_to_vendor.keys())
    )
    rows = qs.values("resolved_ledger_id").annotate(
        debit=Coalesce(Sum("amount", filter=Q(drcr=True)), Value(ZERO, output_field=AMOUNT_FIELD)),
        credit=Coalesce(Sum("amount", filter=Q(drcr=False)), Value(ZERO, output_field=AMOUNT_FIELD)),
    )
    balances = {}
    for row in rows:
        vendor_id = ledger_to_vendor.get(row["resolved_ledger_id"])
        if vendor_id is None:
            continue
        balances[vendor_id] = q2((row["credit"] or ZERO) - (row["debit"] or ZERO))
    return balances


def settlement_integrity_issues(*, entity_id, entityfin_id=None, subentity_id=None, upto_date=None):
    """Return reusable settlement integrity diagnostics for AP controls and close checks."""
    settlement_qs = VendorSettlement.objects.filter(entity_id=entity_id)
    if entityfin_id:
        settlement_qs = settlement_qs.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        settlement_qs = settlement_qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))
    if upto_date is not None:
        settlement_qs = settlement_qs.filter(settlement_date__lte=upto_date)

    settlement_rows = settlement_qs.annotate(
        line_count=Count("lines"),
        line_amount_total=Coalesce(Sum("lines__amount"), Value(ZERO, output_field=AMOUNT_FIELD)),
        line_signed_total=Coalesce(Sum("lines__applied_amount_signed"), Value(ZERO, output_field=AMOUNT_FIELD)),
    ).values(
        "id",
        "vendor_id",
        "reference_no",
        "settlement_type",
        "settlement_date",
        "total_amount",
        "line_count",
        "line_amount_total",
        "line_signed_total",
    )

    issues = []
    for row in settlement_rows:
        if row["line_count"] == 0 and q2(row["total_amount"]) != ZERO:
            issues.append({
                "check_code": "settlement_without_lines",
                "severity": "error",
                "settlement_id": row["id"],
                "vendor_id": row["vendor_id"],
                "reference_no": row["reference_no"],
                "message": "Settlement has a non-zero total but no settlement lines.",
                "amount": f"{q2(row['total_amount']):.2f}",
            })
        if q2(row["line_amount_total"]) != q2(row["total_amount"]):
            issues.append({
                "check_code": "settlement_total_mismatch",
                "severity": "error",
                "settlement_id": row["id"],
                "vendor_id": row["vendor_id"],
                "reference_no": row["reference_no"],
                "message": "Settlement total does not match the sum of line amounts.",
                "amount": f"{q2(row['total_amount']) - q2(row['line_amount_total']):.2f}",
            })

    line_qs = VendorSettlementLine.objects.select_related(
        "settlement",
        "open_item",
        "open_item__header",
        "open_item__vendor",
    ).filter(settlement__entity_id=entity_id)
    if entityfin_id:
        line_qs = line_qs.filter(settlement__entityfinid_id=entityfin_id)
    if subentity_id is not None:
        line_qs = line_qs.filter(Q(settlement__subentity_id=subentity_id) | Q(settlement__subentity__isnull=True))
    if upto_date is not None:
        line_qs = line_qs.filter(settlement__settlement_date__lte=upto_date)

    open_item_applied = defaultdict(lambda: ZERO)
    for line in line_qs.iterator(chunk_size=2000):
        original_amount = q2(getattr(line.open_item, "original_amount", ZERO))
        applied_signed = q2(line.applied_amount_signed)
        line_amount = q2(line.amount)
        open_item_applied[line.open_item_id] = q2(open_item_applied[line.open_item_id] + abs(applied_signed))

        if line_amount > abs(original_amount):
            issues.append({
                "check_code": "settlement_line_exceeds_open_item",
                "severity": "error",
                "settlement_id": line.settlement_id,
                "open_item_id": line.open_item_id,
                "vendor_id": line.open_item.vendor_id,
                "reference_no": line.settlement.reference_no,
                "document_number": line.open_item.purchase_number or line.open_item.supplier_invoice_number,
                "message": "Settlement line amount exceeds the original open-item amount.",
                "amount": f"{line_amount:.2f}",
            })
        if line.settlement.vendor_id != line.open_item.vendor_id:
            issues.append({
                "check_code": "settlement_vendor_mismatch",
                "severity": "error",
                "settlement_id": line.settlement_id,
                "open_item_id": line.open_item_id,
                "vendor_id": line.settlement.vendor_id,
                "reference_no": line.settlement.reference_no,
                "document_number": line.open_item.purchase_number or line.open_item.supplier_invoice_number,
                "message": "Settlement vendor does not match the open-item vendor.",
                "amount": f"{applied_signed:.2f}",
            })
        if original_amount > ZERO and applied_signed < ZERO:
            issues.append({
                "check_code": "invalid_settlement_sign",
                "severity": "error",
                "settlement_id": line.settlement_id,
                "open_item_id": line.open_item_id,
                "vendor_id": line.open_item.vendor_id,
                "reference_no": line.settlement.reference_no,
                "document_number": line.open_item.purchase_number or line.open_item.supplier_invoice_number,
                "message": "Positive payable bill has a negative signed settlement line.",
                "amount": f"{applied_signed:.2f}",
            })
        if original_amount < ZERO and applied_signed > ZERO:
            issues.append({
                "check_code": "invalid_credit_note_sign",
                "severity": "error",
                "settlement_id": line.settlement_id,
                "open_item_id": line.open_item_id,
                "vendor_id": line.open_item.vendor_id,
                "reference_no": line.settlement.reference_no,
                "document_number": line.open_item.purchase_number or line.open_item.supplier_invoice_number,
                "message": "Credit-note style open item has a positive signed settlement line.",
                "amount": f"{applied_signed:.2f}",
            })
        if line.settlement.settlement_date and line.open_item.bill_date and line.settlement.settlement_date < line.open_item.bill_date:
            issues.append({
                "check_code": "settlement_before_bill_date",
                "severity": "warning",
                "settlement_id": line.settlement_id,
                "open_item_id": line.open_item_id,
                "vendor_id": line.open_item.vendor_id,
                "reference_no": line.settlement.reference_no,
                "document_number": line.open_item.purchase_number or line.open_item.supplier_invoice_number,
                "message": "Settlement date is earlier than the bill date.",
                "amount": f"{applied_signed:.2f}",
            })

    open_item_map = {
        row.id: row
        for row in VendorBillOpenItem.objects.filter(pk__in=open_item_applied.keys()).only(
            "id", "vendor_id", "original_amount", "purchase_number", "supplier_invoice_number"
        )
    }
    for open_item_id, applied_total in open_item_applied.items():
        open_item = open_item_map.get(open_item_id)
        if not open_item:
            continue
        if applied_total > abs(q2(open_item.original_amount)):
            issues.append({
                "check_code": "open_item_over_applied",
                "severity": "error",
                "open_item_id": open_item.id,
                "vendor_id": open_item.vendor_id,
                "document_number": open_item.purchase_number or open_item.supplier_invoice_number,
                "message": "Cumulative settlement applications exceed the open-item amount.",
                "amount": f"{applied_total:.2f}",
            })

    return issues


def future_settlement_applications(*, entity_id, entityfin_id=None, subentity_id=None, close_date=None):
    """Return posted settlements after the close date that touch pre-close invoices."""
    if close_date is None:
        return []
    qs = VendorSettlementLine.objects.select_related("settlement", "open_item").filter(
        settlement__entity_id=entity_id,
        settlement__status=VendorSettlement.Status.POSTED,
        settlement__settlement_date__gt=close_date,
        open_item__bill_date__lte=close_date,
    )
    if entityfin_id:
        qs = qs.filter(settlement__entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(Q(settlement__subentity_id=subentity_id) | Q(settlement__subentity__isnull=True))
    rows = []
    for line in qs.iterator(chunk_size=1000):
        rows.append({
            "settlement_id": line.settlement_id,
            "open_item_id": line.open_item_id,
            "vendor_id": line.open_item.vendor_id,
            "reference_no": line.settlement.reference_no,
            "settlement_date": line.settlement.settlement_date,
            "bill_date": line.open_item.bill_date,
            "document_number": line.open_item.purchase_number or line.open_item.supplier_invoice_number,
            "amount": f"{q2(line.applied_amount_signed):.2f}",
        })
    return rows


def settlement_history_queryset(*, entity_id, entityfin_id=None, subentity_id=None, vendor_id=None, from_date=None, to_date=None, settlement_type=None):
    """Return settlements with related lines/open items prefetched for history reporting."""
    qs = VendorSettlement.objects.select_related(
        "vendor",
        "vendor__state",
        "vendor_ledger",
        "advance_balance",
        "subentity",
        "posted_by",
    ).prefetch_related(
        "lines__open_item",
        "lines__open_item__header",
    ).filter(entity_id=entity_id)
    if entityfin_id:
        qs = qs.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))
    if vendor_id:
        qs = qs.filter(vendor_id=vendor_id)
    if from_date:
        qs = qs.filter(settlement_date__gte=from_date)
    if to_date:
        qs = qs.filter(settlement_date__lte=to_date)
    if settlement_type:
        qs = qs.filter(settlement_type=settlement_type)
    return qs.order_by("settlement_date", "id")


def note_register_queryset(*, entity_id, entityfin_id=None, subentity_id=None, vendor_id=None, from_date=None, to_date=None, note_type=None, status=None):
    """Return vendor debit/credit notes with linked references and open-item residuals."""
    qs = PurchaseInvoiceHeader.objects.select_related(
        "vendor",
        "vendor__state",
        "vendor_ledger",
        "ref_document",
        "ap_open_item",
        "subentity",
        "posted_by",
        "created_by",
    ).filter(
        entity_id=entity_id,
        doc_type__in=[PurchaseInvoiceHeader.DocType.CREDIT_NOTE, PurchaseInvoiceHeader.DocType.DEBIT_NOTE],
    )
    if entityfin_id:
        qs = qs.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))
    if vendor_id:
        qs = qs.filter(vendor_id=vendor_id)
    if from_date:
        qs = qs.filter(bill_date__gte=from_date)
    if to_date:
        qs = qs.filter(bill_date__lte=to_date)
    if note_type == "credit":
        qs = qs.filter(doc_type=PurchaseInvoiceHeader.DocType.CREDIT_NOTE)
    elif note_type == "debit":
        qs = qs.filter(doc_type=PurchaseInvoiceHeader.DocType.DEBIT_NOTE)
    if status is not None:
        qs = qs.filter(status=status)
    return qs.order_by("bill_date", "doc_code", "doc_no", "id")
