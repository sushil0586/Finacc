from __future__ import annotations

from datetime import date

from django.utils.dateparse import parse_date
from rest_framework import generics, permissions
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from hrms.models import HrEmploymentContract
from payroll.models import ContractAttendanceSummary, ContractTaxDeclaration, FnFSettlement, PayrollPeriod, PayrollRun, PayrollRunEmployee, PayrollRunEmployeeComponent, Payslip
from payroll.serializers.payroll_product_serializers import (
    AttendanceSummaryPlaceholderSerializer,
    EmployeeAttendanceTraceSerializer,
    EmployeePayslipDetailSerializer,
    EmployeePayslipListSerializer,
    EmployeeStatutoryTraceSerializer,
    FnFSettlementActionSerializer,
    FnFSettlementDetailSerializer,
    FnFSettlementListSerializer,
    PayrollRunComponentTraceSerializer,
    TaxDeclarationSummarySerializer,
)
from payroll.serializers.payroll_run_serializers import PayrollRunListSerializer
from payroll.services import PayrollFnFEngine, PayrollRunReadinessResolverService
from payroll.services.contract_salary_assignment_service import ContractSalaryAssignmentService
from payroll.services.payroll_export_service import PayrollExportService
from payroll.services.payroll_tds_engine import PayrollTDSEngine
from payroll.views.scoped import PayrollScopedAPIView

STATUTORY_SEMANTIC_CODES = {
    "PF_EMPLOYEE",
    "PF_EMPLOYER",
    "ESI_EMPLOYEE",
    "ESI_EMPLOYER",
    "PT",
    "TDS",
    "LWF_EMPLOYEE",
    "LWF_EMPLOYER",
}


def _value_error_to_validation(err: Exception):
    payload = err.args[0] if err.args else str(err)
    if isinstance(payload, dict):
        raise ValidationError(payload)
    raise ValidationError({"detail": str(payload)})


def _readiness_summary_payload(result) -> dict:
    snapshot = result.generated_snapshot_json or {}
    salary_structure = snapshot.get("salary_structure") or {}
    salary_structure_version = snapshot.get("salary_structure_version") or {}
    payroll_policy = snapshot.get("payroll_policy") or {}
    return {
        "contract_id": str(result.contract.id),
        "contract_code": result.contract.contract_code,
        "employee_id": str(result.contract.employee_id),
        "employee_number": getattr(result.contract.employee, "employee_number", "") or "",
        "employee_name": getattr(result.contract.employee, "display_name", "") or "",
        "subentity_id": result.contract.subentity_id,
        "readiness_status": result.readiness_status,
        "warnings": result.warnings,
        "blocking_issues": result.blocking_issues,
        "pay_frequency": (snapshot.get("payroll_profile") or {}).get("pay_frequency"),
        "salary_structure_code": salary_structure.get("code"),
        "salary_structure_version_no": salary_structure_version.get("version_no"),
        "payroll_policy_code": payroll_policy.get("code"),
        "recurring_item_count": len(result.recurring_items),
        "one_time_item_count": len(result.one_time_items),
        "statutory_profile_count": len(result.statutory_profiles),
        "statutory_registration_count": len(result.statutory_registrations),
        "snapshot": snapshot,
    }


