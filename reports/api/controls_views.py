from __future__ import annotations

from django.http import HttpResponse
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from core.entitlements import ScopedEntitlementMixin
from reports.api.financial.export_utils import ExportSection, write_sectioned_csv, write_sectioned_pdf
from reports.api.report_permissions import assert_any_report_permission
from subscriptions.services import SubscriptionLimitCodes, SubscriptionService

from reports.services.controls.phase_one import build_phase_one_controls_hub
from reports.services.controls.opening_setup import apply_posting_setup, build_posting_setup_preview
from reports.services.controls.opening_generation import build_opening_generation, build_opening_generation_rollback, lock_opening_generation, mark_opening_lifecycle
from reports.services.controls.opening_policy import resolve_opening_policy, summarize_opening_policy, update_opening_policy
from reports.services.controls.opening_preview import build_opening_preview
from reports.services.controls.approval_workflow import (
    build_approval_workflow_readiness,
    resolve_approval_workflow_policy,
    summarize_approval_workflow_policy,
    update_approval_workflow_policy,
)
from reports.services.controls.audit_trail import (
    build_audit_trail_readiness,
    build_controls_audit_activity,
    record_controls_audit_event,
    resolve_audit_trail_policy,
    summarize_audit_trail_policy,
    update_audit_trail_policy,
)
from reports.services.controls.attachment_vault import (
    build_attachment_vault_readiness,
    resolve_attachment_vault_policy,
    summarize_attachment_vault_policy,
    update_attachment_vault_policy,
)
from reports.services.controls.close_checklist import update_close_checklist_item
from reports.services.controls.evidence_pack import (
    create_evidence_pack_snapshot,
    get_evidence_pack_snapshot,
    list_evidence_pack_snapshots,
    update_evidence_pack_review,
)
from reports.services.controls.perf import controls_scope_fields, profile_controls_block
from reports.services.controls.recurring_journals import (
    build_recurring_journal_readiness,
    mark_recurring_journal_run,
    resolve_recurring_journal_policy,
    summarize_recurring_journal_policy,
    update_recurring_journal_policy,
)


class ControlsPermissionMixin:
    required_permission_codes: tuple[str, ...] = ()
    permission_denied_message = "You do not have permission to access this controls workspace."

    def enforce_report_permission(self, request, *, entity_id: int, required_permissions=None, message=None):
        assert_any_report_permission(
            user=request.user,
            entity_id=entity_id,
            required_permissions=required_permissions or self.required_permission_codes,
            message=message or self.permission_denied_message,
        )


class PhaseOneControlsScopeSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)


class PhaseOneAuditPackExportSerializer(PhaseOneControlsScopeSerializer):
    format = serializers.ChoiceField(choices=["csv", "pdf"], default="csv")
    snapshot_id = serializers.IntegerField(required=False, allow_null=True)


class PhaseOneAuditActivitySerializer(PhaseOneControlsScopeSerializer):
    module = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    user = serializers.IntegerField(required=False, allow_null=True)
    date_from = serializers.DateField(required=False, allow_null=True)
    date_to = serializers.DateField(required=False, allow_null=True)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=200, default=50)


class PhaseOneAuditActivityExportSerializer(PhaseOneAuditActivitySerializer):
    format = serializers.ChoiceField(choices=["csv", "pdf"], default="csv")


class PhaseOneEvidencePackSnapshotSerializer(PhaseOneControlsScopeSerializer):
    entityfinid = serializers.IntegerField()
    include_payload = serializers.BooleanField(required=False, default=False)


class PhaseOneEvidencePackReviewSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    snapshot_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["prepared", "reviewed", "approved"])
    comment = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class PhaseOneCloseChecklistItemSerializer(PhaseOneControlsScopeSerializer):
    item_key = serializers.CharField()
    status = serializers.ChoiceField(choices=["review", "done"])
    comment = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class PhaseOneControlsHubAPIView(ControlsPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PhaseOneControlsScopeSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.controls_phase_one.view",)
    permission_denied_message = "You do not have permission to access the controls hub."

    def get(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(request, entity_id=scope["entity"])
        with profile_controls_block(
            "controls.phase_one.hub",
            **controls_scope_fields(request=request, entity_id=scope["entity"], entityfin_id=scope.get("entityfinid"), subentity_id=scope.get("subentity")),
        ) as perf:
            payload = build_phase_one_controls_hub(
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
            )
            perf["status"] = payload.get("audit_pack", {}).get("status") or payload.get("report_code")
        return Response(payload)


class PhaseOneControlsAuditPackExportAPIView(ControlsPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PhaseOneAuditPackExportSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.controls_phase_one.view",)
    permission_denied_message = "You do not have permission to export the controls audit pack."

    def get(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(request, entity_id=scope["entity"])
        export_format = scope.get("format") or "csv"
        snapshot_meta = None
        with profile_controls_block(
            "controls.phase_one.audit_pack_export",
            **controls_scope_fields(
                request=request,
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
                export_format=export_format,
                snapshot_id=scope.get("snapshot_id"),
            ),
        ) as perf:
            if scope.get("snapshot_id"):
                snapshot_meta = get_evidence_pack_snapshot(snapshot_id=scope["snapshot_id"], entity_id=scope["entity"], include_payload=True)
                snapshot_payload = snapshot_meta.get("payload") or {}
                hub = snapshot_payload.get("hub") or {}
                audit_pack = snapshot_payload.get("audit_pack") or {}
            else:
                hub = build_phase_one_controls_hub(
                    entity_id=scope["entity"],
                    entityfin_id=scope.get("entityfinid"),
                    subentity_id=scope.get("subentity"),
                )
                audit_pack = hub.get("audit_pack") or {}
            perf["evidence_rows"] = len(audit_pack.get("evidence_rows") or [])
            perf["pack_status"] = audit_pack.get("status")
        rows = [
            [
                row.get("section") or "-",
                row.get("label") or "-",
                row.get("value") if row.get("value") not in (None, "") else "-",
                row.get("status") or "-",
                row.get("note") or "",
            ]
            for row in audit_pack.get("evidence_rows") or []
        ]
        section = ExportSection(
            title="Audit Evidence",
            headers=["Section", "Control", "Value", "Status", "Note"],
            rows=rows,
            center_columns={3},
            col_widths=[120, 170, 100, 70, 190],
            empty_message="No audit evidence is available.",
        )
        title = audit_pack.get("pack_name") or "Financial Controls Phase 1 Audit Pack"
        subtitle = f"{hub.get('entity_name') or 'Entity'} | {hub.get('entityfin_name') or 'Financial year'}"
        meta_items = [
            ("Status", audit_pack.get("status_label") or "-"),
            ("Generated At", audit_pack.get("generated_at") or hub.get("generated_at") or "-"),
            ("Entity", hub.get("entity_name") or "-"),
            ("Financial Year", hub.get("entityfin_name") or "-"),
            ("Subentity", hub.get("subentity_name") or "All"),
        ]
        if snapshot_meta:
            meta_items.extend(
                [
                    ("Evidence Version", f"v{snapshot_meta.get('version')}"),
                    ("Review Status", snapshot_meta.get("status_label") or "-"),
                    ("Snapshot Created At", snapshot_meta.get("generated_at") or "-"),
                ]
            )
        record_controls_audit_event(
            request=request,
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            module="audit_pack",
            action="audit_pack_exported",
            new_data={
                "format": export_format,
                "pack_code": audit_pack.get("pack_code"),
                "snapshot_id": scope.get("snapshot_id"),
                "version": snapshot_meta.get("version") if snapshot_meta else None,
                "status": audit_pack.get("status"),
                "evidence_rows": (audit_pack.get("summary") or {}).get("evidence_rows"),
            },
        )
        if export_format == "pdf":
            content = write_sectioned_pdf(title=title, subtitle=subtitle, meta_items=meta_items, sections=[section])
            response = HttpResponse(content, content_type="application/pdf")
            suffix = f"_v{snapshot_meta.get('version')}" if snapshot_meta else ""
            response["Content-Disposition"] = f'attachment; filename="financial_controls_phase_one_audit_pack{suffix}.pdf"'
            return response

        content = write_sectioned_csv(title=title, meta_items=meta_items, sections=[section])
        response = HttpResponse(content, content_type="text/csv")
        suffix = f"_v{snapshot_meta.get('version')}" if snapshot_meta else ""
        response["Content-Disposition"] = f'attachment; filename="financial_controls_phase_one_audit_pack{suffix}.csv"'
        return response


class PhaseOneEvidencePackSnapshotAPIView(ControlsPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PhaseOneEvidencePackSnapshotSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.controls_phase_one.view",)
    permission_denied_message = "You do not have permission to access controls evidence pack snapshots."

    def get(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(request, entity_id=scope["entity"])
        with profile_controls_block(
            "controls.phase_one.evidence_snapshots",
            **controls_scope_fields(request=request, entity_id=scope["entity"], entityfin_id=scope["entityfinid"], subentity_id=scope.get("subentity")),
        ) as perf:
            payload = list_evidence_pack_snapshots(
                entity_id=scope["entity"],
                entityfin_id=scope["entityfinid"],
                subentity_id=scope.get("subentity"),
                include_payload=scope.get("include_payload") or False,
            )
            perf["snapshots"] = payload.get("count")
        return Response(payload)

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(
            request,
            entity_id=scope["entity"],
            required_permissions=("reports.financial_hub.controls_phase_one.update_policy",),
            message="You do not have permission to create controls evidence pack snapshots.",
        )
        with profile_controls_block(
            "controls.phase_one.evidence_snapshot_create",
            **controls_scope_fields(request=request, entity_id=scope["entity"], entityfin_id=scope["entityfinid"], subentity_id=scope.get("subentity")),
        ) as perf:
            snapshot = create_evidence_pack_snapshot(
                entity_id=scope["entity"],
                entityfin_id=scope["entityfinid"],
                subentity_id=scope.get("subentity"),
                generated_by=request.user,
            )
            perf["version"] = snapshot.get("version")
            perf["pack_status"] = snapshot.get("pack_status")
        record_controls_audit_event(
            request=request,
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            module="audit_pack",
            action="audit_pack_snapshot_created",
            new_data={
                "snapshot_id": snapshot.get("id"),
                "version": snapshot.get("version"),
                "status": snapshot.get("status"),
                "pack_status": snapshot.get("pack_status"),
            },
        )
        return Response(snapshot, status=201)


class PhaseOneEvidencePackReviewAPIView(ControlsPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PhaseOneEvidencePackReviewSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.controls_phase_one.view",)
    permission_denied_message = "You do not have permission to review controls evidence pack snapshots."

    def patch(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        self.enforce_scope(request, entity_id=payload["entity"])
        self.enforce_report_permission(
            request,
            entity_id=payload["entity"],
            required_permissions=("reports.financial_hub.controls_phase_one.update_policy",),
            message="You do not have permission to review controls evidence pack snapshots.",
        )
        with profile_controls_block(
            "controls.phase_one.evidence_snapshot_review",
            **controls_scope_fields(request=request, entity_id=payload["entity"], snapshot_id=payload["snapshot_id"], review_status=payload["status"]),
        ) as perf:
            snapshot = update_evidence_pack_review(
                snapshot_id=payload["snapshot_id"],
                entity_id=payload["entity"],
                status=payload["status"],
                comment=payload.get("comment") or "",
                actor=request.user,
            )
            perf["version"] = snapshot.get("version")
        scope = snapshot.get("scope") or {}
        record_controls_audit_event(
            request=request,
            entity_id=payload["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            module="audit_pack",
            action="audit_pack_snapshot_reviewed",
            old_data={"status": snapshot.get("previous_status")},
            new_data={
                "snapshot_id": snapshot.get("id"),
                "version": snapshot.get("version"),
                "status": snapshot.get("status"),
            },
        )
        return Response(snapshot)


class PhaseOneCloseChecklistAPIView(ControlsPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PhaseOneCloseChecklistItemSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.controls_phase_one.view",)
    permission_denied_message = "You do not have permission to update close checklist controls."

    def patch(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity_id = scope["entity"]
        self.enforce_scope(
            request,
            entity_id=entity_id,
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(
            request,
            entity_id=entity_id,
            required_permissions=("reports.financial_hub.controls_phase_one.update_policy",),
            message="You do not have permission to update close checklist controls.",
        )
        result = update_close_checklist_item(
            entity_id=entity_id,
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            item_key=scope["item_key"],
            status=scope["status"],
            comment=scope.get("comment") or "",
            created_by=getattr(request, "user", None),
        )
        record_controls_audit_event(
            request=request,
            entity_id=entity_id,
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            module="year_end_close",
            action="close_checklist_updated",
            new_data={
                "item_key": scope["item_key"],
                "status": result.get("item", {}).get("status"),
                "requested_status": scope["status"],
                "comment": scope.get("comment") or "",
                "manual_override_applied": result.get("manual_override_applied"),
            },
        )
        return Response(result)


class OpeningPolicySerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    opening_mode = serializers.ChoiceField(choices=["single_batch", "grouped_batches", "hybrid"], required=False)
    batch_materialization = serializers.ChoiceField(choices=["single_batch", "grouped_batches", "hybrid"], required=False)
    opening_posting_date_strategy = serializers.ChoiceField(choices=["first_day_of_new_year", "manual"], required=False)
    require_closed_source_year = serializers.BooleanField(required=False)
    allow_partial_opening = serializers.BooleanField(required=False)
    opening_equity_static_account_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    opening_inventory_static_account_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    carry_forward = serializers.DictField(child=serializers.BooleanField(), required=False)
    reset = serializers.DictField(child=serializers.BooleanField(), required=False)
    grouped_sections = serializers.ListField(child=serializers.CharField(), required=False)


class RecurringJournalTemplateSerializer(serializers.Serializer):
    code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    frequency = serializers.ChoiceField(choices=["weekly", "monthly", "quarterly", "yearly"], required=False)
    status = serializers.ChoiceField(choices=["active", "paused", "failed"], required=False)
    next_run_date = serializers.DateField(required=False, allow_null=True)
    last_run_date = serializers.DateField(required=False, allow_null=True)
    amount = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    debit_account = serializers.IntegerField(required=False, allow_null=True)
    credit_account = serializers.IntegerField(required=False, allow_null=True)


class RecurringJournalPolicySerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    enabled = serializers.BooleanField(required=False)
    run_mode = serializers.ChoiceField(choices=["manual_review", "auto_draft", "auto_post"], required=False)
    auto_post_after_approval = serializers.BooleanField(required=False)
    require_attachment = serializers.BooleanField(required=False)
    default_frequency = serializers.ChoiceField(choices=["weekly", "monthly", "quarterly", "yearly"], required=False)
    templates = RecurringJournalTemplateSerializer(many=True, required=False)


class RecurringJournalRunSerializer(PhaseOneControlsScopeSerializer):
    run_date = serializers.DateField(required=False, allow_null=True)
    retry_failed = serializers.BooleanField(required=False, default=False)


class ApprovalThresholdSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    amount_from = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    amount_to = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    approver_role = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    required_approvals = serializers.IntegerField(required=False, min_value=1)


class ApprovalWorkflowPolicySerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    enabled = serializers.BooleanField(required=False)
    mode = serializers.ChoiceField(choices=["none", "maker_checker", "threshold"], required=False)
    default_approver_role = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    require_comment_on_reject = serializers.BooleanField(required=False)
    document_types = serializers.DictField(child=serializers.BooleanField(), required=False)
    thresholds = ApprovalThresholdSerializer(many=True, required=False)


class AuditTrailPolicySerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    enabled = serializers.BooleanField(required=False)
    retention_days = serializers.IntegerField(required=False, min_value=30, max_value=3650)
    capture_read_actions = serializers.BooleanField(required=False)
    capture_write_actions = serializers.BooleanField(required=False)
    export_enabled = serializers.BooleanField(required=False)
    modules = serializers.DictField(child=serializers.BooleanField(), required=False)


class AttachmentVaultPolicySerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    enabled = serializers.BooleanField(required=False)
    require_for_posting = serializers.BooleanField(required=False)
    allow_delete_after_posting = serializers.BooleanField(required=False)
    max_file_mb = serializers.IntegerField(required=False, min_value=1, max_value=100)
    required_documents = serializers.DictField(child=serializers.BooleanField(), required=False)


class PhaseOneOpeningPolicyAPIView(ControlsPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OpeningPolicySerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.controls_phase_one.view",)
    permission_denied_message = "You do not have permission to access opening policy controls."

    def get(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        entity_id = serializer.validated_data["entity"]
        self.enforce_scope(request, entity_id=entity_id)
        self.enforce_report_permission(request, entity_id=entity_id)
        opening_policy = resolve_opening_policy(entity_id)
        return Response(
            {
                "entity": entity_id,
                "opening_policy": opening_policy,
                "summary": summarize_opening_policy(opening_policy),
            }
        )

    def patch(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity_id = serializer.validated_data["entity"]
        self.enforce_scope(request, entity_id=entity_id)
        self.enforce_report_permission(
            request,
            entity_id=entity_id,
            required_permissions=("reports.financial_hub.controls_phase_one.update_policy",),
            message="You do not have permission to update opening policy controls.",
        )

        updates = {key: value for key, value in serializer.validated_data.items() if key != "entity"}
        old_policy = resolve_opening_policy(entity_id)
        opening_policy = update_opening_policy(
            entity_id=entity_id,
            updates=updates,
            created_by=getattr(request, "user", None),
        )
        record_controls_audit_event(
            request=request,
            entity_id=entity_id,
            module="opening_policy",
            action="policy_updated",
            old_data=old_policy,
            new_data={"policy": opening_policy, "updates": updates},
        )
        return Response(
            {
                "entity": entity_id,
                "opening_policy": opening_policy,
                "summary": summarize_opening_policy(opening_policy),
            }
        )


class PhaseOneRecurringJournalsAPIView(ControlsPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RecurringJournalPolicySerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.controls_phase_one.view",)
    permission_denied_message = "You do not have permission to access recurring journal controls."

    def get(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        entity_id = serializer.validated_data["entity"]
        self.enforce_scope(request, entity_id=entity_id)
        self.enforce_report_permission(request, entity_id=entity_id)
        policy = resolve_recurring_journal_policy(entity_id)
        return Response(
            {
                "entity": entity_id,
                "recurring_journal_policy": policy,
                "summary": summarize_recurring_journal_policy(policy),
                "readiness": build_recurring_journal_readiness(entity_id),
            }
        )

    def patch(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity_id = serializer.validated_data["entity"]
        self.enforce_scope(request, entity_id=entity_id)
        self.enforce_report_permission(
            request,
            entity_id=entity_id,
            required_permissions=("reports.financial_hub.controls_phase_one.update_policy",),
            message="You do not have permission to update recurring journal controls.",
        )
        updates = {key: value for key, value in serializer.validated_data.items() if key != "entity"}
        old_policy = resolve_recurring_journal_policy(entity_id)
        policy = update_recurring_journal_policy(
            entity_id=entity_id,
            updates=updates,
            created_by=getattr(request, "user", None),
        )
        record_controls_audit_event(
            request=request,
            entity_id=entity_id,
            module="recurring_journals",
            action="policy_updated",
            old_data=old_policy,
            new_data={"policy": policy, "updates": updates},
        )
        return Response(
            {
                "entity": entity_id,
                "recurring_journal_policy": policy,
                "summary": summarize_recurring_journal_policy(policy),
                "readiness": build_recurring_journal_readiness(entity_id),
            }
        )


class PhaseOneRecurringJournalRunAPIView(ControlsPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RecurringJournalRunSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.controls_phase_one.view",)
    permission_denied_message = "You do not have permission to run recurring journal controls."

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity_id = scope["entity"]
        self.enforce_scope(
            request,
            entity_id=entity_id,
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(
            request,
            entity_id=entity_id,
            required_permissions=("reports.financial_hub.controls_phase_one.update_policy",),
            message="You do not have permission to run recurring journal controls.",
        )
        result = mark_recurring_journal_run(
            entity_id=entity_id,
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            run_date=scope.get("run_date"),
            created_by=getattr(request, "user", None),
            retry_failed=scope.get("retry_failed", False),
        )
        record_controls_audit_event(
            request=request,
            entity_id=entity_id,
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            module="recurring_journals",
            action="recurring_journal_run_marked",
            new_data={
                "run_date": result.get("run_date"),
                "templates_reviewed": result.get("templates_reviewed"),
                "vouchers_created": result.get("vouchers_created"),
                "created_vouchers": result.get("created_vouchers"),
                "templates": result.get("templates"),
                "status": result.get("status"),
                "failed_templates": result.get("failed_templates"),
                "retry_failed": scope.get("retry_failed", False),
            },
        )
        return Response(result)


class PhaseOneApprovalWorkflowAPIView(ControlsPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ApprovalWorkflowPolicySerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.controls_phase_one.view",)
    permission_denied_message = "You do not have permission to access approval workflow controls."

    def get(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        entity_id = serializer.validated_data["entity"]
        self.enforce_scope(request, entity_id=entity_id)
        self.enforce_report_permission(request, entity_id=entity_id)
        policy = resolve_approval_workflow_policy(entity_id)
        return Response(
            {
                "entity": entity_id,
                "approval_workflow_policy": policy,
                "summary": summarize_approval_workflow_policy(policy),
                "readiness": build_approval_workflow_readiness(entity_id),
            }
        )

    def patch(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity_id = serializer.validated_data["entity"]
        self.enforce_scope(request, entity_id=entity_id)
        self.enforce_report_permission(
            request,
            entity_id=entity_id,
            required_permissions=("reports.financial_hub.controls_phase_one.update_policy",),
            message="You do not have permission to update approval workflow controls.",
        )
        updates = {key: value for key, value in serializer.validated_data.items() if key != "entity"}
        old_policy = resolve_approval_workflow_policy(entity_id)
        policy = update_approval_workflow_policy(
            entity_id=entity_id,
            updates=updates,
            created_by=getattr(request, "user", None),
        )
        record_controls_audit_event(
            request=request,
            entity_id=entity_id,
            module="approval_workflow",
            action="policy_updated",
            old_data=old_policy,
            new_data={"policy": policy, "updates": updates},
        )
        return Response(
            {
                "entity": entity_id,
                "approval_workflow_policy": policy,
                "summary": summarize_approval_workflow_policy(policy),
                "readiness": build_approval_workflow_readiness(entity_id),
            }
        )


class PhaseOneAuditTrailAPIView(ControlsPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AuditTrailPolicySerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.controls_phase_one.view",)
    permission_denied_message = "You do not have permission to access audit trail controls."

    def get(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        entity_id = serializer.validated_data["entity"]
        self.enforce_scope(request, entity_id=entity_id)
        self.enforce_report_permission(request, entity_id=entity_id)
        policy = resolve_audit_trail_policy(entity_id)
        return Response(
            {
                "entity": entity_id,
                "audit_trail_policy": policy,
                "summary": summarize_audit_trail_policy(policy, entity_id=entity_id),
                "readiness": build_audit_trail_readiness(entity_id),
            }
        )

    def patch(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity_id = serializer.validated_data["entity"]
        self.enforce_scope(request, entity_id=entity_id)
        self.enforce_report_permission(
            request,
            entity_id=entity_id,
            required_permissions=("reports.financial_hub.controls_phase_one.update_policy",),
            message="You do not have permission to update audit trail controls.",
        )
        updates = {key: value for key, value in serializer.validated_data.items() if key != "entity"}
        old_policy = resolve_audit_trail_policy(entity_id)
        policy = update_audit_trail_policy(
            entity_id=entity_id,
            updates=updates,
            created_by=getattr(request, "user", None),
        )
        record_controls_audit_event(
            request=request,
            entity_id=entity_id,
            module="audit_trail",
            action="policy_updated",
            old_data=old_policy,
            new_data={"policy": policy, "updates": updates},
        )
        return Response(
            {
                "entity": entity_id,
                "audit_trail_policy": policy,
                "summary": summarize_audit_trail_policy(policy, entity_id=entity_id),
                "readiness": build_audit_trail_readiness(entity_id),
            }
        )


class PhaseOneAuditActivityAPIView(ControlsPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PhaseOneAuditActivitySerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.controls_phase_one.view",)
    permission_denied_message = "You do not have permission to access audit trail activity."

    def get(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity_id = scope["entity"]
        self.enforce_scope(
            request,
            entity_id=entity_id,
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(request, entity_id=entity_id)
        with profile_controls_block(
            "controls.phase_one.audit_activity",
            **controls_scope_fields(
                request=request,
                entity_id=entity_id,
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
                module=scope.get("module") or None,
                limit=scope.get("limit") or 50,
            ),
        ) as perf:
            activity = build_controls_audit_activity(
                entity_id=entity_id,
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
                module=scope.get("module") or None,
                user_id=scope.get("user"),
                date_from=scope.get("date_from"),
                date_to=scope.get("date_to"),
                limit=scope.get("limit") or 50,
            )
            perf["events"] = (activity.get("summary") or {}).get("total") or 0
        return Response(activity)


class PhaseOneAuditActivityExportAPIView(ControlsPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PhaseOneAuditActivityExportSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.controls_phase_one.view",)
    permission_denied_message = "You do not have permission to export audit trail activity."

    def get(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        entity_id = scope["entity"]
        self.enforce_scope(
            request,
            entity_id=entity_id,
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(request, entity_id=entity_id)
        export_format = scope.get("format") or "csv"
        with profile_controls_block(
            "controls.phase_one.audit_activity_export",
            **controls_scope_fields(
                request=request,
                entity_id=entity_id,
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
                export_format=export_format,
                module=scope.get("module") or None,
                limit=scope.get("limit") or 200,
            ),
        ) as perf:
            activity = build_controls_audit_activity(
                entity_id=entity_id,
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
                module=scope.get("module") or None,
                user_id=scope.get("user"),
                date_from=scope.get("date_from"),
                date_to=scope.get("date_to"),
                limit=scope.get("limit") or 200,
            )
            perf["events"] = (activity.get("summary") or {}).get("total") or 0
        rows = [
            [
                event.get("timestamp") or "-",
                event.get("module_label") or "-",
                event.get("action_label") or "-",
                (event.get("actor") or {}).get("name") or (event.get("actor") or {}).get("username") or "System",
                event.get("method") or "-",
                event.get("detail") or "",
            ]
            for event in activity.get("events") or []
        ]
        section = ExportSection(
            title="Audit Activity",
            headers=["Timestamp", "Module", "Action", "Actor", "Method", "Detail"],
            rows=rows,
            center_columns={4},
            col_widths=[120, 95, 125, 110, 55, 190],
            empty_message="No audit activity matched the selected filters.",
        )
        meta_items = [
            ("Entity", str(entity_id)),
            ("Financial Year", str(scope.get("entityfinid") or "All")),
            ("Subentity", str(scope.get("subentity") or "All")),
            ("Module", scope.get("module") or "All"),
            ("Date From", scope.get("date_from").isoformat() if scope.get("date_from") else "All"),
            ("Date To", scope.get("date_to").isoformat() if scope.get("date_to") else "All"),
            ("Events", str((activity.get("summary") or {}).get("total") or 0)),
        ]
        record_controls_audit_event(
            request=request,
            entity_id=entity_id,
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            module="audit_trail",
            action="audit_activity_exported",
            new_data={
                "format": export_format,
                "filters": activity.get("filters") or {},
                "events": (activity.get("summary") or {}).get("total") or 0,
            },
        )
        if export_format == "pdf":
            content = write_sectioned_pdf(
                title="Financial Controls Audit Activity",
                subtitle="Phase One Controls",
                meta_items=meta_items,
                sections=[section],
            )
            response = HttpResponse(content, content_type="application/pdf")
            response["Content-Disposition"] = 'attachment; filename="financial_controls_audit_activity.pdf"'
            return response

        content = write_sectioned_csv(title="Financial Controls Audit Activity", meta_items=meta_items, sections=[section])
        response = HttpResponse(content, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="financial_controls_audit_activity.csv"'
        return response


class PhaseOneAttachmentVaultAPIView(ControlsPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AttachmentVaultPolicySerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.controls_phase_one.view",)
    permission_denied_message = "You do not have permission to access attachment vault controls."

    def get(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        entity_id = serializer.validated_data["entity"]
        self.enforce_scope(request, entity_id=entity_id)
        self.enforce_report_permission(request, entity_id=entity_id)
        policy = resolve_attachment_vault_policy(entity_id)
        return Response(
            {
                "entity": entity_id,
                "attachment_vault_policy": policy,
                "summary": summarize_attachment_vault_policy(policy, entity_id=entity_id),
                "readiness": build_attachment_vault_readiness(entity_id),
            }
        )

    def patch(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity_id = serializer.validated_data["entity"]
        self.enforce_scope(request, entity_id=entity_id)
        self.enforce_report_permission(
            request,
            entity_id=entity_id,
            required_permissions=("reports.financial_hub.controls_phase_one.update_policy",),
            message="You do not have permission to update attachment vault controls.",
        )
        updates = {key: value for key, value in serializer.validated_data.items() if key != "entity"}
        old_policy = resolve_attachment_vault_policy(entity_id)
        policy = update_attachment_vault_policy(
            entity_id=entity_id,
            updates=updates,
            created_by=getattr(request, "user", None),
        )
        record_controls_audit_event(
            request=request,
            entity_id=entity_id,
            module="attachment_vault",
            action="policy_updated",
            old_data=old_policy,
            new_data={"policy": policy, "updates": updates},
        )
        return Response(
            {
                "entity": entity_id,
                "attachment_vault_policy": policy,
                "summary": summarize_attachment_vault_policy(policy, entity_id=entity_id),
                "readiness": build_attachment_vault_readiness(entity_id),
            }
        )


class OpeningPreviewScopeSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)


class PhaseOneOpeningPreviewAPIView(ControlsPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OpeningPreviewScopeSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.controls_phase_one.view",)
    permission_denied_message = "You do not have permission to access opening preview controls."

    def get(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(request, entity_id=scope["entity"])
        with profile_controls_block(
            "controls.phase_one.opening_preview",
            **controls_scope_fields(request=request, entity_id=scope["entity"], entityfin_id=scope.get("entityfinid"), subentity_id=scope.get("subentity")),
        ) as perf:
            payload = build_opening_preview(
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
            )
            perf["status"] = payload.get("status") or payload.get("report_code")
            perf["entries"] = len(payload.get("entries") or [])
        return Response(payload)

class OpeningGenerationSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)


class OpeningLifecycleSerializer(OpeningGenerationSerializer):
    action = serializers.ChoiceField(choices=["ready_for_review", "approved", "lock"])


class PhaseOneOpeningGenerateAPIView(ControlsPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OpeningGenerationSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.controls_phase_one.generate_opening",)
    permission_denied_message = "You do not have permission to generate opening balances."

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(request, entity_id=scope["entity"])
        with profile_controls_block(
            "controls.phase_one.opening_generate",
            **controls_scope_fields(request=request, entity_id=scope["entity"], entityfin_id=scope.get("entityfinid"), subentity_id=scope.get("subentity")),
        ) as perf:
            result = build_opening_generation(
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
                executed_by=getattr(request, "user", None),
            )
            perf["status"] = result.get("status")
            perf["destination_year"] = result.get("destination_year")
        record_controls_audit_event(
            request=request,
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            module="opening_generation",
            action="opening_generated",
            new_data={"message": result.get("message"), "destination_year": result.get("destination_year")},
        )
        return Response(result)


class PhaseOneOpeningLifecycleAPIView(ControlsPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OpeningLifecycleSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.controls_phase_one.generate_opening",)
    permission_denied_message = "You do not have permission to update opening lifecycle."

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(request, entity_id=scope["entity"])
        with profile_controls_block(
            "controls.phase_one.opening_lifecycle",
            **controls_scope_fields(
                request=request,
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
                lifecycle_action=scope["action"],
            ),
        ) as perf:
            if scope["action"] == "lock":
                result = lock_opening_generation(
                    entity_id=scope["entity"],
                    entityfin_id=scope.get("entityfinid"),
                    subentity_id=scope.get("subentity"),
                    actor=getattr(request, "user", None),
                )
            else:
                result = mark_opening_lifecycle(
                    entity_id=scope["entity"],
                    entityfin_id=scope.get("entityfinid"),
                    subentity_id=scope.get("subentity"),
                    action=scope["action"],
                    actor=getattr(request, "user", None),
                )
            perf["status"] = result.get("status")
            perf["lifecycle_state"] = (result.get("lifecycle") or {}).get("status")
        record_controls_audit_event(
            request=request,
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            module="opening_generation",
            action=f"opening_{scope['action']}",
            new_data={"message": result.get("message"), "lifecycle": result.get("lifecycle")},
        )
        return Response(result)


class PhaseOneOpeningRollbackAPIView(ControlsPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OpeningGenerationSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.controls_phase_one.rollback_opening",)
    permission_denied_message = "You do not have permission to roll back opening balances."

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(request, entity_id=scope["entity"])
        with profile_controls_block(
            "controls.phase_one.opening_rollback",
            **controls_scope_fields(request=request, entity_id=scope["entity"], entityfin_id=scope.get("entityfinid"), subentity_id=scope.get("subentity")),
        ) as perf:
            result = build_opening_generation_rollback(
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
                executed_by=getattr(request, "user", None),
            )
            perf["status"] = result.get("status")
            perf["removed_entry_id"] = result.get("removed_entry_id")
        record_controls_audit_event(
            request=request,
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            module="opening_generation",
            action="opening_rolled_back",
            new_data={"message": result.get("message"), "removed_entry_id": result.get("removed_entry_id")},
        )
        return Response(result)


class PostingSetupScopeSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)


class PostingSetupTargetOverrideSerializer(serializers.Serializer):
    code = serializers.CharField()
    enabled = serializers.BooleanField(required=False)
    editable_ledger_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    suggested_ledger_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    editable_account_preference = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    account_preference = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class PostingSetupApplySerializer(PostingSetupScopeSerializer):
    targets = PostingSetupTargetOverrideSerializer(many=True, required=False)


class PhaseOnePostingSetupPreviewAPIView(ControlsPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PostingSetupScopeSerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.posting_setup.view",)
    permission_denied_message = "You do not have permission to access posting setup."

    def get(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(request, entity_id=scope["entity"])
        return Response(
            build_posting_setup_preview(
                entity_id=scope["entity"],
                entityfin_id=scope.get("entityfinid"),
                subentity_id=scope.get("subentity"),
            )
        )


class PhaseOnePostingSetupApplyAPIView(ControlsPermissionMixin, ScopedEntitlementMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PostingSetupApplySerializer
    subscription_feature_code = SubscriptionLimitCodes.FEATURE_REPORTING
    subscription_access_mode = SubscriptionService.ACCESS_MODE_OPERATIONAL
    required_permission_codes = ("reports.financial_hub.posting_setup.apply",)
    permission_denied_message = "You do not have permission to apply posting setup."

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        scope = serializer.validated_data
        self.enforce_scope(
            request,
            entity_id=scope["entity"],
            entityfinid_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
        )
        self.enforce_report_permission(request, entity_id=scope["entity"])
        result = apply_posting_setup(
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            created_by=getattr(request, "user", None),
            target_overrides=scope.get("targets"),
        )
        record_controls_audit_event(
            request=request,
            entity_id=scope["entity"],
            entityfin_id=scope.get("entityfinid"),
            subentity_id=scope.get("subentity"),
            module="posting_setup",
            action="posting_setup_applied",
            new_data={"targets": scope.get("targets") or [], "result": result},
        )
        return Response(result)
