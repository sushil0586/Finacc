from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from payroll.models import (
    ContractAttendanceSummary,
    ContractTaxDeclaration,
    FnFSettlement,
    FnFSettlementComponent,
    PayrollRunEmployee,
    PayrollRunEmployeeComponent,
    Payslip,
)

ZERO2 = Decimal("0.00")

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


def _string_amount(value) -> str:
    try:
        return str(Decimal(str(value or "0")).quantize(Decimal("0.01")))
    except Exception:
        return "0.00"


def _component_semantic_code(component, snapshot: dict | None = None) -> str:
    snapshot = snapshot or {}
    if snapshot.get("semantic_code"):
        return str(snapshot.get("semantic_code") or "")
    if getattr(component, "semantic_code", ""):
        return str(component.semantic_code or "")
    return ""


def _frontend_group(component_type: str, semantic_code: str) -> str:
    if semantic_code in STATUTORY_SEMANTIC_CODES:
        return "statutory"
    if component_type == "EMPLOYER_CONTRIBUTION":
        return "employer_contributions"
    if component_type in {"DEDUCTION", "RECOVERY"}:
        return "deductions"
    return "earnings"


class FnFSettlementActionSerializer(serializers.Serializer):
    contract_id = serializers.UUIDField(required=False)
    separation_date = serializers.DateField(required=False)
    inputs = serializers.JSONField(required=False, default=dict)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    post_reference = serializers.CharField(required=False, allow_blank=True, default="")
    payment_reference = serializers.CharField(required=False, allow_blank=True, default="")


class FnFSettlementComponentSerializer(serializers.ModelSerializer):
    frontend_group = serializers.SerializerMethodField()
    calculation_source = serializers.SerializerMethodField()
    component_trace = serializers.JSONField(source="calculation_trace", read_only=True)

    def get_frontend_group(self, obj):
        semantic_code = str((obj.metadata or {}).get("component_snapshot", {}).get("semantic_code", "") or "")
        return _frontend_group(obj.component_type, semantic_code)

    def get_calculation_source(self, obj):
        return (obj.calculation_trace or {}).get("source") or obj.source_type.lower()

    class Meta:
        model = FnFSettlementComponent
        fields = [
            "id",
            "source_type",
            "frontend_group",
            "component",
            "source_structure_line",
            "component_code",
            "component_name",
            "component_type",
            "posting_behavior",
            "sequence",
            "amount",
            "base_amount",
            "quantity",
            "days",
            "rate",
            "metadata",
            "calculation_source",
            "component_trace",
        ]


class FnFSettlementListSerializer(serializers.ModelSerializer):
    contract_code = serializers.CharField(source="hrms_contract.contract_code", read_only=True)
    employee_code = serializers.CharField(source="contract_payroll_profile.employee_code", read_only=True)
    employee_name = serializers.CharField(source="contract_payroll_profile.employee_name", read_only=True)

    class Meta:
        model = FnFSettlement
        fields = [
            "id",
            "status",
            "approval_status",
            "settlement_number",
            "contract_code",
            "employee_code",
            "employee_name",
            "separation_date",
            "last_working_day",
            "settlement_date",
            "earned_amount",
            "deduction_amount",
            "recovery_amount",
            "reimbursement_amount",
            "net_payable_amount",
            "net_recoverable_amount",
            "approved_at",
            "posted_at",
            "paid_at",
        ]


class FnFSettlementDetailSerializer(FnFSettlementListSerializer):
    components = FnFSettlementComponentSerializer(many=True, read_only=True)
    grouped_components = serializers.SerializerMethodField()
    posting_status = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()

    def get_grouped_components(self, obj):
        grouped = {
            "earnings": [],
            "deductions": [],
            "statutory": [],
            "employer_contributions": [],
        }
        for component in obj.components.all():
            payload = FnFSettlementComponentSerializer(component, context=self.context).data
            grouped[payload["frontend_group"]].append(payload)
        return grouped

    def get_posting_status(self, obj):
        return "posted" if obj.status in {obj.Status.POSTED, obj.Status.PAID} else "not_posted"

    def get_payment_status(self, obj):
        return "paid" if obj.status == obj.Status.PAID else "not_paid"

    class Meta(FnFSettlementListSerializer.Meta):
        fields = FnFSettlementListSerializer.Meta.fields + [
            "entity",
            "entityfinid",
            "subentity",
            "hrms_contract",
            "contract_payroll_profile",
            "salary_structure",
            "salary_structure_version",
            "payroll_period",
            "approval_status",
            "posting_status",
            "payment_status",
            "post_reference",
            "payment_reference",
            "approval_note",
            "calculation_payload",
            "settlement_snapshot",
            "components",
            "grouped_components",
        ]


