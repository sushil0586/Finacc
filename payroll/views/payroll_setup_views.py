from __future__ import annotations

from django.db.models import Max, Q, Sum
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from payroll.models import PayrollAdjustment, PayrollComponent, PayrollEmployeeProfile, PayrollPeriod, PayrollRun, SalaryStructure
from payroll.serializers.payroll_setup_serializers import (
    PayrollAdjustmentSerializer,
    PayrollComponentSerializer,
    PayrollEmployeeProfileSerializer,
    PayrollPeriodSerializer,
    SalaryStructureSerializer,
)
from payroll.services import PayrollPermissionService, PayrollRolloutValidationService, PayrollSetupService


def _permission_denied(message: str):
    raise PermissionDenied(detail=message)


def _assert_access(request, *, groups: set[str], permissions_required: set[str], label: str) -> None:
    try:
        PayrollPermissionService.assert_named_access(
            user=request.user,
            groups=groups,
            permissions=permissions_required,
            label=label,
        )
    except PermissionError as err:
        _permission_denied(str(err))


class PayrollSetupQuerysetMixin:
    scope_fields = ("entity", "entityfinid", "subentity")

    def filter_scope(self, qs):
        for field in self.scope_fields:
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{f"{field}_id": value})
        return qs


class PayrollPeriodListCreateAPIView(PayrollSetupQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PayrollPeriodSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["entity", "entityfinid", "subentity", "status", "pay_frequency"]
    search_fields = ["code"]

    def get_queryset(self):
        qs = PayrollPeriod.objects.select_related("entity", "entityfinid", "subentity", "locked_by", "closed_by")
        return self.filter_scope(qs).order_by("-period_start", "-id")

    def get(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            permissions_required={"payroll.view_payrollperiod"},
            label="view payroll periods",
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_operator", "payroll_admin"},
            permissions_required={"payroll.add_payrollperiod"},
            label="create payroll periods",
        )
        return super().post(request, *args, **kwargs)


class PayrollPeriodRetrieveUpdateAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PayrollPeriodSerializer

    def get_queryset(self):
        return PayrollPeriod.objects.select_related("entity", "entityfinid", "subentity", "locked_by", "closed_by")

    def get(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            permissions_required={"payroll.view_payrollperiod"},
            label="view payroll periods",
        )
        return super().get(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_operator", "payroll_admin"},
            permissions_required={"payroll.change_payrollperiod"},
            label="edit payroll periods",
        )
        return super().patch(request, *args, **kwargs)


class PayrollPeriodActionAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    ACTION_LABELS = {"open": "opened", "close": "closed", "lock": "locked"}

    def post(self, request, pk: int, action: str):
        _assert_access(
            request,
            groups={"payroll_operator", "payroll_admin"},
            permissions_required={"payroll.change_payrollperiod"},
            label=f"{action} payroll periods",
        )
        period = PayrollPeriod.objects.select_related("locked_by", "closed_by").get(pk=pk)
        note = request.data.get("note", "") if isinstance(request.data, dict) else ""
        try:
            period = PayrollSetupService.transition_period(period=period, action=action, user=request.user, note=note)
        except Exception as err:
            raise ValidationError({"detail": str(err)})
        return Response(
            {
                "message": f"Payroll period {self.ACTION_LABELS.get(action, action)} successfully.",
                "data": PayrollPeriodSerializer(period).data,
            }
        )


class PayrollComponentListCreateAPIView(PayrollSetupQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PayrollComponentSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["entity", "component_type", "is_active", "is_statutory"]
    search_fields = ["code", "name", "description"]
    scope_fields = ("entity",)

    def get_queryset(self):
        return self.filter_scope(PayrollComponent.objects.select_related("entity")).order_by("default_sequence", "code")

    def get(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            permissions_required={"payroll.view_payrollcomponent"},
            label="view payroll components",
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_admin"},
            permissions_required={"payroll.add_payrollcomponent"},
            label="create payroll components",
        )
        return super().post(request, *args, **kwargs)


class PayrollComponentRetrieveUpdateAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PayrollComponentSerializer

    def get_queryset(self):
        return PayrollComponent.objects.select_related("entity")

    def get(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            permissions_required={"payroll.view_payrollcomponent"},
            label="view payroll components",
        )
        return super().get(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_admin"},
            permissions_required={"payroll.change_payrollcomponent"},
            label="edit payroll components",
        )
        return super().patch(request, *args, **kwargs)


class SalaryStructureListCreateAPIView(PayrollSetupQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SalaryStructureSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["entity", "entityfinid", "subentity", "status", "is_active", "is_template"]
    search_fields = ["code", "name", "notes"]

    def get_queryset(self):
        return self.filter_scope(
            SalaryStructure.objects.select_related("entity", "entityfinid", "subentity", "current_version").prefetch_related("current_version__lines")
        ).order_by("code")

    def get(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            permissions_required={"payroll.view_salarystructure"},
            label="view salary structures",
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_admin"},
            permissions_required={"payroll.add_salarystructure"},
            label="create salary structures",
        )
        return super().post(request, *args, **kwargs)


class SalaryStructureRetrieveUpdateAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SalaryStructureSerializer

    def get_queryset(self):
        return SalaryStructure.objects.select_related("entity", "entityfinid", "subentity", "current_version").prefetch_related("current_version__lines")

    def get(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            permissions_required={"payroll.view_salarystructure"},
            label="view salary structures",
        )
        return super().get(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_admin"},
            permissions_required={"payroll.change_salarystructure"},
            label="edit salary structures",
        )
        return super().patch(request, *args, **kwargs)


class PayrollProfileListCreateAPIView(PayrollSetupQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PayrollEmployeeProfileSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["entity", "entityfinid", "subentity", "status", "salary_structure", "pay_frequency"]
    search_fields = ["employee_code", "full_name", "work_email", "pan", "uan"]

    def get_queryset(self):
        return self.filter_scope(
            PayrollEmployeeProfile.objects.select_related(
                "entity", "entityfinid", "subentity", "employee_user", "salary_structure", "salary_structure_version", "payment_account"
            )
        ).order_by("employee_code")

    def get(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            permissions_required={"payroll.view_payrollemployeeprofile"},
            label="view payroll profiles",
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_operator", "payroll_admin"},
            permissions_required={"payroll.add_payrollemployeeprofile"},
            label="create payroll profiles",
        )
        return super().post(request, *args, **kwargs)


class PayrollProfileRetrieveUpdateAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PayrollEmployeeProfileSerializer

    def get_queryset(self):
        return PayrollEmployeeProfile.objects.select_related(
            "entity", "entityfinid", "subentity", "employee_user", "salary_structure", "salary_structure_version", "payment_account"
        )

    def get(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            permissions_required={"payroll.view_payrollemployeeprofile"},
            label="view payroll profiles",
        )
        return super().get(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_operator", "payroll_admin"},
            permissions_required={"payroll.change_payrollemployeeprofile"},
            label="edit payroll profiles",
        )
        return super().patch(request, *args, **kwargs)


class PayrollAdjustmentListCreateAPIView(PayrollSetupQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PayrollAdjustmentSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["entity", "entityfinid", "subentity", "status", "kind", "payroll_period", "employee_profile"]
    search_fields = ["employee_profile__employee_code", "employee_profile__full_name", "remarks", "source_reference_id"]

    def get_queryset(self):
        return self.filter_scope(
            PayrollAdjustment.objects.select_related("entity", "entityfinid", "subentity", "employee_profile", "payroll_period", "component")
        ).order_by("-effective_date", "-id")

    def get(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            permissions_required={"payroll.view_payrolladjustment"},
            label="view payroll adjustments",
        )
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_operator", "payroll_admin"},
            permissions_required={"payroll.add_payrolladjustment"},
            label="create payroll adjustments",
        )
        return super().post(request, *args, **kwargs)


class PayrollAdjustmentRetrieveUpdateAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PayrollAdjustmentSerializer

    def get_queryset(self):
        return PayrollAdjustment.objects.select_related("entity", "entityfinid", "subentity", "employee_profile", "payroll_period", "component")

    def get(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            permissions_required={"payroll.view_payrolladjustment"},
            label="view payroll adjustments",
        )
        return super().get(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        _assert_access(
            request,
            groups={"payroll_operator", "payroll_admin"},
            permissions_required={"payroll.change_payrolladjustment"},
            label="edit payroll adjustments",
        )
        return super().patch(request, *args, **kwargs)


class PayrollDashboardSummaryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        _assert_access(
            request,
            groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            permissions_required={"payroll.view_payrollrun"},
            label="view payroll dashboard",
        )
        entity_id = request.query_params.get("entity")
        entityfinid_id = request.query_params.get("entityfinid")
        subentity_id = request.query_params.get("subentity")

        periods = PayrollPeriod.objects.all()
        runs = PayrollRun.objects.all()
        profiles = PayrollEmployeeProfile.objects.all()
        if entity_id:
            periods = periods.filter(entity_id=entity_id)
            runs = runs.filter(entity_id=entity_id)
            profiles = profiles.filter(entity_id=entity_id)
        if entityfinid_id:
            periods = periods.filter(entityfinid_id=entityfinid_id)
            runs = runs.filter(entityfinid_id=entityfinid_id)
            profiles = profiles.filter(Q(entityfinid_id=entityfinid_id) | Q(entityfinid__isnull=True))
        if subentity_id is not None:
            periods = periods.filter(subentity_id=subentity_id)
            runs = runs.filter(subentity_id=subentity_id)
            profiles = profiles.filter(subentity_id=subentity_id)

        current_period = periods.order_by("-period_start", "-id").first()
        latest_run = runs.order_by("-posting_date", "-id").first()
        readiness = PayrollSetupService.readiness_summary(
            entity_id=int(entity_id) if entity_id else None,
            entityfinid_id=int(entityfinid_id) if entityfinid_id else None,
            subentity_id=int(subentity_id) if subentity_id else None,
        )
        pending_actions = {
            "draft_runs": runs.filter(status=PayrollRun.Status.DRAFT).count(),
            "calculated_runs": runs.filter(status=PayrollRun.Status.CALCULATED).count(),
            "approved_runs": runs.filter(status=PayrollRun.Status.APPROVED).count(),
            "payment_handoff_pending": runs.filter(
                status=PayrollRun.Status.POSTED, payment_status=PayrollRun.PaymentStatus.NOT_READY
            ).count(),
            "payment_reconcile_pending": runs.filter(
                payment_status__in=[PayrollRun.PaymentStatus.HANDED_OFF, PayrollRun.PaymentStatus.PARTIALLY_DISBURSED]
            ).count(),
        }
        financial_snapshot = runs.aggregate(
            total_gross=Sum("gross_amount"),
            total_deduction=Sum("deduction_amount"),
            total_net=Sum("net_pay_amount"),
        )
        alerts = []
        if readiness["missing_payroll_profile_count"]:
            alerts.append({"code": "MISSING_PROFILE", "severity": "warning", "message": "Some payroll profiles are missing salary structures."})
        if readiness["missing_ledger_mapping_count"]:
            alerts.append({"code": "LEDGER_MAPPING_MISSING", "severity": "blocking", "message": "Ledger mappings are incomplete for the selected scope."})
        if readiness["negative_net_pay_count"]:
            alerts.append({"code": "NEGATIVE_NET_PAY", "severity": "warning", "message": "Negative net pay cases were detected."})

        payload = {
            "current_period_summary": None if not current_period else PayrollPeriodSerializer(current_period).data,
            "latest_payroll_run_summary": None
            if not latest_run
            else {
                "run_id": latest_run.id,
                "run_number": latest_run.run_number,
                "status": latest_run.status,
                "payment_status": latest_run.payment_status,
                "employee_count": latest_run.employee_count,
                "gross_amount": latest_run.gross_amount,
                "deduction_amount": latest_run.deduction_amount,
                "net_pay_amount": latest_run.net_pay_amount,
            },
            "readiness_counts": readiness,
            "pending_action_counts": pending_actions,
            "financial_snapshot": financial_snapshot,
            "alerts": alerts,
        }
        return Response(payload)


class PayrollReadinessAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        _assert_access(
            request,
            groups={"payroll_operator", "payroll_reviewer", "payroll_finance", "payroll_admin"},
            permissions_required={"payroll.view_payrollemployeeprofile"},
            label="view payroll readiness",
        )
        entity_id = request.query_params.get("entity")
        entityfinid_id = request.query_params.get("entityfinid")
        subentity_id = request.query_params.get("subentity")

        result = PayrollSetupService.readiness_summary(
            entity_id=int(entity_id) if entity_id else None,
            entityfinid_id=int(entityfinid_id) if entityfinid_id else None,
            subentity_id=int(subentity_id) if subentity_id else None,
        )

        rollout = None
        if entity_id and entityfinid_id:
            rollout = PayrollRolloutValidationService.validate_setup(
                entity_id=int(entity_id),
                entityfinid_id=int(entityfinid_id),
                subentity_id=int(subentity_id) if subentity_id else None,
            )

        profiles = PayrollEmployeeProfile.objects.select_related("salary_structure", "payment_account", "subentity").order_by("employee_code")
        if entity_id:
            profiles = profiles.filter(entity_id=entity_id)
        if entityfinid_id:
            profiles = profiles.filter(Q(entityfinid_id=entityfinid_id) | Q(entityfinid__isnull=True))
        if subentity_id is not None:
            profiles = profiles.filter(subentity_id=subentity_id)

        issue_rows = []
        for profile in profiles[:100]:
            issues = []
            if not profile.salary_structure_id:
                issues.append("Salary structure missing")
            if not profile.payment_account_id:
                issues.append("Payment details missing")
            if not profile.tax_regime:
                issues.append("Tax regime missing")
            if not (profile.extra_data or {}).get("attendance_days") or not (profile.extra_data or {}).get("payable_days"):
                issues.append("Attendance/payable days missing")
            if issues:
                issue_rows.append(
                    {
                        "payroll_profile_id": profile.id,
                        "employee_id": profile.employee_user_id,
                        "employee_code": profile.employee_code,
                        "employee_name": profile.full_name,
                        "subentity_id": profile.subentity_id,
                        "issues": issues,
                    }
                )

        payload = {
            **result,
            "employee_issue_rows": issue_rows,
            "rollout_validation": None
            if not rollout
            else {
                "passed": rollout.passed,
                "summary": rollout.summary,
                "issues": [issue.as_dict() for issue in rollout.issues],
            },
        }
        return Response(payload)
