from __future__ import annotations

import json

from django.contrib import admin
from django.db.models import Count, Max
from django.utils.html import format_html

from payroll.models import (
    PayrollAdjustment,
    PayrollComponent,
    PayrollComponentPosting,
    PayrollEmployeeProfile,
    PayrollLedgerPolicy,
    PayrollPeriod,
    PayrollRun,
    PayrollRunActionLog,
    PayrollRunEmployee,
    PayrollRunEmployeeComponent,
    Payslip,
    SalaryStructure,
    SalaryStructureLine,
    SalaryStructureVersion,
)
from payroll.services.payroll_export_service import PayrollExportService
from payroll.services.payroll_traceability_service import PayrollTraceabilityService


def _pretty_json(payload) -> str:
    if not payload:
        return "-"
    try:
        text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    except TypeError:
        text = str(payload)
    return format_html("<pre style='white-space: pre-wrap; max-width: 1100px;'>{}</pre>", text)


def _existing_fields(model, *names):
    concrete = {field.name for field in model._meta.get_fields()}
    return tuple(name for name in names if name in concrete)


class ReadOnlyInlineMixin:
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SalaryStructureLineInline(admin.TabularInline):
    model = SalaryStructureLine
    extra = 0
    autocomplete_fields = ("component", "basis_component")
    fields = (
        "sequence",
        "component",
        "calculation_basis",
        "basis_component",
        "rate",
        "fixed_amount",
        "is_pro_rated",
        "is_override_allowed",
        "is_active",
    )


class SalaryStructureVersionInline(admin.TabularInline):
    model = SalaryStructureVersion
    extra = 0
    fields = ("version_no", "effective_from", "effective_to", "status", "approved_by", "approved_at", "notes")
    readonly_fields = ("approved_at",)
    raw_id_fields = ("approved_by",)
    show_change_link = True


class PayrollRunEmployeeComponentInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = PayrollRunEmployeeComponent
    fields = (
        "sequence",
        "component_code",
        "component_name",
        "component_type",
        "posting_behavior",
        "amount",
        "taxable_amount",
        "is_employer_cost",
        "component_posting_version",
        "source_structure_line",
    )
    readonly_fields = fields
    raw_id_fields = ("component_posting_version", "source_structure_line")
    ordering = ("sequence", "id")


class PayslipInline(ReadOnlyInlineMixin, admin.StackedInline):
    model = Payslip
    fields = (
        "payslip_number",
        "version_no",
        "generated_at",
        "published_at",
        "published_by",
        "voided_at",
        "void_reason",
        "payload_pretty",
    )
    readonly_fields = fields
    raw_id_fields = ("published_by",)

    @admin.display(description="Payload")
    def payload_pretty(self, obj):
        return _pretty_json(getattr(obj, "payload", {}))


class PayrollRunEmployeeInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = PayrollRunEmployee
    fields = (
        "employee_profile",
        "status",
        "payment_status",
        "gross_amount",
        "deduction_amount",
        "employer_contribution_amount",
        "reimbursement_amount",
        "payable_amount",
        "issue_counts",
    )
    readonly_fields = fields
    raw_id_fields = ("employee_profile",)

    @admin.display(description="Issues")
    def issue_counts(self, obj):
        summary = PayrollTraceabilityService.build_employee_issue_summary(row=obj)
        return f"B:{summary['blocking_issue_count']} / W:{summary['warning_count']}"


class PayrollRunActionLogInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = PayrollRunActionLog
    fields = (
        "created_at",
        "action",
        "acted_by",
        "old_status",
        "new_status",
        "old_payment_status",
        "new_payment_status",
        "reason_code",
        "comment",
        "payload_pretty",
    )
    readonly_fields = fields
    raw_id_fields = ("acted_by",)
    ordering = ("-created_at", "-id")

    @admin.display(description="Payload")
    def payload_pretty(self, obj):
        return _pretty_json(obj.payload)


@admin.register(PayrollComponent)
class PayrollComponentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "entity",
        "code",
        "name",
        "component_type",
        "posting_behavior",
        "is_taxable",
        "is_statutory",
        "affects_net_pay",
        "is_active",
    )
    list_filter = ("entity", "component_type", "posting_behavior", "is_active", "is_taxable", "is_statutory")
    search_fields = ("code", "name", "description", "statutory_tag")
    raw_id_fields = ("entity",)
    readonly_fields = _existing_fields(
        PayrollComponent,
        "created_at",
        "updated_at",
    )
    ordering = ("entity_id", "default_sequence", "code")
    save_on_top = True