class PayrollRunComponentTraceSerializer(serializers.ModelSerializer):
    employee_code = serializers.CharField(source="payroll_run_employee.employee_code", read_only=True)
    employee_name = serializers.CharField(source="payroll_run_employee.employee_name", read_only=True)
    semantic_code = serializers.SerializerMethodField()
    frontend_group = serializers.SerializerMethodField()
    calculation_source = serializers.SerializerMethodField()
    component_trace = serializers.SerializerMethodField()
    statutory_trace = serializers.SerializerMethodField()
    attendance_trace = serializers.SerializerMethodField()

    def get_semantic_code(self, obj):
        return _component_semantic_code(obj.component, obj.calculation_basis_snapshot or {})

    def get_frontend_group(self, obj):
        return _frontend_group(obj.component_type, self.get_semantic_code(obj))

    def get_calculation_source(self, obj):
        snapshot = obj.calculation_basis_snapshot or {}
        return (
            snapshot.get("source_type")
            or snapshot.get("contract_native_source")
            or ((obj.metadata or {}).get("source_type"))
            or "structure_line"
        )

    def get_component_trace(self, obj):
        return (obj.metadata or {}).get("calculation_trace") or {}

    def get_statutory_trace(self, obj):
        trace = self.get_component_trace(obj)
        return trace if trace.get("calculation_mode") == "STATUTORY_ENGINE" else {}

    def get_attendance_trace(self, obj):
        return (obj.calculation_basis_snapshot or {}).get("attendance_trace") or {}

    class Meta:
        model = PayrollRunEmployeeComponent
        fields = [
            "id",
            "employee_code",
            "employee_name",
            "component",
            "component_code",
            "component_name",
            "component_type",
            "posting_behavior",
            "amount",
            "taxable_amount",
            "semantic_code",
            "frontend_group",
            "calculation_source",
            "component_trace",
            "statutory_trace",
            "attendance_trace",
            "metadata",
            "calculation_basis_snapshot",
        ]


class EmployeeAttendanceTraceSerializer(serializers.Serializer):
    employee_code = serializers.CharField()
    employee_name = serializers.CharField()
    attendance_execution = serializers.JSONField()
    component_proration = serializers.JSONField()


class EmployeeStatutoryTraceSerializer(serializers.Serializer):
    employee_code = serializers.CharField()
    employee_name = serializers.CharField()
    statutory_components = serializers.JSONField()


