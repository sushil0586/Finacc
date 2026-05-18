from __future__ import annotations

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from payroll.models import PayrollRun, Payslip
from payroll.serializers import (
    PayrollRunActionSerializer,
    PayrollRunCreateSerializer,
    PayrollRunDetailSerializer,
    PayrollRunListSerializer,
    PayrollRunSummarySerializer,
    PayslipSerializer,
)
from payroll.services import PayrollApprovalPolicyService, PayrollPermissionService, PayrollRunService
from payroll.services.payroll_export_service import PayrollExportService
from payroll.services.payroll_reversal_service import PayrollReversalService
from payroll.services.payroll_run_hardening_service import PayrollRunHardeningService
from payroll.views.scoped import PayrollScopedAPIView


def _raise_value_error(err: ValueError):
    payload = err.args[0] if err.args else str(err)
    if isinstance(payload, dict):
        raise ValidationError(payload)
    raise ValidationError({"detail": str(payload)})


def _assert_action_permission(request, action: str, *, entity_id: int | None = None) -> None:
    try:
        PayrollPermissionService.assert_action_access(user=request.user, action=action, entity_id=entity_id)
    except PermissionError as err:
        raise PermissionDenied(detail=str(err))


def _assert_approval_policy_permission(request, *, run: PayrollRun) -> None:
    allowed, reason = PayrollApprovalPolicyService.can_user_approve_run(user=request.user, run=run)
    if allowed:
        return
    raise PermissionDenied(detail=reason or "Approval policy denied this payroll approval action.")


def _assert_submit_policy_permission(request, *, run: PayrollRun) -> None:
    allowed, reason = PayrollApprovalPolicyService.can_user_submit_run(user=request.user, run=run)
    if allowed:
        return
    raise PermissionDenied(detail=reason or "Approval routing is incomplete for this payroll run.")


def _assert_payment_handoff_policy_permission(request, *, run: PayrollRun) -> None:
    allowed, reason = PayrollApprovalPolicyService.can_user_handoff_payment_run(user=request.user, run=run)
    if allowed:
        return
    raise PermissionDenied(detail=reason or "Payment handoff policy denied this payroll action.")


def _assert_posting_policy_permission(request, *, run: PayrollRun) -> None:
    allowed, reason = PayrollApprovalPolicyService.can_user_post_run(user=request.user, run=run)
    if allowed:
        return
    raise PermissionDenied(detail=reason or "Posting policy denied this payroll action.")