@admin.register(PayrollComponentPosting)
class PayrollComponentPostingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "entity",
        "entityfinid",
        "subentity",
        "component",
        "version_no",
        "effective_from",
        "effective_to",
        "expense_account",
        "liability_account",
        "payable_account",
        "is_active",
    )
    list_filter = ("entity", "entityfinid", "subentity", "is_active", "effective_from")
    search_fields = ("component__code", "component__name", "notes")
    raw_id_fields = (
        "entity",
        "entityfinid",
        "subentity",
        "component",
        "expense_account",
        "liability_account",
        "payable_account",
        "approved_by",
        "superseded_by",
    )
    readonly_fields = _existing_fields(PayrollComponentPosting, "created_at", "updated_at", "approved_at")
    list_select_related = ("entity", "entityfinid", "subentity", "component")
    ordering = ("entity_id", "component__code", "-version_no")
    save_on_top = True


@admin.register(SalaryStructure)
class SalaryStructureAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "entity",
        "entityfinid",
        "subentity",
        "code",
        "name",
        "status",
        "current_version",
        "is_active",
        "is_template",
    )
    list_filter = ("entity", "entityfinid", "subentity", "status", "is_active", "is_template")
    search_fields = ("code", "name", "notes")
    raw_id_fields = ("entity", "entityfinid", "subentity", "current_version")
    readonly_fields = _existing_fields(SalaryStructure, "created_at", "updated_at")
    inlines = [SalaryStructureVersionInline]
    list_select_related = ("entity", "entityfinid", "subentity", "current_version")
    ordering = ("entity_id", "code")
    save_on_top = True


@admin.register(SalaryStructureVersion)
class SalaryStructureVersionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "salary_structure",
        "version_no",
        "effective_from",
        "effective_to",
        "status",
        "approved_by",
        "approved_at",
    )
    list_filter = ("status", "effective_from")
    search_fields = ("salary_structure__code", "salary_structure__name", "notes")
    raw_id_fields = ("salary_structure", "approved_by")
    readonly_fields = _existing_fields(SalaryStructureVersion, "created_at", "updated_at", "approved_at", "calculation_policy_pretty")
    fields = (
        "salary_structure",
        "version_no",
        "effective_from",
        "effective_to",
        "status",
        "approved_by",
        "approved_at",
        "notes",
        "calculation_policy_pretty",
    )
    inlines = [SalaryStructureLineInline]
    list_select_related = ("salary_structure", "approved_by")
    ordering = ("salary_structure_id", "-version_no")
    save_on_top = True

    @admin.display(description="Calculation Policy")
    def calculation_policy_pretty(self, obj):
        return _pretty_json(obj.calculation_policy_json)


@admin.register(PayrollEmployeeProfile)
class PayrollEmployeeProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "entity",
        "entityfinid",
        "subentity",
        "employee_code",
        "full_name",
        "status",
        "salary_structure",
        "salary_structure_version",
        "pay_frequency",
        "blocked_for_payroll",
        "locked_for_processing",
    )
    list_filter = (
        "entity",
        "entityfinid",
        "subentity",
        "status",
        "blocked_for_payroll",
        "locked_for_processing",
        "pay_frequency",
    )
    search_fields = ("employee_code", "full_name", "work_email", "pan", "uan")
    raw_id_fields = (
        "entity",
        "entityfinid",
        "subentity",
        "employee_user",
        "salary_structure",
        "salary_structure_version",
        "payment_account",
    )
    readonly_fields = _existing_fields(PayrollEmployeeProfile, "created_at", "updated_at", "extra_data_pretty")
    fieldsets = (
        ("Core Profile", {"fields": ("entity", "entityfinid", "subentity", "employee_user", "employee_code", "full_name", "work_email")}),
        ("Payroll Setup", {"fields": ("status", "salary_structure", "salary_structure_version", "ctc_annual", "payment_account", "tax_regime", "pay_frequency")}),
        ("Operational Flags", {"fields": ("blocked_for_payroll", "locked_for_processing", "effective_from", "effective_to")}),
        ("Identity", {"fields": ("pan", "uan", "date_of_joining")}),
        ("Metadata", {"classes": ("collapse",), "fields": ("extra_data_pretty", "created_at", "updated_at")}),
    )
    list_select_related = ("entity", "entityfinid", "subentity", "salary_structure", "salary_structure_version")
    ordering = ("entity_id", "employee_code")
    save_on_top = True

    @admin.display(description="Extra Data")
    def extra_data_pretty(self, obj):
        return _pretty_json(obj.extra_data)


