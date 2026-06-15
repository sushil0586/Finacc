from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import OuterRef, Prefetch, Q, Subquery
from django.db.models.deletion import ProtectedError
from rest_framework import permissions, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from entity.models import EntityFinancialYear
from financial.models import AccountAddress, AccountBankDetails, ContactDetails, Ledger, ShippingDetails, account, accountHead, accounttype
from financial.serializers_catalog_v2 import AccountHeadV2Serializer, AccountTypeV2Serializer
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
from financial.serializers import (
    ContactDetailsListSerializer,
    ContactDetailsSerializer,
    ShippingDetailsListSerializer,
    ShippingDetailsSerializer,
)
from financial.governance import resolve_financial_master_rule
from financial.services import (
    allocate_next_ledger_code,
    build_ledger_balance_rows,
    ensure_account_profile_for_ledger,
    ledger_should_be_party,
)


def _include_inactive(request):
    return str(request.query_params.get("include_inactive", "")).lower() in {"1", "true", "yes"}


def _active_filter_value(request):
    raw = str(request.query_params.get("isactive", "")).strip().lower()
    if raw in {"1", "true", "yes", "active"}:
        return True
    if raw in {"0", "false", "no", "inactive"}:
        return False
    if raw in {"all", "*"}:
        return None
    return None


def _apply_active_filter(qs, request):
    active_flag = _active_filter_value(request)
    if active_flag is True:
        return qs.filter(isactive=True)
    if active_flag is False:
        return qs.filter(isactive=False)
    if _include_inactive(request):
        return qs
    return qs.filter(isactive=True)


def _linked_account_id(ledger):
    if not hasattr(ledger, "account_profile"):
        return None
    return ledger.account_profile.id


def _ledger_save_kwargs(*, validated_data, request_user, instance=None, include_createdby=False):
    entity = validated_data.get("entity") or getattr(instance, "entity", None)
    accounttype_obj = validated_data.get("accounttype") or getattr(instance, "accounttype", None)
    accounthead_obj = validated_data.get("accounthead") or getattr(instance, "accounthead", None)
    creditaccounthead_obj = validated_data.get("creditaccounthead") or getattr(instance, "creditaccounthead", None)
    is_system = validated_data.get("is_system", getattr(instance, "is_system", False))
    is_party = validated_data.get("is_party", getattr(instance, "is_party", False))
    ledger_code = validated_data.get("ledger_code", getattr(instance, "ledger_code", None))

    save_kwargs = {}
    if include_createdby:
        save_kwargs["createdby"] = request_user
    if ledger_code is None and entity is not None:
        save_kwargs["ledger_code"] = allocate_next_ledger_code(
            entity_id=entity.id,
            account_type_id=getattr(accounttype_obj, "id", None),
            debit_head_id=getattr(accounthead_obj, "id", None),
            credit_head_id=getattr(creditaccounthead_obj, "id", None),
            allocated_by=request_user,
        )

    resolved_is_party = ledger_should_be_party(
        entity=entity,
        is_party=is_party,
        is_system=is_system,
        accounttype_obj=accounttype_obj,
        accounthead_obj=accounthead_obj,
        creditaccounthead_obj=creditaccounthead_obj,
    )
    if resolved_is_party != is_party:
        save_kwargs["is_party"] = resolved_is_party
    return save_kwargs


def _sync_party_management(*, ledger, request_user):
    if ledger_should_be_party(
        entity=ledger.entity,
        is_party=ledger.is_party,
        is_system=ledger.is_system,
        accounttype_obj=ledger.accounttype,
        accounthead_obj=ledger.accounthead,
        creditaccounthead_obj=ledger.creditaccounthead,
    ):
        ensure_account_profile_for_ledger(ledger=ledger, createdby=request_user)
    return ledger


def _resolve_ledger_partytype(ledger):
    account_profile = getattr(ledger, "account_profile", None)
    commercial_profile = getattr(account_profile, "commercial_profile", None) if account_profile else None
    return getattr(commercial_profile, "partytype", "") or ""


