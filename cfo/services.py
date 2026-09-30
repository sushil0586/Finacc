from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Max, Min, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from bank_reco.models import BankReconciliationRun, BankStatementImport
from cfo.models import BudgetLine, BudgetVarianceReview, CashFlowForecastAdjustment, CfoEvidenceItem, CfoInsightSignal, CfoManagementPackSnapshot, CfoRiskReview, CfoScenarioPlan, MonthClosePeriod, MonthCloseTask
from entity.models import Entity, EntityFinancialYear, SubEntity
from purchase.models.purchase_ap import VendorBillOpenItem
from purchase.models.purchase_core import PurchaseInvoiceHeader
from rbac.services import EffectivePermissionService
from sales.models.sales_ar import CustomerBillOpenItem
from sales.models.sales_core import SalesInvoiceHeader


CFO_CONTROL_TOWER_PERMISSION = "cfo.control_tower.view"
CFO_RECEIVABLES_PERMISSION = "cfo.receivables.view"
CFO_PAYABLES_PERMISSION = "cfo.payables.view"
CFO_CASH_FLOW_PERMISSION = "cfo.cash_flow.view"
CFO_CASH_FLOW_ADJUST_PERMISSION = "cfo.cash_flow.manage_adjustments"
CFO_MONTH_CLOSE_PERMISSION = "cfo.month_close.view"
CFO_MONTH_CLOSE_MANAGE_PERMISSION = "cfo.month_close.manage"
CFO_MONTH_CLOSE_LOCK_PERMISSION = "cfo.month_close.lock_period"
CFO_BUDGET_PERMISSION = "cfo.budget.view"
CFO_BUDGET_MANAGE_PERMISSION = "cfo.budget.manage"
CFO_BUDGET_REVIEW_PERMISSION = "cfo.budget.review_variances"
CFO_RISK_QUEUE_PERMISSION = "cfo.risk_queue.view"
CFO_RISK_QUEUE_REVIEW_PERMISSION = "cfo.risk_queue.review"
CFO_MANAGEMENT_PACK_PERMISSION = "cfo.management_pack.view"
CFO_MANAGEMENT_PACK_PUBLISH_PERMISSION = "cfo.management_pack.publish"
CFO_EVIDENCE_CENTER_PERMISSION = "cfo.evidence_center.view"
CFO_EVIDENCE_CENTER_MANAGE_PERMISSION = "cfo.evidence_center.manage"
CFO_INSIGHTS_PERMISSION = "cfo.insights.view"
CFO_INSIGHTS_REVIEW_PERMISSION = "cfo.insights.review"
CFO_SCENARIO_PLANNER_PERMISSION = "cfo.scenario_planner.view"
CFO_SCENARIO_PLANNER_MANAGE_PERMISSION = "cfo.scenario_planner.manage"
ZERO = Decimal("0.00")


BUDGET_CATEGORY_CATALOG = (
    {
        "category": BudgetLine.Category.REVENUE,
        "label": "Revenue",
        "actual_key": "revenue",
        "direction": "income",
        "route": "/saleinvoice",
    },
    {
        "category": BudgetLine.Category.PURCHASE_EXPENSE,
        "label": "Purchase Expense",
        "actual_key": "purchase_expense",
        "direction": "expense",
        "route": "/purchaseinvoice",
    },
    {
        "category": BudgetLine.Category.GROSS_SNAPSHOT,
        "label": "Gross Snapshot",
        "actual_key": "gross_snapshot",
        "direction": "income",
        "route": "/dashboard-analytics",
    },
    {
        "category": BudgetLine.Category.STATUTORY_PAYABLE,
        "label": "Statutory Payable",
        "actual_key": "statutory_payable_estimate",
        "direction": "expense",
        "route": "/cfo",
    },
)


MONTH_CLOSE_TASK_CATALOG = (
    {
        "task_code": "bank_reconciliation",
        "task_label": "Bank reconciliation reviewed",
        "sort_order": 10,
        "evidence_route": "/bank-reco",
    },
    {
        "task_code": "gst_reconciliation",
        "task_label": "GST reconciliation reviewed",
        "sort_order": 20,
        "evidence_route": "/gst-reconciliation",
    },
    {
        "task_code": "tds_tcs_review",
        "task_label": "TDS/TCS liability reviewed",
        "sort_order": 30,
        "evidence_route": "/reports/tds",
    },
    {
        "task_code": "payroll_posted",
        "task_label": "Payroll posted",
        "sort_order": 40,
        "evidence_route": "/payroll",
    },
    {
        "task_code": "inventory_valuation",
        "task_label": "Inventory valuation reviewed",
        "sort_order": 50,
        "evidence_route": "/reports/inventory/stock-summary",
    },
    {
        "task_code": "depreciation_posted",
        "task_label": "Depreciation posted",
        "sort_order": 60,
        "evidence_route": "/depreciationrun",
    },
    {
        "task_code": "accruals_provisions",
        "task_label": "Accruals and provisions posted",
        "sort_order": 70,
        "evidence_route": "/journalvoucher",
    },
    {
        "task_code": "trial_balance_reviewed",
        "task_label": "Trial balance reviewed",
        "sort_order": 80,
        "evidence_route": "/reports/financial/trial-balance",
    },
    {
        "task_code": "financial_reports_reviewed",
        "task_label": "Financial reports reviewed",
        "sort_order": 90,
        "evidence_route": "/dashboard-analytics",
    },
    {
        "task_code": "period_locked",
        "task_label": "Period locked",
        "sort_order": 100,
        "evidence_route": "/cfo/month-close",
    },
)


def _money(value) -> str:
    return str((value or ZERO).quantize(Decimal("0.01")))


def _decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or "0.00"))


def _percent_factor(value) -> Decimal:
    return Decimal("1.00") + (_decimal(value) / Decimal("100.00"))


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _month_end(value: date) -> date:
    return value.replace(day=monthrange(value.year, value.month)[1])


def _resolve_financial_year(*, entity_id: int, entityfinid: int | None):
    if entityfinid:
        return EntityFinancialYear.objects.filter(entity_id=entity_id, id=entityfinid, isactive=True).first()
    return (
        EntityFinancialYear.objects.filter(entity_id=entity_id, isactive=True, is_year_closed=False)
        .order_by("-finendyear", "-finstartyear", "-id")
        .first()
        or EntityFinancialYear.objects.filter(entity_id=entity_id, isactive=True)
        .order_by("-finendyear", "-finstartyear", "-id")
        .first()
    )


def _resolve_subentity(*, entity_id: int, subentity_id: int | None):
    if not subentity_id:
        return None
    return SubEntity.objects.filter(entity_id=entity_id, id=subentity_id, isactive=True).first()


def _scope_filter(scope_context, *, fin_field="entityfinid", subentity_field="subentity"):
    filters = {"entity_id": scope_context["entity"].id}
    financial_year = scope_context.get("financial_year")
    subentity = scope_context.get("subentity")
    if financial_year is not None and fin_field:
        filters[f"{fin_field}_id"] = financial_year.id
    if subentity is not None and subentity_field:
        filters[f"{subentity_field}_id"] = subentity.id
    return filters


def _aggregate_open_items(model, amount_field: str, due_field: str, scope_context):
    as_of_date = scope_context["as_of_date"]
    qs = model.objects.filter(
        **_scope_filter(scope_context),
        is_open=True,
        outstanding_amount__gt=ZERO,
    )
    totals = qs.aggregate(
        total=Coalesce(Sum(amount_field), Value(ZERO)),
        overdue=Coalesce(Sum(amount_field, filter=Q(**{f"{due_field}__lt": as_of_date})), Value(ZERO)),
        due_7_days=Coalesce(
            Sum(amount_field, filter=Q(**{f"{due_field}__gte": as_of_date, f"{due_field}__lte": as_of_date + timedelta(days=7)})),
            Value(ZERO),
        ),
        open_count=Count("id"),
        overdue_count=Count("id", filter=Q(**{f"{due_field}__lt": as_of_date})),
    )
    return {
        "total_outstanding": _money(totals["total"]),
        "overdue_amount": _money(totals["overdue"]),
        "due_next_7_days": _money(totals["due_7_days"]),
        "open_count": totals["open_count"] or 0,
        "overdue_count": totals["overdue_count"] or 0,
    }


def _build_cash_summary(scope_context):
    filters = {
        "entity_id": scope_context["entity"].id,
        "status__in": [
            BankStatementImport.Status.VALIDATED,
            BankStatementImport.Status.READY,
        ],
    }
    financial_year = scope_context.get("financial_year")
    subentity = scope_context.get("subentity")
    if financial_year is not None:
        filters["entityfin_id"] = financial_year.id
    if subentity is not None:
        filters["subentity_id"] = subentity.id

    rows = (
        BankStatementImport.objects.filter(**filters)
        .values("bank_account_id", "bank_account__bank_name")
        .annotate(latest_to=Max("statement_to"))
        .order_by("bank_account__bank_name")
    )
    total = ZERO
    accounts = []
    for row in rows:
        latest = (
            BankStatementImport.objects.filter(
                **filters,
                bank_account_id=row["bank_account_id"],
                statement_to=row["latest_to"],
            )
            .order_by("-id")
            .first()
        )
        if latest is None:
            continue
        total += latest.closing_balance or ZERO
        accounts.append(
            {
                "bank_account_id": latest.bank_account_id,
                "bank_name": row["bank_account__bank_name"] or "Bank account",
                "closing_balance": _money(latest.closing_balance),
                "statement_to": latest.statement_to.isoformat() if latest.statement_to else None,
            }
        )

    return {
        "source": "bank_statement_imports",
        "total_cash_bank_balance": _money(total),
        "account_count": len(accounts),
        "accounts": accounts[:5],
    }


def _cash_balance_decimal(scope_context):
    return _decimal(_build_cash_summary(scope_context)["total_cash_bank_balance"])


def _build_compliance_summary(scope_context):
    purchase_filters = _scope_filter(scope_context)
    sales_filters = _scope_filter(scope_context)
    purchase = PurchaseInvoiceHeader.objects.filter(**purchase_filters).exclude(
        status=PurchaseInvoiceHeader.Status.CANCELLED
    )
    sales = SalesInvoiceHeader.objects.filter(**sales_filters).exclude(
        status=SalesInvoiceHeader.Status.CANCELLED
    )
    purchase_totals = purchase.aggregate(
        tds=Coalesce(Sum("tds_amount"), Value(ZERO)),
        gst_tds=Coalesce(Sum("gst_tds_amount"), Value(ZERO)),
    )
    sales_totals = sales.aggregate(tcs=Coalesce(Sum("tcs_amount"), Value(ZERO)))
    statutory = (purchase_totals["tds"] or ZERO) + (purchase_totals["gst_tds"] or ZERO) + (sales_totals["tcs"] or ZERO)
    return {
        "source": "purchase_and_sales_statutory_amounts",
        "statutory_payable_estimate": _money(statutory),
        "tds_amount": _money(purchase_totals["tds"]),
        "gst_tds_amount": _money(purchase_totals["gst_tds"]),
        "tcs_amount": _money(sales_totals["tcs"]),
    }


def _build_period_performance(scope_context):
    from_date = scope_context["from_date"]
    to_date = scope_context["to_date"]
    sales_filters = {
        **_scope_filter(scope_context),
        "bill_date__range": (from_date, to_date),
    }
    purchase_filters = {
        **_scope_filter(scope_context),
        "bill_date__range": (from_date, to_date),
    }
    sales_total = (
        SalesInvoiceHeader.objects.filter(**sales_filters)
        .exclude(status=SalesInvoiceHeader.Status.CANCELLED)
        .aggregate(total=Coalesce(Sum("grand_total"), Value(ZERO)))["total"]
        or ZERO
    )
    purchase_total = (
        PurchaseInvoiceHeader.objects.filter(**purchase_filters)
        .exclude(status=PurchaseInvoiceHeader.Status.CANCELLED)
        .aggregate(total=Coalesce(Sum("grand_total"), Value(ZERO)))["total"]
        or ZERO
    )
    return {
        "period_from": from_date.isoformat(),
        "period_to": to_date.isoformat(),
        "revenue": _money(sales_total),
        "purchase_expense": _money(purchase_total),
        "gross_snapshot": _money(sales_total - purchase_total),
    }


def _build_bank_reconciliation_summary(scope_context):
    filters = {"entity_id": scope_context["entity"].id}
    financial_year = scope_context.get("financial_year")
    subentity = scope_context.get("subentity")
    if financial_year is not None:
        filters["entityfin_id"] = financial_year.id
    if subentity is not None:
        filters["subentity_id"] = subentity.id
    qs = BankReconciliationRun.objects.filter(**filters)
    totals = qs.aggregate(
        pending_runs=Count("id", filter=~Q(status__in=[BankReconciliationRun.Status.RECONCILED, BankReconciliationRun.Status.LOCKED])),
        exception_lines=Coalesce(Sum("exception_line_count"), Value(0)),
        unmatched_bank_amount=Coalesce(Sum("unmatched_bank_amount"), Value(ZERO)),
        unmatched_book_amount=Coalesce(Sum("unmatched_book_amount"), Value(ZERO)),
    )
    return {
        "pending_runs": totals["pending_runs"] or 0,
        "exception_line_count": totals["exception_lines"] or 0,
        "unmatched_bank_amount": _money(totals["unmatched_bank_amount"]),
        "unmatched_book_amount": _money(totals["unmatched_book_amount"]),
    }


def _resolve_scope_context(*, request, scope: dict):
    entity = EffectivePermissionService.entity_for_user(request.user, scope["entity"])
    if entity is None:
        return None

    as_of_date = scope.get("as_of_date") or timezone.localdate()
    financial_year = _resolve_financial_year(entity_id=entity.id, entityfinid=scope.get("entityfinid"))
    subentity = _resolve_subentity(entity_id=entity.id, subentity_id=scope.get("subentity"))
    return {
        "entity": entity,
        "financial_year": financial_year,
        "subentity": subentity,
        "as_of_date": as_of_date,
        "from_date": scope.get("from_date") or _month_start(as_of_date),
        "to_date": scope.get("to_date") or min(_month_end(as_of_date), as_of_date),
    }


def _scope_payload(scope_context):
    entity = scope_context["entity"]
    financial_year = scope_context.get("financial_year")
    subentity = scope_context.get("subentity")
    return {
        "entity": {"id": entity.id, "name": entity.entityname},
        "financial_year": (
            {
                "id": financial_year.id,
                "label": financial_year.desc,
                "start_date": financial_year.finstartyear.date().isoformat() if financial_year.finstartyear else None,
                "end_date": financial_year.finendyear.date().isoformat() if financial_year.finendyear else None,
            }
            if financial_year
            else None
        ),
        "subentity": (
            {"id": subentity.id, "name": subentity.subentityname}
            if subentity
            else None
        ),
        "as_of_date": scope_context["as_of_date"].isoformat(),
        "from_date": scope_context["from_date"].isoformat(),
        "to_date": scope_context["to_date"].isoformat(),
    }


def _days_overdue(due_date, as_of_date):
    if not due_date or due_date >= as_of_date:
        return 0
    return (as_of_date - due_date).days


