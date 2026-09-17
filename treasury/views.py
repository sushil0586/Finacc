from __future__ import annotations

from django.db import models
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from rbac.services import EffectivePermissionService
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService

from .models import TreasuryCashMovement, TreasuryChequeBook, TreasuryChequeLeaf, TreasuryPaymentBatch, TreasuryPaymentInstrument
from .serializers import (
    TreasuryChequeBookCreateSerializer,
    TreasuryChequeBookSerializer,
    TreasuryChequeLeafSerializer,
    TreasuryCashMovementCancelSerializer,
    TreasuryCashMovementCreateSerializer,
    TreasuryCashMovementSerializer,
    TreasuryPaymentBatchActionSerializer,
    TreasuryPaymentBatchCreateSerializer,
    TreasuryPaymentBatchDetailSerializer,
    TreasuryPaymentBatchListSerializer,
    TreasuryPaymentInstrumentActionSerializer,
    TreasuryPaymentInstrumentSerializer,
    TreasuryVendorPayableCandidateSerializer,
)
from .services import TreasuryPaymentBatchService

VIEW_PERMISSION_CODES = ("treasury.payment_batch.view", "reports.financial_hub.view")
CREATE_PERMISSION_CODES = ("treasury.payment_batch.create", "payments.payment_batch.create")
VALIDATE_PERMISSION_CODES = ("treasury.payment_batch.validate", "treasury.payment_batch.update")
APPROVE_PERMISSION_CODES = ("treasury.payment_batch.approve",)
EXPORT_PERMISSION_CODES = ("treasury.payment_batch.export",)
STATUS_PERMISSION_CODES = ("treasury.payment_batch.update", "treasury.payment_batch.mark_paid")
INSTRUMENT_STATUS_PERMISSION_CODES = (
    "treasury.payment_batch.update",
    "treasury.payment_batch.mark_paid",
    "treasury.payment_batch.export",
)
SETUP_PERMISSION_CODES = ("treasury.setup.view", "treasury.setup.update", "treasury.payment_batch.update", "treasury.payment_batch.create")
CASH_MOVEMENT_PERMISSION_CODES = ("treasury.payment_batch.update", "voucher.bank.view", "voucher.cash.view")


def _parse_int(value, label: str, *, required: bool = True):
    if value in (None, "", "null"):
        if required:
            raise ValidationError({"detail": f"{label} is required."})
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValidationError({"detail": f"{label} must be an integer."})
    return parsed or None


class TreasuryPermissionMixin:
    def require_any_permission(self, request, entity_id: int, permission_codes: tuple[str, ...]) -> None:
        EffectivePermissionService.entity_for_user(request.user, int(entity_id))
        current_codes = set(EffectivePermissionService.permission_codes_for_user(request.user, int(entity_id)))
        if any(code in current_codes for code in permission_codes):
            return
        raise PermissionDenied({"detail": f"Missing permission: one of {', '.join(permission_codes)}"})