class EmployeePayslipListSerializer(serializers.ModelSerializer):
    payroll_run_id = serializers.IntegerField(source="payroll_run_employee.payroll_run_id", read_only=True)
    payroll_period_code = serializers.CharField(source="payroll_run_employee.payroll_run.payroll_period.code", read_only=True)
    approval_status = serializers.CharField(source="payroll_run_employee.payroll_run.status", read_only=True)
    payment_status = serializers.CharField(source="payroll_run_employee.payment_status", read_only=True)
    net_pay = serializers.DecimalField(source="payroll_run_employee.payable_amount", max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Payslip
        fields = [
            "id",
            "payslip_number",
            "payroll_run_id",
            "payroll_period_code",
            "generated_at",
            "published_at",
            "approval_status",
            "payment_status",
            "net_pay",
        ]


class EmployeePayslipDetailSerializer(serializers.ModelSerializer):
    grouped_components = serializers.SerializerMethodField()
    component_trace = serializers.SerializerMethodField()
    calculation_source = serializers.SerializerMethodField()
    approval_status = serializers.CharField(source="payroll_run_employee.payroll_run.status", read_only=True)
    posting_status = serializers.SerializerMethodField()
    payment_status = serializers.CharField(source="payroll_run_employee.payment_status", read_only=True)

    def get_grouped_components(self, obj):
        grouped = {
            "earnings": [],
            "deductions": [],
            "statutory": [],
            "employer_contributions": [],
        }
        for row in obj.payroll_run_employee.components.select_related("component").all():
            semantic_code = _component_semantic_code(row.component, row.calculation_basis_snapshot or {})
            item = {
                "id": row.id,
                "component_code": row.component_code,
                "component_name": row.component_name,
                "amount": _string_amount(row.amount),
                "semantic_code": semantic_code,
                "calculation_source": (
                    (row.calculation_basis_snapshot or {}).get("contract_native_source")
                    or ((row.metadata or {}).get("source_type"))
                    or "structure_line"
                ),
            }
            grouped[_frontend_group(row.component_type, semantic_code)].append(item)
        return grouped

    def get_component_trace(self, obj):
        return [
            PayrollRunComponentTraceSerializer(component, context=self.context).data
            for component in obj.payroll_run_employee.components.select_related("component").all()
        ]

    def get_calculation_source(self, obj):
        return ((obj.payload or {}).get("source_markers") or {}).get("attendance_source") or "contract_native"

    def get_posting_status(self, obj):
        run = obj.payroll_run_employee.payroll_run
        return "posted" if run.status == run.Status.POSTED else "not_posted"

    class Meta:
        model = Payslip
        fields = [
            "id",
            "payslip_number",
            "generated_at",
            "published_at",
            "approval_status",
            "posting_status",
            "payment_status",
            "calculation_source",
            "grouped_components",
            "component_trace",
            "payload",
        ]


class TaxDeclarationSummarySerializer(serializers.ModelSerializer):
    total_declared_amount = serializers.SerializerMethodField()
    total_approved_amount = serializers.SerializerMethodField()
    section_breakdown = serializers.SerializerMethodField()
    projection_trace = serializers.SerializerMethodField()

    def get_total_declared_amount(self, obj):
        return _string_amount(sum((line.declared_amount for line in obj.lines.filter(is_active=True)), ZERO2))

    def get_total_approved_amount(self, obj):
        return _string_amount(sum((line.approved_amount for line in obj.lines.filter(is_active=True)), ZERO2))

    def get_section_breakdown(self, obj):
        return [
            {
                "section_code": line.section_code,
                "declaration_category": getattr(line, "declaration_category", ""),
                "declaration_code": getattr(line, "declaration_code", ""),
                "description": line.description,
                "declared_amount": _string_amount(line.declared_amount),
                "approved_amount": _string_amount(line.approved_amount),
                "evidence_status": line.evidence_status,
            }
            for line in obj.lines.filter(is_active=True).order_by("section_code", "id")
        ]

    def get_projection_trace(self, obj):
        return self.context.get("projection_trace") or {}

    class Meta:
        model = ContractTaxDeclaration
        fields = [
            "id",
            "financial_year",
            "tax_regime",
            "declaration_status",
            "declared_annual_income",
            "annual_other_income",
            "previous_employer_income",
            "previous_employer_tds",
            "standard_deduction_amount",
            "professional_tax_declared",
            "annual_gross_projection",
            "annual_exemption_total",
            "annual_deduction_total",
            "projected_taxable_income",
            "projected_annual_tax",
            "projected_monthly_tds",
            "tax_already_deducted",
            "balance_tax",
            "total_declared_amount",
            "total_approved_amount",
            "section_breakdown",
            "projection_trace",
        ]


class AttendanceSummaryPlaceholderSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    placeholder = serializers.SerializerMethodField()

    def get_status(self, obj):
        return "available" if obj else "placeholder"

    def get_placeholder(self, obj):
        return {
            "enabled": False,
            "message": "Leave and attendance self-service workflows will be surfaced here without changing payroll execution.",
        }

    class Meta:
        model = ContractAttendanceSummary
        fields = [
            "payroll_period",
            "attendance_days",
            "payable_days",
            "lop_days",
            "weekly_off_days",
            "holiday_days",
            "overtime_hours",
            "late_count",
            "half_days",
            "approval_status",
            "status",
            "placeholder",
            "metadata",
        ]
