from __future__ import annotations

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from posting.models import Entry
from reports.schemas.book_reports import CashbookScopeSerializer, DaybookScopeSerializer
from reports.schemas.common import build_report_envelope
from reports.services.financial.books import (
    BOOK_REPORT_DEFAULTS,
    build_cashbook,
    build_daybook,
    build_daybook_entry_detail,
)


class _BaseBookReportAPIView(APIView):
    """Common utilities for thin report views that delegate accounting logic to services."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = None

    def get_scope(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def attach_pagination_links(self, request, payload):
        """Populate stable `next` and `previous` URLs for paginated report responses."""
        page = payload.get("page") or 1
        pages = payload.get("pages") or 0
        if pages <= 0:
            payload["next"] = None
            payload["previous"] = None
            return payload

        def build_url(target_page):
            params = request.GET.copy()
            params["page"] = str(target_page)
            return request.build_absolute_uri(f"{request.path}?{params.urlencode()}")

        payload["next"] = build_url(page + 1) if page < pages else None
        payload["previous"] = build_url(page - 1) if page > 1 else None
        return payload


class DaybookAPIView(_BaseBookReportAPIView):
    """Return Daybook rows derived from posting entries and journal totals."""

    serializer_class = DaybookScopeSerializer

    def get(self, request):
        scope = self.get_scope(request)
        try:
            data = build_daybook(
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
                from_date=scope.get("from_date"),
                to_date=scope.get("to_date"),
                voucher_types=scope.get("voucher_types"),
                account_ids=scope.get("account_ids"),
                statuses=scope.get("statuses"),
                posted=scope.get("posted"),
                search=scope.get("search"),
                page=scope.get("page", BOOK_REPORT_DEFAULTS["default_page_size_page"]),
                page_size=scope.get("page_size", BOOK_REPORT_DEFAULTS["default_page_size"]),
            )
        except ValueError as exc:
            return Response(exc.args[0], status=400)
        self.attach_pagination_links(request, data)
        return Response(
            build_report_envelope(
                report_code="daybook",
                report_name="Daybook",
                payload=data,
                filters={
                    "entity": scope["entity"],
                    "entityfinid": scope.get("entityfinid"),
                    "subentity": scope.get("subentity"),
                    "from_date": scope.get("from_date"),
                    "to_date": scope.get("to_date"),
                    "voucher_type": scope.get("voucher_types", []),
                    "account": scope.get("account_ids", []),
                    "status": scope.get("statuses", []),
                    "posted": scope.get("posted"),
                    "search": scope.get("search"),
                    "page": scope.get("page", BOOK_REPORT_DEFAULTS["default_page_size_page"]),
                    "page_size": scope.get("page_size", BOOK_REPORT_DEFAULTS["default_page_size"]),
                },
                defaults=BOOK_REPORT_DEFAULTS,
            )
        )


class DaybookEntryDetailAPIView(APIView):
    """Return a journal-line drill-down payload for a single posting entry."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, entry_id: int):
        entity_id = request.query_params.get("entity")
        if not entity_id:
            return Response({"detail": "entity is required."}, status=400)
        entityfin_id = request.query_params.get("entityfinid")
        subentity_id = request.query_params.get("subentity")
        try:
            data = build_daybook_entry_detail(
                entry_id=entry_id,
                entity_id=entity_id,
                entityfin_id=entityfin_id,
                subentity_id=subentity_id,
            )
        except Entry.DoesNotExist:
            return Response({"detail": "Entry not found."}, status=404)
        return Response(data)


class CashbookAPIView(_BaseBookReportAPIView):
    """Return audit-safe Cashbook detail or summary output depending on account scope."""

    serializer_class = CashbookScopeSerializer

    def get(self, request):
        scope = self.get_scope(request)
        try:
            data = build_cashbook(
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
                from_date=scope.get("from_date"),
                to_date=scope.get("to_date"),
                mode=scope.get("mode", "both"),
                cash_account_ids=scope.get("cash_account_ids"),
                bank_account_ids=scope.get("bank_account_ids"),
                counter_account_ids=scope.get("counter_account_ids"),
                voucher_types=scope.get("voucher_types"),
                search=scope.get("search"),
                page=scope.get("page", BOOK_REPORT_DEFAULTS["default_page_size_page"]),
                page_size=scope.get("page_size", BOOK_REPORT_DEFAULTS["default_page_size"]),
            )
        except ValueError as exc:
            return Response(exc.args[0], status=400)
        self.attach_pagination_links(request, data)
        return Response(
            build_report_envelope(
                report_code="cashbook",
                report_name="Cashbook",
                payload=data,
                filters={
                    "entity": scope["entity"],
                    "entityfinid": scope.get("entityfinid"),
                    "subentity": scope.get("subentity"),
                    "from_date": scope.get("from_date"),
                    "to_date": scope.get("to_date"),
                    "mode": scope.get("mode", "both"),
                    "cash_account": scope.get("cash_account_ids", []),
                    "bank_account": scope.get("bank_account_ids", []),
                    "account": scope.get("counter_account_ids", []),
                    "voucher_type": scope.get("voucher_types", []),
                    "search": scope.get("search"),
                    "page": scope.get("page", BOOK_REPORT_DEFAULTS["default_page_size_page"]),
                    "page_size": scope.get("page_size", BOOK_REPORT_DEFAULTS["default_page_size"]),
                },
                defaults=BOOK_REPORT_DEFAULTS,
            )
        )
