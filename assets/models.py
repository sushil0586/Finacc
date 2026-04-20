from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models.base import TrackingModel

User = settings.AUTH_USER_MODEL


def default_asset_policy_controls():
    return {
        "capitalization_basis": "manual_or_posting",
        "capitalization_threshold_rule": "warn",
        "depreciation_proration": "daily",
        "depreciation_posting_mode": "manual_run",
        "depreciation_lock_rule": "hard",
        "backdated_capitalization_rule": "warn",
        "backdated_disposal_rule": "hard",
        "negative_nbv_rule": "block",
        "component_accounting": "off",
        "allow_manual_depreciation_override": "warn",
        "allow_posting_without_tag": "on",
        "multi_book_mode": "single",
    }


class AssetSettings(TrackingModel):
    class DefaultWorkflowAction(models.TextChoices):
        DRAFT = "draft", "Save as Draft"
        CONFIRM = "confirm", "Auto Confirm on Save"
        POST = "post", "Auto Post on Save"

    class DefaultDepreciationMethod(models.TextChoices):
        SLM = "SLM", "Straight Line Method"
        WDV = "WDV", "Written Down Value"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="asset_settings")
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True, related_name="asset_settings_scope")

    default_doc_code_asset = models.CharField(max_length=10, default="FA")
    default_doc_code_disposal = models.CharField(max_length=10, default="FAD")
    default_workflow_action = models.CharField(
        max_length=10,
        choices=DefaultWorkflowAction.choices,
        default=DefaultWorkflowAction.DRAFT,
        db_index=True,
    )

    default_depreciation_method = models.CharField(
        max_length=10,
        choices=DefaultDepreciationMethod.choices,
        default=DefaultDepreciationMethod.SLM,
    )
    default_useful_life_months = models.PositiveIntegerField(default=60)
    default_residual_value_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    depreciation_posting_day = models.PositiveSmallIntegerField(default=30)
    allow_multiple_asset_books = models.BooleanField(default=False)
    auto_post_depreciation = models.BooleanField(default=False)
    auto_number_assets = models.BooleanField(default=True)
    require_asset_tag = models.BooleanField(default=False)
    enable_component_accounting = models.BooleanField(default=False)
    enable_impairment_tracking = models.BooleanField(default=True)
    capitalization_threshold = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    policy_controls = models.JSONField(default=default_asset_policy_controls, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("entity", "subentity"), name="uq_asset_settings_entity_subentity"),
        ]
        indexes = [
            models.Index(fields=["entity"], name="ix_asset_settings_entity"),
            models.Index(fields=["entity", "subentity"], name="ix_asset_settings_scope"),
        ]

    def __str__(self) -> str:
        return f"AssetSettings(entity={self.entity_id}, subentity={self.subentity_id})"


