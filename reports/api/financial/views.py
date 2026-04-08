from __future__ import annotations

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from reports.schemas.common import build_report_envelope
from reports.schemas.financial_reports import FinancialReportScopeSerializer, LedgerBookScopeSerializer
from reports.services.financial.meta import REPORT_DEFAULTS, build_financial_report_meta
from reports.services.financial.ledger_book import build_ledger_book
from reports.services.financial.reporting_policy import resolve_financial_reporting_policy
from reports.services.financial.statements import build_balance_sheet, build_profit_and_loss
from reports.services.financial.trial_balance import build_trial_balance
from reports.services.trading_account import build_trading_account_dynamic
from reports.selectors.financial import ensure_date
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService


class _BaseFinancialReportAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FinancialReportScopeSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get_scope(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        return scope

    def build_filters(self, scope):
        return {
            "entity": scope["entity"],
            "entityfinid": scope.get("entityfinid"),
            "subentity": scope.get("subentity"),
            "scope_mode": scope.get("scope_mode"),
            "from_date": scope.get("from_date"),
            "to_date": scope.get("to_date"),
            "as_of_date": scope.get("as_of_date"),
            "group_by": scope.get("group_by"),
            "period_by": scope.get("period_by"),
            "stock_valuation_mode": scope.get(
                "stock_valuation_mode",
                REPORT_DEFAULTS["balance_sheet_stock_valuation_mode"],
            ),
            "stock_valuation_method": scope.get(
                "stock_valuation_method",
                REPORT_DEFAULTS["balance_sheet_stock_valuation_method"],
            ),
            "include_zero_balances": scope.get(
                "include_zero_balances",
                REPORT_DEFAULTS["show_zero_balances_default"],
            ),
            "include_inactive_ledgers": scope.get("include_inactive_ledgers", False),
            "search": scope.get("search"),
            "sort_by": scope.get("sort_by"),
            "sort_order": scope.get("sort_order", "asc"),
            "page": scope.get("page", 1),
            "page_size": scope.get("page_size", REPORT_DEFAULTS["default_page_size"]),
            "export": scope.get("export"),
        }


class FinancialReportsMetaAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get(self, request):
        entity_id = request.query_params.get("entity")
        if not entity_id:
            return Response({"detail": "entity is required."}, status=400)
        entity_id = int(entity_id)
        self.enforce_scope(request, entity_id=entity_id)
        payload = build_financial_report_meta(entity_id)
        payload["reporting_policy"] = resolve_financial_reporting_policy(entity_id)
        return Response(payload)


class TrialBalanceAPIView(_BaseFinancialReportAPIView):
    def get(self, request):
        scope = self.get_scope(request)
        data = build_trial_balance(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            group_by=scope.get("group_by"),
            include_zero_balances=scope.get(
                "include_zero_balances",
                REPORT_DEFAULTS["show_zero_balances_default"],
            ),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "asc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", REPORT_DEFAULTS["default_page_size"]),
            period_by=scope.get("period_by"),
        )
        return Response(
            build_report_envelope(
                report_code="trial_balance",
                report_name="Trial Balance",
                payload=data,
                filters=self.build_filters(scope),
                defaults=REPORT_DEFAULTS,
            )
        )


class LedgerBookAPIView(_BaseFinancialReportAPIView):
    serializer_class = LedgerBookScopeSerializer

    def get(self, request):
        scope = self.get_scope(request)
        data = build_ledger_book(
            entity_id=scope["entity"],
            ledger_id=scope["ledger"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            search=scope.get("search"),
            voucher_types=[scope.get("voucher_type")] if scope.get("voucher_type") else None,
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "asc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", REPORT_DEFAULTS["default_page_size"]),
        )
        return Response(
            build_report_envelope(
                report_code="ledger_book",
                report_name="Ledger Book",
                payload=data,
                filters={**self.build_filters(scope), "ledger": scope["ledger"], "voucher_type": scope.get("voucher_type")},
                defaults=REPORT_DEFAULTS,
            )
        )


class ProfitAndLossAPIView(_BaseFinancialReportAPIView):
    def get(self, request):
        scope = self.get_scope(request)
        reporting_policy = resolve_financial_reporting_policy(scope["entity"])
        data = build_profit_and_loss(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            group_by=scope.get("group_by"),
            include_zero_balances=scope.get(
                "include_zero_balances",
                REPORT_DEFAULTS["show_zero_balances_default"],
            ),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "asc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", REPORT_DEFAULTS["default_page_size"]),
            period_by=scope.get("period_by"),
            reporting_policy=reporting_policy,
        )
        return Response(
            build_report_envelope(
                report_code="profit_loss",
                report_name="Profit and Loss",
                payload=data,
                filters=self.build_filters(scope),
                defaults=REPORT_DEFAULTS,
            )
        )


class BalanceSheetAPIView(_BaseFinancialReportAPIView):
    def get(self, request):
        scope = self.get_scope(request)
        reporting_policy = resolve_financial_reporting_policy(scope["entity"])
        data = build_balance_sheet(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
            as_of_date=scope.get("as_of_date"),
            group_by=scope.get("group_by"),
            include_zero_balances=scope.get(
                "include_zero_balances",
                REPORT_DEFAULTS["show_zero_balances_default"],
            ),
            search=scope.get("search"),
            sort_by=scope.get("sort_by"),
            sort_order=scope.get("sort_order", "asc"),
            page=scope.get("page", 1),
            page_size=scope.get("page_size", REPORT_DEFAULTS["default_page_size"]),
            period_by=scope.get("period_by"),
            reporting_policy=reporting_policy,
        )
        return Response(
            build_report_envelope(
                report_code="balance_sheet",
                report_name="Balance Sheet",
                payload=data,
                filters=self.build_filters(scope),
                defaults=REPORT_DEFAULTS,
            )
        )


class TradingAccountAPIView(ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get(self, request):
        entity_id = request.query_params.get("entity")
        startdate = request.query_params.get("startdate") or request.query_params.get("from_date")
        enddate = request.query_params.get("enddate") or request.query_params.get("to_date")
        entityfinid = request.query_params.get("entityfinid")
        subentity = request.query_params.get("subentity")
        valuation_method = (request.query_params.get("valuation_method") or "fifo").lower()
        level = (request.query_params.get("level") or "head").lower()

        if not entity_id:
            return Response({"detail": "entity is required."}, status=400)
        if not startdate or not enddate:
            return Response({"detail": "startdate and enddate are required."}, status=400)

        entity_id = int(entity_id)
        entityfinid = int(entityfinid) if entityfinid not in (None, "", "0", 0) else None
        subentity = int(subentity) if subentity not in (None, "", "0", 0) else None

        self.enforce_scope(
            request,
            entity_id=entity_id,
            entityfinid_id=entityfinid,
            subentity_id=subentity,
        )

        start = ensure_date(startdate)
        end = ensure_date(enddate)
        data = build_trading_account_dynamic(
            entity_id=entity_id,
            startdate=start.isoformat(),
            enddate=end.isoformat(),
            valuation_method=valuation_method,
            level=level,
        )

        return Response(
            build_report_envelope(
                report_code="trading_account",
                report_name="Trading Account",
                payload=data,
                filters={
                    "entity": entity_id,
                    "entityfinid": entityfinid,
                    "subentity": subentity,
                    "from_date": start.isoformat(),
                    "to_date": end.isoformat(),
                    "level": level,
                    "valuation_method": valuation_method,
                },
                defaults=REPORT_DEFAULTS,
            )
        )
