from __future__ import annotations

from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from payroll.models import FnFSettlement, PayrollRun
from payroll.serializers import PayrollPostingPreviewSerializer, PayrollPostingStatusSerializer
from payroll.services import PayrollPostingService
from payroll.views.scoped import PayrollScopedAPIView


def _sanitize_preview_payload(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if key != "posting"}


def _raise_value_error(err: ValueError):
    payload = err.args[0] if err.args else str(err)
    if isinstance(payload, dict):
        raise ValidationError(payload)
    raise ValidationError({"detail": str(payload)})


class PayrollRunPostingPreviewAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        run = PayrollRun.objects.select_related("payroll_period", "ledger_policy_version").get(pk=pk)
        self._enforce_object_scope(request, run)
        self._assert_entity_permission(request, entity_id=run.entity_id, permission_codes={"payroll.run.view"}, label="view payroll posting preview")
        try:
            payload = _sanitize_preview_payload(PayrollPostingService.preview_run(run))
        except ValueError as err:
            _raise_value_error(err)
        serializer = PayrollPostingPreviewSerializer(payload)
        return Response(serializer.data)


class PayrollRunPostingValidateAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        run = PayrollRun.objects.select_related("payroll_period", "ledger_policy_version").get(pk=pk)
        self._enforce_object_scope(request, run)
        self._assert_entity_permission(request, entity_id=run.entity_id, permission_codes={"payroll.run.manage"}, label="validate payroll posting")
        try:
            payload = _sanitize_preview_payload(PayrollPostingService.validate_run(run))
        except ValueError as err:
            _raise_value_error(err)
        serializer = PayrollPostingPreviewSerializer(payload)
        return Response(serializer.data)


class PayrollRunPostingStatusAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        run = PayrollRun.objects.select_related("payroll_period", "ledger_policy_version").get(pk=pk)
        self._enforce_object_scope(request, run)
        self._assert_entity_permission(request, entity_id=run.entity_id, permission_codes={"payroll.run.view"}, label="view payroll posting status")
        try:
            payload = PayrollPostingService.posting_status_for_run(run)
        except ValueError as err:
            _raise_value_error(err)
        serializer = PayrollPostingStatusSerializer(payload)
        return Response(serializer.data)


class FnFSettlementPostingPreviewAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        settlement = FnFSettlement.objects.select_related(
            "entity",
            "entityfinid",
            "subentity",
            "contract_payroll_profile__hrms_contract__employee",
        ).prefetch_related("components__component").get(pk=pk)
        self._enforce_object_scope(request, settlement)
        self._assert_entity_permission(request, entity_id=settlement.entity_id, permission_codes={"payroll.run.view", "payroll.run.manage"}, label="view FnF posting preview")
        try:
            payload = _sanitize_preview_payload(PayrollPostingService.preview_fnf(settlement))
        except ValueError as err:
            _raise_value_error(err)
        serializer = PayrollPostingPreviewSerializer(payload)
        return Response(serializer.data)


class FnFSettlementPostingValidateAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        settlement = FnFSettlement.objects.select_related(
            "entity",
            "entityfinid",
            "subentity",
            "contract_payroll_profile__hrms_contract__employee",
        ).prefetch_related("components__component").get(pk=pk)
        self._enforce_object_scope(request, settlement)
        self._assert_entity_permission(request, entity_id=settlement.entity_id, permission_codes={"payroll.run.manage"}, label="validate FnF posting")
        try:
            payload = _sanitize_preview_payload(PayrollPostingService.validate_fnf(settlement))
        except ValueError as err:
            _raise_value_error(err)
        serializer = PayrollPostingPreviewSerializer(payload)
        return Response(serializer.data)


class FnFSettlementPostingStatusAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        settlement = FnFSettlement.objects.select_related("entity", "entityfinid", "subentity").get(pk=pk)
        self._enforce_object_scope(request, settlement)
        self._assert_entity_permission(request, entity_id=settlement.entity_id, permission_codes={"payroll.run.view", "payroll.run.manage"}, label="view FnF posting status")
        try:
            payload = PayrollPostingService.posting_status_for_fnf(settlement)
        except ValueError as err:
            _raise_value_error(err)
        serializer = PayrollPostingStatusSerializer(payload)
        return Response(serializer.data)