def _aging_bucket(due_date, as_of_date):
    days = _days_overdue(due_date, as_of_date)
    if days <= 0:
        return "current"
    if days <= 30:
        return "0_30"
    if days <= 60:
        return "31_60"
    if days <= 90:
        return "61_90"
    return "90_plus"


def _empty_bucket_totals():
    return {
        "current": {"amount": ZERO, "count": 0},
        "0_30": {"amount": ZERO, "count": 0},
        "31_60": {"amount": ZERO, "count": 0},
        "61_90": {"amount": ZERO, "count": 0},
        "90_plus": {"amount": ZERO, "count": 0},
    }


def _serialise_bucket_totals(bucket_totals):
    return {
        key: {
            "amount": _money(value["amount"]),
            "count": value["count"],
        }
        for key, value in bucket_totals.items()
    }


def _bucket_filter(bucket: str, as_of_date: date, *, due_field="due_date"):
    if bucket == "current":
        return Q(**{f"{due_field}__isnull": True}) | Q(**{f"{due_field}__gte": as_of_date})
    if bucket == "0_30":
        return Q(**{f"{due_field}__gte": as_of_date - timedelta(days=30), f"{due_field}__lt": as_of_date})
    if bucket == "31_60":
        return Q(**{f"{due_field}__gte": as_of_date - timedelta(days=60), f"{due_field}__lt": as_of_date - timedelta(days=30)})
    if bucket == "61_90":
        return Q(**{f"{due_field}__gte": as_of_date - timedelta(days=90), f"{due_field}__lt": as_of_date - timedelta(days=60)})
    if bucket == "90_plus":
        return Q(**{f"{due_field}__lt": as_of_date - timedelta(days=90)})
    return Q()


def _bucket_annotation_filters(as_of_date: date):
    return {bucket: _bucket_filter(bucket, as_of_date) for bucket in _empty_bucket_totals()}


def _party_label(row, *, party_field, ledger_field):
    party = getattr(row, party_field, None)
    ledger = getattr(row, ledger_field, None)
    return (
        getattr(party, "accountname", None)
        or getattr(party, "legalname", None)
        or getattr(ledger, "name", None)
        or f"Party #{getattr(row, f'{party_field}_id', '') or getattr(row, f'{ledger_field}_id', '') or 'unknown'}"
    )


def _party_label_from_values(row, *, party_field, ledger_field):
    return (
        row.get(f"{party_field}__accountname")
        or row.get(f"{party_field}__legalname")
        or row.get(f"{ledger_field}__name")
        or f"Party #{row.get(f'{party_field}_id') or row.get(f'{ledger_field}_id') or 'unknown'}"
    )


def _open_item_model(kind: str):
    return CustomerBillOpenItem if kind == "receivables" else VendorBillOpenItem


def _open_item_field_names(kind: str):
    if kind == "receivables":
        return {
            "party": "customer",
            "ledger": "customer_ledger",
            "number": "invoice_number",
            "fallback_number": "customer_reference_number",
            "header_status_choices": dict(SalesInvoiceHeader.Status.choices),
        }
    return {
        "party": "vendor",
        "ledger": "vendor_ledger",
        "number": "purchase_number",
        "fallback_number": "supplier_invoice_number",
        "header_status_choices": dict(PurchaseInvoiceHeader.Status.choices),
    }


def _base_open_item_queryset(*, kind: str, scope_context):
    if kind == "receivables":
        return (
            CustomerBillOpenItem.objects.filter(
                **_scope_filter(scope_context),
                is_open=True,
                outstanding_amount__gt=ZERO,
            )
            .select_related("header", "customer", "customer_ledger")
            .order_by("due_date", "-outstanding_amount", "id")
        )
    return (
        VendorBillOpenItem.objects.filter(
            **_scope_filter(scope_context),
            is_open=True,
            outstanding_amount__gt=ZERO,
        )
        .select_related("header", "vendor", "vendor_ledger")
        .order_by("due_date", "-outstanding_amount", "id")
    )


def _forecast_open_item_values(*, kind: str, scope_context, end_date: date):
    model = CustomerBillOpenItem if kind == "receivables" else VendorBillOpenItem
    return (
        model.objects.filter(
            **_scope_filter(scope_context),
            is_open=True,
            outstanding_amount__gt=ZERO,
            due_date__lte=end_date,
        )
        .exclude(due_date__isnull=True)
        .values_list("due_date", "outstanding_amount")
        .iterator(chunk_size=1000)
    )


def _build_aging_control(*, request, scope: dict, kind: str):
    scope_context = _resolve_scope_context(request=request, scope=scope)
    if scope_context is None:
        return None

    permission = CFO_RECEIVABLES_PERMISSION if kind == "receivables" else CFO_PAYABLES_PERMISSION
    permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, scope_context["entity"].id)
    as_of_date = scope_context["as_of_date"]
    model = _open_item_model(kind)
    fields = _open_item_field_names(kind)
    party_field = fields["party"]
    ledger_field = fields["ledger"]

    qs = model.objects.filter(
        **_scope_filter(scope_context),
        is_open=True,
        outstanding_amount__gt=ZERO,
    )
    bucket_filters = _bucket_annotation_filters(as_of_date)
    total_row = qs.aggregate(
        total=Coalesce(Sum("outstanding_amount"), Value(ZERO)),
        open_count=Count("id"),
        current_amount=Coalesce(Sum("outstanding_amount", filter=bucket_filters["current"]), Value(ZERO)),
        current_count=Count("id", filter=bucket_filters["current"]),
        bucket_0_30_amount=Coalesce(Sum("outstanding_amount", filter=bucket_filters["0_30"]), Value(ZERO)),
        bucket_0_30_count=Count("id", filter=bucket_filters["0_30"]),
        bucket_31_60_amount=Coalesce(Sum("outstanding_amount", filter=bucket_filters["31_60"]), Value(ZERO)),
        bucket_31_60_count=Count("id", filter=bucket_filters["31_60"]),
        bucket_61_90_amount=Coalesce(Sum("outstanding_amount", filter=bucket_filters["61_90"]), Value(ZERO)),
        bucket_61_90_count=Count("id", filter=bucket_filters["61_90"]),
        bucket_90_plus_amount=Coalesce(Sum("outstanding_amount", filter=bucket_filters["90_plus"]), Value(ZERO)),
        bucket_90_plus_count=Count("id", filter=bucket_filters["90_plus"]),
    )
    bucket_totals = {
        "current": {"amount": total_row["current_amount"] or ZERO, "count": total_row["current_count"] or 0},
        "0_30": {"amount": total_row["bucket_0_30_amount"] or ZERO, "count": total_row["bucket_0_30_count"] or 0},
        "31_60": {"amount": total_row["bucket_31_60_amount"] or ZERO, "count": total_row["bucket_31_60_count"] or 0},
        "61_90": {"amount": total_row["bucket_61_90_amount"] or ZERO, "count": total_row["bucket_61_90_count"] or 0},
        "90_plus": {"amount": total_row["bucket_90_plus_amount"] or ZERO, "count": total_row["bucket_90_plus_count"] or 0},
    }

    rows = []
    party_values = (
        qs.values(
            f"{party_field}_id",
            f"{party_field}__accountname",
            f"{party_field}__legalname",
            f"{ledger_field}_id",
            f"{ledger_field}__name",
        )
        .annotate(
            total_outstanding=Coalesce(Sum("outstanding_amount"), Value(ZERO)),
            open_count=Count("id"),
            oldest_due_date=Min("due_date"),
            current_amount=Coalesce(Sum("outstanding_amount", filter=bucket_filters["current"]), Value(ZERO)),
            current_count=Count("id", filter=bucket_filters["current"]),
            bucket_0_30_amount=Coalesce(Sum("outstanding_amount", filter=bucket_filters["0_30"]), Value(ZERO)),
            bucket_0_30_count=Count("id", filter=bucket_filters["0_30"]),
            bucket_31_60_amount=Coalesce(Sum("outstanding_amount", filter=bucket_filters["31_60"]), Value(ZERO)),
            bucket_31_60_count=Count("id", filter=bucket_filters["31_60"]),
            bucket_61_90_amount=Coalesce(Sum("outstanding_amount", filter=bucket_filters["61_90"]), Value(ZERO)),
            bucket_61_90_count=Count("id", filter=bucket_filters["61_90"]),
            bucket_90_plus_amount=Coalesce(Sum("outstanding_amount", filter=bucket_filters["90_plus"]), Value(ZERO)),
            bucket_90_plus_count=Count("id", filter=bucket_filters["90_plus"]),
        )
        .order_by("-total_outstanding")[:100]
    )
    for row in party_values:
        row_bucket_totals = {
            "current": {"amount": row["current_amount"] or ZERO, "count": row["current_count"] or 0},
            "0_30": {"amount": row["bucket_0_30_amount"] or ZERO, "count": row["bucket_0_30_count"] or 0},
            "31_60": {"amount": row["bucket_31_60_amount"] or ZERO, "count": row["bucket_31_60_count"] or 0},
            "61_90": {"amount": row["bucket_61_90_amount"] or ZERO, "count": row["bucket_61_90_count"] or 0},
            "90_plus": {"amount": row["bucket_90_plus_amount"] or ZERO, "count": row["bucket_90_plus_count"] or 0},
        }
        rows.append(
            {
                "party_id": row.get(f"{party_field}_id") or 0,
                "party_name": _party_label_from_values(row, party_field=party_field, ledger_field=ledger_field),
                "total_outstanding": _money(row["total_outstanding"]),
                "open_count": row["open_count"],
                "oldest_due_date": row["oldest_due_date"].isoformat() if row["oldest_due_date"] else None,
                "bucket_totals": _serialise_bucket_totals(row_bucket_totals),
            }
        )

    return {
        "control_code": f"cfo_{kind}_aging",
        "kind": kind,
        "page_permission": permission,
        "permissions": {
            "page": {
                "code": permission,
                "granted": permission in permission_codes,
            }
        },
        "scope": _scope_payload(scope_context),
        "summary": {
            "total_outstanding": _money(total_row["total"]),
            "open_count": total_row["open_count"] or 0,
            "bucket_totals": _serialise_bucket_totals(bucket_totals),
        },
        "rows": rows,
    }


def _build_worklist_control(*, request, scope: dict, kind: str):
    scope_context = _resolve_scope_context(request=request, scope=scope)
    if scope_context is None:
        return None

    permission = CFO_RECEIVABLES_PERMISSION if kind == "receivables" else CFO_PAYABLES_PERMISSION
    permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, scope_context["entity"].id)
    as_of_date = scope_context["as_of_date"]
    model = _open_item_model(kind)
    fields = _open_item_field_names(kind)
    party_field = fields["party"]
    ledger_field = fields["ledger"]
    number_field = fields["number"]
    fallback_number_field = fields["fallback_number"]

    bucket_filter = (scope.get("bucket") or "").strip()
    search = (scope.get("search") or "").strip().lower()
    limit = int(scope.get("limit") or 100)
    qs = model.objects.filter(
        **_scope_filter(scope_context),
        is_open=True,
        outstanding_amount__gt=ZERO,
    )
    if bucket_filter:
        if bucket_filter not in _empty_bucket_totals():
            qs = qs.none()
        else:
            qs = qs.filter(_bucket_filter(bucket_filter, as_of_date))
    if search:
        qs = qs.filter(
            Q(**{f"{party_field}__accountname__icontains": search})
            | Q(**{f"{party_field}__legalname__icontains": search})
            | Q(**{f"{ledger_field}__name__icontains": search})
            | Q(**{f"{number_field}__icontains": search})
            | Q(**{f"{fallback_number_field}__icontains": search})
        )
    qs = qs.order_by("due_date", "-outstanding_amount", "id")

    rows = []
    status_choices = fields["header_status_choices"]
    values = qs.values(
        "id",
        "header_id",
        f"{party_field}_id",
        f"{party_field}__accountname",
        f"{party_field}__legalname",
        f"{ledger_field}_id",
        f"{ledger_field}__name",
        number_field,
        fallback_number_field,
        "doc_type",
        "bill_date",
        "due_date",
        "original_amount",
        "settled_amount",
        "outstanding_amount",
        "header__status",
    )[:limit]
    for item in values:
        bucket = _aging_bucket(item["due_date"], as_of_date)
        party_name = _party_label_from_values(item, party_field=party_field, ledger_field=ledger_field)
        document_number = item.get(number_field) or item.get(fallback_number_field) or str(item["header_id"])
        rows.append(
            {
                "id": item["id"],
                "header_id": item["header_id"],
                "party_id": item.get(f"{party_field}_id"),
                "party_name": party_name,
                "document_number": document_number,
                "doc_type": item["doc_type"],
                "bill_date": item["bill_date"].isoformat() if item["bill_date"] else None,
                "due_date": item["due_date"].isoformat() if item["due_date"] else None,
                "days_overdue": _days_overdue(item["due_date"], as_of_date),
                "aging_bucket": bucket,
                "original_amount": _money(item["original_amount"]),
                "settled_amount": _money(item["settled_amount"]),
                "outstanding_amount": _money(item["outstanding_amount"]),
                "status": status_choices.get(item["header__status"], item["header__status"]),
                "source_route": "/saleinvoice" if kind == "receivables" else "/purchaseinvoice",
            }
        )

    return {
        "control_code": f"cfo_{kind}_worklist",
        "kind": kind,
        "page_permission": permission,
        "permissions": {
            "page": {
                "code": permission,
                "granted": permission in permission_codes,
            }
        },
        "scope": _scope_payload(scope_context),
        "filters": {
            "bucket": bucket_filter or None,
            "search": search or None,
            "limit": limit,
        },
        "count": len(rows),
        "rows": rows,
    }


def build_receivables_aging(*, request, scope: dict):
    return _build_aging_control(request=request, scope=scope, kind="receivables")


def build_receivables_worklist(*, request, scope: dict):
    return _build_worklist_control(request=request, scope=scope, kind="receivables")


def build_payables_aging(*, request, scope: dict):
    return _build_aging_control(request=request, scope=scope, kind="payables")


def build_payables_worklist(*, request, scope: dict):
    return _build_worklist_control(request=request, scope=scope, kind="payables")


def _scenario(scope):
    value = (scope.get("scenario") or "base").strip().lower()
    if value not in {"base", "conservative", "optimistic"}:
        return "base"
    return value


def _bucket_index_for_date(value: date | None, *, start_date: date, bucket_count: int):
    if value is None:
        return None
    if value < start_date:
        return 0
    index = (value - start_date).days // 7
    if 0 <= index < bucket_count:
        return index
    return None


def _forecast_adjustment_queryset(scope_context, *, scenario, start_date, end_date):
    filters = {
        "entity_id": scope_context["entity"].id,
        "scenario": scenario,
        "isactive": True,
        "adjustment_date__gte": start_date,
        "adjustment_date__lte": end_date,
    }
    financial_year = scope_context.get("financial_year")
    subentity = scope_context.get("subentity")
    if financial_year is not None:
        filters["entityfinid_id"] = financial_year.id
    if subentity is not None:
        filters["subentity_id"] = subentity.id
    return CashFlowForecastAdjustment.objects.filter(**filters).order_by("adjustment_date", "id")


