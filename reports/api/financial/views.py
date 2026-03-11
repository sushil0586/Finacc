from __future__ import annotations

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.schemas.common import build_report_envelope
from reports.schemas.financial_reports import FinancialReportScopeSerializer, LedgerBookScopeSerializer
from reports.services.financial.meta import REPORT_DEFAULTS, build_financial_report_meta
from reports.services.financial.ledger_book import build_ledger_book
from reports.services.financial.statements import build_balance_sheet, build_profit_and_loss
from reports.services.financial.trial_balance import build_trial_balance


class _BaseFinancialReportAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FinancialReportScopeSerializer

    def get_scope(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def build_filters(self, scope):
        return {
            "entity": scope["entity"],
            "entityfinid": scope.get("entityfinid"),
            "subentity": scope.get("subentity"),
            "from_date": scope.get("from_date"),
            "to_date": scope.get("to_date"),
            "as_of_date": scope.get("as_of_date"),
            "group_by": scope.get("group_by"),
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


class FinancialReportsMetaAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity_id = request.query_params.get("entity")
        if not entity_id:
            return Response({"detail": "entity is required."}, status=400)
        return Response(build_financial_report_meta(int(entity_id)))


class TrialBalanceAPIView(_BaseFinancialReportAPIView):
    def get(self, request):
        scope = self.get_scope(request)
        data = build_trial_balance(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
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
        )
        return Response(
            build_report_envelope(
                report_code="ledger_book",
                report_name="Ledger Book",
                payload=data,
                filters={**self.build_filters(scope), "ledger": scope["ledger"]},
                defaults=REPORT_DEFAULTS,
            )
        )


class ProfitAndLossAPIView(_BaseFinancialReportAPIView):
    def get(self, request):
        scope = self.get_scope(request)
        data = build_profit_and_loss(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
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
        data = build_balance_sheet(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            from_date=scope.get("from_date"),
            to_date=scope.get("to_date"),
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
