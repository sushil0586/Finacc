from __future__ import annotations

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, permissions
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from payroll.models import PayrollRun, Payslip
from payroll.serializers import (
    PayrollRunActionSerializer,
    PayrollRunCreateSerializer,
    PayrollRunDetailSerializer,
    PayrollRunListSerializer,
    PayrollRunSummarySerializer,
    PayslipSerializer,
)
from payroll.services import PayrollRunService
from payroll.services.payroll_reversal_service import PayrollReversalService
from payroll.services.payroll_run_hardening_service import PayrollRunHardeningService


def _raise_value_error(err: ValueError):
    payload = err.args[0] if err.args else str(err)
    if isinstance(payload, dict):
        raise ValidationError(payload)
    raise ValidationError({"detail": str(payload)})


class PayrollRunListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["entity", "entityfinid", "subentity", "payroll_period", "status", "run_type"]

    def get_queryset(self):
        qs = PayrollRun.objects.select_related("entity", "entityfinid", "subentity", "payroll_period")
        entity = self.request.query_params.get("entity")
        entityfinid = self.request.query_params.get("entityfinid")
        if entity:
            qs = qs.filter(entity_id=entity)
        if entityfinid:
            qs = qs.filter(entityfinid_id=entityfinid)
        return qs.order_by("-posting_date", "-id")

    def get_serializer_class(self):
        if self.request.method.upper() == "POST":
            return PayrollRunCreateSerializer
        return PayrollRunListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
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


class PayrollRunRetrieveAPIView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PayrollRunDetailSerializer

    def get_queryset(self):
        return PayrollRun.objects.select_related(
            "entity",
            "entityfinid",
            "subentity",
            "payroll_period",
            "created_by",
            "approved_by",
            "posted_by",
        ).prefetch_related("employee_runs__components")


class PayrollRunCalculateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        serializer = PayrollRunActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        run = PayrollRun.objects.select_related("payroll_period").get(pk=pk)
        try:
            result = PayrollRunService.calculate_run(run, force=serializer.validated_data["force"])
        except ValueError as err:
            _raise_value_error(err)
        return Response({"message": result.message, "data": PayrollRunDetailSerializer(result.run).data})


class PayrollRunApproveAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        serializer = PayrollRunActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        run = PayrollRun.objects.get(pk=pk)
        try:
            result = PayrollRunService.approve_run(
                run,
                approved_by_id=request.user.id,
                note=serializer.validated_data.get("note", ""),
            )
        except ValueError as err:
            _raise_value_error(err)
        return Response({"message": result.message, "data": PayrollRunDetailSerializer(result.run).data})


class PayrollRunSubmitAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        serializer = PayrollRunActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        run = PayrollRun.objects.get(pk=pk)
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


class PayrollRunPostAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        run = PayrollRun.objects.select_related("payroll_period").get(pk=pk)
        try:
            result = PayrollRunService.post_run(run, posted_by_id=request.user.id)
        except ValueError as err:
            _raise_value_error(err)
        return Response({"message": result.message, "data": PayrollRunDetailSerializer(result.run).data})


class PayrollRunPaymentHandoffAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        serializer = PayrollRunActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        run = PayrollRun.objects.get(pk=pk)
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


class PayrollRunPaymentReconcileAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        serializer = PayrollRunActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        run = PayrollRun.objects.get(pk=pk)
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


class PayrollRunReverseAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        serializer = PayrollRunActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        run = PayrollRun.objects.get(pk=pk)
        try:
            reversal = PayrollReversalService.reverse_run(
                run,
                user_id=request.user.id,
                reason=serializer.validated_data.get("note", "") or "Payroll reversal",
            )
        except ValueError as err:
            _raise_value_error(err)
        return Response({"message": "Payroll run reversed.", "data": PayrollRunDetailSerializer(reversal).data})


class PayrollRunSummaryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        run = PayrollRun.objects.get(pk=pk)
        summary = PayrollRunService.summary(run)
        return Response(PayrollRunSummarySerializer(summary).data)


class PayrollRunPayslipAPIView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PayslipSerializer
    lookup_url_kwarg = "employee_run_id"

    def get_queryset(self):
        return Payslip.objects.select_related(
            "payroll_run_employee",
            "payroll_run_employee__employee_profile",
        ).filter(payroll_run_employee__payroll_run_id=self.kwargs["pk"])