def build_cash_flow_forecast(*, request, scope: dict):
    scope_context = _resolve_scope_context(request=request, scope=scope)
    if scope_context is None:
        return None

    permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, scope_context["entity"].id)
    scenario = _scenario(scope)
    start_date = scope_context["as_of_date"]
    bucket_count = 13
    end_date = start_date + timedelta(days=(bucket_count * 7) - 1)
    buckets = []
    for index in range(bucket_count):
        week_start = start_date + timedelta(days=index * 7)
        week_end = week_start + timedelta(days=6)
        buckets.append(
            {
                "week_index": index + 1,
                "week_start": week_start,
                "week_end": week_end,
                "customer_receipts": ZERO,
                "vendor_payments": ZERO,
                "statutory_payments": ZERO,
                "payroll_payments": ZERO,
                "manual_inflows": ZERO,
                "manual_outflows": ZERO,
                "adjustments": [],
            }
        )

    for due_date, outstanding_amount in _forecast_open_item_values(kind="receivables", scope_context=scope_context, end_date=end_date):
        index = _bucket_index_for_date(due_date, start_date=start_date, bucket_count=bucket_count)
        if index is not None:
            buckets[index]["customer_receipts"] += outstanding_amount or ZERO

    for due_date, outstanding_amount in _forecast_open_item_values(kind="payables", scope_context=scope_context, end_date=end_date):
        index = _bucket_index_for_date(due_date, start_date=start_date, bucket_count=bucket_count)
        if index is not None:
            buckets[index]["vendor_payments"] += outstanding_amount or ZERO

    statutory = _decimal(_build_compliance_summary(scope_context)["statutory_payable_estimate"])
    buckets[0]["statutory_payments"] = statutory

    for adjustment in _forecast_adjustment_queryset(scope_context, scenario=scenario, start_date=start_date, end_date=end_date):
        index = _bucket_index_for_date(adjustment.adjustment_date, start_date=start_date, bucket_count=bucket_count)
        if index is None:
            continue
        amount = adjustment.amount or ZERO
        if adjustment.direction == CashFlowForecastAdjustment.Direction.INFLOW:
            buckets[index]["manual_inflows"] += amount
        else:
            buckets[index]["manual_outflows"] += amount
        buckets[index]["adjustments"].append(
            {
                "id": adjustment.id,
                "adjustment_date": adjustment.adjustment_date.isoformat(),
                "direction": adjustment.direction,
                "category": adjustment.category,
                "description": adjustment.description,
                "amount": _money(adjustment.amount),
            }
        )

    opening_cash = _cash_balance_decimal(scope_context)
    running_cash = opening_cash
    rows = []
    for bucket in buckets:
        net_movement = (
            bucket["customer_receipts"]
            + bucket["manual_inflows"]
            - bucket["vendor_payments"]
            - bucket["statutory_payments"]
            - bucket["payroll_payments"]
            - bucket["manual_outflows"]
        )
        closing_cash = running_cash + net_movement
        rows.append(
            {
                "week_index": bucket["week_index"],
                "week_start": bucket["week_start"].isoformat(),
                "week_end": bucket["week_end"].isoformat(),
                "opening_cash": _money(running_cash),
                "customer_receipts": _money(bucket["customer_receipts"]),
                "vendor_payments": _money(bucket["vendor_payments"]),
                "statutory_payments": _money(bucket["statutory_payments"]),
                "payroll_payments": _money(bucket["payroll_payments"]),
                "manual_inflows": _money(bucket["manual_inflows"]),
                "manual_outflows": _money(bucket["manual_outflows"]),
                "net_movement": _money(net_movement),
                "closing_cash": _money(closing_cash),
                "shortfall": closing_cash < ZERO,
                "adjustments": bucket["adjustments"],
            }
        )
        running_cash = closing_cash

    return {
        "control_code": "cfo_cash_flow_forecast",
        "page_permission": CFO_CASH_FLOW_PERMISSION,
        "permissions": {
            "page": {
                "code": CFO_CASH_FLOW_PERMISSION,
                "granted": CFO_CASH_FLOW_PERMISSION in permission_codes,
            },
            "manage_adjustments": {
                "code": CFO_CASH_FLOW_ADJUST_PERMISSION,
                "granted": CFO_CASH_FLOW_ADJUST_PERMISSION in permission_codes,
            },
        },
        "scope": _scope_payload(scope_context),
        "scenario": scenario,
        "summary": {
            "opening_cash": _money(opening_cash),
            "ending_cash": rows[-1]["closing_cash"] if rows else _money(opening_cash),
            "shortfall_weeks": sum(1 for row in rows if row["shortfall"]),
            "forecast_start": start_date.isoformat(),
            "forecast_end": end_date.isoformat(),
        },
        "rows": rows,
        "notes": [
            "Receipts and vendor payments are bucketed by open-item due date; overdue items land in week 1.",
            "Payroll is currently reserved as a forecast line and will be wired to payroll runs in a later enhancement.",
        ],
    }


def _resolve_scope_models_from_payload(payload):
    entity = Entity.objects.filter(id=payload["entity"], isactive=True).first()
    if entity is None:
        raise ValueError("Entity not found.")
    financial_year = _resolve_financial_year(entity_id=entity.id, entityfinid=payload.get("entityfinid"))
    subentity = _resolve_subentity(entity_id=entity.id, subentity_id=payload.get("subentity"))
    return entity, financial_year, subentity


def create_cash_flow_adjustment(*, payload, actor):
    entity, financial_year, subentity = _resolve_scope_models_from_payload(payload)
    return CashFlowForecastAdjustment.objects.create(
        entity=entity,
        entityfinid=financial_year,
        subentity=subentity,
        scenario=payload.get("scenario") or CashFlowForecastAdjustment.Scenario.BASE,
        adjustment_date=payload["adjustment_date"],
        direction=payload["direction"],
        category=(payload.get("category") or "manual_adjustment").strip() or "manual_adjustment",
        description=(payload.get("description") or "").strip(),
        amount=payload["amount"],
        createdby=actor,
    )


def update_cash_flow_adjustment(*, adjustment_id: int, payload, actor):
    adjustment = CashFlowForecastAdjustment.objects.get(pk=adjustment_id, isactive=True)
    entity, financial_year, subentity = _resolve_scope_models_from_payload(payload)
    if adjustment.entity_id != entity.id:
        raise ValueError("Adjustment does not belong to the selected entity.")
    adjustment.entityfinid = financial_year
    adjustment.subentity = subentity
    adjustment.scenario = payload.get("scenario") or adjustment.scenario
    adjustment.adjustment_date = payload["adjustment_date"]
    adjustment.direction = payload["direction"]
    adjustment.category = (payload.get("category") or "manual_adjustment").strip() or "manual_adjustment"
    adjustment.description = (payload.get("description") or "").strip()
    adjustment.amount = payload["amount"]
    adjustment.save(update_fields=["entityfinid", "subentity", "scenario", "adjustment_date", "direction", "category", "description", "amount", "updated_at"])
    return adjustment


def delete_cash_flow_adjustment(*, adjustment_id: int):
    adjustment = CashFlowForecastAdjustment.objects.get(pk=adjustment_id, isactive=True)
    adjustment.isactive = False
    adjustment.save(update_fields=["isactive", "updated_at"])
    return adjustment


def _period_lookup(scope_context):
    return {
        "entity": scope_context["entity"],
        "entityfinid": scope_context.get("financial_year"),
        "subentity": scope_context.get("subentity"),
        "period_start": scope_context["from_date"],
        "period_end": scope_context["to_date"],
    }


def _get_or_create_month_close_period(scope_context):
    period, _ = MonthClosePeriod.objects.get_or_create(
        **_period_lookup(scope_context),
        defaults={"status": MonthClosePeriod.Status.OPEN},
    )
    return period


def _seed_month_close_tasks(period):
    existing_tasks = {
        task.task_code: task
        for task in period.tasks.filter(isactive=True)
    }
    changed = []
    rows = []
    for spec in MONTH_CLOSE_TASK_CATALOG:
        existing_task = existing_tasks.get(spec["task_code"])
        if existing_task:
            has_changes = False
            for field in ("task_label", "sort_order", "evidence_route"):
                if getattr(existing_task, field) != spec[field]:
                    setattr(existing_task, field, spec[field])
                    has_changes = True
            if has_changes:
                changed.append(existing_task)
            continue
        rows.append(
            MonthCloseTask(
                close_period=period,
                task_code=spec["task_code"],
                task_label=spec["task_label"],
                sort_order=spec["sort_order"],
                evidence_route=spec["evidence_route"],
            )
        )
    if changed:
        MonthCloseTask.objects.bulk_update(changed, ["task_label", "sort_order", "evidence_route", "updated_at"])
    if rows:
        MonthCloseTask.objects.bulk_create(rows)


def _find_month_close_period(scope_context):
    return MonthClosePeriod.objects.filter(**_period_lookup(scope_context), isactive=True).first()


def _bank_reco_close_blocker(scope_context):
    filters = {"entity_id": scope_context["entity"].id}
    financial_year = scope_context.get("financial_year")
    subentity = scope_context.get("subentity")
    if financial_year is not None:
        filters["entityfin_id"] = financial_year.id
    if subentity is not None:
        filters["subentity_id"] = subentity.id
    runs = BankReconciliationRun.objects.filter(**filters)
    runs = runs.filter(Q(as_of_date__isnull=True) | Q(as_of_date__lte=scope_context["to_date"]))
    totals = runs.aggregate(
        pending_runs=Count("id", filter=~Q(status__in=[BankReconciliationRun.Status.RECONCILED, BankReconciliationRun.Status.LOCKED])),
        exception_lines=Coalesce(Sum("exception_line_count"), Value(0)),
        unmatched_bank_amount=Coalesce(Sum("unmatched_bank_amount"), Value(ZERO)),
        unmatched_book_amount=Coalesce(Sum("unmatched_book_amount"), Value(ZERO)),
    )
    pending_runs = totals["pending_runs"] or 0
    exception_lines = totals["exception_lines"] or 0
    unmatched_bank = totals["unmatched_bank_amount"] or ZERO
    unmatched_book = totals["unmatched_book_amount"] or ZERO
    if not pending_runs and not exception_lines and unmatched_bank == ZERO and unmatched_book == ZERO:
        return ""
    parts = []
    if pending_runs:
        parts.append(f"{pending_runs} reconciliation runs pending")
    if exception_lines:
        parts.append(f"{exception_lines} exception lines")
    if unmatched_bank != ZERO:
        parts.append(f"unmatched bank {_money(unmatched_bank)}")
    if unmatched_book != ZERO:
        parts.append(f"unmatched books {_money(unmatched_book)}")
    return "; ".join(parts)


def _month_close_blockers(scope_context):
    bank_reco_reason = _bank_reco_close_blocker(scope_context)
    return {"bank_reconciliation": bank_reco_reason} if bank_reco_reason else {}


def _apply_month_close_runtime_state(period, scope_context):
    blockers = _month_close_blockers(scope_context)
    tasks = list(period.tasks.filter(isactive=True).order_by("sort_order", "id"))
    changed = []
    for task in tasks:
        reason = blockers.get(task.task_code, "")
        if reason:
            if task.status != MonthCloseTask.Status.COMPLETED and (
                task.status != MonthCloseTask.Status.BLOCKED or task.blocker_reason != reason
            ):
                task.status = MonthCloseTask.Status.BLOCKED
                task.blocker_reason = reason
                changed.append(task)
        elif task.status == MonthCloseTask.Status.BLOCKED:
            task.status = MonthCloseTask.Status.PENDING
            task.blocker_reason = ""
            changed.append(task)

        if task.task_code == "period_locked":
            should_be_completed = period.status == MonthClosePeriod.Status.LOCKED
            if should_be_completed and task.status != MonthCloseTask.Status.COMPLETED:
                task.status = MonthCloseTask.Status.COMPLETED
                task.blocker_reason = ""
                task.completed_at = period.locked_at or timezone.now()
                task.completed_by = period.locked_by
                changed.append(task)
            if not should_be_completed and task.status == MonthCloseTask.Status.COMPLETED:
                task.status = MonthCloseTask.Status.PENDING
                task.completed_at = None
                task.completed_by = None
                changed.append(task)

    if changed:
        MonthCloseTask.objects.bulk_update(
            changed,
            ["status", "blocker_reason", "completed_at", "completed_by", "updated_at"],
        )
    return list(period.tasks.filter(isactive=True).order_by("sort_order", "id"))


def _serialize_month_close_period(period, tasks, scope_context, permission_codes):
    completed_count = sum(1 for task in tasks if task.status == MonthCloseTask.Status.COMPLETED)
    total_tasks = len(tasks)
    blocked_count = sum(1 for task in tasks if task.status == MonthCloseTask.Status.BLOCKED)
    open_count = total_tasks - completed_count
    return {
        "control_code": "cfo_month_close",
        "page_permission": CFO_MONTH_CLOSE_PERMISSION,
        "permissions": {
            "page": {
                "code": CFO_MONTH_CLOSE_PERMISSION,
                "granted": CFO_MONTH_CLOSE_PERMISSION in permission_codes,
            },
            "manage": {
                "code": CFO_MONTH_CLOSE_MANAGE_PERMISSION,
                "granted": CFO_MONTH_CLOSE_MANAGE_PERMISSION in permission_codes,
            },
            "lock_period": {
                "code": CFO_MONTH_CLOSE_LOCK_PERMISSION,
                "granted": CFO_MONTH_CLOSE_LOCK_PERMISSION in permission_codes,
            },
        },
        "scope": _scope_payload(scope_context),
        "period": {
            "id": period.id,
            "period_start": period.period_start.isoformat(),
            "period_end": period.period_end.isoformat(),
            "status": period.status,
            "locked_at": period.locked_at.isoformat() if period.locked_at else None,
            "locked_by": getattr(period.locked_by, "username", None) if period.locked_by_id else None,
            "notes": period.notes,
        },
        "summary": {
            "completed_tasks": completed_count,
            "total_tasks": total_tasks,
            "open_tasks": open_count,
            "blocked_tasks": blocked_count,
            "progress_percent": round((completed_count / total_tasks) * 100) if total_tasks else 0,
            "can_lock": period.status != MonthClosePeriod.Status.LOCKED and open_count == 1 and all(
                task.status == MonthCloseTask.Status.COMPLETED or task.task_code == "period_locked" for task in tasks
            ),
        },
        "tasks": [
            {
                "id": task.id,
                "task_code": task.task_code,
                "task_label": task.task_label,
                "sort_order": task.sort_order,
                "status": task.status,
                "blocker_reason": task.blocker_reason,
                "evidence_route": task.evidence_route,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "completed_by": getattr(task.completed_by, "username", None) if task.completed_by_id else None,
                "reopened_at": task.reopened_at.isoformat() if task.reopened_at else None,
                "reopened_by": getattr(task.reopened_by, "username", None) if task.reopened_by_id else None,
                "reason": task.reason,
            }
            for task in tasks
        ],
        "notes": [
            "This cockpit tracks CFO close readiness and period lock state for the selected scope.",
            "The period lock is recorded here first; cross-module transaction blocking will be enforced in a later hard-close phase.",
        ],
    }