@admin.register(PayrollLedgerPolicy)
class PayrollLedgerPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "entity",
        "entityfinid",
        "subentity",
        "policy_code",
        "version_no",
        "effective_from",
        "effective_to",
        "salary_payable_account",
        "is_active",
    )
    list_filter = ("entity", "entityfinid", "subentity", "is_active", "effective_from")
    search_fields = ("policy_code",)
    raw_id_fields = (
        "entity",
        "entityfinid",
        "subentity",
        "salary_payable_account",
        "payroll_clearing_account",
        "reimbursement_payable_account",
        "employer_contribution_payable_account",
        "approved_by",
        "superseded_by",
    )
    readonly_fields = _existing_fields(PayrollLedgerPolicy, "created_at", "updated_at", "approved_at", "policy_json_pretty")
    fieldsets = (
        ("Scope", {"fields": ("entity", "entityfinid", "subentity", "policy_code", "version_no", "is_active")}),
        ("Accounts", {"fields": ("salary_payable_account", "payroll_clearing_account", "reimbursement_payable_account", "employer_contribution_payable_account")}),
        ("Effective Dating", {"fields": ("effective_from", "effective_to", "approved_by", "approved_at", "superseded_by")}),
        ("Policy Metadata", {"classes": ("collapse",), "fields": ("policy_json_pretty", "created_at", "updated_at")}),
    )
    list_select_related = ("entity", "entityfinid", "subentity")
    ordering = ("entity_id", "entityfinid_id", "subentity_id", "-version_no")
    save_on_top = True

    @admin.display(description="Policy JSON")
    def policy_json_pretty(self, obj):
        return _pretty_json(obj.policy_json)