class FnFSettlementListAPIView(PayrollScopedAPIView, generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FnFSettlementListSerializer

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_from_query(self.request, require_entity=True)
        qs = FnFSettlement.objects.select_related(
            "entity",
            "entityfinid",
            "subentity",
            "hrms_contract",
            "contract_payroll_profile__hrms_contract__employee",
        ).filter(entity_id=entity_id)
        if entityfinid_id is not None:
            qs = qs.filter(entityfinid_id=entityfinid_id)
        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        status_value = self.request.query_params.get("status")
        if status_value:
            qs = qs.filter(status=status_value)
        awaiting_approval = str(self.request.query_params.get("awaiting_approval", "")).lower()
        if awaiting_approval in {"1", "true", "yes"}:
            qs = qs.filter(status=FnFSettlement.Status.CALCULATED)
        return qs.order_by("-settlement_date", "-id")

    def list(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_entity_permission(request, entity_id=entity_id, permission_codes={"payroll.run.view", "payroll.run.manage"}, label="view FnF settlements")
        return super().list(request, *args, **kwargs)


class FnFSettlementDetailAPIView(PayrollScopedAPIView, generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FnFSettlementDetailSerializer
    queryset = FnFSettlement.objects.select_related(
        "entity",
        "entityfinid",
        "subentity",
        "hrms_contract",
        "contract_payroll_profile__hrms_contract__employee",
        "salary_structure",
        "salary_structure_version",
        "payroll_period",
    ).prefetch_related("components")

    def get_object(self):
        obj = super().get_object()
        self._enforce_object_scope(self.request, obj)
        self._assert_entity_permission(self.request, entity_id=obj.entity_id, permission_codes={"payroll.run.view", "payroll.run.manage"}, label="view FnF settlements")
        return obj


class FnFSettlementCalculateAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = FnFSettlementActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        contract_id = serializer.validated_data.get("contract_id")
        separation_date = serializer.validated_data.get("separation_date")
        if not contract_id or not separation_date:
            raise ValidationError({"detail": "contract_id and separation_date are required."})
        contract = HrEmploymentContract.objects.select_related("entity").get(pk=contract_id)
        self.enforce_scope(request, entity_id=contract.entity_id, subentity_id=contract.subentity_id)
        self._assert_entity_permission(request, entity_id=contract.entity_id, permission_codes={"payroll.run.manage"}, label="calculate FnF settlements")
        try:
            settlement = PayrollFnFEngine.calculate_fnf(contract_id, separation_date=separation_date, inputs=serializer.validated_data.get("inputs") or {})
        except Exception as err:
            _value_error_to_validation(err)
        return Response({"message": "FnF settlement calculated.", "data": FnFSettlementDetailSerializer(settlement).data}, status=201)


class _FnFActionAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def _settlement(self, pk: int) -> FnFSettlement:
        settlement = FnFSettlement.objects.select_related("entity", "entityfinid", "subentity").get(pk=pk)
        self._enforce_object_scope(self.request, settlement)
        self._assert_entity_permission(self.request, entity_id=settlement.entity_id, permission_codes={"payroll.run.manage"}, label="manage FnF settlements")
        return settlement


class FnFSettlementRecalculateAPIView(_FnFActionAPIView):
    def post(self, request, pk: int):
        serializer = FnFSettlementActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        settlement = self._settlement(pk)
        try:
            recalculated = PayrollFnFEngine.recalculate_fnf(settlement.id, serializer.validated_data.get("inputs") or {})
        except Exception as err:
            _value_error_to_validation(err)
        return Response({"message": "FnF settlement recalculated.", "data": FnFSettlementDetailSerializer(recalculated).data})


class FnFSettlementApproveAPIView(_FnFActionAPIView):
    def post(self, request, pk: int):
        serializer = FnFSettlementActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        settlement = self._settlement(pk)
        try:
            approved = PayrollFnFEngine.approve_fnf(settlement.id, user_id=request.user.id, note=serializer.validated_data.get("note", ""))
        except Exception as err:
            _value_error_to_validation(err)
        return Response({"message": "FnF settlement approved.", "data": FnFSettlementDetailSerializer(approved).data})


class FnFSettlementPostAPIView(_FnFActionAPIView):
    def post(self, request, pk: int):
        serializer = FnFSettlementActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        settlement = self._settlement(pk)
        try:
            posted = PayrollFnFEngine.mark_posted(
                settlement.id,
                post_reference=serializer.validated_data.get("post_reference", ""),
                user_id=request.user.id,
            )
        except Exception as err:
            _value_error_to_validation(err)
        return Response({"message": "FnF settlement marked posted.", "data": FnFSettlementDetailSerializer(posted).data})


class FnFSettlementPaidAPIView(_FnFActionAPIView):
    def post(self, request, pk: int):
        serializer = FnFSettlementActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        settlement = self._settlement(pk)
        try:
            paid = PayrollFnFEngine.mark_paid(
                settlement.id,
                payment_reference=serializer.validated_data.get("payment_reference", ""),
                user_id=request.user.id,
            )
        except Exception as err:
            _value_error_to_validation(err)
        return Response({"message": "FnF settlement marked paid.", "data": FnFSettlementDetailSerializer(paid).data})


class FnFSettlementCancelAPIView(_FnFActionAPIView):
    def post(self, request, pk: int):
        serializer = FnFSettlementActionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        settlement = self._settlement(pk)
        try:
            cancelled = PayrollFnFEngine.cancel_fnf(settlement.id, user_id=request.user.id, note=serializer.validated_data.get("note", ""))
        except Exception as err:
            _value_error_to_validation(err)
        return Response({"message": "FnF settlement cancelled.", "data": FnFSettlementDetailSerializer(cancelled).data})


class FnFSettlementStatementPdfAPIView(_FnFActionAPIView):
    def get(self, request, pk: int):
        settlement = self._settlement(pk)
        generated_by = getattr(request.user, "email", None) or getattr(request.user, "username", None) or f"user:{request.user.pk}"
        return PayrollExportService.export_fnf_statement_placeholder_pdf(settlement=settlement, generated_by=generated_by)


class EmployeePayslipListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EmployeePayslipListSerializer

    def get_queryset(self):
        return Payslip.objects.select_related(
            "payroll_run_employee__payroll_run__payroll_period",
            "payroll_run_employee__contract_payroll_profile__hrms_contract__employee",
        ).filter(
            payroll_run_employee__contract_payroll_profile__hrms_contract__employee__linked_user=self.request.user
        ).order_by("-generated_at", "-id")


class EmployeePayslipDetailAPIView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EmployeePayslipDetailSerializer

    def get_queryset(self):
        return Payslip.objects.select_related(
            "payroll_run_employee__payroll_run",
            "payroll_run_employee__contract_payroll_profile__hrms_contract__employee",
        ).prefetch_related("payroll_run_employee__components__component").filter(
            payroll_run_employee__contract_payroll_profile__hrms_contract__employee__linked_user=self.request.user
        )


class EmployeePayslipPdfAPIView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Payslip.objects.select_related(
            "payroll_run_employee__payroll_run__payroll_period",
            "payroll_run_employee__contract_payroll_profile__hrms_contract__employee",
        ).prefetch_related("payroll_run_employee__components__component").filter(
            payroll_run_employee__contract_payroll_profile__hrms_contract__employee__linked_user=self.request.user
        )

    def get(self, request, *args, **kwargs):
        payslip = self.get_object()
        generated_by = getattr(request.user, "email", None) or getattr(request.user, "username", None) or f"user:{request.user.pk}"
        return PayrollExportService.export_payslip_pdf(payslip=payslip, generated_by=generated_by)


class EmployeeTaxDeclarationSummaryAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TaxDeclarationSummarySerializer

    def get(self, request):
        declaration = ContractTaxDeclaration.objects.select_related(
            "contract_payroll_profile__hrms_contract__employee",
            "financial_year",
        ).prefetch_related("lines").filter(
            contract_payroll_profile__hrms_contract__employee__linked_user=request.user,
            is_active=True,
        ).order_by("-created_at", "-id").first()
        if not declaration:
            return Response({"status": "placeholder", "message": "No submitted tax declaration is available yet.", "data": None})
        assignment = ContractSalaryAssignmentService.get_active_assignment_for_payroll_date(
            contract_payroll_profile=declaration.contract_payroll_profile,
            payroll_date=declaration.financial_year.finstartyear.date(),
        )
        policy = getattr(getattr(assignment, "salary_structure_version", None), "calculation_policy_json", None) or {}
        projection = PayrollTDSEngine.build_projection(
            contract_payroll_profile=declaration.contract_payroll_profile,
            salary_assignment=assignment,
            declaration=declaration,
            tax_regime=declaration.tax_regime,
            policy=policy,
        )
        serializer = self.get_serializer(declaration, context={"projection_trace": projection.trace})
        return Response({"status": "available", "data": serializer.data})


class EmployeeReimbursementPlaceholderAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "status": "placeholder",
                "feature": "reimbursements",
                "enabled": False,
                "message": "Claim and reimbursement self-service will be exposed here without changing payroll calculation engines.",
            }
        )


class EmployeeAttendanceSummaryPlaceholderAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AttendanceSummaryPlaceholderSerializer

    def get(self, request):
        summary = ContractAttendanceSummary.objects.select_related(
            "contract_payroll_profile__hrms_contract__employee",
            "payroll_period",
        ).filter(
            contract_payroll_profile__hrms_contract__employee__linked_user=request.user,
            is_active=True,
        ).order_by("-payroll_period__period_end", "-id").first()
        if not summary:
            return Response(
                {
                    "status": "placeholder",
                    "enabled": False,
                    "message": "Attendance and leave self-service will be exposed here once employee workflows are enabled.",
                    "data": None,
                }
            )
        return Response({"status": "available", "data": self.get_serializer(summary).data})


class PayrollPendingFnFApprovalsAPIView(PayrollScopedAPIView, generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FnFSettlementListSerializer

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_from_query(self.request, require_entity=True)
        qs = FnFSettlement.objects.select_related(
            "contract_payroll_profile__hrms_contract__employee",
            "hrms_contract",
        ).filter(entity_id=entity_id, status=FnFSettlement.Status.CALCULATED)
        if entityfinid_id is not None:
            qs = qs.filter(entityfinid_id=entityfinid_id)
        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        return qs.order_by("-settlement_date", "-id")

    def list(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_entity_permission(request, entity_id=entity_id, permission_codes={"payroll.run.view", "payroll.run.manage"}, label="view pending FnF approvals")
        return super().list(request, *args, **kwargs)


class PayrollPendingApprovalsAPIView(PayrollScopedAPIView, generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PayrollRunListSerializer

    def get_queryset(self):
        entity_id, entityfinid_id, subentity_id = self._scope_from_query(self.request, require_entity=True)
        qs = PayrollRun.objects.select_related("payroll_period", "entity", "entityfinid", "subentity").filter(
            entity_id=entity_id,
            status=PayrollRun.Status.CALCULATED,
            submitted_at__isnull=False,
            approved_at__isnull=True,
        )
        if entityfinid_id is not None:
            qs = qs.filter(entityfinid_id=entityfinid_id)
        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        return qs.order_by("-posting_date", "-id")

    def list(self, request, *args, **kwargs):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        self._assert_entity_permission(request, entity_id=entity_id, permission_codes={"payroll.run.view", "payroll.run.manage"}, label="view pending payroll approvals")
        return super().list(request, *args, **kwargs)


class PayrollReadinessDetailAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        contract_id = request.query_params.get("contract")
        payroll_period_id = request.query_params.get("payroll_period")
        payroll_date_raw = request.query_params.get("payroll_date")
        if not contract_id:
            raise ValidationError({"contract": "contract is required."})
        contract = HrEmploymentContract.objects.select_related("employee").get(pk=contract_id, entity_id=entity_id)
        payroll_period = None
        if payroll_period_id:
            payroll_period = PayrollPeriod.objects.get(pk=payroll_period_id, entity_id=entity_id)
            payroll_date = payroll_period.period_end
        else:
            payroll_date = parse_date(payroll_date_raw or "")
        if not payroll_date:
            raise ValidationError({"payroll_date": "payroll_period or payroll_date is required."})
        result = PayrollRunReadinessResolverService.resolve_contract_readiness(
            contract=contract,
            payroll_date=payroll_date,
            payroll_period=payroll_period,
        )
        self._assert_entity_permission(request, entity_id=entity_id, permission_codes={"payroll.run.view", "payroll.run.manage"}, label="view payroll readiness")
        return Response(
            {
                "summary": _readiness_summary_payload(result),
                "warnings": result.warnings,
                "blocking_issues": result.blocking_issues,
                "snapshot": result.generated_snapshot_json,
            }
        )


class PayrollExceptionsAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        payroll_period_id = request.query_params.get("payroll_period")
        if not payroll_period_id:
            raise ValidationError({"payroll_period": "payroll_period is required."})
        payroll_period = PayrollPeriod.objects.select_related("entity").get(pk=payroll_period_id, entity_id=entity_id)
        self._assert_entity_permission(request, entity_id=entity_id, permission_codes={"payroll.run.view", "payroll.run.manage"}, label="view payroll exceptions")
        results = PayrollRunReadinessResolverService.resolve_entity_readiness(entity=payroll_period.entity, payroll_period=payroll_period)
        blocked = [_readiness_summary_payload(result) for result in results if result.readiness_status == result.BLOCKED]
        warnings = [_readiness_summary_payload(result) for result in results if result.readiness_status == result.WARNING]
        return Response(
            {
                "payroll_period": payroll_period.id,
                "blocked_count": len(blocked),
                "warning_count": len(warnings),
                "blocked_contracts": blocked,
                "warning_contracts": warnings,
            }
        )


class PayrollProfileCompletenessAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity_id, _, _ = self._scope_from_query(request, require_entity=True)
        payroll_period_id = request.query_params.get("payroll_period")
        if not payroll_period_id:
            raise ValidationError({"payroll_period": "payroll_period is required."})
        payroll_period = PayrollPeriod.objects.select_related("entity").get(pk=payroll_period_id, entity_id=entity_id)
        self._assert_entity_permission(request, entity_id=entity_id, permission_codes={"payroll.run.view", "payroll.run.manage"}, label="view payroll profile completeness")
        results = PayrollRunReadinessResolverService.resolve_entity_readiness(entity=payroll_period.entity, payroll_period=payroll_period)
        items = []
        for result in results:
            snapshot = result.generated_snapshot_json or {}
            profile = snapshot.get("payroll_profile") or {}
            assignment = snapshot.get("salary_assignment") or {}
            items.append(
                {
                    "contract_id": str(result.contract.id),
                    "contract_code": result.contract.contract_code,
                    "employee_number": getattr(result.contract.employee, "employee_number", "") or "",
                    "employee_name": getattr(result.contract.employee, "display_name", "") or "",
                    "readiness_status": result.readiness_status,
                    "has_payroll_profile": bool(profile),
                    "has_salary_assignment": bool(assignment),
                    "has_bank_account": bool(profile.get("bank_account_id")),
                    "has_payroll_policy": bool(snapshot.get("payroll_policy")),
                    "warning_count": len(result.warnings),
                    "blocking_issue_count": len(result.blocking_issues),
                    "issue_messages": (result.blocking_issues + result.warnings)[:5],
                }
            )
        return Response({"payroll_period": payroll_period.id, "results": items})


class PayrollRunComponentTraceDetailAPIView(PayrollScopedAPIView, generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PayrollRunComponentTraceSerializer
    lookup_url_kwarg = "component_id"

    def get_queryset(self):
        return PayrollRunEmployeeComponent.objects.select_related(
            "component",
            "payroll_run_employee__payroll_run",
            "payroll_run_employee__contract_payroll_profile__hrms_contract__employee",
        ).filter(payroll_run_employee__payroll_run_id=self.kwargs["pk"])

    def get_object(self):
        obj = super().get_object()
        run = obj.payroll_run_employee.payroll_run
        self._enforce_object_scope(self.request, run)
        self._assert_entity_permission(self.request, entity_id=run.entity_id, permission_codes={"payroll.run.view", "payroll.run.manage"}, label="view payroll component trace")
        return obj


class PayrollRunEmployeeAttendanceTraceAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int, employee_run_id: int):
        row = PayrollRunEmployee.objects.select_related("payroll_run", "contract_payroll_profile__hrms_contract__employee").prefetch_related("components__component").get(
            pk=employee_run_id,
            payroll_run_id=pk,
        )
        self._enforce_object_scope(request, row.payroll_run)
        self._assert_entity_permission(request, entity_id=row.payroll_run.entity_id, permission_codes={"payroll.run.view", "payroll.run.manage"}, label="view attendance trace")
        payload = {
            "employee_code": row.employee_code,
            "employee_name": row.employee_name,
            "attendance_execution": (row.calculation_payload or {}).get("attendance_execution") or {},
            "component_proration": [
                {
                    "component_id": component.id,
                    "component_code": component.component_code,
                    "component_name": component.component_name,
                    "attendance_trace": (component.calculation_basis_snapshot or {}).get("attendance_trace") or {},
                }
                for component in row.components.all()
                if (component.calculation_basis_snapshot or {}).get("attendance_trace")
            ],
        }
        return Response(EmployeeAttendanceTraceSerializer(payload).data)


class PayrollRunEmployeeStatutoryTraceAPIView(PayrollScopedAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int, employee_run_id: int):
        row = PayrollRunEmployee.objects.select_related("payroll_run", "contract_payroll_profile__hrms_contract__employee").prefetch_related("components__component").get(
            pk=employee_run_id,
            payroll_run_id=pk,
        )
        self._enforce_object_scope(request, row.payroll_run)
        self._assert_entity_permission(request, entity_id=row.payroll_run.entity_id, permission_codes={"payroll.run.view", "payroll.run.manage"}, label="view statutory trace")
        statutory_components = []
        for component in row.components.all():
            semantic_code = (component.calculation_basis_snapshot or {}).get("semantic_code") or getattr(component.component, "semantic_code", "")
            if semantic_code not in STATUTORY_SEMANTIC_CODES:
                continue
            statutory_components.append(PayrollRunComponentTraceSerializer(component).data)
        payload = {
            "employee_code": row.employee_code,
            "employee_name": row.employee_name,
            "statutory_components": statutory_components,
        }
        return Response(EmployeeStatutoryTraceSerializer(payload).data)