def _month_close_card_summary(scope_context):
    period = _find_month_close_period(scope_context)
    if period is None:
        return {
            "status": "not_started",
            "completed_tasks": 0,
            "total_tasks": len(MONTH_CLOSE_TASK_CATALOG),
            "progress_percent": 0,
            "blocked_tasks": 0,
        }
    tasks = list(period.tasks.filter(isactive=True))
    completed_count = sum(1 for task in tasks if task.status == MonthCloseTask.Status.COMPLETED)
    total_tasks = len(tasks) or len(MONTH_CLOSE_TASK_CATALOG)
    return {
        "status": period.status,
        "completed_tasks": completed_count,
        "total_tasks": total_tasks,
        "progress_percent": round((completed_count / total_tasks) * 100) if total_tasks else 0,
        "blocked_tasks": sum(1 for task in tasks if task.status == MonthCloseTask.Status.BLOCKED),
    }


def build_month_close_status(*, request, scope: dict):
    scope_context = _resolve_scope_context(request=request, scope=scope)
    if scope_context is None:
        return None

    permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, scope_context["entity"].id)
    with transaction.atomic():
        period = _get_or_create_month_close_period(scope_context)
        _seed_month_close_tasks(period)
        tasks = _apply_month_close_runtime_state(period, scope_context)
    return _serialize_month_close_period(period, tasks, scope_context, permission_codes)


def complete_month_close_task(*, request, scope: dict, task_code: str, reason: str = ""):
    scope_context = _resolve_scope_context(request=request, scope=scope)
    if scope_context is None:
        return None
    with transaction.atomic():
        period = _get_or_create_month_close_period(scope_context)
        _seed_month_close_tasks(period)
        tasks = _apply_month_close_runtime_state(period, scope_context)
        task_map = {task.task_code: task for task in tasks}
        task = task_map.get(task_code)
        if task is None:
            raise ValueError("Month close task not found.")
        if task.task_code == "period_locked":
            raise ValueError("Use the lock period action for the period locked task.")
        if task.status == MonthCloseTask.Status.BLOCKED:
            raise ValueError(task.blocker_reason or "This task is blocked.")
        task.status = MonthCloseTask.Status.COMPLETED
        task.blocker_reason = ""
        task.completed_by = request.user
        task.completed_at = timezone.now()
        task.reason = reason or task.reason
        task.save(update_fields=["status", "blocker_reason", "completed_by", "completed_at", "reason", "updated_at"])
    return build_month_close_status(request=request, scope=scope)


def reopen_month_close_task(*, request, scope: dict, task_code: str, reason: str = ""):
    scope_context = _resolve_scope_context(request=request, scope=scope)
    if scope_context is None:
        return None
    with transaction.atomic():
        period = _get_or_create_month_close_period(scope_context)
        _seed_month_close_tasks(period)
        task = period.tasks.filter(task_code=task_code, isactive=True).first()
        if task is None:
            raise ValueError("Month close task not found.")
        if task.task_code == "period_locked":
            raise ValueError("Use the unlock period action for the period locked task.")
        task.status = MonthCloseTask.Status.REOPENED
        task.blocker_reason = ""
        task.reopened_by = request.user
        task.reopened_at = timezone.now()
        task.reason = reason
        task.save(update_fields=["status", "blocker_reason", "reopened_by", "reopened_at", "reason", "updated_at"])
        if period.status == MonthClosePeriod.Status.LOCKED:
            period.status = MonthClosePeriod.Status.REOPENED
            period.locked_by = None
            period.locked_at = None
            period.notes = reason or period.notes
            period.save(update_fields=["status", "locked_by", "locked_at", "notes", "updated_at"])
    return build_month_close_status(request=request, scope=scope)


def lock_month_close_period(*, request, scope: dict, notes: str = ""):
    scope_context = _resolve_scope_context(request=request, scope=scope)
    if scope_context is None:
        return None
    with transaction.atomic():
        period = _get_or_create_month_close_period(scope_context)
        _seed_month_close_tasks(period)
        tasks = _apply_month_close_runtime_state(period, scope_context)
        incomplete = [
            task.task_label
            for task in tasks
            if task.task_code != "period_locked" and task.status != MonthCloseTask.Status.COMPLETED
        ]
        if incomplete:
            raise ValueError(f"Complete all close tasks before locking the period: {', '.join(incomplete[:3])}.")
        period.status = MonthClosePeriod.Status.LOCKED
        period.locked_by = request.user
        period.locked_at = timezone.now()
        period.notes = notes or period.notes
        period.save(update_fields=["status", "locked_by", "locked_at", "notes", "updated_at"])
        lock_task = period.tasks.filter(task_code="period_locked", isactive=True).first()
        if lock_task:
            lock_task.status = MonthCloseTask.Status.COMPLETED
            lock_task.blocker_reason = ""
            lock_task.completed_by = request.user
            lock_task.completed_at = period.locked_at
            lock_task.reason = notes or lock_task.reason
            lock_task.save(update_fields=["status", "blocker_reason", "completed_by", "completed_at", "reason", "updated_at"])
    return build_month_close_status(request=request, scope=scope)


def unlock_month_close_period(*, request, scope: dict, reason: str = ""):
    scope_context = _resolve_scope_context(request=request, scope=scope)
    if scope_context is None:
        return None
    with transaction.atomic():
        period = _get_or_create_month_close_period(scope_context)
        _seed_month_close_tasks(period)
        period.status = MonthClosePeriod.Status.REOPENED
        period.locked_by = None
        period.locked_at = None
        period.notes = reason or period.notes
        period.save(update_fields=["status", "locked_by", "locked_at", "notes", "updated_at"])
        lock_task = period.tasks.filter(task_code="period_locked", isactive=True).first()
        if lock_task:
            lock_task.status = MonthCloseTask.Status.REOPENED
            lock_task.completed_by = None
            lock_task.completed_at = None
            lock_task.reopened_by = request.user
            lock_task.reopened_at = timezone.now()
            lock_task.reason = reason
            lock_task.save(update_fields=["status", "completed_by", "completed_at", "reopened_by", "reopened_at", "reason", "updated_at"])
    return build_month_close_status(request=request, scope=scope)


def _budget_scope_lookup(scope_context):
    return {
        "entity": scope_context["entity"],
        "entityfinid": scope_context.get("financial_year"),
        "subentity": scope_context.get("subentity"),
        "period_start": scope_context["from_date"],
        "period_end": scope_context["to_date"],
    }


def _budget_scope_filter(scope_context):
    lookup = _budget_scope_lookup(scope_context)
    return {
        "entity": lookup["entity"],
        "entityfinid": lookup["entityfinid"],
        "subentity": lookup["subentity"],
        "period_start": lookup["period_start"],
        "period_end": lookup["period_end"],
        "isactive": True,
    }


def _build_budget_actuals(scope_context):
    performance = _build_period_performance(scope_context)
    compliance = _build_compliance_summary(scope_context)
    return {
        "revenue": _decimal(performance["revenue"]),
        "purchase_expense": _decimal(performance["purchase_expense"]),
        "gross_snapshot": _decimal(performance["gross_snapshot"]),
        "statutory_payable_estimate": _decimal(compliance["statutory_payable_estimate"]),
    }


def _variance_percent(variance: Decimal, budget: Decimal):
    if budget == ZERO:
        return None
    return (variance / abs(budget) * Decimal("100.00")).quantize(Decimal("0.01"))


def _is_favorable(*, category_spec, variance: Decimal):
    if category_spec["direction"] == "expense":
        return variance <= ZERO
    return variance >= ZERO


def _is_material(*, variance: Decimal, variance_percent, threshold_amount: Decimal, threshold_percent: Decimal):
    if abs(variance) >= threshold_amount:
        return True
    if variance_percent is not None and abs(variance_percent) >= threshold_percent:
        return True
    return False


def _serialize_budget_line(line):
    return {
        "id": line.id,
        "entity": line.entity_id,
        "entityfinid": line.entityfinid_id,
        "subentity": line.subentity_id,
        "period_start": line.period_start.isoformat(),
        "period_end": line.period_end.isoformat(),
        "category": line.category,
        "budget_amount": _money(line.budget_amount),
        "notes": line.notes,
        "isactive": line.isactive,
    }


def _budget_card_summary(scope_context):
    budget_filter = _budget_scope_filter(scope_context)
    budget_map = {line.category: line for line in BudgetLine.objects.filter(**budget_filter)}
    actuals = _build_budget_actuals(scope_context)
    material_count = 0
    total_budget = ZERO
    total_actual = ZERO
    threshold_amount = Decimal("10000.00")
    threshold_percent = Decimal("10.00")
    for spec in BUDGET_CATEGORY_CATALOG:
        budget = budget_map.get(spec["category"])
        budget_amount = budget.budget_amount if budget else ZERO
        actual_amount = actuals[spec["actual_key"]]
        variance = actual_amount - budget_amount
        variance_percent = _variance_percent(variance, budget_amount)
        total_budget += budget_amount
        total_actual += actual_amount
        if _is_material(
            variance=variance,
            variance_percent=variance_percent,
            threshold_amount=threshold_amount,
            threshold_percent=threshold_percent,
        ):
            material_count += 1
    return {
        "status": "configured" if budget_map else "not_started",
        "total_budget": _money(total_budget),
        "total_actual": _money(total_actual),
        "total_variance": _money(total_actual - total_budget),
        "material_variances": material_count,
    }


def build_budget_vs_actual_summary(*, request, scope: dict):
    scope_context = _resolve_scope_context(request=request, scope=scope)
    if scope_context is None:
        return None

    permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, scope_context["entity"].id)
    threshold_amount = _decimal(scope.get("threshold_amount") or Decimal("10000.00"))
    threshold_percent = _decimal(scope.get("threshold_percent") or Decimal("10.00"))
    budget_filter = _budget_scope_filter(scope_context)
    budget_map = {line.category: line for line in BudgetLine.objects.filter(**budget_filter)}
    review_map = {review.category: review for review in BudgetVarianceReview.objects.filter(**budget_filter)}
    actuals = _build_budget_actuals(scope_context)

    rows = []
    total_budget = ZERO
    total_actual = ZERO
    for spec in BUDGET_CATEGORY_CATALOG:
        budget_line = budget_map.get(spec["category"])
        review = review_map.get(spec["category"])
        budget_amount = budget_line.budget_amount if budget_line else ZERO
        actual_amount = actuals[spec["actual_key"]]
        variance = actual_amount - budget_amount
        variance_percent = _variance_percent(variance, budget_amount)
        material = _is_material(
            variance=variance,
            variance_percent=variance_percent,
            threshold_amount=threshold_amount,
            threshold_percent=threshold_percent,
        )
        total_budget += budget_amount
        total_actual += actual_amount
        rows.append(
            {
                "category": spec["category"],
                "label": spec["label"],
                "direction": spec["direction"],
                "budget_amount": _money(budget_amount),
                "actual_amount": _money(actual_amount),
                "variance_amount": _money(variance),
                "variance_percent": str(variance_percent) if variance_percent is not None else None,
                "is_favorable": _is_favorable(category_spec=spec, variance=variance),
                "is_material": material,
                "budget_present": budget_line is not None,
                "budget_notes": budget_line.notes if budget_line else "",
                "source_route": spec["route"],
                "review": (
                    {
                        "id": review.id,
                        "status": review.status,
                        "explanation": review.explanation,
                        "action_owner": review.action_owner,
                        "due_date": review.due_date.isoformat() if review.due_date else None,
                        "reviewed_by": getattr(review.reviewed_by, "username", None) if review.reviewed_by_id else None,
                        "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
                    }
                    if review
                    else None
                ),
            }
        )

    total_variance = total_actual - total_budget
    material_variances = sum(1 for row in rows if row["is_material"])
    reviewed_variances = sum(1 for row in rows if row["review"] and row["review"]["status"] != BudgetVarianceReview.Status.OPEN)
    return {
        "control_code": "cfo_budget_vs_actual",
        "page_permission": CFO_BUDGET_PERMISSION,
        "permissions": {
            "page": {
                "code": CFO_BUDGET_PERMISSION,
                "granted": CFO_BUDGET_PERMISSION in permission_codes,
            },
            "manage_budget": {
                "code": CFO_BUDGET_MANAGE_PERMISSION,
                "granted": CFO_BUDGET_MANAGE_PERMISSION in permission_codes,
            },
            "review_variances": {
                "code": CFO_BUDGET_REVIEW_PERMISSION,
                "granted": CFO_BUDGET_REVIEW_PERMISSION in permission_codes,
            },
        },
        "scope": _scope_payload(scope_context),
        "thresholds": {
            "amount": _money(threshold_amount),
            "percent": str(threshold_percent),
        },
        "summary": {
            "total_budget": _money(total_budget),
            "total_actual": _money(total_actual),
            "total_variance": _money(total_variance),
            "material_variances": material_variances,
            "reviewed_variances": reviewed_variances,
        },
        "rows": rows,
        "notes": [
            "Actuals use posted sales invoices, purchase invoices, and statutory estimates in the selected period.",
            "A variance is material when it crosses either the amount or percentage threshold.",
        ],
    }


def upsert_budget_line(*, payload, actor):
    entity, financial_year, subentity = _resolve_scope_models_from_payload(payload)
    line, _ = BudgetLine.objects.update_or_create(
        entity=entity,
        entityfinid=financial_year,
        subentity=subentity,
        period_start=payload["from_date"],
        period_end=payload["to_date"],
        category=payload["category"],
        defaults={
            "budget_amount": payload["budget_amount"],
            "notes": (payload.get("notes") or "").strip(),
            "createdby": actor,
            "isactive": True,
        },
    )
    return line


def review_budget_variance(*, payload, category: str, actor):
    entity, financial_year, subentity = _resolve_scope_models_from_payload(payload)
    if category not in {spec["category"] for spec in BUDGET_CATEGORY_CATALOG}:
        raise ValueError("Budget variance category not found.")
    review, _ = BudgetVarianceReview.objects.update_or_create(
        entity=entity,
        entityfinid=financial_year,
        subentity=subentity,
        period_start=payload["from_date"],
        period_end=payload["to_date"],
        category=category,
        defaults={
            "status": payload["status"],
            "explanation": (payload.get("explanation") or "").strip(),
            "action_owner": (payload.get("action_owner") or "").strip(),
            "due_date": payload.get("due_date"),
            "reviewed_by": actor,
            "reviewed_at": timezone.now(),
            "isactive": True,
        },
    )
    return review


def _risk_review_map(scope_context):
    filters = {
        "entity_id": scope_context["entity"].id,
        "isactive": True,
    }
    financial_year = scope_context.get("financial_year")
    subentity = scope_context.get("subentity")
    if financial_year is not None:
        filters["entityfinid_id"] = financial_year.id
    if subentity is not None:
        filters["subentity_id"] = subentity.id
    return {review.item_key: review for review in CfoRiskReview.objects.filter(**filters)}


def _attach_risk_review(row, review_map):
    review = review_map.get(row["item_key"])
    row["review"] = (
        {
            "id": review.id,
            "status": review.status,
            "note": review.note,
            "reviewed_by": getattr(review.reviewed_by, "username", None) if review.reviewed_by_id else None,
            "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
        }
        if review
        else {
            "id": None,
            "status": CfoRiskReview.Status.OPEN,
            "note": "",
            "reviewed_by": None,
            "reviewed_at": None,
        }
    )
    return row