@admin.register(PayrollPeriod)
class PayrollPeriodAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "entity",
        "entityfinid",
        "subentity",
        "code",
        "pay_frequency",
        "period_start",
        "period_end",
        "payout_date",
        "status",
        "locked_at",
        "closed_at",
    )
    list_filter = ("entity", "entityfinid", "subentity", "status", "pay_frequency")
    search_fields = ("code",)
    raw_id_fields = ("entity", "entityfinid", "subentity", "locked_by", "submitted_for_close_by", "closed_by")
    readonly_fields = _existing_fields(PayrollPeriod, "created_at", "updated_at")
    date_hierarchy = "period_start"
    list_select_related = ("entity", "entityfinid", "subentity")
    ordering = ("-period_start", "-id")
    save_on_top = True


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "run_reference",
        "entity",
        "subentity",
        "payroll_period",
        "status",
        "payment_status",
        "reversed_flag",
        "employee_count",
        "gross_amount",
        "deduction_amount",
        "net_pay_amount",
        "created_at",
        "latest_activity_at",
    )
    list_filter = (
        "status",
        "payment_status",
        "entity",
        "subentity",
        "payroll_period",
        "created_at",
        "approved_at",
        "posted_at",
        "reversed_at",
        "run_type",
    )
    search_fields = (
        "run_number",
        "doc_code",
        "doc_no",
        "entity__entityname",
        "subentity__subentityname",
        "payroll_period__code",
        "post_reference",
        "payment_batch_ref",
        "status_comment",
        "reversal_reason",
        "action_logs__comment",
        "action_logs__reason_code",
    )
    raw_id_fields = (
        "entity",
        "entityfinid",
        "subentity",
        "payroll_period",
        "ledger_policy_version",
        "correction_of_run",
        "reversed_run",
        "created_by",
        "submitted_by",
        "approved_by",
        "locked_by",
        "posted_by",
        "cancelled_by",
        "reversed_by",
    )
    readonly_fields = (
        "run_reference",
        "latest_activity_at",
        "posting_summary",
        "payment_summary",
        "reversal_summary",
        "issue_summary",
        "timeline_summary",
        "calculation_payload_pretty",
        "config_snapshot_pretty",
        "payment_handoff_payload_pretty",
        *_existing_fields(
            PayrollRun,
            "created_at",
            "updated_at",
            "submitted_at",
            "approved_at",
            "locked_at",
            "posted_at",
            "cancelled_at",
            "reversed_at",
        ),
    )
    fieldsets = (
        (
            "Core Run Info",
            {
                "fields": (
                    ("id", "run_reference"),
                    ("run_type", "doc_code", "doc_no", "run_number"),
                    ("posting_date", "payout_date"),
                )
            },
        ),
        (
            "Scope",
            {
                "fields": (
                    ("entity", "entityfinid", "subentity"),
                    ("payroll_period", "ledger_policy_version"),
                )
            },
        ),
        (
            "Workflow Status / Audit",
            {
                "fields": (
                    ("status", "payment_status", "is_immutable"),
                    ("created_by", "created_at"),
                    ("submitted_by", "submitted_at"),
                    ("approved_by", "approved_at"),
                    ("locked_by", "locked_at"),
                    ("posted_by", "posted_at"),
                    ("cancelled_by", "cancelled_at"),
                    ("reversed_by", "reversed_at"),
                    ("approval_note", "status_reason_code"),
                    ("status_comment", "latest_activity_at"),
                    "timeline_summary",
                )
            },
        ),
        (
            "Financial Totals",
            {
                "fields": (
                    ("employee_count", "gross_amount", "deduction_amount"),
                    ("employer_contribution_amount", "reimbursement_amount", "net_pay_amount"),
                    "issue_summary",
                )
            },
        ),
        (
            "Posting Traceability",
            {
                "fields": (
                    ("posted_entry_id", "post_reference"),
                    "posting_summary",
                )
            },
        ),
        (
            "Payment Traceability",
            {
                "fields": (
                    ("payment_batch_ref", "payment_handed_off_at", "payment_reconciled_at"),
                    "payment_summary",
                )
            },
        ),
        (
            "Reversal / Correction",
            {
                "fields": (
                    ("correction_of_run", "reversed_run"),
                    ("reversal_reason", "reversal_posting_entry_id"),
                    "reversal_summary",
                )
            },
        ),
        (
            "Raw Metadata",
            {
                "classes": ("collapse",),
                "fields": (
                    "calculation_payload_pretty",
                    "config_snapshot_pretty",
                    "payment_handoff_payload_pretty",
                ),
            },
        ),
    )
    inlines = [PayrollRunEmployeeInline, PayrollRunActionLogInline]
    list_select_related = (
        "entity",
        "entityfinid",
        "subentity",
        "payroll_period",
        "created_by",
        "submitted_by",
        "approved_by",
        "posted_by",
        "reversed_by",
    )
    date_hierarchy = "posting_date"
    ordering = ("-posting_date", "-id")
    save_on_top = True
    show_full_result_count = False
    actions = ("export_run_register_csv", "export_component_totals_csv", "export_deduction_summary_csv")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(*self.list_select_related)
            .annotate(
                latest_action_at=Max("action_logs__created_at"),
                action_count=Count("action_logs", distinct=True),
                reversal_run_count=Count("reversal_runs", distinct=True),
            )
        )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if not obj:
            return readonly
        if obj.status in {PayrollRun.Status.APPROVED, PayrollRun.Status.POSTED, PayrollRun.Status.CANCELLED, PayrollRun.Status.REVERSED}:
            readonly.extend(
                [
                    "entity",
                    "entityfinid",
                    "subentity",
                    "payroll_period",
                    "run_type",
                    "doc_code",
                    "doc_no",
                    "run_number",
                    "posting_date",
                    "payout_date",
                    "employee_count",
                    "gross_amount",
                    "deduction_amount",
                    "employer_contribution_amount",
                    "reimbursement_amount",
                    "net_pay_amount",
                    "ledger_policy_version",
                    "calculation_payload",
                    "config_snapshot",
                    "reversed_run",
                    "correction_of_run",
                ]
            )
        if obj.payment_status != PayrollRun.PaymentStatus.NOT_READY:
            readonly.extend(["payment_status", "payment_batch_ref", "payment_handoff_payload"])
        return tuple(dict.fromkeys(readonly))

    @admin.display(description="Run")
    def run_reference(self, obj):
        return obj.run_number or f"{obj.doc_code}-{obj.doc_no or obj.id}"

    @admin.display(description="Reversed", boolean=True)
    def reversed_flag(self, obj):
        return obj.status == PayrollRun.Status.REVERSED or getattr(obj, "reversal_run_count", 0) > 0 or bool(obj.reversed_run_id)

    @admin.display(description="Latest activity")
    def latest_activity_at(self, obj):
        candidates = [
            getattr(obj, "latest_action_at", None),
            obj.reversed_at,
            obj.posted_at,
            obj.approved_at,
            obj.submitted_at,
            obj.created_at,
        ]
        candidates = [value for value in candidates if value is not None]
        return max(candidates) if candidates else None

    @admin.display(description="Posting summary")
    def posting_summary(self, obj):
        traceability = PayrollTraceabilityService.build_traceability(run=obj)
        posting = traceability["posting"]
        issues = posting["verification_issues"]
        lines = [
            f"Status: {posting['status']}",
            f"Reference: {posting['posting_reference'] or '-'}",
            f"Entry ID: {posting['posting_entry_id'] or '-'}",
            f"Posted by: {(posting['posted_by'] or {}).get('user_name', '-')}",
        ]
        if issues:
            lines.append("Issues:")
            lines.extend([f"- [{item['severity']}] {item['message']}" for item in issues])
        return format_html("<pre style='white-space: pre-wrap'>{}</pre>", "\n".join(lines))

    @admin.display(description="Payment summary")
    def payment_summary(self, obj):
        traceability = PayrollTraceabilityService.build_traceability(run=obj)
        payment = traceability["payment"]
        issues = payment["verification_issues"]
        lines = [
            f"Status: {payment['status']}",
            f"Handoff ref: {payment['handoff_reference'] or '-'}",
            f"Reconciliation ref: {payment['reconciliation_reference'] or '-'}",
            f"Processed by: {(payment['processed_by'] or {}).get('user_name', '-')}",
        ]
        if issues:
            lines.append("Issues:")
            lines.extend([f"- [{item['severity']}] {item['message']}" for item in issues])
        return format_html("<pre style='white-space: pre-wrap'>{}</pre>", "\n".join(lines))

    @admin.display(description="Reversal summary")
    def reversal_summary(self, obj):
        reversal = PayrollTraceabilityService.build_traceability(run=obj)["reversal"]
        lines = [
            f"Status: {reversal['status']}",
            f"Original run: {reversal['original_run_reference'] or '-'}",
            f"Reversing run: {reversal['reversing_run_reference'] or '-'}",
            f"Reason: {reversal['reason'] or '-'}",
            f"Posting ref: {reversal['reversal_posting_reference'] or '-'}",
        ]
        return format_html("<pre style='white-space: pre-wrap'>{}</pre>", "\n".join(lines))

    @admin.display(description="Warnings / blockers")
    def issue_summary(self, obj):
        warnings = 0
        blockers = 0
        for row in obj.employee_runs.select_related("employee_profile").prefetch_related("components").all()[:200]:
            summary = PayrollTraceabilityService.build_employee_issue_summary(row=row)
            warnings += summary["warning_count"]
            blockers += summary["blocking_issue_count"]
        return f"Blocking: {blockers} | Warning: {warnings}"

    @admin.display(description="Latest timeline")
    def timeline_summary(self, obj):
        timeline = PayrollTraceabilityService.build_timeline(run=obj)
        if not timeline:
            return "-"
        lines = []
        for item in timeline[-6:]:
            actor = (item["actor"] or {}).get("user_name", "-")
            lines.append(f"{item['occurred_at']}: {item['label']} [{actor}]")
        return format_html("<pre style='white-space: pre-wrap'>{}</pre>", "\n".join(lines))

    @admin.display(description="Calculation payload")
    def calculation_payload_pretty(self, obj):
        return _pretty_json(obj.calculation_payload)

    @admin.display(description="Config snapshot")
    def config_snapshot_pretty(self, obj):
        return _pretty_json(obj.config_snapshot)

    @admin.display(description="Payment handoff payload")
    def payment_handoff_payload_pretty(self, obj):
        return _pretty_json(obj.payment_handoff_payload)

    @admin.action(description="Export selected payroll runs as CSV register")
    def export_run_register_csv(self, request, queryset):
        queryset = queryset.select_related("entity", "entityfinid", "subentity", "payroll_period")
        return PayrollExportService.export_run_register(runs=queryset)

    @admin.action(description="Export selected payroll component totals as CSV")
    def export_component_totals_csv(self, request, queryset):
        queryset = queryset.prefetch_related("employee_runs__components")
        return PayrollExportService.export_component_totals(runs=queryset)

    @admin.action(description="Export selected payroll deduction summary as CSV")
    def export_deduction_summary_csv(self, request, queryset):
        return PayrollExportService.export_deduction_summary(runs=queryset)