class AssetCategory(TrackingModel):
    class AssetNature(models.TextChoices):
        TANGIBLE = "TANGIBLE", "Tangible"
        INTANGIBLE = "INTANGIBLE", "Intangible"
        ROU = "ROU", "Right-of-Use"
        CAPITAL_WIP = "CWIP", "Capital Work In Progress"

    class DepreciationMethod(models.TextChoices):
        SLM = "SLM", "Straight Line Method"
        WDV = "WDV", "Written Down Value"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="asset_categories")
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True, related_name="asset_category_scope")

    code = models.CharField(max_length=30)
    name = models.CharField(max_length=255)
    nature = models.CharField(max_length=12, choices=AssetNature.choices, default=AssetNature.TANGIBLE, db_index=True)
    depreciation_method = models.CharField(max_length=10, choices=DepreciationMethod.choices, default=DepreciationMethod.SLM)
    useful_life_months = models.PositiveIntegerField(default=60)
    residual_value_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    capitalization_threshold = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    asset_ledger = models.ForeignKey("financial.Ledger", on_delete=models.PROTECT, null=True, blank=True, related_name="asset_category_asset_ledgers")
    accumulated_depreciation_ledger = models.ForeignKey("financial.Ledger", on_delete=models.PROTECT, null=True, blank=True, related_name="asset_category_acc_dep_ledgers")
    depreciation_expense_ledger = models.ForeignKey("financial.Ledger", on_delete=models.PROTECT, null=True, blank=True, related_name="asset_category_dep_expense_ledgers")
    impairment_expense_ledger = models.ForeignKey("financial.Ledger", on_delete=models.PROTECT, null=True, blank=True, related_name="asset_category_impairment_expense_ledgers")
    impairment_reserve_ledger = models.ForeignKey("financial.Ledger", on_delete=models.PROTECT, null=True, blank=True, related_name="asset_category_impairment_reserve_ledgers")
    cwip_ledger = models.ForeignKey("financial.Ledger", on_delete=models.PROTECT, null=True, blank=True, related_name="asset_category_cwip_ledgers")
    gain_on_sale_ledger = models.ForeignKey("financial.Ledger", on_delete=models.PROTECT, null=True, blank=True, related_name="asset_category_gain_ledgers")
    loss_on_sale_ledger = models.ForeignKey("financial.Ledger", on_delete=models.PROTECT, null=True, blank=True, related_name="asset_category_loss_ledgers")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("entity", "subentity", "code"), name="uq_asset_category_scope_code"),
            models.UniqueConstraint(fields=("entity", "subentity", "name"), name="uq_asset_category_scope_name"),
            models.CheckConstraint(check=Q(useful_life_months__gt=0), name="ck_asset_category_life_gt_zero"),
        ]
        indexes = [
            models.Index(fields=["entity", "subentity", "code"], name="ix_asset_category_scope_code"),
            models.Index(fields=["entity", "subentity", "nature"], name="ix_asset_category_scope_nature"),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class AssetBulkJob(TrackingModel):
    class ScopeType(models.TextChoices):
        CATEGORY = "CATEGORY", "Category"
        ASSET = "ASSET", "Fixed Asset"

    class JobType(models.TextChoices):
        VALIDATE = "validate", "Validate"
        IMPORT = "import", "Import"
        TEMPLATE = "template", "Template"
        EXPORT = "export", "Export"

    class JobStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class FileFormat(models.TextChoices):
        XLSX = "xlsx", "XLSX"
        CSV = "csv", "CSV"

    class UpsertMode(models.TextChoices):
        CREATE_ONLY = "create_only", "Create only"
        UPDATE_ONLY = "update_only", "Update only"
        UPSERT = "upsert", "Upsert"

    class DuplicateStrategy(models.TextChoices):
        FAIL = "fail", "Fail"
        SKIP = "skip", "Skip"
        OVERWRITE = "overwrite", "Overwrite"

    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE, related_name="asset_bulk_jobs")
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.CASCADE, null=True, blank=True, related_name="asset_bulk_jobs")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    scope_type = models.CharField(max_length=20, choices=ScopeType.choices, db_index=True)
    job_type = models.CharField(max_length=20, choices=JobType.choices, default=JobType.VALIDATE, db_index=True)
    status = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.PENDING, db_index=True)
    file_format = models.CharField(max_length=10, choices=FileFormat.choices, default=FileFormat.XLSX)
    upsert_mode = models.CharField(max_length=20, choices=UpsertMode.choices, default=UpsertMode.UPSERT)
    duplicate_strategy = models.CharField(max_length=20, choices=DuplicateStrategy.choices, default=DuplicateStrategy.FAIL)

    validation_token = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    input_filename = models.CharField(max_length=255, null=True, blank=True)

    summary = models.JSONField(default=dict, blank=True)
    errors = models.JSONField(default=list, blank=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["entity", "scope_type", "job_type", "status"], name="ix_asset_bulk_entity_scope_job"),
            models.Index(fields=["entity", "validation_token"], name="ix_asset_bulk_entity_token"),
        ]

    def __str__(self) -> str:
        return f"AssetBulkJob<{self.id}> {self.scope_type} {self.job_type} {self.status}"