def _risk_severity(amount: Decimal, high_value_threshold: Decimal):
    if amount >= high_value_threshold * Decimal("5"):
        return "critical"
    if amount >= high_value_threshold:
        return "high"
    return "medium"


def _risk_status(row):
    return (row.get("review") or {}).get("status") or CfoRiskReview.Status.OPEN


def _add_high_value_invoice_risks(rows, *, scope_context, review_map, high_value_threshold: Decimal):
    common_filters = {
        **_scope_filter(scope_context),
        "bill_date__range": (scope_context["from_date"], scope_context["to_date"]),
        "grand_total__gte": high_value_threshold,
    }
    sales_qs = (
        SalesInvoiceHeader.objects.filter(**common_filters)
        .exclude(status=SalesInvoiceHeader.Status.CANCELLED)
        .select_related("customer", "customer_ledger")
        .order_by("-grand_total", "-bill_date", "-id")[:50]
    )
    for invoice in sales_qs:
        amount = invoice.grand_total or ZERO
        rows.append(
            _attach_risk_review(
                {
                    "item_key": f"sales_invoice:{invoice.id}",
                    "risk_type": "high_value_sales_invoice",
                    "source_type": "sales_invoice",
                    "source_id": str(invoice.id),
                    "title": invoice.invoice_number or f"Sales invoice #{invoice.id}",
                    "party_name": getattr(invoice.customer, "accountname", None) or getattr(invoice.customer_ledger, "name", None) or "",
                    "amount": _money(amount),
                    "severity": _risk_severity(amount, high_value_threshold),
                    "age_days": max((scope_context["as_of_date"] - invoice.bill_date).days, 0) if invoice.bill_date else 0,
                    "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
                    "source_route": "/saleinvoice",
                    "reason": f"Sales document value is above CFO threshold {_money(high_value_threshold)}.",
                },
                review_map,
            )
        )

    purchase_qs = (
        PurchaseInvoiceHeader.objects.filter(**common_filters)
        .exclude(status=PurchaseInvoiceHeader.Status.CANCELLED)
        .select_related("vendor", "vendor_ledger")
        .order_by("-grand_total", "-bill_date", "-id")[:50]
    )
    for invoice in purchase_qs:
        amount = invoice.grand_total or ZERO
        rows.append(
            _attach_risk_review(
                {
                    "item_key": f"purchase_invoice:{invoice.id}",
                    "risk_type": "high_value_purchase_invoice",
                    "source_type": "purchase_invoice",
                    "source_id": str(invoice.id),
                    "title": invoice.purchase_number or invoice.supplier_invoice_number or f"Purchase invoice #{invoice.id}",
                    "party_name": getattr(invoice.vendor, "accountname", None) or getattr(invoice.vendor_ledger, "name", None) or "",
                    "amount": _money(amount),
                    "severity": _risk_severity(amount, high_value_threshold),
                    "age_days": max((scope_context["as_of_date"] - invoice.bill_date).days, 0) if invoice.bill_date else 0,
                    "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
                    "source_route": "/purchaseinvoice",
                    "reason": f"Purchase document value is above CFO threshold {_money(high_value_threshold)}.",
                },
                review_map,
            )
        )


def _add_overdue_risks(rows, *, scope_context, review_map, high_value_threshold: Decimal):
    receivable_items = (
        CustomerBillOpenItem.objects.filter(
            **_scope_filter(scope_context),
            is_open=True,
            outstanding_amount__gt=ZERO,
            due_date__lt=scope_context["as_of_date"],
        )
        .select_related("header", "customer", "customer_ledger")
        .order_by("due_date", "-outstanding_amount", "id")[:150]
    )
    for item in receivable_items:
        amount = item.outstanding_amount or ZERO
        rows.append(
            _attach_risk_review(
                {
                    "item_key": f"receivable_open_item:{item.id}",
                    "risk_type": "overdue_receivable",
                    "source_type": "receivable_open_item",
                    "source_id": str(item.id),
                    "title": getattr(item, "invoice_number", None) or str(item.header_id),
                    "party_name": _party_label(item, party_field="customer", ledger_field="customer_ledger"),
                    "amount": _money(amount),
                    "severity": "high" if amount >= high_value_threshold else "medium",
                    "age_days": _days_overdue(item.due_date, scope_context["as_of_date"]),
                    "due_date": item.due_date.isoformat(),
                    "source_route": "/cfo/receivables",
                    "reason": "Customer open item is overdue.",
                },
                review_map,
            )
        )

    payable_items = (
        VendorBillOpenItem.objects.filter(
            **_scope_filter(scope_context),
            is_open=True,
            outstanding_amount__gt=ZERO,
            due_date__lt=scope_context["as_of_date"],
        )
        .select_related("header", "vendor", "vendor_ledger")
        .order_by("due_date", "-outstanding_amount", "id")[:150]
    )
    for item in payable_items:
        amount = item.outstanding_amount or ZERO
        rows.append(
            _attach_risk_review(
                {
                    "item_key": f"payable_open_item:{item.id}",
                    "risk_type": "overdue_payable",
                    "source_type": "payable_open_item",
                    "source_id": str(item.id),
                    "title": getattr(item, "purchase_number", None) or str(item.header_id),
                    "party_name": _party_label(item, party_field="vendor", ledger_field="vendor_ledger"),
                    "amount": _money(amount),
                    "severity": "high" if amount >= high_value_threshold else "medium",
                    "age_days": _days_overdue(item.due_date, scope_context["as_of_date"]),
                    "due_date": item.due_date.isoformat(),
                    "source_route": "/cfo/payables",
                    "reason": "Vendor open item is overdue.",
                },
                review_map,
            )
        )


def _add_month_close_risks(rows, *, scope_context, review_map):
    period = _find_month_close_period(scope_context)
    if period is None:
        return
    tasks = _apply_month_close_runtime_state(period, scope_context)
    for task in tasks:
        if task.status not in {MonthCloseTask.Status.BLOCKED, MonthCloseTask.Status.REOPENED}:
            continue
        rows.append(
            _attach_risk_review(
                {
                    "item_key": f"month_close_task:{task.id}",
                    "risk_type": "month_close_blocker",
                    "source_type": "month_close_task",
                    "source_id": str(task.id),
                    "title": task.task_label,
                    "party_name": "",
                    "amount": "0.00",
                    "severity": "high" if task.status == MonthCloseTask.Status.BLOCKED else "medium",
                    "age_days": 0,
                    "due_date": period.period_end.isoformat(),
                    "source_route": "/cfo/month-close",
                    "reason": task.blocker_reason or "Month close task needs CFO attention.",
                },
                review_map,
            )
        )


def _add_budget_variance_risks(rows, *, request, scope, review_map):
    budget = build_budget_vs_actual_summary(request=request, scope=scope)
    if budget is None:
        return
    for variance_row in budget["rows"]:
        review = variance_row.get("review")
        needs_attention = variance_row["is_material"] and not review
        action_required = review and review["status"] == BudgetVarianceReview.Status.ACTION_REQUIRED
        if not needs_attention and not action_required:
            continue
        rows.append(
            _attach_risk_review(
                {
                    "item_key": f"budget_variance:{budget['scope']['from_date']}:{budget['scope']['to_date']}:{variance_row['category']}",
                    "risk_type": "budget_variance",
                    "source_type": "budget_variance",
                    "source_id": variance_row["category"],
                    "title": variance_row["label"],
                    "party_name": review["action_owner"] if review else "",
                    "amount": variance_row["variance_amount"],
                    "severity": "high" if action_required else "medium",
                    "age_days": 0,
                    "due_date": review["due_date"] if review else budget["scope"]["to_date"],
                    "source_route": "/cfo/budget-vs-actual",
                    "reason": review["explanation"] if review else "Material budget variance needs CFO explanation.",
                },
                review_map,
            )
        )


def _build_risk_rows(*, request, scope, scope_context):
    review_map = _risk_review_map(scope_context)
    high_value_threshold = _decimal(scope.get("threshold_amount") or Decimal("100000.00"))
    rows = []
    _add_high_value_invoice_risks(rows, scope_context=scope_context, review_map=review_map, high_value_threshold=high_value_threshold)
    _add_overdue_risks(rows, scope_context=scope_context, review_map=review_map, high_value_threshold=high_value_threshold)
    _add_month_close_risks(rows, scope_context=scope_context, review_map=review_map)
    _add_budget_variance_risks(rows, request=request, scope=scope, review_map=review_map)
    return rows


def _risk_queue_card_summary(*, request, scope, scope_context, precomputed=None):
    precomputed = precomputed or {}
    high_value_threshold = _decimal(scope.get("threshold_amount") or Decimal("100000.00"))
    critical_threshold = high_value_threshold * Decimal("5")
    invoice_filters = {
        **_scope_filter(scope_context),
        "bill_date__range": (scope_context["from_date"], scope_context["to_date"]),
    }
    sales_risks = (
        SalesInvoiceHeader.objects.filter(**invoice_filters, grand_total__gte=high_value_threshold)
        .exclude(status=SalesInvoiceHeader.Status.CANCELLED)
        .aggregate(
            total=Count("id"),
            critical=Count("id", filter=Q(grand_total__gte=critical_threshold)),
        )
    )
    purchase_risks = (
        PurchaseInvoiceHeader.objects.filter(**invoice_filters, grand_total__gte=high_value_threshold)
        .exclude(status=PurchaseInvoiceHeader.Status.CANCELLED)
        .aggregate(
            total=Count("id"),
            critical=Count("id", filter=Q(grand_total__gte=critical_threshold)),
        )
    )
    receivable_overdue = CustomerBillOpenItem.objects.filter(
        **_scope_filter(scope_context),
        is_open=True,
        outstanding_amount__gt=ZERO,
        due_date__lt=scope_context["as_of_date"],
    ).aggregate(
        total=Count("id"),
        high=Count("id", filter=Q(outstanding_amount__gte=high_value_threshold)),
    )
    payable_overdue = VendorBillOpenItem.objects.filter(
        **_scope_filter(scope_context),
        is_open=True,
        outstanding_amount__gt=ZERO,
        due_date__lt=scope_context["as_of_date"],
    ).aggregate(
        total=Count("id"),
        high=Count("id", filter=Q(outstanding_amount__gte=high_value_threshold)),
    )
    month_close = precomputed.get("month_close") or _month_close_card_summary(scope_context)
    budget = precomputed.get("budget_variance") or _budget_card_summary(scope_context)
    pending_count = (
        (sales_risks["total"] or 0)
        + (purchase_risks["total"] or 0)
        + (receivable_overdue["total"] or 0)
        + (payable_overdue["total"] or 0)
        + int(month_close.get("blocked_tasks") or 0)
        + int(budget.get("material_variances") or 0)
    )
    high_risk_count = (
        (sales_risks["total"] or 0)
        + (purchase_risks["total"] or 0)
        + (receivable_overdue["high"] or 0)
        + (payable_overdue["high"] or 0)
        + int(month_close.get("blocked_tasks") or 0)
    )
    critical_count = (sales_risks["critical"] or 0) + (purchase_risks["critical"] or 0)
    return {
        "pending_count": pending_count,
        "high_risk_count": high_risk_count,
        "critical_count": critical_count,
        "status": "active" if pending_count else "clear",
    }


def build_risk_queue(*, request, scope: dict):
    scope_context = _resolve_scope_context(request=request, scope=scope)
    if scope_context is None:
        return None

    permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, scope_context["entity"].id)
    rows = _build_risk_rows(request=request, scope=scope, scope_context=scope_context)
    risk_type = (scope.get("risk_type") or "").strip()
    status_filter = (scope.get("status") or "active").strip()
    if risk_type:
        rows = [row for row in rows if row["risk_type"] == risk_type]
    if status_filter == "active":
        rows = [row for row in rows if _risk_status(row) not in {CfoRiskReview.Status.RESOLVED, CfoRiskReview.Status.DISMISSED}]
    elif status_filter:
        rows = [row for row in rows if _risk_status(row) == status_filter]

    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    rows.sort(key=lambda row: (severity_rank.get(row["severity"], 9), -_decimal(row["amount"]), -int(row["age_days"] or 0)))
    limit = int(scope.get("limit") or 100)
    return {
        "control_code": "cfo_risk_queue",
        "page_permission": CFO_RISK_QUEUE_PERMISSION,
        "permissions": {
            "page": {
                "code": CFO_RISK_QUEUE_PERMISSION,
                "granted": CFO_RISK_QUEUE_PERMISSION in permission_codes,
            },
            "review": {
                "code": CFO_RISK_QUEUE_REVIEW_PERMISSION,
                "granted": CFO_RISK_QUEUE_REVIEW_PERMISSION in permission_codes,
            },
        },
        "scope": _scope_payload(scope_context),
        "filters": {
            "risk_type": risk_type or None,
            "status": status_filter,
            "threshold_amount": _money(scope.get("threshold_amount") or Decimal("100000.00")),
            "limit": limit,
        },
        "summary": {
            "total_count": len(rows),
            "critical_count": sum(1 for row in rows if row["severity"] == "critical"),
            "high_count": sum(1 for row in rows if row["severity"] == "high"),
            "acknowledged_count": sum(1 for row in rows if _risk_status(row) == CfoRiskReview.Status.ACKNOWLEDGED),
            "resolved_count": sum(1 for row in rows if _risk_status(row) == CfoRiskReview.Status.RESOLVED),
        },
        "rows": rows[:limit],
        "notes": [
            "The risk queue consolidates high-value documents, overdue items, month-close blockers, and budget variance actions.",
            "Acknowledge items to show CFO awareness; resolve or dismiss them when no further CFO follow-up is needed.",
        ],
    }


def review_risk_queue_item(*, payload, actor):
    entity, financial_year, subentity = _resolve_scope_models_from_payload(payload)
    review, _ = CfoRiskReview.objects.update_or_create(
        item_key=payload["item_key"],
        defaults={
            "entity": entity,
            "entityfinid": financial_year,
            "subentity": subentity,
            "risk_type": payload["risk_type"],
            "source_type": payload["source_type"],
            "source_id": payload.get("source_id") or "",
            "status": payload["status"],
            "note": (payload.get("note") or "").strip(),
            "reviewed_by": actor,
            "reviewed_at": timezone.now(),
            "isactive": True,
        },
    )
    return review


def _serialize_pack_snapshot(snapshot):
    return {
        "id": snapshot.id,
        "title": snapshot.title,
        "status": snapshot.status,
        "period_start": snapshot.period_start.isoformat(),
        "period_end": snapshot.period_end.isoformat(),
        "notes": snapshot.notes,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "created_by": getattr(snapshot.createdby, "username", None) if snapshot.createdby_id else None,
        "published_at": snapshot.published_at.isoformat() if snapshot.published_at else None,
        "published_by": getattr(snapshot.published_by, "username", None) if snapshot.published_by_id else None,
    }


def _management_pack_snapshot_filter(scope_context):
    filters = {
        "entity_id": scope_context["entity"].id,
        "period_start": scope_context["from_date"],
        "period_end": scope_context["to_date"],
        "isactive": True,
    }
    financial_year = scope_context.get("financial_year")
    subentity = scope_context.get("subentity")
    if financial_year is not None:
        filters["entityfinid_id"] = financial_year.id
    if subentity is not None:
        filters["subentity_id"] = subentity.id
    return filters


