from __future__ import annotations

from rest_framework import serializers

from payroll.models import PayrollRun, PayrollRunEmployee, PayrollRunEmployeeComponent, Payslip


class PayrollRunCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollRun
        fields = [
            "entity",
            "entityfinid",
            "subentity",
            "payroll_period",
            "run_type",
            "posting_date",
            "payout_date",
        ]


class PayrollRunActionSerializer(serializers.Serializer):
    force = serializers.BooleanField(required=False, default=False)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    reason_code = serializers.CharField(required=False, allow_blank=True, default="")
    payment_batch_ref = serializers.CharField(required=False, allow_blank=True, default="")
    payment_status = serializers.ChoiceField(required=False, choices=PayrollRun.PaymentStatus.choices)


class PayrollRunEmployeeComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollRunEmployeeComponent
        fields = [
            "id",
            "component",
            "component_code",
            "component_name",
            "component_type",
            "posting_behavior",
            "component_posting_version",
            "source_structure_line",
            "amount",
            "taxable_amount",
            "is_employer_cost",
            "metadata",
            "calculation_basis_snapshot",
        ]


class PayrollRunEmployeeSerializer(serializers.ModelSerializer):
    employee_code = serializers.CharField(source="employee_profile.employee_code", read_only=True)
    employee_name = serializers.CharField(source="employee_profile.full_name", read_only=True)
    components = PayrollRunEmployeeComponentSerializer(many=True, read_only=True)

    class Meta:
        model = PayrollRunEmployee
        fields = [
            "id",
            "employee_profile",
            "employee_code",
            "employee_name",
            "status",
            "payment_status",
            "gross_amount",
            "deduction_amount",
            "employer_contribution_amount",
            "reimbursement_amount",
            "payable_amount",
            "remarks",
            "salary_structure_version",
            "ledger_policy_version",
            "statutory_policy_version_ref",
            "calculation_assumptions",
            "components",
        ]


class PayrollRunListSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source="get_status_display", read_only=True)
    payment_status_name = serializers.CharField(source="get_payment_status_display", read_only=True)
    period_code = serializers.CharField(source="payroll_period.code", read_only=True)

    class Meta:
        model = PayrollRun
        fields = [
            "id",
            "entity",
            "entityfinid",
            "subentity",
            "payroll_period",
            "period_code",
            "run_type",
            "doc_code",
            "doc_no",
            "run_number",
            "posting_date",
            "payout_date",
            "status",
            "status_name",
            "payment_status",
            "payment_status_name",
            "employee_count",
            "gross_amount",
            "deduction_amount",
            "employer_contribution_amount",
            "reimbursement_amount",
            "net_pay_amount",
            "posted_entry_id",
            "is_immutable",
        ]


class PayrollRunDetailSerializer(PayrollRunListSerializer):
    employee_runs = PayrollRunEmployeeSerializer(many=True, read_only=True)

    class Meta(PayrollRunListSerializer.Meta):
        fields = PayrollRunListSerializer.Meta.fields + [
            "approval_note",
            "status_reason_code",
            "status_comment",
            "config_snapshot",
            "post_reference",
            "ledger_policy_version",
            "statutory_policy_version_ref",
            "submitted_by",
            "created_by",
            "approved_by",
            "locked_by",
            "posted_by",
            "cancelled_by",
            "reversed_by",
            "submitted_at",
            "approved_at",
            "locked_at",
            "posted_at",
            "cancelled_at",
            "reversed_at",
            "payment_batch_ref",
            "payment_handoff_payload",
            "payment_handed_off_at",
            "payment_reconciled_at",
            "reversed_run",
            "correction_of_run",
            "reversal_reason",
            "employee_runs",
        ]


class PayrollRunSummarySerializer(serializers.Serializer):
    run_id = serializers.IntegerField()
    employee_count = serializers.IntegerField()
    gross_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    deduction_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    employer_contribution_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    reimbursement_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    payable_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    status = serializers.CharField()


class PayslipSerializer(serializers.ModelSerializer):
    employee_code = serializers.CharField(source="payroll_run_employee.employee_profile.employee_code", read_only=True)
    employee_name = serializers.CharField(source="payroll_run_employee.employee_profile.full_name", read_only=True)

    class Meta:
        model = Payslip
        fields = [
            "id",
            "payslip_number",
            "employee_code",
            "employee_name",
            "generated_at",
            "published_at",
            "payload",
        ]
