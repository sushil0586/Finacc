from django.contrib import admin

from .models import (
    CapitalDistributionAuditEvent,
    CapitalDistributionAccountMapping,
    CapitalDistributionLine,
    CapitalDistributionRun,
    CapitalDistributionSegment,
    DistributionBalanceSnapshot,
    DistributionPolicyStakeholder,
    DistributionPolicyVersion,
    EntityFormationProfile,
)


@admin.register(CapitalDistributionAccountMapping)
class CapitalDistributionAccountMappingAdmin(admin.ModelAdmin):
    list_display = ("entity", "ownership", "capital_account", "current_account", "drawings_account", "isactive")
    list_filter = ("isactive",)
    search_fields = ("entity__entityname", "ownership__name")


class DistributionPolicyStakeholderInline(admin.TabularInline):
    model = DistributionPolicyStakeholder
    extra = 0


@admin.register(EntityFormationProfile)
class EntityFormationProfileAdmin(admin.ModelAdmin):
    list_display = ("entity", "formation_type", "strategy_code", "version_number", "status", "effective_from")
    list_filter = ("formation_type", "status", "isactive")
    search_fields = ("entity__entityname", "strategy_code", "resolution_hash")
    readonly_fields = ("resolution_hash", "evidence", "readiness_issues", "verified_at", "verified_by")


@admin.register(DistributionPolicyVersion)
class DistributionPolicyVersionAdmin(admin.ModelAdmin):
    list_display = ("entity", "formation_type", "version_number", "status", "effective_from", "effective_to")
    list_filter = ("formation_type", "status", "isactive")
    search_fields = ("entity__entityname", "governing_document_reference")
    readonly_fields = ("submitted_at", "submitted_by", "approved_at", "approved_by")
    inlines = (DistributionPolicyStakeholderInline,)


@admin.register(CapitalDistributionAuditEvent)
class CapitalDistributionAuditEventAdmin(admin.ModelAdmin):
    list_display = ("entity", "policy", "run", "action", "actor", "correlation_id", "created_at")
    list_filter = ("action", "isactive")
    search_fields = ("entity__entityname", "correlation_id", "reason")
    readonly_fields = (
        "entity",
        "policy",
        "run",
        "actor",
        "action",
        "correlation_id",
        "reason",
        "before_state",
        "after_state",
        "metadata",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CapitalDistributionSegmentInline(admin.TabularInline):
    model = CapitalDistributionSegment
    extra = 0
    readonly_fields = ("policy", "sequence", "period_from", "period_to", "days", "source_profit", "allocation_basis")
    can_delete = False


@admin.register(CapitalDistributionRun)
class CapitalDistributionRunAdmin(admin.ModelAdmin):
    list_display = ("entity", "entityfin", "period_from", "period_to", "status", "source_profit", "distributable_result")
    list_filter = ("status", "profit_source", "cadence", "isactive")
    search_fields = ("entity__entityname", "idempotency_key", "calculation_hash")
    readonly_fields = ("calculation_hash", "source_snapshot", "calculated_at", "calculated_by")
    inlines = (CapitalDistributionSegmentInline,)


@admin.register(CapitalDistributionLine)
class CapitalDistributionLineAdmin(admin.ModelAdmin):
    list_display = ("run", "stakeholder", "component_type", "amount", "side")
    list_filter = ("component_type", "side")
    readonly_fields = ("run", "segment", "stakeholder", "component_type", "basis_amount", "rate", "days", "amount", "side", "explanation", "source_references")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DistributionBalanceSnapshot)
class DistributionBalanceSnapshotAdmin(admin.ModelAdmin):
    list_display = ("run", "stakeholder", "cutoff_date", "capital_balance", "drawing_balance")
    readonly_fields = ("run", "stakeholder", "cutoff_date", "capital_balance", "drawing_balance", "movements", "source_references", "snapshot_hash")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
