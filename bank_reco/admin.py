from django.contrib import admin

from .models import (
    BankReconciliationAuditLog,
    BankReconciliationMatch,
    BankReconciliationMatchBankLine,
    BankReconciliationMatchBookLine,
    BankReconciliationRun,
    BankStatementImport,
    BankStatementLine,
)


@admin.register(BankStatementImport)
class BankStatementImportAdmin(admin.ModelAdmin):
    list_display = ("import_code", "entity", "bank_account", "status", "source_file_type", "statement_from", "statement_to")
    search_fields = ("import_code", "source_file_name", "parser_key", "bank_account__bank_name")
    list_filter = ("status", "source_file_type", "entity")


@admin.register(BankStatementLine)
class BankStatementLineAdmin(admin.ModelAdmin):
    list_display = ("statement_import", "line_no", "txn_date", "reference_no", "debit_amount", "credit_amount", "reconciliation_status")
    search_fields = ("reference_no", "cheque_no", "narration")
    list_filter = ("reconciliation_status", "validation_status")


@admin.register(BankReconciliationRun)
class BankReconciliationRunAdmin(admin.ModelAdmin):
    list_display = ("run_code", "entity", "bank_account", "status", "statement_import", "statement_line_count")
    search_fields = ("run_code", "bank_account__bank_name")
    list_filter = ("status", "entity")


@admin.register(BankReconciliationMatch)
class BankReconciliationMatchAdmin(admin.ModelAdmin):
    list_display = ("match_code", "run", "status", "match_kind", "confidence_score", "matched_amount")
    search_fields = ("match_code", "run__run_code")
    list_filter = ("status", "match_kind")


@admin.register(BankReconciliationMatchBankLine)
class BankReconciliationMatchBankLineAdmin(admin.ModelAdmin):
    list_display = ("match", "statement_line", "allocated_amount", "allocation_order")


@admin.register(BankReconciliationMatchBookLine)
class BankReconciliationMatchBookLineAdmin(admin.ModelAdmin):
    list_display = ("match", "journal_line", "allocated_amount", "allocation_order")


@admin.register(BankReconciliationAuditLog)
class BankReconciliationAuditLogAdmin(admin.ModelAdmin):
    list_display = ("run", "action", "actor", "created_at")
    search_fields = ("action", "run__run_code")
    list_filter = ("action",)

