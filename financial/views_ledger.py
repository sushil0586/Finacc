from rest_framework import permissions, status
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from entity.models import EntityFinancialYear
from financial.models import Ledger, account
from financial.serializers_ledger import (
    AccountProfileV2ReadSerializer,
    AccountProfileV2WriteSerializer,
    AccountListPostV2RowSerializer,
    BaseAccountListV2RowSerializer,
    LedgerBalanceRowSerializer,
    LedgerSerializer,
    LedgerSimpleSerializer,
    SimpleAccountV2Serializer,
)
from financial.services import build_ledger_balance_rows


class LedgerListCreateAPIView(ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        entity_id = self.request.query_params.get("entity")
        qs = Ledger.objects.select_related(
            "entity",
            "accounthead",
            "creditaccounthead",
            "contra_ledger",
            "accounttype",
            "account_profile",
        )
        if entity_id:
            qs = qs.filter(entity_id=entity_id)
        return qs.order_by("ledger_code", "name")

    def get_serializer_class(self):
        return LedgerSerializer

    def perform_create(self, serializer):
        serializer.save(createdby=self.request.user)


class LedgerRetrieveUpdateDestroyAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LedgerSerializer

    def get_queryset(self):
        return Ledger.objects.select_related(
            "entity",
            "accounthead",
            "creditaccounthead",
            "contra_ledger",
            "accounttype",
            "account_profile",
        )


class LedgerSimpleListAPIView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LedgerSimpleSerializer

    def get_queryset(self):
        entity_id = self.request.query_params.get("entity")
        qs = Ledger.objects.select_related("account_profile", "accounthead").filter(isactive=True)
        if entity_id:
            qs = qs.filter(entity_id=entity_id)
        accounthead_codes = self.request.query_params.get("accounthead", "")
        codes = [int(a) for a in accounthead_codes.split(",") if a.isdigit()] if accounthead_codes else []
        if codes:
            qs = qs.filter(accounthead__code__in=codes)
        return qs.order_by("name")


class LedgerBalanceListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _resolve_filters(self, request):
        data = request.data if request.method.upper() == "POST" else request.query_params
        entity = data.get("entity")
        ledger_ids = data.get("ledger_ids")
        accounthead_ids = data.get("accounthead_ids")
        sort_by = data.get("sort_by", "ledger")
        sort_order = data.get("sort_order", "asc")
        top_n = data.get("top_n")
        return entity, ledger_ids, accounthead_ids, sort_by, sort_order, top_n

    def _rows(self, request):
        entity, ledger_ids, accounthead_ids, sort_by, sort_order, top_n = self._resolve_filters(request)
        if not entity:
            return None, Response({"error": "Entity is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            fy = EntityFinancialYear.objects.get(entity=entity, isactive=1)
        except EntityFinancialYear.DoesNotExist:
            return None, Response({"error": "Financial year not found for the entity"}, status=status.HTTP_404_NOT_FOUND)

        rows = build_ledger_balance_rows(
            entity_id=int(entity),
            fin_start=fy.finstartyear,
            fin_end=fy.finendyear,
            ledger_ids=ledger_ids,
            accounthead_ids=accounthead_ids,
        )

        sort_field_map = {
            "ledger": "ledger_name",
            "account": "accountname",
            "accounthead": "accounthead_name",
        }
        sort_key = sort_field_map.get(sort_by, "ledger_name")
        reverse_sort = str(sort_order).lower() == "desc"
        rows.sort(key=lambda x: (x.get(sort_key) or "").lower(), reverse=reverse_sort)

        if top_n:
            try:
                rows = rows[: int(top_n)]
            except (TypeError, ValueError):
                pass

        return rows, None

    def get(self, request, *args, **kwargs):
        rows, error_response = self._rows(request)
        if error_response:
            return error_response
        serializer = LedgerBalanceRowSerializer(rows, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        rows, error_response = self._rows(request)
        if error_response:
            return error_response
        serializer = LedgerBalanceRowSerializer(rows, many=True)
        return Response(serializer.data)


class BaseAccountListV2APIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        entity_ids_raw = request.query_params.get("entity", "")
        accounthead_codes_raw = request.query_params.get("accounthead", "")

        entity_ids = [int(e) for e in entity_ids_raw.split(",") if e.isdigit()] if entity_ids_raw else []
        accounthead_codes = [int(a) for a in accounthead_codes_raw.split(",") if a.isdigit()] if accounthead_codes_raw else []

        if not entity_ids:
            return Response([], status=status.HTTP_200_OK)

        ledger_qs = Ledger.objects.filter(entity_id__in=entity_ids, account_profile__isnull=False, isactive=True)
        if accounthead_codes:
            ledger_qs = ledger_qs.filter(accounthead__code__in=accounthead_codes)

        ledger_map = {
            row["id"]: row
            for row in ledger_qs.values("id", "entity_id", "name", "account_profile_id")
        }
        if not ledger_map:
            return Response([], status=status.HTTP_200_OK)

        fy_map = {
            fy.entity_id: (fy.finstartyear, fy.finendyear)
            for fy in EntityFinancialYear.objects.filter(entity_id__in=entity_ids, isactive=1)
        }

        rows = []
        for entity_id, (fin_start, fin_end) in fy_map.items():
            entity_ledgers = [ledger_id for ledger_id, row in ledger_map.items() if row["entity_id"] == entity_id]
            if not entity_ledgers:
                continue
            balance_rows = build_ledger_balance_rows(
                entity_id=entity_id,
                fin_start=fin_start,
                fin_end=fin_end,
                ledger_ids=entity_ledgers,
            )
            for row in balance_rows:
                if row["account_id"] is None:
                    continue
                rows.append(
                    {
                        "accountid": row["account_id"],
                        "accountname": row["accountname"],
                        "balance": row["balance"],
                    }
                )

        serializer = BaseAccountListV2RowSerializer(rows, many=True)
        return Response(serializer.data)


class SimpleAccountsV2APIView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SimpleAccountV2Serializer

    def get_queryset(self):
        entity_id = self.request.query_params.get("entity")
        if not entity_id:
            return Ledger.objects.none()

        qs = Ledger.objects.filter(
            entity_id=entity_id,
            account_profile__isnull=False,
            isactive=True,
        ).select_related(
            "accounthead",
            "account_profile",
            "account_profile__state",
            "account_profile__district",
            "account_profile__city",
        )

        accounthead_codes = self.request.query_params.get("accounthead", "")
        codes = [int(a) for a in accounthead_codes.split(",") if a.isdigit()] if accounthead_codes else []
        if codes:
            qs = qs.filter(accounthead__code__in=codes)

        return qs.order_by("name")


class AccountListPostV2APIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        entity = request.data.get("entity")
        ledger_ids = request.data.get("ledger_ids")
        account_ids = request.data.get("account_ids")
        accounthead_ids = request.data.get("accounthead_ids")
        sort_by = request.data.get("sort_by", "account")
        sort_order = request.data.get("sort_order", "asc")
        top_n = request.data.get("top_n")

        if not entity:
            return Response({"error": "Entity is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            fy = EntityFinancialYear.objects.get(entity=entity, isactive=1)
        except EntityFinancialYear.DoesNotExist:
            return Response({"error": "Financial year not found for the entity"}, status=status.HTTP_404_NOT_FOUND)

        if not ledger_ids and account_ids:
            ledger_ids = list(
                Ledger.objects.filter(entity_id=entity, account_profile_id__in=account_ids).values_list("id", flat=True)
            )

        rows = build_ledger_balance_rows(
            entity_id=int(entity),
            fin_start=fy.finstartyear,
            fin_end=fy.finendyear,
            ledger_ids=ledger_ids,
            accounthead_ids=accounthead_ids,
        )

        final_rows = [
            {
                "accountname": row["accountname"],
                "debit": row["debit"],
                "credit": row["credit"],
                "accgst": row["accgst"],
                "accpan": row["accpan"],
                "cityname": row["cityname"],
                "accountid": row["account_id"],
                "daccountheadname": row["accounthead_name"],
                "caccountheadname": row["creditaccounthead_name"],
                "accanbedeleted": row["accanbedeleted"],
                "balance": row["balance"],
                "drcr": row["drcr"],
            }
            for row in rows
            if row["account_id"] is not None
        ]

        sort_field_map = {
            "account": "accountname",
            "accounthead": "daccountheadname",
        }
        sort_key = sort_field_map.get(sort_by, "accountname")
        reverse_sort = str(sort_order).lower() == "desc"
        final_rows.sort(key=lambda x: (x.get(sort_key) or "").lower(), reverse=reverse_sort)

        if top_n:
            try:
                final_rows = final_rows[: int(top_n)]
            except (TypeError, ValueError):
                pass

        serializer = AccountListPostV2RowSerializer(final_rows, many=True)
        return Response(serializer.data)


class AccountProfileV2ListCreateAPIView(ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        entity_id = self.request.query_params.get("entity")
        qs = account.objects.select_related(
            "ledger",
            "ledger__accounthead",
            "ledger__creditaccounthead",
            "country",
            "state",
            "district",
            "city",
        )
        if entity_id:
            qs = qs.filter(entity_id=entity_id)
        return qs.order_by("accountname")

    def get_serializer_class(self):
        return AccountProfileV2ReadSerializer if self.request.method.upper() == "GET" else AccountProfileV2WriteSerializer


class AccountProfileV2RetrieveUpdateDestroyAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return account.objects.select_related(
            "ledger",
            "ledger__accounthead",
            "ledger__creditaccounthead",
            "country",
            "state",
            "district",
            "city",
        )

    def get_serializer_class(self):
        return AccountProfileV2ReadSerializer if self.request.method.upper() == "GET" else AccountProfileV2WriteSerializer