@admin.register(PayrollRunEmployee)
class PayrollRunEmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "payroll_run",
        "employee_profile",
        "status",
        "payment_status",
        "gross_amount",
        "deduction_amount",
        "employer_contribution_amount",
        "payable_amount",
        "is_frozen",
    )
    list_filter = ("status", "payment_status", "is_frozen", "payroll_run__entity", "payroll_run__subentity")
    search_fields = (
        "payroll_run__run_number",
        "employee_profile__employee_code",
        "employee_profile__full_name",
        "remarks",
    )
    raw_id_fields = ("payroll_run", "employee_profile", "salary_structure", "salary_structure_version", "ledger_policy_version")
    readonly_fields = (
        "issue_summary",
        "calculation_payload_pretty",
        "calculation_assumptions_pretty",
        *_existing_fields(PayrollRunEmployee, "created_at", "updated_at"),
    )
    fieldsets = (
        ("Core", {"fields": ("payroll_run", "employee_profile", "status", "payment_status", "is_frozen")}),
        ("Amounts", {"fields": ("gross_amount", "deduction_amount", "employer_contribution_amount", "reimbursement_amount", "payable_amount")}),
        ("Config Snapshot", {"fields": ("salary_structure", "salary_structure_version", "ledger_policy_version", "statutory_policy_version_ref")}),
        ("Operational Notes", {"fields": ("remarks", "issue_summary")}),
        ("Metadata", {"classes": ("collapse",), "fields": ("calculation_payload_pretty", "calculation_assumptions_pretty", "created_at", "updated_at")}),
    )
    inlines = [PayrollRunEmployeeComponentInline, PayslipInline]
    list_select_related = ("payroll_run", "employee_profile", "salary_structure", "salary_structure_version", "ledger_policy_version")
    ordering = ("-payroll_run_id", "employee_profile__employee_code")
    save_on_top = True
    show_full_result_count = False
    actions = ("export_selected_employee_rows_csv",)

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj and (obj.is_frozen or obj.payroll_run.status in {PayrollRun.Status.APPROVED, PayrollRun.Status.POSTED, PayrollRun.Status.REVERSED}):
            readonly.extend(
                [
                    "payroll_run",
                    "employee_profile",
                    "salary_structure",
                    "salary_structure_version",
                    "ledger_policy_version",
                    "status",
                    "payment_status",
                    "gross_amount",
                    "deduction_amount",
                    "employer_contribution_amount",
                    "reimbursement_amount",
                    "payable_amount",
                    "remarks",
                    "statutory_policy_version_ref",
                ]
            )
        return tuple(dict.fromkeys(readonly))

    @admin.display(description="Issues")
    def issue_summary(self, obj):
        summary = PayrollTraceabilityService.build_employee_issue_summary(row=obj)
        lines = [f"Blocking: {summary['blocking_issue_count']}", f"Warning: {summary['warning_count']}"]
        if summary["issue_messages"]:
            lines.extend([f"- {message}" for message in summary["issue_messages"]])
        return format_html("<pre style='white-space: pre-wrap'>{}</pre>", "\n".join(lines))

    @admin.display(description="Calculation payload")
    def calculation_payload_pretty(self, obj):
        return _pretty_json(obj.calculation_payload)

    @admin.display(description="Calculation assumptions")
    def calculation_assumptions_pretty(self, obj):
        return _pretty_json(obj.calculation_assumptions)

    @admin.action(description="Export selected payroll employee rows as CSV")
    def export_selected_employee_rows_csv(self, request, queryset):
        queryset = queryset.select_related("payroll_run", "employee_profile")
        return PayrollExportService.export_employee_rows(rows=queryset)


