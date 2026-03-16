from __future__ import annotations

from rest_framework import serializers

from payroll.models import PayrollRun, PayrollRunEmployee, PayrollRunEmployeeComponent, Payslip
from payroll.services.payroll_traceability_service import PayrollTraceabilityService


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
    payroll_profile_id = serializers.IntegerField(source="employee_profile_id", read_only=True)
    employee_id = serializers.IntegerField(source="employee_profile.employee_user_id", read_only=True)
    salary_structure_id = serializers.IntegerField(read_only=True)
    warning_count = serializers.SerializerMethodField()
    blocking_issue_count = serializers.SerializerMethodField()
    issue_messages = serializers.SerializerMethodField()
    components = PayrollRunEmployeeComponentSerializer(many=True, read_only=True)

    def _issue_summary(self, obj):
        return PayrollTraceabilityService.build_employee_issue_summary(row=obj)

    def get_warning_count(self, obj):
        return self._issue_summary(obj)["warning_count"]

    def get_blocking_issue_count(self, obj):
        return self._issue_summary(obj)["blocking_issue_count"]

    def get_issue_messages(self, obj):
        return self._issue_summary(obj)["issue_messages"]

    class Meta:
        model = PayrollRunEmployee
        fields = [
            "id",
            "employee_profile",
            "payroll_profile_id",
            "employee_id",
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
            "salary_structure_id",
            "salary_structure_version",
            "ledger_policy_version",
            "statutory_policy_version_ref",
            "calculation_assumptions",
            "warning_count",
            "blocking_issue_count",
            "issue_messages",
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
    actors = serializers.SerializerMethodField()
    traceability = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()
    employee_rows = serializers.SerializerMethodField()
    component_totals = serializers.SerializerMethodField()
    posting_verification_issues = serializers.SerializerMethodField()
    payment_verification_issues = serializers.SerializerMethodField()

    def _traceability(self, obj):
        cache = self.context.setdefault("_payroll_traceability_cache", {})
        if obj.id not in cache:
            cache[obj.id] = PayrollTraceabilityService.build_traceability(run=obj)
        return cache[obj.id]

    def get_actors(self, obj):
        return PayrollTraceabilityService.build_actor_summary(run=obj)

    def get_traceability(self, obj):
        return self._traceability(obj)

    def get_timeline(self, obj):
        return PayrollTraceabilityService.build_timeline(run=obj)

    def get_employee_rows(self, obj):
        return PayrollTraceabilityService.build_employee_rows(run=obj)

    def get_component_totals(self, obj):
        return PayrollTraceabilityService.build_component_totals(run=obj)

    def get_posting_verification_issues(self, obj):
        return self._traceability(obj)["posting"]["verification_issues"]

    def get_payment_verification_issues(self, obj):
        return self._traceability(obj)["payment"]["verification_issues"]

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
            "actors",
            "traceability",
            "timeline",
            "employee_rows",
            "component_totals",
            "posting_verification_issues",
            "payment_verification_issues",
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
    actors = serializers.JSONField(required=False)
    traceability = serializers.JSONField(required=False)
    timeline = serializers.JSONField(required=False)
    employee_rows = serializers.JSONField(required=False)
    component_totals = serializers.JSONField(required=False)
    posting_verification_issues = serializers.JSONField(required=False)
    payment_verification_issues = serializers.JSONField(required=False)


class PayslipSerializer(serializers.ModelSerializer):
    employee_code = serializers.CharField(source="payroll_run_employee.employee_profile.employee_code", read_only=True)
    employee_name = serializers.CharField(source="payroll_run_employee.employee_profile.full_name", read_only=True)
    payroll_profile_id = serializers.IntegerField(source="payroll_run_employee.employee_profile_id", read_only=True)
    salary_structure_id = serializers.IntegerField(source="payroll_run_employee.salary_structure_id", read_only=True)
    earnings = serializers.SerializerMethodField()
    deductions = serializers.SerializerMethodField()
    employer_contributions = serializers.SerializerMethodField()
    section_totals = serializers.SerializerMethodField()
    metadata = serializers.SerializerMethodField()
    calculation_notes = serializers.SerializerMethodField()
    calculation_flags = serializers.SerializerMethodField()

    def _sections(self, obj):
        cache = self.context.setdefault("_payslip_traceability_cache", {})
        if obj.id not in cache:
            cache[obj.id] = PayrollTraceabilityService.build_payslip_sections(payslip=obj)
        return cache[obj.id]

    def get_earnings(self, obj):
        return self._sections(obj)["earnings"]

    def get_deductions(self, obj):
        return self._sections(obj)["deductions"]

    def get_employer_contributions(self, obj):
        return self._sections(obj)["employer_contributions"]

    def get_section_totals(self, obj):
        return self._sections(obj)["section_totals"]

    def get_metadata(self, obj):
        return obj.payload or {}

    def get_calculation_notes(self, obj):
        payload = obj.payload or {}
        return payload.get("calculation_notes") or obj.payroll_run_employee.calculation_payload.get("notes") or []

    def get_calculation_flags(self, obj):
        payload = obj.payload or {}
        return payload.get("calculation_flags") or payload.get("flags") or []

    class Meta:
        model = Payslip
        fields = [
            "id",
            "payslip_number",
            "payroll_profile_id",
            "salary_structure_id",
            "employee_code",
            "employee_name",
            "generated_at",
            "published_at",
            "earnings",
            "deductions",
            "employer_contributions",
            "section_totals",
            "metadata",
            "calculation_notes",
            "calculation_flags",
            "payload",
        ]