def build_management_pack(*, request, scope: dict):
    scope_context = _resolve_scope_context(request=request, scope=scope)
    if scope_context is None:
        return None

    entity = scope_context["entity"]
    permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, entity.id)
    performance = _build_period_performance(scope_context)
    cash = _build_cash_summary(scope_context)
    receivables = _aggregate_open_items(CustomerBillOpenItem, "outstanding_amount", "due_date", scope_context)
    payables = _aggregate_open_items(VendorBillOpenItem, "outstanding_amount", "due_date", scope_context)
    bank_reconciliation = _build_bank_reconciliation_summary(scope_context)
    month_close = build_month_close_status(request=request, scope=scope)
    budget = build_budget_vs_actual_summary(request=request, scope=scope)
    risk_queue = build_risk_queue(request=request, scope={**scope, "status": "active", "limit": 10})
    cash_flow = build_cash_flow_forecast(request=request, scope={**scope, "scenario": scope.get("scenario") or "base"})
    snapshot_qs = CfoManagementPackSnapshot.objects.filter(**_management_pack_snapshot_filter(scope_context)).order_by("-created_at", "-id")
    latest_snapshot = snapshot_qs.first()

    risk_summary = risk_queue["summary"] if risk_queue else {}
    budget_summary = budget["summary"] if budget else {}
    close_summary = month_close["summary"] if month_close else {}
    executive_flags = []
    if _decimal(performance["gross_snapshot"]) < ZERO:
        executive_flags.append("Gross snapshot is negative for the selected period.")
    if receivables["overdue_count"]:
        executive_flags.append(f"{receivables['overdue_count']} receivable items are overdue.")
    if payables["overdue_count"]:
        executive_flags.append(f"{payables['overdue_count']} payable items are overdue.")
    if bank_reconciliation["exception_line_count"]:
        executive_flags.append(f"{bank_reconciliation['exception_line_count']} bank reconciliation exceptions remain.")
    if budget_summary.get("material_variances", 0):
        executive_flags.append(f"{budget_summary['material_variances']} material budget variances need review.")
    if risk_summary.get("critical_count", 0):
        executive_flags.append(f"{risk_summary['critical_count']} critical CFO risk items are active.")

    return {
        "control_code": "cfo_management_pack",
        "page_permission": CFO_MANAGEMENT_PACK_PERMISSION,
        "permissions": {
            "page": {
                "code": CFO_MANAGEMENT_PACK_PERMISSION,
                "granted": CFO_MANAGEMENT_PACK_PERMISSION in permission_codes,
            },
            "publish": {
                "code": CFO_MANAGEMENT_PACK_PUBLISH_PERMISSION,
                "granted": CFO_MANAGEMENT_PACK_PUBLISH_PERMISSION in permission_codes,
            },
        },
        "scope": _scope_payload(scope_context),
        "executive_summary": {
            "period_label": f"{scope_context['from_date'].isoformat()} to {scope_context['to_date'].isoformat()}",
            "cash_balance": cash["total_cash_bank_balance"],
            "gross_snapshot": performance["gross_snapshot"],
            "receivables_overdue": receivables["overdue_amount"],
            "payables_due_next_7_days": payables["due_next_7_days"],
            "month_close_progress": close_summary.get("progress_percent", 0),
            "material_variances": budget_summary.get("material_variances", 0),
            "active_risks": risk_summary.get("total_count", 0),
            "flags": executive_flags,
        },
        "sections": {
            "performance": performance,
            "cash": cash,
            "cash_flow": {
                "summary": cash_flow["summary"] if cash_flow else {},
                "rows": (cash_flow["rows"][:4] if cash_flow else []),
            },
            "working_capital": {
                "receivables": receivables,
                "payables": payables,
            },
            "bank_reconciliation": bank_reconciliation,
            "month_close": {
                "period": month_close["period"] if month_close else None,
                "summary": close_summary,
                "blocked_tasks": [task for task in (month_close["tasks"] if month_close else []) if task["status"] == MonthCloseTask.Status.BLOCKED],
            },
            "budget": {
                "summary": budget_summary,
                "material_rows": [row for row in (budget["rows"] if budget else []) if row["is_material"]],
            },
            "risk_queue": {
                "summary": risk_summary,
                "rows": risk_queue["rows"] if risk_queue else [],
            },
        },
        "snapshots": {
            "count": snapshot_qs.count(),
            "latest": _serialize_pack_snapshot(latest_snapshot) if latest_snapshot else None,
            "recent": [_serialize_pack_snapshot(snapshot) for snapshot in snapshot_qs[:5]],
        },
        "notes": [
            "The management pack is generated from CFO controls for the selected period.",
            "Saved snapshots preserve the pack payload for board or management reporting history.",
        ],
    }


def create_management_pack_snapshot(*, request, payload):
    scope_context = _resolve_scope_context(request=request, scope=payload)
    if scope_context is None:
        return None
    pack = build_management_pack(request=request, scope=payload)
    if pack is None:
        return None
    title = (payload.get("title") or "").strip() or f"CFO Management Pack {scope_context['from_date'].isoformat()} to {scope_context['to_date'].isoformat()}"
    status = payload.get("status") or CfoManagementPackSnapshot.Status.DRAFT
    snapshot = CfoManagementPackSnapshot.objects.create(
        entity=scope_context["entity"],
        entityfinid=scope_context.get("financial_year"),
        subentity=scope_context.get("subentity"),
        period_start=scope_context["from_date"],
        period_end=scope_context["to_date"],
        title=title,
        status=status,
        payload=pack,
        notes=(payload.get("notes") or "").strip(),
        createdby=request.user,
        published_by=request.user if status == CfoManagementPackSnapshot.Status.PUBLISHED else None,
        published_at=timezone.now() if status == CfoManagementPackSnapshot.Status.PUBLISHED else None,
    )
    return snapshot


def _evidence_scope_filter(scope_context):
    filters = {
        "entity_id": scope_context["entity"].id,
        "period_start__lte": scope_context["to_date"],
        "period_end__gte": scope_context["from_date"],
        "isactive": True,
    }
    financial_year = scope_context.get("financial_year")
    subentity = scope_context.get("subentity")
    if financial_year is not None:
        filters["entityfinid_id"] = financial_year.id
    if subentity is not None:
        filters["subentity_id"] = subentity.id
    return filters


def _serialize_evidence_item(item):
    return {
        "id": item.id,
        "evidence_type": item.evidence_type,
        "title": item.title,
        "description": item.description,
        "source_type": item.source_type,
        "source_id": item.source_id,
        "source_route": item.source_route,
        "status": item.status,
        "owner": item.owner,
        "due_date": item.due_date.isoformat() if item.due_date else None,
        "period_start": item.period_start.isoformat(),
        "period_end": item.period_end.isoformat(),
        "created_by": getattr(item.createdby, "username", None) if item.createdby_id else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "reviewed_by": getattr(item.reviewed_by, "username", None) if item.reviewed_by_id else None,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
    }


def _audit_event(*, event_type, title, source_type, source_id="", source_route="", status="", actor=None, occurred_at=None, detail=""):
    return {
        "event_type": event_type,
        "title": title,
        "source_type": source_type,
        "source_id": str(source_id or ""),
        "source_route": source_route,
        "status": status,
        "actor": actor,
        "occurred_at": occurred_at.isoformat() if occurred_at else None,
        "detail": detail,
    }


def _build_evidence_events(scope_context):
    filters = _evidence_scope_filter(scope_context)
    events = []

    for snapshot in CfoManagementPackSnapshot.objects.filter(**filters).order_by("-created_at", "-id")[:50]:
        events.append(
            _audit_event(
                event_type="management_pack_snapshot",
                title=snapshot.title,
                source_type="management_pack",
                source_id=snapshot.id,
                source_route="/cfo/management-pack",
                status=snapshot.status,
                actor=getattr(snapshot.published_by or snapshot.createdby, "username", None),
                occurred_at=snapshot.published_at or snapshot.created_at,
                detail=snapshot.notes,
            )
        )

    risk_review_filters = {
        **_scope_filter(scope_context),
        "isactive": True,
        "reviewed_at__date__gte": scope_context["from_date"],
        "reviewed_at__date__lte": scope_context["to_date"],
    }
    for review in CfoRiskReview.objects.filter(**risk_review_filters).exclude(status=CfoRiskReview.Status.OPEN).order_by("-reviewed_at", "-updated_at", "-id")[:100]:
        events.append(
            _audit_event(
                event_type="risk_review",
                title=review.item_key,
                source_type=review.source_type,
                source_id=review.source_id,
                source_route="/cfo/risk-queue",
                status=review.status,
                actor=getattr(review.reviewed_by, "username", None) if review.reviewed_by_id else None,
                occurred_at=review.reviewed_at or review.updated_at,
                detail=review.note,
            )
        )

    for review in BudgetVarianceReview.objects.filter(**filters).exclude(status=BudgetVarianceReview.Status.OPEN).order_by("-reviewed_at", "-updated_at", "-id")[:100]:
        events.append(
            _audit_event(
                event_type="budget_variance_review",
                title=review.get_category_display(),
                source_type="budget_variance",
                source_id=review.category,
                source_route="/cfo/budget-vs-actual",
                status=review.status,
                actor=getattr(review.reviewed_by, "username", None) if review.reviewed_by_id else None,
                occurred_at=review.reviewed_at or review.updated_at,
                detail=review.explanation,
            )
        )

    close_filters = {
        "close_period__entity_id": scope_context["entity"].id,
        "close_period__period_start__lte": scope_context["to_date"],
        "close_period__period_end__gte": scope_context["from_date"],
        "isactive": True,
    }
    financial_year = scope_context.get("financial_year")
    subentity = scope_context.get("subentity")
    if financial_year is not None:
        close_filters["close_period__entityfinid_id"] = financial_year.id
    if subentity is not None:
        close_filters["close_period__subentity_id"] = subentity.id
    for task in MonthCloseTask.objects.filter(**close_filters).exclude(status=MonthCloseTask.Status.PENDING).order_by("-updated_at", "-id")[:100]:
        actor = task.completed_by if task.completed_by_id else task.reopened_by
        events.append(
            _audit_event(
                event_type="month_close_task",
                title=task.task_label,
                source_type="month_close_task",
                source_id=task.id,
                source_route="/cfo/month-close",
                status=task.status,
                actor=getattr(actor, "username", None) if actor else None,
                occurred_at=task.completed_at or task.reopened_at or task.updated_at,
                detail=task.blocker_reason or task.reason,
            )
        )

    adjustment_filters = {
        "entity_id": scope_context["entity"].id,
        "adjustment_date__gte": scope_context["from_date"],
        "adjustment_date__lte": scope_context["to_date"],
        "isactive": True,
    }
    if financial_year is not None:
        adjustment_filters["entityfinid_id"] = financial_year.id
    if subentity is not None:
        adjustment_filters["subentity_id"] = subentity.id
    for adjustment in CashFlowForecastAdjustment.objects.filter(**adjustment_filters).order_by("-created_at", "-id")[:50]:
        events.append(
            _audit_event(
                event_type="cash_flow_adjustment",
                title=adjustment.description or adjustment.category,
                source_type="cash_flow_adjustment",
                source_id=adjustment.id,
                source_route="/cfo/cash-flow",
                status=adjustment.direction,
                actor=getattr(adjustment.createdby, "username", None) if adjustment.createdby_id else None,
                occurred_at=adjustment.created_at,
                detail=f"{adjustment.scenario} {_money(adjustment.amount)} on {adjustment.adjustment_date.isoformat()}",
            )
        )

    events.sort(key=lambda row: row["occurred_at"] or "", reverse=True)
    return events


def _evidence_center_card_summary(scope_context):
    items = CfoEvidenceItem.objects.filter(**_evidence_scope_filter(scope_context))
    open_count = items.filter(status=CfoEvidenceItem.Status.OPEN).count()
    reviewed_count = items.filter(status=CfoEvidenceItem.Status.REVIEWED).count()
    return {
        "status": "open" if open_count else "clear",
        "open_items": open_count,
        "reviewed_items": reviewed_count,
        "total_items": items.count(),
    }


def build_evidence_center(*, request, scope: dict):
    scope_context = _resolve_scope_context(request=request, scope=scope)
    if scope_context is None:
        return None
    permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, scope_context["entity"].id)
    items = list(CfoEvidenceItem.objects.filter(**_evidence_scope_filter(scope_context)).order_by("-updated_at", "-id")[: int(scope.get("limit") or 100)])
    events = _build_evidence_events(scope_context)[: int(scope.get("limit") or 100)]
    return {
        "control_code": "cfo_evidence_center",
        "page_permission": CFO_EVIDENCE_CENTER_PERMISSION,
        "permissions": {
            "page": {
                "code": CFO_EVIDENCE_CENTER_PERMISSION,
                "granted": CFO_EVIDENCE_CENTER_PERMISSION in permission_codes,
            },
            "manage": {
                "code": CFO_EVIDENCE_CENTER_MANAGE_PERMISSION,
                "granted": CFO_EVIDENCE_CENTER_MANAGE_PERMISSION in permission_codes,
            },
        },
        "scope": _scope_payload(scope_context),
        "summary": {
            "evidence_items": len(items),
            "open_items": sum(1 for item in items if item.status == CfoEvidenceItem.Status.OPEN),
            "reviewed_items": sum(1 for item in items if item.status == CfoEvidenceItem.Status.REVIEWED),
            "audit_events": len(events),
        },
        "items": [_serialize_evidence_item(item) for item in items],
        "events": events,
        "notes": [
            "Evidence items are CFO-maintained references for auditor and board support.",
            "Audit events are generated from CFO workflow actions in the selected period.",
        ],
    }


def create_evidence_item(*, payload, actor):
    entity, financial_year, subentity = _resolve_scope_models_from_payload(payload)
    return CfoEvidenceItem.objects.create(
        entity=entity,
        entityfinid=financial_year,
        subentity=subentity,
        period_start=payload["from_date"],
        period_end=payload["to_date"],
        evidence_type=payload.get("evidence_type") or CfoEvidenceItem.EvidenceType.OTHER,
        title=(payload.get("title") or "").strip(),
        description=(payload.get("description") or "").strip(),
        source_type=(payload.get("source_type") or "").strip(),
        source_id=(payload.get("source_id") or "").strip(),
        source_route=(payload.get("source_route") or "").strip(),
        status=payload.get("status") or CfoEvidenceItem.Status.OPEN,
        owner=(payload.get("owner") or "").strip(),
        due_date=payload.get("due_date"),
        createdby=actor,
        reviewed_by=actor if payload.get("status") == CfoEvidenceItem.Status.REVIEWED else None,
        reviewed_at=timezone.now() if payload.get("status") == CfoEvidenceItem.Status.REVIEWED else None,
    )


def review_evidence_item(*, item_id: int, payload, actor):
    item = CfoEvidenceItem.objects.get(pk=item_id, isactive=True)
    item.status = payload["status"]
    if "description" in payload:
        item.description = (payload.get("description") or "").strip()
    item.reviewed_by = actor
    item.reviewed_at = timezone.now()
    item.save(update_fields=["status", "description", "reviewed_by", "reviewed_at", "updated_at"])
    return item