class TreasuryPaymentBatchListCreateAPIView(ScopedEntitlementMixin, TreasuryPermissionMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get_serializer_class(self):
        if self.request.method == "POST":
            return TreasuryPaymentBatchCreateSerializer
        return TreasuryPaymentBatchListSerializer

    def get_queryset(self):
        entity_id = _parse_int(self.request.query_params.get("entity"), "entity")
        entityfinid_id = _parse_int(self.request.query_params.get("entityfinid"), "entityfinid", required=False)
        subentity_id = _parse_int(self.request.query_params.get("subentity"), "subentity", required=False)
        self.enforce_scope(self.request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        self.require_any_permission(self.request, entity_id, VIEW_PERMISSION_CODES)
        qs = TreasuryPaymentBatch.objects.select_related("entity", "entityfinid", "subentity").filter(entity_id=entity_id)
        if entityfinid_id:
            qs = qs.filter(entityfinid_id=entityfinid_id)
        if subentity_id:
            qs = qs.filter(subentity_id=subentity_id)
        status_value = self.request.query_params.get("status")
        if status_value:
            qs = qs.filter(status=status_value)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        entity_id = data["entity"]
        entityfinid_id = data["entityfinid"]
        subentity_id = data.get("subentity")
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        self.require_any_permission(request, entity_id, CREATE_PERMISSION_CODES)
        try:
            batch = TreasuryPaymentBatchService.create_from_vendor_open_items(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                open_item_ids=data["open_item_ids"],
                batch_name=data.get("batch_name", ""),
                payout_date=data.get("payout_date"),
                paid_from_id=data.get("paid_from"),
                payment_mode_id=data.get("payment_mode"),
                instrument_bank_name=data.get("instrument_bank_name", ""),
                instrument_no=data.get("instrument_no", ""),
                instrument_date=data.get("instrument_date"),
                export_format=data.get("export_format") or TreasuryPaymentBatch.ExportFormat.GENERIC_CSV,
                user_id=request.user.id,
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})
        batch = TreasuryPaymentBatch.objects.prefetch_related("lines", "exports", "instruments", "status_logs").get(pk=batch.pk)
        return Response({"message": "Treasury payment batch created.", "data": TreasuryPaymentBatchDetailSerializer(batch).data}, status=201)


class TreasuryPaymentBatchRetrieveAPIView(ScopedEntitlementMixin, TreasuryPermissionMixin, generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TreasuryPaymentBatchDetailSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get_queryset(self):
        return TreasuryPaymentBatch.objects.select_related("entity", "entityfinid", "subentity").prefetch_related("lines", "exports", "instruments", "status_logs")

    def get_object(self):
        batch = super().get_object()
        self.enforce_scope(self.request, entity_id=batch.entity_id, entityfinid_id=batch.entityfinid_id, subentity_id=batch.subentity_id)
        self.require_any_permission(self.request, batch.entity_id, VIEW_PERMISSION_CODES)
        return batch


class TreasuryVendorPayableCandidateListAPIView(ScopedEntitlementMixin, TreasuryPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get(self, request):
        entity_id = _parse_int(request.query_params.get("entity"), "entity")
        entityfinid_id = _parse_int(request.query_params.get("entityfinid"), "entityfinid")
        subentity_id = _parse_int(request.query_params.get("subentity"), "subentity", required=False)
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        self.require_any_permission(request, entity_id, VIEW_PERMISSION_CODES)
        qs = TreasuryPaymentBatchService.list_vendor_payable_candidates(
            entity_id=entity_id,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
        )
        return Response(TreasuryVendorPayableCandidateSerializer(qs, many=True).data)


class TreasuryPaymentInstrumentListAPIView(ScopedEntitlementMixin, TreasuryPermissionMixin, generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TreasuryPaymentInstrumentSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get_queryset(self):
        entity_id = _parse_int(self.request.query_params.get("entity"), "entity")
        entityfinid_id = _parse_int(self.request.query_params.get("entityfinid"), "entityfinid", required=False)
        subentity_id = _parse_int(self.request.query_params.get("subentity"), "subentity", required=False)
        self.enforce_scope(self.request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        self.require_any_permission(self.request, entity_id, VIEW_PERMISSION_CODES)
        qs = (
            TreasuryPaymentInstrument.objects
            .select_related(
                "batch",
                "batch__entity",
                "batch__entityfinid",
                "batch__subentity",
                "source_account",
                "payment_mode",
                "cheque_leaf",
                "cheque_leaf__cheque_book",
                "reconciliation_match",
                "reconciled_bank_line",
            )
            .prefetch_related("batch__lines")
            .filter(batch__entity_id=entity_id)
        )
        if entityfinid_id:
            qs = qs.filter(batch__entityfinid_id=entityfinid_id)
        if subentity_id:
            qs = qs.filter(batch__subentity_id=subentity_id)
        status_value = self.request.query_params.get("status")
        if status_value:
            qs = qs.filter(status=status_value)
        instrument_type = self.request.query_params.get("instrument_type")
        if instrument_type:
            qs = qs.filter(instrument_type=instrument_type)
        payment_mode_id = _parse_int(self.request.query_params.get("payment_mode"), "payment_mode", required=False)
        if payment_mode_id:
            qs = qs.filter(payment_mode_id=payment_mode_id)
        source_account_id = _parse_int(self.request.query_params.get("source_account"), "source_account", required=False)
        if source_account_id:
            qs = qs.filter(source_account_id=source_account_id)
        date_from = self.request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(instrument_date__gte=date_from)
        date_to = self.request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(instrument_date__lte=date_to)
        search = (self.request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                models.Q(reference_no__icontains=search)
                | models.Q(instrument_no__icontains=search)
                | models.Q(bank_name__icontains=search)
                | models.Q(batch__batch_number__icontains=search)
                | models.Q(batch__batch_name__icontains=search)
                | models.Q(batch__lines__party_name__icontains=search)
                | models.Q(batch__lines__source_doc_number__icontains=search)
            ).distinct()
        return qs


class TreasuryChequeBookListCreateAPIView(ScopedEntitlementMixin, TreasuryPermissionMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get_serializer_class(self):
        if self.request.method == "POST":
            return TreasuryChequeBookCreateSerializer
        return TreasuryChequeBookSerializer

    def get_queryset(self):
        entity_id = _parse_int(self.request.query_params.get("entity"), "entity")
        entityfinid_id = _parse_int(self.request.query_params.get("entityfinid"), "entityfinid", required=False)
        subentity_id = _parse_int(self.request.query_params.get("subentity"), "subentity", required=False)
        self.enforce_scope(self.request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        self.require_any_permission(self.request, entity_id, VIEW_PERMISSION_CODES)
        qs = (
            TreasuryChequeBook.objects.select_related("entity", "entityfinid", "subentity", "bank_account")
            .annotate(
                available_leaf_count=models.Count("leaves", filter=models.Q(leaves__status=TreasuryChequeLeaf.Status.AVAILABLE)),
                reserved_leaf_count=models.Count("leaves", filter=models.Q(leaves__status=TreasuryChequeLeaf.Status.RESERVED)),
                used_leaf_count=models.Count(
                    "leaves",
                    filter=models.Q(leaves__status__in=[TreasuryChequeLeaf.Status.ISSUED, TreasuryChequeLeaf.Status.CLEARED]),
                ),
                cancelled_leaf_count=models.Count(
                    "leaves",
                    filter=models.Q(
                        leaves__status__in=[
                            TreasuryChequeLeaf.Status.CANCELLED,
                            TreasuryChequeLeaf.Status.BOUNCED,
                            TreasuryChequeLeaf.Status.STALE,
                            TreasuryChequeLeaf.Status.REISSUED,
                        ]
                    ),
                ),
            )
            .filter(entity_id=entity_id)
        )
        if entityfinid_id:
            qs = qs.filter(entityfinid_id=entityfinid_id)
        if subentity_id:
            qs = qs.filter(subentity_id=subentity_id)
        bank_account_id = _parse_int(self.request.query_params.get("bank_account"), "bank_account", required=False)
        if bank_account_id:
            qs = qs.filter(bank_account_id=bank_account_id)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        entity_id = data["entity"]
        entityfinid_id = data.get("entityfinid")
        subentity_id = data.get("subentity")
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        self.require_any_permission(request, entity_id, SETUP_PERMISSION_CODES)
        try:
            book = TreasuryPaymentBatchService.create_cheque_book(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                bank_account_id=data["bank_account"],
                book_number=data["book_number"],
                start_leaf=data["start_leaf"],
                end_leaf=data["end_leaf"],
                issued_on=data.get("issued_on"),
                remarks=data.get("remarks", ""),
                user_id=request.user.id,
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})
        book = (
            TreasuryChequeBook.objects.select_related("entity", "entityfinid", "subentity", "bank_account")
            .annotate(
                available_leaf_count=models.Count("leaves", filter=models.Q(leaves__status=TreasuryChequeLeaf.Status.AVAILABLE)),
                reserved_leaf_count=models.Count("leaves", filter=models.Q(leaves__status=TreasuryChequeLeaf.Status.RESERVED)),
                used_leaf_count=models.Count(
                    "leaves",
                    filter=models.Q(leaves__status__in=[TreasuryChequeLeaf.Status.ISSUED, TreasuryChequeLeaf.Status.CLEARED]),
                ),
                cancelled_leaf_count=models.Count(
                    "leaves",
                    filter=models.Q(
                        leaves__status__in=[
                            TreasuryChequeLeaf.Status.CANCELLED,
                            TreasuryChequeLeaf.Status.BOUNCED,
                            TreasuryChequeLeaf.Status.STALE,
                            TreasuryChequeLeaf.Status.REISSUED,
                        ]
                    ),
                ),
            )
            .get(pk=book.pk)
        )
        return Response({"message": "Cheque book created.", "data": TreasuryChequeBookSerializer(book).data}, status=201)


class TreasuryChequeLeafListAPIView(ScopedEntitlementMixin, TreasuryPermissionMixin, generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TreasuryChequeLeafSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get_queryset(self):
        entity_id = _parse_int(self.request.query_params.get("entity"), "entity")
        self.enforce_scope(self.request, entity_id=entity_id)
        self.require_any_permission(self.request, entity_id, VIEW_PERMISSION_CODES)
        qs = TreasuryChequeLeaf.objects.select_related("cheque_book", "bank_account").filter(entity_id=entity_id)
        bank_account_id = _parse_int(self.request.query_params.get("bank_account"), "bank_account", required=False)
        if bank_account_id:
            qs = qs.filter(bank_account_id=bank_account_id)
        cheque_book_id = self.request.query_params.get("cheque_book")
        if cheque_book_id:
            qs = qs.filter(cheque_book_id=cheque_book_id)
        status_value = self.request.query_params.get("status")
        if status_value:
            qs = qs.filter(status=status_value)
        return qs


class TreasuryPaymentInstrumentActionAPIView(ScopedEntitlementMixin, TreasuryPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TreasuryPaymentInstrumentActionSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request, pk, action):
        instrument = get_object_or_404(
            TreasuryPaymentInstrument.objects
            .select_related("batch", "batch__entity", "batch__entityfinid", "batch__subentity", "source_account", "payment_mode", "cheque_leaf")
            .prefetch_related("batch__lines"),
            pk=pk,
        )
        batch = instrument.batch
        self.enforce_scope(request, entity_id=batch.entity_id, entityfinid_id=batch.entityfinid_id, subentity_id=batch.subentity_id)
        self.require_any_permission(request, batch.entity_id, INSTRUMENT_STATUS_PERMISSION_CODES)
        serializer = self.serializer_class(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            instrument = TreasuryPaymentBatchService.transition_instrument(
                instrument=instrument,
                action=action,
                user_id=request.user.id,
                reference_no=data.get("reference_no", ""),
                instrument_no=data.get("instrument_no", ""),
                instrument_date=data.get("instrument_date"),
                bank_name=data.get("bank_name", ""),
                cheque_leaf_id=data.get("cheque_leaf"),
                reason=data.get("reason", ""),
                comment=data.get("comment", ""),
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})
        instrument = (
            TreasuryPaymentInstrument.objects
            .select_related("batch", "batch__entity", "batch__entityfinid", "batch__subentity", "source_account", "payment_mode", "cheque_leaf", "cheque_leaf__cheque_book")
            .prefetch_related("batch__lines")
            .get(pk=instrument.pk)
        )
        return Response({"message": "Treasury payment instrument updated.", "data": TreasuryPaymentInstrumentSerializer(instrument).data})


class TreasuryCashMovementListCreateAPIView(ScopedEntitlementMixin, TreasuryPermissionMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def get_serializer_class(self):
        if self.request.method == "POST":
            return TreasuryCashMovementCreateSerializer
        return TreasuryCashMovementSerializer

    def get_queryset(self):
        entity_id = _parse_int(self.request.query_params.get("entity"), "entity")
        entityfinid_id = _parse_int(self.request.query_params.get("entityfinid"), "entityfinid", required=False)
        subentity_id = _parse_int(self.request.query_params.get("subentity"), "subentity", required=False)
        self.enforce_scope(self.request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        self.require_any_permission(self.request, entity_id, VIEW_PERMISSION_CODES)
        qs = (
            TreasuryCashMovement.objects
            .select_related("entity", "entityfinid", "subentity", "source_account", "destination_account", "payment_mode", "voucher")
            .filter(entity_id=entity_id)
        )
        if entityfinid_id:
            qs = qs.filter(entityfinid_id=entityfinid_id)
        if subentity_id:
            qs = qs.filter(subentity_id=subentity_id)
        movement_type = self.request.query_params.get("movement_type")
        if movement_type:
            qs = qs.filter(movement_type=movement_type)
        status_value = self.request.query_params.get("status")
        if status_value:
            qs = qs.filter(status=status_value)
        account_id = _parse_int(self.request.query_params.get("account"), "account", required=False)
        if account_id:
            qs = qs.filter(models.Q(source_account_id=account_id) | models.Q(destination_account_id=account_id))
        date_from = self.request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(movement_date__gte=date_from)
        date_to = self.request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(movement_date__lte=date_to)
        search = (self.request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                models.Q(movement_number__icontains=search)
                | models.Q(reference_no__icontains=search)
                | models.Q(instrument_no__icontains=search)
                | models.Q(bank_name__icontains=search)
                | models.Q(narration__icontains=search)
                | models.Q(voucher__voucher_code__icontains=search)
                | models.Q(source_account__accountname__icontains=search)
                | models.Q(destination_account__accountname__icontains=search)
            )
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        entity_id = data["entity"]
        entityfinid_id = data["entityfinid"]
        subentity_id = data.get("subentity")
        self.enforce_scope(request, entity_id=entity_id, entityfinid_id=entityfinid_id, subentity_id=subentity_id)
        self.require_any_permission(request, entity_id, CASH_MOVEMENT_PERMISSION_CODES)
        try:
            movement = TreasuryPaymentBatchService.create_cash_movement(
                entity_id=entity_id,
                entityfinid_id=entityfinid_id,
                subentity_id=subentity_id,
                movement_type=data["movement_type"],
                movement_date=data.get("movement_date"),
                source_account_id=data["source_account"],
                destination_account_id=data["destination_account"],
                payment_mode_id=data.get("payment_mode"),
                amount=data["amount"],
                reference_no=data.get("reference_no", ""),
                instrument_no=data.get("instrument_no", ""),
                instrument_date=data.get("instrument_date"),
                bank_name=data.get("bank_name", ""),
                narration=data.get("narration", ""),
                user_id=request.user.id,
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})
        movement = (
            TreasuryCashMovement.objects
            .select_related("entity", "entityfinid", "subentity", "source_account", "destination_account", "payment_mode", "voucher")
            .get(pk=movement.pk)
        )
        return Response({"message": "Treasury cash movement posted.", "data": TreasuryCashMovementSerializer(movement).data}, status=201)


class TreasuryCashMovementCancelAPIView(ScopedEntitlementMixin, TreasuryPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TreasuryCashMovementCancelSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def post(self, request, pk):
        movement = get_object_or_404(TreasuryCashMovement.objects.select_related("voucher"), pk=pk)
        self.enforce_scope(request, entity_id=movement.entity_id, entityfinid_id=movement.entityfinid_id, subentity_id=movement.subentity_id)
        self.require_any_permission(request, movement.entity_id, CASH_MOVEMENT_PERMISSION_CODES)
        serializer = self.serializer_class(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            movement = TreasuryPaymentBatchService.cancel_cash_movement(
                movement=movement,
                user_id=request.user.id,
                reason=serializer.validated_data.get("reason", ""),
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})
        movement = TreasuryCashMovement.objects.select_related("source_account", "destination_account", "payment_mode", "voucher").get(pk=movement.pk)
        return Response({"message": "Treasury cash movement cancelled.", "data": TreasuryCashMovementSerializer(movement).data})


class _TreasuryPaymentBatchActionAPIView(ScopedEntitlementMixin, TreasuryPermissionMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TreasuryPaymentBatchActionSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_FINANCIAL
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    permission_codes: tuple[str, ...] = VIEW_PERMISSION_CODES

    def get_batch(self, request, pk):
        batch = TreasuryPaymentBatch.objects.get(pk=pk)
        self.enforce_scope(request, entity_id=batch.entity_id, entityfinid_id=batch.entityfinid_id, subentity_id=batch.subentity_id)
        self.require_any_permission(request, batch.entity_id, self.permission_codes)
        return batch


class TreasuryPaymentBatchValidateAPIView(_TreasuryPaymentBatchActionAPIView):
    permission_codes = VALIDATE_PERMISSION_CODES

    def post(self, request, pk):
        serializer = self.serializer_class(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            batch = TreasuryPaymentBatchService.validate_batch(
                batch=self.get_batch(request, pk),
                user_id=request.user.id,
                comment=serializer.validated_data.get("comment", ""),
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response({"message": "Treasury payment batch validated.", "data": TreasuryPaymentBatchDetailSerializer(batch).data})


class TreasuryPaymentBatchApproveAPIView(_TreasuryPaymentBatchActionAPIView):
    permission_codes = APPROVE_PERMISSION_CODES

    def post(self, request, pk):
        serializer = self.serializer_class(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            batch = TreasuryPaymentBatchService.approve_batch(
                batch=self.get_batch(request, pk),
                user_id=request.user.id,
                comment=serializer.validated_data.get("comment", ""),
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response({"message": "Treasury payment batch approved.", "data": TreasuryPaymentBatchDetailSerializer(batch).data})


class TreasuryPaymentBatchExportAPIView(_TreasuryPaymentBatchActionAPIView):
    permission_codes = EXPORT_PERMISSION_CODES

    def post(self, request, pk):
        serializer = self.serializer_class(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            result = TreasuryPaymentBatchService.export_batch(
                batch=self.get_batch(request, pk),
                user_id=request.user.id,
                export_format=serializer.validated_data.get("export_format"),
                comment=serializer.validated_data.get("comment", ""),
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})
        response = HttpResponse(result.file_content, content_type=result.content_type)
        response["Content-Disposition"] = f'attachment; filename="{result.file_name}"'
        response["X-Treasury-Payment-Batch-Id"] = str(result.batch.id)
        return response


class TreasuryPaymentBatchMarkPaidAPIView(_TreasuryPaymentBatchActionAPIView):
    permission_codes = STATUS_PERMISSION_CODES

    def post(self, request, pk):
        serializer = self.serializer_class(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            batch = TreasuryPaymentBatchService.mark_paid(
                batch=self.get_batch(request, pk),
                user_id=request.user.id,
                payment_reference=serializer.validated_data.get("payment_reference", ""),
                comment=serializer.validated_data.get("comment", ""),
                paid_from_id=serializer.validated_data.get("paid_from"),
                payment_mode_id=serializer.validated_data.get("payment_mode"),
                instrument_bank_name=serializer.validated_data.get("instrument_bank_name", ""),
                instrument_no=serializer.validated_data.get("instrument_no", ""),
                instrument_date=serializer.validated_data.get("instrument_date"),
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response({"message": "Treasury payment batch marked paid.", "data": TreasuryPaymentBatchDetailSerializer(batch).data})


class TreasuryPaymentBatchMarkFailedAPIView(_TreasuryPaymentBatchActionAPIView):
    permission_codes = STATUS_PERMISSION_CODES

    def post(self, request, pk):
        serializer = self.serializer_class(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            batch = TreasuryPaymentBatchService.mark_failed(
                batch=self.get_batch(request, pk),
                user_id=request.user.id,
                failure_reason=serializer.validated_data.get("failure_reason", ""),
                comment=serializer.validated_data.get("comment", ""),
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response({"message": "Treasury payment batch marked failed.", "data": TreasuryPaymentBatchDetailSerializer(batch).data})


class TreasuryPaymentBatchCancelAPIView(_TreasuryPaymentBatchActionAPIView):
    permission_codes = STATUS_PERMISSION_CODES

    def post(self, request, pk):
        serializer = self.serializer_class(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            batch = TreasuryPaymentBatchService.cancel_batch(
                batch=self.get_batch(request, pk),
                user_id=request.user.id,
                cancellation_reason=serializer.validated_data.get("cancellation_reason", ""),
                comment=serializer.validated_data.get("comment", ""),
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response({"message": "Treasury payment batch cancelled.", "data": TreasuryPaymentBatchDetailSerializer(batch).data})