class PayrollRunListCreateAPIView(PayrollScopedAPIView, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["entity", "entityfinid", "subentity", "payroll_period", "status", "run_type", "payment_status"]

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_from_query(self.request, require_entity=True)
        qs = PayrollRun.objects.select_related("entity", "entityfinid", "subentity", "payroll_period").filter(entity_id=entity_id)
        if entityfinid_id is not None:
            qs = qs.filter(entityfinid_id=entityfinid_id)
        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        awaiting_approval = self.request.query_params.get("awaiting_approval")
        if awaiting_approval and str(awaiting_approval).lower() in {"1", "true", "yes"}:
            qs = qs.filter(
                status=PayrollRun.Status.CALCULATED,
                submitted_at__isnull=False,
                approved_at__isnull=True,
            )
        return qs.order_by("-posting_date", "-id")

    def get_serializer_class(self):
        if self.request.method.upper() == "POST":
            return PayrollRunCreateSerializer
        return PayrollRunListSerializer

    def list(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_entity_permission(request, entity_id=entity_id, permission_codes={"payroll.run.view"}, label="view payroll runs")
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=data["entity"].id,
            entityfinid_id=data["entityfinid"].id,
            subentity_id=getattr(data.get("subentity"), "id", None),
        )
        _assert_action_permission(request, "create", entity_id=data["entity"].id)
        try:
            result = PayrollRunService.create_run(
                entity_id=data["entity"].id,
                entityfinid_id=data["entityfinid"].id,
                subentity_id=getattr(data.get("subentity"), "id", None),
                payroll_period_id=data["payroll_period"].id,
                run_type=data["run_type"],
                posting_date=data.get("posting_date"),
                payout_date=data.get("payout_date"),
                created_by_id=request.user.id,
            )
        except ValueError as err:
            _raise_value_error(err)
        return Response(
            {
                "message": result.message,
                "data": PayrollRunDetailSerializer(result.run).data,
            },
            status=201,
        )


class PayrollRunRetrieveAPIView(PayrollScopedAPIView, generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PayrollRunDetailSerializer

    def get_queryset(self):
        return PayrollRun.objects.select_related(
            "entity",
            "entityfinid",
            "subentity",
            "payroll_period",
            "created_by",
            "submitted_by",
            "approved_by",
            "locked_by",
            "posted_by",
            "reversed_by",
            "reversed_run",
            "ledger_policy_version",
        ).prefetch_related(
            "action_logs__acted_by",
            "reversal_runs",
            "employee_runs__contract_payroll_profile__hrms_contract__employee",
            "employee_runs__salary_structure",
            "employee_runs__salary_structure_version",
            "employee_runs__components",
            "employee_runs__components__component",
            "employee_runs__payslip",
        )

    def get_object(self):
        obj = super().get_object()
        self._enforce_object_scope(self.request, obj)
        self._assert_entity_permission(self.request, entity_id=obj.entity_id, permission_codes={"payroll.run.view"}, label="view payroll runs")
        return obj


class PayrollRunCalculateAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        serializer = PayrollRunActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        run = PayrollRun.objects.select_related("payroll_period").get(pk=pk)
        self._enforce_object_scope(request, run)
        _assert_action_permission(request, "calculate", entity_id=run.entity_id)
        try:
            result = PayrollRunService.calculate_run(run, force=serializer.validated_data["force"])
        except ValueError as err:
            _raise_value_error(err)
        readiness_summary = (result.run.config_snapshot or {}).get("contract_readiness")
        response_payload = {"message": result.message, "data": PayrollRunDetailSerializer(result.run).data}
        if readiness_summary:
            response_payload["readiness_summary"] = {
                "ready_count": readiness_summary.get("ready_count", 0),
                "warning_count": readiness_summary.get("warning_count", 0),
                "blocked_count": readiness_summary.get("blocked_count", 0),
                "blocked_contracts": readiness_summary.get("blocked_contracts", []),
            }
        return Response(response_payload)


class PayrollRunApproveAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        serializer = PayrollRunActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        run = PayrollRun.objects.get(pk=pk)
        self._enforce_object_scope(request, run)
        _assert_action_permission(request, "approve", entity_id=run.entity_id)
        _assert_approval_policy_permission(request, run=run)
        try:
            result = PayrollRunService.approve_run(
                run,
                approved_by_id=request.user.id,
                note=serializer.validated_data.get("note", ""),
            )
        except ValueError as err:
            _raise_value_error(err)
        return Response({"message": result.message, "data": PayrollRunDetailSerializer(result.run).data})


class PayrollRunSubmitAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        serializer = PayrollRunActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        run = PayrollRun.objects.get(pk=pk)
        self._enforce_object_scope(request, run)
        _assert_action_permission(request, "submit", entity_id=run.entity_id)
        _assert_submit_policy_permission(request, run=run)
        try:
            result = PayrollRunService.submit_run(
                run,
                submitted_by_id=request.user.id,
                note=serializer.validated_data.get("note", ""),
                reason_code=serializer.validated_data.get("reason_code", ""),
            )
        except ValueError as err:
            _raise_value_error(err)
        return Response({"message": result.message, "data": PayrollRunDetailSerializer(result.run).data})


class PayrollRunPostAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        run = PayrollRun.objects.select_related("payroll_period").get(pk=pk)
        self._enforce_object_scope(request, run)
        _assert_action_permission(request, "post", entity_id=run.entity_id)
        _assert_posting_policy_permission(request, run=run)
        try:
            result = PayrollRunService.post_run(run, posted_by_id=request.user.id)
        except ValueError as err:
            _raise_value_error(err)
        return Response({"message": result.message, "data": PayrollRunDetailSerializer(result.run).data})


class PayrollRunPaymentHandoffAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        serializer = PayrollRunActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        run = PayrollRun.objects.get(pk=pk)
        self._enforce_object_scope(request, run)
        _assert_action_permission(request, "payment_handoff", entity_id=run.entity_id)
        _assert_payment_handoff_policy_permission(request, run=run)
        try:
            run = PayrollRunHardeningService.handoff_payment(
                run,
                user_id=request.user.id,
                batch_ref=serializer.validated_data.get("payment_batch_ref", ""),
                payload={"note": serializer.validated_data.get("note", "")},
            )
        except ValueError as err:
            _raise_value_error(err)
        return Response({"message": "Payroll run handed off to payments.", "data": PayrollRunDetailSerializer(run).data})


class PayrollRunPaymentReconcileAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        serializer = PayrollRunActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        run = PayrollRun.objects.get(pk=pk)
        self._enforce_object_scope(request, run)
        _assert_action_permission(request, "payment_reconcile", entity_id=run.entity_id)
        payment_status = serializer.validated_data.get("payment_status")
        if not payment_status:
            raise ValidationError({"payment_status": "This field is required."})
        try:
            run = PayrollRunHardeningService.reconcile_payment(
                run,
                user_id=request.user.id,
                payment_status=payment_status,
                comment=serializer.validated_data.get("note", ""),
            )
        except ValueError as err:
            _raise_value_error(err)
        return Response({"message": "Payroll payment status updated.", "data": PayrollRunDetailSerializer(run).data})


class PayrollRunReverseAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        serializer = PayrollRunActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        run = PayrollRun.objects.get(pk=pk)
        self._enforce_object_scope(request, run)
        _assert_action_permission(request, "reverse", entity_id=run.entity_id)
        try:
            reversal = PayrollReversalService.reverse_run(
                run,
                user_id=request.user.id,
                reason=serializer.validated_data.get("note", "") or "Payroll reversal",
            )
        except ValueError as err:
            _raise_value_error(err)
        return Response({"message": "Payroll run reversed.", "data": PayrollRunDetailSerializer(reversal).data})


class PayrollRunSummaryAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        run = (
            PayrollRun.objects.select_related(
                "entity",
                "entityfinid",
                "subentity",
                "payroll_period",
                "created_by",
                "submitted_by",
                "approved_by",
                "posted_by",
                "reversed_by",
                "reversed_run",
                "ledger_policy_version",
            )
            .prefetch_related(
                "action_logs__acted_by",
                "reversal_runs",
                "employee_runs__contract_payroll_profile__hrms_contract__employee",
                "employee_runs__salary_structure",
                "employee_runs__salary_structure_version",
                "employee_runs__components",
                "employee_runs__components__component",
                "employee_runs__payslip",
            )
            .get(pk=pk)
        )
        self._enforce_object_scope(request, run)
        self._assert_entity_permission(request, entity_id=run.entity_id, permission_codes={"payroll.run.view"}, label="view payroll runs")
        summary = PayrollRunService.summary(run)
        return Response(PayrollRunSummarySerializer(summary).data)


class PayrollRunPayslipAPIView(PayrollScopedAPIView, generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PayslipSerializer
    lookup_url_kwarg = "employee_run_id"

    def get_queryset(self):
        return Payslip.objects.select_related(
            "payroll_run_employee",
            "payroll_run_employee__contract_payroll_profile__hrms_contract__employee",
            "payroll_run_employee__salary_structure",
        ).prefetch_related(
            "payroll_run_employee__components",
        ).filter(payroll_run_employee__payroll_run_id=self.kwargs["pk"])

    def get_object(self):
        obj = super().get_object()
        run = obj.payroll_run_employee.payroll_run
        self._enforce_object_scope(self.request, run)
        self._assert_entity_permission(self.request, entity_id=run.entity_id, permission_codes={"payroll.run.view"}, label="view payroll runs")
        return obj


class PayrollRunPayslipPdfAPIView(PayrollScopedAPIView, generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    lookup_url_kwarg = "employee_run_id"

    def get_queryset(self):
        return Payslip.objects.select_related(
            "payroll_run_employee__payroll_run__payroll_period",
            "payroll_run_employee__contract_payroll_profile__hrms_contract__employee",
        ).prefetch_related("payroll_run_employee__components__component").filter(
            payroll_run_employee__payroll_run_id=self.kwargs["pk"]
        )

    def get(self, request, *args, **kwargs):
        payslip = self.get_object()
        run = payslip.payroll_run_employee.payroll_run
        self._enforce_object_scope(request, run)
        self._assert_entity_permission(request, entity_id=run.entity_id, permission_codes={"payroll.run.view"}, label="view payroll runs")
        generated_by = getattr(request.user, "email", None) or getattr(request.user, "username", None) or f"user:{request.user.pk}"
        return PayrollExportService.export_payslip_pdf(payslip=payslip, generated_by=generated_by)