@admin.register(PayrollAdjustment)
class PayrollAdjustmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "entity",
        "entityfinid",
        "subentity",
        "employee_profile",
        "kind",
        "amount",
        "effective_date",
        "status",
        "approved_run",
    )
    list_filter = ("entity", "entityfinid", "subentity", "kind", "status", "effective_date")
    search_fields = ("employee_profile__employee_code", "employee_profile__full_name", "remarks", "source_reference_id")
    raw_id_fields = (
        "entity",
        "entityfinid",
        "subentity",
        "employee_profile",
        "payroll_period",
        "component",
        "approved_by",
        "approved_run",
        "reversed_adjustment",
    )
    readonly_fields = _existing_fields(PayrollAdjustment, "created_at", "updated_at", "approved_at")
    list_select_related = ("entity", "entityfinid", "subentity", "employee_profile", "approved_run")
    ordering = ("-effective_date", "-id")
    save_on_top = True


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "payslip_number",
        "payroll_run_reference",
        "employee_code",
        "version_no",
        "generated_at",
        "published_at",
        "voided_at",
    )
    list_filter = ("generated_at", "published_at", "voided_at")
    search_fields = (
        "payslip_number",
        "payroll_run_employee__employee_profile__employee_code",
        "payroll_run_employee__employee_profile__full_name",
        "payroll_run_employee__payroll_run__run_number",
    )
    raw_id_fields = ("payroll_run_employee", "published_by")
    readonly_fields = (
        "employee_code",
        "payroll_run_reference",
        "payload_pretty",
        *_existing_fields(Payslip, "created_at", "updated_at", "generated_at"),
    )
    fieldsets = (
        ("Core", {"fields": ("payslip_number", "payroll_run_employee", "payroll_run_reference", "employee_code", "version_no")}),
        ("Publication", {"fields": ("generated_at", "published_at", "published_by", "voided_at", "void_reason")}),
        ("Payload", {"classes": ("collapse",), "fields": ("payload_pretty", "payload")}),
    )
    list_select_related = ("payroll_run_employee__employee_profile", "payroll_run_employee__payroll_run")
    ordering = ("-generated_at", "-id")
    date_hierarchy = "generated_at"
    show_full_result_count = False

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj:
            readonly.extend(["payroll_run_employee", "payslip_number", "version_no", "payload"])
        return tuple(dict.fromkeys(readonly))

    @admin.display(description="Run")
    def payroll_run_reference(self, obj):
        run = obj.payroll_run_employee.payroll_run
        return run.run_number or f"{run.doc_code}-{run.doc_no or run.id}"

    @admin.display(description="Employee")
    def employee_code(self, obj):
        return obj.payroll_run_employee.employee_profile.employee_code

    @admin.display(description="Payload")
    def payload_pretty(self, obj):
        return _pretty_json(obj.payload)


@admin.register(PayrollRunActionLog)
class PayrollRunActionLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "payroll_run",
        "action",
        "old_status",
        "new_status",
        "old_payment_status",
        "new_payment_status",
        "acted_by",
        "created_at",
    )
    list_filter = ("action", "new_status", "new_payment_status", "created_at")
    search_fields = ("payroll_run__run_number", "comment", "reason_code")
    raw_id_fields = ("payroll_run", "acted_by")
    readonly_fields = (
        "payroll_run",
        "action",
        "old_status",
        "new_status",
        "old_payment_status",
        "new_payment_status",
        "acted_by",
        "reason_code",
        "comment",
        "payload_pretty",
        *_existing_fields(PayrollRunActionLog, "created_at", "updated_at"),
    )
    fields = readonly_fields
    list_select_related = ("payroll_run", "acted_by")
    ordering = ("-created_at", "-id")
    date_hierarchy = "created_at"
    show_full_result_count = False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Payload")
    def payload_pretty(self, obj):
        return _pretty_json(obj.payload)