def _insight_scope_key(scope_context):
    financial_year = scope_context.get("financial_year")
    subentity = scope_context.get("subentity")
    return f"{scope_context['entity'].id}:{financial_year.id if financial_year else 0}:{subentity.id if subentity else 0}:{scope_context['from_date'].isoformat()}:{scope_context['to_date'].isoformat()}"


def _insight_review_map(scope_context):
    filters = {
        "entity_id": scope_context["entity"].id,
        "period_start": scope_context["from_date"],
        "period_end": scope_context["to_date"],
        "isactive": True,
    }
    financial_year = scope_context.get("financial_year")
    subentity = scope_context.get("subentity")
    if financial_year is not None:
        filters["entityfinid_id"] = financial_year.id
    if subentity is not None:
        filters["subentity_id"] = subentity.id
    return {signal.signal_key: signal for signal in CfoInsightSignal.objects.filter(**filters)}


def _build_signal(scope_context, *, signal_type, title, severity, metric_value, threshold, narrative, recommended_action, source_route):
    return {
        "signal_key": f"{signal_type}:{_insight_scope_key(scope_context)}",
        "signal_type": signal_type,
        "title": title,
        "severity": severity,
        "metric_value": metric_value,
        "threshold": threshold,
        "narrative": narrative,
        "recommended_action": recommended_action,
        "source_route": source_route,
        "review": {
            "id": None,
            "status": CfoInsightSignal.Status.OPEN,
            "note": "",
            "reviewed_by": None,
            "reviewed_at": None,
        },
    }


def _attach_signal_reviews(signals, review_map):
    for signal in signals:
        review = review_map.get(signal["signal_key"])
        if not review:
            continue
        signal["review"] = {
            "id": review.id,
            "status": review.status,
            "note": review.note,
            "reviewed_by": getattr(review.reviewed_by, "username", None) if review.reviewed_by_id else None,
            "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
        }
    return signals


def _active_insight_signals(signals):
    return [
        signal
        for signal in signals
        if signal["review"]["status"] not in {CfoInsightSignal.Status.RESOLVED, CfoInsightSignal.Status.DISMISSED}
    ]


def _previous_period_context(scope_context):
    days = (scope_context["to_date"] - scope_context["from_date"]).days + 1
    previous_to = scope_context["from_date"] - timedelta(days=1)
    previous_from = previous_to - timedelta(days=days - 1)
    return {**scope_context, "from_date": previous_from, "to_date": previous_to}


def _generate_insight_signals(*, request, scope, scope_context):
    signals = []
    forecast = build_cash_flow_forecast(request=request, scope={**scope, "scenario": scope.get("scenario") or "base"})
    if forecast:
        shortfall_rows = [row for row in forecast["rows"] if row["shortfall"]]
        if shortfall_rows:
            first = shortfall_rows[0]
            severity = CfoInsightSignal.Severity.CRITICAL if _decimal(first["closing_cash"]) < ZERO else CfoInsightSignal.Severity.HIGH
            signals.append(
                _build_signal(
                    scope_context,
                    signal_type="cash_shortfall",
                    title="Cash shortfall projected",
                    severity=severity,
                    metric_value=first["closing_cash"],
                    threshold="0.00",
                    narrative=f"Forecast week {first['week_index']} closes below zero cash.",
                    recommended_action="Review collections, vendor payment timing, and manual cash-flow assumptions.",
                    source_route="/cfo/cash-flow",
                )
            )

    receivables = _aggregate_open_items(CustomerBillOpenItem, "outstanding_amount", "due_date", scope_context)
    overdue_receivables = _decimal(receivables["overdue_amount"])
    if overdue_receivables > ZERO:
        severity = CfoInsightSignal.Severity.HIGH if overdue_receivables >= Decimal("100000.00") else CfoInsightSignal.Severity.MEDIUM
        signals.append(
            _build_signal(
                scope_context,
                signal_type="overdue_receivable_risk",
                title="Receivable overdue risk increasing",
                severity=severity,
                metric_value=receivables["overdue_amount"],
                threshold="0.00",
                narrative=f"{receivables['overdue_count']} customer items are overdue.",
                recommended_action="Prioritize collection follow-up for oldest and highest-value overdue customers.",
                source_route="/cfo/receivables",
            )
        )

    payables = _aggregate_open_items(VendorBillOpenItem, "outstanding_amount", "due_date", scope_context)
    cash_balance = _cash_balance_decimal(scope_context)
    payables_due = _decimal(payables["due_next_7_days"])
    if payables_due > cash_balance and payables_due > ZERO:
        signals.append(
            _build_signal(
                scope_context,
                signal_type="payables_cash_pressure",
                title="Payables exceed available cash",
                severity=CfoInsightSignal.Severity.HIGH,
                metric_value=_money(payables_due - cash_balance),
                threshold="0.00",
                narrative="Vendor payments due in the next 7 days exceed latest bank cash balance.",
                recommended_action="Re-phase vendor payments or accelerate near-term receipts.",
                source_route="/cfo/payables",
            )
        )

    budget = _budget_card_summary(scope_context)
    if budget["material_variances"]:
        severity = CfoInsightSignal.Severity.HIGH if budget["material_variances"] >= 3 else CfoInsightSignal.Severity.MEDIUM
        signals.append(
            _build_signal(
                scope_context,
                signal_type="budget_variance_cluster",
                title="Material variance cluster detected",
                severity=severity,
                metric_value=str(budget["material_variances"]),
                threshold="1",
                narrative="Multiple budget lines have crossed configured materiality thresholds.",
                recommended_action="Capture explanations and owners for each material variance.",
                source_route="/cfo/budget-vs-actual",
            )
        )

    month_close = _month_close_card_summary(scope_context)
    if month_close["blocked_tasks"]:
        signals.append(
            _build_signal(
                scope_context,
                signal_type="month_close_blocker",
                title="Month close blockers remain",
                severity=CfoInsightSignal.Severity.HIGH,
                metric_value=str(month_close["blocked_tasks"]),
                threshold="0",
                narrative="One or more close tasks are blocked by unresolved operating exceptions.",
                recommended_action="Clear blocker tasks before locking the close period.",
                source_route="/cfo/month-close",
            )
        )

    bank_reconciliation = _build_bank_reconciliation_summary(scope_context)
    if bank_reconciliation["exception_line_count"]:
        signals.append(
            _build_signal(
                scope_context,
                signal_type="bank_reconciliation_exposure",
                title="Bank reconciliation exceptions open",
                severity=CfoInsightSignal.Severity.HIGH if bank_reconciliation["exception_line_count"] >= 10 else CfoInsightSignal.Severity.MEDIUM,
                metric_value=str(bank_reconciliation["exception_line_count"]),
                threshold="0",
                narrative="Bank reconciliation exceptions can distort cash reporting and close readiness.",
                recommended_action="Review unmatched bank/book lines and clear reconciliation exceptions.",
                source_route="/bank-reco",
            )
        )

    risk_queue = _risk_queue_card_summary(
        request=request,
        scope=scope,
        scope_context=scope_context,
        precomputed={"month_close": month_close, "budget_variance": budget},
    )
    if risk_queue["critical_count"]:
        signals.append(
            _build_signal(
                scope_context,
                signal_type="critical_risk_queue",
                title="Critical CFO risk items active",
                severity=CfoInsightSignal.Severity.CRITICAL,
                metric_value=str(risk_queue["critical_count"]),
                threshold="0",
                narrative="The CFO risk queue contains critical active items.",
                recommended_action="Acknowledge or resolve critical risk items.",
                source_route="/cfo/risk-queue",
            )
        )

    current_performance = _build_period_performance(scope_context)
    previous_performance = _build_period_performance(_previous_period_context(scope_context))
    previous_revenue = _decimal(previous_performance["revenue"])
    current_revenue = _decimal(current_performance["revenue"])
    if previous_revenue > ZERO and current_revenue < previous_revenue * Decimal("0.80"):
        drop_percent = ((previous_revenue - current_revenue) / previous_revenue * Decimal("100.00")).quantize(Decimal("0.01"))
        signals.append(
            _build_signal(
                scope_context,
                signal_type="revenue_drop",
                title="Revenue dropped versus previous comparable period",
                severity=CfoInsightSignal.Severity.MEDIUM,
                metric_value=str(drop_percent),
                threshold="20.00",
                narrative=f"Revenue is down {drop_percent}% versus the previous comparable period.",
                recommended_action="Review customer billing gaps, delayed dispatches, or demand changes.",
                source_route="/dashboard-analytics",
            )
        )

    evidence = _evidence_center_card_summary(scope_context)
    if evidence["open_items"]:
        signals.append(
            _build_signal(
                scope_context,
                signal_type="open_evidence_items",
                title="Open evidence items need review",
                severity=CfoInsightSignal.Severity.LOW,
                metric_value=str(evidence["open_items"]),
                threshold="0",
                narrative="Manual CFO evidence references are still open.",
                recommended_action="Review or archive open evidence before board/audit circulation.",
                source_route="/cfo/evidence-center",
            )
        )

    return _attach_signal_reviews(signals, _insight_review_map(scope_context))


def _insights_card_summary(*, request, scope, scope_context, precomputed=None):
    precomputed = precomputed or {}
    receivables = precomputed.get("receivables") or _aggregate_open_items(CustomerBillOpenItem, "outstanding_amount", "due_date", scope_context)
    payables = precomputed.get("payables") or _aggregate_open_items(VendorBillOpenItem, "outstanding_amount", "due_date", scope_context)
    bank_reconciliation = precomputed.get("bank_reconciliation") or _build_bank_reconciliation_summary(scope_context)
    budget = precomputed.get("budget_variance") or _budget_card_summary(scope_context)
    month_close = precomputed.get("month_close") or _month_close_card_summary(scope_context)
    risk_queue = precomputed.get("risk_queue") or _risk_queue_card_summary(request=request, scope=scope, scope_context=scope_context)
    evidence = precomputed.get("evidence_center") or _evidence_center_card_summary(scope_context)
    cash_balance = _cash_balance_decimal(scope_context)

    signal_summaries = []
    overdue_receivables = _decimal(receivables["overdue_amount"])
    if overdue_receivables > ZERO:
        signal_summaries.append(CfoInsightSignal.Severity.HIGH if overdue_receivables >= Decimal("100000.00") else CfoInsightSignal.Severity.MEDIUM)
    if _decimal(payables["due_next_7_days"]) > cash_balance and _decimal(payables["due_next_7_days"]) > ZERO:
        signal_summaries.append(CfoInsightSignal.Severity.HIGH)
    if int(budget.get("material_variances") or 0):
        signal_summaries.append(CfoInsightSignal.Severity.HIGH if int(budget["material_variances"]) >= 3 else CfoInsightSignal.Severity.MEDIUM)
    if int(month_close.get("blocked_tasks") or 0):
        signal_summaries.append(CfoInsightSignal.Severity.HIGH)
    if int(bank_reconciliation.get("exception_line_count") or 0):
        signal_summaries.append(CfoInsightSignal.Severity.HIGH if int(bank_reconciliation["exception_line_count"]) >= 10 else CfoInsightSignal.Severity.MEDIUM)
    if int(risk_queue.get("critical_count") or 0):
        signal_summaries.append(CfoInsightSignal.Severity.CRITICAL)
    if int(evidence.get("open_items") or 0):
        signal_summaries.append(CfoInsightSignal.Severity.LOW)

    return {
        "status": "active" if signal_summaries else "clear",
        "active_count": len(signal_summaries),
        "critical_count": sum(1 for severity in signal_summaries if severity == CfoInsightSignal.Severity.CRITICAL),
        "high_count": sum(1 for severity in signal_summaries if severity == CfoInsightSignal.Severity.HIGH),
    }


def build_predictive_insights(*, request, scope: dict):
    scope_context = _resolve_scope_context(request=request, scope=scope)
    if scope_context is None:
        return None
    permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, scope_context["entity"].id)
    signals = _generate_insight_signals(request=request, scope=scope, scope_context=scope_context)
    status_filter = (scope.get("status") or "active").strip()
    if status_filter == "active":
        filtered = _active_insight_signals(signals)
    elif status_filter:
        filtered = [signal for signal in signals if signal["review"]["status"] == status_filter]
    else:
        filtered = signals
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    filtered.sort(key=lambda row: severity_rank.get(row["severity"], 9))
    return {
        "control_code": "cfo_predictive_insights",
        "page_permission": CFO_INSIGHTS_PERMISSION,
        "permissions": {
            "page": {
                "code": CFO_INSIGHTS_PERMISSION,
                "granted": CFO_INSIGHTS_PERMISSION in permission_codes,
            },
            "review": {
                "code": CFO_INSIGHTS_REVIEW_PERMISSION,
                "granted": CFO_INSIGHTS_REVIEW_PERMISSION in permission_codes,
            },
        },
        "scope": _scope_payload(scope_context),
        "filters": {
            "status": status_filter,
            "scenario": scope.get("scenario") or "base",
        },
        "summary": {
            "total_count": len(filtered),
            "critical_count": sum(1 for signal in filtered if signal["severity"] == CfoInsightSignal.Severity.CRITICAL),
            "high_count": sum(1 for signal in filtered if signal["severity"] == CfoInsightSignal.Severity.HIGH),
            "acknowledged_count": sum(1 for signal in filtered if signal["review"]["status"] == CfoInsightSignal.Status.ACKNOWLEDGED),
            "resolved_count": sum(1 for signal in filtered if signal["review"]["status"] == CfoInsightSignal.Status.RESOLVED),
        },
        "signals": filtered[: int(scope.get("limit") or 100)],
        "notes": [
            "Signals are deterministic and explainable, generated from CFO control data in the selected period.",
            "Treat insights as decision support; CFO review status is stored separately from source transactions.",
        ],
    }


def review_insight_signal(*, payload, actor):
    entity, financial_year, subentity = _resolve_scope_models_from_payload(payload)
    signal, _ = CfoInsightSignal.objects.update_or_create(
        signal_key=payload["signal_key"],
        defaults={
            "entity": entity,
            "entityfinid": financial_year,
            "subentity": subentity,
            "period_start": payload["from_date"],
            "period_end": payload["to_date"],
            "signal_type": payload["signal_type"],
            "severity": payload["severity"],
            "status": payload["status"],
            "note": (payload.get("note") or "").strip(),
            "reviewed_by": actor,
            "reviewed_at": timezone.now(),
            "isactive": True,
        },
    )
    return signal


def _scenario_assumptions(scope):
    return {
        "revenue_change_percent": _money(scope.get("revenue_change_percent") or ZERO),
        "purchase_change_percent": _money(scope.get("purchase_change_percent") or ZERO),
        "collection_delay_days": int(scope.get("collection_delay_days") or 0),
        "vendor_delay_days": int(scope.get("vendor_delay_days") or 0),
        "expense_increase_amount": _money(scope.get("expense_increase_amount") or ZERO),
        "one_time_cash_inflow": _money(scope.get("one_time_cash_inflow") or ZERO),
        "one_time_cash_outflow": _money(scope.get("one_time_cash_outflow") or ZERO),
    }