class FixedAsset(TrackingModel):
    class AssetStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        CAPITAL_WIP = "CAPITAL_WIP", "Capital WIP"
        ACTIVE = "ACTIVE", "Active"
        HELD_FOR_SALE = "HELD_FOR_SALE", "Held for Sale"
        DISPOSED = "DISPOSED", "Disposed"
        SCRAPPED = "SCRAPPED", "Scrapped"
        TRANSFERRED = "TRANSFERRED", "Transferred"

    class DepreciationMethod(models.TextChoices):
        SLM = "SLM", "Straight Line Method"
        WDV = "WDV", "Written Down Value"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="fixed_assets")
    entityfinid = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.PROTECT, null=True, blank=True, related_name="fixed_assets_opened")
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True, related_name="fixed_assets_scope")

    category = models.ForeignKey(AssetCategory, on_delete=models.PROTECT, related_name="assets")
    ledger = models.ForeignKey("financial.Ledger", on_delete=models.PROTECT, null=True, blank=True, related_name="fixed_assets")

    asset_code = models.CharField(max_length=50)
    asset_name = models.CharField(max_length=255)
    asset_tag = models.CharField(max_length=100, null=True, blank=True)
    serial_number = models.CharField(max_length=100, null=True, blank=True)
    manufacturer = models.CharField(max_length=255, null=True, blank=True)
    model_number = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(max_length=20, choices=AssetStatus.choices, default=AssetStatus.DRAFT, db_index=True)

    acquisition_date = models.DateField()
    capitalization_date = models.DateField(null=True, blank=True, db_index=True)
    put_to_use_date = models.DateField(null=True, blank=True)
    depreciation_start_date = models.DateField(null=True, blank=True, db_index=True)
    disposal_date = models.DateField(null=True, blank=True, db_index=True)

    quantity = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("1.0000"))
    gross_block = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    residual_value = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    useful_life_months = models.PositiveIntegerField(default=60)
    depreciation_method = models.CharField(max_length=10, choices=DepreciationMethod.choices, default=DepreciationMethod.SLM)
    depreciation_rate = models.DecimalField(max_digits=9, decimal_places=4, default=Decimal("0.0000"))

    accumulated_depreciation = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    impairment_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    net_book_value = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    location_name = models.CharField(max_length=255, null=True, blank=True)
    department_name = models.CharField(max_length=255, null=True, blank=True)
    custodian_name = models.CharField(max_length=255, null=True, blank=True)
    vendor_account = models.ForeignKey("financial.account", on_delete=models.PROTECT, null=True, blank=True, related_name="fixed_asset_vendors")
    capitalization_posting_batch = models.ForeignKey("posting.PostingBatch", on_delete=models.SET_NULL, null=True, blank=True, related_name="capitalized_assets")
    impairment_posting_batch = models.ForeignKey("posting.PostingBatch", on_delete=models.SET_NULL, null=True, blank=True, related_name="impaired_assets")
    disposal_posting_batch = models.ForeignKey("posting.PostingBatch", on_delete=models.SET_NULL, null=True, blank=True, related_name="disposed_assets")
    disposal_proceeds = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    disposal_gain_loss = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    purchase_document_no = models.CharField(max_length=100, null=True, blank=True)
    external_reference = models.CharField(max_length=100, null=True, blank=True)
    notes = models.CharField(max_length=500, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("entity", "asset_code"), name="uq_fixed_asset_entity_code"),
            models.UniqueConstraint(
                fields=("entity", "asset_tag"),
                condition=Q(asset_tag__isnull=False),
                name="uq_fixed_asset_entity_tag",
            ),
            models.CheckConstraint(check=Q(gross_block__gte=0), name="ck_fixed_asset_gross_nonneg"),
            models.CheckConstraint(check=Q(accumulated_depreciation__gte=0), name="ck_fixed_asset_accdep_nonneg"),
            models.CheckConstraint(check=Q(impairment_amount__gte=0), name="ck_fixed_asset_impairment_nonneg"),
            models.CheckConstraint(check=Q(useful_life_months__gt=0), name="ck_fixed_asset_life_gt_zero"),
        ]
        indexes = [
            models.Index(fields=["entity", "status"], name="ix_fixed_asset_entity_status"),
            models.Index(fields=["entity", "category", "status"], name="ix_fa_ent_cat_stat"),
            models.Index(fields=["entity", "capitalization_date"], name="ix_fa_ent_capdate"),
            models.Index(fields=["entity", "depreciation_start_date"], name="ix_fa_ent_depstart"),
        ]

    def __str__(self) -> str:
        return f"{self.asset_code} - {self.asset_name}"


class DepreciationRun(TrackingModel):
    class RunStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        CALCULATED = "CALCULATED", "Calculated"
        POSTED = "POSTED", "Posted"
        CANCELLED = "CANCELLED", "Cancelled"

    entity = models.ForeignKey("entity.Entity", on_delete=models.PROTECT, related_name="asset_depreciation_runs")
    entityfinid = models.ForeignKey("entity.EntityFinancialYear", on_delete=models.PROTECT, related_name="asset_depreciation_runs")
    subentity = models.ForeignKey("entity.SubEntity", on_delete=models.PROTECT, null=True, blank=True, related_name="asset_depreciation_runs_scope")

    run_code = models.CharField(max_length=50)
    period_from = models.DateField(db_index=True)
    period_to = models.DateField(db_index=True)
    posting_date = models.DateField(db_index=True)
    status = models.CharField(max_length=12, choices=RunStatus.choices, default=RunStatus.DRAFT, db_index=True)
    depreciation_method = models.CharField(max_length=10, default="SLM")
    total_assets = models.PositiveIntegerField(default=0)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    posting_batch = models.ForeignKey("posting.PostingBatch", on_delete=models.SET_NULL, null=True, blank=True, related_name="asset_depreciation_runs")
    note = models.CharField(max_length=500, null=True, blank=True)
    calculated_at = models.DateTimeField(null=True, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="asset_depreciation_runs_posted")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("entity", "entityfinid", "subentity", "run_code"), name="uq_asset_dep_run_scope_code"),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "subentity", "posting_date"], name="ix_fa_dep_scope_dt"),
        ]

    def __str__(self) -> str:
        return f"{self.run_code} ({self.period_from} - {self.period_to})"


class DepreciationRunLine(models.Model):
    run = models.ForeignKey(DepreciationRun, on_delete=models.CASCADE, related_name="lines")
    asset = models.ForeignKey(FixedAsset, on_delete=models.PROTECT, related_name="depreciation_lines")
    period_from = models.DateField()
    period_to = models.DateField()
    opening_gross_block = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    opening_accumulated_depreciation = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    depreciation_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    closing_accumulated_depreciation = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    closing_net_book_value = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    is_manual_override = models.BooleanField(default=False)
    calculation_meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("run", "asset"), name="uq_asset_dep_run_asset"),
        ]
        indexes = [
            models.Index(fields=["asset", "period_to"], name="ix_fa_depline_ast_dt"),
        ]

    def __str__(self) -> str:
        return f"{self.run_id} - {self.asset_id}"