def _ledger_direct_edit_blocked(*, ledger, request_user=None):
    partytype = _resolve_ledger_partytype(ledger)
    rule = resolve_financial_master_rule(
        entity=ledger.entity,
        partytype=partytype,
        account_type_id=getattr(ledger, "accounttype_id", None),
        debit_head_id=getattr(ledger, "accounthead_id", None),
        credit_head_id=getattr(ledger, "creditaccounthead_id", None),
    )
    if rule and rule.allow_direct_ledger_edit:
        return False, _linked_account_id(ledger)

    should_be_party = ledger_should_be_party(
        entity=ledger.entity,
        is_party=ledger.is_party,
        is_system=ledger.is_system,
        accounttype_obj=getattr(ledger, "accounttype", None),
        accounthead_obj=getattr(ledger, "accounthead", None),
        creditaccounthead_obj=getattr(ledger, "creditaccounthead", None),
    )
    if hasattr(ledger, "account_profile") or should_be_party:
        if should_be_party and not hasattr(ledger, "account_profile") and request_user is not None:
            ensure_account_profile_for_ledger(ledger=ledger, createdby=request_user)
            ledger.refresh_from_db()
        return True, _linked_account_id(ledger)
    return False, _linked_account_id(ledger)


_LEGACY_ENDPOINT_ALIASES = {
    "/baseaccountlistv2": "/base-account-list-v2",
    "/accounts/simplev2": "/accounts/simple-v2",
    "/accountListPostV2": "/account-list-post-v2",
}


def _replacement_path_for_legacy_alias(request):
    normalized_path = request.path_info.rstrip("/")
    for legacy_suffix, canonical_suffix in _LEGACY_ENDPOINT_ALIASES.items():
        if normalized_path.endswith(legacy_suffix):
            return f"{normalized_path[:-len(legacy_suffix)]}{canonical_suffix}"
    return None


def _attach_deprecation_headers(request, response):
    replacement = _replacement_path_for_legacy_alias(request)
    if replacement:
        response["X-API-Deprecated"] = "true"
        response["X-API-Replacement"] = replacement
    return response


class AccountProfileV2Pagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200


class SoftDeleteRetrieveUpdateDestroyAPIView(RetrieveUpdateDestroyAPIView):
    """
    Financial master deletes should remove the record when safe.
    When the record is referenced, return a clean validation response
    instead of silently converting it to inactive.
    """

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            instance.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict") and exc.message_dict:
                return Response(exc.message_dict, status=status.HTTP_409_CONFLICT)
            messages = list(getattr(exc, "messages", []) or [])
            detail = messages[0] if messages else str(exc)
            if "because it is referenced in:" in detail:
                detail = "This record cannot be deleted because it is already used in other records or transactions."
            return Response({"detail": detail}, status=status.HTTP_409_CONFLICT)
        except ProtectedError:
            return Response(
                {"detail": "This record cannot be deleted because it is already used in other records or transactions."},
                status=status.HTTP_409_CONFLICT,
            )