def _shift_week(index, *, delay_days, row_count):
    target = index + ((int(delay_days or 0) + 6) // 7)
    return target if target < row_count else None


def _min_cash(rows):
    if not rows:
        return ZERO
    return min(_decimal(row["closing_cash"]) for row in rows)


def _build_scenario_rows(baseline_rows, assumptions):
    revenue_factor = _percent_factor(assumptions["revenue_change_percent"])
    purchase_factor = _percent_factor(assumptions["purchase_change_percent"])
    expense_increase = _decimal(assumptions["expense_increase_amount"])
    one_time_cash_inflow = _decimal(assumptions["one_time_cash_inflow"])
    one_time_cash_outflow = _decimal(assumptions["one_time_cash_outflow"])
    row_count = len(baseline_rows)
    buckets = []
    for row in baseline_rows:
        buckets.append(
            {
                "week_index": row["week_index"],
                "week_start": row["week_start"],
                "week_end": row["week_end"],
                "opening_cash": ZERO,
                "customer_receipts": ZERO,
                "vendor_payments": ZERO,
                "statutory_payments": _decimal(row["statutory_payments"]),
                "payroll_payments": _decimal(row["payroll_payments"]),
                "manual_inflows": _decimal(row["manual_inflows"]),
                "manual_outflows": _decimal(row["manual_outflows"]),
            }
        )

    deferred_receipts = ZERO
    deferred_payments = ZERO
    for index, row in enumerate(baseline_rows):
        receipt_target = _shift_week(index, delay_days=assumptions["collection_delay_days"], row_count=row_count)
        receipt_amount = (_decimal(row["customer_receipts"]) * revenue_factor).quantize(Decimal("0.01"))
        if receipt_target is None:
            deferred_receipts += receipt_amount
        else:
            buckets[receipt_target]["customer_receipts"] += receipt_amount

        payment_target = _shift_week(index, delay_days=assumptions["vendor_delay_days"], row_count=row_count)
        payment_amount = (_decimal(row["vendor_payments"]) * purchase_factor).quantize(Decimal("0.01"))
        if payment_target is None:
            deferred_payments += payment_amount
        else:
            buckets[payment_target]["vendor_payments"] += payment_amount

    if buckets:
        buckets[0]["manual_inflows"] += one_time_cash_inflow
        buckets[0]["manual_outflows"] += one_time_cash_outflow + expense_increase

    running_cash = _decimal(baseline_rows[0]["opening_cash"]) if baseline_rows else ZERO
    rows = []
    for bucket in buckets:
        net_movement = (
            bucket["customer_receipts"]
            + bucket["manual_inflows"]
            - bucket["vendor_payments"]
            - bucket["statutory_payments"]
            - bucket["payroll_payments"]
            - bucket["manual_outflows"]
        )
        closing_cash = running_cash + net_movement
        rows.append(
            {
                "week_index": bucket["week_index"],
                "week_start": bucket["week_start"],
                "week_end": bucket["week_end"],
                "opening_cash": _money(running_cash),
                "customer_receipts": _money(bucket["customer_receipts"]),
                "vendor_payments": _money(bucket["vendor_payments"]),
                "statutory_payments": _money(bucket["statutory_payments"]),
                "payroll_payments": _money(bucket["payroll_payments"]),
                "manual_inflows": _money(bucket["manual_inflows"]),
                "manual_outflows": _money(bucket["manual_outflows"]),
                "net_movement": _money(net_movement),
                "closing_cash": _money(closing_cash),
                "shortfall": closing_cash < ZERO,
            }
        )
        running_cash = closing_cash
    return rows, deferred_receipts, deferred_payments


def _scenario_plan_filter(scope_context):
    filters = {
        "entity_id": scope_context["entity"].id,
        "period_start": scope_context["from_date"],
        "period_end": scope_context["to_date"],
        "isactive": True,
    }
    financial_year = scope_context.get("financial_year")
    subentity = scope_context.get("subentity")
    if financial_year is not None:
        filters["entityfinid_id"] = financial_year.id
    if subentity is not None:
        filters["subentity_id"] = subentity.id
    return filters


def _serialize_scenario_plan(plan):
    return {
        "id": plan.id,
        "entity": plan.entity_id,
        "entityfinid": plan.entityfinid_id,
        "subentity": plan.subentity_id,
        "period_start": plan.period_start.isoformat(),
        "period_end": plan.period_end.isoformat(),
        "title": plan.title,
        "status": plan.status,
        "assumptions": plan.assumptions,
        "result": plan.result,
        "notes": plan.notes,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "created_by": getattr(plan.createdby, "username", None) if plan.createdby_id else None,
        "approved_at": plan.approved_at.isoformat() if plan.approved_at else None,
        "approved_by": getattr(plan.approved_by, "username", None) if plan.approved_by_id else None,
    }


def _scenario_simulation_payload(*, request, scope, scope_context):
    baseline = build_cash_flow_forecast(request=request, scope={**scope, "scenario": scope.get("scenario") or "base"})
    performance = _build_period_performance(scope_context)
    assumptions = _scenario_assumptions(scope)
    scenario_rows, deferred_receipts, deferred_payments = _build_scenario_rows(baseline["rows"], assumptions)

    baseline_ending_cash = _decimal(baseline["summary"]["ending_cash"])
    scenario_ending_cash = _decimal(scenario_rows[-1]["closing_cash"]) if scenario_rows else baseline_ending_cash
    baseline_revenue = _decimal(performance["revenue"])
    baseline_purchase = _decimal(performance["purchase_expense"])
    baseline_gross = _decimal(performance["gross_snapshot"])
    scenario_revenue = (baseline_revenue * _percent_factor(assumptions["revenue_change_percent"])).quantize(Decimal("0.01"))
    scenario_purchase = (
        baseline_purchase * _percent_factor(assumptions["purchase_change_percent"])
        + _decimal(assumptions["expense_increase_amount"])
    ).quantize(Decimal("0.01"))
    scenario_gross = scenario_revenue - scenario_purchase

    return {
        "assumptions": assumptions,
        "baseline": {
            "ending_cash": _money(baseline_ending_cash),
            "minimum_cash": _money(_min_cash(baseline["rows"])),
            "shortfall_weeks": baseline["summary"]["shortfall_weeks"],
            "revenue": performance["revenue"],
            "purchase_expense": performance["purchase_expense"],
            "gross_snapshot": performance["gross_snapshot"],
        },
        "scenario": {
            "ending_cash": _money(scenario_ending_cash),
            "minimum_cash": _money(_min_cash(scenario_rows)),
            "shortfall_weeks": sum(1 for row in scenario_rows if row["shortfall"]),
            "revenue": _money(scenario_revenue),
            "purchase_expense": _money(scenario_purchase),
            "gross_snapshot": _money(scenario_gross),
            "deferred_receipts_outside_horizon": _money(deferred_receipts),
            "deferred_payments_outside_horizon": _money(deferred_payments),
        },
        "impact": {
            "ending_cash_delta": _money(scenario_ending_cash - baseline_ending_cash),
            "minimum_cash_delta": _money(_min_cash(scenario_rows) - _min_cash(baseline["rows"])),
            "gross_delta": _money(scenario_gross - baseline_gross),
            "shortfall_week_delta": sum(1 for row in scenario_rows if row["shortfall"]) - int(baseline["summary"]["shortfall_weeks"] or 0),
        },
        "rows": scenario_rows,
    }


def _scenario_planner_card_summary(scope_context):
    saved = CfoScenarioPlan.objects.filter(**_scenario_plan_filter(scope_context))
    latest = saved.order_by("-updated_at", "-id").first()
    latest_delta = ZERO
    if latest:
        latest_delta = _decimal((latest.result or {}).get("impact", {}).get("ending_cash_delta") or ZERO)
    return {
        "status": "saved" if latest else "ready",
        "saved_count": saved.count(),
        "latest_ending_cash_delta": _money(latest_delta),
    }


def build_scenario_planner(*, request, scope: dict):
    scope_context = _resolve_scope_context(request=request, scope=scope)
    if scope_context is None:
        return None
    permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, scope_context["entity"].id)
    simulation = _scenario_simulation_payload(request=request, scope=scope, scope_context=scope_context)
    saved = CfoScenarioPlan.objects.filter(**_scenario_plan_filter(scope_context)).order_by("-updated_at", "-id")[:10]
    return {
        "control_code": "cfo_scenario_planner",
        "page_permission": CFO_SCENARIO_PLANNER_PERMISSION,
        "permissions": {
            "page": {
                "code": CFO_SCENARIO_PLANNER_PERMISSION,
                "granted": CFO_SCENARIO_PLANNER_PERMISSION in permission_codes,
            },
            "manage": {
                "code": CFO_SCENARIO_PLANNER_MANAGE_PERMISSION,
                "granted": CFO_SCENARIO_PLANNER_MANAGE_PERMISSION in permission_codes,
            },
        },
        "scope": _scope_payload(scope_context),
        **simulation,
        "saved_scenarios": {
            "count": CfoScenarioPlan.objects.filter(**_scenario_plan_filter(scope_context)).count(),
            "recent": [_serialize_scenario_plan(plan) for plan in saved],
        },
        "notes": [
            "Scenario rows use current 13-week forecast buckets, then apply CFO assumptions without changing source transactions.",
            "Delayed receipts or payments that move beyond the 13-week horizon are shown separately for transparency.",
        ],
    }


def create_scenario_plan(*, request, payload, actor):
    entity, financial_year, subentity = _resolve_scope_models_from_payload(payload)
    scope_context = {
        "entity": entity,
        "financial_year": financial_year,
        "subentity": subentity,
        "as_of_date": payload.get("as_of_date") or timezone.localdate(),
        "from_date": payload["from_date"],
        "to_date": payload["to_date"],
    }
    simulation = _scenario_simulation_payload(request=request, scope=payload, scope_context=scope_context)
    title = (payload.get("title") or f"CFO Scenario {payload['from_date'].isoformat()} to {payload['to_date'].isoformat()}").strip()
    status = payload.get("status") or CfoScenarioPlan.Status.DRAFT
    return CfoScenarioPlan.objects.create(
        entity=entity,
        entityfinid=financial_year,
        subentity=subentity,
        period_start=payload["from_date"],
        period_end=payload["to_date"],
        title=title[:180],
        status=status,
        assumptions=simulation["assumptions"],
        result={key: simulation[key] for key in ("baseline", "scenario", "impact")},
        notes=(payload.get("notes") or "").strip(),
        createdby=actor,
        approved_by=actor if status == CfoScenarioPlan.Status.APPROVED else None,
        approved_at=timezone.now() if status == CfoScenarioPlan.Status.APPROVED else None,
    )


def build_control_tower_summary(*, request, scope: dict):
    scope_context = _resolve_scope_context(request=request, scope=scope)
    if scope_context is None:
        return None

    entity = scope_context["entity"]
    permission_codes = EffectivePermissionService.permission_codes_for_user(request.user, entity.id)

    cash = _build_cash_summary(scope_context)
    receivables = _aggregate_open_items(CustomerBillOpenItem, "outstanding_amount", "due_date", scope_context)
    payables = _aggregate_open_items(VendorBillOpenItem, "outstanding_amount", "due_date", scope_context)
    compliance = _build_compliance_summary(scope_context)
    performance = _build_period_performance(scope_context)
    bank_reconciliation = _build_bank_reconciliation_summary(scope_context)
    month_close = _month_close_card_summary(scope_context)
    budget_variance = _budget_card_summary(scope_context)
    risk_queue = _risk_queue_card_summary(
        request=request,
        scope=scope,
        scope_context=scope_context,
        precomputed={"month_close": month_close, "budget_variance": budget_variance},
    )
    snapshot_count = CfoManagementPackSnapshot.objects.filter(**_management_pack_snapshot_filter(scope_context)).count()
    evidence_center = _evidence_center_card_summary(scope_context)
    predictive_insights = _insights_card_summary(
        request=request,
        scope=scope,
        scope_context=scope_context,
        precomputed={
            "cash": cash,
            "receivables": receivables,
            "payables": payables,
            "bank_reconciliation": bank_reconciliation,
            "month_close": month_close,
            "budget_variance": budget_variance,
            "risk_queue": risk_queue,
            "evidence_center": evidence_center,
        },
    )
    scenario_planner = _scenario_planner_card_summary(scope_context)

    return {
        "dashboard_code": "cfo_control_tower",
        "dashboard_name": "CFO Control Tower",
        "page_permission": CFO_CONTROL_TOWER_PERMISSION,
        "permissions": {
            "page": {
                "code": CFO_CONTROL_TOWER_PERMISSION,
                "granted": CFO_CONTROL_TOWER_PERMISSION in permission_codes,
            }
        },
        "scope": _scope_payload(scope_context),
        "cards": {
            "cash": cash,
            "receivables": receivables,
            "payables": payables,
            "compliance": compliance,
            "performance": performance,
            "bank_reconciliation": bank_reconciliation,
            "month_close": month_close,
            "budget_variance": budget_variance,
            "management_pack": {
                "status": "saved" if snapshot_count else "not_started",
                "snapshot_count": snapshot_count,
                "latest_period": scope_context["to_date"].isoformat(),
            },
            "evidence_center": evidence_center,
            "predictive_insights": predictive_insights,
            "scenario_planner": scenario_planner,
            "approvals": risk_queue,
        },
        "exception_previews": {
            "critical_receivables": {
                "count": receivables["overdue_count"],
                "amount": receivables["overdue_amount"],
                "route": "/cfo/receivables",
            },
            "critical_payables": {
                "count": payables["overdue_count"],
                "amount": payables["overdue_amount"],
                "route": "/cfo/payables",
            },
            "reconciliation_exceptions": {
                "count": bank_reconciliation["exception_line_count"],
                "route": "/bank-reco",
            },
            "budget_variances": {
                "count": budget_variance["material_variances"],
                "route": "/cfo/budget-vs-actual",
            },
            "risk_queue": {
                "count": risk_queue["pending_count"],
                "route": "/cfo/risk-queue",
            },
            "management_pack": {
                "count": snapshot_count,
                "route": "/cfo/management-pack",
            },
            "evidence_center": {
                "count": evidence_center["open_items"],
                "route": "/cfo/evidence-center",
            },
            "predictive_insights": {
                "count": predictive_insights["active_count"],
                "route": "/cfo/insights",
            },
            "scenario_planner": {
                "count": scenario_planner["saved_count"],
                "amount": scenario_planner["latest_ending_cash_delta"],
                "route": "/cfo/scenario-planner",
            },
        },
        "notes": [
            "Cash uses the latest validated/ready bank statement closing balance per bank account.",
            "Month close opens the CFO close cockpit for checklist and lock readiness.",
            "Budget variance compares period budgets with live sales, purchase, gross, and statutory actuals.",
            "Approval card opens the CFO risk queue for review and follow-up.",
            "Management pack generates a board-ready monthly CFO summary from the control layer.",
            "Evidence center links CFO controls to review history and supporting references.",
            "Predictive insights highlight explainable early-warning signals from CFO control data.",
            "Scenario planner compares CFO what-if assumptions against the current cash and performance baseline.",
        ],
    }
