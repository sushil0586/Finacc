from django.contrib import admin

from .models import (
    BankReconciliationAuditLog,
    BankReconciliationExceptionItem,
    BankReconciliationMatch,
    BankReconciliationMatchAllocation,
    BankReconciliationRule,
    BankStatementImportProfile,
    BankReconciliationSession,
    BankStatementBatch,
    BankStatementLine,
)


class BankStatementLineInline(admin.TabularInline):
    model = BankStatementLine
    extra = 0
    fields = ("line_no", "transaction_date", "description", "reference_number", "debit_amount", "credit_amount", "match_status")
    readonly_fields = ("line_no", "transaction_date", "description", "reference_number", "debit_amount", "credit_amount", "match_status")
    can_delete = False


class BankStatementBatchInline(admin.TabularInline):
    model = BankStatementBatch
    extra = 0
    fields = ("batch_code", "source_name", "source_format", "imported_row_count", "duplicate_row_count")
    readonly_fields = ("batch_code", "source_name", "source_format", "imported_row_count", "duplicate_row_count")
    can_delete = False


@admin.register(BankReconciliationSession)
class BankReconciliationSessionAdmin(admin.ModelAdmin):
    list_display = ("session_code", "entity", "entityfin", "subentity", "bank_account", "status", "imported_row_count", "matched_row_count", "difference_amount", "created_at")
    list_filter = ("status", "entity", "entityfin", "bank_account", "created_at")
    search_fields = ("session_code", "statement_label", "source_name", "entity__entityname", "bank_account__bank_name", "bank_account__account_number")
    autocomplete_fields = ("entity", "entityfin", "subentity", "createdby")
    raw_id_fields = ("bank_account",)
    inlines = [BankStatementBatchInline]
    readonly_fields = ("session_code", "created_at", "updated_at")


@admin.register(BankStatementBatch)
class BankStatementBatchAdmin(admin.ModelAdmin):
    list_display = ("batch_code", "session", "source_name", "source_format", "imported_row_count", "duplicate_row_count", "created_at")
    list_filter = ("source_format", "created_at")
    search_fields = ("batch_code", "source_name", "session__session_code")
    autocomplete_fields = ("session", "importedby")
    inlines = [BankStatementLineInline]
    readonly_fields = ("batch_code", "created_at", "updated_at")


@admin.register(BankStatementLine)
class BankStatementLineAdmin(admin.ModelAdmin):
    list_display = ("batch", "line_no", "transaction_date", "reference_number", "debit_amount", "credit_amount", "match_status")
    list_filter = ("match_status", "transaction_date", "value_date")
    search_fields = ("description", "reference_number", "counterparty", "batch__batch_code")
    readonly_fields = ("row_hash", "created_at", "updated_at")


@admin.register(BankReconciliationRule)
class BankReconciliationRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "entity", "rule_type", "priority", "is_active", "amount_tolerance", "date_window_days")
    list_filter = ("rule_type", "is_active", "entity")
    search_fields = ("name", "entity__entityname")
    autocomplete_fields = ("entity", "createdby")


@admin.register(BankStatementImportProfile)
class BankStatementImportProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "entity", "bank_account", "source_format", "is_active", "created_at")
    list_filter = ("source_format", "is_active", "entity")
    search_fields = ("name", "entity__entityname", "bank_account__bank_name")
    autocomplete_fields = ("entity", "createdby")
    raw_id_fields = ("bank_account",)


class BankReconciliationMatchAllocationInline(admin.TabularInline):
    model = BankReconciliationMatchAllocation
    extra = 0
    fields = ("allocation_order", "journal_line", "allocated_amount", "notes")
    readonly_fields = ("allocation_order", "journal_line", "allocated_amount", "notes")
    can_delete = False


@admin.register(BankReconciliationMatch)
class BankReconciliationMatchAdmin(admin.ModelAdmin):
    list_display = ("session", "match_kind", "matched_amount", "difference_amount", "confidence", "matched_at")
    list_filter = ("match_kind", "matched_at")
    search_fields = ("session__session_code", "notes")
    autocomplete_fields = ("session", "statement_line", "entry", "journal_line", "matchedby")
    inlines = [BankReconciliationMatchAllocationInline]


@admin.register(BankReconciliationMatchAllocation)
class BankReconciliationMatchAllocationAdmin(admin.ModelAdmin):
    list_display = ("match", "allocation_order", "journal_line", "allocated_amount")
    list_filter = ("created_at",)
    search_fields = ("match__session__session_code", "journal_line__voucher_no", "journal_line__description")
    autocomplete_fields = ("match", "journal_line", "createdby")


@admin.register(BankReconciliationAuditLog)
class BankReconciliationAuditLogAdmin(admin.ModelAdmin):
    list_display = ("session", "action", "actor", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("session__session_code", "action")
    autocomplete_fields = ("session", "actor")


@admin.register(BankReconciliationExceptionItem)
class BankReconciliationExceptionItemAdmin(admin.ModelAdmin):
    list_display = ("session", "statement_line", "exception_type", "status", "amount", "resolved_at")
    list_filter = ("exception_type", "status", "created_at")
    search_fields = ("session__session_code", "statement_line__description", "notes")
    autocomplete_fields = ("session", "statement_line", "createdby", "resolvedby")