class AccountTypeV2ListCreateAPIView(ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AccountTypeV2Serializer

    def get_queryset(self):
        entity_id = self.request.query_params.get("entity")
        q = (self.request.query_params.get("q") or "").strip()
        qs = accounttype.objects.all()
        if entity_id:
            qs = qs.filter(entity_id=entity_id)
        qs = _apply_active_filter(qs, self.request)
        if q:
            qs = qs.filter(Q(accounttypename__icontains=q) | Q(accounttypecode__icontains=q))
        return qs.order_by("accounttypename")

    def perform_create(self, serializer):
        try:
            serializer.save(createdby=self.request.user)
        except IntegrityError:
            raise serializers.ValidationError({"detail": "An account type with the same name or code already exists."})


class ShippingDetailsListCreateAPIView(ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ShippingDetails.objects.select_related(
            "account", "entity", "country", "state", "district", "city"
        )

    def get_serializer_class(self):
        if self.request.method.upper() == "GET":
            return ShippingDetailsListSerializer
        return ShippingDetailsSerializer

    def perform_create(self, serializer):
        serializer.save(createdby=self.request.user)


class ShippingDetailsRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ShippingDetailsSerializer

    def get_queryset(self):
        return ShippingDetails.objects.select_related(
            "account", "entity", "country", "state", "district", "city"
        )


class ShippingDetailsByAccountView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ShippingDetailsListSerializer

    def get_queryset(self):
        account_id = self.kwargs.get("account_id")
        return (
            ShippingDetails.objects.select_related(
                "account", "entity", "country", "state", "district", "city"
            )
            .filter(account_id=account_id)
            .order_by("-isprimary", "id")
            .only(
                "id",
                "account_id",
                "entity_id",
                "gstno",
                "address1",
                "address2",
                "pincode",
                "phoneno",
                "full_name",
                "emailid",
                "isprimary",
                "country_id",
                "state_id",
                "district_id",
                "city_id",
            )
        )


class ContactDetailsListCreateView(ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ContactDetails.objects.select_related(
            "account", "entity", "country", "state", "district", "city"
        )

    def get_serializer_class(self):
        if self.request.method.upper() == "GET":
            return ContactDetailsListSerializer
        return ContactDetailsSerializer

    def perform_create(self, serializer):
        serializer.save(createdby=self.request.user)


class ContactDetailsRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ContactDetailsSerializer

    def get_queryset(self):
        return ContactDetails.objects.select_related(
            "account", "entity", "country", "state", "district", "city"
        )


class ContactDetailsByAccountView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ContactDetailsListSerializer

    def get_queryset(self):
        account_id = self.kwargs.get("account_id")
        return (
            ContactDetails.objects.select_related(
                "account", "entity", "country", "state", "district", "city"
            )
            .filter(account_id=account_id)
            .order_by("-isprimary", "id")
            .only(
                "id",
                "account_id",
                "entity_id",
                "address1",
                "address2",
                "pincode",
                "phoneno",
                "full_name",
                "emailid",
                "designation",
                "isprimary",
                "country_id",
                "state_id",
                "district_id",
                "city_id",
            )
        )


class AccountTypeV2RetrieveUpdateDestroyAPIView(SoftDeleteRetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AccountTypeV2Serializer

    def get_queryset(self):
        return accounttype.objects.all()

    def perform_update(self, serializer):
        try:
            serializer.save()
        except IntegrityError:
            raise serializers.ValidationError({"detail": "An account type with the same name or code already exists."})


class AccountHeadV2ListCreateAPIView(ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AccountHeadV2Serializer

    def get_queryset(self):
        entity_id = self.request.query_params.get("entity")
        q = (self.request.query_params.get("q") or "").strip()
        qs = accountHead.objects.select_related("accountheadsr", "accounttype")
        if entity_id:
            qs = qs.filter(entity_id=entity_id)
        qs = _apply_active_filter(qs, self.request)
        if q:
            filters = Q(name__icontains=q) | Q(description__icontains=q)
            if q.isdigit():
                filters |= Q(code=int(q))
            qs = qs.filter(filters)
        return qs.order_by("code", "name")

    def perform_create(self, serializer):
        try:
            serializer.save(createdby=self.request.user)
        except IntegrityError:
            raise serializers.ValidationError({"detail": "An account head with the same name or code already exists."})


class AccountHeadV2RetrieveUpdateDestroyAPIView(SoftDeleteRetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AccountHeadV2Serializer

    def get_queryset(self):
        return accountHead.objects.select_related("accountheadsr", "accounttype")

    def perform_update(self, serializer):
        try:
            serializer.save()
        except IntegrityError:
            raise serializers.ValidationError({"detail": "An account head with the same name or code already exists."})


class LedgerListCreateAPIView(ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        entity_id = self.request.query_params.get("entity")
        q = (self.request.query_params.get("q") or "").strip()
        qs = Ledger.objects.select_related(
            "entity",
            "accounthead",
            "creditaccounthead",
            "contra_ledger",
            "accounttype",
            "account_profile",
            "account_profile__compliance_profile",
        )
        if entity_id:
            qs = qs.filter(entity_id=entity_id)
        qs = _apply_active_filter(qs, self.request)
        if q:
            filters = Q(name__icontains=q) | Q(legal_name__icontains=q)
            if q.isdigit():
                filters |= Q(ledger_code=int(q))
            qs = qs.filter(filters)
        return qs.order_by("ledger_code", "name")

    def get_serializer_class(self):
        return LedgerSerializer

    def perform_create(self, serializer):
        save_kwargs = _ledger_save_kwargs(
            validated_data=getattr(serializer, "validated_data", {}) or {},
            request_user=self.request.user,
            include_createdby=True,
        )
        try:
            ledger = serializer.save(**save_kwargs)
        except IntegrityError:
            raise serializers.ValidationError({"detail": "A ledger with this code already exists."})
        _sync_party_management(ledger=ledger, request_user=self.request.user)


class LedgerRetrieveUpdateDestroyAPIView(SoftDeleteRetrieveUpdateDestroyAPIView):
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
            "account_profile__compliance_profile",
        )

    def _auto_managed_response(self, account_id, action):
        return Response(
            {
                "detail": "This ledger is auto-managed from the Account page.",
                "error": "This ledger is auto-managed from the Account page.",
                "code": "ledger_auto_managed",
                "account_id": account_id,
                "action": action,
                "redirect": {
                    "route_name": "financial-master-accounts",
                    "hint": "Open the linked account and edit there.",
                },
            },
            status=status.HTTP_409_CONFLICT,
        )

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        blocked, account_id = _ledger_direct_edit_blocked(ledger=instance, request_user=request.user)
        if blocked:
            return self._auto_managed_response(account_id, "edit_linked_account")
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        save_kwargs = _ledger_save_kwargs(
            validated_data=getattr(serializer, "validated_data", {}) or {},
            request_user=self.request.user,
            instance=serializer.instance,
        )
        try:
            ledger = serializer.save(**save_kwargs)
        except IntegrityError:
            raise serializers.ValidationError({"detail": "A ledger with this code already exists."})
        _sync_party_management(ledger=ledger, request_user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        blocked, account_id = _ledger_direct_edit_blocked(ledger=instance, request_user=request.user)
        if blocked:
            return self._auto_managed_response(account_id, "deactivate_linked_account")
        return super().destroy(request, *args, **kwargs)


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
            return _attach_deprecation_headers(request, Response([], status=status.HTTP_200_OK))

        ledger_qs = Ledger.objects.filter(entity_id__in=entity_ids, account_profile__isnull=False, isactive=True).select_related(
            "account_profile"
        )
        if accounthead_codes:
            ledger_qs = ledger_qs.filter(accounthead__code__in=accounthead_codes)

        ledger_map = {
            ledger.id: {
                "id": ledger.id,
                "entity_id": ledger.entity_id,
                "name": ledger.name,
                "account_profile_id": ledger.account_profile.id,
            }
            for ledger in ledger_qs
        }
        if not ledger_map:
            return _attach_deprecation_headers(request, Response([], status=status.HTTP_200_OK))

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
        return _attach_deprecation_headers(request, Response(serializer.data))


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
            "account_profile__compliance_profile",
        ).prefetch_related(
            Prefetch(
                "account_profile__addresses",
                queryset=AccountAddress.objects.filter(isprimary=True, isactive=True).select_related("state"),
                to_attr="prefetched_primary_addresses",
            )
        )

        accounthead_codes = self.request.query_params.get("accounthead", "")
        codes = [int(a) for a in accounthead_codes.split(",") if a.isdigit()] if accounthead_codes else []
        if codes:
            qs = qs.filter(accounthead__code__in=codes)

        return qs.order_by("name")

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return _attach_deprecation_headers(request, response)


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
            return _attach_deprecation_headers(
                request,
                Response({"error": "Entity is required"}, status=status.HTTP_400_BAD_REQUEST),
            )

        try:
            fy = EntityFinancialYear.objects.get(entity=entity, isactive=1)
        except EntityFinancialYear.DoesNotExist:
            return _attach_deprecation_headers(
                request,
                Response({"error": "Financial year not found for the entity"}, status=status.HTTP_404_NOT_FOUND),
            )

        if not ledger_ids and account_ids:
            ledger_ids = list(
                Ledger.objects.filter(entity_id=entity, account_profile__id__in=account_ids).values_list("id", flat=True)
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
        return _attach_deprecation_headers(request, Response(serializer.data))


class AccountProfileV2ListCreateAPIView(ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = AccountProfileV2Pagination

    def get_queryset(self):
        primary_address_qs = AccountAddress.objects.filter(isprimary=True, isactive=True)
        primary_contact_qs = ContactDetails.objects.filter(isprimary=True).only(
            "id", "account_id", "phoneno", "emailid", "full_name", "designation", "isprimary"
        )
        primary_bank_qs = AccountBankDetails.objects.filter(isprimary=True, isactive=True).only(
            "id", "account_id", "bankname", "banKAcno", "ifsc", "branch", "isprimary"
        )
        entity_id = self.request.query_params.get("entity")
        q = (self.request.query_params.get("q") or "").strip()
        qs = account.objects.select_related(
            "ledger",
            "ledger__accounthead",
            "ledger__creditaccounthead",
            "compliance_profile",
            "commercial_profile",
        ).prefetch_related(
            Prefetch("addresses", queryset=primary_address_qs, to_attr="prefetched_primary_addresses"),
            Prefetch("contact_details", queryset=primary_contact_qs, to_attr="prefetched_primary_contacts"),
            Prefetch("bank_details", queryset=primary_bank_qs, to_attr="prefetched_primary_bank_details"),
        )
        if entity_id:
            qs = qs.filter(entity_id=entity_id)
        if not _include_inactive(self.request):
            qs = qs.filter(isactive=True)
        if q:
            filters = (
                Q(accountname__icontains=q) |
                Q(legalname__icontains=q) |
                Q(compliance_profile__gstno__icontains=q) |
                Q(compliance_profile__pan__icontains=q) |
                Q(contact_details__emailid__icontains=q) |
                Q(contact_details__phoneno__icontains=q) |
                Q(contact_details__full_name__icontains=q) |
                Q(bank_details__bankname__icontains=q) |
                Q(bank_details__banKAcno__icontains=q)
            )
            if q.isdigit():
                filters |= Q(ledger__ledger_code=int(q))
            qs = qs.filter(filters).distinct()

        primary_city_subquery = AccountAddress.objects.filter(
            account_id=OuterRef("pk"),
            isprimary=True,
            isactive=True,
        ).values("city__cityname")[:1]
        qs = qs.annotate(primary_city_name=Subquery(primary_city_subquery))

        ordering_raw = (self.request.query_params.get("ordering") or "").strip()
        ordering_token = ordering_raw.split(",")[0].strip() if ordering_raw else "accountname"
        desc = ordering_token.startswith("-")
        ordering_key = ordering_token[1:] if desc else ordering_token
        ordering_map = {
            "accountname": "accountname",
            "legalname": "legalname",
            "partytype": "commercial_profile__partytype",
            "gstno": "compliance_profile__gstno",
            "pan": "compliance_profile__pan",
            "city": "primary_city_name",
            "status": "isactive",
        }
        ordering_field = ordering_map.get(ordering_key, "accountname")
        direction = "-" if desc else ""
        return qs.order_by(f"{direction}{ordering_field}", "id")

    def get_serializer_class(self):
        return AccountProfileV2ReadSerializer if self.request.method.upper() == "GET" else AccountProfileV2WriteSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        if request.query_params.get("page") or request.query_params.get("page_size"):
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        write_serializer = self.get_serializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        try:
            instance = write_serializer.save()
        except IntegrityError:
            raise serializers.ValidationError({"detail": "An account with the same key details already exists."})
        read_serializer = AccountProfileV2ReadSerializer(instance, context=self.get_serializer_context())
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class AccountProfileV2RetrieveUpdateDestroyAPIView(SoftDeleteRetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        primary_address_qs = AccountAddress.objects.filter(isprimary=True, isactive=True)
        primary_contact_qs = ContactDetails.objects.filter(isprimary=True).only(
            "id", "account_id", "phoneno", "emailid", "full_name", "designation", "isprimary"
        )
        primary_bank_qs = AccountBankDetails.objects.filter(isprimary=True, isactive=True).only(
            "id", "account_id", "bankname", "banKAcno", "ifsc", "branch", "isprimary"
        )
        return account.objects.select_related(
            "ledger",
            "ledger__accounthead",
            "ledger__creditaccounthead",
            "compliance_profile",
            "commercial_profile",
        ).prefetch_related(
            Prefetch("addresses", queryset=primary_address_qs, to_attr="prefetched_primary_addresses"),
            Prefetch("contact_details", queryset=primary_contact_qs, to_attr="prefetched_primary_contacts"),
            Prefetch("bank_details", queryset=primary_bank_qs, to_attr="prefetched_primary_bank_details"),
        )

    def get_serializer_class(self):
        return AccountProfileV2ReadSerializer if self.request.method.upper() == "GET" else AccountProfileV2WriteSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        write_serializer = self.get_serializer(instance, data=request.data, partial=partial)
        write_serializer.is_valid(raise_exception=True)
        try:
            instance = write_serializer.save()
        except IntegrityError:
            raise serializers.ValidationError({"detail": "An account with the same key details already exists."})
        read_serializer = AccountProfileV2ReadSerializer(instance, context=self.get_serializer_context())
        return Response(read_serializer.data)
